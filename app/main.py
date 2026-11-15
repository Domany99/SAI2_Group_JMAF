"""Streamlit-UI für Schritt 2: fixe Fragen, ohne LLM.

Start im Repo-Hauptordner:

    streamlit run app/main.py

Die Fragen sind die Expert:innen-Hints aus den Übungsdateien. Die Antworten
bewertet die Testleitung per Knopf. In Schritt 3 ersetzt LLM 1 die fixen
Fragen und LLM 2 die Knöpfe. Die Stufen-Logik bleibt dieselbe.

Umgebungsvariable HOOK=incident zeigt Stufe 0 (Vorfall-Hook), falls die Übung
einen `hook` hat. Standard ist HOOK=none.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# `streamlit run app/main.py` legt nur app/ in den Suchpfad. Für `import core`
# braucht es den Repo-Hauptordner.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st  # noqa: E402

from core.exercises import load_all  # noqa: E402
from core.models import Exercise  # noqa: E402
from core.stages import LAST_STAGE, Outcome, Verdict, finish_hook, on_verdict, start  # noqa: E402

HOOK_ENABLED = os.environ.get("HOOK", "none").strip().lower() == "incident"

VERDICT_BUTTONS = [
    (Verdict.RECOGNIZED, "Erkannt"),
    (Verdict.PARTIAL, "Teilweise"),
    (Verdict.NOT, "Nicht erkannt"),
]
VERDICT_LABELS = dict(VERDICT_BUTTONS)

st.set_page_config(page_title="Security-Tutor", page_icon="🛡️", layout="wide")


@st.cache_resource
def get_exercises() -> dict[str, Exercise]:
    return load_all(REPO_ROOT / "exercises")


# --- Sitzungszustand -------------------------------------------------------


def begin(exercise_id: str) -> None:
    exercise = get_exercises()[exercise_id]
    st.session_state.exercise_id = exercise_id
    st.session_state.state = start(with_hook=HOOK_ENABLED and exercise.hook is not None)
    st.session_state.history = []  # pro Antwort: Stufe, Frage, Antwort, Urteil
    st.session_state.pending = None  # Antwort, die noch bewertet werden muss


def back_to_selection() -> None:
    for key in ("exercise_id", "state", "history", "pending"):
        st.session_state.pop(key, None)


def submit_answer() -> None:
    answer = st.session_state.get("answer_input", "").strip()
    if answer:
        st.session_state.pending = answer
        st.session_state.answer_input = ""


def judge(verdict: Verdict) -> None:
    exercise = get_exercises()[st.session_state.exercise_id]
    state = st.session_state.state
    st.session_state.history.append(
        {
            "stage": state.stage,
            "question": exercise.stages[state.stage].hint,
            "answer": st.session_state.pending,
            "verdict": verdict,
        }
    )
    st.session_state.state = on_verdict(state, verdict)
    st.session_state.pending = None


def leave_hook() -> None:
    st.session_state.state = finish_hook(st.session_state.state)


# --- Ansichten -------------------------------------------------------------


def show_selection(exercises: dict[str, Exercise]) -> None:
    st.title("Findest du die unsichere Entscheidung?")
    st.write(
        "Jede Übung zeigt einen Kursauftrag, den Chat mit der KI und den Code, den die KI "
        "geliefert hat. Der Tutor nennt die Lücke nicht. Er stellt dir bis zu drei Fragen, "
        "die dich hinführen."
    )
    choice = st.radio(
        "Übung",
        options=list(exercises),
        format_func=lambda exercise_id: exercises[exercise_id].title,
    )
    st.button("Übung starten", type="primary", on_click=begin, args=(choice,))


def show_scenario(exercise: Exercise) -> None:
    st.header(exercise.title)
    st.subheader("Kursauftrag")
    st.write(exercise.scenario.requirement)
    st.subheader("Chat mit der KI")
    if exercise.scenario.ai_chat.lstrip().upper().startswith("TODO"):
        st.info("Platzhalter: Der Auszug aus dem echten Testchat fehlt in der Übungsdatei noch.")
    else:
        st.markdown(exercise.scenario.ai_chat)
    st.subheader("Code der KI")
    code = exercise.scenario.code
    st.code(code, language="html" if code.lstrip().startswith("<") else "javascript")


def show_history() -> None:
    for turn in st.session_state.history:
        with st.chat_message("assistant", avatar="🛡️"):
            st.markdown(f"**Stufe {turn['stage']}:** {turn['question']}")
        with st.chat_message("user"):
            st.write(turn["answer"])
            st.caption(f"Testleitung: {VERDICT_LABELS[turn['verdict']]}")


def show_progress(stage: int, done: bool) -> None:
    current = LAST_STAGE + 1 if done else stage
    labels = [f"Stufe {n}" for n in range(1, LAST_STAGE + 1)] + ["Abschluss"]
    parts = []
    for n, label in enumerate(labels, start=1):
        parts.append(f"**{label}**" if n == current else label)
    st.caption(" → ".join(parts))


def show_tutor(exercise: Exercise) -> None:
    state = st.session_state.state

    if state.in_hook:
        with st.chat_message("assistant", avatar="🛡️"):
            st.markdown(exercise.hook or "")
        st.button("Weiter zur Übung", type="primary", on_click=leave_hook)
        return

    show_progress(state.stage, state.done)
    show_history()

    if not state.done:
        with st.chat_message("assistant", avatar="🛡️"):
            st.markdown(f"**Stufe {state.stage} von {LAST_STAGE}:** {exercise.stages[state.stage].hint}")

        if st.session_state.pending is None:
            with st.form("answer_form", clear_on_submit=False):
                st.text_area(
                    "Deine Antwort",
                    key="answer_input",
                    placeholder="Beschreib in eigenen Worten, was dir auffällt …",
                )
                st.form_submit_button("Antwort senden", type="primary", on_click=submit_answer)
        else:
            with st.chat_message("user"):
                st.write(st.session_state.pending)
            with st.container(border=True):
                st.markdown("**Nur im Test:** Die Testleitung beurteilt die Antwort (ersetzt später LLM 2).")
                columns = st.columns(len(VERDICT_BUTTONS))
                for column, (verdict, label) in zip(columns, VERDICT_BUTTONS):
                    column.button(label, key=f"verdict_{verdict}", on_click=judge, args=(verdict,), use_container_width=True)
        return

    show_close(exercise, state.outcome, state.stage)


def show_close(exercise: Exercise, outcome: Outcome | None, stage: int) -> None:
    if outcome is Outcome.RECOGNIZED:
        st.success(f"Gefunden auf Stufe {stage}. Du hast die Lücke selbst entdeckt.")
    else:
        st.warning("Auflösung nach Stufe 3: Das war die unsichere Entscheidung.")
    st.markdown(f"**Problem:** {exercise.answer_key.issue}")
    st.markdown(f"**Folge:** {exercise.answer_key.consequence}")
    st.markdown(f"**So behebst du es:** {exercise.close.fix}")
    st.info(f"**Prüfmuster zum Mitnehmen:** {exercise.close.pruefmuster}")

    left, right = st.columns(2)
    left.button("Übung wiederholen", type="primary", on_click=begin, args=(exercise.id,), use_container_width=True)
    right.button("Andere Übung wählen", on_click=back_to_selection, use_container_width=True)


def main() -> None:
    exercises = get_exercises()

    with st.sidebar:
        st.markdown("### Security-Tutor")
        st.caption("Prototyp, Schritt 2: fixe Fragen, ohne LLM")
        if "exercise_id" in st.session_state:
            st.button("Andere Übung wählen", on_click=back_to_selection, key="sidebar_back")

    if not exercises:
        st.error("Keine Übungen im Ordner exercises/ gefunden.")
        return

    if "exercise_id" not in st.session_state:
        show_selection(exercises)
        return

    exercise = exercises[st.session_state.exercise_id]
    left, right = st.columns([3, 2], gap="large")
    with left:
        show_scenario(exercise)
    with right:
        show_tutor(exercise)


main()
