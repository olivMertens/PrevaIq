"""Shared brand configuration for demo PDF generation.

Each script imports a BrandProfile to parameterize colors, logos, text, and
email addresses. This avoids duplicating brand config across 4+ scripts.

Usage:
    from _brand_config import get_brand
    brand = get_brand("prevaiq")
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BrandProfile:
    """All brand-specific values needed by PDF generation scripts."""
    name: str                  # "PrevaIQ"
    name_upper: str            # "PREVAIQ"
    color_hex: str             # Primary brand color
    color_rgb: tuple[float, float, float]  # PyMuPDF (0-1) color
    logo_path: str             # Path to logo PNG
    logo_rect: tuple[float, float, float, float]  # (x0, y0, x1, y1) for fitz.Rect
    email_sinistres_hab: str   # sinistres.habitation@...
    email_sinistres_auto: str  # sinistres.auto@...
    email_sante: str           # sante@...
    email_souscription: str    # souscription@...
    phone_general: str         # Main service phone
    phone_sante: str           # Health service phone
    banner_label: str          # Banner text in email PDFs
    member_term: str           # "client"
    member_id_prefix: str      # "PRV"
    espace_client_url: str     # Client portal URL
    region_name: str           # "France"
    region_name_2: str         # "France"
    legal_footer: str          # Footer on claim/underwriting PDFs
    advisor_email_1: str       # sophie.duval@...
    advisor_email_2: str       # marc.lemaitre@...
    demo_output_dir: str       # "assets/demo-prevaiq"
    # Accent color for backgrounds (light tint of brand color)
    accent_bg_rgb: tuple[float, float, float]  # Light background tint


PREVAIQ = BrandProfile(
    name="PrevaIQ",
    name_upper="PREVAIQ",
    color_hex="#17395C",
    color_rgb=(0.09, 0.22, 0.36),
    logo_path="assets/logo-prevaiq.png",
    logo_rect=(40, 18, 185, 58),
    email_sinistres_hab="sinistres.habitation@prevaiq.example.fr",
    email_sinistres_auto="sinistres.auto@prevaiq.example.fr",
    email_sante="sante@prevaiq.example.fr",
    email_souscription="souscription@prevaiq.example.fr",
    phone_general="09 72 12 34 56",
    phone_sante="09 72 12 34 57",
    banner_label="PREVAIQ — Service Sinistres Habitation",
    member_term="client",
    member_id_prefix="PRV",
    espace_client_url="https://espace-assure.prevaiq.example.fr/documents",
    region_name="France",
    region_name_2="France",
    legal_footer="PrevaIQ Assurance — Société fictive créée pour démonstration",
    advisor_email_1="sophie.duval@prevaiq.example.fr",
    advisor_email_2="marc.lemaitre@prevaiq.example.fr",
    demo_output_dir="assets/demo-prevaiq",
    accent_bg_rgb=(0.94, 0.98, 0.99),
)

_BRANDS = {"prevaiq": PREVAIQ}


def get_brand(name: str = "prevaiq") -> BrandProfile:
    """Return the BrandProfile for the given brand name (case-insensitive)."""
    key = name.lower().strip()
    if key not in _BRANDS:
        raise ValueError(f"Unknown brand '{name}'. Choose from: {list(_BRANDS.keys())}")
    return _BRANDS[key]


def add_brand_arg(parser) -> None:
    """Add --brand argument to an argparse parser."""
    parser.add_argument(
        "--brand",
        default="prevaiq",
        choices=list(_BRANDS.keys()),
        help="Brand to use for PDF generation (default: prevaiq)",
    )
