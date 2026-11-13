"""Pro Validierungsregel ein gültiger und ein ungültiger Fall.

Jeder ungültige Fall prüft, dass die Meldung Datei, Feld und Regel nennt.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from core.exercises import ExerciseValidationError, load_all, load_exercise
from tests.conftest import EXERCISES_DIR

Writer = Callable[..., Path]


def _problems(path: Path) -> list[str]:
    with pytest.raises(ExerciseValidationError) as info:
        load_exercise(path)
    return info.value.problems


def _assert_problem(problems: list[str], path: Path, field: str, rule_fragment: str) -> None:
    prefix = f"{path}: {field}: "
    matching = [p for p in problems if p.startswith(prefix) and rule_fragment in p]
    assert matching, f"erwartet {prefix}…{rule_fragment}…, bekommen: {problems}"


# --- Echte Übungen -----------------------------------------------------------


def test_real_exercises_load_without_errors() -> None:
    exercises = load_all(EXERCISES_DIR)
    assert list(exercises) == ["api-key-frontend", "strapi-public-create"]


# --- Gültiger Grundfall --------------------------------------------------------


def test_valid_file_loads(write_exercise: Writer, valid_data: dict[str, Any]) -> None:
    exercise = load_exercise(write_exercise(valid_data))
    assert exercise.id == "beispiel"


def test_load_exercise_accepts_str_path(write_exercise: Writer, valid_data: dict[str, Any]) -> None:
    assert load_exercise(str(write_exercise(valid_data))).id == "beispiel"


# --- Regel: Stufen 1, 2 und 3 vorhanden ----------------------------------------


@pytest.mark.parametrize("missing", [1, 2, 3])
def test_missing_stage(write_exercise: Writer, valid_data: dict[str, Any], missing: int) -> None:
    del valid_data["stages"][missing]
    path = write_exercise(valid_data)
    _assert_problem(_problems(path), path, "stages", f"fehlt: [{missing}]")


def test_unknown_stage(write_exercise: Writer, valid_data: dict[str, Any]) -> None:
    valid_data["stages"][4] = {"goal": "g", "hint": "h", "forbidden": ["x"]}
    path = write_exercise(valid_data)
    _assert_problem(_problems(path), path, "stages", "unbekannt: [4]")


def test_stage_key_must_be_a_number(write_exercise: Writer, valid_data: dict[str, Any]) -> None:
    valid_data["stages"]["eins"] = valid_data["stages"].pop(1)
    path = write_exercise(valid_data)
    _assert_problem(_problems(path), path, "stages.eins.[key]", "")


# --- Regel: goal und hint nicht leer -------------------------------------------


@pytest.mark.parametrize("field", ["goal", "hint"])
@pytest.mark.parametrize("value", ["", "   \n"])
def test_empty_goal_or_hint(write_exercise: Writer, valid_data: dict[str, Any], field: str, value: str) -> None:
    valid_data["stages"][2][field] = value
    path = write_exercise(valid_data)
    _assert_problem(_problems(path), path, f"stages.2.{field}", "darf nicht leer sein")


@pytest.mark.parametrize("field", ["goal", "hint", "forbidden"])
def test_missing_stage_field(write_exercise: Writer, valid_data: dict[str, Any], field: str) -> None:
    del valid_data["stages"][1][field]
    path = write_exercise(valid_data)
    _assert_problem(_problems(path), path, f"stages.1.{field}", "Pflichtfeld fehlt")


# --- Regel: forbidden für Stufe 1 und 2 nicht leer -----------------------------


@pytest.mark.parametrize("stage", [1, 2])
def test_empty_forbidden_in_guarded_stage(write_exercise: Writer, valid_data: dict[str, Any], stage: int) -> None:
    valid_data["stages"][stage]["forbidden"] = []
    path = write_exercise(valid_data)
    _assert_problem(_problems(path), path, f"stages.{stage}.forbidden", "nicht leer")


def test_empty_forbidden_allowed_in_stage_3(write_exercise: Writer, valid_data: dict[str, Any]) -> None:
    valid_data["stages"][3]["forbidden"] = []
    assert load_exercise(write_exercise(valid_data)).stages[3].forbidden == []


def test_blank_forbidden_term(write_exercise: Writer, valid_data: dict[str, Any]) -> None:
    valid_data["stages"][1]["forbidden"] = ["Schlüssel", " "]
    path = write_exercise(valid_data)
    _assert_problem(_problems(path), path, "stages.1.forbidden.1", "darf nicht leer sein")


# --- Regel: decoy explizit gesetzt ---------------------------------------------


@pytest.mark.parametrize("value", [True, False])
def test_decoy_set(write_exercise: Writer, valid_data: dict[str, Any], value: bool) -> None:
    valid_data["decoy"] = value
    assert load_exercise(write_exercise(valid_data)).decoy is value


def test_decoy_missing(write_exercise: Writer, valid_data: dict[str, Any]) -> None:
    del valid_data["decoy"]
    path = write_exercise(valid_data)
    _assert_problem(_problems(path), path, "decoy", "Pflichtfeld fehlt")


@pytest.mark.parametrize("value", ["ja", "false", 0, None])
def test_decoy_not_a_bool(write_exercise: Writer, valid_data: dict[str, Any], value: Any) -> None:
    valid_data["decoy"] = value
    path = write_exercise(valid_data)
    _assert_problem(_problems(path), path, "decoy", "true oder false")


# --- Regel: answer_key.accepted mindestens 2 Einträge --------------------------


def test_accepted_with_two_entries(write_exercise: Writer, valid_data: dict[str, Any]) -> None:
    assert len(load_exercise(write_exercise(valid_data)).answer_key.accepted) == 2


@pytest.mark.parametrize("accepted", [[], ["nur eine"]])
def test_accepted_too_short(write_exercise: Writer, valid_data: dict[str, Any], accepted: list[str]) -> None:
    valid_data["answer_key"]["accepted"] = accepted
    path = write_exercise(valid_data)
    _assert_problem(_problems(path), path, "answer_key.accepted", "mindestens 2")


# --- Regel: hint enthält keine eigenen forbidden-Begriffe ----------------------


@pytest.mark.parametrize(
    "hint",
    [
        "Wo steht der Schlüssel?",
        "Wo steht der Schluessel?",  # Umlaut-Umschreibung
        "Wo steht der SCHLÜSSEL!",  # Gross/klein, Satzzeichen
        "Siehst du den api_key?",  # Bindestrich vs. Unterstrich
    ],
)
def test_hint_contains_own_forbidden_term(write_exercise: Writer, valid_data: dict[str, Any], hint: str) -> None:
    valid_data["stages"][1]["hint"] = hint
    path = write_exercise(valid_data)
    _assert_problem(_problems(path), path, "stages.1.hint", "forbidden-Begriffe")


def test_hint_may_contain_forbidden_term_of_other_stage(write_exercise: Writer, valid_data: dict[str, Any]) -> None:
    # "secret" ist nur in Stufe 2 verboten, nicht in Stufe 1.
    valid_data["stages"][1]["hint"] = "Ist das ein secret?"
    assert load_exercise(write_exercise(valid_data))


def test_hint_check_applies_to_stage_3_too(write_exercise: Writer, valid_data: dict[str, Any]) -> None:
    valid_data["stages"][3]["forbidden"] = ["Spam"]
    valid_data["stages"][3]["hint"] = "Was ist mit Spam?"
    path = write_exercise(valid_data)
    _assert_problem(_problems(path), path, "stages.3.hint", "['Spam']")


def test_multiple_stage_violations_are_all_reported(write_exercise: Writer, valid_data: dict[str, Any]) -> None:
    valid_data["stages"][1]["forbidden"] = []
    valid_data["stages"][2]["hint"] = "Wo ist das secret?"
    path = write_exercise(valid_data)
    problems = _problems(path)
    _assert_problem(problems, path, "stages.1.forbidden", "nicht leer")
    _assert_problem(problems, path, "stages.2.hint", "forbidden-Begriffe")


# --- Regel: id entspricht dem Dateinamen ---------------------------------------


def test_id_differs_from_filename(write_exercise: Writer, valid_data: dict[str, Any]) -> None:
    path = write_exercise(valid_data, name="anderer-name.yaml")
    _assert_problem(_problems(path), path, "id", "Dateinamen")


def test_yml_suffix_is_accepted(write_exercise: Writer, valid_data: dict[str, Any]) -> None:
    assert load_exercise(write_exercise(valid_data, name="beispiel.yml")).id == "beispiel"


@pytest.mark.parametrize("bad_id", ["Gross-Buchstaben", "mit leerzeichen", "-start", "ende-", "a--b"])
def test_id_format(write_exercise: Writer, valid_data: dict[str, Any], bad_id: str) -> None:
    valid_data["id"] = bad_id
    path = write_exercise(valid_data, name="x.yaml")
    _assert_problem(_problems(path), path, "id", "Kleinbuchstaben")


# --- Regel: id eindeutig --------------------------------------------------------


def test_unique_ids_load(write_exercise: Writer, valid_data: dict[str, Any], tmp_path: Path) -> None:
    write_exercise(valid_data)
    valid_data["id"] = "zweite"
    write_exercise(valid_data)
    assert list(load_all(tmp_path)) == ["beispiel", "zweite"]


def test_duplicate_id(write_exercise: Writer, valid_data: dict[str, Any], tmp_path: Path) -> None:
    write_exercise(valid_data, name="beispiel.yaml")
    second = write_exercise(valid_data, name="beispiel.yml")
    with pytest.raises(ExerciseValidationError) as info:
        load_all(tmp_path)
    _assert_problem(info.value.problems, second, "id", "eindeutig")


# --- Weitere Feldregeln ---------------------------------------------------------


def test_unknown_field(write_exercise: Writer, valid_data: dict[str, Any]) -> None:
    valid_data["stages"][1]["forbiden"] = ["Tippfehler"]
    path = write_exercise(valid_data)
    _assert_problem(_problems(path), path, "stages.1.forbiden", "unbekanntes Feld")


@pytest.mark.parametrize("value", [0, "1"])
def test_version_must_be_positive_int(write_exercise: Writer, valid_data: dict[str, Any], value: Any) -> None:
    valid_data["version"] = value
    path = write_exercise(valid_data)
    assert any(p.startswith(f"{path}: version: ") for p in _problems(path))


@pytest.mark.parametrize("section", ["scenario", "answer_key", "close"])
def test_missing_section(write_exercise: Writer, valid_data: dict[str, Any], section: str) -> None:
    del valid_data[section]
    path = write_exercise(valid_data)
    _assert_problem(_problems(path), path, section, "Pflichtfeld fehlt")


@pytest.mark.parametrize(("section", "field"), [("scenario", "code"), ("close", "fix"), ("answer_key", "issue")])
def test_empty_text_field(write_exercise: Writer, valid_data: dict[str, Any], section: str, field: str) -> None:
    valid_data[section][field] = " "
    path = write_exercise(valid_data)
    _assert_problem(_problems(path), path, f"{section}.{field}", "darf nicht leer sein")


# --- Dateiebene ------------------------------------------------------------------


def test_invalid_yaml(tmp_path: Path) -> None:
    path = tmp_path / "kaputt.yaml"
    path.write_text("id: [nicht geschlossen\n", encoding="utf-8")
    _assert_problem(_problems(path), path, "(datei)", "ungültiges YAML")


@pytest.mark.parametrize("content", ["", "- eine\n- liste\n", "nur text\n"])
def test_file_is_not_a_mapping(tmp_path: Path, content: str) -> None:
    path = tmp_path / "leer.yaml"
    path.write_text(content, encoding="utf-8")
    _assert_problem(_problems(path), path, "(datei)", "YAML-Objekt")


# --- load_all ----------------------------------------------------------------


def test_load_all_collects_problems_of_all_files(
    write_exercise: Writer, valid_data: dict[str, Any], tmp_path: Path
) -> None:
    valid_data["decoy"] = "ja"
    first = write_exercise(valid_data)
    valid_data["id"] = "zweite"
    valid_data["decoy"] = False
    valid_data["answer_key"]["accepted"] = ["nur eine"]
    second = write_exercise(valid_data)

    with pytest.raises(ExerciseValidationError) as info:
        load_all(tmp_path)

    problems = info.value.problems
    _assert_problem(problems, first, "decoy", "true oder false")
    _assert_problem(problems, second, "answer_key.accepted", "mindestens 2")
    assert str(info.value) == "\n".join(problems)


def test_load_all_ignores_other_files(write_exercise: Writer, valid_data: dict[str, Any], tmp_path: Path) -> None:
    write_exercise(valid_data)
    (tmp_path / "notizen.md").write_text("keine Übung", encoding="utf-8")
    (tmp_path / "unterordner.yaml").mkdir()
    assert list(load_all(tmp_path)) == ["beispiel"]


def test_load_all_empty_folder(tmp_path: Path) -> None:
    assert load_all(tmp_path) == {}


def test_load_all_missing_folder(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_all(tmp_path / "gibt-es-nicht")
