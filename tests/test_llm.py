"""Tests für core/llm.py und core/config.py. Nur gemockter Client, kein Netz."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx2
import openai
import pytest

from core import llm
from core.config import ConfigError, LLMConfig, load_config

FAKE_KEY = "sk-test-SUPERGEHEIM-1234567890"
REQUEST = httpx2.Request("POST", "https://proxy.test/v1/chat/completions")
ENV_VARS = ["LLM_BASE_URL", "LLM_API_KEY", "TUTOR_MODEL", "GRADER_MODEL", "LLM_TIMEOUT_S", "LLM_MAX_RETRIES"]


def _status_error(status: int, message: str = "fehler") -> openai.APIStatusError:
    """Baut die passende openai-Exception für einen HTTP-Status, ohne Netz."""
    response = httpx2.Response(status, request=REQUEST, json={"error": {"message": message}})
    cls = {
        400: openai.BadRequestError,
        401: openai.AuthenticationError,
        404: openai.NotFoundError,
        429: openai.RateLimitError,
    }.get(status, openai.InternalServerError if status >= 500 else openai.APIStatusError)
    return cls(message, response=response, body={"error": {"message": message}})


def _completion(
    content: str | None = "Antwort",
    finish_reason: str = "stop",
    reasoning: str | None = None,
) -> SimpleNamespace:
    message = SimpleNamespace(content=content, role="assistant")
    if reasoning is not None:
        message.reasoning_content = reasoning
    return SimpleNamespace(
        model="proxy-model-name",
        choices=[SimpleNamespace(message=message, finish_reason=finish_reason)],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=34),
    )


class FakeClient:
    """Gibt der Reihe nach die vorgegebenen Antworten zurück oder wirft sie."""

    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))
        self.models = SimpleNamespace(list=self._list)

    def _create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def _list(self) -> list[SimpleNamespace]:
        return [SimpleNamespace(id="b-model"), SimpleNamespace(id="a-model")]


@pytest.fixture
def cfg() -> LLMConfig:
    return LLMConfig(
        base_url="https://proxy.test/v1",
        api_key=FAKE_KEY,
        tutor_model="tutor",
        grader_model="grader",
        timeout_s=5,
        max_retries=3,
    )


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Ersetzt das Warten im Backoff und zeichnet die Wartezeiten auf."""
    recorded: list[float] = []
    monkeypatch.setattr(llm, "_sleep", recorded.append)
    return recorded


def _chat(client: FakeClient, cfg: LLMConfig, **kwargs: Any) -> llm.LLMResult:
    messages = [{"role": "user", "content": "Hallo"}]
    return llm.chat(messages, model="m", temperature=0.3, client=client, config=cfg, **kwargs)


# --- Erfolgsfall -------------------------------------------------------------


def test_success_fills_all_fields(cfg: LLMConfig, sleeps: list[float]) -> None:
    client = FakeClient(_completion("  Hallo Welt  "))
    res = _chat(client, cfg, max_tokens=50)

    assert res == llm.LLMResult(
        text="Hallo Welt",
        model="m",
        temperature=0.3,
        tokens_in=12,
        tokens_out=34,
        latency_ms=res.latency_ms,
        json_mode_requested=False,
        json_mode_fallback=False,
        finish_reason="stop",
        warnings=[],
    )
    assert isinstance(res.latency_ms, int) and res.latency_ms >= 0
    assert client.calls[0]["max_tokens"] == 50
    assert "response_format" not in client.calls[0]
    assert sleeps == []


def test_missing_usage_gives_none(cfg: LLMConfig) -> None:
    response = _completion()
    response.usage = None
    res = _chat(FakeClient(response), cfg)
    assert res.tokens_in is None and res.tokens_out is None


# --- Retries -----------------------------------------------------------------


@pytest.mark.parametrize("status", [429, 503])
def test_retry_then_success(cfg: LLMConfig, sleeps: list[float], status: int) -> None:
    client = FakeClient(_status_error(status), _status_error(status), _completion("ok"))
    res = _chat(client, cfg)
    assert res.text == "ok"
    assert len(client.calls) == 3
    assert len(sleeps) == 2


