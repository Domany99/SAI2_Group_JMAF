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

import copy
import html
import os
import random
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
  padding: 0 var(--pad) 64px !important; max-width: none !important; position: relative;
}}
h1, h2, h3 {{ font-family: 'Space Grotesk', system-ui, sans-serif !important; color: {NAVY}; letter-spacing: -0.01em; }}

/* Header und Warnstreifen */
.mtg-header {{
  display: flex; flex-wrap: wrap; align-items: center; gap: 24px;
  margin: 0 calc(-1 * var(--pad)); padding: 14px var(--pad); background: {NAVY}; color: #ffffff;
}}
.mtg-logo {{ display: flex; align-items: center; gap: 6px; }}
/* In der Übung führt ein Klick aufs Logo zur Übersicht. Der Streamlit-Knopf liegt
   unsichtbar über dem Logo im Header, sein Text bleibt für Screenreader lesbar. */
.st-key-logo_home {{ position: absolute; top: 24px; left: calc(var(--pad) - 6px); z-index: 20; width: auto !important; }}
.st-key-logo_home button {{
  width: 146px; min-height: 42px !important; height: 42px; padding: 0;
  background: transparent !important; border: 2px solid transparent !important; box-shadow: none !important;
  color: transparent !important; border-radius: 8px; cursor: pointer;
}}
.st-key-logo_home button:hover {{ border-color: {YELLOW} !important; }}
.st-key-logo_home button:focus-visible {{ outline: 3px solid {YELLOW}; outline-offset: 2px; }}
.st-key-logo_home button p {{ color: transparent !important; }}
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
/* Streamlit macht Scrollbalken global durchsichtig. Lange Codezeilen (z. B.
   beim Decoy und bei XSS) müssen aber sichtbar scrollbar sein. */
.mtg-code-body {{ scrollbar-width: auto; scrollbar-color: {YELLOW} {NAVY}; }}
.mtg-code-body::-webkit-scrollbar {{ height: 12px; }}
.mtg-code-body::-webkit-scrollbar-track {{ background: {NAVY}; }}
.mtg-code-body::-webkit-scrollbar-thumb {{ background: {YELLOW}; border-radius: 6px; }}

