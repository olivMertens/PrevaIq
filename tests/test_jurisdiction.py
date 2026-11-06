from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.jurisdiction import (
    FRANCE,
    application_jurisdiction,
    detect_jurisdiction,
    format_amount,
    parse_amount,
    swiss_language,
)


def _fields(**values: str) -> dict:
    return {
        f"llm_extracted:{key}": {"field_name": key, "value": value} for key, value in values.items()
    }


def test_swiss_claim_is_detected_from_address_phone_and_currency() -> None:
    result = detect_jurisdiction(
        _fields(
            AdresseAssure="Marktgasse 12, 8400 Winterthur",
            TelephoneAssure="+41 52 555 01 23",
            MontantEstime="CHF 1'697'400.00",
        )
    )
    assert (result.country, result.language, result.currency, result.postal_code) == (
        "CH",
        "de",
        "CHF",
        "8400",
    )


@pytest.mark.parametrize(
    ("address", "language"),
    [
        ("Rue du Marché 4, 1204 Genève, Suisse", "fr"),
        ("Via Nassa 7, 6900 Lugano, Svizzera", "it"),
        ("CH-3011 Bern", "de"),
    ],
)
def test_swiss_language_follows_the_postcode_area(address: str, language: str) -> None:
    result = detect_jurisdiction(_fields(LieuSinistre=address))
    assert result.country == "CH"
    assert result.language == language


def test_french_claims_stay_french() -> None:
    result = detect_jurisdiction(
        _fields(
            AdresseAssure="12 rue des Vignobles, 33000 Bordeaux",
            TelephoneAssure="+33 6 12 34 56 78",
            MontantEstime="10 825 €",
        )
    )
    assert result == FRANCE


def test_weak_or_missing_signals_default_to_france() -> None:
    assert detect_jurisdiction({}) == FRANCE
    assert detect_jurisdiction(None) == FRANCE
    # A 4-digit street number alone is not enough to switch to Switzerland.
    assert detect_jurisdiction(_fields(AdresseAssure="1200 chemin des Vignes")) == FRANCE
    # 5-digit postcodes never yield a 4-digit Swiss postcode.
    assert detect_jurisdiction(_fields(LieuSinistre="33000 Bordeaux, CHF")).country == "FR"


def test_free_text_adds_country_signals() -> None:
    result = detect_jurisdiction(
        _fields(LieuSinistre="8400 Winterthur"),
        texts=["Schadenmeldung — Geschäftsversicherung, Schweiz"],
    )
    assert result.country == "CH"


def test_application_jurisdiction_reads_extracted_fields() -> None:
    app_md = SimpleNamespace(
        extracted_fields=_fields(LieuSinistre="CH-8400 Winterthur", MontantEstime="CHF 96'000")
    )
    assert application_jurisdiction(app_md).currency == "CHF"
    assert application_jurisdiction(SimpleNamespace()).country == "FR"


def test_swiss_language_defaults_to_german() -> None:
    assert swiss_language(None) == "de"
    assert swiss_language("abcd") == "de"
    assert swiss_language("2500") == "fr"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("CHF 1'697'400.00", 1697400.0),
        ("Fr. 2'500.–", 2500.0),
        ("2'500.-", 2500.0),
        ("10 825 €", 10825.0),
        ("6,560.00", 6560.0),
        ("6 560,00 €", 6560.0),
        ("1.234,56", 1234.56),
        ("1,234", 1234.0),
        ("96000", 96000.0),
        (184000, 184000.0),
        ("", None),
        ("non spécifié", None),
        (None, None),
    ],
)
def test_parse_amount_handles_swiss_and_french_formats(text, expected) -> None:
    assert parse_amount(text) == expected


def test_format_amount_is_local() -> None:
    assert format_amount(1697400, "CHF", "de") == "CHF 1'697'400"
    assert format_amount(1697400, "CHF", "de-CH") == "CHF 1'697'400"
    assert format_amount(1697400, "CHF", "en") == "CHF 1,697,400"
    assert format_amount(1697400, "CHF", "fr") == "1\u202f697\u202f400 CHF"
    assert format_amount(6560, "EUR", "en") == "€6,560"
    assert format_amount(6560, "EUR", "fr") == "6\u202f560 €"
    assert format_amount(6560, "EUR", "de-CH") == "6'560 €"
    assert format_amount(None, "EUR") == ""
