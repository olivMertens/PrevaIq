#!/usr/bin/env python3
"""
Generate a demo underwriting PDF — Souscription Complémentaire Santé.

Creates a realistic French health insurance subscription request with:
- Client email requesting Complémentaire Santé
- Health questionnaire with pre-existing conditions
- List of attached documents

Usage:
    python scripts/generate_demo_underwriting.py
    python scripts/generate_demo_underwriting.py --brand prevaiq
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


def generate_underwriting_pdf(brand: BrandProfile):
    output_dir = Path(brand.demo_output_dir) / "sante"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "souscription-sante-lefevre.pdf"

    doc = fitz.open()

    # ─── Page 1: Email du client + Demande de souscription ─────
    page = doc.new_page(width=595, height=842)

    logo_path = Path(brand.logo_path)
    logo_rect = fitz.Rect(*brand.logo_rect)
    if logo_path.exists():
        page.insert_image(logo_rect, filename=str(logo_path))

    title_y = logo_rect.y1 + 12
    page.insert_text((40, title_y), "DEMANDE DE SOUSCRIPTION", fontsize=16,
                     fontname="helv", color=brand.color_rgb)
    page.insert_text((40, title_y + 16), "Complementaire Sante — Formule Equilibre Plus", fontsize=10,
                     fontname="helv", color=(0.4, 0.4, 0.4))
    sep_y = title_y + 24
    page.draw_line((40, sep_y), (555, sep_y), color=brand.color_rgb, width=1.5)

    y = sep_y + 10
    lh = 13
    sg = 16

    def title(text, yp):
        page.insert_text((40, yp), text, fontsize=11, fontname="helv", color=brand.color_rgb)
        page.draw_line((40, yp + 4), (555, yp + 4), color=(0.85, 0.85, 0.85), width=0.5)
        return yp + sg

    def fld(label, value, yp, xv=200):
        page.insert_text((50, yp), label, fontsize=9, fontname="helv", color=(0.3, 0.3, 0.3))
        page.insert_text((xv, yp), value, fontsize=9, fontname="helv", color=(0.1, 0.1, 0.1))
        return yp + lh

    # Email block
    page.draw_rect(fitz.Rect(40, y - 5, 555, y + 72), color=(0.95, 0.95, 0.95), fill=(0.97, 0.97, 0.97))
    page.insert_text((50, y + 8), "De : antoine.lefevre@cuisine-bordeaux.fr", fontsize=8, fontname="helv", color=(0.3, 0.3, 0.3))
    page.insert_text((50, y + 18), f"A : {brand.email_souscription}", fontsize=8, fontname="helv", color=(0.3, 0.3, 0.3))
    page.insert_text((50, y + 28), "Date : 25 mars 2026", fontsize=8, fontname="helv", color=(0.3, 0.3, 0.3))
    page.insert_text((50, y + 38), "Objet : Demande de souscription Complementaire Sante — LEFEVRE Antoine", fontsize=8, fontname="helv", color=(0.2, 0.2, 0.2))
    page.insert_text((50, y + 52), "Pieces jointes : carte d'identite, attestation SS, RIB, ordonnance HTA, resultats analyses", fontsize=7, fontname="helv", color=(0.4, 0.4, 0.4))
    page.insert_text((50, y + 62), "\"Je souhaite souscrire a votre offre Equilibre Plus. Chef cuisinier independant, 48 ans.\"", fontsize=7, fontname="helv", color=(0.4, 0.4, 0.4))

    y += 84

    # Informations personnelles
    y = title("INFORMATIONS DU SOUSCRIPTEUR", y)
    y = fld("Nom et prenom :", "LEFEVRE Antoine", y)
    y = fld("Date de naissance :", "12 septembre 1977 (48 ans)", y)
    y = fld("Adresse :", "7 place du Marche, 33000 Bordeaux", y)
    y = fld("Telephone :", "06 87 65 43 21", y)
    y = fld("Email :", "antoine.lefevre@cuisine-bordeaux.fr", y)
    y = fld("N Securite Sociale :", "1 77 09 33 063 234 67", y)
    y = fld("Profession :", "Chef cuisinier independant (TNS)", y)
    y = fld("Regime SS :", "Regime general — CPAM Gironde", y)
    y += 8

    # Couverture demandee
    y = title("COUVERTURE DEMANDEE", y)
    y = fld("Formule :", "Equilibre Plus (hospitalisation + soins courants + optique + dentaire)", y)
    y = fld("Date d'effet :", "01/05/2026", y)
    y = fld("Beneficiaires :", "Souscripteur seul (pas d'ayants droit)", y)
    y = fld("Cotisation estimee :", "127,00 EUR / mois (indication, sous reserve d'acceptation)", y)
    y = fld("Mode de paiement :", "Prelevement mensuel — RIB joint", y)
    y += 8

    # Antecedents medicaux (resume)
    y = title("RESUME MEDICAL (voir questionnaire page 2)", y)
    y = fld("Taille / Poids :", "178 cm / 86 kg (IMC 27.2 — surpoids leger)", y)
    y = fld("Tabac :", "Ancien fumeur (arrete en 2021, 15 paquets/an avant)", y)
    y = fld("Alcool :", "Consommation moderee (professionnel de la restauration)", y)
    y = fld("Pathologie en cours :", "Hypertension arterielle controlee sous traitement", y)
    y = fld("Traitement actuel :", "Amlodipine 5mg — 1 cp/jour depuis 2022", y)
    y = fld("ATCD familiaux :", "Pere : diabete type 2 diagnostique a 55 ans", y)
    y = fld("Hospitalisation :", "Appendicectomie en 2005 (sans complications)", y)
    y = fld("Arret de travail :", "15 jours en 2024 (entorse cheville — accident cuisine)", y)

    # Footer
    page.insert_text((40, 800), f"{brand.name} {brand.region_name} — Service Souscription Sante", fontsize=7, fontname="helv", color=(0.5, 0.5, 0.5))
    page.insert_text((440, 800), "Page 1/3", fontsize=7, fontname="helv", color=(0.5, 0.5, 0.5))

    # ─── Page 2: Questionnaire de sante detaille ───────────────
    page2 = doc.new_page(width=595, height=842)

    if logo_path.exists():
        page2.insert_image(fitz.Rect(*brand.logo_rect), filename=str(logo_path))

    p2_title_y = logo_rect.y1 + 12
    page2.insert_text((40, p2_title_y), "QUESTIONNAIRE DE SANTE", fontsize=16, fontname="helv", color=brand.color_rgb)
    page2.insert_text((40, p2_title_y + 16), "Souscripteur : LEFEVRE Antoine — Ne le 12/09/1977", fontsize=9, fontname="helv", color=(0.4, 0.4, 0.4))
    p2_sep_y = p2_title_y + 24
    page2.draw_line((40, p2_sep_y), (555, p2_sep_y), color=brand.color_rgb, width=1.5)

    y2 = p2_sep_y + 12
    q_num = 0

    def question(num, text, answer, detail, yp):
        page2.insert_text((50, yp), f"Q{num}.", fontsize=9, fontname="helv", color=brand.color_rgb)
        page2.insert_text((75, yp), text, fontsize=9, fontname="helv", color=(0.15, 0.15, 0.15))
        ans_color = (0.8, 0.0, 0.0) if answer == "OUI" else (0.0, 0.5, 0.0)
        page2.insert_text((480, yp), answer, fontsize=9, fontname="helv", color=ans_color)
        yp += 14
        if detail:
            page2.insert_text((75, yp), detail, fontsize=8, fontname="helv", color=(0.4, 0.4, 0.4))
            yp += 14
        return yp + 4

    questions = [
        ("Etes-vous actuellement en arret de travail ou en invalidite ?", "NON", ""),
        ("Suivez-vous actuellement un traitement medical ?", "OUI", "Amlodipine 5mg/jour pour hypertension arterielle depuis janvier 2022."),
        ("Avez-vous ete hospitalise au cours des 10 dernieres annees ?", "NON", "Appendicectomie en 2005 (> 10 ans)."),
        ("Avez-vous ete opere au cours des 5 dernieres annees ?", "NON", ""),
        ("Souffrez-vous de maladie cardiaque ou vasculaire ?", "OUI", "Hypertension arterielle essentielle diagnostiquee en 2021, controlee sous Amlodipine. TA derniere mesure : 135/82 mmHg."),
        ("Souffrez-vous de diabete ?", "NON", "Glycemie a jeun : 1.05 g/L (normale). Pere diabetique type 2."),
        ("Avez-vous des troubles de la vue necessitant correction ?", "OUI", "Presbytie + myopie legere. Port de lunettes progressives depuis 2023."),
        ("Avez-vous des soins dentaires prevus ou en cours ?", "OUI", "Couronne ceramique prevue sur premolaire superieure droite (devis joint si demande)."),
        ("Fumez-vous ou avez-vous fume ?", "OUI", "Ancien fumeur. Arret definitif en mars 2021. Environ 15 paquets-annee."),
        ("Consommez-vous de l'alcool regulierement ?", "NON", "Consommation occasionnelle et moderee dans le cadre professionnel (chef cuisinier)."),
        ("Pratiquez-vous un sport a risque ?", "NON", "Jogging 2x/semaine, natation 1x/semaine."),
        ("Avez-vous des allergies connues ?", "OUI", "Allergie aux acariens (rhinite allergique saisonniere, traitement Cetirizine au besoin)."),
        ("Avez-vous des antecedents familiaux significatifs ?", "OUI", "Pere : diabete type 2 (diagnostique a 55 ans, sous metformine). Mere : en bonne sante."),
        ("Avez-vous subi un bilan de sante complet recemment ?", "OUI", "Bilan complet mars 2026 : voir resultats analyses joints."),
    ]

    for i, (q, a, d) in enumerate(questions, 1):
        y2 = question(i, q, a, d, y2)
        if y2 > 720:
            break

    # Signature
    y2 += 10
    page2.draw_line((40, y2), (555, y2), color=(0.85, 0.85, 0.85), width=0.5)
    y2 += 16
    page2.insert_text((50, y2), "Je certifie sur l'honneur que les reponses ci-dessus sont exactes et completes.", fontsize=8, fontname="helv", color=(0.15, 0.15, 0.15))
    y2 += 14
    page2.insert_text((50, y2), "Fait a Bordeaux, le 25 mars 2026", fontsize=9, fontname="helv", color=(0.15, 0.15, 0.15))
    y2 += 14
    page2.insert_text((50, y2), "Signature : A. Lefevre", fontsize=9, fontname="helv", color=(0.15, 0.15, 0.15))

    # Liste des pieces jointes
    y2 += 30
    page2.draw_rect(fitz.Rect(40, y2 - 5, 555, y2 + 85), color=brand.accent_bg_rgb, fill=brand.accent_bg_rgb)
    page2.insert_text((50, y2 + 8), "PIECES JOINTES A FOURNIR :", fontsize=9, fontname="helv", color=brand.color_rgb)

    pieces = [
        "1. Copie de la carte nationale d'identite (recto/verso)",
        "2. Attestation de droits Securite Sociale (CPAM Gironde)",
        "3. RIB bancaire pour prelevement mensuel",
        "4. Ordonnance medicale en cours (Amlodipine 5mg)",
        "5. Resultats d'analyses sanguines (bilan mars 2026)",
    ]
    yp = y2 + 22
    for p in pieces:
        page2.insert_text((60, yp), p, fontsize=8, fontname="helv", color=(0.2, 0.2, 0.2))
        yp += 12

    # Footer
    page2.insert_text((40, 800), f"{brand.name} {brand.region_name} — Service Souscription Sante", fontsize=7, fontname="helv", color=(0.5, 0.5, 0.5))
    page2.insert_text((40, 812), "Document confidentiel — Usage strictement limite a l'analyse de la demande de souscription.", fontsize=7, fontname="helv", color=(0.5, 0.5, 0.5))
    page2.insert_text((440, 812), "Page 2/3", fontsize=7, fontname="helv", color=(0.5, 0.5, 0.5))

    # ─── Page 3: Resultats d'analyses de laboratoire ───────────
    # Design completement different (style labo francais, pas de logo assureur)
    page3 = doc.new_page(width=595, height=842)
    lab_blue = (0.10, 0.23, 0.36)  # #1a3a5c
    lab_light = (0.93, 0.95, 0.97)
    lab_border = (0.75, 0.80, 0.85)

    # Lab header — dark blue banner
    page3.draw_rect(fitz.Rect(0, 0, 595, 70), color=lab_blue, fill=lab_blue)
    page3.insert_text((30, 25), "LABORATOIRE D'ANALYSES MEDICALES", fontsize=14,
                      fontname="helv", color=(1, 1, 1))
    page3.insert_text((30, 40), "BORDEAUX SUD", fontsize=11,
                      fontname="helv", color=(0.7, 0.8, 0.9))
    page3.insert_text((30, 56), "12 cours Victor Hugo, 33000 Bordeaux — Tel. 05 56 00 12 34",
                      fontsize=7, fontname="helv", color=(0.7, 0.8, 0.9))
    page3.insert_text((380, 25), "FINESS : 330 012 345", fontsize=7,
                      fontname="helv", color=(0.7, 0.8, 0.9))
    page3.insert_text((380, 37), "Directeur : Dr. C. DUBOIS", fontsize=7,
                      fontname="helv", color=(0.7, 0.8, 0.9))
    page3.insert_text((380, 49), "Accreditation COFRAC n 8-1234", fontsize=7,
                      fontname="helv", color=(0.7, 0.8, 0.9))

    # Patient info block
    page3.draw_rect(fitz.Rect(30, 80, 565, 145), color=lab_border, fill=lab_light)
    page3.insert_text((40, 96), "COMPTE RENDU DE RESULTATS", fontsize=10,
                      fontname="helv", color=lab_blue)
    page3.insert_text((40, 112), "Patient :", fontsize=8, fontname="helv", color=(0.4, 0.4, 0.4))
    page3.insert_text((95, 112), "LEFEVRE Antoine", fontsize=9, fontname="helv", color=(0.1, 0.1, 0.1))
    page3.insert_text((250, 112), "Ne le : 12/09/1977  (48 ans,  M)", fontsize=8,
                      fontname="helv", color=(0.3, 0.3, 0.3))
    page3.insert_text((40, 126), "N SS :", fontsize=8, fontname="helv", color=(0.4, 0.4, 0.4))
    page3.insert_text((95, 126), "1 77 09 33 063 234 67", fontsize=8, fontname="helv", color=(0.3, 0.3, 0.3))
    page3.insert_text((250, 126), "Prescripteur : Dr. F. MARTIN (Med. traitant)", fontsize=8,
                      fontname="helv", color=(0.3, 0.3, 0.3))
    page3.insert_text((40, 138), "Date de prelevement : 15/03/2026  a  08h15", fontsize=8,
                      fontname="helv", color=(0.3, 0.3, 0.3))
    page3.insert_text((300, 138), "Date de rendu : 15/03/2026", fontsize=8,
                      fontname="helv", color=(0.3, 0.3, 0.3))

    # Table header
    y3 = 165
    col_analyse = 40
    col_resultat = 280
    col_unite = 370
    col_ref = 440

    page3.draw_rect(fitz.Rect(30, y3 - 5, 565, y3 + 12), color=lab_blue, fill=lab_blue)
    page3.insert_text((col_analyse, y3 + 7), "Analyse", fontsize=8, fontname="helv", color=(1, 1, 1))
    page3.insert_text((col_resultat, y3 + 7), "Resultat", fontsize=8, fontname="helv", color=(1, 1, 1))
    page3.insert_text((col_unite, y3 + 7), "Unite", fontsize=8, fontname="helv", color=(1, 1, 1))
    page3.insert_text((col_ref, y3 + 7), "Valeurs de reference", fontsize=8, fontname="helv", color=(1, 1, 1))
    y3 += 18

    def lab_section(title_text, yp):
        """Draw a section header row."""
        page3.draw_rect(fitz.Rect(30, yp - 2, 565, yp + 12), color=(0.88, 0.91, 0.95), fill=(0.88, 0.91, 0.95))
        page3.insert_text((col_analyse, yp + 8), title_text, fontsize=8, fontname="helv", color=lab_blue)
        return yp + 17

    def lab_row(name, result, unit, ref, yp, alt=False):
        """Draw one result row with optional alternating background."""
        if alt:
            page3.draw_rect(fitz.Rect(30, yp - 2, 565, yp + 11), color=lab_light, fill=lab_light)
        page3.insert_text((col_analyse, yp + 7), name, fontsize=8, fontname="helv", color=(0.15, 0.15, 0.15))
        page3.insert_text((col_resultat, yp + 7), result, fontsize=9, fontname="helv", color=(0.05, 0.05, 0.05))
        page3.insert_text((col_unite, yp + 7), unit, fontsize=8, fontname="helv", color=(0.4, 0.4, 0.4))
        page3.insert_text((col_ref, yp + 7), ref, fontsize=7, fontname="helv", color=(0.4, 0.4, 0.4))
        return yp + 15

    # ── HEMATOLOGIE ──
    y3 = lab_section("HEMATOLOGIE — Numeration Formule Sanguine", y3)
    y3 = lab_row("Hemoglobine", "15,2", "g/dL", "13,0 - 17,5", y3, alt=False)
    y3 = lab_row("Hematocrite", "45,1", "%", "40 - 54", y3, alt=True)
    y3 = lab_row("Globules rouges", "5,10", "T/L", "4,5 - 5,5", y3, alt=False)
    y3 = lab_row("Leucocytes", "6 800", "/mm3", "4 000 - 10 000", y3, alt=True)
    y3 = lab_row("Plaquettes", "245 000", "/mm3", "150 000 - 400 000", y3, alt=False)
    y3 = lab_row("VGM", "88", "fL", "80 - 100", y3, alt=True)
    y3 += 5

    # ── BIOCHIMIE ──
    y3 = lab_section("BIOCHIMIE", y3)
    y3 = lab_row("Glycemie a jeun", "5,8", "mmol/L", "3,9 - 6,1", y3, alt=False)
    y3 = lab_row("Hemoglobine glyquee (HbA1c)", "5,4", "%", "< 6,0", y3, alt=True)
    y3 = lab_row("Creatinine", "82", "umol/L", "62 - 106", y3, alt=False)
    y3 = lab_row("DFG estime (CKD-EPI)", "92", "mL/min/1,73m2", "> 90", y3, alt=True)
    y3 = lab_row("Acide urique", "320", "umol/L", "210 - 420", y3, alt=False)
    y3 += 5

    # ── BILAN LIPIDIQUE ──
    y3 = lab_section("BILAN LIPIDIQUE", y3)
    y3 = lab_row("Cholesterol total", "5,10", "mmol/L", "< 5,2", y3, alt=False)
    y3 = lab_row("LDL cholesterol (calcule)", "3,02", "mmol/L", "< 3,4", y3, alt=True)
    y3 = lab_row("HDL cholesterol", "1,45", "mmol/L", "> 1,0", y3, alt=False)
    y3 = lab_row("Triglycerides", "1,10", "mmol/L", "< 1,7", y3, alt=True)
    y3 = lab_row("Rapport CT/HDL", "3,52", "", "< 4,5", y3, alt=False)
    y3 += 5

    # ── BILAN HEPATIQUE ──
    y3 = lab_section("BILAN HEPATIQUE", y3)
    y3 = lab_row("ASAT (SGOT)", "24", "UI/L", "< 40", y3, alt=False)
    y3 = lab_row("ALAT (SGPT)", "28", "UI/L", "< 41", y3, alt=True)
    y3 = lab_row("Gamma GT (GGT)", "35", "UI/L", "< 60", y3, alt=False)
    y3 = lab_row("Phosphatases alcalines", "68", "UI/L", "40 - 130", y3, alt=True)
    y3 += 5

    # ── THYROIDE ──
    y3 = lab_section("THYROIDE", y3)
    y3 = lab_row("TSH ultrasensible", "2,10", "mUI/L", "0,4 - 4,0", y3, alt=False)
    y3 += 5

    # ── VITESSE DE SEDIMENTATION ──
    y3 = lab_section("INFLAMMATION", y3)
    y3 = lab_row("Vitesse de sedimentation (VS)", "8", "mm/1h", "< 15", y3, alt=False)
    y3 = lab_row("CRP (Proteine C reactive)", "2,1", "mg/L", "< 5,0", y3, alt=True)

    # ── Conclusion ──
    y3 += 20
    page3.draw_line((30, y3), (565, y3), color=lab_border, width=0.5)
    y3 += 14
    page3.insert_text((40, y3), "Conclusion : Bilan sanguin dans les limites de la normale.",
                      fontsize=9, fontname="helv", color=(0.15, 0.15, 0.15))
    y3 += 14
    page3.insert_text((40, y3), "Glycemie et HbA1c normales, bilan lipidique satisfaisant, fonction renale conservee.",
                      fontsize=8, fontname="helv", color=(0.3, 0.3, 0.3))
    y3 += 14
    page3.insert_text((40, y3), "A noter : leger surpoids (IMC 27,2) — surveillance lipidique annuelle recommandee.",
                      fontsize=8, fontname="helv", color=(0.3, 0.3, 0.3))

    # Signature biologiste
    y3 += 30
    page3.insert_text((350, y3), "Dr. C. DUBOIS", fontsize=9, fontname="helv", color=(0.15, 0.15, 0.15))
    y3 += 12
    page3.insert_text((350, y3), "Biologiste responsable", fontsize=8, fontname="helv", color=(0.4, 0.4, 0.4))
    y3 += 12
    page3.insert_text((350, y3), "Laboratoire accredite COFRAC", fontsize=7, fontname="helv", color=(0.4, 0.4, 0.4))

    # Footer
    page3.draw_line((30, 790), (565, 790), color=lab_border, width=0.5)
    page3.insert_text((30, 802), "Laboratoire d'Analyses Medicales Bordeaux Sud — SAS au capital de 50 000 EUR",
                      fontsize=6, fontname="helv", color=(0.5, 0.5, 0.5))
    page3.insert_text((30, 812), "Accreditation COFRAC n 8-1234 — Portee disponible sur www.cofrac.fr",
                      fontsize=6, fontname="helv", color=(0.5, 0.5, 0.5))
    page3.insert_text((480, 812), "Page 3/3", fontsize=7, fontname="helv", color=(0.5, 0.5, 0.5))

    doc.save(str(output_path), deflate=True, garbage=3)
    doc.close()

    print(f"PDF genere : {output_path}")
    print(f"   3 pages, logo {brand.name} (p1-2) + resultats labo (p3)")
    print(f"   Client : Antoine LEFEVRE, 48 ans, chef cuisinier, Bordeaux")
    print(f"   Email  : antoine.lefevre@cuisine-bordeaux.fr")
    print(f"   Pathologies : HTA controlee, ancien fumeur, allergie acariens")
    print(f"   ATCD familiaux : pere diabetique type 2")
    print(f"   Formule : Equilibre Plus (~127 EUR/mois)")
    print(f"   Labo p3 : bilan sanguin normal (glycemie, lipides, hepatique, NFS)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate demo underwriting PDF")
    add_brand_arg(parser)
    args = parser.parse_args()
    brand = get_brand(args.brand)
    generate_underwriting_pdf(brand)
