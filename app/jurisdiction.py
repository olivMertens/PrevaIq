"""Country, language and currency of a claim, inferred from its extracted fields.

The workbench was built for French claims (EUR, Cat-Nat, 5-digit postcodes). Swiss claims
need CHF amounts, German or French sources and Swiss policy terms, so callers branch on
the detected jurisdiction instead of assuming France.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Optional


@dataclass(frozen=True)
class Jurisdiction:
    country: str  # "FR" or "CH"
    language: str  # main language of local sources: "fr", "de" or "it"
    currency: str  # "EUR" or "CHF"
    postal_code: Optional[str] = None


FRANCE = Jurisdiction(country="FR", language="fr", currency="EUR")

# Fields that hold an address or a place: the postcode is only read from these.
_ADDRESS_KEYS = ("adresse", "address", "lieu", "location", "ort", "strasse", "ville", "commune")

_SWISS_COUNTRY_RE = re.compile(r"\b(schweiz|suisse|svizzera|switzerland)\b", re.I)
_SWISS_POSTCODE_RE = re.compile(
    r"(?:\bCH-\s?|(?<![\d'’.,]))(\d{4})(?![\d'’.,])\s+(?=[A-ZÀ-ÖØ-Þa-zß-öø-ÿ])"
)
_SWISS_PREFIXED_POSTCODE_RE = re.compile(r"\bCH-\s?(\d{4})\b")
_FRENCH_POSTCODE_RE = re.compile(r"(?<![\d'’.,])(\d{5})(?![\d'’.,])\s+(?=[A-ZÀ-ÖØ-Þa-zß-öø-ÿ])")
_SWISS_PHONE_RE = re.compile(r"(?:\+|\b00)41[\s.\-/]?\d")
_FRENCH_PHONE_RE = re.compile(r"(?:\+|\b00)33[\s.\-/]?\d")
_CHF_RE = re.compile(r"\bCHF\b|\bFr\.\s?\d|\d\s?Fr\.|\bSFr\b", re.I)
_EUR_RE = re.compile(r"€|\bEUR\b|\beuros?\b", re.I)


def _field_value(entry: Any) -> str:
    if isinstance(entry, Mapping):
        entry = entry.get("value")
    if entry is None:
        return ""
    return str(entry).strip()


def _field_name(key: str, entry: Any) -> str:
    if isinstance(entry, Mapping) and entry.get("field_name"):
        return str(entry["field_name"])
    return key.split(":")[-1]


def swiss_language(postal_code: Optional[str]) -> str:
    """Main language of a Swiss postcode area: Romandie fr, Ticino it, else de."""
    if not postal_code or not postal_code.isdigit():
        return "de"
    code = int(postal_code)
    if 1000 <= code <= 2999:
        return "fr"
    if 6500 <= code <= 6999:
        return "it"
    return "de"


def detect_jurisdiction(
    fields: Optional[Mapping[str, Any]],
    texts: Iterable[str] = (),
) -> Jurisdiction:
    """Jurisdiction of a claim from extracted fields (FR when nothing points to Switzerland).

    Signals: country names, ``CH-`` or 4-digit postcodes in address fields, +41 / +33 phone
    numbers and CHF / EUR amounts. ``texts`` adds free text (e.g. a declaration) for the
    country, phone and currency signals only.
    """
    swiss = 0
    french = 0
    postal_code: Optional[str] = None
    values: list[str] = []

    for key, entry in (fields or {}).items():
        value = _field_value(entry)
        if not value:
            continue
        values.append(value)
        name = _field_name(str(key), entry).lower()
        if not any(marker in name for marker in _ADDRESS_KEYS):
            continue
        prefixed = _SWISS_PREFIXED_POSTCODE_RE.search(value)
        if prefixed:
            swiss += 3
            postal_code = postal_code or prefixed.group(1)
        elif _FRENCH_POSTCODE_RE.search(value):
            french += 2
        else:
            match = _SWISS_POSTCODE_RE.search(value)
            if match:
                swiss += 2
                postal_code = postal_code or match.group(1)

    for value in [*values, *texts]:
        if _SWISS_COUNTRY_RE.search(value):
            swiss += 3
        if _SWISS_PHONE_RE.search(value):
            swiss += 2
        if _FRENCH_PHONE_RE.search(value):
            french += 2
        if _CHF_RE.search(value):
            swiss += 2
        if _EUR_RE.search(value):
            french += 1

    # A lone 4-digit number in an address could be a street number: Switzerland needs a
    # second signal (country, CH- prefix, +41 phone or CHF amount).
    if swiss >= 3 and swiss > french:
        return Jurisdiction(
            country="CH",
            language=swiss_language(postal_code),
            currency="CHF",
            postal_code=postal_code,
        )
    return FRANCE


def application_jurisdiction(app_md: Any) -> Jurisdiction:
    """Jurisdiction of a stored application (extracted fields only)."""
    return detect_jurisdiction(getattr(app_md, "extracted_fields", None) or {})


_AMOUNT_RE = re.compile(r"[-+]?\d[\d\s'’ .,]*")


def parse_amount(value: Any) -> Optional[float]:
    """Numeric amount from text: "CHF 1'697'400.00", "Fr. 2'500.–", "10 825 €", "6,560.00".

    Thousands separators may be apostrophes, spaces, dots or commas; the decimal separator
    is the last "." or "," followed by one or two digits. Returns None when no number.
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace("\u00a0", " ").replace("\u202f", " ")
    text = re.sub(r"[.,]\s*[–-]+", "", text)  # "2'500.–" means no cents
    match = _AMOUNT_RE.search(text)
    if not match:
        return None
    raw = re.sub(r"[\s'’]", "", match.group(0)).rstrip(".,")
    if not raw or raw in {"-", "+"}:
        return None
    last = max(raw.rfind("."), raw.rfind(","))
    if last >= 0 and 1 <= len(raw) - last - 1 <= 2:
        integer = re.sub(r"[.,]", "", raw[:last])
        number = f"{integer}.{raw[last + 1 :]}"
    else:
        number = re.sub(r"[.,]", "", raw)
    try:
        return float(number)
    except ValueError:
        return None


def format_amount(value: Optional[float], currency: str, language: str = "fr") -> str:
    """Display an amount the local way: "1 697 400 CHF" (fr), "CHF 1'697'400" (de), "€6,560" (en)."""
    if value is None:
        return ""
    rounded = round(value)
    if currency == "CHF":
        if language == "de":
            return "CHF " + f"{rounded:,}".replace(",", "'")
        if language == "en":
            return f"CHF {rounded:,}"
        return f"{rounded:,}".replace(",", "\u202f") + " CHF"
    if language == "en":
        return f"€{rounded:,}"
    if language == "de":
        return f"{rounded:,}".replace(",", ".") + " €"
    return f"{rounded:,}".replace(",", "\u202f") + " €"
