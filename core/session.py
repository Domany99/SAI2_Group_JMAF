"""Ablauf einer Übung im LLM-Modus, ohne UI: Frage holen, Antwort bewerten, loggen.

Die Streamlit-App (`app/main.py`, `MODE=llm`) ruft nur diese Funktionen auf.
So lässt sich der Ablauf mit gemocktem LLM testen, und jeder Turn wird an
genau einer Stelle geloggt:

- `ask_question`  Tutor über den Leak Guard, loggt alle Versuche und einen
                  allfälligen Hint-Fallback (tutor-/hint-Turns)
- `log_answer`    loggt die Antwort der Person (student-Turn), einmal pro
                  Antwort, auch wenn die Bewertung danach wiederholt wird
- `grade_answer`  Grader und Stufen-Logik, loggt das Urteil (grader-Turn)

Welche Stufe als nächste kommt, entscheidet weiterhin `core.stages`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core import grader, leak_guard
from core import logging as turn_log
from core.config import LLMConfig
from core.models import Exercise, Hook, Turn
from core.prior_knowledge import PriorKnowledge
from core.stages import StageState, on_verdict

Writer = Callable[[Turn, Path], Any]


@dataclass(frozen=True)
class SessionContext:
    """Was zu jedem Turn einer Sitzung gehört. Keine Namen, keine E-Mail-Adressen."""

    session: str
    hook: Hook
    prior_knowledge: PriorKnowledge
    log_dir: Path


@dataclass(frozen=True)
class Grading:
    """Ergebnis einer Bewertung: das Urteil des Graders und der neue Zustand."""

    result: grader.GraderResult
    state: StageState


def ask_question(
    ctx: SessionContext,
    exercise: Exercise,
    stage: int,
    exercises: Mapping[str, Exercise],
    previous_answer: str | None = None,
    *,
    config: LLMConfig | None = None,
    write: Writer = turn_log.write_turn,
) -> leak_guard.GuardedQuestion:
    """Frage für `stage` über Tutor und Leak Guard. Loggt alle entstandenen Turns.

    Wirft keinen `LLMError`: Antwortet der Tutor nicht, kommt der
    Expert:innen-Hint (`fallback="llm_error"`).
    """
    question = leak_guard.ask_guarded(
        exercise, stage, ctx.prior_knowledge, exercises, previous_answer=previous_answer, config=config
    )
    for turn in question.turns(ctx.session, ctx.hook, turn_log.now()):
        write(turn, ctx.log_dir)
    return question


def log_answer(
    ctx: SessionContext,
    exercise: Exercise,
    stage: int,
    answer: str,
    *,
    write: Writer = turn_log.write_turn,
) -> Turn:
    """Loggt die Antwort der Person als student-Turn."""
    turn = Turn(
        session=ctx.session,
        exercise=exercise.id,
        exercise_version=exercise.version,
        stage=stage,
        role="student",
        text=answer,
        ts=turn_log.now(),
        prior_knowledge=ctx.prior_knowledge,
        hook=ctx.hook,
    )
    write(turn, ctx.log_dir)
    return turn


def grade_answer(
    ctx: SessionContext,
    exercise: Exercise,
    state: StageState,
    answer: str,
    *,
    config: LLMConfig | None = None,
    write: Writer = turn_log.write_turn,
) -> Grading:
    """Lässt den Grader bewerten, loggt das Urteil und wendet die Stufen-Logik an.

    Raises:
        LLMError: Grader nicht erreichbar. Dann ist nichts geloggt und der
            Zustand unverändert; der Aufrufer kann es erneut versuchen.
        StageError: Die Übung ist abgeschlossen oder in Stufe 0.
    """
    if state.done or state.in_hook:
        # Vor dem LLM-Aufruf prüfen, damit kein Urteil ohne gültigen Übergang geloggt wird.
        on_verdict(state, "partial")  # wirft StageError mit passender Meldung
    result = grader.grade(exercise, answer, config=config)
    write(
        Turn(
            session=ctx.session,
            exercise=exercise.id,
            exercise_version=exercise.version,
            stage=state.stage,
            role="grader",
            text=result.output.evidence,
            verdict=result.verdict,
            prompt_version=result.prompt_version,
            model=result.model,
            temperature=result.temperature,
            prompt_hash=result.prompt_hash,
            cache_hit=result.cache_hit,
            error=result.error,
            ts=turn_log.now(),
            prior_knowledge=ctx.prior_knowledge,
            hook=ctx.hook,
        ),
        ctx.log_dir,
    )
    return Grading(result=result, state=on_verdict(state, result.verdict))
