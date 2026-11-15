from __future__ import annotations

import pytest

from core.stages import (
    FIRST_STAGE,
    HOOK_STAGE,
    LAST_STAGE,
    Outcome,
    StageError,
    StageState,
    Verdict,
    finish_hook,
    on_verdict,
    start,
)

NOT_YET = [Verdict.PARTIAL, Verdict.NOT]


def test_start_without_hook_begins_at_stage_1() -> None:
    state = start()
    assert state == StageState(stage=1)
    assert not state.done
    assert not state.in_hook


def test_start_with_hook_begins_at_stage_0() -> None:
    state = start(with_hook=True)
    assert state.stage == HOOK_STAGE
    assert state.in_hook
    assert not state.done


def test_finish_hook_moves_to_stage_1() -> None:
    assert finish_hook(start(with_hook=True)) == StageState(stage=FIRST_STAGE)


@pytest.mark.parametrize("stage", [1, 2, 3])
def test_finish_hook_outside_stage_0_is_an_error(stage: int) -> None:
    with pytest.raises(StageError, match="nur in Stufe 0"):
        finish_hook(StageState(stage=stage))


def test_verdict_in_hook_is_an_error() -> None:
    with pytest.raises(StageError, match="Stufe 0"):
        on_verdict(start(with_hook=True), Verdict.RECOGNIZED)


@pytest.mark.parametrize("stage", [1, 2, 3])
def test_recognized_closes_at_any_stage(stage: int) -> None:
    state = on_verdict(StageState(stage=stage), Verdict.RECOGNIZED)
    assert state.done
    assert state.outcome is Outcome.RECOGNIZED
    assert state.stage == stage  # die Stufe, auf der gefunden wurde
    assert not state.reveal_issue


@pytest.mark.parametrize("verdict", NOT_YET)
@pytest.mark.parametrize("stage", [1, 2])
def test_not_yet_before_stage_3_goes_to_next_stage(stage: int, verdict: Verdict) -> None:
    state = on_verdict(StageState(stage=stage), verdict)
    assert state == StageState(stage=stage + 1)
    assert not state.done
    assert not state.reveal_issue


@pytest.mark.parametrize("verdict", NOT_YET)
def test_not_yet_at_stage_3_reveals_and_closes(verdict: Verdict) -> None:
    state = on_verdict(StageState(stage=LAST_STAGE), verdict)
    assert state.done
    assert state.outcome is Outcome.REVEALED
    assert state.reveal_issue


def test_issue_is_never_revealed_before_stage_3() -> None:
    """Die Garantie aus development.md: aufgelöst wird erst nach Stufe 3."""
    state = start()
    seen = []
    while not state.done:
        seen.append((state.stage, state.reveal_issue))
        state = on_verdict(state, Verdict.NOT)
    assert seen == [(1, False), (2, False), (3, False)]
    assert state.reveal_issue


@pytest.mark.parametrize("raw", ["recognized", "partial", "not"])
def test_string_verdicts_are_accepted(raw: str) -> None:
    assert on_verdict(StageState(stage=1), raw) == on_verdict(StageState(stage=1), Verdict(raw))


@pytest.mark.parametrize("raw", ["", "Recognized", "erkannt", "yes", None])
def test_unknown_verdict_is_an_error(raw: object) -> None:
    with pytest.raises(StageError, match="unbekanntes Urteil"):
        on_verdict(StageState(stage=1), raw)  # type: ignore[arg-type]


@pytest.mark.parametrize("outcome", list(Outcome))
def test_no_transition_after_done(outcome: Outcome) -> None:
    done = StageState(stage=2, outcome=outcome)
    with pytest.raises(StageError, match="bereits abgeschlossen"):
        on_verdict(done, Verdict.NOT)


@pytest.mark.parametrize("stage", [-1, 4, 10])
def test_invalid_stage_is_rejected(stage: int) -> None:
    with pytest.raises(StageError, match="Stufe muss"):
        StageState(stage=stage)


def test_cannot_be_done_in_hook() -> None:
    with pytest.raises(StageError, match="Stufe 0"):
        StageState(stage=HOOK_STAGE, outcome=Outcome.RECOGNIZED)


def test_state_is_immutable() -> None:
    state = start()
    with pytest.raises(AttributeError):
        state.stage = 2  # type: ignore[misc]


def test_transitions_do_not_change_the_old_state() -> None:
    before = StageState(stage=1)
    on_verdict(before, Verdict.NOT)
    assert before == StageState(stage=1)


def test_full_run_with_hook() -> None:
    state = finish_hook(start(with_hook=True))
    state = on_verdict(state, "partial")
    state = on_verdict(state, "recognized")
    assert state == StageState(stage=2, outcome=Outcome.RECOGNIZED)
