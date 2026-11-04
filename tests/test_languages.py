from __future__ import annotations

from app.languages import language_instruction, normalize_language


def test_supported_languages_are_normalized() -> None:
    assert normalize_language("en-US") == "en"
    assert normalize_language("fr-FR") == "fr"
    assert normalize_language("de-DE") == "de"
    assert normalize_language("unsupported") == "en"


def test_german_instruction_is_explicit() -> None:
    instruction = language_instruction("de")
    assert "auf Deutsch" in instruction
    assert "Quellenzitate" in instruction
    assert "unverändert" in instruction
