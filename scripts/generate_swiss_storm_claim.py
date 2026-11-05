"""Generate the Swiss hailstorm demo claim: Winterthur chocolate maker, Friday 28.08.2026.

The business, people, policy, references and amounts are fictitious; only the municipality
(Winterthur) and the storm date are real. Identity checks (see ``IDENTITY_CHECKS``) make sure
no real company, street, UID or phone number is used. Writes:

* ``assets/pdf/prevaiq/prevaiq-ch-avb-kmu-geschaeftsversicherung-2026.pdf`` — fictitious Swiss
  policy conditions (German), indexed by the RAG as ``property_casualty_ch``;
* ``assets/demo-prevaiq/property-claims/swiss-chocolate-storm/`` — claim form (German), the
  first notice e-mail (German) and the consolidated estimate e-mail (English) as ``.eml`` and
  print PDF, six photos and ``manifest.json`` (provenance and scenario facts).

Usage::

    python scripts/generate_swiss_storm_claim.py            # documents and manifest
    python scripts/generate_swiss_storm_claim.py --photos   # also (re)generate the photos
    python scripts/generate_swiss_storm_claim.py --refine IMG_20260828_104355.jpg  # edit one photo
    python scripts/index_pdf_policies.py --file assets/pdf/prevaiq/prevaiq-ch-avb-kmu-geschaeftsversicherung-2026.pdf --force

Photos use a MAI-Image-2.6 deployment through Microsoft Entra ID (no key):
``MAI_IMAGE_ENDPOINT`` and ``MAI_IMAGE_DEPLOYMENT`` override the defaults below.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass
from email import policy
from email.message import EmailMessage
from pathlib import Path

import fitz

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_policy_pdfs import CSS, draw_logo, section, table  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SCENARIO_DIR = ROOT / "assets" / "demo-prevaiq" / "property-claims" / "swiss-chocolate-storm"
AVB_PATH = (
    ROOT / "assets" / "pdf" / "prevaiq" / "prevaiq-ch-avb-kmu-geschaeftsversicherung-2026.pdf"
)

# ── Fictitious identity (checked 05.11.2026, see IDENTITY_CHECKS) ────────────────
FIRM = "Schoggimanufaktur Eulachblick GmbH"
UID = "CHE-482.135.757"
STREET = "Kakaogasse 7"
TOWN = "8400 Winterthur"
PHONE = "+41 52 048 21 37"
IBAN = "CH93 0076 2011 6238 5295 7"
DOMAIN = "eulachblick-schoggi.example"
OWNER = "Andrea Keller"
OWNER_EMAIL = f"a.keller@{DOMAIN}"
PARTNER = "Daniel Hartley"
PARTNER_EMAIL = f"d.hartley@{DOMAIN}"
INSURER = "PrevaIQ Versicherungen (Schweiz) AG"
INSURER_EMAIL = "schaden@prevaiq.example"
POLICY = "PIQ-CH-KMU-2026-048213"
CLAIM_NO = "PIQ-S-2026-082814"
GVZ_REF = "2026-08-4471"
AVB = "AVB KMU-Geschäftsversicherung, Ausgabe 01/2026"

IDENTITY_CHECKS = {
    "company": "Zefix (incl. deleted firms): no result for 'Schoggimanufaktur Eulachblick' or "
    "'Eulachblick'; no exact web match",
    "uid": "eCH-0097 mod-11 check digit of 48213575 would be 10, so no valid UID has this "
    "number; Zefix: no result",
    "street": "geo.admin.ch: no street 'Kakaogasse' anywhere in Switzerland",
    "phone": "search.ch: no directory entry for 052 048 21 37",
    "iban": "Example IBAN of the SWIFT IBAN registry for Switzerland",
    "email": "Reserved .example domains (RFC 2606)",
}

# ── Scenario facts ───────────────────────────────────────────────────────────
DAMAGES = [
    # (German label, English label, CHF, German note)
    (
        "Gebäude: Schaufensterverglasung, Oblicht Atelier, Markise, Fassadenbleche",
        "Building items: shop window glazing, workshop skylight, awning and facade panels",
        184_000,
        f"Auch der GVZ gemeldet (Nr. {GVZ_REF}); 2019 als Mieterausbau erneuert",
    ),
    (
        "Warenvorrat Laden und Lager (Pralinés, Tafeln, Saisonware, Verpackungen)",
        "Stock in the shop and storeroom (pralines, bars, autumn and Christmas stock, packaging)",
        312_500,
        "Inventar per 31.07.2026 und Zugänge August",
    ),
    (
        "Kühlgut im Kühlraum (Frischrahm-Truffes, Ganache, Halbfabrikate)",
        "Refrigerated goods in the cold room",
        96_400,
        "Verdorben nach Stromunterbruch 28.08., 11:30 bis 29.08., 15:00",
    ),
    (
        "Produktionsanlagen (2 Temperiermaschinen, Überziehmaschine, Kühltunnel, Giessanlage)",
        "Production equipment (two tempering machines, enrobing machine, cooling tunnel, "
        "moulding line)",
        486_000,
        "Wasser- und Hagelschaden, Kurzschluss",
    ),
    (
        "Ladeneinrichtung (Verkaufstheke, Vitrinen, Kühlvitrine, Beleuchtung, Kassensystem)",
        "Shop fittings (counter, display cases, chilled display, lighting, till system)",
        168_000,
        "Glas- und Wasserschäden",
    ),
    (
        "Betriebsunterbruch: Ertragsausfall September bis Dezember 2026 (Weihnachtsgeschäft)",
        "Business interruption, September to December 2026 (Christmas season)",
        398_000,
        "Schätzung auf Basis der Vorjahre",
    ),
    (
        "Aufräumung, Entsorgung, Notverglasung, Trocknung",
        "Clean-up, disposal, emergency glazing and drying",
        52_500,
        "Rechnungen folgen",
    ),
]
TOTAL = sum(amount for *_, amount, _ in DAMAGES)
assert TOTAL == 1_697_400

TIMELINE = [
    (
        "26.08.2026 18:34",
        "Photo of the fully stocked shop window (stock evidence, before the storm)",
    ),
    (
        "28.08.2026 09:50-10:20",
        "Hailstorm (hail up to about 5 cm, gusts); water ingress, short circuit, main fuse tripped",
    ),
    ("28.08.2026 10:41-11:26", "Four damage photos"),
    ("28.08.2026 11:30", "Emergency electrician cuts the power for safety"),
    ("28.08.2026 14:00", "Emergency glazing"),
    ("28.08.2026 16:52", "E-mail 1 (German): first notice of loss"),
    ("29.08.2026 15:00", "Power restored; cold room at 23.8 °C (photo 15:04)"),
    ("01.09.2026", "Claim form signed; e-mail 2 (English): consolidated estimate"),
    ("04.09.2026 09:00", "Loss adjuster's visit"),
]
ATTENTION_POINTS = [
    "Building items (CHF 184,000) are insured by the cantonal building insurer GVZ in Zurich "
    "and were also reported there: risk of double compensation; tenant improvements are not "
    "part of the policy (AVB B1.3, A6).",
    "Refrigerated goods (CHF 96,400) were lost through the power cut; the Kühlgut extension "
    "is not in the policy, even when an insured event caused the outage (AVB B4.1).",
    "One photo predates the storm (26.08.2026, 18:34): legitimate stock evidence that must be "
    "checked, not damage evidence (AVB A4.3).",
]

# ── Photos (MAI-Image-2.6) ───────────────────────────────────────────────────
MAI_MODEL = "MAI-Image-2.6"
MAI_VERSION = "2026-07-31"
MAI_SCOPE = "https://cognitiveservices.azure.com/.default"
PHOTO_SIZE = (1728, 1296)  # 4:3, within the 2,359,296-pixel limit
STYLE = (
    " Realistic smartphone photo, natural light, slightly imperfect framing. No people, no "
    "brand logos, no watermark, no text overlay."
)


@dataclass(frozen=True)
class Photo:
    name: str
    taken: str
    caption: str  # German, as listed in the claim form
    prompt: str
    reference: str | None = None  # earlier photo edited to keep the same shop
    refinements: tuple[str, ...] = ()  # edits applied after generation to remove AI artefacts


PHOTOS = [
    Photo(
        "IMG_20260826_183447.jpg",
        "26.08.2026 18:34",
        "Schaufenster am Mittwochabend (Bestand)",
        "Exterior of a small traditional artisan chocolate shop in the old town of Winterthur, "
        "Switzerland, on a late-summer evening around 6:30 pm. Ground floor of a historic "
        "three-storey building with a light ochre plastered facade, one large shop window full "
        "of neatly arranged pralines, truffles, chocolate bars and autumn gift boxes, a dark "
        "green fabric awning, a small hanging wooden sign reading 'Eulachblick' in simple gold "
        "letters, a wooden entrance door with a glass panel. Cobblestone pedestrian lane, warm "
        "golden light, two potted plants." + STYLE,
    ),
    Photo(
        "IMG_20260828_104112.jpg",
        "28.08.2026 10:41",
        "Fassade nach dem Hagelzug",
        "The same chocolate shop and building as in the reference photo, now photographed on a "
        "grey morning twenty minutes after a violent hailstorm: the large shop window is "
        "shattered with a big hole and spider-web cracks, glass shards on the window display "
        "and the pavement, the green awning is torn and hangs down, hundreds of white "
        "hailstones up to 5 cm lie on the wet cobblestones together with torn leaves, the "
        "facade is wet. Keep the same building, facade colour, awning colour, door and hanging "
        "sign." + STYLE,
        reference="IMG_20260826_183447.jpg",
    ),
    Photo(
        "IMG_20260828_104355.jpg",
        "28.08.2026 10:43",
        "Hagelkörner neben Meterstab (bis ca. 5 cm)",
        "Close-up from above of large hailstones, the biggest about 5 cm in diameter, lying on "
        "wet grey cobblestones next to a yellow wooden folding ruler with centimetre markings "
        "for scale, smaller hailstones melting, a few glass shards nearby, overcast daylight."
        + STYLE,
        refinements=(
            "Edit this photo: keep the wet cobblestones, the hailstones, the glass shards and "
            "the camera angle. Replace the folding ruler with a clean yellow wooden folding "
            "ruler whose centimetre graduations are numbered 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 in "
            "increasing order along one edge only, with no other numbers. Make the largest "
            "hailstone about 5 cm across measured against that ruler, and keep the other "
            "hailstones between 2 and 4 cm.",
            "Edit this photo: on the folding ruler keep the numbers 1 to 10 along the left "
            "edge and remove every number from the right edge, leaving only plain tick marks "
            "there. Keep everything else unchanged.",
        ),
    ),
    Photo(
        "IMG_20260828_105207.jpg",
        "28.08.2026 10:52",
        "Verkaufsraum mit Glasscherben und Wasser",
        "Interior of a small traditional Swiss chocolate shop right after a hailstorm: the shop "
        "window is broken, glass shards cover the wooden sales counter and a glass display case "
        "of pralines and truffles wet with rain water, puddles on the tiled floor, a fallen "
        "shelf of chocolate gift boxes with soaked packaging, grey daylight through the broken "
        "window, warm wooden fittings with dark green accents, lights off." + STYLE,
        refinements=(
            "Edit this photo: keep the shop interior, the broken window, the glass shards, the "
            "wet floor, the fallen gift boxes and the praline display unchanged. Make the "
            "window frame dark brown wood. Through the broken window show only a narrow wet "
            "cobblestone old-town lane with historic three-storey houses in ochre and white "
            "plaster on the opposite side under a grey overcast sky; remove the mountains, "
            "the flag, the traffic signs and the wide road.",
        ),
    ),
    Photo(
        "IMG_20260828_112604.jpg",
        "28.08.2026 11:26",
        "Atelier: zerbrochenes Oblicht, Wasser auf der Temperiermaschine",
        "Small artisan chocolate workshop behind a shop: a broken glass skylight in the ceiling "
        "with jagged glass, partly covered by a blue tarpaulin, rain water dripping onto a "
        "stainless-steel chocolate tempering machine filled with chocolate, water pooling on "
        "the stainless worktable and the floor, an enrobing machine and a small cooling tunnel "
        "in the background, lights off, only grey daylight from the skylight." + STYLE,
    ),
    Photo(
        "IMG_20260829_150418.jpg",
        "29.08.2026 15:04",
        "Kühlraum nach dem Stromunterbruch (23,8 °C)",
        "Inside the small walk-in cold room of a chocolate workshop the day after a long power "
        "cut: the cooling unit is off, a wall-mounted digital thermometer clearly shows "
        "23.8 °C, stacked cardboard boxes of seasonal chocolate products are soaked and "
        "sagging, condensation on the metal shelves, open trays of softened truffles, dim "
        "light from the open door." + STYLE,
    ),
]
EMAIL_1_PHOTOS = [photo.name for photo in PHOTOS if photo.taken.startswith("28.08.2026")]
FOOTER_DE = (
    "Fiktives Dokument — Demonstration PrevaIQ. Firma, Personen, Police und Beträge sind erfunden."
)
FOOTER_EN = "Fictitious document — PrevaIQ demonstration. Business, people, policy and amounts are invented."


def chf(amount: float) -> str:
    """Swiss notation: CHF 1'697'400.00."""
    return "CHF " + f"{amount:,.2f}".replace(",", "'")


def chf_en(amount: float) -> str:
    return f"CHF {amount:,.2f}"


def ziff(number: str, title: str, body: str) -> str:
    return f"<h3>Ziff. {number} — {title}</h3>{body}"


def paragraphs(*texts: str) -> str:
    return "".join(f"<p>{text}</p>" for text in texts)


# ── Swiss policy conditions (AVB) ────────────────────────────────────────────


def avb_html() -> str:
    deductibles = table(
        ["Gefahr", "Selbstbehalt pro Ereignis"],
        [
            [
                "Elementarschäden an Fahrhabe (Waren, Einrichtungen, Maschinen)",
                "10 % der Entschädigung, mindestens CHF 2'500, höchstens CHF 50'000 "
                "(AVO Art. 175 Abs. 1 lit. c)",
            ],
            ["Feuer, Wasser, Diebstahl, Glasbruch", "CHF 1'000"],
            ["Betriebsunterbruch", "Karenzfrist 24 Stunden"],
        ],
    )
    return (
        section(
            "A. GEMEINSAME BESTIMMUNGEN",
            ziff(
                "A1",
                "Vertragsgrundlagen",
                paragraphs(
                    f"Der Vertrag besteht aus der Police, diesen Allgemeinen Versicherungsbedingungen "
                    f"({AVB}) und allfälligen Zusatzbedingungen. Ergänzend gilt das Bundesgesetz über "
                    "den Versicherungsvertrag (VVG)."
                ),
            )
            + ziff(
                "A2",
                "Versicherte Sachen und Versicherungsort",
                paragraphs(
                    "Versichert ist die in der Police aufgeführte Fahrhabe des Betriebs (Waren, "
                    "Einrichtungen, Maschinen) am Versicherungsort. Mieterausbauten sind nur "
                    "versichert, wenn sie in der Police ausdrücklich aufgeführt sind."
                ),
            )
            + ziff(
                "A3",
                "Versicherungswert und Unterversicherung",
                paragraphs(
                    "A3.1 Einrichtungen und Maschinen sind zum Neuwert versichert, Waren zum "
                    "Wiederbeschaffungspreis oder zu den Herstellungskosten.",
                    "A3.2 Ist die Versicherungssumme niedriger als der Ersatzwert (Unterversicherung), "
                    "wird der Schaden nur im Verhältnis der Versicherungssumme zum Ersatzwert "
                    "entschädigt (VVG Art. 69 Abs. 2).",
                ),
            )
            + ziff(
                "A4",
                "Obliegenheiten im Schadenfall",
                paragraphs(
                    "A4.1 Anzeige: Der Schaden ist unverzüglich zu melden (VVG Art. 38). Gebäudeschäden "
                    "sind zudem der zuständigen kantonalen Gebäudeversicherung zu melden.",
                    "A4.2 Schadenminderung: Die versicherte Person sorgt nach Möglichkeit für die "
                    "Minderung des Schadens (VVG Art. 61). Angemessene Rettungskosten sind versichert.",
                    "A4.3 Belege: Auf Verlangen sind eine detaillierte Schadenaufstellung, Fotos, "
                    "Inventar- und Buchhaltungsunterlagen einzureichen. Fotos aus der Zeit vor dem "
                    "Ereignis können als Bestandesnachweis dienen; Echtheit und Datum werden geprüft.",
                    "A4.4 Veränderungsverbot: Bis zur Besichtigung darf die Schadenstelle nur zur "
                    "Schadenminderung verändert werden.",
                    "A4.5 Bei schuldhafter Verletzung dieser Obliegenheiten kann die Entschädigung um "
                    "den dadurch entstandenen Mehrschaden gekürzt werden.",
                ),
            )
            + ziff("A5", "Selbstbehalte", deductibles)
            + ziff(
                "A6",
                "Bereicherungsverbot und andere Versicherungen",
                paragraphs(
                    "Die Versicherung darf nicht zu einer Bereicherung führen. Leistungen anderer "
                    "Versicherer, insbesondere der kantonalen Gebäudeversicherung, werden angerechnet; "
                    "eine Doppelentschädigung ist ausgeschlossen."
                ),
            )
            + ziff(
                "A7",
                "Betrügerische Begründung des Anspruchs",
                paragraphs(
                    "Werden Tatsachen zur Täuschung unrichtig mitgeteilt oder verschwiegen, ist "
                    f"{INSURER} an den Vertrag nicht gebunden (VVG Art. 40)."
                ),
            ),
        )
        + section(
            "B. SACHVERSICHERUNG",
            ziff(
                "B1",
                "Feuer und Gebäude",
                paragraphs(
                    "B1.1 Versichert sind Schäden durch Feuer, Rauch, Blitz und Explosion an der "
                    "versicherten Fahrhabe.",
                    "B1.3 Gebäude: In Kantonen mit kantonaler Gebäudeversicherung, zum Beispiel im "
                    "Kanton Zürich (Gebäudeversicherung Kanton Zürich, GVZ), sind Gebäude und "
                    "Gebäudebestandteile gegen Feuer- und Elementarschäden ausschliesslich dort "
                    "versichert. Dazu gehören fest verbundene Verglasungen, Schaufenster, Oblichter, "
                    "Storen, Markisen und Fassadenbleche. Sie sind nicht Gegenstand dieser "
                    "Versicherung.",
                ),
            )
            + ziff(
                "B2",
                "Elementarschäden",
                paragraphs(
                    "B2.1 Versichert sind Schäden durch Hochwasser, Überschwemmung, Sturm (Wind von "
                    "mindestens 75 km/h, der in der Umgebung der versicherten Sachen Bäume umwirft "
                    "oder Gebäude abdeckt), Hagel, Lawine, Schneedruck, Felssturz, Steinschlag und "
                    "Erdrutsch. In der Schweiz gibt es kein Cat-Nat-Regime: massgebend ist das "
                    "nachgewiesene Naturereignis, ohne amtlichen Erlass.",
                    "B2.2 Dringt Wasser durch eine von Hagel oder Sturm verursachte Öffnung ein, gilt "
                    "der Folgeschaden als Elementarschaden.",
                    "B2.3 Der Selbstbehalt richtet sich nach Ziff. A5 (AVO Art. 175 Abs. 1 lit. c).",
                    "B2.4 Nicht versichert sind Schäden durch Grundwasser, Rückstau aus der "
                    "Kanalisation und Bodensenkungen.",
                ),
            )
            + ziff(
                "B3",
                "Wasser",
                paragraphs(
                    "Versichert sind Schäden durch Leitungswasser aus Leitungsanlagen, die nur dem "
                    "Gebäude dienen, sowie durch Regen-, Schnee- und Schmelzwasser, das durch das "
                    "Dach oder durch geschlossene Fenster eindringt."
                ),
            )
            + ziff(
                "B4",
                "Kühlgut (Zusatzdeckung)",
                paragraphs(
                    "B4.1 Der Verderb von Kühl- und Tiefkühlgut infolge Temperaturveränderung durch "
                    "Ausfall oder Störung der Kühlanlage oder der Stromversorgung ist nur versichert, "
                    "wenn die Zusatzdeckung «Kühlgut» in der Police vereinbart ist. Dies gilt auch, "
                    "wenn der Ausfall durch ein versichertes Ereignis verursacht wurde.",
                    "B4.2 Wird Kühlgut direkt durch eingedrungenes Wasser oder Hagel beschädigt, gilt "
                    "der Schaden als Elementarschaden an Waren; die direkte Einwirkung ist "
                    "nachzuweisen.",
                ),
            )
            + ziff(
                "B5",
                "Kosten",
                paragraphs(
                    "Aufräumungs-, Entsorgungs- und Notmassnahmenkosten (Notverglasung, Trocknung) "
                    "sind auf Erstrisiko bis CHF 100'000 pro Ereignis versichert, ohne Anrechnung "
                    "einer Unterversicherung."
                ),
            ),
        )
        + section(
            "C. BETRIEBSUNTERBRUCH",
            ziff(
                "C1",
                "Gegenstand",
                paragraphs(
                    "Versichert sind der Ertragsausfall und die Mehrkosten infolge eines versicherten "
                    "Sachschadens am Versicherungsort. Beruht der Unterbruch ganz oder teilweise auf "
                    "einem nicht versicherten Schaden (zum Beispiel Gebäude bei der kantonalen "
                    "Gebäudeversicherung oder Kühlgut ohne Zusatzdeckung), wird der entsprechende "
                    "Anteil nicht übernommen."
                ),
            )
            + ziff(
                "C2",
                "Haftzeit",
                paragraphs("Die Haftzeit beträgt 12 Monate ab Eintritt des Sachschadens."),
            )
            + ziff(
                "C3",
                "Berechnung",
                paragraphs(
                    "Massgebend sind der Gewinn und die fortlaufenden Kosten. Saisonale Umsätze, zum "
                    "Beispiel das Weihnachtsgeschäft, werden anhand der Buchhaltung der Vorjahre "
                    "berücksichtigt. Massnahmen zur Schadenminderung (Provisorium, Auslagerung der "
                    "Produktion) mindern den Ertragsausfall; ihre Mehrkosten sind versichert."
                ),
            ),
        )
        + section(
            "D. ALLGEMEINE AUSSCHLÜSSE",
            paragraphs(
                "Nicht versichert sind Schäden, die vorsätzlich herbeigeführt werden, Schäden durch "
                "kriegerische Ereignisse, Kernenergie und Erdbeben sowie Abnützung und allmähliche "
                "Einwirkungen."
            ),
        )
        + section(
            "E. SCHLUSSBESTIMMUNGEN",
            paragraphs(
                "Aufsichtsbehörde ist die Eidgenössische Finanzmarktaufsicht FINMA. Personendaten "
                "werden nach dem Datenschutzgesetz (DSG) bearbeitet. Bei Meinungsverschiedenheiten "
                "steht die Ombudsstelle der Privatversicherung zur Verfügung."
            ),
        )
    )


# ── Claim form (Schadenmeldung) ──────────────────────────────────────────────


def claim_form_html() -> str:
    rows = [
        [f"{i}", label, chf(amount).replace(" ", "&#160;"), note]
        for i, (label, _, amount, note) in enumerate(DAMAGES, 1)
    ]
    rows.append(
        ["", "<b>Total geltend gemacht</b>", f"<b>{chf(TOTAL).replace(' ', '&#160;')}</b>", ""]
    )
    photos = "".join(f"<li>{p.name} — {p.taken} — {p.caption}</li>" for p in PHOTOS)
    return (
        f"<h1>Schadenmeldung — KMU-Geschäftsversicherung</h1>"
        f"<p>{INSURER} · Schadenservice · {INSURER_EMAIL} · Schaden-Nr. {CLAIM_NO}</p>"
        + section(
            "1. Versicherungsnehmer",
            table(
                ["Angabe", "Wert"],
                [
                    ["Firma", FIRM],
                    ["UID", UID],
                    ["Adresse", f"{STREET}, {TOWN}, Schweiz"],
                    ["Kontaktperson", f"{OWNER}, Geschäftsführerin"],
                    ["Telefon", PHONE],
                    ["E-Mail", OWNER_EMAIL],
                    ["IBAN für Zahlungen", IBAN],
                ],
            ),
        )
        + section(
            "2. Policendaten (vom System vorausgefüllt)",
            table(
                ["Deckung", "Versicherungssumme / Bedingung"],
                [
                    ["Police", f"{POLICY} — {AVB}"],
                    ["Versicherungsort", f"{STREET}, {TOWN} (Laden, Atelier, Lager)"],
                    [
                        "Feuer und Elementar, Fahrhabe (Waren, Einrichtungen, Maschinen)",
                        "CHF 1'250'000 (Neuwert)",
                    ],
                    ["Wasser", "CHF 1'250'000"],
                    ["Diebstahl", "CHF 50'000"],
                    ["Betriebsunterbruch (Ertragsausfall)", "CHF 950'000, Haftzeit 12 Monate"],
                    ["Kosten (Aufräumung, Notmassnahmen)", "Erstrisiko CHF 100'000"],
                    ["Glasbruch Mobiliar", "versichert"],
                    ["Zusatzdeckung Kühlgut", "<b>nicht abgeschlossen</b>"],
                    ["Mieterausbauten", "<b>nicht vereinbart</b>"],
                    ["Gebäude", "<b>nicht Gegenstand der Police</b> (Kanton Zürich: GVZ)"],
                    ["Selbstbehalt Elementar", "10 %, mindestens CHF 2'500, höchstens CHF 50'000"],
                ],
            ),
        )
        + section(
            "3. Schadenereignis",
            table(
                ["Angabe", "Wert"],
                [
                    ["Datum und Zeit", "Freitag, 28.08.2026, ca. 09:50–10:20 Uhr"],
                    ["Schadenort", f"{STREET}, {TOWN}"],
                    ["Ursache", "Hagel / Sturm (Elementarschaden)"],
                    ["Polizei / Behörden", "Kein Polizeirapport (Naturereignis)"],
                ],
            )
            + paragraphs(
                "Am Freitag, 28. August 2026, zog zwischen ca. 09:50 und 10:20 Uhr ein heftiges "
                "Hagelgewitter mit starken Sturmböen über Winterthur. Hagelkörner von bis zu "
                "ca. 5 cm Durchmesser zerschlugen das Schaufenster unseres Ladens und das Oblicht "
                "über dem Atelier; die Markise wurde zerrissen. Durch die Öffnungen drang "
                "Regenwasser in den Verkaufsraum und ins Atelier ein.",
                "An der Temperiermaschine entstand ein Kurzschluss, die Hauptsicherung löste aus. "
                "Der Elektro-Notdienst hat die Stromversorgung um 11:30 Uhr aus "
                "Sicherheitsgründen abgestellt; sie wurde erst am Samstag, 29. August 2026, um "
                "15:00 Uhr wieder eingeschaltet. In dieser Zeit stieg die Temperatur im Kühlraum "
                "auf 23,8 °C; die dort gelagerten Pralinés, Truffes und Ganache-Halbfabrikate "
                "sind verdorben.",
                "Ein grosser Teil des Warenvorrats für die Herbst- und Weihnachtssaison, die "
                "Ladeneinrichtung und mehrere Produktionsmaschinen sind beschädigt. Der Betrieb "
                "ist bis auf Weiteres geschlossen.",
            ),
        )
        + section(
            "4. Massnahmen zur Schadenminderung",
            paragraphs(
                "28.08.2026, 14:00 Uhr: Notverglasung durch einen Glaser-Notdienst, Abdeckung des "
                "Oblichts mit einer Plane, Abdeckung der Maschinen.",
                "Ab 29.08.2026: Bautrockner im Verkaufsraum und im Atelier. Unbeschädigte Ware wurde "
                "ausgelagert und gekühlt gelagert.",
            ),
        )
        + section(
            "5. Gebäudeschaden und kantonale Gebäudeversicherung",
            paragraphs(
                "Die Liegenschaftsverwaltung hat den Gebäudeschaden am 28.08.2026 der "
                f"Gebäudeversicherung Kanton Zürich (GVZ) gemeldet, GVZ-Schaden-Nr. {GVZ_REF}. "
                "Schaufenster und Oblicht wurden 2019 von uns als Mieterausbau erneuert; wir machen "
                "sie deshalb hier ebenfalls geltend."
            ),
        )
        + section(
            "6. Schadenaufstellung", table(["Pos.", "Bezeichnung", "Betrag", "Bemerkung"], rows)
        )
        + section(
            "7. Beilagen",
            f"<ul>{photos}</ul>"
            + paragraphs(
                "Folgen bis 11.09.2026: Inventarlisten per 31.07.2026, Umsatzzahlen September bis "
                "Dezember 2024 und 2025, Offerten der Unternehmer."
            ),
        )
        + section(
            "8. Erklärung",
            paragraphs(
                "Die Unterzeichnende bestätigt, dass die Angaben vollständig und wahrheitsgetreu "
                "sind, und ermächtigt die Versicherung, die zur Abklärung nötigen Auskünfte "
                "einzuholen.",
                f"Winterthur, 01.09.2026 — {OWNER}, Geschäftsführerin (elektronisch unterzeichnet)",
            ),
        )
    )


# ── E-mails ──────────────────────────────────────────────────────────────────

EMAIL_1 = {
    "file": "email-01-schadenmeldung-de",
    "from": (OWNER, OWNER_EMAIL),
    "to": ("PrevaIQ Schadenservice", INSURER_EMAIL),
    "cc": None,
    "date": "Fri, 28 Aug 2026 16:52:00 +0200",
    "date_label": "Freitag, 28. August 2026 16:52",
    "message_id": f"<20260828165200.4471@{DOMAIN}>",
    "subject": f"Schadenmeldung Hagelunwetter – Police {POLICY} – {FIRM}",
    "attachments": EMAIL_1_PHOTOS,
    "labels": ("Von", "Gesendet", "An", "Cc", "Betreff", "Anlagen"),
    "footer": FOOTER_DE,
    "body": f"""Sehr geehrte Damen und Herren

