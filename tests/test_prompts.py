from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.exercises import load_all
from core.prompts import (
    FROZEN_FILE,
    PROMPTS_DIR,
    PromptError,
    PromptTemplate,
    available_versions,
    hash_text,
    load_prompt,
    prompt_hash,
    read_frozen,
)
from tests.conftest import EXERCISES_DIR

# Vertrag mit core/tutor.py (I-07) und core/grader.py (I-08), siehe prompts/README.md.
TUTOR_V1_PLACEHOLDERS = {"stage", "goal", "hint", "prior_knowledge", "examples"}
GRADER_V1_PLACEHOLDERS = {"decoy", "issue", "consequence", "accepted", "misconceptions"}


def write(dir_: Path, name: str, text: str) -> Path:
    path = dir_ / name
    path.write_text(text, encoding="utf-8")
    return path


# --- Echte Prompt-Dateien ---------------------------------------------------


def test_tutor_v1_placeholders() -> None:
    assert load_prompt("tutor", 1).placeholders == TUTOR_V1_PLACEHOLDERS


@pytest.mark.parametrize("number", [1, 2])
def test_grader_placeholders(number: int) -> None:
    # v2 ändert nur die Rubrik, der Vertrag mit core/grader.py bleibt gleich.
    assert load_prompt("grader", number).placeholders == GRADER_V1_PLACEHOLDERS


def test_grader_v2_adds_fix_rule_and_example() -> None:
    v1 = load_prompt("grader", 1).text
    v2 = load_prompt("grader", 2).text
    rule = "Ein Fix ohne Begründung des Problems ist partial."
    assert rule not in v1 and rule in v2
    assert "Man sollte ein zufälliges Token statt der User-ID verwenden." in v2
    # Sonst nichts geändert: v2 ist v1 plus Regel plus Beispiel.
    removed = [line for line in v1.splitlines() if line not in v2.splitlines()]
    assert removed == []


@pytest.mark.parametrize("number", [1, 2])
def test_grader_gets_no_prior_knowledge(number: int) -> None:
    # Sonst bewertet der Grader dieselbe Antwort je nach Segment anders (I-08, H11).
    template = load_prompt("grader", number)
    assert "prior_knowledge" not in template.placeholders
    assert not re.search(r"vorwissen|experienced|basics", template.text, re.IGNORECASE)


@pytest.mark.parametrize(("role", "required"), [
    ("tutor", ["Feed back", "Feed up", "Feed forward", "neutral", "experienced", "basics", "new", "Beispiele"]),
    ("grader", ["recognized", "partial", "not", "Im Zweifel partial", "Decoy-Regel", "Beispiele", '"verdict"',
                '"evidence"', '"misconception"']),
])  # fmt: skip
def test_v1_covers_issue_requirements(role: str, required: list[str]) -> None:
    text = load_prompt(role, 1).text
    missing = [r for r in required if r not in text]
    assert not missing


ALL_PROMPTS = [("tutor", 1), ("grader", 1), ("grader", 2), ("tutor_strict", 1)]


def test_tutor_strict_v1_has_no_placeholders() -> None:
    # Wird unverändert an den Tutor-Prompt angehängt.
    template = load_prompt("tutor_strict", 1)
    assert template.placeholders == frozenset()
    assert template.version == "tutor_strict_v1"


def test_tutor_strict_is_not_a_tutor_version(tmp_path: Path) -> None:
    # tutor_strict_v1.md darf nicht als Tutor-Version zählen.
    for name in ["tutor_v1.md", "tutor_strict_v1.md", "tutor_strict_v2.md"]:
        write(tmp_path, name, "x")
    assert available_versions("tutor", tmp_path) == [1]
    assert available_versions("tutor_strict", tmp_path) == [1, 2]


@pytest.mark.parametrize(("role", "number"), ALL_PROMPTS)
def test_prompts_use_swiss_spelling(role: str, number: int) -> None:
    assert "ß" not in load_prompt(role, number).text


