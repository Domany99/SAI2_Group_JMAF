"""Konfiguration aus `.env` und Umgebung, validiert mit Pydantic.

Der API-Key wird als `SecretStr` gehalten, damit er in `repr`, Logs und
Fehlermeldungen nie im Klartext erscheint.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator

REPO_ROOT = Path(__file__).resolve().parent.parent
KEY_URL = "access.mlmp.ti.bfh.ch/my-key"


class ConfigError(Exception):
    """Konfiguration fehlt oder ist ungültig. Enthält nie den Wert des Keys."""


class LLMConfig(BaseModel):
    """Verbindung zum LLM-Proxy und Modellwahl."""

    model_config = ConfigDict(frozen=True)

    base_url: str = Field(min_length=1)
    api_key: SecretStr
    tutor_model: str = Field(min_length=1)
    grader_model: str = Field(min_length=1)
    timeout_s: float = Field(gt=0)
    max_retries: int = Field(ge=0)

    @field_validator("api_key")
    @classmethod
    def _key_not_empty(cls, v: SecretStr) -> SecretStr:
        if not v.get_secret_value().strip():
            raise ValueError("leer")
        return v


_ENV_TO_FIELD = {
    "LLM_BASE_URL": "base_url",
    "LLM_API_KEY": "api_key",
    "TUTOR_MODEL": "tutor_model",
    "GRADER_MODEL": "grader_model",
    "LLM_TIMEOUT_S": "timeout_s",
    "LLM_MAX_RETRIES": "max_retries",
}
_FIELD_TO_ENV = {f: e for e, f in _ENV_TO_FIELD.items()}
_DEFAULTS = {
    "base_url": "https://inference.proxy.ti.bfh.ch/v1",
    "tutor_model": "qwen3.8-27b",
    "grader_model": "gpt-oss:120b",
    "timeout_s": "60",
    "max_retries": "3",
}


def load_config(env_file: Path | None = REPO_ROOT / ".env") -> LLMConfig:
    """Lädt `.env` (echte Umgebungsvariablen haben Vorrang) und validiert.

    Wirft `ConfigError` mit einer Meldung pro fehlerhaftem Feld. Die Meldung
    nennt nur den Variablennamen, nie den Wert.
    """
    if env_file is not None:
        load_dotenv(env_file, override=False)

    raw: dict[str, str] = dict(_DEFAULTS)
    for env, field in _ENV_TO_FIELD.items():
        value = os.environ.get(env)
        if value is not None and value.strip():
            raw[field] = value.strip()

    if "api_key" not in raw:
        raise ConfigError(f"LLM_API_KEY fehlt. In .env setzen (persönlicher Key unter {KEY_URL}).")

    try:
        return LLMConfig(**raw)
    except ValidationError as exc:
        problems = []
        for err in exc.errors(include_input=False, include_url=False):
            field = str(err["loc"][0]) if err["loc"] else "?"
            problems.append(f"{_FIELD_TO_ENV.get(field, field)}: {err['msg']}")
        raise ConfigError("Ungültige Konfiguration: " + "; ".join(problems)) from None
