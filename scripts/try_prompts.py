"""Zeigt die fertig eingesetzten Prompts für Tutor und Grader, ohne LLM-Aufruf.

Praktisch, um Vorlagen und Few-Shot-Auswahl zu prüfen, bevor etwas an den
Proxy geht. Braucht weder VPN noch API-Key.

    python scripts/try_prompts.py --exercise api-key-frontend --stage 2 --level new
    python scripts/try_prompts.py --exercise strapi-auth-false --role grader --grader-version 1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import grader, tutor  # noqa: E402
from core.exercises import load_all  # noqa: E402
from core.prior_knowledge import PriorKnowledge  # noqa: E402
from core.prompts import hash_text, load_prompt  # noqa: E402

EXERCISES_DIR = Path(__file__).resolve().parent.parent / "exercises"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--exercise", required=True, help="id der Übung")
    parser.add_argument("--role", choices=["tutor", "grader", "both"], default="both")
    parser.add_argument("--stage", type=int, default=1, choices=[1, 2, 3])
    parser.add_argument("--level", default="basics", choices=[p.value for p in PriorKnowledge])
    parser.add_argument("--answer", default=None, help="letzte Antwort (Tutor) bzw. zu bewertende Antwort (Grader)")
    parser.add_argument("--tutor-version", type=int, default=1)
    parser.add_argument("--grader-version", type=int, default=2)
    args = parser.parse_args()

    exercises = load_all(EXERCISES_DIR)
    if args.exercise not in exercises:
        print(f"Unbekannte Übung {args.exercise!r}. Vorhanden: {', '.join(sorted(exercises))}", file=sys.stderr)
        return 2
    exercise = exercises[args.exercise]

    if args.role in ("tutor", "both"):
        template = load_prompt("tutor", args.tutor_version)
        messages, n_examples = tutor.build_messages(
            template, exercise, args.stage, PriorKnowledge(args.level), exercises, args.answer
        )
        _show(f"{template.version} | Stufe {args.stage} | {args.level} | n_examples={n_examples}", messages)

    if args.role in ("grader", "both"):
        template = load_prompt("grader", args.grader_version)
        messages = grader.build_messages(template, exercise, args.answer or "(Antwort der Person)")
        _show(f"{template.version} | decoy={exercise.decoy}", messages)
    return 0


def _show(title: str, messages: list[dict[str, str]]) -> None:
    print(f"{'=' * 78}\n{title}\nprompt_hash={hash_text(messages[0]['content'])}\n{'=' * 78}")
    for m in messages:
        print(f"--- {m['role']} ---\n{m['content']}\n")


if __name__ == "__main__":
    sys.exit(main())
