#!/usr/bin/env python3
"""Generate realistic email exchange threads for demo.

Creates coherent client ↔ insurer email threads as PDFs:
- Initial customer email (informal, stressed)
- Insurer auto-reply (formal, empathetic)
- Customer follow-up (frustrated)
- Insurer resolution (professional)

Usage:
    pip install reportlab
    python scripts/generate_demo_email_threads.py [--brand prevaiq]
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
except ImportError:
    print("Install reportlab: pip install reportlab")
    raise

from _brand_config import get_brand, add_brand_arg, BrandProfile

# Resolved at runtime via get_brand()
BRAND: BrandProfile = None  # type: ignore[assignment]
BRAND_COLOR: HexColor = None  # type: ignore[assignment]

LIGHT_GRAY = HexColor("#f5f5f5")
MEDIUM_GRAY = HexColor("#999999")
DARK_GRAY = HexColor("#333333")
BLUE_LINK = HexColor("#1a73e8")


def _member_id(suffix: str) -> str:
    return f"{BRAND.member_id_prefix}-{suffix}"


def _email_header(c: canvas.Canvas, from_: str, to: str, date: str, subject: str,
                  color: str = "#1a1a1a", cc: str = "", reply: bool = False):
    h = A4[1]
    c.setFillColor(LIGHT_GRAY)
    c.rect(0, h - 55 * mm, A4[0], 55 * mm, fill=True)
    y = h - 12 * mm
    c.setFillColor(DARK_GRAY)
    fields = [("De :", from_), ("À :", to)]
    if cc:
        fields.append(("Cc :", cc))
    fields.append(("Date :", date))
    for label, val in fields:
        c.setFont("Helvetica-Bold", 10)
        c.drawString(15 * mm, y, label)
        c.setFont("Helvetica", 10)
        c.drawString(30 * mm, y, val)
        y -= 5.5 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(15 * mm, y, "Objet :")
    c.setFillColor(HexColor(color))
    c.setFont("Helvetica-Bold", 10)
    prefix = "RE: " if reply else ""
    c.drawString(30 * mm, y, f"{prefix}{subject}")
    return y - 12 * mm


def _write(c: canvas.Canvas, y: float, lines: list[str], font: str = "Helvetica",
           size: int = 10, color=DARK_GRAY) -> float:
    c.setFillColor(color)
    c.setFont(font, size)
    for line in lines:
        if y < 25 * mm:
            c.showPage()
            y = A4[1] - 20 * mm
            c.setFillColor(color)
            c.setFont(font, size)
        c.drawString(15 * mm, y, line)
        y -= 4.5 * mm
    return y


def _brand_banner(c: canvas.Canvas, y: float) -> float:
    c.setFillColor(BRAND_COLOR)
    c.rect(15 * mm, y - 8 * mm, 170 * mm, 10 * mm, fill=True)
    c.setFillColor(white)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20 * mm, y - 5.5 * mm, BRAND.banner_label)
    c.setFont("Helvetica", 8)
    c.drawString(120 * mm, y - 5.5 * mm, BRAND.email_sinistres_hab)
    return y - 14 * mm


# ═══════════════════════════════════════════════════════════════════
# THREAD 1 — Sinistre Habitation DDE (MERTENS LAFFITE)
# ═══════════════════════════════════════════════════════════════════

def thread1_email1(out: Path):
    """Client initial — stressed, informal, cave inondée."""
    fp = out / "thread1-01-client-declaration.pdf"
    c = canvas.Canvas(str(fp), pagesize=A4)
    y = _email_header(c, "olivier.mertens-laffite@example.com", BRAND.email_sinistres_hab,
                       "27 mars 2026 à 08:42",
                       "URGENT — Dégâts des eaux cave — Contrat HAB-33-2021-091745")
    y = _write(c, y, [
        "Bonjour,", "",
        "Je vous contacte en URGENCE suite à d'importants dégâts des eaux survenus dans",
        "ma maison au 42 rue des Vignobles, 33000 Bordeaux.",
        "",
        "Suite à la tempête de cette nuit, ma cave et mon sous-sol sont inondés.",
        "Les dégâts sont importants :",
        "  - Murs : moisissures, salpêtre, fissures visibles",
        "  - Cave : bouteilles de vin de collection détruites (Château Mertens Laffite,",
        "    Nuit Sans Pareil, Grand Cru, millésimes 2015 et 2020)",
        "  - Casiers en bois souillés et endommagés",
        "  - Installation électrique de la cave endommagée",
        "",
        "J'ai fait intervenir un plombier en urgence. Le devis préliminaire est de 1 237,50 € TTC.",
        "Je vous joins ma déclaration de sinistre + 4 photos des dommages.",
        "",
        "Mon contrat : HAB-33-2021-091745 (Formule Confort Plus)",
        f"N° {BRAND.member_term} : SOC-33-789456",
        "",
        "Merci de traiter ce dossier en priorité, la situation empire de jour en jour.",
        "",
        "Cordialement,",
        "Olivier MERTENS LAFFITE",
        "Tél : 06 12 34 56 78",
        "",
        "PJ : declaration-sinistre-habitation.pdf, 4 photos PNG",
    ])
    c.save()
    print(f"  ✓ {fp.name}")


def thread1_email2(out: Path):
    """Insurer auto-response — formal, empathetic, professional."""
    fp = out / f"thread1-02-{BRAND.name.lower()}-accuseReception.pdf"
    c = canvas.Canvas(str(fp), pagesize=A4)
    y = _email_header(c, BRAND.email_sinistres_hab, "olivier.mertens-laffite@example.com",
                       "27 mars 2026 à 09:15",
                       "URGENT — Dégâts des eaux cave — Contrat HAB-33-2021-091745",
                       reply=True)
    y = _brand_banner(c, y)
    y = _write(c, y, [
        "Monsieur MERTENS LAFFITE,", "",
        "Nous accusons réception de votre déclaration de sinistre et comprenons",
        "l'urgence de votre situation. Votre dossier a été enregistré sous la référence :",
        "",
        "   Réf. dossier : SIN-2026-HAB-04837",
        "   Contrat : HAB-33-2021-091745",
        "   Date de sinistre : 27/03/2026",
        "   Nature : Dégâts des eaux — infiltration suite à tempête",
        "",
        "Un conseiller spécialisé prendra en charge votre dossier dans les 24 heures.",
        "",
        "En attendant, nous vous recommandons de :",
        "  1. Conserver toutes les factures d'intervention d'urgence",
        "  2. Ne pas jeter les biens endommagés avant le passage de l'expert",
        "  3. Prendre des photos supplémentaires si les dommages évoluent",
        "  4. Sécuriser l'installation électrique (couper le disjoncteur de la cave)",
        "",
        "Votre contrat Confort Plus inclut la garantie Dégâts des Eaux avec :",
        "  - Franchise applicable : 250 €",
        "  - Plafond biens mobiliers : selon conditions particulières",
        "  - Garantie recherche de fuite : incluse",
        "",
        "Nous vous tiendrons informé de l'avancement de votre dossier.",
        "",
        "Cordialement,",
        f"Service Sinistres Habitation — {BRAND.name}",
        f"{BRAND.phone_general} (appel non surtaxé)",
        "",
        "Ce message est généré automatiquement. Ne pas répondre directement.",
    ])
    c.save()
    print(f"  ✓ {fp.name}")


def thread1_email3(out: Path):
    """Client follow-up — frustrated, 10 days later."""
    fp = out / "thread1-03-client-relance.pdf"
    c = canvas.Canvas(str(fp), pagesize=A4)
    y = _email_header(c, "olivier.mertens-laffite@example.com", BRAND.email_sinistres_hab,
                       "5 avril 2026 à 14:18",
                       "URGENT — Dégâts des eaux cave — Contrat HAB-33-2021-091745",
                       color="#cc0000", reply=True)
    y = _write(c, y, [
        "Bonjour,", "",
        "Je me permets de vous relancer car je n'ai reçu AUCUNE réponse depuis ma",
        "déclaration du 27 mars dernier (réf. SIN-2026-HAB-04837).",
        "",
        "La situation a considérablement empiré :",
        "  - Les moisissures se sont étendues sur 3 murs de la cave",
        "  - Odeur d'humidité permanente au rez-de-chaussée",
        "  - Le plombier est revenu une 2ème fois (fuites résiduelles)",
        "  - L'électricien a dû intervenir pour sécuriser le tableau de la cave",
        "",
        "FACTURES :",
        "  - Devis initial plombier : 1 237,50 € TTC",
        "  - Facture finale plombier : 1 556,50 € TTC (travaux supplémentaires)",
        "  - Facture électricien : 1 171,50 € TTC (mise en sécurité)",
        "  - TOTAL : 2 728,00 € TTC — écart devis/facture : +25%",
        "",
        f"Je vous ai appelé 3 fois au {BRAND.phone_general} sans succès.",
        f"Je suis {BRAND.member_term} {BRAND.name} depuis 12 ans, premier sinistre.",
        "Je ne comprends pas ce silence.",
        "",
        "Merci de me confirmer la prise en charge dans les PLUS BREFS DÉLAIS.",
        "",
        "Cordialement,",
        "Olivier MERTENS LAFFITE",
        "",
        "PJ : facture-plombier.pdf, facture-electricien.pdf, devis-initial.pdf",
    ])
    c.save()
    print(f"  ✓ {fp.name}")


def thread1_email4(out: Path):
    """Insurer response — apology, expert mandate, timeline."""
    fp = out / f"thread1-04-{BRAND.name.lower()}-priseEnCharge.pdf"
    c = canvas.Canvas(str(fp), pagesize=A4)
    y = _email_header(c, BRAND.advisor_email_1, "olivier.mertens-laffite@example.com",
                       "7 avril 2026 à 10:30",
                       "URGENT — Dégâts des eaux cave — Contrat HAB-33-2021-091745",
                       reply=True, cc=BRAND.email_sinistres_hab)
    y = _brand_banner(c, y)
    y = _write(c, y, [
        "Monsieur MERTENS LAFFITE,", "",
        "Je suis Sophie DUVAL, votre conseillère dédiée pour le dossier SIN-2026-HAB-04837.",
        "Je vous prie d'accepter nos excuses pour le délai de réponse.",
        "",
        "Votre dossier a été analysé et voici les prochaines étapes :",
        "",
        "1. EXPERTISE :",
        "   Un expert mandaté (Cabinet SARETEC) vous contactera sous 48h pour",
        "   fixer un rendez-vous de constatation. Réf. expert : EXP-2026-33-1247",
        "",
        "2. PRISE EN CHARGE PROVISOIRE :",
        "   Au vu de l'urgence, un acompte de 70% sur le devis initial est autorisé :",
        "   Montant acompte : 866,25 € (70% de 1 237,50 €)",
        "   Versement sous 5 jours ouvrés sur votre compte bancaire.",
        "",
        "3. FACTURES COMPLÉMENTAIRES :",
        "   Les factures plombier (1 556,50 €) et électricien (1 171,50 €) seront",
        "   examinées par l'expert lors de sa visite. L'écart devis/facture (+25%)",
        "   est noté et sera justifié par le prestataire.",
        "",
        "4. VÉRIFICATION CAT-NAT :",
        "   Nous vérifions si un arrêté de catastrophe naturelle a été publié pour",
        "   votre commune (Bordeaux) à la date du sinistre. Si confirmé, le régime",
        "   Cat-Nat s'appliquera (franchise légale de 380 €).",
        "",
        "Je reste votre interlocutrice unique. N'hésitez pas à me contacter",
        "directement au 05 56 44 78 92.",
        "",
        "Bien cordialement,",
        "Sophie DUVAL — Conseillère Indemnisation",
        f"{BRAND.name} {BRAND.region_name}",
        f"{BRAND.advisor_email_1} | 05 56 44 78 92",
    ])
    c.save()
    print(f"  ✓ {fp.name}")


# ═══════════════════════════════════════════════════════════════════
# THREAD 2 — Sinistre Auto (accident + attestation scolaire)
# ═══════════════════════════════════════════════════════════════════

def thread2_email1(out: Path):
    """Client — informal, accident + attestation scolaire, with photo."""
    fp = out / "thread2-01-client-accident-auto.pdf"
    c = canvas.Canvas(str(fp), pagesize=A4)
    y = _email_header(c, "olivier.mertens-laffite@example.com", BRAND.email_sinistres_auto,
                       "29 janvier 2026 à 11:38",
                       "PAPIER URGENT et la voiture !!!")
    y = _write(c, y, [
        "Slt,", "",
        "Ta vu la photo là ?? C'est la cata totale... regarde :",
        "[Photo : crash-voiture.jpg — portière enfoncée, pare-choc arraché]",
        "",
        "J'ai glissé, ça a tapé direct, la portière elle s'ouvre même plus pfff.",
        "Bref je suis en galère avec la dépanneuse là.",
        "",
        "Sinon pour le truc de l'école, l'attestation scolaire tu peux me faire le PDF stp ?",
        "C'est pour le dossier parce que sans voiture je peux pas aller au secrétariat",
        "chercher la feuille. Il me le faut vite en format fichier pour l'envoyer.",
        "",
        "Dis-moi si tu es là ou si je dois appeler l'assurance d'abord, je comprends rien.",
        "",
        "Merci de faire vite.",
        "",
        "A+",
        "",
        "Mertens Olivier",
        "06.45.26.24.42",
        "olivier.mertens-laffite@example.com",
        "",
        "PJ : crash-1308575_1280.jpg (428 Ko)",
    ])
    c.save()
    print(f"  ✓ {fp.name}")


def thread2_email2(out: Path):
    """Insurer response — 2 subjects handled separately."""
    fp = out / f"thread2-02-{BRAND.name.lower()}-reponse-auto.pdf"
    c = canvas.Canvas(str(fp), pagesize=A4)
    y = _email_header(c, BRAND.email_sinistres_auto, "olivier.mertens-laffite@example.com",
                       "29 janvier 2026 à 14:05",
                       "PAPIER URGENT et la voiture !!!",
                       reply=True)
    y = _brand_banner(c, y)
    y = _write(c, y, [
        "Monsieur MERTENS,", "",
        "Nous avons bien reçu votre message. Voici la prise en charge de vos deux demandes :",
        "",
        "═══ 1. SINISTRE AUTO ═══",
        "",
        "Votre déclaration d'accident a été enregistrée :",
        "  Réf. sinistre : SIN-2026-AUTO-00142",
        "  Véhicule : à préciser (merci de nous communiquer l'immatriculation)",
        "  Date : 29/01/2026",
        "",
        "Actions immédiates :",
        "  ✓ Dépanneuse prise en charge par votre contrat (assistance 24h)",
        "  → Merci de remplir le constat amiable joint et de nous le retourner",
        "  → Un expert sera mandaté sous 48h pour évaluer les dommages",
        "",
        "Documents nécessaires :",
        "  - Constat amiable signé",
        "  - Photos complémentaires (intérieur véhicule, compteur kilométrique)",
        "  - Copie du permis de conduire",
        "",
        "═══ 2. ATTESTATION SCOLAIRE ═══",
        "",
        "Votre attestation d'assurance scolaire est disponible en téléchargement",
        f"sur votre espace client : {BRAND.espace_client_url}",
        "",
        "Si vous n'avez pas accès, le document est joint à cet email en PDF.",
        "",
        f"N'hésitez pas à nous contacter au {BRAND.phone_general}.",
        "",
        "Cordialement,",
        f"Service Sinistres Auto — {BRAND.name}",
        "",
        "PJ : attestation-scolaire-2026.pdf, constat-amiable-vierge.pdf",
    ])
    c.save()
    print(f"  ✓ {fp.name}")


# ═══════════════════════════════════════════════════════════════════
# THREAD 3 — Sinistre Habitation Grêle (véranda)
# ═══════════════════════════════════════════════════════════════════

def thread3_email1(out: Path):
    """Client — grêle sur véranda, impatient."""
    fp = out / "thread3-01-client-grele-veranda.pdf"
    c = canvas.Canvas(str(fp), pagesize=A4)
    y = _email_header(c, "louis.moreau@example.com", BRAND.email_sinistres_hab,
                       "12 avril 2026 à 16:45",
                       "Dommages grêle sur véranda — Contrat HAB-44-2023-056789")
    y = _write(c, y, [
        "Bonjour,", "",
        "Je vous écris concernant un problème avec ma véranda. Il y a eu de gros grêlons",
        "la semaine dernière, et l'impact est bien visible. Les panneaux en polycarbonate",
        "sont fissurés sur 3 surfaces, et un des profilés aluminium est tordu.",
        "",
        "J'ai contacté un vitrier qui m'a donné un devis de 2 340 € TTC pour le",
        "remplacement des panneaux + remise en forme du profilé.",
        "",
        "Je vous avais déjà contacté il y a 5 jours mais sans réponse.",
        "",
        "Mon contrat : HAB-44-2023-056789 (Formule Confort)",
        "Adresse du sinistre : 28 avenue des Tilleuls, 44000 Nantes",
        "",
        "Merci de traiter cette demande rapidement, l'hiver approche et la véranda",
        "n'est plus étanche.",
        "",
        "Cordialement,",
        "Louis MOREAU",
        "07 71 27 54 33",
        "",
        "PJ : photos-grele-veranda.zip (3 photos), devis-vitrier.pdf",
    ])
    c.save()
    print(f"  ✓ {fp.name}")


def thread3_email2(out: Path):
    """Insurer response — Cat-Nat check, expert dispatch."""
    fp = out / f"thread3-02-{BRAND.name.lower()}-reponse-grele.pdf"
    c = canvas.Canvas(str(fp), pagesize=A4)
    y = _email_header(c, BRAND.advisor_email_2, "louis.moreau@example.com",
                       "14 avril 2026 à 09:20",
                       "Dommages grêle sur véranda — Contrat HAB-44-2023-056789",
                       reply=True)
    y = _brand_banner(c, y)
    y = _write(c, y, [
        "Monsieur MOREAU,", "",
        "Votre déclaration de sinistre a été enregistrée sous la référence :",
        "   Réf. : SIN-2026-HAB-07821",
        "",
        "ANALYSE PRÉLIMINAIRE :",
        "  ✓ Votre contrat Confort couvre les dommages liés à la grêle",
        "  ✓ Franchise applicable : 300 € (événement climatique)",
        "  ✓ Le devis de 2 340 € est dans la fourchette des interventions similaires",
        "",
        "VÉRIFICATION EN COURS :",
        "  → Nous vérifions si un arrêté de catastrophe naturelle / événement climatique",
        "    a été publié pour Nantes (44) à la date du sinistre.",
        "  → Si un arrêté Cat-Nat est confirmé, la franchise légale de 380 € s'appliquera",
        "    à la place de la franchise contractuelle.",
        "",
        "PROCHAINES ÉTAPES :",
        "  1. Un expert passera dans les 5 jours ouvrés pour constater les dommages",
        "  2. Vous recevrez un accord de prise en charge sous 10 jours",
        "  3. Vous pourrez alors engager les travaux avec le vitrier de votre choix",
        "",
        "IMPORTANT : ne commencez pas les travaux avant l'accord écrit de notre part.",
        "",
        "Je suis votre interlocuteur dédié pour ce dossier.",
        "",
        "Bien cordialement,",
        "Marc LEMAITRE — Conseiller Indemnisation",
        f"{BRAND.name} {BRAND.region_name_2}",
        f"{BRAND.advisor_email_2} | 02 51 82 34 56",
    ])
    c.save()
    print(f"  ✓ {fp.name}")


# ═══════════════════════════════════════════════════════════════════
# THREAD 4 — Sinistre Santé (soins dentaires urgents)
# ═══════════════════════════════════════════════════════════════════

def thread4_email1(out: Path):
    """Client — dental emergency, worried about coverage."""
    fp = out / "thread4-01-client-dentaire.pdf"
    c = canvas.Canvas(str(fp), pagesize=A4)
    y = _email_header(c, "antoine.laurent@example.com", BRAND.email_sante,
                       "10 avril 2026 à 17:22",
                       f"Besoin d'info urgente — soins dentaires — N° adhérent {_member_id('2024-SA-4521')}")
    y = _write(c, y, [
        "Bonjour,", "",
        "J'ai un problème dentaire urgent et j'ai besoin de savoir rapidement",
        f"si ma complémentaire santé {BRAND.name} couvre les soins suivants :",
        "",
        "  - Consultation d'urgence chez le dentiste",
        "  - Radio panoramique",
        "  - Possible extraction + implant",
        "",
        "Mon dentiste m'a donné un devis de 2 800 € pour l'ensemble du traitement.",
        "Le reste à charge après Sécu serait d'environ 1 900 €.",
        "",
        "Ma formule : Complémentaire Santé — Offre Équilibre Plus",
        f"N° adhérent : {_member_id('2024-SA-4521')}",
        "",
        "J'ai déjà envoyé une demande il y a 3 jours, sans retour.",
        "C'est vraiment urgent car j'ai mal et le dentiste peut me prendre jeudi.",
        "",
        "Merci de votre retour rapide,",
        "Antoine LAURENT",
        "07 00 94 21 02",
    ])
    c.save()
    print(f"  ✓ {fp.name}")


def thread4_email2(out: Path):
    """Insurer response — coverage details, devis préalable."""
    fp = out / f"thread4-02-{BRAND.name.lower()}-reponse-dentaire.pdf"
    c = canvas.Canvas(str(fp), pagesize=A4)
    y = _email_header(c, BRAND.email_sante, "antoine.laurent@example.com",
                       "11 avril 2026 à 08:45",
                       f"Besoin d'info urgente — soins dentaires — N° adhérent {_member_id('2024-SA-4521')}",
                       reply=True)
    y = _brand_banner(c, y)
    y = _write(c, y, [
        "Monsieur LAURENT,", "",
        "Suite à votre demande, voici les informations sur vos garanties dentaires :",
        "",
        "VOTRE COUVERTURE (Offre Équilibre Plus) :",
        "  ┌─────────────────────────────────────────────────────────────┐",
        "  │ Soins dentaires courants      : 100% BR (base remboursement) │",
        "  │ Prothèses dentaires           : 300% BR                      │",
        "  │ Implantologie                 : forfait 400 €/an             │",
        "  │ Radio panoramique             : prise en charge intégrale     │",
        "  └─────────────────────────────────────────────────────────────┘",
        "",
        "ESTIMATION POUR VOTRE CAS :",
        "  Devis total : 2 800 €",
        "  Part Sécurité Sociale : ~900 €",
        f"  Part {BRAND.name} estimée : ~1 500 €",
        "  Reste à charge estimé : ~400 € (vs 1 900 € sans complémentaire)",
        "",
        "PROCÉDURE DEVIS PRÉALABLE :",
        "  Pour l'implant, un devis préalable est OBLIGATOIRE. Merci de :",
        "  1. Demander un devis détaillé à votre dentiste (formulaire S3346)",
        "  2. Nous l'envoyer via votre espace client ou par courrier",
        "  3. Nous vous confirmerons la prise en charge sous 48h",
        "",
        "  → Pour la consultation + radio, vous pouvez engager les soins",
        "    immédiatement, la prise en charge est automatique avec votre carte",
        f"    de tiers payant {BRAND.name}.",
        "",
        f"N'hésitez pas à nous rappeler au {BRAND.phone_sante} (service santé).",
        "",
        "Bien cordialement,",
        f"Service Santé — {BRAND.name}",
    ])
    c.save()
    print(f"  ✓ {fp.name}")


def main():
    global BRAND, BRAND_COLOR
    parser = argparse.ArgumentParser(description="Generate demo email threads")
    parser.add_argument("--output-dir", default=None)
    add_brand_arg(parser)
    args = parser.parse_args()

    BRAND = get_brand(args.brand)
    BRAND_COLOR = HexColor(BRAND.color_hex)

    out = Path(args.output_dir or f"{BRAND.demo_output_dir}/emails")
    out.mkdir(parents=True, exist_ok=True)

    print(f"Generating email exchange threads ({BRAND.name})...\n")

    print("─── Thread 1 : Sinistre Habitation DDE (MERTENS LAFFITE) ───")
    thread1_email1(out)
    thread1_email2(out)
    thread1_email3(out)
    thread1_email4(out)

    print("\n─── Thread 2 : Sinistre Auto + Attestation scolaire ───")
    thread2_email1(out)
    thread2_email2(out)

    print("\n─── Thread 3 : Sinistre Grêle Véranda ───")
    thread3_email1(out)
    thread3_email2(out)

    print("\n─── Thread 4 : Sinistre Santé Dentaire ───")
    thread4_email1(out)
    thread4_email2(out)

    print(f"\n✅ {10} emails generated in {out}/")
    print("\n📋 Threads de démo :")
    print("  Thread 1 (Habitation DDE) : 4 emails — déclaration → accusé → relance → prise en charge")
    print("  Thread 2 (Auto + scolaire) : 2 emails — accident + attestation → double réponse")
    print("  Thread 3 (Grêle véranda) : 2 emails — déclaration → vérification Cat-Nat")
    print("  Thread 4 (Santé dentaire) : 2 emails — urgence → couverture détaillée")


if __name__ == "__main__":
    main()
