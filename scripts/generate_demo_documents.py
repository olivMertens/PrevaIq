#!/usr/bin/env python3
"""Generate realistic fake demo documents for claims processing.

Creates:
- Facture de réparation (plombier)
- Devis de réparation
- Facture électricien
- Email de réclamation client (format PDF)
- Email de relance client

Usage:
    pip install reportlab
    python scripts/generate_demo_documents.py [--brand prevaiq]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor, white
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Table, TableStyle
except ImportError:
    print("Install reportlab: pip install reportlab")
    raise

from _brand_config import get_brand, add_brand_arg, BrandProfile

BRAND: BrandProfile = None  # type: ignore[assignment]
BRAND_COLOR: HexColor = None  # type: ignore[assignment]

LIGHT_GRAY = HexColor("#f5f5f5")
MEDIUM_GRAY = HexColor("#999999")
DARK_GRAY = HexColor("#333333")


def _header(c: canvas.Canvas, title: str, subtitle: str = ""):
    w, h = A4
    c.setFillColor(BRAND_COLOR)
    c.rect(0, h - 25 * mm, w, 25 * mm, fill=True)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(20 * mm, h - 17 * mm, title)
    if subtitle:
        c.setFont("Helvetica", 9)
        c.drawString(20 * mm, h - 22 * mm, subtitle)


def _invoice_table(c: canvas.Canvas, y: float, data: list[list[str]]) -> float:
    table = Table(data, colWidths=[100 * mm, 15 * mm, 25 * mm, 25 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), BRAND_COLOR),
        ("TEXTCOLOR", (0, 0), (-1, 0), white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
        ("GRID", (0, 0), (-1, -1), 0.5, MEDIUM_GRAY),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [white, LIGHT_GRAY]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    _, th = table.wrap(0, 0)
    table.drawOn(c, 20 * mm, y - th)
    return y - th - 8 * mm


def _company_block(c: canvas.Canvas, y: float, name: str, addr: str, siret: str, extra: str = "") -> float:
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(DARK_GRAY)
    c.drawString(20 * mm, y, name)
    c.setFont("Helvetica", 9)
    y -= 5 * mm
    c.drawString(20 * mm, y, addr)
    y -= 4 * mm
    c.drawString(20 * mm, y, siret)
    if extra:
        y -= 4 * mm
        c.drawString(20 * mm, y, extra)
    return y


def _client_block(c: canvas.Canvas, y: float) -> float:
    c.setFont("Helvetica-Bold", 10)
    c.drawString(120 * mm, y, "Client :")
    c.setFont("Helvetica", 9)
    y -= 5 * mm
    c.drawString(120 * mm, y, "M. MERTENS LAFFITE Olivier")
    y -= 4 * mm
    c.drawString(120 * mm, y, "42 rue des Vignobles, 33000 Bordeaux")
    return y


def _totals(c: canvas.Canvas, y: float, ht: str, tva: str, ttc: str) -> float:
    w = A4[0]
    c.setFont("Helvetica", 9)
    c.setFillColor(DARK_GRAY)
    c.drawRightString(w - 20 * mm, y, f"Total HT : {ht}")
    y -= 5 * mm
    c.drawRightString(w - 20 * mm, y, f"TVA 10% : {tva}")
    y -= 6 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(w - 20 * mm, y, f"Total TTC : {ttc}")
    return y


# ── Document generators ────────────────────────────────────────────


def gen_facture_plombier(out: Path):
    fp = out / "facture-plombier-degats-eaux.pdf"
    c = canvas.Canvas(str(fp), pagesize=A4)
    h = A4[1]
    _header(c, "FACTURE", "N° FACT-2026-0487")
    y = h - 40 * mm
    y = _company_block(c, y, "DURAND PLOMBERIE SARL",
                       "14 rue des Artisans, 33000 Bordeaux",
                       "SIRET : 498 721 345 00028 — TVA : FR 72 498721345",
                       "Tél : 05 56 78 12 34 — contact@durand-plomberie.fr")
    y -= 8 * mm
    y = _client_block(c, y)
    y -= 10 * mm
    c.setFont("Helvetica", 9)
    c.setFillColor(MEDIUM_GRAY)
    c.drawString(20 * mm, y, "Date de facture : 02/04/2026")
    c.drawString(120 * mm, y, "Intervention : 28/03/2026")
    y -= 4 * mm
    c.drawString(20 * mm, y, "Réf. sinistre : SIN-2026-HAB-04837")
    y -= 12 * mm
    y = _invoice_table(c, y, [
        ["Désignation", "Qté", "P.U. HT", "Total HT"],
        ["Déplacement urgence + diagnostic fuite", "1", "95,00 €", "95,00 €"],
        ["Recherche de fuite par caméra thermique", "1", "250,00 €", "250,00 €"],
        ["Remplacement canalisation cuivre Ø22 (3ml)", "3", "45,00 €", "135,00 €"],
        ["Raccords, joints, colliers de fixation", "1", "65,00 €", "65,00 €"],
        ["Main d'œuvre réparation (4h)", "4", "55,00 €", "220,00 €"],
        ["Pompage eau résiduelle cave", "1", "180,00 €", "180,00 €"],
        ["Traitement anti-humidité murs (2 couches)", "1", "320,00 €", "320,00 €"],
        ["Nettoyage et remise en état", "1", "150,00 €", "150,00 €"],
    ])
    y = _totals(c, y, "1 415,00 €", "141,50 €", "1 556,50 €")
    y -= 15 * mm
    c.setFont("Helvetica", 8)
    c.setFillColor(MEDIUM_GRAY)
    c.drawString(20 * mm, y, "Conditions : 30 jours fin de mois — RIB : FR76 3000 4012 3400 0107 8456 123")
    c.save()
    print(f"  ✓ {fp.name}")
    return fp


def gen_devis(out: Path):
    fp = out / "devis-reparation-habitation.pdf"
    c = canvas.Canvas(str(fp), pagesize=A4)
    h = A4[1]
    _header(c, "DEVIS", "N° DEV-2026-0412")
    y = h - 40 * mm
    y = _company_block(c, y, "DURAND PLOMBERIE SARL",
                       "14 rue des Artisans, 33000 Bordeaux",
                       "SIRET : 498 721 345 00028")
    y -= 8 * mm
    y = _client_block(c, y)
    y -= 10 * mm
    c.setFont("Helvetica", 9)
    c.setFillColor(MEDIUM_GRAY)
    c.drawString(20 * mm, y, "Date du devis : 28/03/2026        Validité : 30 jours")
    y -= 4 * mm
    c.drawString(20 * mm, y, "Objet : Réparation suite sinistre dégâts des eaux — infiltration cave")
    y -= 12 * mm
    y = _invoice_table(c, y, [
        ["Désignation", "Qté", "P.U. HT", "Total HT"],
        ["Diagnostic et recherche de fuite", "1", "250,00 €", "250,00 €"],
        ["Réparation canalisation", "1", "200,00 €", "200,00 €"],
        ["Matériaux (cuivre, raccords, joints)", "1", "65,00 €", "65,00 €"],
        ["Pompage et assèchement", "1", "180,00 €", "180,00 €"],
        ["Traitement anti-humidité", "1", "280,00 €", "280,00 €"],
        ["Remise en état des surfaces", "1", "150,00 €", "150,00 €"],
    ])
    # Devis = 1125 HT vs facture = 1415 HT → +25.8% écart
    y = _totals(c, y, "1 125,00 €", "112,50 €", "1 237,50 €")
    y -= 20 * mm
    c.setFont("Helvetica", 8)
    c.setFillColor(MEDIUM_GRAY)
    c.drawString(20 * mm, y, "Devis valable 30 jours. Bon pour accord :")
    y -= 12 * mm
    c.drawString(20 * mm, y, "Date : ........................    Signature : ........................")
    c.save()
    print(f"  ✓ {fp.name}")
    return fp


def gen_facture_electricien(out: Path):
    fp = out / "facture-electricien-mise-securite.pdf"
    c = canvas.Canvas(str(fp), pagesize=A4)
    h = A4[1]
    _header(c, "FACTURE", "N° FE-2026-1089")
    y = h - 40 * mm
    y = _company_block(c, y, "GIRONDE ÉLECTRICITÉ",
                       "8 avenue de la République, 33000 Bordeaux",
                       "SIRET : 523 891 467 00015 — TVA : FR 85 523891467")
    y -= 8 * mm
    y = _client_block(c, y)
    y -= 10 * mm
    c.setFont("Helvetica", 9)
    c.setFillColor(MEDIUM_GRAY)
    c.drawString(20 * mm, y, "Date : 30/03/2026    |    Réf. sinistre : SIN-2026-HAB-04837")
    y -= 12 * mm
    y = _invoice_table(c, y, [
        ["Désignation", "Qté", "P.U. HT", "Total HT"],
        ["Diagnostic installation électrique cave", "1", "120,00 €", "120,00 €"],
        ["Remplacement tableau divisionnaire cave", "1", "350,00 €", "350,00 €"],
        ["Câblage neuf section cave (15ml)", "15", "12,00 €", "180,00 €"],
        ["Prises étanches IP44 (remplacement)", "4", "35,00 €", "140,00 €"],
        ["Main d'œuvre (3h)", "3", "60,00 €", "180,00 €"],
        ["Mise en conformité + attestation Consuel", "1", "95,00 €", "95,00 €"],
    ])
    y = _totals(c, y, "1 065,00 €", "106,50 €", "1 171,50 €")
    y -= 15 * mm
    c.setFont("Helvetica", 8)
    c.setFillColor(MEDIUM_GRAY)
    c.drawString(20 * mm, y, "Règlement sous 30 jours — RIB sur demande")
    c.save()
    print(f"  ✓ {fp.name}")
    return fp


def _email_header(c: canvas.Canvas, from_: str, to: str, date: str, subject: str, color: str = "#1a1a1a", attachments: str = ""):
    h = A4[1]
    c.setFillColor(LIGHT_GRAY)
    c.rect(0, h - 50 * mm, A4[0], 50 * mm, fill=True)
    y = h - 12 * mm
    c.setFillColor(DARK_GRAY)
    for label, val in [("De :", from_), ("À :", to), ("Date :", date)]:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(15 * mm, y, label)
        c.setFont("Helvetica", 10)
        c.drawString(30 * mm, y, val)
        y -= 6 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(15 * mm, y, "Objet :")
    c.setFillColor(HexColor(color))
    c.setFont("Helvetica-Bold", 10)
    c.drawString(30 * mm, y, subject)
    y -= 6 * mm
    if attachments:
        c.setFont("Helvetica", 8)
        c.setFillColor(MEDIUM_GRAY)
        c.drawString(15 * mm, y, f"Pièces jointes : {attachments}")
    return y - 10 * mm


def _write_lines(c: canvas.Canvas, y: float, lines: list[str]) -> float:
    c.setFillColor(DARK_GRAY)
    c.setFont("Helvetica", 10)
    for line in lines:
        c.drawString(15 * mm, y, line)
        y -= 4.5 * mm
    return y


def gen_email_reclamation(out: Path):
    fp = out / "email-reclamation-client.pdf"
    c = canvas.Canvas(str(fp), pagesize=A4)
    y = _email_header(c,
        "olivier.mertens-laffite@example.com",
        BRAND.email_sinistres_hab,
        "27 mars 2026 à 08:42",
        "URGENT — Déclaration de sinistre dégâts des eaux — Contrat HAB-33-2021-091745",
        attachments="declaration-sinistre-habitation.pdf, photos (4)")

    y = _write_lines(c, y, [
        "Bonjour,",
        "",
        "Je vous contacte en URGENCE suite à d'importants dégâts des eaux survenus",
        "dans ma maison située au 42 rue des Vignobles, 33000 Bordeaux.",
        "",
        "Les faits :",
        "- Date du sinistre : 27 mars 2026, suite à la tempête",
        "- Infiltration massive par le toit → cave et sous-sol inondés",
        "- Dégâts constatés :",
        "    • Murs : moisissures noires, salpêtre, fissures visibles",
        "    • Sol : dégradation de l'enduit mural",
        "    • Cave : bouteilles de vin de collection détruites",
        "      (Château Mertens Laffite, Nuit Sans Pareil, Grand Cru)",
        "    • Casiers en bois : souillés et endommagés",
        "",
        "J'ai fait intervenir un plombier en urgence (facture à suivre).",
        "Je vous joins ma déclaration de sinistre + photos des dommages.",
        "",
        "Mon contrat : HAB-33-2021-091745 (Formule Confort Plus)",
        f"Mon n° de {BRAND.member_term} : SOC-33-789456",
        "",
        "C'est la TROISIÈME fois que je vous contacte depuis 48h sans réponse.",
        "Je suis très inquiet car les moisissures se propagent rapidement.",
        "Merci de traiter ce dossier en priorité.",
        "",
        "Cordialement,",
        "Olivier MERTENS LAFFITE",
        "Tél : 06 12 34 56 78",
    ])
    c.save()
    print(f"  ✓ {fp.name}")
    return fp


def gen_email_relance(out: Path):
    fp = out / "email-relance-client.pdf"
    c = canvas.Canvas(str(fp), pagesize=A4)
    y = _email_header(c,
        "olivier.mertens-laffite@example.com",
        BRAND.email_sinistres_hab,
        "5 avril 2026 à 14:18",
        "RE: URGENT — Relance sinistre HAB-33-2021-091745 — SANS RÉPONSE DEPUIS 10 JOURS",
        color="#cc0000")

    y = _write_lines(c, y, [
        "Bonjour,",
        "",
        "Je me permets de vous relancer car je n'ai toujours reçu AUCUNE réponse",
        "à ma déclaration de sinistre envoyée le 27 mars dernier.",
        "",
        "La situation a empiré :",
        "- Les moisissures se sont étendues sur 3 murs de la cave",
        "- Une odeur d'humidité permanente rend le rez-de-chaussée difficile",
        "- J'ai dû faire venir le plombier une 2ème fois (fuites résiduelles)",
        "- Le devis de réparation s'élève à 1 237,50 € TTC",
        "- La facture d'intervention d'urgence est de 1 556,50 € TTC",
        "",
        "Soit un écart de +25% par rapport au devis initial.",
        "Le plombier m'a expliqué que des travaux supplémentaires étaient",
        "nécessaires (caméra thermique, traitement anti-humidité renforcé).",
        "",
        f"Je vous ai appelé 3 fois au {BRAND.phone_general}, sans succès.",
        f"Je suis {BRAND.member_term} {BRAND.name} depuis 12 ans et n'ai jamais eu de sinistre.",
        "Je ne comprends pas ce silence.",
        "",
        "Merci de me confirmer la prise en charge dans les plus brefs délais.",
        "",
        "Cordialement,",
        "Olivier MERTENS LAFFITE",
    ])
    c.save()
    print(f"  ✓ {fp.name}")
    return fp


def main():
    global BRAND, BRAND_COLOR
    parser = argparse.ArgumentParser(description="Generate demo documents")
    parser.add_argument("--output-dir", default=None, help="Output directory")
    add_brand_arg(parser)
    args = parser.parse_args()

    BRAND = get_brand(args.brand)
    BRAND_COLOR = HexColor(BRAND.color_hex)

    out = Path(args.output_dir or f"{BRAND.demo_output_dir}/habitation")
    out.mkdir(parents=True, exist_ok=True)

    print(f"Generating demo documents ({BRAND.name})...\n")
    gen_facture_plombier(out)
    gen_devis(out)
    gen_facture_electricien(out)
    gen_email_reclamation(out)
    gen_email_relance(out)

    print(f"\n✅ All documents generated in {out}/")
    print("\n📋 Scénario démo :")
    print("  1. email-reclamation-client.pdf — Email initial (27/03)")
    print("  2. devis-reparation-habitation.pdf — Devis plombier (28/03) = 1 237,50 €")
    print("  3. facture-plombier-degats-eaux.pdf — Facture (02/04) = 1 556,50 € (+25%)")
    print("  4. facture-electricien-mise-securite.pdf — Électricien (30/03) = 1 171,50 €")
    print("  5. email-relance-client.pdf — Relance stressée (05/04)")
    print("\n🎯 Total sinistre : 2 728,00 € TTC — Écart devis/facture : +25%")


if __name__ == "__main__":
    main()
