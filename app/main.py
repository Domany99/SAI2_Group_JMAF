"""Streamlit-UI des Security-Tutors.

Start im Repo-Hauptordner:

    streamlit run app/main.py

Zwei Modi, Umgebungsvariable `MODE` (auch in `.env`):

- `MODE=llm` (Standard): Die Frage jeder Stufe kommt von LLM 1 über den Leak
  Guard, die Antwort bewertet LLM 2. Jeder Turn wird nach `logs/` geloggt.
  Der Ablauf steht in `core/session.py`, hier nur Anzeige, Ladezustand und
  Fehlermeldungen. Braucht eine gültige `.env` (API-Key) und VPN.
- `MODE=fixed`: Schritt 2, für Tests und als Notfall. Die Fragen sind die
  Expert:innen-Hints, die Testleitung bewertet per Knopf. Kein LLM, kein Log.

Die Stufen-Logik (`core/stages.py`) ist in beiden Modi dieselbe.

Umgebungsvariable HOOK=incident zeigt Stufe 0 (Vorfall-Hook), falls die Übung
einen `hook` hat. Standard ist HOOK=none.

Das Aussehen folgt dem Low-Fi-Prototyp "Mind the Gap" (Navy, Gelb,
Warnstreifen). Die Styles stehen in `CSS` unten, das Theme in
`.streamlit/config.toml`.
"""

from __future__ import annotations

import html
import os
import sys
from pathlib import Path

# `streamlit run app/main.py` legt nur app/ in den Suchpfad. Für `import core`
# braucht es den Repo-Hauptordner.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import streamlit as st  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from core import logging as turn_log  # noqa: E402
from core import session  # noqa: E402
from core.config import ConfigError  # noqa: E402
from core.exercises import load_all  # noqa: E402
from core.llm import LLMError, get_config  # noqa: E402
from core.models import Exercise  # noqa: E402
from core.prior_knowledge import LEVELS, PriorKnowledge  # noqa: E402
from core.stages import LAST_STAGE, Outcome, Verdict, finish_hook, on_verdict, start  # noqa: E402

# MODE und HOOK dürfen auch in .env stehen. Echte Umgebungsvariablen haben Vorrang.
load_dotenv(REPO_ROOT / ".env", override=False)

MODES = ("llm", "fixed")
MODE_LABELS = {
    "llm": "Prototyp · Schritt 3 · Tutor und Grader mit LLM",
    "fixed": "Prototyp · Schritt 2 · fixe Fragen, ohne LLM",
}
MODE = os.environ.get("MODE", "llm").strip().lower()
HOOK = "incident" if os.environ.get("HOOK", "none").strip().lower() == "incident" else "none"
HOOK_ENABLED = HOOK == "incident"

VERDICT_BUTTONS = [
    (Verdict.RECOGNIZED, "Erkannt"),
    (Verdict.PARTIAL, "Teilweise"),
    (Verdict.NOT, "Nicht erkannt"),
]
VERDICT_LABELS = dict(VERDICT_BUTTONS)

NAVY = "#0b1726"
PANEL = "#0f1f33"
YELLOW = "#ffd21f"

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;700&family=Space+Grotesk:wght@500;700&display=swap');