@pytest.mark.parametrize(
    "error",
    [openai.APITimeoutError(request=REQUEST), openai.APIConnectionError(request=REQUEST)],
    ids=["timeout", "connection"],
)
def test_retry_on_timeout_and_connection_error(cfg: LLMConfig, sleeps: list[float], error: Exception) -> None:
    client = FakeClient(error, _completion("ok"))
    assert _chat(client, cfg).text == "ok"
    assert len(sleeps) == 1


def test_gives_up_after_max_retries(cfg: LLMConfig, sleeps: list[float]) -> None:
    client = FakeClient(*[_status_error(503) for _ in range(10)])
    with pytest.raises(llm.LLMUnavailableError, match="4 Versuchen") as info:
        _chat(client, cfg)
    assert len(client.calls) == cfg.max_retries + 1
    assert len(sleeps) == cfg.max_retries
    assert info.value.__cause__ is None and info.value.__suppress_context__


def test_backoff_grows_with_jitter_and_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm.random, "uniform", lambda lo, hi: hi)
    assert [llm._backoff(n) for n in range(6)] == [1.0, 2.0, 4.0, 8.0, 16.0, 20.0]
    monkeypatch.setattr(llm.random, "uniform", lambda lo, hi: lo)
    assert llm._backoff(2) == 2.0


# --- Kein Retry bei 400 / 401 ------------------------------------------------


def test_no_retry_on_401_and_message_without_key(cfg: LLMConfig, sleeps: list[float]) -> None:
    client = FakeClient(_status_error(401, f"Invalid key {FAKE_KEY}"), _completion())
    with pytest.raises(llm.LLMAuthError) as info:
        _chat(client, cfg)
    message = str(info.value)
    assert "access.mlmp.ti.bfh.ch/my-key" in message
    assert "neu generieren" in message.lower()
    assert FAKE_KEY not in message and "SUPERGEHEIM" not in message
    assert info.value.__cause__ is None and info.value.__suppress_context__
    assert len(client.calls) == 1
    assert sleeps == []


def test_no_retry_on_400_without_json_mode(cfg: LLMConfig, sleeps: list[float]) -> None:
    client = FakeClient(_status_error(400, f"bad request, key was {FAKE_KEY} or sk-other-key"))
    with pytest.raises(llm.LLMRequestError) as info:
        _chat(client, cfg)
    assert info.value.status_code == 400
    assert FAKE_KEY not in str(info.value) and "sk-other-key" not in str(info.value)
    assert "[redacted]" in str(info.value)
    assert len(client.calls) == 1
    assert sleeps == []


def test_404_is_request_error_with_provider_message(cfg: LLMConfig) -> None:
    client = FakeClient(_status_error(404, "model not found"))
    with pytest.raises(llm.LLMRequestError, match="model not found") as info:
        _chat(client, cfg)
    assert info.value.status_code == 404


# --- json_mode ---------------------------------------------------------------


def test_json_mode_sends_response_format(cfg: LLMConfig) -> None:
    client = FakeClient(_completion('{"verdict": "not"}'))
    res = _chat(client, cfg, json_mode=True)
    assert client.calls[0]["response_format"] == {"type": "json_object"}
    assert res.json_mode_requested and not res.json_mode_fallback
    assert res.text == '{"verdict": "not"}'


def test_json_mode_falls_back_on_400(cfg: LLMConfig, sleeps: list[float]) -> None:
    client = FakeClient(_status_error(400, "response_format not supported"), _completion('{"verdict": "partial"}'))
    res = _chat(client, cfg, json_mode=True)
    assert res.json_mode_requested and res.json_mode_fallback
    assert "response_format" in client.calls[0]
    assert "response_format" not in client.calls[1]
    assert res.text == '{"verdict": "partial"}'
    assert sleeps == []


def test_json_mode_fallback_also_400_raises(cfg: LLMConfig) -> None:
    client = FakeClient(_status_error(400), _status_error(400))
    with pytest.raises(llm.LLMRequestError):
        _chat(client, cfg, json_mode=True)
    assert len(client.calls) == 2


def test_json_mode_no_fallback_on_other_4xx(cfg: LLMConfig) -> None:
    client = FakeClient(_status_error(404))
    with pytest.raises(llm.LLMRequestError):
        _chat(client, cfg, json_mode=True)
    assert len(client.calls) == 1


# --- Reasoning und Warnungen -------------------------------------------------


