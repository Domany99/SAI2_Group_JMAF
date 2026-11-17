from __future__ import annotations

import pytest

from core.prior_knowledge import LEVELS, PriorKnowledge, parse_level


def test_every_level_has_info() -> None:
    assert set(LEVELS) == set(PriorKnowledge)


def test_level_numbers_are_unique_and_ordered() -> None:
    numbers = [LEVELS[level].number for level in PriorKnowledge]
    assert numbers == ["01", "02", "03"]


@pytest.mark.parametrize("raw", ["new", "basics", "experienced"])
def test_parse_level_accepts_stored_values(raw: str) -> None:
    assert parse_level(raw) == PriorKnowledge(raw)


@pytest.mark.parametrize("raw", ["", "pro", "Neu", "NEW"])
def test_parse_level_rejects_unknown_values(raw: str) -> None:
    with pytest.raises(ValueError, match="unbekannte Vorwissen-Stufe"):
        parse_level(raw)