@pytest.mark.parametrize(("role", "number"), ALL_PROMPTS)
def test_prompts_contain_no_content_from_real_exercises(role: str, number: int) -> None:
    # Tutor: Few-Shot kommt dynamisch aus anderen Übungen, nie fest im Prompt.
    # Grader: gelabelte Beispiele dürfen nicht aus echten Übungen stammen.
    text = load_prompt(role, number).text
    for exercise in load_all(EXERCISES_DIR).values():
        snippets = [s.hint for s in exercise.stages.values()] + list(exercise.answer_key.accepted)
        leaked = [s for s in snippets if s in text]
        assert not leaked, exercise.id


@pytest.mark.parametrize("number", [1, 2])
def test_grader_example_outputs_match_schema(number: int) -> None:
    # Die Beispielausgaben sind das Vorbild für das Modell, sie müssen selbst gültig sein.
    import json

    text = load_prompt("grader", number).text
    examples = [json.loads(line) for line in text.splitlines() if line.startswith('{"verdict": "') and "|" not in line]
    assert len(examples) >= 6
    for ex in examples:
        assert set(ex) == {"verdict", "evidence", "misconception"}
        assert ex["verdict"] in {"recognized", "partial", "not"}
    assert {ex["verdict"] for ex in examples} == {"recognized", "partial", "not"}


def test_rendered_v1_has_no_placeholders_left() -> None:
    values = {name: f"<{name}>" for name in TUTOR_V1_PLACEHOLDERS}
    rendered = load_prompt("tutor", 1).render(values)
    assert "{{" not in rendered and "}}" not in rendered
    assert "<goal>" in rendered


def test_available_versions_lists_real_files() -> None:
    assert 1 in available_versions("tutor")
    assert {1, 2} <= set(available_versions("grader"))


# --- Eingefrorene Versionen -------------------------------------------------


def test_frozen_prompts_are_unchanged() -> None:
    for name, digest in read_frozen().items():
        path = PROMPTS_DIR / name
        assert path.is_file(), f"{name} steht in frozen.txt, existiert aber nicht"
        assert prompt_hash(path) == digest, f"{name} ist eingefroren und wurde geändert. Neue Version anlegen."


def test_frozen_file_exists() -> None:
    assert FROZEN_FILE.is_file()


def test_read_frozen_parses_entries_and_comments(tmp_path: Path) -> None:
    digest = "a" * 64
    path = write(tmp_path, "frozen.txt", f"# Kommentar\n\n{digest}  tutor_v1.md  # nach Eval-Lauf 1\n")
    assert read_frozen(path) == {"tutor_v1.md": digest}


@pytest.mark.parametrize("line", ["kein-hash  tutor_v1.md", "a" * 64, f"{'a' * 64}  x.md  y.md", f"{'A' * 64}  x.md"])
def test_read_frozen_rejects_bad_lines(tmp_path: Path, line: str) -> None:
    with pytest.raises(PromptError, match="frozen.txt:1"):
        read_frozen(write(tmp_path, "frozen.txt", line + "\n"))


def test_read_frozen_rejects_duplicates(tmp_path: Path) -> None:
    line = f"{'a' * 64}  tutor_v1.md\n"
    with pytest.raises(PromptError, match="doppelt"):
        read_frozen(write(tmp_path, "frozen.txt", line * 2))


def test_hash_ignores_line_endings(tmp_path: Path) -> None:
    lf = tmp_path / "lf.md"
    crlf = tmp_path / "crlf.md"
    lf.write_bytes(b"Zeile 1\nZeile 2\n")
    crlf.write_bytes(b"Zeile 1\r\nZeile 2\r\n")
    assert prompt_hash(lf) == prompt_hash(crlf)


def test_hash_text_matches_file_hash_and_ignores_line_endings(tmp_path: Path) -> None:
    path = tmp_path / "x.md"
    path.write_bytes(b"A\r\nB\n")
    assert hash_text("A\nB\n") == hash_text("A\r\nB\r\n") == hash_text("A\rB\r") == prompt_hash(path)
    assert re.fullmatch(r"[0-9a-f]{64}", hash_text(""))


def test_hash_changes_with_content(tmp_path: Path) -> None:
    a = write(tmp_path, "a.md", "Text")
    b = write(tmp_path, "b.md", "Text.")
    assert prompt_hash(a) != prompt_hash(b)


