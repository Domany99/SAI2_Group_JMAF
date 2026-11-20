"""Tests für core/leak_guard.py. Das LLM ist gemockt, kein Netz.

Die drei Pfade aus I-09: sauber, Treffer -> sauber, Treffer -> Treffer -> Fallback.
Dazu der Fallback bei einem Ausfall des Tutors.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from core import leak_guard, tutor
from core import logging as turn_log
from core.config import LLMConfig
from core.llm import LLMResult, LLMUnavailableError
from core.models import Exercise
from core.prior_knowledge import PriorKnowledge
from core.prompts import PromptError, load_prompt

# Stufe 1 der Beispielübung verbietet "Schlüssel" und "API-Key", Stufe 3 nichts.
CLEAN = "Wer kann alles sehen, was die Seite an den Browser schickt?"
LEAK = "Wo steht der API key im Code?"
LEAK_2 = "Ist der Schlüssel für alle sichtbar?"
TS = datetime(2026, 11, 20, 10, 14, 3, tzinfo=timezone(timedelta(hours=1)))
SESSION = "s-7f3a91c2"


class ScriptedChat:
    """Ersetzt core.llm.chat: liefert der Reihe nach Texte oder wirft Fehler."""

    def __init__(self, *outcomes: str | Exception) -> None:
        self.outcomes = list(outcomes)
        self.systems: list[str] = []
        self.users: list[str] = []

    def __call__(self, messages: list[dict[str, str]], model: str, temperature: float, **kwargs: Any) -> LLMResult:
        self.systems.append(messages[0]["content"])
        self.users.append(messages[1]["content"])
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return LLMResult(
            text=outcome,
            model=model,
            temperature=temperature,
            tokens_in=10,
            tokens_out=5,
            latency_ms=100,
            json_mode_requested=False,
            json_mode_fallback=False,
            finish_reason="stop",
        )

    @property
    def calls(self) -> int:
        return len(self.systems)


@pytest.fixture
def cfg() -> LLMConfig:
    return LLMConfig(
        base_url="https://proxy.test/v1",
        api_key="sk-test",
        tutor_model="tutor-modell",
        grader_model="grader-modell",
        timeout_s=5,
        max_retries=0,
    )


@pytest.fixture
def exercise(valid_data: dict[str, Any]) -> Exercise:
    return Exercise.model_validate(valid_data)


def run(monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig, *outcomes: str | Exception,
        stage: int = 1, **kwargs: Any) -> tuple[leak_guard.GuardedQuestion, ScriptedChat]:  # fmt: skip
    chat = ScriptedChat(*outcomes)
    monkeypatch.setattr(tutor, "chat", chat)
    result = leak_guard.ask_guarded(exercise, stage, PriorKnowledge.NEW, {exercise.id: exercise}, config=cfg, **kwargs)
    return result, chat


# --- Pfad 1: sauber ---------------------------------------------------------


def test_clean_first_attempt_is_shown(monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig) -> None:
    result, chat = run(monkeypatch, exercise, cfg, CLEAN)

    assert result.text == CLEAN
    assert result.from_tutor and result.fallback is None
    assert chat.calls == 1
    assert len(result.attempts) == 1 and not result.attempts[0].blocked
    assert result.guard_hits == 0


def test_clean_path_logs_one_tutor_turn(monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig) -> None:
    result, _ = run(monkeypatch, exercise, cfg, CLEAN)
    [turn] = result.turns(SESSION, "none", TS)
    assert (turn.role, turn.text, turn.guard_hit, turn.attempt) == ("tutor", CLEAN, False, 1)


# --- Pfad 2: Treffer -> sauber ----------------------------------------------


def test_hit_then_clean_shows_second(monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig) -> None:
    result, chat = run(monkeypatch, exercise, cfg, LEAK, CLEAN)

    assert result.text == CLEAN
    assert result.from_tutor
    assert chat.calls == 2
    assert result.attempts[0].hits == ("API-Key",)
    assert not result.attempts[1].blocked
    assert result.guard_hits == 1


def test_second_attempt_uses_strict_prompt(monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig) -> None:
    result, chat = run(monkeypatch, exercise, cfg, LEAK, CLEAN)
    strict = load_prompt("tutor_strict", 1).text.strip()

    assert strict not in chat.systems[0]
    assert chat.systems[1].rstrip().endswith(strict)
    assert chat.systems[1].startswith(chat.systems[0].rstrip())  # gleicher Prompt plus Zusatz
    assert chat.users[0] == chat.users[1]
    assert result.attempts[0].question.strict_version is None
    assert result.attempts[1].question.strict_version == "tutor_strict_v1"
    assert result.attempts[0].question.prompt_hash != result.attempts[1].question.prompt_hash


def test_retry_does_not_reveal_hit_words(monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig) -> None:
    # Der Tutor erfährt nicht, welche Wörter getroffen wurden, und sieht seine blockierte Frage nicht.
    _, chat = run(monkeypatch, exercise, cfg, LEAK, CLEAN)
    second = chat.systems[1] + chat.users[1]
    for term in exercise.stages[1].forbidden:
        assert term not in second
    assert LEAK not in second


def test_hit_then_clean_logs_both_attempts(monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig) -> None:
    result, _ = run(monkeypatch, exercise, cfg, LEAK, CLEAN)
    first, second = result.turns(SESSION, "incident", TS)

    assert (first.role, first.text, first.guard_hit, first.attempt) == ("tutor", LEAK, True, 1)
    assert (second.role, second.text, second.guard_hit, second.attempt) == ("tutor", CLEAN, False, 2)
    assert first.prompt_hash != second.prompt_hash


# --- Pfad 3: Treffer -> Treffer -> Fallback ---------------------------------


def test_two_hits_fall_back_to_hint(monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig) -> None:
    result, chat = run(monkeypatch, exercise, cfg, LEAK, LEAK_2)

    assert result.text == exercise.stages[1].hint
    assert result.fallback == "guard"
    assert not result.from_tutor
    assert chat.calls == 2  # nur einmal neu erzeugt, kein dritter Versuch
    assert result.guard_hits == 2
    assert result.attempts[1].hits == ("Schlüssel",)


def test_fallback_logs_two_hits_and_hint(monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig) -> None:
    result, _ = run(monkeypatch, exercise, cfg, LEAK, LEAK_2)
    first, second, hint = result.turns(SESSION, "none", TS)

    assert (first.guard_hit, first.attempt, first.text) == (True, 1, LEAK)
    assert (second.guard_hit, second.attempt, second.text) == (True, 2, LEAK_2)
    assert (hint.role, hint.text, hint.fallback, hint.guard_hit) == ("hint", exercise.stages[1].hint, "guard", False)
    assert hint.model is None and hint.attempt is None


# --- Ausfall des Tutors -----------------------------------------------------


def test_llm_error_on_first_attempt_falls_back(monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig) -> None:
    result, _ = run(monkeypatch, exercise, cfg, LLMUnavailableError("LLM-Proxy nicht verfügbar (Timeout)"))

    assert result.text == exercise.stages[1].hint
    assert result.fallback == "llm_error"
    assert result.attempts == ()
    assert result.llm_error == "LLM-Proxy nicht verfügbar (Timeout)"
    [hint] = result.turns(SESSION, "none", TS)
    assert (hint.role, hint.fallback) == ("hint", "llm_error")


def test_llm_error_on_retry_keeps_first_attempt(monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig) -> None:
    result, _ = run(monkeypatch, exercise, cfg, LEAK, LLMUnavailableError("weg"))

    assert result.fallback == "llm_error"
    first, hint = result.turns(SESSION, "none", TS)
    assert (first.guard_hit, first.attempt) == (True, 1)  # der Treffer zählt trotzdem für die Leak-Rate
    assert hint.fallback == "llm_error"


def test_empty_tutor_answer_falls_back(monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig) -> None:
    # Leerer Text ergibt TutorError (ein LLMError) und damit denselben Fallback.
    result, _ = run(monkeypatch, exercise, cfg, "")
    assert result.fallback == "llm_error"
    assert result.text == exercise.stages[1].hint


# --- Programmfehler gehen weiter --------------------------------------------


def test_invalid_stage_raises(monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig) -> None:
    with pytest.raises(ValueError, match="Stufe"):
        run(monkeypatch, exercise, cfg, CLEAN, stage=0)


def test_missing_strict_prompt_raises(monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig) -> None:
    with pytest.raises(PromptError, match="tutor_strict_v9"):
        run(monkeypatch, exercise, cfg, LEAK, CLEAN, strict_version=9)


# --- Guard-Prüfung ----------------------------------------------------------


@pytest.mark.parametrize("text", [
    "Wo steht der API-Key?", "wo steht der api_key?", "Siehst du den SCHLÜSSEL?", "Siehst du den Schluessel?",
])  # fmt: skip
def test_hits_use_guard_normalization(
    monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig, text: str
) -> None:
    result, _ = run(monkeypatch, exercise, cfg, text, CLEAN)
    assert result.attempts[0].blocked


def test_partial_words_are_no_hit(monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig) -> None:
    # Ganze Wörter wie im Guard: "Schlüsselbund" ist kein "Schlüssel".
    result, _ = run(monkeypatch, exercise, cfg, "Wo liegt dein Schlüsselbund?")
    assert result.guard_hits == 0


def test_only_current_stage_forbidden_counts(monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig) -> None:
    # Stufe 2 verbietet nur "secret"; "API-Key" (aus Stufe 1) ist hier erlaubt.
    result, _ = run(monkeypatch, exercise, cfg, LEAK, stage=2)
    assert result.text == LEAK
    assert result.guard_hits == 0


def test_stage_3_without_forbidden_never_blocks(monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig) -> None:
    result, _ = run(monkeypatch, exercise, cfg, LEAK, stage=3)
    assert result.text == LEAK and result.from_tutor


# --- Parameter und Log ------------------------------------------------------


def test_parameters_are_passed_to_tutor(monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig) -> None:
    result, chat = run(monkeypatch, exercise, cfg, LEAK, CLEAN, previous_answer="Meine Antwort",
                       model="anderes", temperature=0.2, prompt_version=1)  # fmt: skip
    assert all("Meine Antwort" in u for u in chat.users)
    for a in result.attempts:
        assert (a.question.model, a.question.temperature, a.question.prompt_version) == ("anderes", 0.2, "tutor_v1")


def test_prior_knowledge_as_string(monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig) -> None:
    chat = ScriptedChat(CLEAN)
    monkeypatch.setattr(tutor, "chat", chat)
    result = leak_guard.ask_guarded(exercise, 1, "experienced", {exercise.id: exercise}, config=cfg)
    assert result.prior_knowledge is PriorKnowledge.EXPERIENCED


def test_turns_carry_session_context(monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig) -> None:
    result, _ = run(monkeypatch, exercise, cfg, LEAK, LEAK_2)
    for turn in result.turns(SESSION, "incident", TS):
        assert (turn.session, turn.exercise, turn.stage, turn.hook, turn.ts) == (SESSION, "beispiel", 1, "incident", TS)
        assert turn.prior_knowledge is PriorKnowledge.NEW


def test_turns_can_be_written_and_read(
    monkeypatch: pytest.MonkeyPatch, exercise: Exercise, cfg: LLMConfig, tmp_path: Path
) -> None:
    result, _ = run(monkeypatch, exercise, cfg, LEAK, LEAK_2)
    for turn in result.turns(SESSION, "none", TS):
        path = turn_log.write_turn(turn, tmp_path)
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    assert [(r["role"], r["guard_hit"], r["attempt"], r["fallback"]) for r in records] == [
        ("tutor", True, 1, None),
        ("tutor", True, 2, None),
        ("hint", False, None, "guard"),
    ]
    # Leak-Rate für Step 4: blockierte erste Versuche / alle ersten Versuche.
    first = [r for r in records if r["role"] == "tutor" and r["attempt"] == 1]
    assert sum(r["guard_hit"] for r in first) / len(first) == 1.0