html, body, .stApp, .stApp p, .stApp label, .stApp textarea, .stApp button {{
  font-family: Inter, system-ui, sans-serif;
}}
.stApp {{ background: #ffffff; color: {NAVY}; }}
header[data-testid="stHeader"] {{ display: none; }}
:root {{ --pad: clamp(16px, 3.5vw, 56px); }}
.block-container {{
  padding: 0 var(--pad) 64px !important; max-width: none !important;
}}
h1, h2, h3 {{ font-family: 'Space Grotesk', system-ui, sans-serif !important; color: {NAVY}; letter-spacing: -0.01em; }}

/* Header und Warnstreifen */
.mtg-header {{
  display: flex; flex-wrap: wrap; align-items: center; gap: 24px;
  margin: 0 calc(-1 * var(--pad)); padding: 14px var(--pad); background: {NAVY}; color: #ffffff;
}}
.mtg-logo {{ display: flex; align-items: center; gap: 6px; }}
.mtg-logo b {{ font-family: 'Space Grotesk', sans-serif; font-size: 18px; }}
.mtg-logo span {{
  font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 15px;
  background: {YELLOW}; color: {NAVY}; padding: 2px 7px; border-radius: 5px;
}}
.mtg-header .mtg-lesson {{
  flex: 1 1 260px; display: flex; align-items: center; gap: 14px;
  font-family: 'JetBrains Mono', monospace; font-size: 13px; color: #c9d1dc;
}}
.mtg-progress {{ flex: 1; display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 6px; }}
.mtg-progress div {{ height: 8px; border-radius: 4px; background: #2a3a52; }}
.mtg-progress div.on {{ background: {YELLOW}; }}
.mtg-stripe {{
  height: 8px; margin: 0 calc(-1 * var(--pad)) clamp(16px, 2.5vw, 32px);
  background: repeating-linear-gradient(135deg, {YELLOW} 0 14px, {NAVY} 14px 28px);
}}

/* Kleine Labels in Monospace */
.mtg-label {{
  font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 700;
  letter-spacing: 0.06em; color: #4b5563; text-transform: uppercase;
}}
.mtg-label.yellow {{ color: {YELLOW}; }}

/* Linke Spalte: Szenario auf dunklem Grund */
.st-key-scenario {{
  background: {PANEL}; color: #ffffff; border-radius: 16px; padding: clamp(18px, 2.4vw, 32px);
}}
.st-key-scenario p, .st-key-scenario span, .st-key-scenario div {{ color: #e5e9ef; }}
.mtg-bubble {{
  max-width: 85%; padding: 10px 14px; border-radius: 12px 12px 12px 2px;
  border: 1px solid #3b4d66; font-size: 14px; line-height: 1.45; white-space: pre-line;
}}
.mtg-bubble .ai {{
  font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 700;
  color: {NAVY} !important; background: #c9d1dc; padding: 1px 6px; border-radius: 4px; margin-right: 6px;
}}
.mtg-placeholder {{ border-style: dashed; color: #c9d1dc; }}
.mtg-code {{ border: 1px solid #3b4d66; border-radius: 12px; overflow: hidden; }}
.mtg-code-bar {{
  display: flex; align-items: center; gap: 8px; padding: 10px 14px;
  background: {NAVY}; border-bottom: 1px solid #3b4d66;
  font-family: 'JetBrains Mono', monospace; font-size: 13px;
}}
.mtg-code-bar i {{ width: 10px; height: 10px; border-radius: 5px; background: #3b4d66; display: inline-block; }}
.mtg-code-bar .right {{ margin-left: auto; font-size: 12px; color: #c9d1dc; }}
.mtg-code-body {{
  padding: 14px 16px; overflow-x: auto;
  font-family: 'JetBrains Mono', monospace; font-size: 13px; line-height: 1.7;
}}
.mtg-code-body div {{ display: flex; gap: 16px; min-height: 1.7em; }}
.mtg-code-body .n {{ flex: none; width: 22px; text-align: right; color: #8b9bb0 !important; }}
.mtg-code-body .t {{ white-space: pre; color: #e5e9ef; }}

/* Rechte Spalte: Tutor */
.mtg-step {{ display: flex; align-items: center; gap: 10px; }}
.mtg-step b {{
  font-family: 'JetBrains Mono', monospace; font-size: 13px; padding: 5px 10px;
  border-radius: 6px; background: {NAVY}; color: {YELLOW};
}}
.mtg-step i {{ width: 14px; height: 14px; border-radius: 4px; border: 2px solid #8b95a3; box-sizing: border-box; display: inline-block; }}
.mtg-step i.on {{ background: {NAVY}; border-color: {NAVY}; }}
.mtg-question {{ font-family: 'Space Grotesk', sans-serif; font-size: clamp(22px, 2.2vw, 30px); line-height: 1.15; font-weight: 700; margin: 8px 0 4px; }}
.mtg-history {{ padding: 12px 14px; border-radius: 12px; background: #f3f4f6; margin-bottom: 10px; font-size: 14px; line-height: 1.45; }}
.mtg-history .mtg-label {{ font-size: 12px; }}
.mtg-answer {{ font-weight: 600; }}
.mtg-test {{
  padding: 14px 16px; border: 2px dashed #b45309; background: #fff6dc; border-radius: 14px;
  color: #7c2d12; font-size: 14px; line-height: 1.5; margin-bottom: 12px;
}}
.mtg-dark {{ padding: 24px; border-radius: 16px; background: {NAVY}; color: #ffffff; margin-bottom: 16px; }}
.mtg-dark h2 {{ color: #ffffff !important; margin: 6px 0 10px; font-size: clamp(24px, 2.4vw, 32px); }}
.mtg-dark p {{ color: #e5e9ef; margin: 0 0 8px; font-size: 16px; line-height: 1.5; }}
.mtg-box {{ padding: 20px; border-radius: 16px; border: 2px solid {NAVY}; margin-bottom: 16px; }}
.mtg-box p {{ margin: 8px 0 0; color: #374151; line-height: 1.55; }}
.mtg-pattern {{ border-radius: 16px; background: {NAVY}; overflow: hidden; margin-bottom: 20px; }}
.mtg-pattern .stripe {{ height: 10px; background: repeating-linear-gradient(135deg, {YELLOW} 0 14px, {NAVY} 14px 28px); }}
.mtg-pattern .body {{ padding: 20px; }}
.mtg-pattern p {{ font-family: 'Space Grotesk', sans-serif; font-size: 21px; line-height: 1.3; font-weight: 700; color: #ffffff; margin: 10px 0 0; }}

/* Willkommen: Einstufung */
.st-key-welcome_left {{
  background: {NAVY}; color: #ffffff; border-radius: 18px; padding: clamp(24px, 4vw, 56px);
  min-height: calc(100vh - 2 * var(--pad)); margin-top: var(--pad); box-sizing: border-box;
  display: flex; flex-direction: column;
}}
.st-key-welcome_left p, .st-key-welcome_left span, .st-key-welcome_left div {{ color: #ffffff; }}
.mtg-biglogo {{ display: flex; align-items: center; gap: 10px; }}
.mtg-biglogo b {{ font-family: 'Space Grotesk', sans-serif; font-size: 30px; letter-spacing: -0.02em; }}
.mtg-biglogo span {{
  font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 26px;
  background: {YELLOW}; color: {NAVY} !important; padding: 4px 10px; border-radius: 8px;
}}
.mtg-minis {{ height: 8px; width: 260px; border-radius: 4px; margin: 14px 0 32px;
  background: repeating-linear-gradient(135deg, {YELLOW} 0 12px, {NAVY} 12px 24px); }}
.mtg-term {{ font-family: 'JetBrains Mono', monospace; font-size: 14px; line-height: 1.7; }}
.mtg-term span {{ color: #c9d1dc !important; }}
.mtg-term b {{ color: {YELLOW}; }}
.mtg-welcome-h1 {{
  font-family: 'Space Grotesk', sans-serif; font-size: clamp(30px, 3.6vw, 56px); line-height: 1.08; font-weight: 700;
  letter-spacing: -0.02em; margin: clamp(20px, 3vw, 36px) 0; max-width: 680px;
}}
.mtg-welcome-h1 em {{ font-style: normal; color: {YELLOW}; }}
.mtg-gapdia {{ display: flex; align-items: stretch; max-width: 680px; margin-bottom: 32px; }}
.mtg-gapdia .state {{ flex: 1; padding: 18px; border: 2px solid #ffffff; display: flex; flex-direction: column; gap: 4px; }}
.mtg-gapdia .state:first-child {{ border-radius: 12px 0 0 12px; }}
.mtg-gapdia .state:last-child {{ border-radius: 0 12px 12px 0; border-style: dashed; }}
.mtg-gapdia small {{ font-family: 'JetBrains Mono', monospace; font-size: 13px; color: #c9d1dc !important; }}
.mtg-gapdia strong {{ font-family: 'Space Grotesk', sans-serif; font-size: clamp(16px, 1.6vw, 22px); }}
.mtg-gapdia .gap {{
  flex: 0 0 clamp(72px, 8vw, 120px); display: flex; align-items: center; justify-content: center;
  background: repeating-linear-gradient(135deg, {YELLOW} 0 12px, {NAVY} 12px 24px);
}}
.mtg-gapdia .gap span {{
  font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 14px;
  background: {NAVY}; color: {YELLOW} !important; padding: 4px 8px; border-radius: 6px;
}}
.st-key-welcome_right {{
  min-height: calc(100vh - 2 * var(--pad)); margin-top: var(--pad);
  justify-content: center; padding: 0 clamp(0px, 2vw, 32px); max-width: 620px;
}}
.st-key-welcome_right h2 {{ font-size: clamp(26px, 2.6vw, 38px); line-height: 1.15; margin: 10px 0 8px; }}
.st-key-welcome_right .stRadio, .st-key-welcome_right .stRadio > div {{ width: 100%; }}
.st-key-welcome_right [role="radiogroup"] {{ gap: 12px; width: 100%; }}
.st-key-welcome_right [role="radiogroup"] > div {{
  width: 100%; box-sizing: border-box; padding: 14px 18px;
  border: 2px solid #c3c9d2; border-radius: 14px; background: #ffffff;
}}
.st-key-welcome_right [role="radiogroup"] > div:has(input:checked) {{
  border-color: {NAVY}; background: #fff6cc; box-shadow: 4px 4px 0 {NAVY};
}}
.st-key-welcome_right [data-testid="stRadioOption"] {{ width: 100%; margin: 0; }}
.st-key-welcome_right [data-testid="stRadioOption"] p {{ font-size: 17px; font-weight: 700; }}
.st-key-welcome_right [data-testid="stRadioCaption"] {{ padding-left: 28px; }}
@media (max-width: 900px) {{
  .st-key-welcome_left, .st-key-welcome_right {{ min-height: 0; }}
  .st-key-welcome_right {{ padding: 8px 0 32px; }}
}}
.mtg-level-chip {{
  display: inline-block; font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 700;
  padding: 3px 8px; border-radius: 6px; background: {YELLOW}; color: {NAVY} !important;
}}

/* Startseite */
.mtg-hero h1 {{ font-size: clamp(30px, 3.4vw, 48px) !important; line-height: 1.1; margin: 8px 0 12px; }}
.mtg-hero p {{ font-size: 17px; line-height: 1.55; color: #374151; max-width: 760px; }}
[class*="st-key-card_"] {{
  border: 2px solid {NAVY}; border-radius: 18px; padding: 24px; background: #ffffff;
}}
[class*="st-key-card_"] h3 {{ font-size: 22px; margin: 6px 0 8px; }}
[class*="st-key-card_"] p {{ color: #374151; font-size: 15px; line-height: 1.5; }}

/* Buttons und Eingabefeld */
.stButton button, .stFormSubmitButton button {{
  min-height: 48px; border-radius: 12px; border: 2px solid {NAVY};
  background: #ffffff; color: {NAVY}; font-weight: 700;
}}
.stButton button[kind="primary"], .stFormSubmitButton button[kind="primaryFormSubmit"],
button[data-testid="stBaseButton-primary"], button[data-testid="stBaseButton-primaryFormSubmit"] {{
  background: {YELLOW}; color: {NAVY}; border: 2px solid {NAVY}; box-shadow: 4px 4px 0 {NAVY};
}}
.stButton button:hover, .stFormSubmitButton button:hover {{ border-color: {NAVY}; color: {NAVY}; filter: brightness(0.97); }}
.stTextArea textarea {{ border: 2px solid {NAVY} !important; border-radius: 12px; font-size: 16px; }}
[data-testid="stForm"] {{ border: none; padding: 0; }}
</style>
"""

st.set_page_config(page_title="Mind the Gap · Security-Tutor", page_icon="🛡️", layout="wide")


@st.cache_resource
def get_exercises() -> dict[str, Exercise]:
    return load_all(REPO_ROOT / "exercises")


def esc(text: str) -> str:
    """Escaped Text für HTML. Ja, auch in der eigenen App: genau darum geht es."""
    return html.escape(text.strip())


# --- Sitzungszustand -------------------------------------------------------


EXERCISE_KEYS = ("exercise_id", "state", "history", "pending", "question", "grade_error")


def begin(exercise_id: str) -> None:
    exercise = get_exercises()[exercise_id]
    st.session_state.exercise_id = exercise_id
    st.session_state.state = start(with_hook=HOOK_ENABLED and exercise.hook is not None)
    st.session_state.history = []  # pro Antwort: Stufe, Frage, Antwort, Urteil
    st.session_state.pending = None  # Antwort, die noch bewertet werden muss
    st.session_state.question = None  # nur MODE=llm: GuardedQuestion der aktuellen Stufe
    st.session_state.grade_error = None  # nur MODE=llm: Meldung, wenn der Grader nicht antwortet


def back_to_selection() -> None:
    for key in EXERCISE_KEYS:
        st.session_state.pop(key, None)


def submit_answer() -> None:
    answer = st.session_state.get("answer_input", "").strip()
    if answer:
        st.session_state.pending = answer
        st.session_state.answer_input = ""
        if MODE == "llm":
            # Einmal pro Antwort loggen, auch wenn die Bewertung wiederholt werden muss.
            exercise = get_exercises()[st.session_state.exercise_id]
            session.log_answer(session_context(), exercise, st.session_state.state.stage, answer)


def judge(verdict: Verdict) -> None:
    """MODE=fixed: Die Testleitung bewertet per Knopf."""
    exercise = get_exercises()[st.session_state.exercise_id]
    record(exercise, verdict, exercise.stages[st.session_state.state.stage].hint)


def leave_hook() -> None:
    st.session_state.state = finish_hook(st.session_state.state)


# --- LLM-Modus -------------------------------------------------------------


def session_context() -> session.SessionContext:
    """Pseudonyme Sitzung: zufällige ID pro Browser-Sitzung, keine Namen."""
    if "session_id" not in st.session_state:
        st.session_state.session_id = turn_log.new_session_id()
    return session.SessionContext(
        session=st.session_state.session_id,
        hook=HOOK,
        prior_knowledge=st.session_state.level,
        log_dir=turn_log.LOG_DIR,
    )


def current_question(exercise: Exercise) -> str:
    """Frage der aktuellen Stufe. Im LLM-Modus einmal pro Stufe erzeugt und gemerkt."""
    state = st.session_state.state
    if MODE == "fixed":
        return exercise.stages[state.stage].hint

    cached = st.session_state.question
    if cached is None or cached.stage != state.stage:
        history = st.session_state.history
        previous = history[-1]["answer"] if history else None
        with st.spinner("Der Tutor formuliert die nächste Frage …"):
            cached = session.ask_question(session_context(), exercise, state.stage, get_exercises(), previous)
        st.session_state.question = cached
    return cached.text


def record(exercise: Exercise, verdict: Verdict, question: str) -> None:
    """Antwort mit Urteil in den Verlauf übernehmen und zur nächsten Stufe."""
    state = st.session_state.state
    st.session_state.history.append(
        {
            "stage": state.stage,
            "question": question,
            "answer": st.session_state.pending,
            "verdict": verdict,
            "level": st.session_state.level,
        }
    )
    st.session_state.state = on_verdict(state, verdict)
    st.session_state.pending = None


def grade_pending(exercise: Exercise, question: str) -> None:
    """Bewertet die offene Antwort mit LLM 2. Bei einem Fehler bleibt sie stehen."""
    with st.spinner("Deine Antwort wird ausgewertet …"):
        try:
            grading = session.grade_answer(
                session_context(), exercise, st.session_state.state, st.session_state.pending
            )
        except LLMError as exc:
            st.session_state.grade_error = str(exc)
            return
    record(exercise, grading.result.verdict, question)  # gleicher Übergang wie grading.state
    st.session_state.grade_error = None
    st.rerun()


def retry_grading() -> None:
    st.session_state.grade_error = None


# --- Bausteine -------------------------------------------------------------


def show_header(label: str, progress: int | None = None) -> None:
    """Navy-Header mit Logo, Label und optional 4 Fortschrittsbalken."""
    bars = ""
    if progress is not None:
        cells = "".join(f'<div class="{"on" if n <= progress else ""}"></div>' for n in range(1, LAST_STAGE + 2))
        bars = f'<div class="mtg-progress" aria-label="Fortschritt: Teil {progress} von {LAST_STAGE + 1}">{cells}</div>'
    st.markdown(
        f"""
        <div class="mtg-header">
          <div class="mtg-logo" role="img" aria-label="Mind the Gap"><b>mind the</b><span>gap_</span></div>
          <div class="mtg-lesson"><span>{esc(label)}</span>{bars}</div>
        </div>
        <div class="mtg-stripe" aria-hidden="true"></div>
        """,
        unsafe_allow_html=True,
    )


def show_code(code: str, filename: str) -> None:
    rows = "".join(
        f'<div><span class="n">{i}</span><span class="t">{html.escape(line)}</span></div>'
        for i, line in enumerate(code.rstrip("\n").split("\n"), start=1)
    )
    st.markdown(
        f"""
        <div class="mtg-code">
          <div class="mtg-code-bar"><i></i><i></i><i></i>
            <span style="margin-left:8px;color:#c9d1dc">{esc(filename)}</span>
            <span class="right">von der KI erzeugt</span></div>
          <div class="mtg-code-body">{rows}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# --- Ansichten -------------------------------------------------------------


def save_level() -> None:
    choice = st.session_state.get("level_choice")
    if choice is not None:
        st.session_state.level = PriorKnowledge(choice)


def change_level() -> None:
    st.session_state.pop("level", None)
    back_to_selection()


def show_welcome() -> None:
    """Pflichtschritt vor der ersten Übung: Selbsteinschätzung des Vorwissens."""
    left, right = st.columns(2, gap="large")
    with left:
        with st.container(key="welcome_left"):
            st.markdown(
                """
                <div class="mtg-biglogo" role="img" aria-label="Mind the Gap"><b>mind the</b><span>gap_</span></div>
                <div class="mtg-minis" aria-hidden="true"></div>
                <div class="mtg-term"><span><b>$</b> ai --generate frontend</span><br>
                <span>build passed · tests passed · ready to ship?</span></div>
                <div class="mtg-welcome-h1">Erkenne die Lücke zwischen Code, der <em>läuft</em>, und Code, der <em>sicher</em> ist.</div>
                <div class="mtg-gapdia" role="img" aria-label="Zwischen 'es läuft' und 'es ist sicher' liegt die Lücke">
                  <div class="state"><small>ZUSTAND A</small><strong>Es läuft</strong></div>
                  <div class="gap"><span>die Lücke</span></div>
                  <div class="state"><small>ZUSTAND B</small><strong>Es ist sicher</strong></div>
                </div>
                <p style="color:#c9d1dc;font-size:16px;line-height:1.5;max-width:520px">
                Kurze Übungen zu Entscheidungen, die die KI für dich trifft. Fragen statt Antworten.</p>
                """,
                unsafe_allow_html=True,
            )
    with right:
        with st.container(key="welcome_right"):
            st.markdown(
                '<span class="mtg-label">Einstufung · vor deiner ersten Übung</span>'
                "<h2>Wie viel weisst du über Web-Security?</h2>"
                '<p style="color:#4b5563;font-size:16px;line-height:1.5">Der Tutor passt die Formulierung seiner Fragen an dich an. '
                "Du kannst das später jederzeit ändern.</p>",
                unsafe_allow_html=True,
            )
            options = list(PriorKnowledge)
            current = st.session_state.get("level")
            st.radio(
                "Vorwissen",
                options=[level.value for level in options],
                index=options.index(current) if current in options else None,
                format_func=lambda value: f"{LEVELS[PriorKnowledge(value)].number}  {LEVELS[PriorKnowledge(value)].title}",
                captions=[LEVELS[level].description for level in options],
                key="level_choice",
                label_visibility="collapsed",
            )
            chosen = st.session_state.get("level_choice") is not None
            st.button("Weiter →", type="primary", on_click=save_level, disabled=not chosen)
            if not chosen:
                st.caption("Wähl zuerst eine Stufe aus. Erst danach kannst du eine Übung starten.")


def show_selection(exercises: dict[str, Exercise]) -> None:
    level = st.session_state.level
    show_header(f"SECURITY-TUTOR · VORWISSEN: {LEVELS[level].title.upper()}")
    _, right = st.columns([5, 1])
    right.button("Einstufung ändern", on_click=change_level, key="change_level", use_container_width=True)
    st.markdown(
        f"""
        <div class="mtg-hero">
          <span class="mtg-label">{esc(MODE_LABELS[MODE])}</span>
          <h1>Findest du die unsichere Entscheidung?</h1>
          <p>Jede Übung zeigt einen Kursauftrag, den Chat mit der KI und den Code, den die KI
          geliefert hat. Der Tutor nennt die Lücke nicht. Er stellt dir bis zu drei Fragen,
          die dich hinführen.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    columns = st.columns(min(len(exercises), 3), gap="medium")
    for index, (exercise_id, exercise) in enumerate(exercises.items()):
        with columns[index % len(columns)]:
            with st.container(key=f"card_{exercise_id}"):
                st.markdown(
                    f'<span class="mtg-label">Übung {index + 1:02d}</span>'
                    f"<h3>{esc(exercise.title)}</h3>"
                    f"<p>{esc(exercise.scenario.requirement)}</p>",
                    unsafe_allow_html=True,
                )
                st.button(
                    "Übung starten →",
                    key=f"start_{exercise_id}",
                    type="primary",
                    on_click=begin,
                    args=(exercise_id,),
                )


def show_scenario(exercise: Exercise) -> None:
    with st.container(key="scenario"):
        st.markdown(
            f'<span class="mtg-label yellow">Szenario · {esc(exercise.title)}</span>'
            f'<p style="font-size:16px;line-height:1.5;margin:6px 0 18px">{esc(exercise.scenario.requirement)}</p>',
            unsafe_allow_html=True,
        )
        chat = exercise.scenario.ai_chat
        if chat.lstrip().upper().startswith("TODO"):
            bubble = '<div class="mtg-bubble mtg-placeholder">Platzhalter: Der Auszug aus dem echten Testchat fehlt in der Übungsdatei noch.</div>'
        else:
            bubble = f'<div class="mtg-bubble"><span class="ai">KI</span>{esc(chat)}</div>'
        st.markdown(bubble + '<div style="height:18px"></div>', unsafe_allow_html=True)
        code = exercise.scenario.code
        show_code(code, "index.html" if code.lstrip().startswith("<") else "app.js")


def show_step_badge(stage: int) -> None:
    boxes = "".join(f'<i class="{"on" if n <= stage else ""}"></i>' for n in range(1, LAST_STAGE + 1))
    st.markdown(
        f'<div class="mtg-step"><b>STUFE {stage} VON {LAST_STAGE}</b><span aria-hidden="true" style="display:flex;gap:6px">{boxes}</span></div>',
        unsafe_allow_html=True,
    )


def show_history() -> None:
    for turn in st.session_state.history:
        st.markdown(
            f"""
            <div class="mtg-history">
              <span class="mtg-label">Stufe {turn['stage']} · {esc(VERDICT_LABELS[turn['verdict']])}</span><br>
              {esc(turn['question'])}<br>
              <span class="mtg-answer">„{esc(turn['answer'])}“</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def show_tutor(exercise: Exercise) -> None:
    state = st.session_state.state

    top_left, top_right = st.columns([3, 2])
    top_left.markdown('<span class="mtg-label">Dein Tutor · fragt, verrät nichts</span>', unsafe_allow_html=True)
    top_right.button("Übung verlassen", on_click=back_to_selection, key="leave", use_container_width=True)

    if state.in_hook:
        st.markdown(f'<div class="mtg-dark"><p>{esc(exercise.hook or "")}</p></div>', unsafe_allow_html=True)
        st.button("Weiter zur Übung →", type="primary", on_click=leave_hook)
        return

    if not state.done:
        show_step_badge(state.stage)
    show_history()

    if not state.done:
        question = current_question(exercise)
        st.markdown(f'<div class="mtg-question">{esc(question)}</div>', unsafe_allow_html=True)
        cached = st.session_state.get("question")
        if MODE == "llm" and cached is not None and cached.fallback == "llm_error":
            st.caption("Der Tutor ist gerade nicht erreichbar. Diese Frage stammt direkt von der Fachperson.")

        if st.session_state.pending is None:
            with st.form("answer_form", clear_on_submit=False):
                st.text_area(
                    "Deine Antwort",
                    key="answer_input",
                    height=120,
                    placeholder="Beschreib in eigenen Worten, was dir auffällt …",
                )
                st.form_submit_button("Antwort senden", type="primary", on_click=submit_answer)
            st.caption("Die Lösung kommt erst nach Stufe 3.")
        elif MODE == "llm":
            st.markdown(
                f'<div class="mtg-history"><span class="mtg-answer">„{esc(st.session_state.pending)}“</span></div>',
                unsafe_allow_html=True,
            )
            if st.session_state.grade_error is None:
                grade_pending(exercise, question)  # bei Erfolg neuer Durchlauf, sonst ist grade_error gesetzt
            if st.session_state.grade_error is not None:
                st.error(
                    "Deine Antwort konnte gerade nicht ausgewertet werden. Sie ist gespeichert, "
                    "du musst sie nicht neu schreiben. Versuch es in einem Moment noch einmal."
                )
                with st.expander("Technische Details"):
                    st.code(st.session_state.grade_error, language=None)
                st.button("Erneut auswerten", type="primary", on_click=retry_grading, key="retry_grading")
        else:
            st.markdown(
                f'<div class="mtg-history"><span class="mtg-answer">„{esc(st.session_state.pending)}“</span></div>'
                '<div class="mtg-test"><strong>Nur im Test:</strong> Die Testleitung beurteilt die Antwort. '
                "Später übernimmt das LLM 2.</div>",
                unsafe_allow_html=True,
            )
            columns = st.columns(len(VERDICT_BUTTONS))
            for column, (verdict, label) in zip(columns, VERDICT_BUTTONS):
                column.button(
                    label,
                    key=f"verdict_{verdict}",
                    type="primary" if verdict is Verdict.RECOGNIZED else "secondary",
                    on_click=judge,
                    args=(verdict,),
                    use_container_width=True,
                )
        return

    show_close(exercise, state.outcome, state.stage)


def show_close(exercise: Exercise, outcome: Outcome | None, stage: int) -> None:
    if outcome is Outcome.RECOGNIZED:
        label, title = f"Lücke gefunden auf Stufe {stage}", "Du hast die Lücke gefunden!"
    else:
        label, title = f"Auflösung nach Stufe {LAST_STAGE}", "Das war die unsichere Entscheidung."
    st.markdown(
        f"""
        <div class="mtg-dark">
          <span class="mtg-label yellow">{esc(label)}</span>
          <h2>{esc(title)}</h2>
          <p>{esc(exercise.answer_key.issue)}</p>
          <p style="color:#c9d1dc"><strong style="color:#ffffff">Folge:</strong> {esc(exercise.answer_key.consequence)}</p>
        </div>
        <div class="mtg-box">
          <span class="mtg-label">So behebst du es</span>
          <p>{esc(exercise.close.fix)}</p>
        </div>
        <div class="mtg-pattern">
          <div class="stripe" aria-hidden="true"></div>
          <div class="body">
            <span class="mtg-label yellow">Prüfmuster zum Mitnehmen</span>
            <p>{esc(exercise.close.pruefmuster)}</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    left, right = st.columns(2)
    left.button("Übung wiederholen", type="primary", on_click=begin, args=(exercise.id,), use_container_width=True)
    right.button("Andere Übung wählen", on_click=back_to_selection, use_container_width=True, key="other")


def main() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    exercises = get_exercises()

    if not exercises:
        show_header("SECURITY-TUTOR · PROTOTYP")
        st.error("Keine Übungen im Ordner exercises/ gefunden.")
        return

    if MODE not in MODES:
        show_header("SECURITY-TUTOR · PROTOTYP")
        st.error(f"Unbekannter Modus MODE={MODE!r}. Erlaubt sind: {', '.join(MODES)}.")
        return

    if MODE == "llm":
        try:
            get_config()
        except ConfigError as exc:
            show_header("SECURITY-TUTOR · PROTOTYP")
            st.error(
                "Der Tutor kann nicht starten, weil die LLM-Konfiguration fehlt oder ungültig ist.\n\n"
                f"{exc}\n\n"
                "Ohne LLM lässt sich die App mit `MODE=fixed` starten (fixe Fragen, Bewertung per Knopf)."
            )
            return

    # Ohne Einstufung keine Übung: zuerst das Vorwissen erfassen.
    if "level" not in st.session_state:
        show_welcome()
        return

    if "exercise_id" not in st.session_state:
        show_selection(exercises)
        return

    exercise = exercises[st.session_state.exercise_id]
    state = st.session_state.state
    progress = LAST_STAGE + 1 if state.done else max(state.stage, 1)
    number = list(exercises).index(exercise.id) + 1
    show_header(f"ÜBUNG {number:02d} · {exercise.title.upper()}", progress)

    left, right = st.columns([11, 9], gap="large")
    with left:
        show_scenario(exercise)
    with right:
        show_tutor(exercise)


main()