Heute Morgen, zwischen ca. 09:50 und 10:20 Uhr, hat ein heftiges Hagelgewitter unser Geschäft an der {STREET} in Winterthur schwer beschädigt. Das Schaufenster und das Oblicht über dem Atelier sind zerschlagen, Regenwasser ist in den Laden und ins Atelier eingedrungen. An der Temperiermaschine gab es einen Kurzschluss; der Elektro-Notdienst hat den Strom um 11:30 Uhr aus Sicherheitsgründen abgestellt. Wann er wieder eingeschaltet werden kann, ist noch offen – im Kühlraum lagern Pralinés und Truffes für den Herbstverkauf.

Wir haben für heute 14:00 Uhr eine Notverglasung organisiert und die Maschinen abgedeckt. Die Liegenschaftsverwaltung meldet den Gebäudeschaden der GVZ.

Im Anhang finden Sie vier Fotos von heute Vormittag. Die vollständige Schadenmeldung mit der Schadenaufstellung reichen wir nach. Bitte teilen Sie uns die Schadennummer mit und ob eine Besichtigung vorgesehen ist.

Freundliche Grüsse

{OWNER}
Geschäftsführerin
{FIRM}
{STREET}, {TOWN}
Tel. {PHONE}
Police Nr. {POLICY}
""",
}

_estimate_lines = "\n".join(f"- {english}: {chf_en(amount)}" for _, english, amount, _ in DAMAGES)
EMAIL_2 = {
    "file": "email-02-loss-estimate-en",
    "from": (PARTNER, PARTNER_EMAIL),
    "to": ("PrevaIQ Claims Service", INSURER_EMAIL),
    "cc": (OWNER, OWNER_EMAIL),
    "date": "Tue, 01 Sep 2026 18:05:00 +0200",
    "date_label": "Tuesday, 1 September 2026 18:05",
    "message_id": f"<20260901180500.4471@{DOMAIN}>",
    "subject": f"Claim {CLAIM_NO} – consolidated loss estimate and documents (hailstorm 28 August 2026)",
    "attachments": ["schadenmeldung-geschaeftsversicherung.pdf", *[p.name for p in PHOTOS]],
    "labels": ("From", "Sent", "To", "Cc", "Subject", "Attachments"),
    "footer": FOOTER_EN,
    "body": f"""Dear Sir or Madam,

