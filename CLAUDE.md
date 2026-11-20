# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Prototype of a security tutor (BFH course SAI2). The tutor leads students to an insecure decision in AI-generated web code through stepwise questions, without naming it. `development.md` is the specification: architecture, exercise format, stage logic, leak guard, logging, evaluation and the "Order of work". **Do not edit `development.md`.** If you find a gap or contradiction in it, list it for the user instead of deciding it yourself. Decisions that fill gaps go in the "Entscheide" section of `README.md`.

Status: steps 1 and 2 of the "Order of work" are largely done (exercise format and validation, stage logic, Streamlit UI with fixed questions and a human judge). Step 3 has begun: the LLM wrapper, the turn logger, the v1 prompts with their loader and the tutor exist, but grader and leak-guard flow do not, and the UI does not log yet. Open work is tracked as GitHub issues at https://github.com/Domany99/SAI2_Group_JMAF/issues (the `I-xx` issues follow the spec's order of work). Check them instead of relying on a status list here.

## Commands

```bash
python -m venv .venv && .venv\Scripts\activate   # Windows; POSIX: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                              # then set LLM_API_KEY (personal key, never commit)
streamlit run app/main.py                         # UI; HOOK=incident shows stage 0
python scripts/smoke_llm.py [--models a,b]        # manual check against the real proxy, not part of pytest
pytest                                            # all tests (no network, LLM calls are mocked)
pytest tests/test_exercises.py::test_duplicate_id # single test
pytest -k hint                                    # by name
```

Run from the repo root: tests import `core` and `tests.conftest` as packages. Dependencies in `requirements.txt` must be pinned to exact versions (a grading criterion in the course; `streamlit` is still unpinned, see the issues). Do not add dependencies without asking. Guard and stage logic need full coverage (spec). `coverage` is not a dependency, so install it only temporarily if you need to measure.

The LLM backend is the BFH LiteLLM proxy (OpenAI-compatible, `LLM_BASE_URL`). Outside the BFH network it needs VPN. Default models: `TUTOR_MODEL=qwen3.8-27b`, `GRADER_MODEL=gpt-oss:120b`; tutor defaults `TUTOR_TEMPERATURE=0.7`, `TUTOR_PROMPT_VERSION=1`.

## Architecture

The core guarantee is that **the tutor LLM can never reveal the answer**. Several pieces work together for this:

