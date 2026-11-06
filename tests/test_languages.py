from __future__ import annotations

import pytest

from app.languages import base_language, language_instruction, normalize_language, require_language


def test_supported_languages_are_normalized() -> None:
    assert normalize_language("en-US") == "en"
    assert normalize_language("fr-FR") == "fr"
    assert normalize_language("de-DE") == "de"
    assert normalize_language("de-CH") == "de-CH"
    assert normalize_language("unsupported") == "en"


def test_german_instruction_is_explicit() -> None:
    instruction = language_instruction("de")
    assert "auf Deutsch" in instruction
    assert "Quellenzitate" in instruction
    assert "unverändert" in instruction


@pytest.mark.parametrize("language", ["de", "de-DE", "de-CH", "DE-CH"])
def test_swiss_ui_locale_keeps_the_requested_output_variant(language: str) -> None:
    expected = "de-CH" if language.lower() == "de-ch" else "de"
    assert require_language(language) == expected


def test_swiss_instruction_is_explicit_without_changing_the_case_jurisdiction() -> None:
    instruction = language_instruction("de-CH")
    assert instruction != language_instruction("de")
    for requirement in ("Schweizer Hochdeutsch", "ss", "Dialekt", "Quellenzitate", "Rechtsordnung"):
        assert requirement in instruction


def test_swiss_locale_still_matches_german_source_evidence() -> None:
    assert base_language("de-CH") == base_language("de") == "de"
