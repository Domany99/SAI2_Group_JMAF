from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
EXERCISES_DIR = REPO_ROOT / "exercises"

_VALID: dict[str, Any] = {
    "id": "beispiel",
    "title": "Beispielübung",
    "version": 1,
    "decoy": False,
    "scenario": {"requirement": "Auftrag", "ai_chat": "Chat", "code": "const x = 1;"},
    "answer_key": {
        "issue": "GEHEIMES-PROBLEM",
        "consequence": "GEHEIME-FOLGE",
        "accepted": ["Antwort A", "Antwort B"],
    },
    "stages": {
        1: {"goal": "Ziel 1", "hint": "Wer sieht das?", "forbidden": ["Schlüssel", "API-Key"]},
        2: {"goal": "Ziel 2", "hint": "Schau in den Netzwerk-Tab.", "forbidden": ["secret"]},
        3: {"goal": "Ziel 3", "hint": "Was kann man damit tun?", "forbidden": []},
    },
    "close": {"fix": "GEHEIMER-FIX", "pruefmuster": "GEHEIMES-PRUEFMUSTER"},
}


@pytest.fixture
def valid_data() -> dict[str, Any]:
    """Eine gültige Übung als dict. Jeder Test bekommt eine eigene Kopie."""
    return copy.deepcopy(_VALID)


@pytest.fixture
def write_exercise(tmp_path: Path) -> Callable[..., Path]:
    """Schreibt ein dict als YAML in tmp_path und gibt den Pfad zurück."""

    def _write(data: Any, name: str | None = None) -> Path:
        filename = name or f"{data['id']}.yaml"
        path = tmp_path / filename
        path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
        return path

    return _write
