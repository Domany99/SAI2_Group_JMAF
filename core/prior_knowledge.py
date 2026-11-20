"""Einstufung des Vorwissens (Selbsteinschätzung vor der ersten Übung).

Laut Lösungsarchitektur passt der Tutor seine Fragen an das Vorwissen an.
In Schritt 2 wird die Stufe nur erfasst und angezeigt. Ab Schritt 3 geht sie
in den Kontext für LLM 1 (Tutor) und in die Logs, damit sich die Segmente
(z. B. mit und ohne Security-Vorbildung, H11) vergleichen lassen.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PriorKnowledge(StrEnum):
    NEW = "new"
    BASICS = "basics"
    EXPERIENCED = "experienced"


@dataclass(frozen=True)
class LevelInfo:
    number: str
    title: str
    description: str


LEVELS: dict[PriorKnowledge, LevelInfo] = {
    PriorKnowledge.NEW: LevelInfo("01", "Neu im Thema", "Führ mich mit Fragen Schritt für Schritt hin."),
    PriorKnowledge.BASICS: LevelInfo("02", "Ich kenne die Grundlagen", "Weniger Hinweise, schnellere Schritte."),
    PriorKnowledge.EXPERIENCED: LevelInfo("03", "Erfahren", "Kurze Checks, direkt auf den Punkt."),
}


def parse_level(value: PriorKnowledge | str) -> PriorKnowledge:
    """Wandelt einen gespeicherten Wert in eine Stufe um. Unbekannte Werte sind ein Fehler."""
    try:
        return PriorKnowledge(value)
    except ValueError:
        raise ValueError(f"unbekannte Vorwissen-Stufe: {value!r}") from None
