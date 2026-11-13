from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from core.models import Exercise, RuleViolations, Violation

SECRETS = ("GEHEIMES-PROBLEM", "GEHEIME-FOLGE", "Antwort A", "Antwort B", "GEHEIMER-FIX", "GEHEIMES-PRUEFMUSTER")


def test_valid_exercise_builds(valid_data: dict[str, Any]) -> None:
    exercise = Exercise.model_validate(valid_data)
    assert exercise.id == "beispiel"
    assert set(exercise.stages) == {1, 2, 3}
    assert exercise.hook is None


def test_hook_is_optional_text(valid_data: dict[str, Any]) -> None:
    valid_data["hook"] = "2023 wurde ein Key aus einer Kursseite missbraucht."
    assert Exercise.model_validate(valid_data).hook is not None


def test_exercise_is_immutable(valid_data: dict[str, Any]) -> None:
    exercise = Exercise.model_validate(valid_data)
    with pytest.raises(ValidationError):
        exercise.decoy = True  # type: ignore[misc]


@pytest.mark.parametrize("stage", [1, 2])
def test_tutor_context_hides_answer_key_and_close(valid_data: dict[str, Any], stage: int) -> None:
    context = Exercise.model_validate(valid_data).tutor_context(stage)

    assert set(context) == {"exercise_id", "stage", "goal", "hint"}
    assert "answer_key" not in context
    assert "close" not in context
    # Auch die Inhalte dürfen nicht unter anderem Namen hineinrutschen.
    flat = repr(context)
    for secret in SECRETS:
        assert secret not in flat


@pytest.mark.parametrize("stage", [1, 2, 3])
def test_tutor_context_returns_goal_and_hint_of_that_stage(valid_data: dict[str, Any], stage: int) -> None:
    context = Exercise.model_validate(valid_data).tutor_context(stage)
    assert context == {
        "exercise_id": "beispiel",
        "stage": stage,
        "goal": valid_data["stages"][stage]["goal"],
        "hint": valid_data["stages"][stage]["hint"],
    }


def test_tutor_context_hides_forbidden_terms(valid_data: dict[str, Any]) -> None:
    context = Exercise.model_validate(valid_data).tutor_context(1)
    assert "forbidden" not in context


@pytest.mark.parametrize("stage", [0, 4, -1])
def test_tutor_context_rejects_unknown_stage(valid_data: dict[str, Any], stage: int) -> None:
    with pytest.raises(ValueError, match="Stufe muss 1, 2 oder 3 sein"):
        Exercise.model_validate(valid_data).tutor_context(stage)


def test_rule_violations_message_lists_all_violations() -> None:
    error = RuleViolations([Violation("stages.1.hint", "Regel A"), Violation("stages", "Regel B")])
    assert str(error) == "stages.1.hint: Regel A; stages: Regel B"
    assert isinstance(error, ValueError)
