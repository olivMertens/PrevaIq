#!/usr/bin/env python3
"""
Generate a demo claim PDF — Tempête et dégâts des eaux habitation.

Creates a realistic French insurance claim declaration with the brand logo,
client details, incident description, and inventory of damaged items.

Usage:
    python scripts/generate_demo_claim.py
    python scripts/generate_demo_claim.py --brand prevaiq
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

try:
    import fitz  # PyMuPDF
except ImportError:
    print("PyMuPDF required: uv add pymupdf")
    sys.exit(1)

from _brand_config import get_brand, add_brand_arg, BrandProfile


def generate_claim_pdf(brand: BrandProfile):
    """Generate a demo insurance claim PDF with brand-specific styling."""
    output_dir = Path(brand.demo_output_dir) / "habitation"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "declaration-sinistre-habitation.pdf"

    doc = fitz.open()

    # ─── Page 1: Déclaration de sinistre ───────────────────────
    page = doc.new_page(width=595, height=842)  # A4

    # Brand logo (top left)
    logo_path = Path(brand.logo_path)
    logo_rect = fitz.Rect(*brand.logo_rect)
    if logo_path.exists():
        page.insert_image(logo_rect, filename=str(logo_path))

    # Header — position relative to logo bottom
    title_y = logo_rect.y1 + 12
    page.insert_text((40, title_y), "DÉCLARATION DE SINISTRE HABITATION", fontsize=16,
                     fontname="helv", color=brand.color_rgb)
    page.insert_text((40, title_y + 16), "Réf. dossier : SIN-2026-HAB-04837", fontsize=9,
                     fontname="helv", color=(0.4, 0.4, 0.4))

    # Separator line
    sep_y = title_y + 24
    page.draw_line((40, sep_y), (555, sep_y), color=brand.color_rgb, width=1.5)

    y = sep_y + 12
    line_height = 13
    section_gap = 18

    def section_title(text, ypos):
        page.insert_text((40, ypos), text, fontsize=11,
                         fontname="helv", color=brand.color_rgb)
        page.draw_line((40, ypos + 4), (555, ypos + 4),
                       color=(0.85, 0.85, 0.85), width=0.5)
        return ypos + section_gap

    def field(label, value, ypos, x_val=200):
        page.insert_text((50, ypos), label, fontsize=9, fontname="helv",
                         color=(0.3, 0.3, 0.3))
        page.insert_text((x_val, ypos), value, fontsize=9, fontname="helv",
                         color=(0.1, 0.1, 0.1))
        return ypos + line_height

    # ─── Section: Informations Assuré ──────────────────────────
    y = section_title("INFORMATIONS DE L'ASSURÉ", y)
    y = field("Nom et prénom :", "MERTENS LAFFITE Olivier", y)
    y = field("Adresse :", "42 rue des Vignobles, 33000 Bordeaux", y)
    y = field("Téléphone :", "06 12 34 56 78", y)
    y = field("Email :", "mlo@wine.com", y)
    y = field(f"N° de {brand.member_term} :", f"{brand.member_id_prefix}-2021-917453", y)
    y += 8

    # ─── Section: Contrat d'assurance ──────────────────────────
    y = section_title("CONTRAT D'ASSURANCE", y)
    y = field("N° de contrat :", "HAB-33-2021-091745", y)
    y = field("Formule :", "Multirisque Habitation — Formule Confort Plus", y)
    y = field("Date d'effet :", "15/06/2021", y)
    y = field("Dernière cotisation :", "15/01/2026 — 912,00 € / an", y)
    y = field("Franchise :", "250 € (dégâts des eaux) / 380 € (tempête)", y)
    y += 8

    # ─── Section: Circonstances du sinistre ────────────────────
    y = section_title("CIRCONSTANCES DU SINISTRE", y)
    y = field("Date du sinistre :", "27 mars 2026", y)
    y = field("Heure :", "Constaté vers 07h30 le 28 mars 2026", y)
    y = field("Nature du sinistre :", "Dégâts des eaux — Infiltration suite à tempête", y)
    y = field("Lieu exact :", "Cave et sous-sol de la maison individuelle", y)
    y += 6

    # Description longue
    page.insert_text((50, y), "Description détaillée :", fontsize=9,
                     fontname="helv", color=(0.3, 0.3, 0.3))
    y += line_height

    desc_lines = [
        "Suite aux fortes pluies et vents violents de la nuit du 27 au 28 mars 2026",
        "(tempête Gérard, rafales 115 km/h — station Météo France Bordeaux-Mérignac),",
        "importante infiltration d'eau dans la cave par le soupirail ouest et fissures",
        "dans le mur de fondation côté jardin.",
        "",
        "L'eau a envahi le sous-sol sur ~15 cm, endommageant la cave à vins (casiers bois,",
        "bouteilles au sol), le mobilier de rangement et les revêtements muraux. Traces de",
        "moisissure visibles. Compteur électrique touché — installation a disjoncté 2 fois.",
        "",
        "Mesures immédiates : coupure alimentation électrique, pompage eau résiduelle,",
        "photos des dommages. Plombier intervenu le 29/03 (canalisation obstruée par débris).",
        "Collection de vins : grands crus Saint-Émilion et Pauillac.",
    ]
    for line in desc_lines:
        if line:
            page.insert_text((60, y), line, fontsize=8, fontname="helv",
                             color=(0.15, 0.15, 0.15))
        y += 11
    y += 4

    # ─── Section: Tiers impliqués ──────────────────────────────
    y = section_title("TIERS IMPLIQUÉS", y)
    y = field("Tiers responsable :", "Non applicable (événement climatique)", y)
    y = field("Voisinage impacté :", "Oui — voisin au 44 rue des Vignobles (M. Dupont)", y)
    y += 8

    # ─── Section: Mesures prises ──────────────────────────────
    y = section_title("MESURES CONSERVATOIRES PRISES", y)
    y = field("Pompage des eaux :", "Effectué le 28/03/2026 par l'assuré", y)
    y = field("Coupure électrique :", "Sous-sol isolé le 28/03/2026", y)
    y = field("Intervention plombier :", "SOS Plomberie Bordeaux — Facture n° F2026-1847", y)
    y = field("Devis de remise en état :", "Entreprise Réno'Caves — en attente", y)

    # Footer
    page.insert_text((40, 800), brand.legal_footer,
                     fontsize=7, fontname="helv", color=(0.5, 0.5, 0.5))
    page.insert_text((40, 812), "3 place des Quinconces, 33000 Bordeaux — Tél. 05 56 XX XX XX",
                     fontsize=7, fontname="helv", color=(0.5, 0.5, 0.5))
    page.insert_text((440, 812), "Page 1/2", fontsize=7, fontname="helv",
                     color=(0.5, 0.5, 0.5))

    # ─── Page 2: Inventaire des biens endommagés ───────────────
    page2 = doc.new_page(width=595, height=842)

    # Logo
    if logo_path.exists():
        page2.insert_image(fitz.Rect(*brand.logo_rect), filename=str(logo_path))

    p2_title_y = logo_rect.y1 + 12
    page2.insert_text((40, p2_title_y), "INVENTAIRE DES BIENS ENDOMMAGÉS", fontsize=16,
                      fontname="helv", color=brand.color_rgb)
    page2.insert_text((40, p2_title_y + 16), "Réf. dossier : SIN-2026-HAB-04837 — Suite",
                      fontsize=9, fontname="helv", color=(0.4, 0.4, 0.4))
    p2_sep_y = p2_title_y + 24
    page2.draw_line((40, p2_sep_y), (555, p2_sep_y), color=brand.color_rgb, width=1.5)

    y2 = p2_sep_y + 12

    # Table header
    headers = ["Bien endommagé", "Qté", "Valeur estim.", "État", "Justificatif"]
    col_x = [50, 250, 310, 390, 460]

    # Header background
    page2.draw_rect(fitz.Rect(40, y2 - 12, 555, y2 + 4),
                    color=(0.93, 0.93, 0.93), fill=(0.93, 0.93, 0.93))
    for i, h in enumerate(headers):
        page2.insert_text((col_x[i], y2), h, fontsize=8, fontname="helv",
                          color=(0.2, 0.2, 0.2))
    y2 += 18

    # Table rows
    items = [
        ["Bouteilles de vin (Saint-Émilion Grand Cru)", "6", "1 800 €", "Détruit", "Photos + factures"],
        ["Bouteilles de vin (Pauillac 2018)", "12", "2 640 €", "Détruit", "Photos + factures"],
        ["Bouteilles de vin (Bordeaux sup.)", "24", "960 €", "Détruit", "Photos"],
        ["Bouteilles champagne / Sauternes", "8", "480 €", "Détruit", "Photos"],
        ["Casiers à vin en bois de chêne", "4", "680 €", "Détruit", "Photo + devis"],
        ["Étagères métalliques de rangement", "2", "240 €", "Endommagé", "Photo"],
        ["Outils de jardinage", "—", "350 €", "Endommagé", "Estimation"],
        ["Cartons de documents personnels", "6", "—", "Détruit", "—"],
        ["Vélo VTT adulte (Decathlon)", "1", "450 €", "Endommagé", "Facture"],
        ["Revêtement mural cave (peinture)", "35 m²", "1 200 €", "À refaire", "Devis"],
        ["Compteur électrique sous-sol", "1", "380 €", "HS", "Facture électricien"],
        ["Pompe de relevage (remplacement)", "1", "290 €", "HS", "Facture plombier"],
        ["Détecteur de fumée cave", "1", "45 €", "HS", "—"],
        ["Porte de cave en bois", "1", "520 €", "Gonflée", "Devis menuisier"],
        ["Traitement anti-moisissure", "—", "850 €", "À réaliser", "Devis"],
    ]

    for row in items:
        if y2 > 700:
            break
        for i, val in enumerate(row):
            page2.insert_text((col_x[i], y2), val, fontsize=8, fontname="helv",
                              color=(0.15, 0.15, 0.15))
        page2.draw_line((40, y2 + 5), (555, y2 + 5),
                        color=(0.92, 0.92, 0.92), width=0.3)
        y2 += 16

    # Total
    y2 += 10
    page2.draw_rect(fitz.Rect(40, y2 - 12, 555, y2 + 8),
                    color=brand.color_rgb, fill=brand.accent_bg_rgb)
    page2.insert_text((50, y2), "TOTAL ESTIMÉ DES DOMMAGES :", fontsize=10,
                      fontname="helv", color=brand.color_rgb)
    page2.insert_text((350, y2), "10 825 €", fontsize=12,
                      fontname="helv", color=brand.color_rgb)

    # Signature block
    y2 += 40
    page2.insert_text((50, y2), "Déclaration sur l'honneur :", fontsize=9,
                      fontname="helv", color=(0.3, 0.3, 0.3))
    y2 += 16
    page2.insert_text((50, y2),
                      "Je soussigné Olivier MERTENS LAFFITE certifie l'exactitude des informations",
                      fontsize=8.5, fontname="helv", color=(0.15, 0.15, 0.15))
    y2 += 12
    page2.insert_text((50, y2),
                      "ci-dessus et m'engage à fournir tous justificatifs complémentaires",
                      fontsize=8.5, fontname="helv", color=(0.15, 0.15, 0.15))
    y2 += 12
    page2.insert_text((50, y2),
                      f"demandés par {brand.name} pour l'instruction de ce dossier.",
                      fontsize=8.5, fontname="helv", color=(0.15, 0.15, 0.15))
    y2 += 26
    page2.insert_text((50, y2), "Fait à Bordeaux, le 29 mars 2026", fontsize=9,
                      fontname="helv", color=(0.15, 0.15, 0.15))
    y2 += 16
    page2.insert_text((50, y2), "Signature : O. Mertens Laffite", fontsize=9,
                      fontname="helv", color=(0.15, 0.15, 0.15))

    # Email block (bottom — simulates forwarded email)
    y2 += 40
    page2.draw_rect(fitz.Rect(40, y2 - 10, 555, y2 + 80),
                    color=(0.95, 0.95, 0.95), fill=(0.97, 0.97, 0.97))
    page2.insert_text((50, y2 + 4), "📧 Email du client — 29/03/2026 08:14", fontsize=8,
                      fontname="helv", color=(0.4, 0.4, 0.4))
    page2.insert_text((50, y2 + 18), "De : mlo@wine.com", fontsize=8,
                      fontname="helv", color=(0.3, 0.3, 0.3))
    page2.insert_text((50, y2 + 30), f"À : {brand.email_sinistres_hab}", fontsize=8,
                      fontname="helv", color=(0.3, 0.3, 0.3))
    page2.insert_text((50, y2 + 42),
                      "Objet : URGENT — Déclaration sinistre habitation suite tempête Gérard",
                      fontsize=8, fontname="helv", color=(0.3, 0.3, 0.3))
    page2.insert_text((50, y2 + 58),
                      "Bonjour, veuillez trouver ci-joint ma déclaration de sinistre et les photos",
                      fontsize=8, fontname="helv", color=(0.3, 0.3, 0.3))
    page2.insert_text((50, y2 + 68),
                      "des dégâts dans ma cave. Mes grands crus sont totalement perdus. Merci de traiter en urgence.",
                      fontsize=8, fontname="helv", color=(0.3, 0.3, 0.3))

    # Footer
    page2.insert_text((40, 800),
                      brand.legal_footer,
                      fontsize=7, fontname="helv", color=(0.5, 0.5, 0.5))
    page2.insert_text((40, 812),
                      "Ce document est confidentiel. Toute utilisation ou diffusion non autorisée est interdite.",
                      fontsize=7, fontname="helv", color=(0.5, 0.5, 0.5))
    page2.insert_text((440, 812), "Page 2/2", fontsize=7, fontname="helv",
                      color=(0.5, 0.5, 0.5))

    # Save
    doc.save(str(output_path), deflate=True, garbage=3)
    doc.close()

    print(f"✅ PDF généré : {output_path}")
    print(f"   2 pages, logo {brand.name}, déclaration sinistre tempête + inventaire cave à vins")
    print("   Client : Olivier MERTENS LAFFITE, 42 rue des Vignobles, Bordeaux")
    print("   Email  : mlo@wine.com")
    print("   Sinistre : Tempête Gérard (27/03/2026) — Dégâts des eaux cave")
    print("   Montant estimé : 10 825 €")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate demo claim PDF")
    add_brand_arg(parser)
    args = parser.parse_args()
    brand = get_brand(args.brand)
    generate_claim_pdf(brand)
