"""Dünner Wrapper um die LLM-API (OpenAI-kompatibler BFH-LiteLLM-Proxy).

Das ist der einzige Ort, an dem der Provider vorkommt. Tutor und Grader rufen
nur `chat()` auf und bekommen ein `LLMResult` zurück. JSON wird hier nicht
geparst, das macht der Grader mit Pydantic.

Sicherheit: Der API-Key wird nie geloggt, ausgegeben oder in Exceptions
weitergereicht. Provider-Exceptions werden in eigene Exceptions übersetzt
(`from None`), deren Text von Key-Mustern bereinigt ist.
"""

from __future__ import annotations

import random
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

import openai

from core.config import KEY_URL, LLMConfig, load_config

Message = dict[str, str]
T = TypeVar("T")

BACKOFF_BASE_S = 1.0
BACKOFF_CAP_S = 20.0

# Austauschbar im Test, damit Retries nicht wirklich warten.
_sleep: Callable[[float], None] = time.sleep

_client: openai.OpenAI | None = None
_config: LLMConfig | None = None

_THINK_BLOCK = re.compile(r"<think>.*?(</think>|\Z)", re.DOTALL | re.IGNORECASE)
_KEY_PATTERN = re.compile(r"sk-[A-Za-z0-9_\-]+")


@dataclass(frozen=True)
class LLMResult:
    """Ergebnis eines Chat-Aufrufs.

    `text` enthält nur den sichtbaren Antworttext (`message.content`), nie
    Reasoning. `warnings` ist leer, wenn alles normal war; sonst stehen dort
    z. B. leere oder abgeschnittene Antworten. `latency_ms` misst die gesamte
    Dauer inklusive Retries und JSON-Fallback.
    """

    text: str
    model: str
    temperature: float
    tokens_in: int | None
    tokens_out: int | None
    latency_ms: int
    json_mode_requested: bool
    json_mode_fallback: bool
    finish_reason: str | None
    warnings: list[str] = field(default_factory=list)


class LLMError(Exception):
    """Basisklasse. Enthält nie den API-Key."""


class LLMAuthError(LLMError):
    """401: Key ungültig oder abgelaufen. Wird nicht wiederholt."""


