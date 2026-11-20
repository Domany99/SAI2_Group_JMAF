"""Probelauf Tutor (LLM 1) gegen den echten BFH-Proxy (nicht Teil von pytest).

Fragt pro Übung und Einstufung eine Frage ab und prüft sie mit dem Leak Guard
(nur Anzeige, keine Regenerierung). Braucht VPN ausserhalb des BFH-Netzes und
eine ausgefüllte .env. Keys stehen nie im Skript.

    python scripts/try_tutor.py
    python scripts/try_tutor.py --exercises xss-projektsuche --stage 2 --answer "Der Begriff kommt aus dem Link."
    python scripts/try_tutor.py --guarded --exercises strapi-auth-false --levels new
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import leak_guard, tutor  # noqa: E402
from core.config import ConfigError  # noqa: E402
from core.exercises import load_all  # noqa: E402
from core.guard import find_forbidden  # noqa: E402
from core.llm import LLMError  # noqa: E402
from core.prior_knowledge import PriorKnowledge  # noqa: E402

EXERCISES_DIR = Path(__file__).resolve().parent.parent / "exercises"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--exercises", help="Kommagetrennte ids. Default: alle.")
    parser.add_argument("--stage", type=int, default=1, choices=[1, 2, 3])
    parser.add_argument("--levels", default="new,basics,experienced")
    parser.add_argument("--answer", default=None, help="letzte Antwort der Person (ab Stufe 2)")
    parser.add_argument("--prompt-version", type=int, default=None)
    parser.add_argument("--model", default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--guarded", action="store_true", help="mit Leak-Guard-Ablauf (Regenerierung, Fallback)")
    args = parser.parse_args()
    if args.guarded:
        return _guarded(args)

    exercises = load_all(EXERCISES_DIR)
    ids = [i.strip() for i in args.exercises.split(",")] if args.exercises else sorted(exercises)
    levels = [PriorKnowledge(lv.strip()) for lv in args.levels.split(",")]

    leaks = 0
    for exercise_id in ids:
        exercise = exercises[exercise_id]
        forbidden = exercise.stages[args.stage].forbidden
        for level in levels:
            try:
                q = tutor.ask(
                    exercise, args.stage, level, exercises,
                    previous_answer=args.answer, prompt_version=args.prompt_version,
                    model=args.model, temperature=args.temperature,
                )  # fmt: skip
            except ConfigError as exc:
                print(f"Konfigurationsfehler: {exc}", file=sys.stderr)
                return 2
            except LLMError as exc:
                print(f"--- {exercise_id} / {level.value}: Fehler {type(exc).__name__}: {exc}\n")
                continue
            hits = find_forbidden(q.text, forbidden)
            leaks += bool(hits)
            print(
                f"--- {exercise_id} | Stufe {args.stage} | {level.value} | {q.model} t={q.temperature} "
                f"{q.prompt_version} | {q.latency_ms} ms | cache_hit={q.cache_hit} | n_examples={q.n_examples} "
                f"| guard={hits or 'ok'}"
            )
            for w in q.warnings:
                print(f"    Warnung: {w}")
            print(f"{q.text}\n")
    print(f"Guard-Treffer: {leaks}")
    return 0


def _guarded(args: argparse.Namespace) -> int:
    """Wie oben, aber über core.leak_guard: zeigt alle Versuche und was die Person sähe."""
    exercises = load_all(EXERCISES_DIR)
    ids = [i.strip() for i in args.exercises.split(",")] if args.exercises else sorted(exercises)
    levels = [PriorKnowledge(lv.strip()) for lv in args.levels.split(",")]
    counts = {"tutor": 0, "guard": 0, "llm_error": 0}
    for exercise_id in ids:
        for level in levels:
            try:
                g = leak_guard.ask_guarded(
                    exercises[exercise_id], args.stage, level, exercises,
                    previous_answer=args.answer, prompt_version=args.prompt_version,
                    model=args.model, temperature=args.temperature,
                )  # fmt: skip
            except ConfigError as exc:
                print(f"Konfigurationsfehler: {exc}", file=sys.stderr)
                return 2
            counts[g.fallback or "tutor"] += 1
            print(f"--- {exercise_id} | Stufe {args.stage} | {level.value} | Ergebnis: {g.fallback or 'Tutor-Frage'}")
            for number, a in enumerate(g.attempts, start=1):
                q = a.question
                print(f"  Versuch {number} ({q.strict_version or q.prompt_version}, {q.latency_ms} ms, "
                      f"cache_hit={q.cache_hit}): guard={list(a.hits) or 'ok'}\n    {q.text}")  # fmt: skip
            if g.llm_error:
                print(f"  LLM-Fehler: {g.llm_error}")
            print(f"  Angezeigt: {g.text}\n")
    print(f"Tutor-Frage: {counts['tutor']}, Fallback guard: {counts['guard']}, Fallback llm_error: {counts['llm_error']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
