"""Pydantic-Modelle für eine Übung (Abschnitt "Exercise format") und für
einen geloggten Turn (Abschnitt "Logging").

Die Regeln, die nur ein einzelnes Feld betreffen, stehen direkt am Feld. Die
Regeln über mehrere Felder (Stufen vollständig, forbidden gesetzt, Hint ohne
eigene forbidden-Begriffe) prüft `Exercise._check_stages`, die Regeln für
misconceptions und fix_choices `Exercise._check_extras`. Regeln, die den
Dateinamen oder andere Dateien brauchen, prüft `core.exercises`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from core.guard import find_forbidden
from core.prior_knowledge import PriorKnowledge

STAGES: tuple[int, ...] = (1, 2, 3)
# In diesen Stufen darf der Tutor das Problem nicht nennen, also braucht es
# forbidden-Begriffe, und der Tutor sieht weder answer_key noch close.
GUARDED_STAGES: tuple[int, ...] = (1, 2)
MIN_ACCEPTED = 2
MIN_FIX_CHOICES = 2


def _not_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("darf nicht leer sein")
    return value


NonEmptyStr = Annotated[str, AfterValidator(_not_blank)]
ExerciseId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]
# Gleiches Format wie die Übungs-id. Der Grader gibt diese id als
# "misconception" zurück, damit der Code die passende Reaktion findet.
MisconceptionId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]


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


class Misconception(_Model):
    """Typische Fehlannahme mit vorbereiteter Reaktion (Expert:innen-Text)."""

    id: MisconceptionId
    belief: NonEmptyStr  # so äussert sich die Fehlannahme in einer Antwort
    reaction: NonEmptyStr  # Rückfrage, die die Annahme aufgreift statt sie als falsch zu markieren


class FixChoice(_Model):
    """Eine Option der Fix-Auswahl. Wird erst nach dem Erkennen gezeigt."""

    text: NonEmptyStr
    verdict: Literal["correct", "partial", "wrong"]
    reason: NonEmptyStr


class Close(_Model):
    fix: NonEmptyStr
    pruefmuster: NonEmptyStr
    fix_choices: list[FixChoice] = []  # optional, Regeln in Exercise._check_extras


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
    misconceptions: list[Misconception] = []  # optional, nie im Tutor-Kontext

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

    @model_validator(mode="after")
    def _check_extras(self) -> Exercise:
        """Regeln für misconceptions und close.fix_choices.

        Läuft nach _check_stages. Schlägt jene fehl, meldet Pydantic nur deren
        Verstösse; diese hier erscheinen dann beim nächsten Laden.
        """
        violations: list[Violation] = []

        ids = [m.id for m in self.misconceptions]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            violations.append(Violation("misconceptions", f"id muss eindeutig sein (doppelt: {duplicates})"))

        choices = self.close.fix_choices
        if choices:
            if len(choices) < MIN_FIX_CHOICES:
                violations.append(
                    Violation(
                        "close.fix_choices",
                        f"mindestens {MIN_FIX_CHOICES} Optionen nötig (gefunden: {len(choices)})",
                    )
                )
            if not any(c.verdict == "correct" for c in choices):
                violations.append(Violation("close.fix_choices", "mindestens eine Option muss correct sein"))

        if violations:
            raise RuleViolations(violations)
        return self

    def tutor_context(self, stage: int) -> dict[str, Any]:
        """Was der Tutor (LLM 1) für eine Stufe sehen darf.

        Nur goal und hint der Stufe. answer_key, close, misconceptions und
        forbidden sind bewusst nicht enthalten: Was der Tutor nicht kennt, kann er auch
        nicht umschreiben und so verraten.
        """
        if stage not in STAGES:
            raise ValueError(f"Stufe muss 1, 2 oder 3 sein, nicht {stage!r}")
        current = self.stages[stage]
        return {"exercise_id": self.id, "stage": stage, "goal": current.goal, "hint": current.hint}


class Verdict(StrEnum):
    """Urteil über eine Antwort: Ausgabe von LLM 2 und Eingabe der Stufen-Logik."""

    RECOGNIZED = "recognized"
    PARTIAL = "partial"
    NOT = "not"


# Wer einen Turn erzeugt hat:
#   tutor   Frage von LLM 1 (auch eine vom Leak Guard blockierte, dann guard_hit=True)
#   student Antwort der Studierenden
#   grader  Urteil von LLM 2 (verdict gesetzt, text = evidence)
#   hint    Fallback auf den Expert:innen-Hint nach dem zweiten Guard-Treffer
Role = Literal["tutor", "student", "grader", "hint"]
LLM_ROLES: tuple[str, ...] = ("tutor", "grader")
SESSION_ID_PATTERN = r"^s-[0-9a-f]{8}$"
SessionId = Annotated[str, StringConstraints(pattern=SESSION_ID_PATTERN)]
PromptHash = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
# A/B-Test Stufe 0: welcher Arm für die Sitzung gilt (Umgebungsvariable HOOK).
Hook = Literal["incident", "none"]
# Warum ein Grader-Urteil auf partial gesetzt wurde. Details stehen in den
# Warnungen von core.grader.GraderResult, nicht im Log.
#   empty_output      Modell hat nichts geliefert
#   invalid_json      Ausgabe ist kein gültiges JSON
#   not_an_object     JSON, aber kein Objekt
#   schema_violation  Objekt, aber verdict/evidence/misconception ungültig
#   quote_not_found   recognized ohne echtes Zitat aus der Antwort, herabgestuft
GraderError = Literal["empty_output", "invalid_json", "not_an_object", "schema_violation", "quote_not_found"]
# Warum ein hint-Turn statt einer Tutor-Frage gezeigt wurde (core.leak_guard):
#   guard      zweiter Guard-Treffer
#   llm_error  Tutor hat nicht geantwortet (Proxy, Timeout, leere Antwort)
Fallback = Literal["guard", "llm_error"]


class Turn(_Model):
    """Eine Zeile im JSONL-Log (Abschnitt "Logging").

    Die Feldreihenfolge ist die Reihenfolge im Log: zuerst die Felder der
    Spezifikation, danach die Ergänzungen. Es gibt bewusst kein Feld für Namen
    oder E-Mail-Adressen; `extra="forbid"` verhindert, dass eines dazukommt.

    Regeln pro Rolle (`_check_role`):
    - `prompt_version`, `model`, `temperature`, `prompt_hash`, `cache_hit`:
      Pflicht bei tutor und grader, sonst null.
    - `n_examples`, `attempt`: Pflicht bei tutor, sonst null.
    - `fallback`: Pflicht bei hint, sonst null.
    - `verdict`: Pflicht bei grader, sonst null. `error` nur bei grader und
      nur zusammen mit partial.
    - `guard_hit`: nur bei tutor.
    """

    session: SessionId
    exercise: ExerciseId
    stage: int
    role: Role
    prompt_version: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0)
    text: str
    guard_hit: bool = False
    verdict: Verdict | None = None
    ts: AwareDatetime  # ISO 8601 mit Zeitzone; naive Zeitstempel sind ein Fehler
    prior_knowledge: PriorKnowledge
    hook: Hook
    # SHA-256 des fertig eingesetzten System-Prompts (inkl. Few-Shot). Die
    # Version allein reicht nicht: Die Beispiele ändern sich mit den Übungen.
    prompt_hash: PromptHash | None = None
    n_examples: int | None = Field(default=None, ge=0)  # Few-Shot-Beispiele im Tutor-Prompt
    # Versuch des Tutors für diese Frage: 1, oder 2 nach einem Guard-Treffer
    # (mit tutor_strict). Die Leak-Rate zählt nur attempt=1.
    attempt: int | None = Field(default=None, ge=1, le=2)
    cache_hit: bool | None = None  # Antwort kam aus dem Cache des Proxys
    # Nur bei hint: warum der Expert:innen-Hint statt einer Tutor-Frage kam.
    fallback: Fallback | None = None
    error: GraderError | None = None

    @field_validator("stage")
    @classmethod
    def _known_stage(cls, value: int) -> int:
        # Stufe 0 (Hook) hat keine Frage und keine Antwort, also keinen Turn.
        if value not in STAGES:
            raise ValueError(f"Stufe muss 1, 2 oder 3 sein, nicht {value!r}")
        return value

    @model_validator(mode="after")
    def _check_role(self) -> Turn:
        violations: list[Violation] = []
        llm_fields = {
            "prompt_version": self.prompt_version,
            "model": self.model,
            "temperature": self.temperature,
            "prompt_hash": self.prompt_hash,
            "cache_hit": self.cache_hit,
        }

        if self.role in LLM_ROLES:
            for name, value in llm_fields.items():
                if value is None or (isinstance(value, str) and not value.strip()):
                    violations.append(Violation(name, f"Pflicht bei role={self.role}"))
            # Prompt-Dateien heissen <role>_v<n>.md (Abschnitt "Prompts").
            if self.prompt_version and not _matches_prompt_version(self.prompt_version, self.role):
                violations.append(Violation("prompt_version", f"muss {self.role}_v<n> sein"))
        else:
            for name, value in llm_fields.items():
                if value is not None:
                    violations.append(Violation(name, f"nur bei tutor und grader erlaubt, nicht bei {self.role}"))

        for name, value in (("n_examples", self.n_examples), ("attempt", self.attempt)):
            if self.role == "tutor" and value is None:
                violations.append(Violation(name, "Pflicht bei role=tutor"))
            if self.role != "tutor" and value is not None:
                violations.append(Violation(name, "nur bei role=tutor erlaubt"))
        if self.role == "hint" and self.fallback is None:
            violations.append(Violation("fallback", "Pflicht bei role=hint"))
        if self.role != "hint" and self.fallback is not None:
            violations.append(Violation("fallback", "nur bei role=hint erlaubt"))
        if self.role == "grader" and self.verdict is None:
            violations.append(Violation("verdict", "Pflicht bei role=grader"))
        if self.role != "grader" and self.verdict is not None:
            violations.append(Violation("verdict", "nur bei role=grader erlaubt"))
        if self.guard_hit and self.role != "tutor":
            violations.append(Violation("guard_hit", "nur bei role=tutor möglich"))
        if self.error is not None:
            if self.role != "grader":
                violations.append(Violation("error", "nur bei role=grader erlaubt"))
            elif self.verdict is not Verdict.PARTIAL:
                violations.append(Violation("error", "bei einem Fehler ist das Urteil immer partial"))

        if violations:
            raise RuleViolations(violations)
        return self


def _matches_prompt_version(value: str, role: str) -> bool:
    return re.fullmatch(rf"{role}_v[1-9][0-9]*", value) is not None
