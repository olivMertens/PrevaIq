#!/usr/bin/env python3
"""Generate branded mortgage demo PDF packs for PrevaIQ.

Creates synthetic mortgage files with logo + brand header and writes them into:
  assets/demo-prevaiq/mortgage/<category>/<subitem>/<app-id>/

Usage:
  python scripts/generate_mortgage_demo_documents.py
  python scripts/generate_mortgage_demo_documents.py --brand prevaiq
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from reportlab.lib.colors import HexColor, white
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas
except ImportError:
    print("Install reportlab: pip install reportlab")
    raise

from _brand_config import add_brand_arg, get_brand


@dataclass(frozen=True)
class MortgageScenario:
    app_id: str
    category: str
    subitem: str
    files: list[str]
    title: str
    borrower: str
    city: str


SCENARIOS: list[MortgageScenario] = [
    MortgageScenario(
        app_id="app-mtg-004",
        category="souscription-hypothecaire",
        subitem="primo-accedant",
        files=[
            "demande_pret_immobilier.pdf",
            "avis_imposition_2024.pdf",
            "compromis_vente.pdf",
        ],
        title="Dossier prêt immobilier - Primo-accédant",
        borrower="Marie DUPONT",
        city="Paris",
    ),
    MortgageScenario(
        app_id="app-mtg-005",
        category="souscription-hypothecaire",
        subitem="primo-accedant-ptz",
        files=[
            "demande_pret_ptz.pdf",
            "simulation_pret.pdf",
            "attestation_primo_accedant.pdf",
        ],
        title="Dossier PTZ - Primo-accédant",
        borrower="Stéphanie BLANCHARD",
        city="Orléans",
    ),
    MortgageScenario(
        app_id="app-mtg-006",
        category="souscription-hypothecaire",
        subitem="rachat-credit",
        files=[
            "demande_rachat_credit.pdf",
            "tableau_amortissement.pdf",
        ],
        title="Dossier rachat de crédit",
        borrower="Véronique BONNET",
        city="Clermont-Ferrand",
    ),
    MortgageScenario(
        app_id="app-mtg-007",
        category="souscription-hypothecaire",
        subitem="frontalier",
        files=[
            "demande_pret_frontalier.pdf",
            "contrat_travail_suisse.pdf",
        ],
        title="Dossier frontalier France/Suisse",
        borrower="Hans MULLER",
        city="Saint-Louis",
    ),
    MortgageScenario(
        app_id="app-mtg-008",
        category="souscription-hypothecaire",
        subitem="incomplet",
        files=["demande_pret.pdf"],
        title="Dossier incomplet - pièces manquantes",
        borrower="Julie CHEVALIER",
        city="Grenoble",
    ),
]


def _header(c: canvas.Canvas, brand_name: str, brand_color: str, logo_path: Path, document_name: str) -> None:
    width, height = A4
    c.setFillColor(HexColor(brand_color))
    c.rect(0, height - 28 * mm, width, 28 * mm, fill=True)

    if logo_path.exists():
        c.drawImage(str(logo_path), 14 * mm, height - 24 * mm, width=22 * mm, height=18 * mm, mask="auto")

    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(42 * mm, height - 15 * mm, f"{brand_name} - Dossier hypothécaire")
    c.setFont("Helvetica", 9)
    c.drawString(42 * mm, height - 21 * mm, document_name)


def _body(c: canvas.Canvas, scenario: MortgageScenario, filename: str, brand_name: str) -> None:
    width, height = A4
    y = height - 42 * mm

    c.setFillColor(HexColor("#222222"))
    c.setFont("Helvetica-Bold", 12)
    c.drawString(20 * mm, y, scenario.title)
    y -= 8 * mm

    c.setFont("Helvetica", 10)
    lines = [
        f"Référence dossier: {scenario.app_id}",
        f"Emprunteur: {scenario.borrower}",
        f"Ville du bien: {scenario.city}",
        f"Document: {filename}",
        "",
        "Ce document est un support de démonstration généré automatiquement.",
        "Les informations sont synthétiques et destinées à des tests UI / extraction.",
        "",
        "Points de contrôle HCSF:",
        "- Taux d'endettement cible <= 35%",
        "- Vérification apport / origine des fonds",
        "- Vérification stabilité des revenus",
    ]
    for line in lines:
        c.drawString(20 * mm, y, line)
        y -= 6 * mm

    c.setStrokeColor(HexColor("#DDDDDD"))
    c.line(20 * mm, 25 * mm, width - 20 * mm, 25 * mm)
    c.setFillColor(HexColor("#666666"))
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 20 * mm, f"{brand_name} - Document de démonstration")


def _output_root(brand: str) -> Path:
    return Path("assets") / f"demo-{brand}" / "mortgage"


def _render_document(
    out_file: Path,
    brand_name: str,
    brand_color: str,
    logo_path: Path,
    scenario: MortgageScenario,
    filename: str,
) -> None:
    out_file.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(out_file), pagesize=A4)
    _header(c, brand_name, brand_color, logo_path, filename)
    _body(c, scenario, filename, brand_name)
    c.save()


def generate_for_brand(brand: str) -> None:
    profile = get_brand(brand)
    root = _output_root(brand)
    logo = Path(profile.logo_path)

    print(f"Generating mortgage PDFs for {profile.name} in {root} ...")

    for scenario in SCENARIOS:
        scenario_root = root / scenario.category / scenario.subitem / scenario.app_id
        for filename in scenario.files:
            out_file = scenario_root / filename
            _render_document(
                out_file=out_file,
                brand_name=profile.name,
                brand_color=profile.color_hex,
                logo_path=logo,
                scenario=scenario,
                filename=filename,
            )
            print(f"  ✓ {out_file}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate branded mortgage demo documents")
    add_brand_arg(parser)
    args = parser.parse_args()

    generate_for_brand(args.brand)

    print("\nDone.")


if __name__ == "__main__":
    main()