Further to Andrea Keller's first notice of Friday 28 August (your claim no. {CLAIM_NO}, policy {POLICY}), please find attached our signed claim form (Schadenmeldung) and six photos.

Our consolidated loss estimate amounts to {chf_en(TOTAL)}:
{_estimate_lines}

A few points for your assessment:

1. The emergency electrician cut the power on 28 August at 11:30; it was restored on 29 August at 15:00. By then the cold room had reached 23.8 °C (photo of 29 August) and its contents were lost. We understand that our policy may not include the refrigerated goods extension; as the power cut was a direct consequence of the hailstorm, we ask you to consider this loss as part of the storm damage.

2. The property management has also reported the building damage to the GVZ (GVZ claim no. {GVZ_REF}). We renewed the shop window and the skylight ourselves in 2019 as tenant improvements, which is why we include them here.

3. The photo dated Wednesday 26 August (18:34) shows the fully stocked shop window two days before the storm. We provide it as evidence of our stock levels.

Inventory lists as at 31 July 2026, our September to December sales figures for 2024 and 2025 and the contractors' quotes will follow by 11 September.

Thank you for scheduling the loss adjuster's visit on Friday 4 September 2026 at 09:00; we will be on site.

Kind regards,

{PARTNER}
Co-owner, Finance
{FIRM}
{STREET}, {TOWN}, Switzerland
{PHONE}
""",
}


def _mail_attachment(name: str) -> tuple[bytes, str, str] | None:
    """Attachment as sent by a phone mail client: photos downscaled to 1024 px."""
    path = SCENARIO_DIR / name
    if not path.exists():
        return None
    if path.suffix == ".pdf":
        return path.read_bytes(), "application", "pdf"
    pixmap = fitz.Pixmap(path.read_bytes())
    scale = min(1.0, 1024 / max(pixmap.width, pixmap.height))
    if scale < 1.0:
        pixmap = fitz.Pixmap(pixmap, round(pixmap.width * scale), round(pixmap.height * scale))
    return pixmap.tobytes("jpg", jpg_quality=78), "image", "jpeg"


def write_email(mail: dict) -> list[str]:
    message = EmailMessage()
    message["From"] = f"{mail['from'][0]} <{mail['from'][1]}>"
    message["To"] = f"{mail['to'][0]} <{mail['to'][1]}>"
    if mail["cc"]:
        message["Cc"] = f"{mail['cc'][0]} <{mail['cc'][1]}>"
    message["Subject"] = mail["subject"]
    message["Date"] = mail["date"]
    message["Message-ID"] = mail["message_id"]
    message.set_content(mail["body"])
    attached, missing = [], []
    for name in mail["attachments"]:
        attachment = _mail_attachment(name)
        if attachment is None:
            missing.append(name)
            continue
        content, maintype, subtype = attachment
        message.add_attachment(content, maintype=maintype, subtype=subtype, filename=name)
        attached.append((name, len(content)))
    (SCENARIO_DIR / f"{mail['file']}.eml").write_bytes(message.as_bytes(policy=policy.SMTP))

    sender, sent, to, cc, subject, files = mail["labels"]
    header_rows = [
        [sender, f"{mail['from'][0]} &lt;{mail['from'][1]}&gt;"],
        [sent, mail["date_label"]],
        [to, f"{mail['to'][0]} &lt;{mail['to'][1]}&gt;"],
    ]
    if mail["cc"]:
        header_rows.append([cc, f"{mail['cc'][0]} &lt;{mail['cc'][1]}&gt;"])
    header_rows.append([subject, f"<b>{mail['subject']}</b>"])
    if attached:
        header_rows.append([files, ", ".join(f"{n} ({size // 1024} KB)" for n, size in attached)])
    body = "".join(
        "<p>" + "<br/>".join(block.split("\n")) + "</p>"
        for block in mail["body"].strip().split("\n\n")
    )
    html = (
        f"<h2>{mail['from'][0]}</h2>"
        + "".join(f"<p><b>{k}:</b> {v}</p>" for k, v in header_rows)
        + "<hr/>"
        + body
    )
    render_pdf(
        SCENARIO_DIR / f"{mail['file']}.pdf",
        html,
        mail["footer"],
        logo=False,
        title=mail["subject"],
        author=mail["from"][0],
    )
    return missing


# ── Rendering ────────────────────────────────────────────────────────────────


def render_pdf(path: Path, html: str, footer: str, *, logo: bool, title: str, author: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mediabox = fitz.paper_rect("a4")
    where = mediabox + (50, 80 if logo else 50, -50, -56)
    writer = fitz.DocumentWriter(str(path))
    story = fitz.Story(html=html, user_css=CSS)
    more = 1
    while more:
        device = writer.begin_page(mediabox)
        more, _ = story.place(where)
        story.draw(device)
        writer.end_page()
    writer.close()

    doc = fitz.open(path)
    for page in doc:
        if logo:
            draw_logo(page, 50, 22, 30)
            page.insert_text((300, 42), INSURER, fontsize=7.5)
            page.draw_line((50, 62), (545, 62), color=(0.18, 0.77, 0.71), width=0.8)
        page.insert_text((50, 815), footer, fontsize=6.5, color=(0.4, 0.4, 0.4))
        page.insert_text((520, 815), f"{page.number + 1}/{doc.page_count}", fontsize=7.5)
    doc.set_metadata(
        {
            "title": title,
            "author": author,
            "subject": footer,
            "creator": "scripts/generate_swiss_storm_claim.py",
        }
    )
    doc.saveIncr()
    doc.close()


# ── Photos ───────────────────────────────────────────────────────────────────


class MaiImages:
    """MAI image generations and edits with Microsoft Entra ID, retrying on throttling."""

    def __init__(self) -> None:
        import httpx
        from azure.identity import (
            AzureCliCredential,
            ChainedTokenCredential,
            DefaultAzureCredential,
        )

        self.endpoint = os.getenv(
            "MAI_IMAGE_ENDPOINT", "https://ai-workbenchiq-foundry.services.ai.azure.com"
        ).rstrip("/")
        self.deployment = os.getenv("MAI_IMAGE_DEPLOYMENT", "mai-image-2-6-temp")
        self.credential = ChainedTokenCredential(
            AzureCliCredential(process_timeout=60),
            DefaultAzureCredential(exclude_cli_credential=True),
        )
        self.client = httpx.Client(timeout=300)

    def _post(self, path: str, **kwargs) -> bytes:
        for attempt in range(6):
            token = self.credential.get_token(MAI_SCOPE).token
            response = self.client.post(
                f"{self.endpoint}/mai/v1/images/{path}",
                headers={"Authorization": f"Bearer {token}"},
                **kwargs,
            )
            if response.status_code == 429 or response.status_code >= 500:
                wait = int(response.headers.get("retry-after") or 0) or 20 * (attempt + 1)
                print(f"  MAI {response.status_code}, retrying in {wait} s", flush=True)
                time.sleep(wait)
                continue
            response.raise_for_status()
            return base64.b64decode(response.json()["data"][0]["b64_json"])
        raise RuntimeError(f"MAI {path} kept failing (throttled)")

    def generate(self, prompt: str) -> bytes:
        width, height = PHOTO_SIZE
        return self._post(
            "generations",
            json={
                "model": self.deployment,
                "prompt": prompt,
                "width": width,
                "height": height,
            },
        )

    def edit(self, prompt: str, reference: bytes) -> bytes:
        is_jpeg = reference[:3] == b"\xff\xd8\xff"
        name, mime = ("reference.jpg", "image/jpeg") if is_jpeg else ("reference.png", "image/png")
        return self._post(
            "edits",
            data={"model": self.deployment, "prompt": prompt, "auto_aspect_ratio": "true"},
            files=[("image", (name, reference, mime))],
        )


def _save_jpeg(png: bytes, name: str) -> None:
    pixmap = fitz.Pixmap(png)
    if pixmap.alpha:
        pixmap = fitz.Pixmap(pixmap, 0)
    (SCENARIO_DIR / name).write_bytes(pixmap.tobytes("jpg", jpg_quality=86))
    print(f"  {pixmap.width}x{pixmap.height}", flush=True)


def generate_photos() -> None:
    mai = MaiImages()
    originals: dict[str, bytes] = {}
    for photo in PHOTOS:
        print(f"Generating {photo.name} ({photo.caption})", flush=True)
        if photo.reference:
            png = mai.edit(photo.prompt, originals[photo.reference])
        else:
            png = mai.generate(photo.prompt)
        for refinement in photo.refinements:
            png = mai.edit(refinement, png)
        originals[photo.name] = png
        _save_jpeg(png, photo.name)


def refine_photos(names: list[str]) -> None:
    """Apply the last refinement edit of each named photo to its existing file."""
    mai = MaiImages()
    for photo in PHOTOS:
        if photo.name in names and photo.refinements:
            print(f"Refining {photo.name}", flush=True)
            _save_jpeg(
                mai.edit(photo.refinements[-1], (SCENARIO_DIR / photo.name).read_bytes()),
                photo.name,
            )


def write_manifest() -> None:
    photos = []
    for photo in PHOTOS:
        path = SCENARIO_DIR / photo.name
        entry = {
            "file": photo.name,
            "kind": "photo",
            "scenario_time": photo.taken,
            "caption_de": photo.caption,
            "model": MAI_MODEL,
            "model_version": MAI_VERSION,
            "prompt": photo.prompt,
            "edited_from": photo.reference,
            "refinement_prompts": list(photo.refinements),
        }
        if path.exists():
            entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        photos.append(entry)
    documents = []
    for name, kind in [
        ("schadenmeldung-geschaeftsversicherung.pdf", "claim form (German)"),
        ("email-01-schadenmeldung-de.eml", "first notice e-mail (German)"),
        ("email-01-schadenmeldung-de.pdf", "print of the first notice e-mail"),
        ("email-02-loss-estimate-en.eml", "consolidated estimate e-mail (English)"),
        ("email-02-loss-estimate-en.pdf", "print of the consolidated estimate e-mail"),
    ]:
        path = SCENARIO_DIR / name
        documents.append(
            {"file": name, "kind": kind, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        )
    manifest = {
        "scenario": "swiss-chocolate-storm",
        "title": f"Hailstorm in Winterthur, 28.08.2026 — {FIRM}",
        "persona": "habitation_claims",
        "synthetic": True,
        "notice": "Business, people, policy, references, amounts, documents and photos are "
        "fictitious and created for the PrevaIQ demo. Only the municipality (Winterthur) and "
        "the storm date are real. The photos are AI-generated (MAI-Image-2.6).",
        "generator": "scripts/generate_swiss_storm_claim.py",
        "policy_conditions": str(AVB_PATH.relative_to(ROOT)).replace("\\", "/"),
        "identity": {
            "company": FIRM,
            "uid": UID,
            "address": f"{STREET}, {TOWN}",
            "phone": PHONE,
            "iban": IBAN,
            "policy": POLICY,
            "claim": CLAIM_NO,
        },
        "identity_checks": IDENTITY_CHECKS,
        "timeline": [{"when": when, "event": event} for when, event in TIMELINE],
        "amounts_chf": {english: amount for _, english, amount, _ in DAMAGES} | {"total": TOTAL},
        "attention_points": ATTENTION_POINTS,
        "documents": documents,
        "photos": photos,
    }
    (SCENARIO_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--photos", action="store_true", help="(re)generate the MAI photos")
    parser.add_argument(
        "--refine",
        nargs="+",
        metavar="PHOTO",
        help="apply the last refinement edit to existing photos",
    )
    args = parser.parse_args()
    SCENARIO_DIR.mkdir(parents=True, exist_ok=True)

    if args.photos:
        generate_photos()
    if args.refine:
        refine_photos(args.refine)
    render_pdf(
        AVB_PATH,
        f"<h1>Allgemeine Versicherungsbedingungen (AVB)</h1>"
        f"<p><b>KMU-Geschäftsversicherung — {INSURER}</b><br/>Ausgabe 01/2026</p>" + avb_html(),
        f"{INSURER} — fiktive Versicherungsgesellschaft für "
        "Demonstrationszwecke. Dokument ohne Vertragswert.",
        logo=True,
        title=f"{AVB} — {INSURER}",
        author=INSURER,
    )
    render_pdf(
        SCENARIO_DIR / "schadenmeldung-geschaeftsversicherung.pdf",
        claim_form_html(),
        FOOTER_DE,
        logo=True,
        title=f"Schadenmeldung {CLAIM_NO} — {FIRM}",
        author=OWNER,
    )
    missing = write_email(EMAIL_1) + write_email(EMAIL_2)
    write_manifest()
    for path in [AVB_PATH, *sorted(SCENARIO_DIR.iterdir())]:
        print(f"{path.relative_to(ROOT)}: {path.stat().st_size // 1024} KB")
    if missing:
        print(f"Not attached (run with --photos first): {', '.join(sorted(set(missing)))}")


if __name__ == "__main__":
    main()
