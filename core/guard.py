"""Leak guard.

Bisher nur die Normalisierung und der Begriffsabgleich (Schritt 1 und 2 aus
"Leak guard" in development.md). Die Validierung der Übungen nutzt dieselben
Funktionen, damit Hints und Tutor-Ausgaben gleich geprüft werden.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
# Alles ausser Buchstaben, Ziffern und Leerraum gilt als Satzzeichen. "_" zählt
# in Regex als Wortzeichen, soll hier aber trennen (api_key == api key).
_PUNCTUATION = re.compile(r"[^\w\s]|_")


def normalize(text: str) -> str:
    """Kleinschreibung, ä/ö/ü/ß -> ae/oe/ue/ss, Satzzeichen -> Leerzeichen.

    Leerraum wird zu einem Leerzeichen zusammengefasst. Dadurch werden
    "API-Key", "API key", "api_key" und "Schlüssel"/"Schluessel" gleich.
    """
    text = text.lower().translate(_UMLAUTS)
    text = _PUNCTUATION.sub(" ", text)
    return " ".join(text.split())


def find_forbidden(text: str, terms: Iterable[str]) -> list[str]:
    """Gibt die Begriffe aus `terms` zurück, die in `text` vorkommen.

    Verglichen wird auf normalisierten, ganzen Wörtern: "leak" trifft "leak"
    und "Leak!", aber nicht "leaking". Begriffe, die nach der Normalisierung
    leer sind, werden ignoriert.
    """
    haystack = f" {normalize(text)} "
    hits: list[str] = []
    for term in terms:
        needle = normalize(term)
        if needle and f" {needle} " in haystack:
            hits.append(term)
    return hits


def contains_forbidden(text: str, terms: Iterable[str]) -> bool:
    """True, wenn mindestens ein Begriff aus `terms` in `text` vorkommt."""
    return bool(find_forbidden(text, terms))
