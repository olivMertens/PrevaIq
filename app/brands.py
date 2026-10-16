from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class BrandProfile:
    brand_name: str
    brand_key: str
    app_name: str
    prefix: str
    label: str | None
    primary: str
    secondary: str
    accent: str
    insurer_phone: str
    insurer_email: str
    portal_base_url: str
    signature: str
    member_term: str
    legal_footer: str


PREVAIQ = BrandProfile(
    brand_name="PrevaIQ",
    brand_key="prevaiq",
    app_name="PrevaIQ",
    prefix="Preva",
    label=None,
    primary="#17395C",
    secondary="#2EC4B6",
    accent="#0F2E4D",
    insurer_phone="09 72 12 34 56",
    insurer_email="sinistres@prevaiq.example.fr",
    portal_base_url="https://espace-assure.prevaiq.example.fr",
    signature="Votre conseiller PrevaIQ",
    member_term="client",
    legal_footer="PrevaIQ Assurance — Société fictive créée pour démonstration",
)

DEFAULT_BRAND = PREVAIQ

_BRANDS_BY_KEY = {PREVAIQ.brand_key: PREVAIQ}

_ALIASES = {
    "prevaiq": PREVAIQ.brand_key,
    "preva": PREVAIQ.brand_key,
}


def _normalize_lookup(value: str | None) -> str:
    raw = (value or DEFAULT_BRAND.brand_name).strip().lower()
    return raw.replace(" ", "").replace("-", "").replace("_", "")


def get_brand_profile(value: str | None = None) -> BrandProfile:
    """Return the canonical brand profile for a BRAND_NAME or brand key."""
    lookup = _normalize_lookup(value)
    key = _ALIASES.get(lookup)
    if key is None:
        raise ValueError(
            f"Unknown brand '{value}'. Choose from: "
            f"{', '.join(profile.brand_name for profile in _BRANDS_BY_KEY.values())}"
        )
    return _BRANDS_BY_KEY[key]


def get_current_brand_profile() -> BrandProfile:
    return get_brand_profile(os.getenv("BRAND_NAME", DEFAULT_BRAND.brand_name))


def current_brand_name() -> str:
    return get_current_brand_profile().brand_name


def current_brand_key() -> str:
    return get_current_brand_profile().brand_key
