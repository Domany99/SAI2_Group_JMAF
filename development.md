# Development: SAI2 Security Tutor Prototype

Prototype for the SAI2 project (BFH, "Innovation through Generative AI"). The tutor leads students to an insecure decision in AI-generated web code through stepwise questions, without naming it. The decisions we cover are things like an API key in the frontend because the course required it, a public `create` permission in Strapi, or unchecked data in `innerHTML`.

Scope is Step 6: **curated exercises only**. The rule scanner and "own code" mode are out of scope and stay listed as an extension.

## Principles

1. **The answer key is fixed before any LLM runs.** The LLM never searches for issues itself.
2. **Stage logic lives in code.** The LLM never decides when to reveal the issue.
3. **The leak guard enforces this.** Every tutor question is checked against forbidden terms before it is shown.
4. **The grader errs towards "not yet".** A false `recognized` ends the dialogue too early. If the grader is unsure, the result is `partial`.
5. **Everything is logged and versioned.** Every turn records the prompt version and model, so Step 3 variants can be compared.

## Architecture

```
Exercise file ──► LLM 1: Tutor ──► Leak guard ──► Student
                      ▲                              │
                      │ not yet: next stage          ▼
                 Stage logic ◄──── verdict ──── LLM 2: Grader
                      │
                      └──► recognized, or after stage 3 ──► Close: fix + Prüfmuster

All turns ──► logs/*.jsonl
```

| Component | Type | Responsibility |
|---|---|---|
| Exercise file | YAML, written by team and experts | Scenario, answer key, stage hints, forbidden terms, fix, Prüfmuster |
| LLM 1: Tutor | LLM | Phrases the question for the current stage, matched to prior knowledge, without naming the issue |
| Leak guard | Code | Blocks tutor output containing forbidden terms. Regenerates once, then falls back to the expert hint |
| LLM 2: Grader | LLM, structured output | Compares the answer to the key and returns `recognized`, `partial` or `not` |
| Stage logic | Code, state machine | Decides next stage or close. The issue is named only after stage 3 |
| Logger | Code | Writes every turn as one JSONL line |

## Repository layout

```
exercises/          one YAML file per exercise
prompts/            versioned prompt files (tutor_v1.md, grader_v1.md, …)
core/
  models.py         dataclasses for Exercise, Turn, Verdict
  exercises.py      load and validate YAML
  tutor.py          LLM 1
  grader.py         LLM 2
  guard.py          leak check
  stages.py         state machine
  llm.py            thin wrapper around the provider API (model, temperature, retries)
  logging.py        JSONL writer
app/
  main.py           Streamlit UI
eval/
  data/             grader_labels.csv, tutor_reference.csv (pseudonymized)
  run_grid.py       prompt × model × temperature runs → results/*.csv
  metrics.py        false-recognized rate, accuracy, leak rate
logs/               runtime logs (gitignored)
tests/
.env.example        API key and model names, never committed with real values
```

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # streamlit, pyyaml, pydantic, the provider SDK, pytest
cp .env.example .env               # add API key and model names
streamlit run app/main.py
```

Run the tests with `pytest`. Guard and stage logic need full coverage, because they carry the guarantees.

## Exercise format

```yaml
id: api-key-frontend
title: API key in the frontend
version: 1
decoy: false                     # true = the AI decision is actually fine

scenario:
  requirement: >
    Course brief: call the weather API directly from the page.
  ai_chat: |
    (excerpt from the real test chat)
  code: |
    const API_KEY = "…";
    fetch(`https://api.example.com/weather?key=${API_KEY}`)

answer_key:
  issue: The key is shipped to every visitor's browser.
  consequence: Anyone can read and misuse the key at the owner's cost.
  accepted: ["key visible in browser", "anyone can copy the key", "devtools/source shows key"]

stages:
  1:
    goal: Open question about who can see the code
    hint: "Who besides you can see what this page sends?"
    forbidden: ["API-Key", "API key", "Schlüssel", "secret", "leak"]
  2:
    goal: Narrow to the request
    hint: "Look at the network tab when the page loads. What do you notice?"
    forbidden: ["API-Key", "API key", "secret"]
  3:
    goal: Concrete misuse scenario
    hint: "What could someone do with everything they see in that request?"
    forbidden: []

