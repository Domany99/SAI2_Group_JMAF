"""Pydantic-Modelle für eine Übung (Abschnitt "Exercise format").

Die Regeln, die nur ein einzelnes Feld betreffen, stehen direkt am Feld. Die
Regeln über mehrere Felder (Stufen vollständig, forbidden gesetzt, Hint ohne
eigene forbidden-Begriffe) prüft `Exercise._check_stages`. Regeln, die den
Dateinamen oder andere Dateien brauchen, prüft `core.exercises`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from core.guard import find_forbidden

STAGES: tuple[int, ...] = (1, 2, 3)
# In diesen Stufen darf der Tutor das Problem nicht nennen, also braucht es
# forbidden-Begriffe, und der Tutor sieht weder answer_key noch close.
GUARDED_STAGES: tuple[int, ...] = (1, 2)
MIN_ACCEPTED = 2


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("darf nicht leer sein")
    return value


NonEmptyStr = Annotated[str, AfterValidator(_not_blank)]
ExerciseId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]


@dataclass(frozen=True)
class Violation:
    """Ein Regelverstoss mit vollem Feldpfad, z. B. 'stages.1.hint'."""

    field: str
    rule: str


class RuleViolations(ValueError):
    """Sammelt mehrere Verstösse aus einem Validator.

    Pydantic legt die Exception in `ctx["error"]` ab, so kann der Loader
    jeden Verstoss mit eigenem Feldpfad melden.
    """

    def __init__(self, violations: list[Violation]) -> None:
        self.violations = violations
        super().__init__("; ".join(f"{v.field}: {v.rule}" for v in violations))


class _Model(BaseModel):
    # extra="forbid": Tippfehler im YAML (z. B. "forbiden") fallen auf.
    model_config = ConfigDict(extra="forbid", frozen=True)


class Scenario(_Model):
    requirement: NonEmptyStr
    ai_chat: NonEmptyStr
    code: NonEmptyStr


class AnswerKey(_Model):
    issue: NonEmptyStr
    consequence: NonEmptyStr
    accepted: list[NonEmptyStr]

    @field_validator("accepted")
    @classmethod
    def _enough_accepted(cls, value: list[str]) -> list[str]:
        if len(value) < MIN_ACCEPTED:
            raise ValueError(f"mindestens {MIN_ACCEPTED} akzeptierte Antworten nötig (gefunden: {len(value)})")
        return value


class Stage(_Model):
    goal: NonEmptyStr
    hint: NonEmptyStr  # Expert:innen-Hint: Gold Standard und Fallback des Leak Guards
    forbidden: list[NonEmptyStr]


class Close(_Model):
    fix: NonEmptyStr
    pruefmuster: NonEmptyStr


class Exercise(_Model):
    id: ExerciseId
    title: NonEmptyStr
    version: int = Field(strict=True, ge=1)
    decoy: bool = Field(strict=True)  # Pflichtfeld ohne Default
    hook: NonEmptyStr | None = None  # Stufe 0: optionaler Incident-Hook
    scenario: Scenario
    answer_key: AnswerKey
    stages: dict[int, Stage]
    close: Close

    @model_validator(mode="after")
    def _check_stages(self) -> Exercise:
        violations: list[Violation] = []

        missing = [n for n in STAGES if n not in self.stages]
        unknown = sorted(n for n in self.stages if n not in STAGES)
        if missing:
            violations.append(Violation("stages", f"Stufen 1, 2 und 3 müssen vorhanden sein (fehlt: {missing})"))
        if unknown:
            violations.append(Violation("stages", f"nur Stufen 1, 2 und 3 erlaubt (unbekannt: {unknown})"))

        for number, stage in sorted(self.stages.items()):
            if number in GUARDED_STAGES and not stage.forbidden:
                violations.append(
                    Violation(f"stages.{number}.forbidden", "darf für Stufe 1 und 2 nicht leer sein")
                )
            hits = find_forbidden(stage.hint, stage.forbidden)
            if hits:
                violations.append(
                    Violation(f"stages.{number}.hint", f"Hint enthält eigene forbidden-Begriffe: {hits}")
                )

        if violations:
            raise RuleViolations(violations)
        return self

    def tutor_context(self, stage: int) -> dict[str, Any]:
        """Was der Tutor (LLM 1) für eine Stufe sehen darf.

        Nur goal und hint der Stufe. answer_key, close und forbidden sind
        bewusst nicht enthalten: Was der Tutor nicht kennt, kann er auch
        nicht umschreiben und so verraten.
        """
        if stage not in STAGES:
            raise ValueError(f"Stufe muss 1, 2 oder 3 sein, nicht {stage!r}")
        current = self.stages[stage]
        return {"exercise_id": self.id, "stage": stage, "goal": current.goal, "hint": current.hint}
