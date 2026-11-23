"""Beheben-Phase nach dem Abschluss der Stufen (app/main.py, MODE=fixed).

Ablauf laut README (Entscheid "Fix-Auswahl"): zuerst ein eigener Vorschlag,
die Optionen nur auf Wunsch und nur mit Begründung, erst danach Fix und
Prüfmuster. MODE=fixed, damit kein LLM nötig ist; die Testleitung bewertet.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from core.exercises import load_all
from tests.conftest import EXERCISES_DIR
from tests.test_app import APP, answer, log_dir, open_exercise, text_of  # noqa: F401 (log_dir ist eine Fixture)

EXERCISES = load_all(EXERCISES_DIR)
API_KEY = EXERCISES["api-key-frontend"]
DECOY = EXERCISES["kommentare-bereinigt"]
FIX_SUBMIT = "FormSubmitter:fix_form-Vorschlag senden"
CHOICE_SUBMIT = "FormSubmitter:fix_choice_form-Wahl senden"


@pytest.fixture
def fixed_mode(monkeypatch: pytest.MonkeyPatch, log_dir: Path) -> None:  # noqa: F811
    monkeypatch.setenv("MODE", "fixed")


def recognized(exercise_id: str = "api-key-frontend") -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=30)
    open_exercise(at, exercise_id)
    answer(at)
    at.button(key="verdict_recognized").click().run()
    return at


def test_fix_is_not_shown_before_own_proposal(fixed_mode: None) -> None:
    at = recognized()
    text = text_of(at)
    assert "Du hast die Lücke gefunden!" in text
    assert "Wie würdest du das beheben?" in text
    assert API_KEY.close.fix.strip() not in text
    assert API_KEY.close.pruefmuster not in text


def test_own_proposal_then_fix_and_pattern(fixed_mode: None) -> None:
    at = recognized()
    at.text_area(key="fix_input").input("Einen Proxy dazwischen bauen.")
    at.button(key=FIX_SUBMIT).click().run()

    text = text_of(at)
    assert "Einen Proxy dazwischen bauen." in text
    assert API_KEY.close.fix.strip() in text
    assert API_KEY.close.pruefmuster in text
    assert not [r for r in at.radio if r.key == "fix_choice"]  # keine Auswahl nötig


def test_empty_proposal_is_not_accepted(fixed_mode: None) -> None:
    at = recognized()
    at.button(key=FIX_SUBMIT).click().run()
    assert at.session_state["fix_step"] == "ask"
    assert any("Schreib zuerst" in c.value for c in at.caption)


def test_choices_need_a_reason(fixed_mode: None) -> None:
    at = recognized()
    at.button(key="fix_help").click().run()
    radio = at.radio(key="fix_choice")
    assert sorted(radio.options) == sorted(c.text for c in API_KEY.close.fix_choices)  # Texte, nie das Urteil

    correct = next(i for i, c in enumerate(API_KEY.close.fix_choices) if c.verdict == "correct")
    radio.set_value(correct)
    at.button(key=CHOICE_SUBMIT).click().run()
    assert at.session_state["fix_step"] == "choose"  # ohne Begründung geht es nicht weiter
    assert API_KEY.close.fix.strip() not in text_of(at)

    at.text_area(key="fix_reason_input").input("Weil der Key dann nie im Browser landet.")
    at.button(key=CHOICE_SUBMIT).click().run()
    text = text_of(at)
    assert "Passt:" in text
    assert API_KEY.close.fix_choices[correct].reason in text
    assert API_KEY.close.fix.strip() in text


def test_wrong_choice_gets_its_reason(fixed_mode: None) -> None:
    at = recognized()
    at.button(key="fix_help").click().run()
    wrong = next(i for i, c in enumerate(API_KEY.close.fix_choices) if c.verdict == "wrong")
    at.radio(key="fix_choice").set_value(wrong)
    at.text_area(key="fix_reason_input").input("Dann sieht man ihn nicht mehr.")
    at.button(key=CHOICE_SUBMIT).click().run()
    assert "Passt nicht:" in text_of(at)
    assert API_KEY.close.fix_choices[wrong].reason in text_of(at)


def test_choice_order_stays_the_same_across_reruns(fixed_mode: None) -> None:
    at = recognized()
    order = list(at.session_state["fix_order"])
    assert sorted(order) == list(range(len(API_KEY.close.fix_choices)))
    at.button(key="fix_help").click().run()
    at.run()
    assert list(at.session_state["fix_order"]) == order


def test_revealed_after_stage_3_also_asks_for_fix(fixed_mode: None) -> None:
    at = AppTest.from_file(str(APP), default_timeout=30)
    open_exercise(at)
    for _ in range(3):
        answer(at)
        at.button(key="verdict_partial").click().run()
    assert "Das war die unsichere Entscheidung." in text_of(at)
    assert "Wie würdest du das beheben?" in text_of(at)


def test_decoy_does_not_talk_about_a_gap(fixed_mode: None) -> None:
    at = recognized("kommentare-bereinigt")
    text = text_of(at)
    assert "Der Code ist in Ordnung." in text
    assert "Lücke gefunden" not in text
    assert "Würdest du am Code trotzdem etwas ändern?" in text

    at.text_area(key="fix_input").input("Nichts, es wird beim Anzeigen bereinigt.")
    at.button(key=FIX_SUBMIT).click().run()
    assert "Was zu tun ist" in text_of(at)
    assert "So behebst du es" not in text_of(at)