def test_reasoning_field_not_in_text(cfg: LLMConfig) -> None:
    client = FakeClient(_completion("Sichtbare Antwort", reasoning="GEHEIMES-REASONING"))
    res = _chat(client, cfg)
    assert res.text == "Sichtbare Antwort"
    assert "GEHEIMES-REASONING" not in repr(res)


def test_think_block_in_content_is_removed(cfg: LLMConfig) -> None:
    client = FakeClient(_completion("<think>GEHEIMES-REASONING</think>\nSichtbare Antwort"))
    res = _chat(client, cfg)
    assert res.text == "Sichtbare Antwort"
    assert any("Reasoning" in w for w in res.warnings)


def test_unclosed_think_block_is_removed(cfg: LLMConfig) -> None:
    client = FakeClient(_completion("<think>GEHEIMES-REASONING ohne Ende", finish_reason="length"))
    res = _chat(client, cfg)
    assert res.text == ""
    assert "GEHEIMES" not in res.text


@pytest.mark.parametrize("content", [None, "", "   "])
def test_empty_content_gives_warning(cfg: LLMConfig, content: str | None) -> None:
    res = _chat(FakeClient(_completion(content)), cfg)
    assert res.text == ""
    assert any("Leere Antwort" in w for w in res.warnings)


def test_finish_reason_length_gives_warning(cfg: LLMConfig) -> None:
    res = _chat(FakeClient(_completion("Abgeschnit", finish_reason="length")), cfg)
    assert res.text == "Abgeschnit"
    assert res.finish_reason == "length"
    assert any("abgeschnitten" in w for w in res.warnings)


def test_no_choices_gives_warning(cfg: LLMConfig) -> None:
    response = _completion()
    response.choices = []
    res = _chat(FakeClient(response), cfg)
    assert res.text == "" and res.finish_reason is None
    assert any("choices" in w for w in res.warnings)


# --- list_models und Client ---------------------------------------------------


def test_list_models_sorted(cfg: LLMConfig) -> None:
    assert llm.list_models(client=FakeClient(), config=cfg) == ["a-model", "b-model"]


def test_client_is_created_once(cfg: LLMConfig, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(llm, "_client", None)
    first = llm.get_client(cfg)
    assert llm.get_client(cfg) is first
    assert first.max_retries == 0
    assert str(first.base_url).rstrip("/") == "https://proxy.test/v1"


# --- Konfiguration -----------------------------------------------------------


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    return monkeypatch


def test_config_missing_key_clear_message(clean_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="LLM_API_KEY fehlt") as info:
        load_config(tmp_path / "gibt-es-nicht.env")
    assert "access.mlmp.ti.bfh.ch/my-key" in str(info.value)


def test_config_empty_key_in_env_file(clean_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("LLM_API_KEY=\nTUTOR_MODEL=x\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="LLM_API_KEY fehlt"):
        load_config(env_file)


def test_config_loads_env_file_and_hides_key(clean_env: pytest.MonkeyPatch, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(f"LLM_API_KEY={FAKE_KEY}\nLLM_MAX_RETRIES=5\nTUTOR_MODEL=gemma-4-26b\n", encoding="utf-8")
    config = load_config(env_file)
    assert config.api_key.get_secret_value() == FAKE_KEY
    assert config.max_retries == 5
    assert config.tutor_model == "gemma-4-26b"
    assert config.grader_model == "gpt-oss:120b"
    assert config.base_url == "https://inference.proxy.ti.bfh.ch/v1"
    assert FAKE_KEY not in repr(config) and FAKE_KEY not in str(config)


def test_config_invalid_value_names_variable_not_key(clean_env: pytest.MonkeyPatch) -> None:
    clean_env.setenv("LLM_API_KEY", FAKE_KEY)
    clean_env.setenv("LLM_TIMEOUT_S", "-1")
    with pytest.raises(ConfigError, match="LLM_TIMEOUT_S") as info:
        load_config(None)
    assert FAKE_KEY not in str(info.value)
    assert info.value.__cause__ is None


def test_config_whitespace_key_rejected_by_model() -> None:
    with pytest.raises(ValueError):
        LLMConfig(base_url="u", api_key="   ", tutor_model="t", grader_model="g", timeout_s=1, max_retries=0)
