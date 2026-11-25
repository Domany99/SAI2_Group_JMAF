"""Tests für app/main.py mit Streamlits AppTest. LLM gemockt, Log in tmp_path.

AppTest führt das Skript im selben Prozess aus, deshalb wirken die Mocks auf
`core.tutor.chat`, `core.grader.chat` und `core.llm._config`.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from streamlit.testing.v1 import AppTest

from core import grader, llm, tutor
from core import logging as turn_log
from core.config import ConfigError, LLMConfig
from core.exercises import load_exercise
from core.llm import LLMResult, LLMUnavailableError
from core.logging import read_turns

APP = Path(__file__).resolve().parent.parent / "app" / "main.py"
EXERCISE = "api-key-frontend"
# Aus der Übungsdatei gelesen, damit die Tests Textänderungen an der Übung überstehen.
_EXERCISE_FILE = load_exercise(APP.parent.parent / "exercises" / f"{EXERCISE}.yaml")
_STAGE_1 = _EXERCISE_FILE.stages[1]
HINT_1 = _STAGE_1.hint
LEAK_1 = f"Ist das {_STAGE_1.forbidden[0]}?"  # enthält einen verbotenen Begriff aus Stufe 1
SUBMIT = "FormSubmitter:answer_form-Antwort senden"
TUTOR_QUESTION = "Wer kann das alles im Browser sehen?"
ANSWER = "Den Key sieht jeder im Netzwerk-Tab."


class Scripted:
    """Ersetzt chat() in einem Modul: liefert der Reihe nach Texte oder wirft Fehler."""

    def __init__(self, *outcomes: str | Exception) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def __call__(self, messages: Any, model: str, temperature: float, **kwargs: Any) -> LLMResult:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return LLMResult(
            text=outcome, model=model, temperature=temperature, tokens_in=1, tokens_out=1, latency_ms=5,
            json_mode_requested=False, json_mode_fallback=False, finish_reason="stop",
        )  # fmt: skip


def verdict_json(verdict: str, evidence: str = "Den Key sieht jeder") -> str:
    return json.dumps({"verdict": verdict, "evidence": evidence, "misconception": None})


@pytest.fixture
def log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(turn_log, "LOG_DIR", tmp_path)
    monkeypatch.setenv("HOOK", "none")
    return tmp_path


@pytest.fixture
def llm_mode(monkeypatch: pytest.MonkeyPatch, log_dir: Path) -> None:
    monkeypatch.setenv("MODE", "llm")
    cfg = LLMConfig(
        base_url="https://proxy.test/v1", api_key="sk-test", tutor_model="tutor-m", grader_model="grader-m",
        timeout_s=5, max_retries=0,
    )  # fmt: skip
    monkeypatch.setattr(llm, "_config", cfg)


def logged(log_dir: Path) -> list[Any]:
    return [t for f in sorted(log_dir.glob("*.jsonl")) for t in read_turns(f)]


def text_of(at: AppTest) -> str:
    return "\n".join(m.value for m in at.markdown)


def open_exercise(at: AppTest, exercise_id: str = EXERCISE) -> None:
    at.run()
    at.radio(key="level_choice").set_value("basics").run()
    next(b for b in at.button if b.label.startswith("Weiter")).click().run()
    at.button(key=f"start_{exercise_id}").click().run()


def answer(at: AppTest, text: str = ANSWER) -> None:
    at.text_area(key="answer_input").input(text)
    at.button(key=SUBMIT).click().run()


# --- MODE=fixed -------------------------------------------------------------


def test_fixed_mode_uses_hints_and_buttons_and_logs_nothing(
    monkeypatch: pytest.MonkeyPatch, log_dir: Path
) -> None:
    monkeypatch.setenv("MODE", "fixed")
    chat = Scripted()
    monkeypatch.setattr(tutor, "chat", chat)
    at = AppTest.from_file(str(APP), default_timeout=30)
    open_exercise(at)

    assert HINT_1 in text_of(at)  # Hint aus der Übungsdatei
    answer(at)
    assert at.button(key="verdict_partial")
    at.button(key="verdict_partial").click().run()

    assert not at.exception
    assert "STUFE 2 VON 3" in text_of(at)
    assert chat.calls == 0
    assert logged(log_dir) == []


# --- MODE=llm ---------------------------------------------------------------


def test_llm_mode_question_from_tutor_answer_to_grader(
    monkeypatch: pytest.MonkeyPatch, llm_mode: None, log_dir: Path
) -> None:
    monkeypatch.setattr(tutor, "chat", Scripted(TUTOR_QUESTION))
    monkeypatch.setattr(grader, "chat", Scripted(verdict_json("recognized")))
    at = AppTest.from_file(str(APP), default_timeout=30)
    open_exercise(at)

    assert TUTOR_QUESTION in text_of(at)
    assert not [b for b in at.button if (b.key or "").startswith("verdict_")]  # keine Knöpfe der Testleitung
    answer(at)

    assert not at.exception
    assert "Du hast die Lücke gefunden!" in text_of(at)
    turns = logged(log_dir)
    assert [(t.role, t.stage) for t in turns] == [("tutor", 1), ("student", 1), ("grader", 1)]
    assert turns[1].text == ANSWER
    assert len({t.session for t in turns}) == 1
    assert all(t.hook == "none" and t.prior_knowledge.value == "basics" for t in turns)
    assert {t.exercise_version for t in turns} == {_EXERCISE_FILE.version}


def test_llm_mode_question_is_asked_once_per_stage(
    monkeypatch: pytest.MonkeyPatch, llm_mode: None, log_dir: Path
) -> None:
    tutor_chat = Scripted(TUTOR_QUESTION, "Zweite Frage?")
    monkeypatch.setattr(tutor, "chat", tutor_chat)
    monkeypatch.setattr(grader, "chat", Scripted(verdict_json("not", "Den Key")))
    at = AppTest.from_file(str(APP), default_timeout=30)
    open_exercise(at)
    at.run()  # weitere Reruns erzeugen keine neue Frage
    assert tutor_chat.calls == 1

    answer(at)
    assert "STUFE 2 VON 3" in text_of(at)
    assert "Zweite Frage?" in text_of(at)
    assert tutor_chat.calls == 2


def test_llm_mode_guard_hit_regenerates_and_logs(
    monkeypatch: pytest.MonkeyPatch, llm_mode: None, log_dir: Path
) -> None:
    monkeypatch.setattr(tutor, "chat", Scripted(LEAK_1, TUTOR_QUESTION))
    at = AppTest.from_file(str(APP), default_timeout=30)
    open_exercise(at)

    assert TUTOR_QUESTION in text_of(at)
    assert LEAK_1 not in text_of(at)
    assert [(t.role, t.guard_hit, t.attempt) for t in logged(log_dir)] == [("tutor", True, 1), ("tutor", False, 2)]


def test_llm_mode_tutor_down_shows_hint_with_note(
    monkeypatch: pytest.MonkeyPatch, llm_mode: None, log_dir: Path
) -> None:
    monkeypatch.setattr(tutor, "chat", Scripted(LLMUnavailableError("Timeout")))
    at = AppTest.from_file(str(APP), default_timeout=30)
    open_exercise(at)

    assert HINT_1 in text_of(at)
    assert any("nicht erreichbar" in c.value for c in at.caption)
    [hint] = logged(log_dir)
    assert (hint.role, hint.fallback) == ("hint", "llm_error")


def test_llm_mode_grader_error_shows_message_and_retry(
    monkeypatch: pytest.MonkeyPatch, llm_mode: None, log_dir: Path
) -> None:
    monkeypatch.setattr(tutor, "chat", Scripted(TUTOR_QUESTION))
    grader_chat = Scripted(LLMUnavailableError("LLM-Proxy nicht verfügbar"), verdict_json("recognized"))
    monkeypatch.setattr(grader, "chat", grader_chat)
    at = AppTest.from_file(str(APP), default_timeout=30)
    open_exercise(at)
    answer(at)

    assert not at.exception
    assert any("nicht ausgewertet werden" in e.value for e in at.error)
    assert "STUFE 1 VON 3" in text_of(at)  # Stufe unverändert
    assert grader_chat.calls == 1
    at.run()  # kein automatischer neuer Versuch bei einem Rerun
    assert grader_chat.calls == 1

    at.button(key="retry_grading").click().run()
    assert "Du hast die Lücke gefunden!" in text_of(at)
    assert [t.role for t in logged(log_dir)] == ["tutor", "student", "grader"]  # Antwort nur einmal geloggt


def test_llm_mode_without_config_shows_clear_error(monkeypatch: pytest.MonkeyPatch, log_dir: Path) -> None:
    monkeypatch.setenv("MODE", "llm")
    monkeypatch.setattr(llm, "_config", None)

    def missing() -> LLMConfig:
        raise ConfigError("LLM_API_KEY fehlt. In .env setzen.")

    monkeypatch.setattr(llm, "load_config", missing)
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.run()

    [error] = at.error
    assert "LLM_API_KEY fehlt" in error.value
    assert "MODE=fixed" in error.value
    assert not at.radio  # keine Einstufung, keine Übung


def test_unknown_mode_shows_error(monkeypatch: pytest.MonkeyPatch, log_dir: Path) -> None:
    monkeypatch.setenv("MODE", "turbo")
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.run()
    [error] = at.error
    assert "MODE='turbo'" in error.value


def test_llm_mode_history_shows_no_verdict(
    monkeypatch: pytest.MonkeyPatch, llm_mode: None, log_dir: Path
) -> None:
    # Der Tutor darf Antworten nicht als richtig oder falsch werten, also auch die UI nicht.
    monkeypatch.setattr(tutor, "chat", Scripted(TUTOR_QUESTION, "Zweite Frage?"))
    monkeypatch.setattr(grader, "chat", Scripted(verdict_json("not", "Den Key")))
    at = AppTest.from_file(str(APP), default_timeout=30)
    open_exercise(at)
    answer(at)

    assert "STUFE 2 VON 3" in text_of(at)
    assert ANSWER in text_of(at)  # die Antwort steht im Verlauf
    for label in ("Nicht erkannt", "Teilweise", "Erkannt"):
        assert label not in text_of(at)


def test_code_shows_filename_from_exercise(monkeypatch: pytest.MonkeyPatch, log_dir: Path) -> None:
    monkeypatch.setenv("MODE", "fixed")
    at = AppTest.from_file(str(APP), default_timeout=30)
    open_exercise(at)
    assert _EXERCISE_FILE.scenario.filename in text_of(at)


def test_logo_leads_back_to_overview(monkeypatch: pytest.MonkeyPatch, log_dir: Path) -> None:
    monkeypatch.setenv("MODE", "fixed")
    at = AppTest.from_file(str(APP), default_timeout=30)
    open_exercise(at)
    assert "STUFE 1 VON 3" in text_of(at)

    at.button(key="logo_home").click().run()

    assert not at.exception
    assert "Hält die Entscheidung der KI?" in text_of(at)
    assert "STUFE 1 VON 3" not in text_of(at)
    assert at.button(key=f"start_{EXERCISE}")  # Übersicht mit den Übungskarten


# --- Status pro Übung -------------------------------------------------------


def back_home(at: AppTest) -> None:
    at.button(key="logo_home").click().run()


def test_cards_show_open_status_at_start(monkeypatch: pytest.MonkeyPatch, log_dir: Path) -> None:
    monkeypatch.setenv("MODE", "fixed")
    at = AppTest.from_file(str(APP), default_timeout=30)
    at.run()
    at.radio(key="level_choice").set_value("basics").run()
    next(b for b in at.button if b.label.startswith("Weiter")).click().run()

    assert "Offen" in text_of(at)
    assert "Angefangen" not in text_of(at)
    assert "Erledigt" not in text_of(at)
    assert at.button(key=f"start_{EXERCISE}").label == "Übung starten →"


def test_started_exercise_resumes_at_same_stage(monkeypatch: pytest.MonkeyPatch, log_dir: Path) -> None:
    monkeypatch.setenv("MODE", "fixed")
    at = AppTest.from_file(str(APP), default_timeout=30)
    open_exercise(at)
    answer(at)
    at.button(key="verdict_partial").click().run()
    assert "STUFE 2 VON 3" in text_of(at)

    back_home(at)
    assert "Angefangen · Stufe 2 von 3" in text_of(at)
    assert at.button(key=f"start_{EXERCISE}").label == "Weitermachen →"

    at.button(key=f"start_{EXERCISE}").click().run()
    assert not at.exception
    assert "STUFE 2 VON 3" in text_of(at)
    assert ANSWER in text_of(at)  # Verlauf von Stufe 1 ist noch da


def test_finished_exercise_shows_done_and_can_restart(monkeypatch: pytest.MonkeyPatch, log_dir: Path) -> None:
    monkeypatch.setenv("MODE", "fixed")
    at = AppTest.from_file(str(APP), default_timeout=30)
    open_exercise(at)
    answer(at)
    at.button(key="verdict_recognized").click().run()
    at.text_area(key="fix_input").input("Key auf den Server verschieben.")
    at.button(key="FormSubmitter:fix_form-Vorschlag senden").click().run()

    back_home(at)
    assert "Erledigt" in text_of(at)
    assert at.button(key=f"start_{EXERCISE}").label == "Ergebnis ansehen"

    at.button(key=f"start_{EXERCISE}").click().run()  # Ergebnis bleibt erhalten
    assert "Prüfmuster zum Mitnehmen" in text_of(at)

    back_home(at)
    at.button(key=f"restart_{EXERCISE}").click().run()  # Neustart bei Stufe 1
    assert "STUFE 1 VON 3" in text_of(at)
    assert ANSWER not in text_of(at)


def test_fix_phase_counts_as_started(monkeypatch: pytest.MonkeyPatch, log_dir: Path) -> None:
    monkeypatch.setenv("MODE", "fixed")
    at = AppTest.from_file(str(APP), default_timeout=30)
    open_exercise(at)
    answer(at)
    at.button(key="verdict_recognized").click().run()  # Stufen fertig, Beheben offen

    back_home(at)
    assert "Angefangen · Beheben" in text_of(at)
    at.button(key=f"start_{EXERCISE}").click().run()
    assert at.text_area(key="fix_input")  # wieder in der Beheben-Phase