close:
  fix: Move the call to a server route, keep the key in an environment variable.
  pruefmuster: "Before shipping: what in this code ends up in the browser, and may everyone see it?"
```

Rules:

- Write 5–6 exercises from our tests (API key, Strapi public `create`, `innerHTML` with Strapi data), plus 1–2 decoys.
- Stage hints come from the experts. They are the gold standard for LLM 1 and the fallback for the leak guard.
- `exercises.py` validates every file on load: all stages present, forbidden terms set for stages 1–2, `decoy` set.

## Stage logic

```
state: stage ∈ {0, 1, 2, 3}, done ∈ {false, true}

stage 0: optional hook (real incident), then go to stage 1
on verdict:
  recognized            → close
  partial | not, stage<3 → stage + 1, ask again
  partial | not, stage=3 → reveal issue, close
```

- Stage 0 holds the real-incident hook and is behind a feature flag for the A/B test (`HOOK=incident|none`).
- The stage counter and transitions are plain code with unit tests. No prompt can change them.

## Leak guard

1. Normalize the tutor output (lowercase, strip punctuation, umlauts ↔ ae/oe/ue).
2. Check it against `forbidden` for the current stage.
3. On a hit, regenerate once with a stricter instruction.
4. On a second hit, show the expert `hint` for that stage.
5. Log every hit (`guard_hit: true`). This is the leak rate for Step 4.

## Grader output

```json
{
  "verdict": "recognized | partial | not",
  "evidence": "short quote from the student answer",
  "misconception": "optional, what the student got wrong"
}
```

- Validate with Pydantic. Treat invalid JSON as `partial` and log it.
- Run the grader at low temperature.
- For decoys, `recognized` means the student correctly judged the code as safe.

## Prompts

- Store each prompt as a file in `prompts/`, named `<role>_v<n>.md`. Never edit a version that has been used in an eval run. Create a new version instead.
- **Tutor:** role, Hattie criteria (feed up / back / forward), stage goal, instruction to stay neutral about whether the code is safe, few-shot examples from the expert hints of *other* exercises.
- **Grader:** rubric, answer key, accepted answers, labeled examples, output schema.

## Logging

One line per turn in `logs/<date>.jsonl`:

```json
{"session": "s-7f3a", "exercise": "api-key-frontend", "stage": 2,
 "role": "tutor", "prompt_version": "tutor_v3", "model": "…", "temperature": 0.7,
 "text": "…", "guard_hit": false, "verdict": null, "ts": "2026-11-20T10:14:03+01:00"}
```

Session IDs are random. No names, no email addresses.

## Evaluation (Step 3/4)

| Dataset | Source | Main metric |
|---|---|---|
| Grader | Interview answers, labeled independently by two team members, agreement checked | False-`recognized` rate, then accuracy |
| Tutor | Model question vs. expert hint per exercise and stage | Hattie rubric (human rating), leak rate |
| Step 3 grid | Prompt × model × temperature | One CSV per run in `eval/results/` |

`run_grid.py` runs every combination over both datasets and writes one row per item, so results can be compared in R or Python.

## Order of work

1. Write 2 exercises completely with one expert.
2. Build the UI and stage logic with **fixed questions, no LLM**. Test the flow with 2–3 students.
3. Add LLM 1 and LLM 2, the leak guard and logging.
4. Expand to 5–6 exercises and run the Step 3/4 evaluation.
5. Run a pilot with real students. Measure issues found on a new exercise, before and after.

## Data protection

- Student answers go to an external API. Pseudonymize sessions and never send names.
- Check BFH rules for external AI services before the pilot.
- `logs/` and `eval/data/` are gitignored. Share labeled data only in pseudonymized form.

## Out of scope (extension)

- Rule scanner (e.g. Semgrep or ESLint rules) for "own code" mode
- Prior-knowledge detection beyond a self-assessment at the start
- Multi-user accounts, persistence beyond JSONL logs