- `core/models.py` holds the Pydantic models for one exercise (`Exercise`, `Stage`, `AnswerKey`, `Misconception`, `FixChoice`, …). Cross-field rules live in `Exercise._check_stages` (stages 1–3 present, `forbidden` non-empty for stages 1–2, no hint containing its own forbidden terms) and `Exercise._check_extras` (unique misconception ids, `fix_choices` rules). `Exercise.tutor_context(stage)` is the only thing the tutor may receive. It returns only `goal` and `hint` and deliberately excludes `answer_key`, `close`, `misconceptions` and `forbidden`. Tests assert this, so keep it that way.
- `core/guard.py` provides `normalize()` (lowercase, ä/ö/ü/ß → ae/oe/ue/ss, punctuation → space) and `find_forbidden()` (matches whole normalized words). Exercise validation already uses them. The leak guard must reuse the same functions so that hints and tutor output are checked identically.
- `core/exercises.py` has `load_exercise()` and `load_all(path)`. It turns Pydantic errors into `ExerciseValidationError` with messages of the form `<file>: <field>: <rule>`. Model validators raise `RuleViolations` (a `ValueError` carrying a list of `Violation(field, rule)`). The loader reads them from `ctx["error"]` so that each violation keeps its own field path. File-level rules (id equals the filename stem, ids unique across files) live in the loader, not the model.
- `core/stages.py` is the stage state machine in plain code, no LLM. `StageState` is immutable (stage 0–3 plus `outcome`); `start()`, `finish_hook()` and `on_verdict()` return new states. `recognized` ends the exercise; `partial`/`not` advance a stage; after stage 3 the outcome is `revealed`. Invalid transitions raise `StageError`. `Verdict` uses the same values as the grader output; invalid grader output must be mapped to `partial` before it reaches `on_verdict()`.
- `core/models.py` also holds `Verdict` (re-exported by `core/stages.py`) and `Turn`, one JSONL log line. `Turn` enforces per-role rules in `_check_role`: roles `tutor | student | grader | hint`; LLM fields (`model`, `prompt_version` = `<role>_v<n>`, `temperature`) only for tutor/grader; `verdict` only for grader; `guard_hit` only for tutor; `ts` must be timezone-aware; session id `s-` + 8 hex. No field for names or emails, and `extra="forbid"` keeps it that way.
- `core/logging.py` appends a `Turn` to `logs/<YYYY-MM-DD>.jsonl` (date of `ts` in its own zone, thread lock for Streamlit) and provides `new_session_id()`, `now()` and `read_turns()`. It is only importable as `core.logging`, so a plain `import logging` elsewhere still gets the stdlib.
- `core/prompts.py` loads `prompts/<role>_v<n>.md` via `load_prompt(role, n)`; `PromptTemplate.render(values)` fills `{{name}}` placeholders strictly (missing or extra values raise `PromptError`, no recursive substitution). A template is the system prompt; student answers always go in a separate user message. Placeholder contracts per version are in `prompts/README.md` and asserted in `tests/test_prompts.py`. **Never edit a prompt version listed in `prompts/frozen.txt`** (a hash test enforces it); create `<role>_v<n+1>.md` instead. Grader few-shot examples must not come from `eval/data/` or `exercises/`.
- `core/tutor.py` (LLM 1): `ask(exercise, stage, prior_knowledge, exercises, previous_answer=…, prompt_version=…, model=…, temperature=…)` returns a `TutorQuestion` (text plus log metadata). It renders the tutor prompt from `tutor_context(stage)`, the prior-knowledge level and `few_shot_examples()` (same-stage hints of *other* exercises, minus those containing the current stage's forbidden terms); the previous answer goes only into the user message. Empty model output raises `TutorError` (a `LLMError`). It does not run the leak guard. Tests mock `core.tutor.chat`.
- `core/config.py` loads `.env` into a frozen `LLMConfig` (API key as `SecretStr`; errors name only the variable, never the value).
- `core/llm.py` is the only place the provider appears. `chat(messages, model, temperature, json_mode)` returns an `LLMResult` (text without `<think>` blocks, tokens, latency, `warnings`). It has its own retry/backoff (SDK retries off), a JSON-mode fallback on HTTP 400, and translates provider exceptions into `LLMAuthError` / `LLMRequestError` / `LLMUnavailableError` with the key redacted. Never log or print the key.
- `core/prior_knowledge.py` holds the students' self-assessment (`new | basics | experienced`). In step 2 it is only shown; from step 3 it goes into the tutor context and the logs.
- `app/main.py` is the Streamlit UI (design "Mind the Gap", theme in `.streamlit/config.toml`, CSS inline). It currently shows the expert hints as fixed questions, and a test lead judges answers with buttons that map to `Verdict`. In step 3, LLM 1 replaces the fixed questions and LLM 2 the buttons. The stage logic stays the same.

Still to build (spec, step 3): `core/grader.py`, the guard flow (check, regenerate once, then fall back to the expert `hint`, log every hit). The grader returns `recognized | partial | not`, and when unsure it should answer `partial`. `eval/` (step 4) is still empty.

## Exercises (`exercises/*.yaml`)

- The filename stem is the `id` (`^[a-z0-9]+(-[a-z0-9]+)*$`). Unknown keys are errors (`extra="forbid"`). `decoy` must be an explicit bool. `answer_key.accepted` needs at least 2 entries. Optional: `hook` (stage 0), `misconceptions` (`id`, `belief`, `reaction`) and `close.fix_choices` (≥ 2 options, at least one `correct`).
- Student-facing text (`scenario`, `hint`, `reaction`, `fix`, `pruefmuster`, `fix_choices`) is German with Swiss spelling (ss, never ß).
- Hints are drafts marked `# TODO Expert:in`. The final hints come from the domain expert (gold standard). `ai_chat` placeholders say `TODO: Auszug aus dem echten Testchat einfügen`.
- Code samples are short (≤ 20 lines), realistic and runnable.
- `tests/test_exercises.py::test_real_exercises_load_without_errors` lists the expected exercise ids. Update it when adding an exercise.

## Claude instructions
- In this repo do not commit by yourself!
- Always check the requirements
