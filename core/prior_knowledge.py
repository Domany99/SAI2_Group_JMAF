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


# Die Beschreibungen fragen nach Erfahrung, nicht nach dem Hilfewunsch. So wählen
# Studierende nach dem, was sie getan haben, und Stufe 03 entspricht dem Segment
# "mit Security-Vorbildung" (H11). Sie versprechen nichts, was die App nicht tut:
# Stufen und Hinweise sind für alle gleich, nur die Formulierung ändert sich.
LEVELS: dict[PriorKnowledge, LevelInfo] = {
    PriorKnowledge.NEW: LevelInfo(
        "01",
        "Neu im Thema",
        "Begriffe wie XSS oder API-Key sagen mir wenig. Code auf Sicherheitslücken geprüft habe ich noch nie.",
    ),
    PriorKnowledge.BASICS: LevelInfo(
        "02",
        "Ich kenne die Grundlagen",
        "Begriffe wie XSS oder API-Key kenne ich aus dem Unterricht, selbst Code darauf geprüft habe ich selten oder nie.",
    ),
    PriorKnowledge.EXPERIENCED: LevelInfo(
        "03",
        "Erfahren",
        "Ich habe ein Security-Modul besucht oder prüfe Code regelmässig auf Sicherheitslücken.",
    ),
}


def parse_level(value: PriorKnowledge | str) -> PriorKnowledge:
    """Wandelt einen gespeicherten Wert in eine Stufe um. Unbekannte Werte sind ein Fehler."""
    try:
        return PriorKnowledge(value)
    except ValueError:
        raise ValueError(f"unbekannte Vorwissen-Stufe: {value!r}") from None
