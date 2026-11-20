"""Leak-Guard-Ablauf (Abschnitt "Leak guard", Schritte 3 bis 5).

Jede Tutor-Frage wird vor dem Anzeigen gegen `forbidden` der aktuellen Stufe
geprüft, mit derselben Normalisierung wie die Validierung der Übungen
(`core.guard.find_forbidden`):

    Versuch 1 sauber                 -> Frage anzeigen
    Versuch 1 Treffer, 2 sauber      -> zweite Frage anzeigen (mit tutor_strict)
    Versuch 1 Treffer, 2 Treffer     -> Expert:innen-Hint anzeigen (fallback=guard)
    Tutor antwortet nicht (LLMError) -> Expert:innen-Hint anzeigen (fallback=llm_error)

Der zweite Versuch nennt dem Tutor die getroffenen Wörter bewusst nicht: Er
sähe sonst einen Teil der forbidden-Liste und wiche auf Synonyme aus, die der
Guard nicht kennt. Stattdessen kommt eine allgemein strengere Anweisung dazu.

Geloggt wird jeder Versuch als tutor-Turn (blockierte mit `guard_hit=True`,
das ist die Leak-Rate für Step 4) und ein Fallback als hint-Turn. Diese Turns
baut `GuardedQuestion.turns()`; schreiben muss sie der Aufrufer mit
`core.logging.write_turn`.

Das Modul heisst nicht `guard.py`, weil `core.models` von dort importiert und
der Ablauf `core.tutor` braucht (sonst Import-Kreis).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from core import tutor
from core.config import LLMConfig
from core.guard import find_forbidden
from core.llm import LLMError
from core.models import Exercise, Fallback, Hook, Turn
from core.prior_knowledge import PriorKnowledge, parse_level

MAX_ATTEMPTS = 2


@dataclass(frozen=True)
class Attempt:
    """Ein Versuch des Tutors und die Treffer des Guards darin."""

    question: tutor.TutorQuestion
    hits: tuple[str, ...]

    @property
    def blocked(self) -> bool:
        return bool(self.hits)


@dataclass(frozen=True)
class GuardedQuestion:
    """Was die Person sieht, und wie es dazu kam.

    `text` ist entweder die Frage des letzten Versuchs oder der Hint der
    Stufe (`fallback` gesetzt). `attempts` enthält 0 bis 2 Versuche: 0, wenn
    der Tutor gleich beim ersten Mal nicht geantwortet hat. `llm_error` ist
    die Fehlermeldung bei `fallback="llm_error"`, nur für Konsole und
    Fehlersuche, nicht fürs Log.
    """

    text: str
    exercise: str
    stage: int
    prior_knowledge: PriorKnowledge
    attempts: tuple[Attempt, ...]
    fallback: Fallback | None = None
    llm_error: str | None = None

    @property
    def from_tutor(self) -> bool:
        return self.fallback is None

    @property
    def guard_hits(self) -> int:
        """Zahl der blockierten Versuche (0, 1 oder 2)."""
        return sum(a.blocked for a in self.attempts)

    def turns(self, session: str, hook: Hook, ts: datetime) -> list[Turn]:
        """Die Turns fürs Log, in der Reihenfolge, in der sie entstanden sind.

        Ein tutor-Turn pro Versuch (blockierte mit `guard_hit=True`, auch ihr
        Text wird geloggt, die Person sieht ihn nie), danach bei einem Fallback
        ein hint-Turn mit dem Grund.
        """
        common: dict[str, Any] = {
            "session": session,
            "exercise": self.exercise,
            "stage": self.stage,
            "prior_knowledge": self.prior_knowledge,
            "hook": hook,
            "ts": ts,
        }
        turns = [
            Turn(
                **common,
                role="tutor",
                text=a.question.text,
                guard_hit=a.blocked,
                attempt=number,
                prompt_version=a.question.prompt_version,
                model=a.question.model,
                temperature=a.question.temperature,
                prompt_hash=a.question.prompt_hash,
                n_examples=a.question.n_examples,
                cache_hit=a.question.cache_hit,
            )
            for number, a in enumerate(self.attempts, start=1)
        ]
        if self.fallback is not None:
            turns.append(Turn(**common, role="hint", text=self.text, fallback=self.fallback))
        return turns


def ask_guarded(
    exercise: Exercise,
    stage: int,
    prior_knowledge: PriorKnowledge | str,
    exercises: Mapping[str, Exercise],
    *,
    previous_answer: str | None = None,
    prompt_version: int | None = None,
    strict_version: int | None = None,
    model: str | None = None,
    temperature: float | None = None,
    config: LLMConfig | None = None,
    client: Any = None,
) -> GuardedQuestion:
    """Lässt den Tutor fragen und zeigt nur, was den Guard passiert.

    Parameter wie `core.tutor.ask`. Fehler in Übung, Stufe, Einstufung oder
    Prompt-Vorlage (`ValueError`, `PromptError`) gehen weiter: Das sind
    Programmfehler, kein Grund für einen stillen Fallback.
    """
    level = parse_level(prior_knowledge)
    hint = exercise.tutor_context(stage)["hint"]  # prüft auch die Stufe
    forbidden = exercise.stages[stage].forbidden
    attempts: list[Attempt] = []

    def done(text: str, fallback: Fallback | None = None, llm_error: str | None = None) -> GuardedQuestion:
        return GuardedQuestion(
            text=text,
            exercise=exercise.id,
            stage=stage,
            prior_knowledge=level,
            attempts=tuple(attempts),
            fallback=fallback,
            llm_error=llm_error,
        )

    for number in range(1, MAX_ATTEMPTS + 1):
        try:
            question = tutor.ask(
                exercise, stage, level, exercises,
                previous_answer=previous_answer,
                strict=number > 1,
                prompt_version=prompt_version,
                strict_version=strict_version,
                model=model,
                temperature=temperature,
                config=config,
                client=client,
            )  # fmt: skip
        except LLMError as exc:
            return done(hint, fallback="llm_error", llm_error=str(exc))

        attempt = Attempt(question=question, hits=tuple(find_forbidden(question.text, forbidden)))
        attempts.append(attempt)
        if not attempt.blocked:
            return done(question.text)

    return done(hint, fallback="guard")
