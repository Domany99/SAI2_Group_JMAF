"""Stufen-Logik als kleine State Machine (Abschnitt "Stage logic").

Die Logik ist reiner Code ohne LLM und ohne UI. Kein Prompt kann sie ändern:
Der Tutor bekommt nur die aktuelle Stufe, die Entscheidung über die nächste
Stufe oder den Abschluss fällt hier.

    stage 0: optionaler Hook (echter Vorfall), dann Stufe 1
    recognized               -> Abschluss
    partial | not, Stufe < 3 -> Stufe + 1
    partial | not, Stufe = 3 -> Lücke auflösen, Abschluss

Die Zustände sind unveränderlich. Jeder Übergang gibt einen neuen Zustand
zurück, so lassen sich Sitzungen einfach speichern und testen.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum

from core.models import STAGES

HOOK_STAGE = 0
FIRST_STAGE = STAGES[0]
LAST_STAGE = STAGES[-1]


class Verdict(StrEnum):
    """Urteil über eine Antwort. Dieselben Werte liefert später LLM 2."""

    RECOGNIZED = "recognized"
    PARTIAL = "partial"
    NOT = "not"


class Outcome(StrEnum):
    """Wie eine abgeschlossene Übung geendet hat."""

    RECOGNIZED = "recognized"  # selbst gefunden
    REVEALED = "revealed"  # nach Stufe 3 aufgelöst


class StageError(ValueError):
    """Ein Übergang ist im aktuellen Zustand nicht erlaubt."""


@dataclass(frozen=True)
class StageState:
    """Zustand einer Übung: aktuelle Stufe, ob fertig und wie sie endete."""

    stage: int
    outcome: Outcome | None = None

    def __post_init__(self) -> None:
        if self.stage != HOOK_STAGE and self.stage not in STAGES:
            raise StageError(f"Stufe muss 0, 1, 2 oder 3 sein, nicht {self.stage!r}")
        if self.outcome is not None and self.stage == HOOK_STAGE:
            raise StageError("eine Übung kann nicht in Stufe 0 abgeschlossen sein")

    @property
    def done(self) -> bool:
        return self.outcome is not None

    @property
    def in_hook(self) -> bool:
        return self.stage == HOOK_STAGE

    @property
    def reveal_issue(self) -> bool:
        """True erst nach Stufe 3 ohne Treffer. Nur dann wird die Lücke genannt."""
        return self.outcome is Outcome.REVEALED


def start(with_hook: bool = False) -> StageState:
    """Startzustand. Mit Hook beginnt die Übung in Stufe 0."""
    return StageState(stage=HOOK_STAGE if with_hook else FIRST_STAGE)


def finish_hook(state: StageState) -> StageState:
    """Hook gelesen, weiter zu Stufe 1."""
    if not state.in_hook:
        raise StageError("finish_hook ist nur in Stufe 0 erlaubt")
    return replace(state, stage=FIRST_STAGE)


def on_verdict(state: StageState, verdict: Verdict | str) -> StageState:
    """Nächster Zustand nach dem Urteil über eine Antwort.

    Akzeptiert auch die Strings "recognized", "partial" und "not", damit die
    Ausgabe von LLM 2 direkt durchgereicht werden kann. Alles andere ist ein
    Fehler: Ungültige Grader-Ausgaben werden vorher zu "partial" (siehe
    development.md, Grader output), nicht hier.
    """
    if state.done:
        raise StageError("die Übung ist bereits abgeschlossen")
    if state.in_hook:
        raise StageError("in Stufe 0 gibt es keine Antwort zu bewerten, erst finish_hook aufrufen")
    try:
        verdict = Verdict(verdict)
    except ValueError:
        raise StageError(f"unbekanntes Urteil: {verdict!r}") from None

    if verdict is Verdict.RECOGNIZED:
        return replace(state, outcome=Outcome.RECOGNIZED)
    if state.stage < LAST_STAGE:
        return replace(state, stage=state.stage + 1)
    return replace(state, outcome=Outcome.REVEALED)
