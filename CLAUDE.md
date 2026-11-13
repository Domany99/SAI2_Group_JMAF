# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Prototype of a security tutor (BFH course SAI2). The tutor leads students to an insecure decision in AI-generated web code through stepwise questions, without naming it. `development.md` is the specification: architecture, exercise format, stage logic, leak guard, logging, evaluation and the "Order of work". **Do not edit `development.md`.** If you find a gap or contradiction in it, list it for the user instead of deciding it yourself. Decisions that fill gaps go in the "Entscheide" section of `README.md`.

Status: only step 1 of the "Order of work" is done (exercise format, validation, 2 draft exercises). `app/`, `eval/`, `prompts/`, `logs/` hold only `.gitkeep`. The modules `tutor.py`, `grader.py`, `stages.py`, `llm.py`, `logging.py` listed in the spec do not exist yet.

## Commands

```bash
python -m venv .venv && .venv\Scripts\activate   # Windows; POSIX: source .venv/bin/activate
pip install -r requirements.txt
pytest                                            # all tests
pytest tests/test_exercises.py::test_duplicate_id # single test
pytest -k hint                                    # by name
```

Run from the repo root: tests import `core` and `tests.conftest` as packages. Dependencies in `requirements.txt` are pinned to exact versions (a grading criterion in the course). Keep them pinned and do not add dependencies without asking. Guard and stage logic need full coverage (spec). `coverage` is not a dependency, so install it only temporarily if you need to measure.

## Architecture

The core guarantee is that **the tutor LLM can never reveal the answer**. Several pieces work together for this:

- `core/models.py` holds the Pydantic models for one exercise (`Exercise`, `Stage`, `AnswerKey`, …). Cross-field rules live in `Exercise._check_stages`: stages 1–3 present, `forbidden` non-empty for stages 1–2, and no hint containing its own forbidden terms. `Exercise.tutor_context(stage)` is the only thing the tutor may receive. It returns only `goal` and `hint` and deliberately excludes `answer_key`, `close` and `forbidden`. Tests assert this, so keep it that way.
- `core/guard.py` provides `normalize()` (lowercase, ä/ö/ü/ß → ae/oe/ue/ss, punctuation → space) and `find_forbidden()` (matches whole normalized words). Exercise validation already uses them. The future leak guard must reuse the same functions so that hints and tutor output are checked identically.
- `core/exercises.py` has `load_exercise()` and `load_all(path)`. It turns Pydantic errors into `ExerciseValidationError` with messages of the form `<file>: <field>: <rule>`. Model validators raise `RuleViolations` (a `ValueError` carrying a list of `Violation(field, rule)`). The loader reads them from `ctx["error"]` so that each violation keeps its own field path. File-level rules (id equals the filename stem, ids unique across files) live in the loader, not the model.

Planned flow (spec): stage logic in plain code decides stage progression, not the LLM. The tutor phrases the question from `tutor_context`. The guard checks it, regenerates once, then falls back to the expert `hint`. The grader returns `recognized | partial | not`, and when unsure it should answer `partial`.

## Exercises (`exercises/*.yaml`)

- The filename stem is the `id` (`^[a-z0-9]+(-[a-z0-9]+)*$`). Unknown keys are errors (`extra="forbid"`). `decoy` must be an explicit bool. `answer_key.accepted` needs at least 2 entries. `hook` (stage 0) is optional.
- Student-facing text (`scenario`, `hint`, `fix`, `pruefmuster`) is German with Swiss spelling (ss, never ß).
- Hints are drafts marked `# TODO Expert:in`. The final hints come from the domain expert (gold standard). `ai_chat` placeholders say `TODO: Auszug aus dem echten Testchat einfügen`.
- Code samples are short (≤ 20 lines), realistic and runnable.
- `tests/test_exercises.py::test_real_exercises_load_without_errors` lists the expected exercise ids. Update it when adding an exercise.

## Claude instructions
- In this repo do not commit by yourself!
- Always check the requirements
