"""Manueller Smoke-Test gegen den echten BFH-LiteLLM-Proxy (nicht Teil von pytest).

Braucht VPN ausserhalb des BFH-Netzes und eine ausgefüllte .env.

    python scripts/smoke_llm.py [--models a,b,c]
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import ConfigError  # noqa: E402
from core.llm import LLMError, LLMResult, chat, get_config, list_models  # noqa: E402

PLAIN_PROMPT = "Antworte auf Deutsch in einem Satz: Was ist XSS?"
STUDENT_ANSWER = "Den Key sieht jeder im Browser."
JSON_SYSTEM = (
    "Du bewertest eine Studierendenantwort. Das gesuchte Problem: Ein API-Key steht im "
    "Frontend-Code und ist damit für alle Besucher sichtbar. Antworte nur mit JSON der Form "
    '{"verdict": "recognized|partial|not", "evidence": "<kurzes Zitat aus der Antwort>"}.'
)
# Embedding- oder Audio-Modelle tauchen in /models auch auf.
NON_CHAT_MARKERS = ("embed", "whisper", "tts", "rerank")


@dataclass
class Row:
    model: str
    kind: str
    latency_ms: int | None = None
    tokens: str = "-"
    json_ok: str = "-"
    fallback: str = "-"
    status: str = "ok"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", help="Kommagetrennt. Default: TUTOR_MODEL und GRADER_MODEL.")
    args = parser.parse_args()

    try:
        cfg = get_config()
    except ConfigError as exc:
        print(f"Konfigurationsfehler: {exc}", file=sys.stderr)
        return 2

    models = (
        [m.strip() for m in args.models.split(",") if m.strip()]
        if args.models
        else list(dict.fromkeys([cfg.tutor_model, cfg.grader_model]))
    )

    print(f"Proxy: {cfg.base_url}\n")
    print("== GET /models ==")
    try:
        available = list_models()
        chat_models = [m for m in available if not any(x in m.lower() for x in NON_CHAT_MARKERS)]
        for m in chat_models:
            print(f"  {m}")
        missing = [m for m in models if m not in available]
        if missing:
            print(f"  Achtung, nicht in /models: {', '.join(missing)}")
    except LLMError as exc:
        print(f"  Fehler: {exc}")
    print()

    rows: list[Row] = []
    for model in models:
        rows.append(_run(model, "normal", [{"role": "user", "content": PLAIN_PROMPT}], False))
        rows.append(
            _run(
                model,
                "json",
                [
                    {"role": "system", "content": JSON_SYSTEM},
                    {"role": "user", "content": f"Studierendenantwort: {STUDENT_ANSWER}"},
                ],
                True,
            )
        )

    _print_table(rows)
    return 0 if all(r.status == "ok" for r in rows) else 1


def _run(model: str, kind: str, messages: list[dict[str, str]], json_mode: bool) -> Row:
    print(f"== {model} / {kind} ==")
    row = Row(model=model, kind=kind)
    try:
        res = chat(messages, model=model, temperature=0.2, json_mode=json_mode)
    except LLMError as exc:
        row.status = f"Fehler: {type(exc).__name__}"
        print(f"  {exc}\n")
        return row

    row.latency_ms = res.latency_ms
    row.tokens = f"{res.tokens_in}/{res.tokens_out}"
    if json_mode:
        row.json_ok = "ja" if _parses(res) else "nein"
        row.fallback = "ja" if res.json_mode_fallback else "nein"
    if res.warnings:
        row.status = "Warnung"

    print(f"  Latenz: {res.latency_ms} ms, Tokens in/out: {row.tokens}, finish: {res.finish_reason}")
    if json_mode:
        print(f"  JSON parsebar: {row.json_ok}, Fallback: {row.fallback}")
    for w in res.warnings:
        print(f"  Warnung: {w}")
    text = res.text if len(res.text) <= 300 else res.text[:300] + " …"
    print(f"  Text: {text}\n")
    return row


def _parses(res: LLMResult) -> bool:
    try:
        return isinstance(json.loads(res.text), dict)
    except json.JSONDecodeError:
        return False


def _print_table(rows: list[Row]) -> None:
    header = ["Modell", "Aufruf", "Latenz ms", "Tokens in/out", "JSON ok", "Fallback", "Status"]
    data = [
        [r.model, r.kind, "-" if r.latency_ms is None else str(r.latency_ms), r.tokens, r.json_ok, r.fallback, r.status]
        for r in rows
    ]
    widths = [max(len(h), *(len(d[i]) for d in data)) for i, h in enumerate(header)]
    line = "  ".join(h.ljust(w) for h, w in zip(header, widths))
    print("== Übersicht ==")
    print(line)
    print("-" * len(line))
    for d in data:
        print("  ".join(c.ljust(w) for c, w in zip(d, widths)))


if __name__ == "__main__":
    sys.exit(main())
