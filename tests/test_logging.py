from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from core import logging as turn_log
from core.models import SESSION_ID_PATTERN, Turn, Verdict
from core.prior_knowledge import PriorKnowledge

CET = timezone(timedelta(hours=1))
TS = datetime(2026, 11, 20, 10, 14, 3, tzinfo=CET)

# Reihenfolge und Namen wie im Abschnitt "Logging" der Spezifikation, plus prior_knowledge.
EXPECTED_KEYS = [
    "session", "exercise", "stage", "role", "prompt_version", "model", "temperature",
    "text", "guard_hit", "verdict", "ts",
    # Ergänzungen (Entscheide im README)
    "prior_knowledge", "hook", "prompt_hash", "n_examples", "cache_hit", "error",
]  # fmt: skip
HASH = "a" * 64


def tutor_turn(**overrides: Any) -> Turn:
    data: dict[str, Any] = {
        "session": "s-7f3a91c2",
        "exercise": "api-key-frontend",
        "stage": 2,
        "role": "tutor",
        "prompt_version": "tutor_v3",
        "model": "qwen3.8-27b",
        "temperature": 0.7,
        "text": "Wer kann diese Zeile im Browser sehen?",
        "ts": TS,
        "prior_knowledge": PriorKnowledge.BASICS,
        "hook": "none",
        "prompt_hash": HASH,
        "n_examples": 2,
        "cache_hit": False,
    }
    data.update(overrides)
    return Turn(**data)


def student_turn(**overrides: Any) -> Turn:
    data: dict[str, Any] = {
        "role": "student",
        "prompt_version": None,
        "model": None,
        "temperature": None,
        "prompt_hash": None,
        "n_examples": None,
        "cache_hit": None,
        "text": "Alle, die die Seite öffnen.",
    }
    data.update(overrides)
    return tutor_turn(**data)


def grader_turn(**overrides: Any) -> Turn:
    data: dict[str, Any] = {
        "role": "grader",
        "prompt_version": "grader_v1",
        "model": "gpt-oss:120b",
        "temperature": 0.0,
        "n_examples": None,
        "text": "Alle, die die Seite öffnen.",
        "verdict": Verdict.PARTIAL,
    }
    data.update(overrides)
    return tutor_turn(**data)


# --- Format -----------------------------------------------------------------


def test_line_has_spec_fields_in_order(tmp_path: Path) -> None:
    path = turn_log.write_turn(tutor_turn(), tmp_path)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert list(record) == EXPECTED_KEYS
    assert record == {
        "session": "s-7f3a91c2",
        "exercise": "api-key-frontend",
        "stage": 2,
        "role": "tutor",
        "prompt_version": "tutor_v3",
        "model": "qwen3.8-27b",
        "temperature": 0.7,
        "text": "Wer kann diese Zeile im Browser sehen?",
        "guard_hit": False,
        "verdict": None,
        "ts": "2026-11-20T10:14:03+01:00",
        "prior_knowledge": "basics",
        "hook": "none",
        "prompt_hash": HASH,
        "n_examples": 2,
        "cache_hit": False,
        "error": None,
    }


