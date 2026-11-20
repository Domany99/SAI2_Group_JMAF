"""Versionierte Prompt-Vorlagen aus `prompts/<role>_v<n>.md` (Abschnitt "Prompts").

Platzhalter-Syntax: `{{name}}` mit `name` aus Kleinbuchstaben, Ziffern und
`_` (beginnt mit einem Buchstaben), Leerzeichen innerhalb der Klammern sind
erlaubt. Doppelte Klammern, weil Prompts JSON mit einfachen `{}` enthalten.
`render()` ist streng: Jeder Platzhalter braucht einen Wert, und Werte ohne
Platzhalter sind ein Fehler. So fällt auf, wenn Code und Vorlage nicht mehr
zusammenpassen. Eingesetzte Werte werden nicht erneut ersetzt, ein `{{x}}` in
einem Hint oder einer Antwort bleibt also stehen.

Eine Vorlage ist der System-Prompt. Antworten der Studierenden gehören nie in
die Vorlage, sondern als eigene Nachricht an das Modell (Prompt Injection).

Eingefrorene Versionen (in einem Eval-Lauf verwendet) stehen mit SHA-256 in
`prompts/frozen.txt`. Ein Test prüft, dass sie sich nicht mehr ändern.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = REPO_ROOT / "prompts"
FROZEN_FILE = PROMPTS_DIR / "frozen.txt"
# tutor_strict: Zusatz zum Tutor-Prompt für den zweiten Versuch nach einem
# Guard-Treffer (core.leak_guard). Wird an den System-Prompt angehängt.
PROMPT_ROLES: tuple[str, ...] = ("tutor", "grader", "tutor_strict")

_PLACEHOLDER = re.compile(r"\{\{\s*([a-z][a-z0-9_]*)\s*\}\}")
# Alles, was wie ein Platzhalter beginnt oder endet, aber nicht passt, z. B. {{ Name }} oder {{goal}.
_BRACES = re.compile(r"\{\{|\}\}")


class PromptError(Exception):
    """Vorlage fehlt, ist fehlerhaft oder passt nicht zu den übergebenen Werten."""


@dataclass(frozen=True)
class PromptTemplate:
    """Eine geladene Vorlage. `version` (z. B. 'tutor_v1') geht so ins Log."""

    role: str
    number: int
    text: str

    @property
    def version(self) -> str:
        return f"{self.role}_v{self.number}"

    @property
    def placeholders(self) -> frozenset[str]:
        return frozenset(_PLACEHOLDER.findall(self.text))

    def render(self, values: Mapping[str, str]) -> str:
        """Setzt alle Platzhalter ein. Fehlende oder überzählige Werte sind ein Fehler."""
        missing = sorted(self.placeholders - values.keys())
        unknown = sorted(values.keys() - self.placeholders)
        problems = []
        if missing:
            problems.append(f"fehlende Werte: {missing}")
        if unknown:
            problems.append(f"unbekannte Werte: {unknown}")
        not_str = sorted(k for k, v in values.items() if not isinstance(v, str))
        if not_str:
            problems.append(f"Werte müssen Text sein: {not_str}")
        if problems:
            raise PromptError(f"{self.version}: " + "; ".join(problems))
        return _PLACEHOLDER.sub(lambda m: values[m.group(1)], self.text)


def prompt_path(role: str, number: int, prompts_dir: Path = PROMPTS_DIR) -> Path:
    return prompts_dir / f"{role}_v{number}.md"


def load_prompt(role: str, number: int, prompts_dir: Path = PROMPTS_DIR) -> PromptTemplate:
    """Lädt `prompts/<role>_v<number>.md` und prüft die Platzhalter-Syntax."""
    if role not in PROMPT_ROLES:
        raise PromptError(f"Rolle muss {' oder '.join(PROMPT_ROLES)} sein, nicht {role!r}")
    if isinstance(number, bool) or not isinstance(number, int) or number < 1:
        raise PromptError(f"Version muss eine ganze Zahl ab 1 sein, nicht {number!r}")

    path = prompt_path(role, number, prompts_dir)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise PromptError(f"{path.name}: Datei nicht gefunden in {prompts_dir}") from None

    leftover = _BRACES.findall(_PLACEHOLDER.sub("", text))
    if leftover:
        raise PromptError(
            f"{path.name}: ungültiger Platzhalter. Erlaubt ist {{{{name}}}} mit Kleinbuchstaben, Ziffern und _"
        )
    if not text.strip():
        raise PromptError(f"{path.name}: Datei ist leer")
    return PromptTemplate(role=role, number=number, text=text)


def available_versions(role: str, prompts_dir: Path = PROMPTS_DIR) -> list[int]:
    """Alle vorhandenen Versionsnummern einer Rolle, aufsteigend."""
    pattern = re.compile(rf"{re.escape(role)}_v([1-9][0-9]*)\.md")
    numbers = (pattern.fullmatch(p.name) for p in prompts_dir.glob(f"{role}_v*.md"))
    return sorted(int(m.group(1)) for m in numbers if m)


def hash_text(text: str) -> str:
    """SHA-256 (hex) eines Textes, Zeilenenden vereinheitlicht.

    Für `Turn.prompt_hash`: den fertig eingesetzten System-Prompt hashen.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def prompt_hash(path: Path) -> str:
    """SHA-256 einer Vorlagen-Datei mit vereinheitlichten Zeilenenden.

    So ergibt dieselbe Datei unter Windows (git autocrlf) und Linux denselben Hash.
    """
    return hash_text(path.read_text(encoding="utf-8"))


def read_frozen(frozen_file: Path = FROZEN_FILE) -> dict[str, str]:
    """Liest `frozen.txt`: pro Zeile `<sha256>  <dateiname>`, `#` leitet Kommentare ein."""
    entries: dict[str, str] = {}
    for number, raw in enumerate(frozen_file.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            raise PromptError(f"{frozen_file.name}:{number}: erwartet '<sha256>  <dateiname>'")
        digest, name = parts
        if name in entries:
            raise PromptError(f"{frozen_file.name}:{number}: {name} ist doppelt eingetragen")
        entries[name] = digest
    return entries
