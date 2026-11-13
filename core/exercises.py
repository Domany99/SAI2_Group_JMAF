"""Übungen aus YAML laden und validieren.

Jede Fehlermeldung hat die Form "<datei>: <feld>: <regel>".
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from core.models import Exercise, RuleViolations

EXERCISE_SUFFIXES = (".yaml", ".yml")
FILE_FIELD = "(datei)"

# Pydantic-Fehlertypen, für die wir eine verständlichere Regel angeben.
_RULES_BY_TYPE = {
    "missing": "Pflichtfeld fehlt",
    "extra_forbidden": "unbekanntes Feld",
    "bool_type": "muss true oder false sein",
    "int_type": "muss eine ganze Zahl sein",
    "string_pattern_mismatch": "nur Kleinbuchstaben, Ziffern und Bindestriche erlaubt",
}


class ExerciseValidationError(Exception):
    """Eine oder mehrere Übungsdateien sind ungültig."""

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        super().__init__("\n".join(problems))


def _problem(path: Path, field: str, rule: str) -> str:
    return f"{path}: {field}: {rule}"


def _problems_from(path: Path, error: ValidationError) -> list[str]:
    problems: list[str] = []
    for detail in error.errors():
        cause = detail.get("ctx", {}).get("error")
        if isinstance(cause, RuleViolations):
            problems.extend(_problem(path, v.field, v.rule) for v in cause.violations)
            continue
        field = ".".join(str(part) for part in detail["loc"]) or FILE_FIELD
        if isinstance(cause, ValueError):
            rule = str(cause)
        else:
            rule = _RULES_BY_TYPE.get(detail["type"], detail["msg"])
        problems.append(_problem(path, field, rule))
    return problems


def load_exercise(path: str | Path) -> Exercise:
    """Lädt eine Datei und prüft alle Regeln, die nur diese Datei betreffen."""
    path = Path(path)
    try:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ExerciseValidationError([_problem(path, FILE_FIELD, f"ungültiges YAML ({exc})")]) from exc
    if not isinstance(data, dict):
        raise ExerciseValidationError([_problem(path, FILE_FIELD, "muss ein YAML-Objekt (Mapping) enthalten")])

    try:
        exercise = Exercise.model_validate(data)
    except ValidationError as exc:
        raise ExerciseValidationError(_problems_from(path, exc)) from exc

    if exercise.id != path.stem:
        raise ExerciseValidationError(
            [_problem(path, "id", f"muss dem Dateinamen entsprechen (erwartet {path.stem!r}, ist {exercise.id!r})")]
        )
    return exercise


def load_all(path: str | Path = "exercises") -> dict[str, Exercise]:
    """Lädt alle Übungen eines Ordners, sortiert nach id.

    Sammelt die Fehler aller Dateien und wirft am Ende eine einzige
    ExerciseValidationError, damit man alle Probleme auf einmal sieht.
    """
    folder = Path(path)
    if not folder.is_dir():
        raise FileNotFoundError(f"Übungsordner nicht gefunden: {folder}")

    files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix in EXERCISE_SUFFIXES)
    exercises: dict[str, Exercise] = {}
    sources: dict[str, Path] = {}
    problems: list[str] = []

    for file in files:
        try:
            exercise = load_exercise(file)
        except ExerciseValidationError as exc:
            problems.extend(exc.problems)
            continue
        if exercise.id in exercises:
            problems.append(_problem(file, "id", f"muss eindeutig sein (schon verwendet in {sources[exercise.id]})"))
            continue
        exercises[exercise.id] = exercise
        sources[exercise.id] = file

    if problems:
        raise ExerciseValidationError(problems)
    return dict(sorted(exercises.items()))