class LLMRequestError(LLMError):
    """Anfrage abgelehnt (4xx ausser 401/429). Wird nicht wiederholt."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class LLMUnavailableError(LLMError):
    """429, 5xx, Timeout oder Verbindungsfehler, auch nach allen Retries."""


def get_config() -> LLMConfig:
    """Lädt die Konfiguration einmal und gibt sie danach aus dem Cache zurück."""
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_client(config: LLMConfig | None = None) -> openai.OpenAI:
    """Gibt den einen, wiederverwendeten Client zurück (lazy erzeugt).

    SDK-eigene Retries sind aus, damit nur unsere Retry-Logik gilt.
    """
    global _client
    if _client is None:
        cfg = config or get_config()
        _client = openai.OpenAI(
            base_url=cfg.base_url,
            api_key=cfg.api_key.get_secret_value(),
            timeout=cfg.timeout_s,
            max_retries=0,
        )
    return _client


def chat(
    messages: list[Message],
    model: str,
    temperature: float,
    json_mode: bool = False,
    max_tokens: int | None = None,
    *,
    client: Any = None,
    config: LLMConfig | None = None,
) -> LLMResult:
    """Schickt `messages` an `model` und gibt ein `LLMResult` zurück.

    Mit `json_mode=True` wird `response_format={"type": "json_object"}`
    gesendet. Lehnt der Proxy das mit 400 ab, wird einmal ohne
    `response_format` wiederholt und `json_mode_fallback=True` gesetzt.

    `client` und `config` sind nur für Tests; normal werden der globale Client
    und die Konfiguration aus `.env` verwendet.

    Raises:
        LLMAuthError: Key ungültig oder abgelaufen (401).
        LLMRequestError: Anfrage abgelehnt (400, 404, …).
        LLMUnavailableError: Proxy nach allen Retries nicht erreichbar.
    """
    cfg = config or get_config()
    cl = client or get_client(cfg)

    kwargs: dict[str, Any] = {"model": model, "messages": messages, "temperature": temperature}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    start = time.perf_counter()
    fallback = False
    if json_mode:
        try:
            response = _with_retries(
                lambda: cl.chat.completions.create(**kwargs, response_format={"type": "json_object"}),
                cfg,
            )
        except LLMRequestError as exc:
            if exc.status_code != 400:
                raise
            fallback = True
            response = _with_retries(lambda: cl.chat.completions.create(**kwargs), cfg)
    else:
        response = _with_retries(lambda: cl.chat.completions.create(**kwargs), cfg)
    latency_ms = round((time.perf_counter() - start) * 1000)

    return _to_result(response, model, temperature, latency_ms, json_mode, fallback)


def list_models(*, client: Any = None, config: LLMConfig | None = None) -> list[str]:
    """Gibt die IDs aller Modelle zurück, die der Proxy anbietet (GET /models)."""
    cfg = config or get_config()
    cl = client or get_client(cfg)
    page = _with_retries(lambda: cl.models.list(), cfg)
    return sorted(m.id for m in page)


def _to_result(
    response: Any,
    model: str,
    temperature: float,
    latency_ms: int,
    json_mode: bool,
    fallback: bool,
) -> LLMResult:
    """Übersetzt die Provider-Antwort. Liest nur `message.content`."""
    warnings: list[str] = []
    text = ""
    finish_reason: str | None = None

    if response.choices:
        choice = response.choices[0]
        finish_reason = choice.finish_reason
        text = choice.message.content or ""
    else:
        warnings.append("Antwort ohne choices")

    stripped = _THINK_BLOCK.sub("", text)
    if stripped != text:
        warnings.append("Reasoning-Block (<think>) aus dem Text entfernt")
    text = stripped.strip()

    if not text:
        warnings.append("Leere Antwort (content leer)")
    if finish_reason == "length":
        warnings.append("Antwort abgeschnitten (finish_reason=length, max_tokens zu klein?)")

    usage = response.usage
    return LLMResult(
        text=text,
        model=model,
        temperature=temperature,
        tokens_in=usage.prompt_tokens if usage else None,
        tokens_out=usage.completion_tokens if usage else None,
        latency_ms=latency_ms,
        json_mode_requested=json_mode,
        json_mode_fallback=fallback,
        finish_reason=finish_reason,
        warnings=warnings,
    )


def _with_retries(call: Callable[[], T], cfg: LLMConfig) -> T:
    """Führt `call` aus, mit Retries bei 429, 5xx, Timeout und Verbindungsfehler.

    Höchstens `cfg.max_retries` Wiederholungen, exponentieller Backoff mit
    Jitter. Provider-Exceptions werden in `LLMError`-Unterklassen übersetzt.
    """
    key = cfg.api_key.get_secret_value()
    for attempt in range(cfg.max_retries + 1):
        try:
            return call()
        except openai.AuthenticationError:
            raise LLMAuthError(
                f"LLM-Proxy: Key ungültig oder abgelaufen (401). Neu generieren unter {KEY_URL} "
                "und in .env als LLM_API_KEY eintragen."
            ) from None
        except (openai.APIConnectionError, openai.RateLimitError, openai.InternalServerError) as exc:
            reason = _describe(exc)
        except openai.APIStatusError as exc:
            if exc.status_code < 500:
                detail = _redact(_provider_message(exc), key)
                raise LLMRequestError(
                    f"LLM-Proxy hat die Anfrage abgelehnt (HTTP {exc.status_code}): {detail}",
                    exc.status_code,
                ) from None
            reason = _describe(exc)

        if attempt == cfg.max_retries:
            raise LLMUnavailableError(
                f"LLM-Proxy nicht verfügbar nach {attempt + 1} Versuchen ({reason})."
            ) from None
        _sleep(_backoff(attempt))
    raise AssertionError("unreachable")  # pragma: no cover


def _backoff(attempt: int) -> float:
    """Exponentieller Backoff mit Jitter: 50–100 % von min(cap, base·2^n)."""
    return min(BACKOFF_CAP_S, BACKOFF_BASE_S * 2**attempt) * random.uniform(0.5, 1.0)


def _describe(exc: Exception) -> str:
    """Kurzbeschreibung ohne Provider-Text (kann Header oder Key enthalten)."""
    if isinstance(exc, openai.APITimeoutError):
        return "Timeout, VPN aktiv?"
    if isinstance(exc, openai.APIConnectionError):
        return "Verbindungsfehler, VPN aktiv?"
    if isinstance(exc, openai.APIStatusError):
        return f"HTTP {exc.status_code}"
    return type(exc).__name__


def _provider_message(exc: openai.APIStatusError) -> str:
    """Fehlermeldung aus dem Body, z. B. 'model not found'. Gekürzt."""
    body = exc.body
    msg: Any = None
    if isinstance(body, dict):
        err = body.get("error", body)
        msg = err.get("message") if isinstance(err, dict) else err
    return str(msg or type(exc).__name__)[:300]


def _redact(text: str, key: str) -> str:
    """Entfernt den Key und alles, was wie ein Key aussieht."""
    if key:
        text = text.replace(key, "[redacted]")
    return _KEY_PATTERN.sub("[redacted]", text)