# --- Loader -----------------------------------------------------------------


def test_load_by_role_and_version(tmp_path: Path) -> None:
    write(tmp_path, "tutor_v2.md", "Ziel: {{goal}}")
    template = load_prompt("tutor", 2, tmp_path)
    assert template.version == "tutor_v2"
    assert template.role == "tutor"
    assert template.number == 2
    assert template.placeholders == {"goal"}


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(PromptError, match="tutor_v7.md: Datei nicht gefunden"):
        load_prompt("tutor", 7, tmp_path)


def test_empty_file(tmp_path: Path) -> None:
    write(tmp_path, "tutor_v1.md", "  \n")
    with pytest.raises(PromptError, match="leer"):
        load_prompt("tutor", 1, tmp_path)


@pytest.mark.parametrize("role", ["student", "hint", "Tutor", "", "strict"])
def test_unknown_role(tmp_path: Path, role: str) -> None:
    with pytest.raises(PromptError, match="Rolle"):
        load_prompt(role, 1, tmp_path)


@pytest.mark.parametrize("number", [0, -1, True, "1", 1.0])
def test_invalid_version(tmp_path: Path, number: object) -> None:
    with pytest.raises(PromptError, match="Version"):
        load_prompt("tutor", number, tmp_path)  # type: ignore[arg-type]


@pytest.mark.parametrize("text", ["{{ Goal }}", "{{goal}", "{goal}}", "{{1goal}}", "{{go-al}}", "{{}}", "a }} b"])
def test_invalid_placeholder_syntax(tmp_path: Path, text: str) -> None:
    write(tmp_path, "tutor_v1.md", text)
    with pytest.raises(PromptError, match="ungültiger Platzhalter"):
        load_prompt("tutor", 1, tmp_path)


def test_single_braces_are_plain_text(tmp_path: Path) -> None:
    write(tmp_path, "grader_v1.md", '{"verdict": "partial"} und {{issue}}')
    template = load_prompt("grader", 1, tmp_path)
    assert template.placeholders == {"issue"}
    assert template.render({"issue": "X"}) == '{"verdict": "partial"} und X'


def test_available_versions_sorted_and_filtered(tmp_path: Path) -> None:
    for name in ["tutor_v10.md", "tutor_v2.md", "tutor_v1.md", "tutor_v01.md", "tutor_vx.md", "grader_v3.md"]:
        write(tmp_path, name, "x")
    assert available_versions("tutor", tmp_path) == [1, 2, 10]
    assert available_versions("grader", tmp_path) == [3]


# --- render -----------------------------------------------------------------


def template(text: str) -> PromptTemplate:
    return PromptTemplate(role="tutor", number=1, text=text)


def test_render_replaces_all_occurrences_and_allows_spaces() -> None:
    assert template("{{a}} und {{ a }} und {{b}}").render({"a": "1", "b": "2"}) == "1 und 1 und 2"


def test_render_missing_value() -> None:
    with pytest.raises(PromptError, match=r"tutor_v1: fehlende Werte: \['b'\]"):
        template("{{a}} {{b}}").render({"a": "1"})


def test_render_unknown_value() -> None:
    with pytest.raises(PromptError, match=r"unbekannte Werte: \['c'\]"):
        template("{{a}}").render({"a": "1", "c": "3"})


def test_render_non_string_value() -> None:
    with pytest.raises(PromptError, match="Text"):
        template("Stufe {{stage}}").render({"stage": 2})  # type: ignore[dict-item]


def test_render_does_not_substitute_inside_values() -> None:
    # Ein Hint oder eine Antwort mit {{…}} darf keine weiteren Platzhalter auslösen.
    result = template("{{hint}} / {{goal}}").render({"hint": "{{goal}}", "goal": "Ziel"})
    assert result == "{{goal}} / Ziel"


def test_render_keeps_backslashes_literal() -> None:
    # re.sub mit Funktion: \1 oder \n im Wert werden nicht interpretiert.
    assert template("{{a}}").render({"a": r"C:\new\1"}) == r"C:\new\1"
