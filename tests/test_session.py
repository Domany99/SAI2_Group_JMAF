"""Tests für core/session.py: Ablauf im LLM-Modus mit gemocktem LLM und echtem Log in tmp_path."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from core import grader, session, tutor
from core.config import LLMConfig
from core.llm import LLMResult, LLMUnavailableError
from core.logging import read_turns
from core.models import Exercise, Verdict
from core.prior_knowledge import PriorKnowledge
from core.stages import Outcome, StageError, StageState, start

CLEAN = "Wer kann alles sehen, was die Seite an den Browser schickt?"
LEAK = "Wo steht der API key im Code?"  # Stufe 1 der Beispielübung verbietet "API-Key"
ANSWER = "Antwort A, weil jeder den Code sieht."


def result(text: str, **extra: Any) -> LLMResult:
    return LLMResult(
        text=text, model=extra.pop("model", "m"), temperature=extra.pop("temperature", 0.0), tokens_in=1,
        tokens_out=1, latency_ms=10, json_mode_requested=False, json_mode_fallback=False, finish_reason="stop",
        **extra,
    )  # fmt: skip


class Scripted:
    """Ersetzt chat() in einem Modul: liefert der Reihe nach Texte oder wirft Fehler."""

    def __init__(self, *outcomes: str | Exception) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, messages: Any, model: str, temperature: float, **kwargs: Any) -> LLMResult:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return result(outcome, model=model, temperature=temperature)


def verdict_json(verdict: str, evidence: str = "Antwort A") -> str:
    return json.dumps({"verdict": verdict, "evidence": evidence, "misconception": None})


@pytest.fixture
def cfg() -> LLMConfig:
    return LLMConfig(
        base_url="https://proxy.test/v1", api_key="sk-test", tutor_model="tutor-m", grader_model="grader-m",
        timeout_s=5, max_retries=0,
    )  # fmt: skip


@pytest.fixture
def exercise(valid_data: dict[str, Any]) -> Exercise:
    return Exercise.model_validate(valid_data)


@pytest.fixture
def ctx(tmp_path: Path) -> session.SessionContext:
    return session.SessionContext(
        session="s-0a1b2c3d", hook="incident", prior_knowledge=PriorKnowledge.BASICS, log_dir=tmp_path
    )


def logged(ctx: session.SessionContext) -> list[Any]:
    files = sorted(ctx.log_dir.glob("*.jsonl"))
    return [turn for f in files for turn in read_turns(f)]


# --- Frage ------------------------------------------------------------------


def test_ask_question_logs_tutor_turn(
    monkeypatch: pytest.MonkeyPatch, ctx: session.SessionContext, exercise: Exercise, cfg: LLMConfig
) -> None:
    monkeypatch.setattr(tutor, "chat", Scripted(CLEAN))
    q = session.ask_question(ctx, exercise, 1, {exercise.id: exercise}, config=cfg)

    assert q.text == CLEAN
    [turn] = logged(ctx)
    assert (turn.role, turn.text, turn.attempt, turn.guard_hit) == ("tutor", CLEAN, 1, False)
    assert (turn.session, turn.hook, turn.prior_knowledge) == ("s-0a1b2c3d", "incident", PriorKnowledge.BASICS)
    assert turn.ts.utcoffset() is not None


def test_ask_question_logs_guard_hits_and_fallback(
    monkeypatch: pytest.MonkeyPatch, ctx: session.SessionContext, exercise: Exercise, cfg: LLMConfig
) -> None:
    monkeypatch.setattr(tutor, "chat", Scripted(LEAK, LEAK))
    q = session.ask_question(ctx, exercise, 1, {exercise.id: exercise}, config=cfg)

    assert q.fallback == "guard"
    assert [(t.role, t.guard_hit, t.attempt, t.fallback) for t in logged(ctx)] == [
        ("tutor", True, 1, None),
        ("tutor", True, 2, None),
        ("hint", False, None, "guard"),
    ]


def test_ask_question_never_raises_on_llm_error(
    monkeypatch: pytest.MonkeyPatch, ctx: session.SessionContext, exercise: Exercise, cfg: LLMConfig
) -> None:
    monkeypatch.setattr(tutor, "chat", Scripted(LLMUnavailableError("Timeout")))
    q = session.ask_question(ctx, exercise, 1, {exercise.id: exercise}, config=cfg)

    assert q.text == exercise.stages[1].hint
    [hint] = logged(ctx)
    assert (hint.role, hint.fallback) == ("hint", "llm_error")


def test_ask_question_passes_previous_answer(
    monkeypatch: pytest.MonkeyPatch, ctx: session.SessionContext, exercise: Exercise, cfg: LLMConfig
) -> None:
    seen: list[str] = []

    def chat(messages: Any, model: str, temperature: float, **kwargs: Any) -> LLMResult:
        seen.append(messages[1]["content"])
        return result(CLEAN)

    monkeypatch.setattr(tutor, "chat", chat)
    session.ask_question(ctx, exercise, 2, {exercise.id: exercise}, "Meine letzte Antwort", config=cfg)
    assert "Meine letzte Antwort" in seen[0]


def test_every_logged_turn_carries_the_exercise_version(
    monkeypatch: pytest.MonkeyPatch, ctx: session.SessionContext, valid_data: dict[str, Any], cfg: LLMConfig
) -> None:
    valid_data["version"] = 3
    ex = Exercise.model_validate(valid_data)
    monkeypatch.setattr(tutor, "chat", Scripted(LEAK, LEAK))  # tutor, tutor, hint
    session.ask_question(ctx, ex, 1, {ex.id: ex}, config=cfg)
    session.log_answer(ctx, ex, 1, ANSWER)
    monkeypatch.setattr(grader, "chat", Scripted(verdict_json("partial")))
    session.grade_answer(ctx, ex, start(), ANSWER, config=cfg)

    turns = logged(ctx)
    assert [t.role for t in turns] == ["tutor", "tutor", "hint", "student", "grader"]
    assert {t.exercise_version for t in turns} == {3}


# --- Antwort ----------------------------------------------------------------


def test_log_answer_writes_student_turn(ctx: session.SessionContext, exercise: Exercise) -> None:
    turn = session.log_answer(ctx, exercise, 2, ANSWER)
    assert logged(ctx) == [turn]
    assert (turn.role, turn.text, turn.stage, turn.model, turn.verdict) == ("student", ANSWER, 2, None, None)


# --- Bewertung --------------------------------------------------------------


@pytest.mark.parametrize(("verdict", "expected"), [
    ("recognized", StageState(stage=1, outcome=Outcome.RECOGNIZED)),
    ("partial", StageState(stage=2)),
    ("not", StageState(stage=2)),
])  # fmt: skip
def test_grade_answer_applies_stage_logic(
    monkeypatch: pytest.MonkeyPatch, ctx: session.SessionContext, exercise: Exercise, cfg: LLMConfig,
    verdict: str, expected: StageState,
) -> None:  # fmt: skip
    monkeypatch.setattr(grader, "chat", Scripted(verdict_json(verdict)))
    grading = session.grade_answer(ctx, exercise, start(), ANSWER, config=cfg)
    assert grading.result.verdict == verdict
    assert grading.state == expected


def test_grade_answer_at_stage_3_reveals(
    monkeypatch: pytest.MonkeyPatch, ctx: session.SessionContext, exercise: Exercise, cfg: LLMConfig
) -> None:
    monkeypatch.setattr(grader, "chat", Scripted(verdict_json("not")))
    grading = session.grade_answer(ctx, exercise, StageState(stage=3), ANSWER, config=cfg)
    assert grading.state.reveal_issue


def test_grade_answer_logs_grader_turn(
    monkeypatch: pytest.MonkeyPatch, ctx: session.SessionContext, exercise: Exercise, cfg: LLMConfig
) -> None:
    monkeypatch.setattr(grader, "chat", Scripted(verdict_json("recognized", "Antwort A")))
    session.grade_answer(ctx, exercise, StageState(stage=2), ANSWER, config=cfg)

    [turn] = logged(ctx)
    assert (turn.role, turn.stage, turn.verdict, turn.text) == ("grader", 2, Verdict.RECOGNIZED, "Antwort A")
    assert (turn.model, turn.prompt_version, turn.temperature) == ("grader-m", "grader_v3", 0.0)  # Default seit 24.11.
    assert turn.error is None and turn.cache_hit is False and len(turn.prompt_hash or "") == 64


def test_grade_answer_logs_fallback_error_code(
    monkeypatch: pytest.MonkeyPatch, ctx: session.SessionContext, exercise: Exercise, cfg: LLMConfig
) -> None:
    monkeypatch.setattr(grader, "chat", Scripted("kein json"))
    grading = session.grade_answer(ctx, exercise, start(), ANSWER, config=cfg)

    assert grading.result.verdict is Verdict.PARTIAL
    [turn] = logged(ctx)
    assert (turn.verdict, turn.error) == (Verdict.PARTIAL, "invalid_json")


def test_grade_answer_llm_error_logs_nothing(
    monkeypatch: pytest.MonkeyPatch, ctx: session.SessionContext, exercise: Exercise, cfg: LLMConfig
) -> None:
    monkeypatch.setattr(grader, "chat", Scripted(LLMUnavailableError("Proxy weg")))
    with pytest.raises(LLMUnavailableError):
        session.grade_answer(ctx, exercise, start(), ANSWER, config=cfg)
    assert logged(ctx) == []


def test_retry_after_grader_error_logs_answer_once(
    monkeypatch: pytest.MonkeyPatch, ctx: session.SessionContext, exercise: Exercise, cfg: LLMConfig
) -> None:
    # So nutzt die App die Funktionen: Antwort einmal loggen, Bewertung bei Bedarf wiederholen.
    monkeypatch.setattr(grader, "chat", Scripted(LLMUnavailableError("weg"), verdict_json("partial")))
    session.log_answer(ctx, exercise, 1, ANSWER)
    with pytest.raises(LLMUnavailableError):
        session.grade_answer(ctx, exercise, start(), ANSWER, config=cfg)
    session.grade_answer(ctx, exercise, start(), ANSWER, config=cfg)

    assert [t.role for t in logged(ctx)] == ["student", "grader"]


@pytest.mark.parametrize("state", [StageState(stage=2, outcome=Outcome.RECOGNIZED), start(with_hook=True)])
def test_grade_answer_rejects_invalid_state_before_calling_llm(
    monkeypatch: pytest.MonkeyPatch, ctx: session.SessionContext, exercise: Exercise, cfg: LLMConfig,
    state: StageState,
) -> None:  # fmt: skip
    chat = Scripted(verdict_json("recognized"))
    monkeypatch.setattr(grader, "chat", chat)
    with pytest.raises(StageError):
        session.grade_answer(ctx, exercise, state, ANSWER, config=cfg)
    assert chat.calls == 0
    assert logged(ctx) == []


# --- Ganze Übung ------------------------------------------------------------


def test_full_exercise_logs_every_turn_in_order(
    monkeypatch: pytest.MonkeyPatch, ctx: session.SessionContext, exercise: Exercise, cfg: LLMConfig
) -> None:
    monkeypatch.setattr(tutor, "chat", Scripted(LEAK, CLEAN, "Frage 2?", "Frage 3?"))
    monkeypatch.setattr(grader, "chat", Scripted(verdict_json("not"), verdict_json("partial"), verdict_json("not")))
    exercises = {exercise.id: exercise}

    state, previous = start(), None
    while not state.done:
        session.ask_question(ctx, exercise, state.stage, exercises, previous, config=cfg)
        session.log_answer(ctx, exercise, state.stage, ANSWER)
        state = session.grade_answer(ctx, exercise, state, ANSWER, config=cfg).state
        previous = ANSWER

    assert state.reveal_issue
    assert [(t.stage, t.role) for t in logged(ctx)] == [
        (1, "tutor"), (1, "tutor"), (1, "student"), (1, "grader"),
        (2, "tutor"), (2, "student"), (2, "grader"),
        (3, "tutor"), (3, "student"), (3, "grader"),
    ]  # fmt: skip
    assert {t.session for t in logged(ctx)} == {"s-0a1b2c3d"}