/* Rechte Spalte: Tutor */
.mtg-step {{ display: flex; align-items: center; gap: 10px; }}
.mtg-step b {{
  font-family: 'JetBrains Mono', monospace; font-size: 13px; padding: 5px 10px;
  border-radius: 6px; background: {NAVY}; color: {YELLOW};
}}
.mtg-step i {{ width: 14px; height: 14px; border-radius: 4px; border: 2px solid #8b95a3; box-sizing: border-box; display: inline-block; }}
.mtg-step i.on {{ background: {NAVY}; border-color: {NAVY}; }}
/* Tutor-Frage: Die LLM-Fragen sind oft mehrere Sätze lang, deshalb Fliesstext statt
   Überschrift (Inter, mittlere Grösse, ruhige Zeilenhöhe, begrenzte Zeilenlänge). */
.mtg-question {{
  font-family: Inter, system-ui, sans-serif; font-size: clamp(16px, 1.25vw, 18px); line-height: 1.6;
  font-weight: 500; color: {NAVY}; max-width: 68ch; margin: 10px 0 12px;
}}
/* Fragen der Beheben-Phase: kleiner als die Tutor-Frage, damit sie nicht wie eine Überschrift wirken. */
.mtg-question.small {{ font-size: clamp(15px, 1.15vw, 17px); line-height: 1.5; font-weight: 600; margin: 4px 0 8px; }}
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
/* Übungskarten: bei schmalem Fenster umbrechen statt zusammenquetschen. */
[data-testid="stHorizontalBlock"]:has([class*="st-key-card_"]) {{ flex-wrap: wrap; row-gap: 16px; }}
[data-testid="stHorizontalBlock"]:has([class*="st-key-card_"]) > [data-testid="stColumn"] {{
  flex: 1 1 300px !important; min-width: min(300px, 100%) !important;
}}
[class*="st-key-card_"] {{
  border: 2px solid {NAVY}; border-radius: 18px; padding: 24px; background: #ffffff;
}}
.mtg-card-top {{ display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; }}
.mtg-status {{
  font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 700; letter-spacing: 0.04em;
  padding: 4px 9px; border-radius: 6px; white-space: nowrap;
}}
.mtg-status.open {{ border: 2px solid #c3c9d2; color: #4b5563; }}
.mtg-status.started {{ background: {YELLOW}; color: {NAVY}; border: 2px solid {NAVY}; }}
.mtg-status.done {{ background: {NAVY}; color: {YELLOW}; border: 2px solid {NAVY}; }}
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


EXERCISE_KEYS = (
    "exercise_id", "state", "history", "pending", "question", "grade_error",
    "fix_step", "fix_order", "fix_own", "fix_pick", "fix_reason", "fix_error",
)  # fmt: skip

# Beheben-Phase nach dem Abschluss der Stufen (README, Entscheid "Fix-Auswahl"):
# zuerst ein eigener Vorschlag, die Auswahl nur auf Wunsch, mit Begründung.
FIX_ASK, FIX_CHOOSE, FIX_DONE = "ask", "choose", "done"
FIX_VERDICT_LABELS = {"correct": "Passt", "partial": "Teilweise", "wrong": "Passt nicht"}


def begin(exercise_id: str) -> None:
    exercise = get_exercises()[exercise_id]
    st.session_state.exercise_id = exercise_id
    st.session_state.state = start(with_hook=HOOK_ENABLED and exercise.hook is not None)
    st.session_state.history = []  # pro Antwort: Stufe, Frage, Antwort, Urteil
    st.session_state.pending = None  # Antwort, die noch bewertet werden muss
    st.session_state.question = None  # nur MODE=llm: GuardedQuestion der aktuellen Stufe
    st.session_state.grade_error = None  # nur MODE=llm: Meldung, wenn der Grader nicht antwortet
    st.session_state.fix_step = FIX_ASK
    # Reihenfolge der Fix-Optionen einmal pro Start mischen: In der Datei steht
    # die richtige Option oft zuerst, und Reruns sollen sie nicht neu mischen.
    st.session_state.fix_order = random.sample(range(len(exercise.close.fix_choices)), len(exercise.close.fix_choices))
    st.session_state.fix_own = None  # eigener Vorschlag der Person
    st.session_state.fix_pick = None  # Index in close.fix_choices
    st.session_state.fix_reason = None  # Begründung der Wahl
    st.session_state.fix_error = None


# Status pro Übung (Issue: angefangen, erledigt, offen). Beim Verlassen einer Übung
# wird ihr Stand gemerkt, ein Klick auf die Karte macht dort weiter. Der Stand lebt
# nur in der Browser-Sitzung, wie die Einstufung (development.md: keine Persistenz
# über die JSONL-Logs hinaus).
STATUS_OPEN, STATUS_STARTED, STATUS_DONE = "open", "started", "done"


def saved_runs() -> dict[str, dict]:
    if "saved_runs" not in st.session_state:
        st.session_state.saved_runs = {}
    return st.session_state.saved_runs


def save_current_run() -> None:
    """Merkt den Stand der offenen Übung, damit man später weitermachen kann."""
    exercise_id = st.session_state.get("exercise_id")
    if exercise_id is None:
        return
    saved_runs()[exercise_id] = {key: copy.deepcopy(st.session_state.get(key)) for key in EXERCISE_KEYS}


def run_status(exercise_id: str) -> str:
    run = saved_runs().get(exercise_id)
    if run is None:
        return STATUS_OPEN
    if run["state"].done and run["fix_step"] == FIX_DONE:
        return STATUS_DONE
    return STATUS_STARTED


def run_position(exercise_id: str) -> str:
    """Wo eine angefangene Übung steht, für die Karte."""
    state = saved_runs()[exercise_id]["state"]
    if state.done:
        return "Beheben"
    if state.in_hook:
        return "Einstieg"
    return f"Stufe {state.stage} von {LAST_STAGE}"


def resume(exercise_id: str) -> None:
    """Macht bei einer angefangenen oder erledigten Übung weiter, sonst Neustart."""
    run = saved_runs().get(exercise_id)
    if run is None:
        begin(exercise_id)
        return
    for key, value in run.items():
        st.session_state[key] = copy.deepcopy(value)


def back_to_selection() -> None:
    save_current_run()
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


def submit_fix() -> None:
    """Eigener Fix-Vorschlag. Leer zählt nicht."""
    own = st.session_state.get("fix_input", "").strip()
    if not own:
        st.session_state.fix_error = "Schreib zuerst deinen Vorschlag, oder lass dir Optionen zeigen."
        return
    st.session_state.fix_own = own
    st.session_state.fix_error = None
    st.session_state.fix_step = FIX_DONE


def ask_for_fix_choices() -> None:
    """Die Person findet keinen eigenen Fix. Ohne Optionen in der Übung direkt zur Lösung."""
    exercise = get_exercises()[st.session_state.exercise_id]
    st.session_state.fix_error = None
    st.session_state.fix_step = FIX_CHOOSE if exercise.close.fix_choices else FIX_DONE


def submit_fix_choice() -> None:
    """Wahl aus den Optionen, nur mit Begründung."""
    pick = st.session_state.get("fix_choice")
    reason = st.session_state.get("fix_reason_input", "").strip()
    if pick is None or not reason:
        st.session_state.fix_error = "Wähl eine Option und begründe deine Wahl in einem Satz."
        return
    st.session_state.fix_pick = pick
    st.session_state.fix_reason = reason
    st.session_state.fix_error = None
    st.session_state.fix_step = FIX_DONE


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
        with st.spinner("Der Tutor formuliert die nächste Frage … Das kann bis zu zwei Minuten dauern."):
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
    with st.spinner("Deine Antwort wird ausgewertet … Das kann einen Moment dauern."):
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


def status_chip(exercise_id: str, status: str) -> str:
    if status == STATUS_DONE:
        return '<span class="mtg-status done">✓ Erledigt</span>'
    if status == STATUS_STARTED:
        return f'<span class="mtg-status started">Angefangen · {esc(run_position(exercise_id))}</span>'
    return '<span class="mtg-status open">Offen</span>'


def show_selection(exercises: dict[str, Exercise]) -> None:
    level = st.session_state.level
    show_header(f"SECURITY-TUTOR · VORWISSEN: {LEVELS[level].title.upper()}")
    _, right = st.columns([5, 1])
    right.button("Einstufung ändern", on_click=change_level, key="change_level", use_container_width=True)
    st.markdown(
        f"""
        <div class="mtg-hero">
          <span class="mtg-label">{esc(MODE_LABELS[MODE])}</span>
          <h1>Hält die Entscheidung der KI?</h1>
          <p>Jede Übung zeigt einen Kursauftrag, den Chat mit der KI und den Code, den die KI
          geliefert hat. Der Tutor sagt dir nicht, ob und wo eine Lücke steckt. Er stellt dir
          bis zu drei Fragen, die dich beim Prüfen leiten.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    columns = st.columns(min(len(exercises), 3), gap="medium")
    for index, (exercise_id, exercise) in enumerate(exercises.items()):
        with columns[index % len(columns)]:
            with st.container(key=f"card_{exercise_id}"):
                status = run_status(exercise_id)
                st.markdown(
                    f'<div class="mtg-card-top"><span class="mtg-label">Übung {index + 1:02d}</span>'
                    f"{status_chip(exercise_id, status)}</div>"
                    f"<h3>{esc(exercise.title)}</h3>"
                    f"<p>{esc(exercise.scenario.requirement)}</p>",
                    unsafe_allow_html=True,
                )
                label = {
                    STATUS_OPEN: "Übung starten →",
                    STATUS_STARTED: "Weitermachen →",
                    STATUS_DONE: "Ergebnis ansehen",
                }[status]
                st.button(
                    label,
                    key=f"start_{exercise_id}",
                    type="secondary" if status == STATUS_DONE else "primary",
                    on_click=resume,
                    args=(exercise_id,),
                )
                if status == STATUS_DONE:
                    st.button("Neu starten", key=f"restart_{exercise_id}", on_click=begin, args=(exercise_id,))


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
    # Ohne Urteil: Der Tutor darf Antworten nicht als richtig oder falsch werten,
    # also zeigt auch der Verlauf kein "Teilweise" oder "Nicht erkannt".
    for turn in st.session_state.history:
        st.markdown(
            f"""
            <div class="mtg-history">
              <span class="mtg-label">Stufe {turn['stage']}</span><br>
              {esc(turn['question'])}<br>
              <span class="mtg-answer">„{esc(turn['answer'])}“</span>
            </div>
            """,
            unsafe_allow_html=True,
        )


def show_tutor(exercise: Exercise) -> None:
    state = st.session_state.state

    top_left, top_right = st.columns([3, 2])
    top_left.markdown('<span class="mtg-label">Dein Tutor · Fragen statt Antworten</span>', unsafe_allow_html=True)
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
    """Abschluss: Auflösung, dann Beheben-Phase, erst danach Fix und Prüfmuster."""
    show_resolution(exercise, outcome, stage)
    step = st.session_state.get("fix_step", FIX_DONE)
    if step == FIX_ASK:
        show_fix_ask(exercise)
    elif step == FIX_CHOOSE:
        show_fix_choose(exercise)
    else:
        show_fix_result(exercise)
        show_fix_and_pattern(exercise)
        show_reflection(exercise)
        left, right = st.columns(2)
        left.button("Übung wiederholen", type="primary", on_click=begin, args=(exercise.id,), use_container_width=True)
        right.button("Andere Übung wählen", on_click=back_to_selection, use_container_width=True, key="other")


def show_resolution(exercise: Exercise, outcome: Outcome | None, stage: int) -> None:
    if exercise.decoy:
        if outcome is Outcome.RECOGNIZED:
            label, title = f"Richtig beurteilt auf Stufe {stage}", "Richtig beurteilt: Der Code ist in Ordnung."
        else:
            label, title = f"Auflösung nach Stufe {LAST_STAGE}", "Der Code ist in Ordnung."
    elif outcome is Outcome.RECOGNIZED:
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
        """,
        unsafe_allow_html=True,
    )


def show_fix_ask(exercise: Exercise) -> None:
    if exercise.decoy:
        prompt = "Würdest du am Code trotzdem etwas ändern? Beschreib es in eigenen Worten, oder schreib, warum nicht."
    else:
        prompt = "Wie würdest du das beheben? Beschreib deinen Fix in eigenen Worten."
    st.markdown(f'<div class="mtg-question small">{esc(prompt)}</div>', unsafe_allow_html=True)
    with st.form("fix_form", clear_on_submit=False):
        st.text_area("Dein Vorschlag", key="fix_input", height=110, placeholder="Was würdest du ändern, und warum?")
        st.form_submit_button("Vorschlag senden", type="primary", on_click=submit_fix)
    if st.session_state.get("fix_error"):
        st.caption(st.session_state.fix_error)
    label = "Ich komme nicht weiter, zeig mir Optionen" if exercise.close.fix_choices else "Ich komme nicht weiter"
    st.button(label, key="fix_help", on_click=ask_for_fix_choices)


def show_fix_choose(exercise: Exercise) -> None:
    choices = exercise.close.fix_choices
    st.markdown(
        '<div class="mtg-question small">Welche Option würdest du wählen? Begründe deine Wahl in einem Satz.</div>',
        unsafe_allow_html=True,
    )
    with st.form("fix_choice_form", clear_on_submit=False):
        st.radio(
            "Optionen",
            options=st.session_state.fix_order,
            index=None,
            format_func=lambda i: choices[i].text,
            key="fix_choice",
            label_visibility="collapsed",
        )
        st.text_area("Deine Begründung", key="fix_reason_input", height=90, placeholder="Ich wähle das, weil …")
        st.form_submit_button("Wahl senden", type="primary", on_click=submit_fix_choice)
    if st.session_state.get("fix_error"):
        st.caption(st.session_state.fix_error)


def show_fix_result(exercise: Exercise) -> None:
    """Was die Person in der Beheben-Phase gesagt oder gewählt hat."""
    if st.session_state.get("fix_own"):
        st.markdown(
            '<div class="mtg-history"><span class="mtg-label">Dein Vorschlag</span><br>'
            f'<span class="mtg-answer">„{esc(st.session_state.fix_own)}“</span><br>'
            "Vergleich ihn mit dem Fix unten.</div>",
            unsafe_allow_html=True,
        )
        return
    pick = st.session_state.get("fix_pick")
    if pick is None:
        return
    choices = exercise.close.fix_choices
    chosen = choices[pick]
    st.markdown(
        '<div class="mtg-history"><span class="mtg-label">Deine Wahl</span><br>'
        f"{esc(chosen.text)}<br>"
        f'<span class="mtg-answer">„{esc(st.session_state.fix_reason or "")}“</span><br>'
        f"<strong>{esc(FIX_VERDICT_LABELS[chosen.verdict])}:</strong> {esc(chosen.reason)}</div>",
        unsafe_allow_html=True,
    )
    with st.expander("Alle Optionen mit Begründung"):
        for i in st.session_state.fix_order:
            option = choices[i]
            st.markdown(
                f"<p><strong>{esc(FIX_VERDICT_LABELS[option.verdict])}:</strong> {esc(option.text)}<br>"
                f"{esc(option.reason)}</p>",
                unsafe_allow_html=True,
            )


def show_reflection(exercise: Exercise) -> None:
    """Zum Weiterdenken: persönlicher Bezug und Fragen zum eigenen Code (ohne Eingabe)."""
    reflection = exercise.close.reflection
    if reflection is None:
        return
    parts = []
    if reflection.personal:
        parts.append(f"<p><em>{esc(reflection.personal)}</em></p>")
    if reflection.questions:
        items = "".join(f"<li>{esc(q)}</li>" for q in reflection.questions)
        parts.append(f"<ul>{items}</ul>")
    st.markdown(
        '<div class="mtg-box"><span class="mtg-label">Zum Weiterdenken</span>' + "".join(parts) + "</div>",
        unsafe_allow_html=True,
    )


def show_fix_and_pattern(exercise: Exercise) -> None:
    heading = "Was zu tun ist" if exercise.decoy else "So behebst du es"
    st.markdown(
        f"""
        <div class="mtg-box">
          <span class="mtg-label">{esc(heading)}</span>
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
    st.button("Zur Übungsübersicht", key="logo_home", on_click=back_to_selection)

    left, right = st.columns([11, 9], gap="large")
    with left:
        show_scenario(exercise)
    with right:
        show_tutor(exercise)


main()
