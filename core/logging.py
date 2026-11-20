"""JSONL-Logger: eine Zeile pro Turn in `logs/<YYYY-MM-DD>.jsonl` (Abschnitt "Logging").

Das Datum im Dateinamen ist das Datum von `turn.ts` in dessen eigener
Zeitzone. Ein Turn um 23:59 landet also in der Datei dieses Tages, der
nächste um 00:00 in einer neuen Datei.

Datenschutz: Die Session-ID ist zufällig (`secrets`) und enthält nichts über
die Person. `Turn` hat kein Feld für Namen oder E-Mail-Adressen. `logs/` ist
gitignored.

Hinweis zum Namen: Das Modul heisst wie die Standardbibliothek, ist aber nur
als `core.logging` erreichbar. Ein `import logging` in anderen Modulen lädt
weiterhin die Standardbibliothek.
"""

from __future__ import annotations

import secrets
import threading
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.models import Turn

# Unter Windows bringt Python keine Zeitzonen-Daten mit, dafür ist tzdata
# in requirements.txt gepinnt.
TIMEZONE = ZoneInfo("Europe/Zurich")
REPO_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = REPO_ROOT / "logs"
SESSION_ID_HEX_BYTES = 4  # 8 Hex-Zeichen

# Streamlit bedient mehrere Sessions in Threads desselben Prozesses. Das Lock
# verhindert, dass sich zwei Zeilen beim gleichzeitigen Anhängen vermischen.
_lock = threading.Lock()


def new_session_id() -> str:
    """Zufällige, pseudonyme Session-ID, z. B. 's-7f3a91c2'."""
    return "s-" + secrets.token_hex(SESSION_ID_HEX_BYTES)


def now() -> datetime:
    """Aktuelle Zeit in Schweizer Zeit, auf Sekunden gerundet (wie in der Spezifikation).

    Fest Europe/Zurich statt der Server-Zone: Streamlit Community Cloud läuft
    in UTC, sonst lägen Zeitstempel und Tagesgrenze der Logdateien daneben.
    """
    return datetime.now(TIMEZONE).replace(microsecond=0)


def log_path(ts: datetime, log_dir: Path = LOG_DIR) -> Path:
    """Pfad der Logdatei für den Tag von `ts`."""
    return log_dir / f"{ts.date().isoformat()}.jsonl"


def write_turn(turn: Turn, log_dir: Path = LOG_DIR) -> Path:
    """Hängt `turn` als eine JSON-Zeile an die Tagesdatei an und gibt deren Pfad zurück.

    Legt `log_dir` bei Bedarf an. Bestehende Zeilen werden nie überschrieben.
    """
    path = log_path(turn.ts, log_dir)
    line = turn.model_dump_json() + "\n"
    with _lock:
        log_dir.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(line)
    return path


def read_turns(path: Path) -> list[Turn]:
    """Liest eine Logdatei und validiert jede Zeile wieder als `Turn` (für Tests und Eval)."""
    with path.open(encoding="utf-8") as f:
        return [Turn.model_validate_json(line) for line in f if line.strip()]
