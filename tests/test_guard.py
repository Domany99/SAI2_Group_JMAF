from __future__ import annotations

import pytest

from core.guard import contains_forbidden, find_forbidden, normalize


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("API-Key", "api key"),
        ("API key", "api key"),
        ("api_key", "api key"),
        ("Schlüssel", "schluessel"),
        ("SCHLÜSSEL", "schluessel"),
        ("Öffne die Tür", "oeffne die tuer"),
        ("Ärger", "aerger"),
        ("Strasse / Straße", "strasse strasse"),
        ("Wer sieht das?!", "wer sieht das"),
        ("  viel   \n Leerraum\t", "viel leerraum"),
        ("«Netzwerk»-Tab, 10'000×", "netzwerk tab 10 000"),
        ("", ""),
        ("...!?", ""),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


def test_normalize_treats_umlaut_and_spelled_out_form_alike() -> None:
    assert normalize("Schlüssel") == normalize("Schluessel")


def test_normalize_is_idempotent() -> None:
    once = normalize("Der API-Key im «Frontend»!")
    assert normalize(once) == once


def test_find_forbidden_matches_spelling_variants() -> None:
    text = "Im Quelltext steht der api_key und ein Schluessel."
    assert find_forbidden(text, ["API-Key", "Schlüssel", "secret"]) == ["API-Key", "Schlüssel"]


def test_find_forbidden_matches_only_whole_words() -> None:
    assert find_forbidden("The data is leaking", ["leak"]) == []
    assert find_forbidden("A leak!", ["leak"]) == ["leak"]


def test_find_forbidden_matches_multi_word_terms() -> None:
    assert find_forbidden("Ist das ein API Key?", ["API-Key"]) == ["API-Key"]
    assert find_forbidden("API und dann Key", ["API-Key"]) == []


def test_find_forbidden_ignores_terms_that_normalize_to_empty() -> None:
    assert find_forbidden("irgendein Text", ["", "--", "!"]) == []


def test_find_forbidden_without_terms() -> None:
    assert find_forbidden("irgendein Text", []) == []


def test_contains_forbidden() -> None:
    assert contains_forbidden("Wo ist der SECRET?", ["secret"]) is True
    assert contains_forbidden("Wer sieht das?", ["secret"]) is False