def test_grader_turn_logs_verdict_as_string(tmp_path: Path) -> None:
    path = turn_log.write_turn(grader_turn(), tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["verdict"] == "partial"


def test_umlauts_and_newlines_stay_on_one_line(tmp_path: Path) -> None:
    turn = student_turn(text="Zeile 1\nZeile 2 mit Ümläut")
    path = turn_log.write_turn(turn, tmp_path)

    content = path.read_text(encoding="utf-8")
    assert content.count("\n") == 1
    assert "Ümläut" in content  # lesbar, nicht als \u-Escape
    assert turn_log.read_turns(path) == [turn]


def test_roundtrip_keeps_every_field(tmp_path: Path) -> None:
    turns = [tutor_turn(), student_turn(), grader_turn(), tutor_turn(guard_hit=True)]
    for turn in turns:
        path = turn_log.write_turn(turn, tmp_path)
    assert turn_log.read_turns(path) == turns


def test_read_skips_blank_lines(tmp_path: Path) -> None:
    path = turn_log.write_turn(tutor_turn(), tmp_path)
    with path.open("a", encoding="utf-8") as f:
        f.write("\n")
    assert len(turn_log.read_turns(path)) == 1


# --- Anhängen und Ordner ----------------------------------------------------


def test_appends_instead_of_overwriting(tmp_path: Path) -> None:
    first = turn_log.write_turn(tutor_turn(), tmp_path)
    second = turn_log.write_turn(student_turn(), tmp_path)

    assert first == second
    assert [t.role for t in turn_log.read_turns(first)] == ["tutor", "student"]


def test_creates_missing_log_dir(tmp_path: Path) -> None:
    log_dir = tmp_path / "nested" / "logs"
    path = turn_log.write_turn(tutor_turn(), log_dir)
    assert path == log_dir / "2026-11-20.jsonl"
    assert path.is_file()


def test_concurrent_writes_do_not_mix_lines(tmp_path: Path) -> None:
    per_thread = 50

    def worker(n: int) -> None:
        for i in range(per_thread):
            turn_log.write_turn(student_turn(text=f"t{n}-{i} " + "x" * 2000), tmp_path)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    turns = turn_log.read_turns(tmp_path / "2026-11-20.jsonl")
    assert len(turns) == 4 * per_thread


# --- Datumswechsel ----------------------------------------------------------


def test_date_change_starts_new_file(tmp_path: Path) -> None:
    before = turn_log.write_turn(tutor_turn(ts=datetime(2026, 11, 20, 23, 59, 59, tzinfo=CET)), tmp_path)
    after = turn_log.write_turn(student_turn(ts=datetime(2026, 11, 21, 0, 0, 0, tzinfo=CET)), tmp_path)

    assert before.name == "2026-11-20.jsonl"
    assert after.name == "2026-11-21.jsonl"
    assert len(turn_log.read_turns(before)) == 1
    assert len(turn_log.read_turns(after)) == 1


def test_file_date_follows_timezone_of_ts(tmp_path: Path) -> None:
    # 23:30 UTC ist in der Schweiz schon der nächste Tag; massgebend ist die Zone von ts.
    utc = datetime(2026, 11, 20, 23, 30, tzinfo=timezone.utc)
    assert turn_log.log_path(utc, tmp_path).name == "2026-11-20.jsonl"
    assert turn_log.log_path(utc.astimezone(CET), tmp_path).name == "2026-11-21.jsonl"


# --- Session-ID und Zeitstempel ---------------------------------------------


def test_session_id_format() -> None:
    assert re.fullmatch(SESSION_ID_PATTERN, turn_log.new_session_id())


def test_session_ids_are_random() -> None:
    ids = {turn_log.new_session_id() for _ in range(1000)}
    assert len(ids) == 1000


def test_now_is_timezone_aware_iso_without_microseconds() -> None:
    ts = turn_log.now()
    assert ts.tzinfo is not None
    assert ts.microsecond == 0
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[+-]\d\d:\d\d", ts.isoformat())
    # Und es lässt sich direkt in einen Turn übernehmen.
    assert tutor_turn(ts=ts).ts == ts


def test_now_uses_swiss_time_regardless_of_server_zone(monkeypatch: pytest.MonkeyPatch) -> None:
    # Streamlit Cloud läuft in UTC. Um 23:30 UTC im Winter ist es in der Schweiz schon der nächste Tag.
    fixed_utc = datetime(2026, 11, 20, 23, 30, 15, 123456, tzinfo=timezone.utc)

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
            return fixed_utc.astimezone(tz) if tz else fixed_utc.replace(tzinfo=None)

    monkeypatch.setattr(turn_log, "datetime", FakeDatetime)
    ts = turn_log.now()
    assert ts.isoformat() == "2026-11-21T00:30:15+01:00"
    assert turn_log.log_path(ts).name == "2026-11-21.jsonl"


def test_timezone_is_zurich_with_summer_time() -> None:
    summer = datetime(2027, 7, 1, 12, 0, tzinfo=turn_log.TIMEZONE)
    winter = datetime(2026, 12, 1, 12, 0, tzinfo=turn_log.TIMEZONE)
    assert summer.utcoffset() == timedelta(hours=2)
    assert winter.utcoffset() == timedelta(hours=1)


# --- Turn-Regeln ------------------------------------------------------------


def test_naive_timestamp_is_rejected() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        tutor_turn(ts=datetime(2026, 11, 20, 10, 14, 3))


@pytest.mark.parametrize("session", ["s-7f3a", "7f3a91c2", "s-7F3A91C2", "s-7f3a91c2x", "anna.muster@bfh.ch"])
def test_invalid_session_id_is_rejected(session: str) -> None:
    with pytest.raises(ValidationError, match="session"):
        tutor_turn(session=session)


def test_unknown_field_is_rejected() -> None:
    # Kein Platz für Namen oder E-Mail-Adressen.
    with pytest.raises(ValidationError, match="email"):
        tutor_turn(email="anna.muster@bfh.ch")


@pytest.mark.parametrize("stage", [0, 4, -1])
def test_stage_outside_1_to_3_is_rejected(stage: int) -> None:
    with pytest.raises(ValidationError, match="Stufe muss 1, 2 oder 3 sein"):
        tutor_turn(stage=stage)


def test_unknown_role_is_rejected() -> None:
    with pytest.raises(ValidationError, match="role"):
        tutor_turn(role="system")


def test_unknown_prior_knowledge_is_rejected() -> None:
    with pytest.raises(ValidationError, match="prior_knowledge"):
        tutor_turn(prior_knowledge="neu")


def test_negative_temperature_is_rejected() -> None:
    with pytest.raises(ValidationError, match="temperature"):
        tutor_turn(temperature=-0.1)


@pytest.mark.parametrize("field", ["prompt_version", "model", "temperature", "prompt_hash", "cache_hit"])
@pytest.mark.parametrize("factory", [tutor_turn, grader_turn])
def test_llm_turn_needs_llm_fields(factory: Any, field: str) -> None:
    with pytest.raises(ValidationError, match=f"{field}: Pflicht"):
        factory(**{field: None})


def test_blank_model_counts_as_missing() -> None:
    with pytest.raises(ValidationError, match="model: Pflicht"):
        tutor_turn(model="  ")


@pytest.mark.parametrize("version", ["grader_v1", "tutor", "tutor_v", "tutor_v0", "tutor_v01", "tutor_v²", "v1"])
def test_prompt_version_must_match_role(version: str) -> None:
    with pytest.raises(ValidationError, match="prompt_version: muss tutor_v<n> sein"):
        tutor_turn(prompt_version=version)


@pytest.mark.parametrize("version", ["tutor_v1", "tutor_v12"])
def test_valid_prompt_versions(version: str) -> None:
    assert tutor_turn(prompt_version=version).prompt_version == version


@pytest.mark.parametrize("role", ["student", "hint"])
@pytest.mark.parametrize(
    ("field", "value"),
    [("prompt_version", "tutor_v1"), ("model", "qwen3.8-27b"), ("temperature", 0.2), ("prompt_hash", "b" * 64),
     ("cache_hit", False)],
)  # fmt: skip
def test_non_llm_turn_has_no_llm_fields(role: str, field: str, value: Any) -> None:
    with pytest.raises(ValidationError, match=f"{field}: nur bei tutor und grader erlaubt"):
        student_turn(role=role, **{field: value})


def test_hint_turn_is_valid_without_llm_fields() -> None:
    assert student_turn(role="hint", text="Expert:innen-Hint").role == "hint"


def test_grader_needs_verdict() -> None:
    with pytest.raises(ValidationError, match="verdict: Pflicht bei role=grader"):
        grader_turn(verdict=None)


@pytest.mark.parametrize("factory", [tutor_turn, student_turn])
def test_only_grader_has_verdict(factory: Any) -> None:
    with pytest.raises(ValidationError, match="verdict: nur bei role=grader"):
        factory(verdict="recognized")


@pytest.mark.parametrize("factory", [student_turn, grader_turn])
def test_guard_hit_only_on_tutor(factory: Any) -> None:
    with pytest.raises(ValidationError, match="guard_hit: nur bei role=tutor"):
        factory(guard_hit=True)


def test_guard_hit_on_hint_is_rejected() -> None:
    with pytest.raises(ValidationError, match="guard_hit"):
        student_turn(role="hint", guard_hit=True)


GRADER_ERRORS = ["empty_output", "invalid_json", "not_an_object", "schema_violation", "quote_not_found"]


@pytest.mark.parametrize("code", GRADER_ERRORS)
def test_grader_error_codes_with_partial_are_valid(tmp_path: Path, code: str) -> None:
    turn = grader_turn(verdict="partial", text="", error=code)
    path = turn_log.write_turn(turn, tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["error"] == code


@pytest.mark.parametrize("code", ["ungültiges JSON", "  ", "INVALID_JSON", "timeout"])
def test_unknown_error_code_is_rejected(code: str) -> None:
    with pytest.raises(ValidationError, match="error"):
        grader_turn(verdict="partial", error=code)


@pytest.mark.parametrize("verdict", ["recognized", "not"])
def test_grader_error_requires_partial(verdict: str) -> None:
    with pytest.raises(ValidationError, match="error: bei einem Fehler ist das Urteil immer partial"):
        grader_turn(verdict=verdict, error="invalid_json")


@pytest.mark.parametrize("factory", [tutor_turn, student_turn])
def test_error_only_on_grader(factory: Any) -> None:
    with pytest.raises(ValidationError, match="error: nur bei role=grader"):
        factory(error="invalid_json")


# --- hook, prompt_hash, n_examples, cache_hit -------------------------------


@pytest.mark.parametrize("factory", [tutor_turn, student_turn, grader_turn])
@pytest.mark.parametrize("hook", ["incident", "none"])
def test_hook_is_logged_for_every_role(tmp_path: Path, factory: Any, hook: str) -> None:
    path = turn_log.write_turn(factory(hook=hook), tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["hook"] == hook


def test_hook_is_required() -> None:
    with pytest.raises(ValidationError, match="hook"):
        tutor_turn(hook=None)


@pytest.mark.parametrize("hook", ["Incident", "ja", ""])
def test_unknown_hook_is_rejected(hook: str) -> None:
    with pytest.raises(ValidationError, match="hook"):
        tutor_turn(hook=hook)


@pytest.mark.parametrize("value", ["a" * 63, "A" * 64, "g" * 64, "a" * 65, "sha256:" + "a" * 57])
def test_prompt_hash_must_be_sha256_hex(value: str) -> None:
    with pytest.raises(ValidationError, match="prompt_hash"):
        tutor_turn(prompt_hash=value)


def test_cache_hit_true_is_logged(tmp_path: Path) -> None:
    path = turn_log.write_turn(grader_turn(cache_hit=True), tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["cache_hit"] is True


def test_tutor_needs_n_examples() -> None:
    with pytest.raises(ValidationError, match="n_examples: Pflicht bei role=tutor"):
        tutor_turn(n_examples=None)


def test_zero_examples_is_valid() -> None:
    assert tutor_turn(n_examples=0).n_examples == 0


def test_negative_examples_rejected() -> None:
    with pytest.raises(ValidationError, match="n_examples"):
        tutor_turn(n_examples=-1)


@pytest.mark.parametrize("factory", [student_turn, grader_turn])
def test_n_examples_only_on_tutor(factory: Any) -> None:
    with pytest.raises(ValidationError, match="n_examples: nur bei role=tutor"):
        factory(n_examples=2)


def test_turn_is_immutable() -> None:
    turn = tutor_turn()
    with pytest.raises(ValidationError):
        turn.text = "anders"  # type: ignore[misc]
