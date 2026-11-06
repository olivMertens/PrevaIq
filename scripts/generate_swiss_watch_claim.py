"""Generate the Swiss windstorm demo claim: Schaffhausen watch manufacture, Friday 28.08.2026.

A clean but very large claim. The storm front of 28.08.2026 (hail in Winterthur, record gusts
of 142 km/h in Schaffhausen) tore off part of the flat roof of a fictitious haute horlogerie
manufacture; flying roof debris broke the skylights and the rain poured into the assembly
workshop and, through the ceilings, into the clean room, the final inspection and the parts
workshop. Contents and business interruption are claimed under the demo policy; building
repairs are handled separately by the GVSH. Photos show selected visible damage, not the
full inventory or internal defects. Quantities, repair scope and valuation require inventory
records, technical reports and adjuster review; those supporting records are not attached.

The business, people, policy, references and amounts are fictitious (see ``IDENTITY_CHECKS``);
the real address is a labelled map anchor only, not the depicted premises or occupants;
the municipality, the storm and the public sources about it are real
(``EVENT_SOURCES``). The policy conditions are the Swiss AVB written by
``generate_swiss_storm_claim.py``. Writes ``assets/demo-prevaiq/property-claims/
swiss-watch-storm/``: the claim form and the cost estimate (German), the first notice e-mail
(German) and the consolidated estimate e-mail (English) as ``.eml`` and print PDF, ten photos
and ``manifest.json``.

Usage::

    python scripts/generate_swiss_watch_claim.py            # documents and manifest
    python scripts/generate_swiss_watch_claim.py --photos   # also (re)generate the photos
    python scripts/generate_swiss_watch_claim.py --photos IMG_20260828_105014.jpg  # one photo
    python scripts/generate_swiss_watch_claim.py --refine IMG_20260828_110322.jpg  # edit one photo

Photos use the MAI-Image-2.6 deployment of ``generate_swiss_storm_claim.py``
(``MAI_IMAGE_ENDPOINT`` and ``MAI_IMAGE_DEPLOYMENT`` override its defaults).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_policy_pdfs import section, table  # noqa: E402
from generate_swiss_storm_claim import (  # noqa: E402
    AVB,
    AVB_PATH,
    IBAN,
    INSURER,
    INSURER_EMAIL,
    MAI_MODEL,
    MAI_VERSION,
    MaiImages,
    _save_jpeg,
    chf,
    chf_en,
    paragraphs,
    render_pdf,
    write_email,
)

ROOT = Path(__file__).resolve().parent.parent
SCENARIO_DIR = ROOT / "assets" / "demo-prevaiq" / "property-claims" / "swiss-watch-storm"
CREATOR = "scripts/generate_swiss_watch_claim.py"

# ── Fictitious identity (checked 05.11.2026, see IDENTITY_CHECKS) ────────────────
FIRM = "Rheinkaliber Uhrenmanufaktur AG"
UID = "CHE-715.062.384"
STREET = "Mühlentalstrasse 185"
TOWN = "8200 Schaffhausen"
LOCATION_DE = (
    "Demo-Kartenanker: Mühlentalstrasse 185, 8200 Schaffhausen. Die Adresse ist real; Firma, "
    "Betriebsräume und Schaden sind erfunden. Die KI-Bilder zeigen nicht das reale Gebäude "
    "oder dessen Nutzer. Street View zeigt den realen Ort, nicht diese Schadensszenen."
)
LOCATION_EN = (
    "Demo map anchor: Mühlentalstrasse 185, 8200 Schaffhausen. The address is real; the "
    "business, premises and loss are fictional. AI images do not depict the actual building "
    "or its occupants. Street View shows the real location, not these damage scenes."
)
MAP_ANCHOR = {
    "address": f"{STREET}, {TOWN}, Schweiz",
    "country": "CH",
    "purpose": "Real geocodable demo anchor only; fictional premises and loss",
    "official_source": "https://api3.geo.admin.ch/rest/services/ech/MapServer/"
    "ch.swisstopo.amtliches-gebaeudeadressverzeichnis/102134100",
    "official_coordinates": {"lat": 47.70854568481445, "lon": 8.630566596984863},
    "geocoder": "OpenStreetMap / Nominatim",
    "verified_result": {"lat": 47.7086398, "lon": 8.6305155, "level": "building"},
    "postcode_note": "Official register uses 8200; Nominatim currently returns 8204 at the "
    "same address in Schaffhausen. Documents retain the official postal address.",
    "street_view": "External real-location view; coverage is provider-dependent, not damage evidence",
}
PHONE = "+41 52 048 63 12"
DOMAIN = "rheinkaliber-uhren.example"
COO = "Martina Gerber"
COO_TITLE = "Leiterin Produktion"
COO_EMAIL = f"m.gerber@{DOMAIN}"
CFO = "Helen Marsh"
CFO_EMAIL = f"h.marsh@{DOMAIN}"
ADJUSTER = "Thomas Wyss"
POLICY = "PIQ-CH-KMU-2026-071506"
CLAIM_NO = "PIQ-S-2026-082853"
GVSH_REF = "SH-2026-0912"

IDENTITY_CHECKS = {
    "company": "No web match for 'Rheinkaliber' (company, brand or product); 'Randenblick' "
    "was rejected because real Schaffhausen businesses use it",
    "uid": "eCH-0097 mod-11 check digit of 71506238 would be 10, so no valid UID has this number",
    "street": "Real demo anchor verified in the Swiss official building-address register and "
    "Nominatim; no claim about the actual occupants or building",
    "phone": "search.ch: no directory entry for 052 048 63 12",
    "iban": "Example IBAN of the SWIFT IBAN registry for Switzerland",
    "email": "Reserved .example domains (RFC 2606)",
    "brand": "No real watch brand, logo, model name or building: the manufacture, its "
    "calibres and its premises are invented",
}
EVENT_SOURCES = [
    {
        "source": "Schaffhauser Polizei, 28.08.2026",
        "url": "https://sh.ch/CMS/Webseite/Schaffhauser-Polizei-23509044-DE.html",
        "fact": "Violent storm over the canton shortly after 10:00; about 90 damage reports, "
        "roofs torn off, flooded basements and garages, transformer stations out of service",
    },
    {
        "source": "Schaffhauser Nachrichten, 28.08.2026",
        "url": "https://www.shn.ch/region/kanton/2026-08-28/sturm-faellt-baeume-flutet-keller-"
        "und-raeumt-daecher-ab-diese-schaeden",
        "fact": "Gust of 142 km/h at the Schaffhausen measuring station (11:00 hourly maximum), "
        "the third highest value since 1982",
    },
    {
        "source": "Gebäudeversicherung Schaffhausen (GVSH)",
        "url": "https://gv.sh.ch/CMS/Webseite/Geb-udeversicherung-Schaffhausen--GVSH--"
        "1535223-DE.html",
        "fact": "About 1,500 building claims from the storm of 28.08.2026",
    },
]

# ── Policy (summary printed on the claim form) ───────────────────────────────
SUM_INSURED_CONTENTS = 62_000_000
INSURABLE_VALUE = 57_860_000  # inventory and fixed-asset register at 30.06.2026
SUM_INSURED_BI = 36_000_000
DEDUCTIBLE = 50_000  # 10 % of the compensation, capped at CHF 50,000 (AVB A5)

# ── Scenario facts ───────────────────────────────────────────────────────────
# (German label, English label, CHF, German note, cost-estimate lines (German, CHF))
DAMAGES = [
    (
        "Uhrwerke in Montage, Atelier Grande Complication: 312 Kaliber (u. a. 38 Tourbillon, "
        "21 Minutenrepetition, 64 Ewiger Kalender)",
        "Movements in assembly, haute complication workshop: 312 calibres (incl. 38 "
        "tourbillons, 21 minute repeaters and 64 perpetual calendars)",
        3_960_000,
        "265 zu revidieren, 47 irreparabel; Herstellungskosten gemäss Betriebsabrechnung",
        [
            (
                "Revision von 265 Werken (zerlegen, reinigen, Spiralfedern ersetzen, ölen, "
                "regulieren)",
                1_986_000,
            ),
            (
                "Neuanfertigung von 47 irreparablen Werken (davon 9 Tourbillon, 4 "
                "Minutenrepetition)",
                1_974_000,
            ),
        ],
    ),
    (
        "Komponenten und Halbfabrikate (Platinen, Brücken, Räder, Spiralfedern, Lagersteine) "
        "im Reinraum und im Montagelager",
        "Components and semi-finished parts (main plates, bridges, wheels, hairsprings, jewels) "
        "in the clean room and the assembly store",
        1_240_000,
        "Bestand gemäss Inventur 29.–30.08.2026",
        [
            ("Spiralfedern und Unruhen im Reinraum, 1'860 Stück", 412_000),
            ("Platinen, Brücken, Räder und Lagersteine", 828_000),
        ],
    ),
    (
        "Fertige Uhren in der Endkontrolle: 186 wasserexponierte Uhren in Gold- und "
        "Platingehäusen (Innenschaden zu prüfen)",
        "Finished watches in final inspection: 186 water-exposed watches in gold and platinum "
        "cases (internal damage subject to inspection)",
        3_540_000,
        "Kalkulationsansatz; Revisionsumfang nach technischer Prüfung, keine Verkaufspreise",
        [
            (
                "Budgetierte Revision von 186 Uhren mit Dichtheits- und Gangprüfung "
                "(Umfang zu bestätigen)",
                3_069_000,
            ),
            ("Ersatz von 29 beschädigten Zifferblättern", 412_000),
            ("Ersatz von 41 Armbändern und der Dichtungen", 59_000),
        ],
    ),
    (
        "Zifferblätter, Zeiger und Saphirgläser im Lager Endmontage (u. a. 64 "
        "Grand-Feu-Emailzifferblätter)",
        "Dials, hands and sapphire crystals in the final assembly store (incl. 64 grand feu "
        "enamel dials)",
        610_000,
        "Emailzifferblätter mit Wasserflecken nicht reparierbar",
        [
            ("64 Grand-Feu-Emailzifferblätter (Neuanfertigung)", 512_000),
            ("Zeiger und Saphirgläser", 98_000),
        ],
    ),
    (
        "Maschinen Teilefertigung: zwei Fünfachs-Bearbeitungszentren (Steuerungen und "
        "Schaltschränke), eine Drahterodiermaschine, eine Laserschweissanlage",
        "Parts manufacturing machines: two five-axis machining centres (controls and electrical "
        "cabinets), a wire EDM machine and a laser welding station",
        2_260_000,
        "Neuwert gemäss Offerten der Maschinenlieferanten",
        [
            (
                "Zwei Fünfachs-Bearbeitungszentren: Steuerungen, Antriebe, Schaltschränke "
                "(Offerte M-26-3318)",
                1_480_000,
            ),
            ("Drahterodiermaschine: Generator und Steuerung (Offerte M-26-3321)", 540_000),
            ("Laserschweissanlage (Offerte M-26-3324)", 240_000),
        ],
    ),
    (
        "Uhrmacherwerkbänke, Mikroskope, Zeitwaagen und Werkzeuge (Atelier, Endkontrolle); "
        "mobile Laminarflow-Werkbänke im Reinraum",
        "Watchmaker benches, microscopes, timing machines and tools (workshop, final "
        "inspection); mobile laminar-flow benches in the clean room",
        690_000,
        "24 Werkplätze, Neuwert",
        [
            ("24 Uhrmacherwerkplätze mit Mikroskopen", 456_000),
            ("Zeitwaagen und Werkzeuge", 118_000),
            ("6 mobile Laminarflow-Werkbänke", 116_000),
        ],
    ),
    (
        "Mess- und Prüfgeräte (optische Messmaschine, Dichtheitsprüfung, Gangprüfanlage) und "
        "IT im Atelier",
        "Measuring and test equipment (optical measuring machine, water-resistance tester, rate "
        "testing installation) and IT in the workshop",
        420_000,
        "Herstellerdiagnose vom 02.09.2026",
        [
            ("Optische Messmaschine", 236_000),
            ("Dichtheits- und Gangprüfanlage", 128_000),
            ("IT-Arbeitsplätze und Netzwerk im Atelier", 56_000),
        ],
    ),
    (
        "Betriebsunterbruch: Ertragsausfall und Mehrkosten bis zur Wiederinbetriebnahme von "
        "Atelier und Reinraum (geplant 30.11.2026)",
        "Business interruption: loss of gross profit and extra costs until the workshop and the "
        "clean room restart (planned 30 November 2026)",
        2_150_000,
        "Berechnung nach AVB C3; Endmontage ab 14.09.2026 ins Atelier Süd verlagert",
        [
            ("Ertragsausfall 29.08. bis 30.11.2026 (Budget 2026, Vorjahre)", 1_860_000),
            ("Mehrkosten: Verlagerung der Endmontage, Überstunden, Expresstransporte", 290_000),
        ],
    ),
    (
        "Notmassnahmen und Aufräumung Fahrhabe (Wasserabsaugung, Trocknung, Schutzabdeckung "
        "der Maschinen, Entsorgung)",
        "Emergency measures and clean-up for the contents (water extraction, drying, protective "
        "covers, disposal)",
        98_600,
        "Erstrisiko CHF 100'000 (AVB B5); Notdach über die GVSH",
        [
            ("Wasserabsaugung und Trocknung (Rechnung T-2026-5582)", 61_400),
            ("Schutzabdeckungen, Reinigung und Entsorgung", 37_200),
        ],
    ),
]
TOTAL = sum(amount for _, _, amount, _, _ in DAMAGES)
assert TOTAL == 14_968_600
assert all(amount == sum(value for _, value in lines) for _, _, amount, _, lines in DAMAGES)
NET = TOTAL - DEDUCTIBLE

TIMELINE = [
    (
        "28.08.2026 10:05-10:30",
        "Windstorm with gusts up to 142 km/h and torrential rain; about 420 m² of the flat roof "
        "membrane and insulation torn off, 9 of 24 skylight panes broken by flying roof debris",
    ),
    ("28.08.2026 10:12", "Workshop evacuated; accessible movements moved to safes where possible"),
    ("28.08.2026 10:20", "Facility manager cuts the power to the north wing for safety"),
    (
        "28.08.2026 10:38-11:31",
        "Six sample damage photos; rain ingress and drainage of residual water continue "
        "after the peak gusts, including through the ceiling void",
    ),
    ("28.08.2026 11:45", f"Building damage reported to the GVSH (no. {GVSH_REF})"),
    ("28.08.2026 13:12", "E-mail 1 (German): first notice of loss"),
    ("28.08.2026 14:30", "Roofers start emergency covering; photo at 14:32 shows work in progress"),
    ("29.08.2026 08:00", "Drying company on site (photo 09:17)"),
    ("29.-30.08.2026", "Inventory count with the statutory auditor (photo 29.08, 14:15)"),
    ("31.08.2026 10:00", f"PrevaIQ loss adjuster's visit, {ADJUSTER} (photo 10:05)"),
    ("02.09.2026", "Machine manufacturers' diagnosis; quotes follow"),
    (
        "18.09.2026",
        "Claim form and cost estimate signed; e-mail 2 (English): consolidated estimate",
    ),
]
EXPECTED_OUTCOME = [
    "The storm is confirmed by public sources (Schaffhausen police, Schaffhauser Nachrichten, "
    "GVSH): Elementar damage, wind above 75 km/h (AVB B2.1); rain entering through the storm "
    "openings counts as Elementar damage (B2.2).",
    "Photos, timeline, cost estimate and e-mails are consistent; no photo predates the storm.",
    "Building damage is handled by the GVSH and is not claimed (B1.3, A6); goods are valued at "
    "manufacturing cost (A3.1); no underinsurance; costs within the CHF 100,000 first-loss "
    "limit (B5).",
    f"Deductible {chf_en(DEDUCTIBLE)} (10 %, capped, A5); estimated net {chf_en(NET)}. "
    "Photos show sample visible damage, not the full inventory, internal watch damage "
    "or the entire valuation; inventory records and technical reports require validation.",
]

# ── Photos (MAI-Image-2.6) ───────────────────────────────────────────────────
STYLE = (
    " Realistic smartphone photo, natural light, slightly imperfect framing. No people, no "
    "brand logos, no watermark, no text overlay."
)
STYLE_PEOPLE = (
    " Realistic smartphone photo, natural light, slightly imperfect framing. People seen from "
    "behind or from a distance, faces not visible. No brand logos, no watermark, no text "
    "overlay."
)
IMAGE_SYSTEM_INSTRUCTIONS = (
    "MANDATORY IMAGE CONSTRUCTION RULES. Produce a physically credible documentary "
    "photograph of a fictional Swiss watch manufacture, not an illustration or display. "
    "Use one consistent camera projection, metric scale, gravity and load-bearing geometry. "
    "Opaque roof construction and glazed skylight construction are DISTINCT: roof insulation "
    "belongs ONLY inside opaque roof assemblies. A glazed opening contains glass, glazing "
    "seals and metal framing, NOT exposed mineral-wool batts. Never generate insulation "
    "growing out of glass, glazing bars or window frames. Do not invent a torn opaque roof "
    "edge merely to add insulation. Every damaged object needs the scene's stated cause. "
    "Keep unsupported material out of mid-air and equipment correctly supported. "
    "ALL readable physical text must be GERMAN as used in Schaffhausen, Switzerland: "
    "no English or French words, invented brands, gibberish or random dates. "
    "Use the scene's exact short German wording only where specified. Other labels "
    "are unlettered, turned away or too small to read; do not generate fake fine print. "
    "Numeric inventory IDs and normal watch hour markings are permitted. These rules "
    "also apply to edits; retain scene geometry unless a correction explicitly changes it."
)


@dataclass(frozen=True)
class Photo:
    name: str
    taken: str
    caption: str  # German, as listed in the claim form
    prompt: str
    reference: str | None = None  # earlier photo edited to keep the same room
    refinements: tuple[str, ...] = ()  # edits applied after generation to remove AI artefacts
    system_prompt: str = ""


PHOTOS = [
    Photo(
        "IMG_20260828_103852.jpg",
        "28.08.2026 10:38",
        "Flachdach Nordflügel: Dachhaut und Dämmung abgerissen, Oblichter zerschlagen",
        "Flat roof of a modern three-storey watch manufacturing building in an industrial area "
        "of Schaffhausen, Switzerland, photographed from the rooftop access hatch twenty minutes "
        "after a violent windstorm: a large section of the grey roof membrane and of the yellow "
        "insulation boards beneath has been torn off and rolled back, exposing the concrete "
        "deck; insulation pieces and gravel scattered across the roof; a row of saw-tooth "
        "north-light glass skylights with several panes smashed by flying roof debris; a "
        "rooftop ventilation unit knocked over on its side; rain puddles, wet surfaces, broken "
        "tree branches; dark grey sky with low fast-moving clouds, wooded hills in the "
        "distance." + STYLE,
    ),
    Photo(
        "IMG_20260828_104507.jpg",
        "28.08.2026 10:45",
        "Atelier Grande Complication: zerbrochene Oblichter, Wasser auf den Werkbänken",
        "PURPOSE: an unposed insurance-documentation photograph of an evacuated artisanal "
        "watch-assembly atelier in a Swiss manufacture, at 10:45 after a windstorm. "
        "This is a working room, not a luxury showroom or an architectural catalogue. "
        "WORKFLOW AND SCALE: show two watchmaker stations, not a row of duplicates. "
        "Heavy timber benches have raised padded "
        "forearm rests, a recessed green working mat and drawers. Each visible station "
        "has ONE compact binocular microscope on its own broad base and ONE short "
        "two-joint task lamp securely clamped to that bench's rear edge. Lamp arms serve "
        "only their own station, never span an aisle or connect neighbouring benches. "
        "A movement holder, loupe, tweezers and compartmented parts tray indicate "
        "interrupted individual hand assembly, not rows of watches for sale. "
        "DAMAGE MECHANISM: the vertical windows and main roof structure remain intact. "
        "Two adjacent overhead skylight panes have broken; a local downward gust and "
        "wind-driven rain entered there during the storm. At the photographed moment "
        "the gust has subsided: loose debris has settled and rain still enters. "
        "Below that opening, small glass fragments and rain form a localized "
        "fall zone on one bench and the floor. A few light papers have travelled "
        "farther toward the rear aisle, unlike the heavier glass. Beyond the fall "
        "zone, benches are substantially cleaner and drier. "
        "OBJECT HISTORY: the heavy benches and base-mounted microscopes remain stable. "
        "At the affected station the departing worker folded the short lamp down out "
        "of the way; its head rests on its own mat and its clamp remains attached. "
        "The other lamp remains parked near the back of its bench. "
        "The departing watchmaker pushed one ordinary five-caster task chair back "
        "and turned it obliquely during evacuation. The sheltered station was not in "
        "use and its chair remains tucked in. Both remain "
        "upright on their wheels. Chairs are not arranged at identical angles or "
        "overturned without an impact cause. "
        "PHYSICS AND SAFETY: fine intermittent rain droplets fall from the actual "
        "opening; runoff follows frames and drips from low edges, forming shallow "
        "irregular wet patches below. Glass, tools and fallen material rest on real "
        "surfaces with contact shadows. Power was isolated at 10:20: all lamps, "
        "microscope lights and equipment indicators are dark. No people are working "
        "under the broken roof. "
        "CAMERA: handheld eye-level photograph from the dry doorway, ordinary "
        "35 mm-equivalent perspective, slight off-centre framing, overcast daylight. "
        "Low wooded Schaffhausen hills outside. No panoramic mountain scenery, "
        "perfect symmetry, giant lamp booms, duplicate tools, airborne debris, "
        "uniformly distributed damage or cinematic disaster lighting." + STYLE,
        refinements=(
            "Check the causal consistency of this newly generated atelier, retaining "
            "its small-scale hand-assembly workflow and camera position. Damage is "
            "concentrated beneath the two broken skylight panes, not evenly scattered "
            "throughout the room. Keep one short independently clamped lamp per station; "
            "the affected lamp head rests on its mat after being folded by its user, "
            "while the sheltered lamp stays parked. Each microscope has one stable base. "
            "The two upright chairs have different plausible positions: one rolled back "
            "and rotated, one tucked in. Keep heavy benches stationary, settled debris "
            "supported, lamps unlit and the room evacuated. Do not beautify the scene "
            "into symmetrical rows, add long shared lamp arms or invent more damage.",
            "LOCAL FINISHING: keep the exact room and camera. The opaque ceiling "
            "strip at the very TOP LEFT above the front steel beam is closed with "
            "continuous intact light-grey soffit panels. No torn panel, exposed "
            "roof layers, mineral wool or hanging fragments anywhere in this view. "
            "Only the skylight glass is broken, inside its original metal frame. "
            "REMOVE all paper notices and the digital clock from both doorway "
            "walls, leaving plain continuous plaster. Do not replace them with "
            "other text. Keep tools small: any movement in a holder is 28 mm "
            "across, a loupe 25 mm and tweezers 120 mm long. Fold the affected "
            "rear bench lamp down at its existing hinges so the head rests on "
            "that bench's mat, retaining its actual clamp and arm connections. "
            "Leave the sheltered lamp raised. Do not add any material to the "
            "skylight, bench, floor or window. All existing settled glass and "
            "water remain. No signage, clock or additional text.",
        ),
        system_prompt=IMAGE_SYSTEM_INSTRUCTIONS
        + " SCENE GEOMETRY: the visible atelier bay is 5.0 m wide, 6.0 m deep, "
        "with its structural beam 2.8 m above the floor. Camera height 1.55 m at "
        "the doorway, 35 mm-equivalent lens, level verticals. Two benches are "
        "1.20 m wide, 0.70 m deep and 0.95 m high; leave a 1.0 m clear aisle. "
        "Chair seat height 0.58 m, five-caster base diameter 0.62 m; chair backs "
        "rise 0.35 m above the seats. Microscopes are 0.30 m high on 0.20 m bases. "
        "Task-lamp arm segments are each 0.25 m, with 0.12 m heads. A 28 mm movement "
        "is smaller than the 40 mm holder, a 25 mm loupe and 120 mm tweezers provide "
        "consistent scale. No dimension arrows or drawn measurements in the image. "
        "BUILDING SECTION: a raised sawtooth rooflight strip is above the rear bench. "
        "Its inclined glazed faces have slender metal mullions and two locally broken "
        "0.60 m by 0.90 m panes. All neighbouring opaque roof soffits are INTACT, "
        "so NO insulation, gypsum, roof lining or structural debris is exposed "
        "or falling in this view. Only broken glazing and rain entered this bay. "
        "Keep damaged glass edges within their glazing rebates; no enormous "
        "freely dangling sheet of glass. The rest of the room remains stable.",
    ),
    Photo(
        "IMG_20260828_105014.jpg",
        "28.08.2026 10:50",
        "Werkbank: drei Uhrwerke als Ausschnitt, Wasser und Glassplitter",
        "Documentary macro photograph looking down onto a wet green watchmaker's bench mat "
        "after rain entered through a broken skylight. Exactly three separate ordinary "
        "28 mm mechanical movements in 40 mm black plastic holders; small circular metal "
        "baseplates, properly screwed bridges, one balance wheel per movement, a few "
        "coherent gears, no artistic skeleton mechanisms. A 120 mm steel tweezer lies "
        "flat alongside the holders and is more than four movement diameters long. "
        "A small 25 mm loupe rests separately. Sparse tiny glass splinters, dirty water "
        "droplets and a shallow wet patch on the mat. Ordinary credible parts scale and "
        "contact shadows, no giant detached balance wheels, no extra cases or piles "
        "of gears. Blurred workshop background, no broken vertical window. Natural "
        "overcast light; a real loss-documentation photo, not a watch advertisement." + STYLE,
        refinements=(
            "Make this a physically credible close-up of the same wet watchmaker's bench. "
            "Keep the green mat, rain droplets, small glass fragments and natural light. "
            "Show only three separate conventional mechanical movements, each 28 to 32 mm "
            "in diameter, seated flat in its own roughly 40 mm black movement holder. "
            "Each movement has a coherent circular baseplate, firmly screwed-down bridges, "
            "a few properly meshing gears and one balance wheel; no giant loose tourbillon "
            "wheel, fused gears, duplicated balances or impossible mechanical piles. "
            "One ordinary 120 mm steel tweezer lies flat beside them, about four times a "
            "movement diameter, its two tips joined at the heel; a small parts tray and "
            "a 25 mm loupe rest separately on the same mat. Keep all objects supported and "
            "correctly scaled with contact shadows, droplets and modest glass splinters "
            "resting on surfaces. The blurred background belongs to the skylit workshop, "
            "not a newly broken vertical window. No brands, text overlays or people.",
        ),
    ),
    Photo(
        "IMG_20260828_110322.jpg",
        "28.08.2026 11:03",
        "Endkontrolle: vier Uhren im flachen Arbeitstablett, Wasser und gefallene Deckenplatte",
        "PURPOSE: an unposed insurance-documentation photograph of a working mechanical "
        "watch final-inspection bench in a Swiss manufacture, at 11:03 after storm-water "
        "ingress. This is an interrupted production check and a small visible sample "
        "of the inventory. "
        "CAMERA FIRST: the photographer stands beside the bench and points the camera "
        "DOWN at about 55 degrees. The tabletop occupies most of the picture, with a "
        "narrow strip of wet floor and part of the task chair at the near edge. The "
        "ceiling itself is OUT OF FRAME; do not lower the viewpoint to include it. "
        "Use an ordinary 35 mm-equivalent lens and grey side-window daylight. "
        "WORK TRAY: a low-sided rectangular GREY PLASTIC factory parts tray lies "
        "completely flat on the worktop. Its bottom is a thin black anti-static foam "
        "sheet, divided by thin plastic partitions. The entire underside is supported "
        "by the tabletop; all tray corners lie in the same horizontal plane. "
        "Four 38-42 mm finished mechanical wristwatches lie on their case backs in "
        "separate cells. Their unbuckled leather straps extend flat along each cell. "
        "Dials face vertically UP toward the camera above. Leave some cells empty. "
        "The tray is plain working equipment with no lid, velvet, cushions, hinges, "
        "raised backboard, presentation stand or watch rolls. "
        "WORKFLOW: beside the tray are a compact timing instrument with an actual "
        "microphone cradle, a small closed pressure-test chamber, a 25 mm loupe and "
        "one displaced A4 inspection worksheet. Its sole readable heading is "
        "'ENDKONTROLLE'; below it are empty ruled boxes with no dates or other words. "
        "The instruments have dark displays "
        "and unlit indicators because the room was electrically isolated at 10:20. "
        "Watch dials have ordinary central hands and plain baton markers. "
        "DAMAGE HISTORY: a ceiling tile above this bench was saturated by roof "
        "leakage and fell earlier. A settled broken tile fragment rests on the visible "
        "floor edge, never in mid-air. Rain still drips from above the frame onto "
        "the near end of the worktop. Show irregular shallow wet patches and exterior "
        "droplets on the nearer tray cells and exposed watch crystals. The farther "
        "instruments and tray cells remain comparatively dry; water runs over the "
        "near bench edge into the shallow wet floor patch below. "
        "MATERIAL PHYSICS: sealed watch crystals remain clear inside; wet exteriors "
        "alone do not imply internal condensation. Leather darkens slightly where "
        "wet. Tools and watches retain ordinary scale relative to one another; every "
        "item rests on the worktop, tray foam or floor with consistent contact shadows. "
        "No instant heavy rust or shattered metal cases. Keep an imperfect evidence "
        "photograph rather than a symmetrical product arrangement." + STYLE,
        refinements=(
            "Preserve the HIGH DOWNWARD camera angle and working-bench composition. "
            "Keep the plain low-sided grey factory tray lying entirely flat on the "
            "tabletop, four watches on their backs with open straps lying flat in "
            "separate foam-lined cells. Keep empty cells, real test instruments, "
            "dark displays, irregular exterior rain droplets and the comparatively "
            "dry far end. The roof opening stays outside the frame. Do not introduce "
            "a propped presentation case, raised tray back, velvet jewellery box, "
            "cushions, watch rolls, internal crystal fog, repeated racks or a new "
            "eye-level camera viewpoint. Preserve supporting surfaces and scale.",
            "LOCAL TEXT CLEANUP ONLY: keep the exact camera, workbench, flat grey "
            "tray, four watches, German worksheet heading ENDKONTROLLE, water "
            "and supported tile fragments. Remove the wall slogan and wall clock "
            "at the upper right, leaving plain plaster. Remove every small fake "
            "brand or word on both instrument housings and around their screens; "
            "those panels are plain unlettered metal or plastic with dark screens. "
            "Remove all tiny writing from the worksheet's table cells, retaining "
            "only empty ruled boxes and its exact German heading ENDKONTROLLE. "
            "Watch dials have plain baton markers and hands, no invented brand. "
            "Do not replace removed text with new labels or alter object sizes.",
        ),
        system_prompt=IMAGE_SYSTEM_INSTRUCTIONS
        + " SCENE SCALE: a 1.40 m by 0.75 m bench, worktop height 0.85 m. "
        "Camera height 1.55 m, aimed downward at 55 degrees with a 35 mm-equivalent "
        "lens. The plain horizontal factory tray measures 0.36 m by 0.28 m, "
        "rim height 0.025 m. Four parallel 0.055 m-wide cells are each 0.25 m long, "
        "allowing a 40 mm watch and its 0.22 m open strap to lie entirely flat; "
        "one extra cell remains empty. Every cell runs front-to-back, with no "
        "cross-wall cutting a strap in two. A4 worksheet is 0.210 m by 0.297 m, "
        "larger than the compact 0.18 m-wide timing instrument. A closed pressure "
        "chamber is 0.18 m in diameter and 0.20 m high; loupe diameter 0.025 m. "
        "The tray is approximately nine watch-case diameters wide, not giant "
        "relative to the bench. No drawn dimensions or measuring annotations. "
        "BUILDING SECTION: this separate inspection room has an opaque flat roof "
        "and suspended fibre ceiling tiles, not a glazed ceiling. Rain tracked "
        "through the roof void; one saturated tile fell. Roof insulation stays "
        "above the ceiling and OUT OF VIEW. No mineral wool in windows. "
        "TEXT: the worksheet heading is exactly 'ENDKONTROLLE', no English "
        "'FINAL INSPECTION', no invented date, serial number, logo or dial brand.",
    ),
    Photo(
        "IMG_20260828_111840.jpg",
        "28.08.2026 11:18",
        "Reinraum: Deckenplatten heruntergefallen, Wasser und Schmutz",
        "Watchmaking clean room on the first floor of a modern manufacture after rain water came "
        "through the ceiling during a storm: white walls and white floor, several fallen white "
        "ceiling panels lying on laminar-flow workstations and on the floor, muddy water on the "
        "floor and on the stainless steel worktables, small parts trays and microscopes on the "
        "benches covered with dirty droplets, a wall-mounted emergency light on, the room "
        "otherwise dim." + STYLE,
        refinements=(
            "Correct the physics of this same storm-damaged clean room without changing "
            "its layout or damage. Remove the unsupported ceiling tile hanging diagonally "
            "in mid-air. Fallen tiles lie flat on the floor or rest with a broad face on "
            "a worktable, with visible support and realistic shadows; no tile balances on "
            "a single sharp corner. Retain the open ceiling grid and wet insulation above. "
            "Water drips vertically from the damaged ceiling and forms shallow connected "
            "puddles on the floor; there are no floating fragments. Turn off the laminar "
            "cabinet task lights, microscopes and every mains-powered light because power "
            "has been isolated. Only the small battery emergency light may glow. Window "
            "views show low wooded hills, not alpine peaks. Preserve the stainless benches, "
            "microscopes, parts trays, daylight, and absence of people or brands.",
            "Make only this lighting correction: the three long bright white light strips "
            "under the laminar-flow cabinet hoods are SWITCHED OFF. Replace those glowing "
            "white strips with unlit neutral grey diffuser strips; no luminous bar or "
            "light spill remains under any hood. Leave the small rectangular battery "
            "emergency light on the upper right wall illuminated. Preserve everything "
            "else, especially the supported fallen panels, water, benches and daylight.",
        ),
    ),
    Photo(
        "IMG_20260828_113105.jpg",
        "28.08.2026 11:31",
        "Teilefertigung: Bearbeitungszentrum, Wasser im Schaltschrank",
        "Ground-floor precision machining workshop of a fictional watch manufacture after "
        "storm water leaked through its ceiling. Documentary photograph, grey daylight "
        "only through large windows, ALL rectangular ceiling lights dark grey and unlit. "
        "A realistic five-axis CNC machining centre with a light grey enclosure, ordinary "
        "spindle and workholding table; access door open. At its right is a firmly attached "
        "open electrical cabinet showing water droplets on organized terminal blocks and "
        "wiring bundles secured to cable trays. All machine displays are BLACK and all "
        "LEDs are OFF: the entire north wing was electrically isolated at 10:20. "
        "No loose or cut cables on the wet floor; supply enters through a sealed conduit. "
        "A small sloping waterproof diversion sheet on a freestanding four-legged support "
        "frame catches the ceiling leak ABOVE the machine and drains through one continuous "
        "hose into a bucket to the LEFT, away from the open cabinet. Visible load-bearing "
        "feet on the floor, gravity-consistent runoff, no floating tarp or water pouring "
        "through intact fabric. Shallow rainwater puddles on grey epoxy floor, ordinary "
        "window reflections, no glowing artificial lights. Other isolated machines in "
        "the background. Low wooded Schaffhausen hills outside, no alpine mountains." + STYLE,
        refinements=(
            "Correct this same flooded CNC workshop at 11:31, after the north wing's "
            "electricity was isolated at 10:20. ALL machine displays, status indicators, "
            "work lights and ceiling lights must be dark. Use only grey window daylight. "
            "The open electrical cabinet is de-energized, its cable bundles terminate "
            "in actual terminals or cable glands, not disconnected live cables trailing "
            "into water. Keep evidence of water inside the cabinet. Replace the "
            "impossible ceiling-hung sagging tarp that spills onto the machine with a "
            "small supported sloping temporary water-diversion sheet on a stable "
            "freestanding frame, draining by a continuous hose into a visible bucket "
            "on the floor AWAY from the cabinet. No water can pour out of intact fabric. "
            "Keep the same CNC enclosure, spindle and room geometry. Floor puddles have "
            "realistic shallow depth and reflections. No people, logos or new damage.",
        ),
    ),
    Photo(
        "IMG_20260828_143218.jpg",
        "28.08.2026 14:32",
        "Notabdeckung des Daches: Arbeiten im Gang, Oblichter noch nicht vollständig abgedeckt",
        "The same flat roof, skylights and surroundings as in the reference photo, about four "
        "hours later: three roofers in orange high-visibility jackets and white helmets are "
        "fixing large grey waterproof tarpaulins with wooden battens and sandbags over the torn "
        "roof area and the broken skylights; the rain has stopped, the sky is still overcast, a "
        "pallet of roofing material stands near the hatch. Keep the same roof, skylights, "
        "ventilation unit and hills." + STYLE_PEOPLE,
        reference="IMG_20260828_103852.jpg",
        refinements=(
            "Correct the practical roof repair in this photo while preserving the original "
            "roof, damaged skylights, toppled ventilation unit, hatch and low wooded hills. "
            "Three roofers have coherent normal hands and feet, protective helmets and "
            "properly attached fall-protection harnesses with visible lanyards to a "
            "temporary safety line. The waterproof cover actually spans the damaged "
            "roof area and all broken panes, with overlapping edges, firmly secured "
            "battens and weighted edges, a shallow fall toward drainage, no loose "
            "rectangular timber grid floating above fabric or sagging rain trap. "
            "Do not cover intact unrelated roof areas instead of the openings. "
            "Keep their boots in visible contact with solid roof, not unsupported "
            "skylight glass. It is overcast and has stopped raining. No brand logos.",
        ),
    ),
    Photo(
        "IMG_20260829_091744.jpg",
        "29.08.2026 09:17",
        "Atelier: zwei Trocknungsgeräte und ein Luftgebläse, Werkbänke abgedeckt",
        "The same evacuated hand-assembly atelier as in the reference photo, the next "
        "morning during professional drying. Preserve its exact bench positions, short "
        "independently clamped lamps, chair locations, windows and camera angle; do not "
        "replace it with a large showroom. Broken skylights are now sealed externally "
        "with secured grey waterproof covers. Loose glass has been "
        "removed; watches, parts and microscopes have been taken away for documented "
        "salvage. Benchtops are cleared and loosely protected, with the space underneath "
        "open to drying airflow, not sealed around wet equipment. Two compact industrial "
        "dehumidifiers and one blue air mover stand on the cleared floor, spaced to "
        "leave a real access aisle. Air outlets face open room space. Power cords run "
        "to a dry protected temporary distribution box and are secured at crossings. "
        "No active ceiling leak, loose glass, random tape crosses or operating damaged "
        "bench equipment. Ceiling water stains remain. Use overcast daylight and safe "
        "temporary lighting, not the disconnected workshop lamps." + STYLE,
        reference="IMG_20260828_104507.jpg",
        refinements=(
            "Retain the reference atelier's exact architecture, benches, independent "
            "short task lamps and camera position. This is the next morning after "
            "cleanup: no active leak or loose glass remains, and damaged microscopes, "
            "watches and parts have been removed for salvage. Secured exterior roof "
            "covers seal the two broken panes. Protective sheets lie loosely over "
            "cleared benchtops only; leave their undersides open for drying airflow. "
            "Keep exactly two compact dehumidifiers and one blue air mover on stable "
            "feet, with outlets facing open space and a clear access aisle. Each "
            "unit's cord runs continuously to a dry orange protected distribution "
            "box outside the former wet area; its incoming cable exits through the "
            "dry doorway. Cable crossings are secured by actual cable covers or "
            "tape over the cord, never decorative crosses. The atelier's damaged "
            "lamps remain off; only temporary safe equipment is powered. Preserve "
            "water stains and the modest wooded-hill view. No new damage or equipment.",
            "LOCAL CONTINUITY FIX: preserve the entire room and equipment layout. "
            "REMOVE the extra small glowing lamp floating above the rear bench; "
            "leave that wall plain. The only task lamps are the two existing "
            "bench-clamped lamps, both OFF, with the rear one folded down. "
            "The TWO MIDDLE glazed bays of the four-bay rooflight were broken "
            "in the storm reference. Cover BOTH middle bays with flat continuous "
            "grey weatherproof sheets secured OUTSIDE to their glazing-frame "
            "perimeters; sheets follow the same glazing slope and lie flush "
            "with the frames. The leftmost and rightmost intact panes remain "
            "transparent. No stuffed window recess, insulation, new hinge, "
            "hanging frame or open sash. Remove small invented branding from "
            "drying units and the orange distribution box, leaving plain housings "
            "and actual physical controls. No new lights, words or equipment.",
        ),
        system_prompt=IMAGE_SYSTEM_INSTRUCTIONS
        + " SCENE CONTINUITY: edit the newly generated atelier reference, not a "
        "new building. Retain the same 5.0 m by 6.0 m bay, 2.8 m beam, "
        "1.20 m by 0.70 m benches at 0.95 m height, 0.62 m chair bases, "
        "1.0 m aisle and doorway camera projection. Skylight frames contain "
        "only glazing; adjacent opaque soffits remain intact. Remove broken "
        "glass after salvage and show secured external covers over the same "
        "two damaged panes, not wool, interior stuffing or a new opaque roof. "
        "Two drying units are each 0.40 m wide, 0.35 m deep and 0.65 m high, "
        "the blue air mover 0.40 m in diameter. Distribute them along the aisle "
        "edges with at least 0.80 m remaining for access; do not block the door. "
        "The dry orange supply box is 0.30 m high, with three real outgoing "
        "connections and one incoming cable. Keep clear continuous cable routes. "
        "No readable device branding, English signs or invented technical text.",
    ),
    Photo(
        "IMG_20260829_141506.jpg",
        "29.08.2026 14:15",
        "Inventur: sechs verpackte Teile als Ausschnitt, Nummern 1001 bis 1006",
        "Documentary photo of a small inventoried sample of storm-water-damaged watch "
        "components on a white meeting-room table. Exactly six closed transparent "
        "anti-static bags in two rows of three, each containing one realistically sized "
        "28 mm movement or 40 mm watch case supported on a small inert foam pad. "
        "Only six paper labels, one affixed to the OUTSIDE of each bag: 1001, 1002, "
        "1003, 1004, 1005, 1006, each number appearing ONCE. No other numbered objects "
        "or trays. Fine moisture marks, not heavy rust or years of corrosion on gold. "
        "An ordinary pair of five-finger white nitrile gloves lies beside the bags. "
        "A closed clipboard with its blank back facing the camera and a laptop "
        "with its dark screen angled away sit at the far end: no invented readable "
        "text or duplicate inventory tables. All items touch the tabletop with "
        "coherent contact shadows and sensible scale. Modest office windows show "
        "low wooded Schaffhausen hills, no alpine peaks. Natural daylight." + STYLE,
        refinements=(
            "Keep this as a small sample with SIX closed bags and six distinct "
            "identifiers only. Every movement or case is physically supported inside "
            "one closed bag, not fused with another part. Each bag has exactly one "
            "OUTSIDE label; 1001, 1002, 1003, 1004, 1005 and 1006 each occur once. "
            "No extra labels, numbered trays, pseudo-English paperwork or heavily "
            "rusted precious metal. Preserve the table, glove pair, dark turned-away "
            "laptop and blank clipboard back. Keep all objects supported, realistically "
            "scaled, with shallow moisture marks and natural contact shadows.",
            "Minimal local correction only: the paper label on the UPPER RIGHT bag, "
            "containing an empty metal watch case, must read 1003, not 1002. "
            "Change just its last handwritten digit from 2 to 3, retaining the same "
            "ink, paper, scale and perspective. All other labels are already correct "
            "and MUST remain unchanged: upper left 1001, upper middle 1002, "
            "lower left 1004, lower middle 1005, lower right 1006. Preserve every "
            "other pixel and object; do not add or move components or bags.",
        ),
    ),
    Photo(
        "IMG_20260831_100512.jpg",
        "31.08.2026 10:05",
        "Besichtigung durch den Sachverständigen am Bearbeitungszentrum",
        "The same CNC machining centre and open electrical cabinet as in the reference photo, "
        "three days later and dry: a loss adjuster in a dark jacket photographs the opened "
        "control cabinet with a tablet while a facility manager in a grey work coat points at "
        "the damaged components; no numbered markers or dangling tags. The machine and "
        "cabinet remain electrically isolated with all their LEDs and displays dark. "
        "The tarpaulin has been removed and the floor is dry; the room lights are on "
        "from a separate safe supply. Keep the same machine, cabinet and workshop." + STYLE_PEOPLE,
        reference="IMG_20260828_113105.jpg",
        refinements=(
            "Correct the later inspection of this SAME CNC machine and control cabinet. "
            "The storm-damaged CNC machine and its open cabinet remain electrically "
            "isolated: all their displays, LEDs and machine lamps are dark. Room "
            "lighting may be on from a separate safe supply. The floor is now dry, "
            "cleaned of loose electrical cable loops and glass. Cabinet wiring is "
            "organized into actual terminals and cable glands, with no severed live "
            "cables on the floor. Remove any remaining tarp or drain bucket from "
            "the initial mitigation. The loss adjuster stands beside the OPEN cabinet "
            "and aims a tablet's REAR camera at its damaged internal components; "
            "the screen faces the adjuster, not the photographed subject. The facility "
            "manager points at a real component inside that cabinet, not an unrelated "
            "panel or empty air. Their hands, arms, tablet grip and feet are coherent, "
            "faces turned away. Damage tags hang by real ties. Keep the same machine "
            "enclosure, cabinet location and windows; no brand names.",
            "Minimal cleanup of this existing inspection photograph. REMOVE every "
            "yellow paper tag, numbered marker and dangling string from the two "
            "people, their clothes and trousers, the machine and the cabinet door. "
            "Leave no floating labels and no numbers on clothing. The storm-damaged "
            "CNC cabinet is disconnected: turn OFF its tiny green, amber and red "
            "indicator lights and those on the machine's control panel. Retain "
            "the room ceiling lights from their separate restored supply. Keep "
            "the cabinet open, wiring organized, floor dry, tablet held naturally "
            "and both people inspecting the same cabinet. Change nothing else.",
        ),
    ),
]
# Photos taken before the first notice (28.08.2026, 13:12)
EMAIL_1_PHOTOS = [
    photo.name
    for photo in PHOTOS
    if photo.taken.startswith("28.08.2026") and photo.taken[11:] < "13:12"
]
assert len(PHOTOS) == 10 and len(EMAIL_1_PHOTOS) == 6
FOOTER_DE = (
    "Fiktives Dokument — Demonstration PrevaIQ. Firma, Personen, Police und Beträge sind erfunden."
)
FOOTER_EN = "Fictitious document — PrevaIQ demonstration. Business, people, policy and amounts are invented."

PHOTO_EVIDENCE_DE = (
    "Fotografierte Ausschnitte: Die Atelieraufnahme zeigt zwei Werkplätze und zwei "
    "beschädigte Scheiben in einem Teil des Oblichtbands. Die Dachaufnahme zeigt "
    "separat die abgerissene Dämmung der opaken Dachfläche; Dämmstoff gehört nicht "
    "zum Glasaufbau der Oblichter. Im Atelier sind die opaken Innenverkleidungen "
    "geschlossen. Im Reinraum und in der Endkontrolle sind dagegen Deckenplatten "
    "infolge des Wassereintritts heruntergefallen.",
    "Die Nahaufnahme zeigt drei Uhrwerke, die Endkontrolle vier fertige Uhren in "
    "einem flachen Arbeitstablett und die Teilefertigung ein geöffnetes "
    "Bearbeitungszentrum. Die Inventuraufnahme zeigt sechs verpackte Musterteile "
    "mit den Nummern 1001 bis 1006. Am Folgetag sind zwei Trocknungsgeräte und ein "
    "Luftgebläse sowie abgedeckte Werkbänke im gleichen Atelier sichtbar.",
    "Nach den stärksten Böen drangen weiterhin Regen und Restwasser durch die "
    "Öffnungen und den Deckenhohlraum ein. Die Notabdeckung begann am 28.08. um "
    "14:30 Uhr; das Foto von 14:32 Uhr zeigt laufende Arbeiten, noch keine "
    "vollständige Abdichtung aller Oblichter. Im Atelier sind die beiden "
    "beschädigten Scheiben am Folgetag abgedeckt, lose Scherben entfernt und "
    "Instrumente zur Sicherung ausgeräumt. Die Trocknungsgeräte werden separat "
    "geschützt versorgt. Bei der Besichtigung am 31.08. ist die Raumbeleuchtung "
    "wieder eingeschaltet, das besichtigte Bearbeitungszentrum bleibt isoliert.",
    "Die Fotos sind kein Vollinventar und kein Nachweis für Feuchtigkeit im Gehäuse "
    "geschlossener Uhren, Irreparabilität, Gold- oder Platinfeingehalt oder konkrete "
    "Reparaturkosten. 312 Kaliber, 186 fertige Uhren und 24 Werkplätze sind der "
    "gemeldete Gesamtumfang, nicht die im Bild gezählten Gegenstände. Auch "
    "Lagerbestände, weitere Maschinen und der Betriebsunterbruch sind nicht "
    "vollständig fotografiert. Inventurlisten und technische Prüfberichte sowie "
    "Offerten und Betriebsunterlagen sind zur Prüfung beizuziehen; sie sind "
    "nicht Bestandteil der beigefügten Dateien. Die Beträge sind eine "
    "Schadenkalkulation unter Vorbehalt der sachverständigen Prüfung.",
)
PHOTO_EVIDENCE_EN = (
    "The photos show selected areas, not a complete inventory: two assembly stations "
    "and two damaged panes in one rooflight section, three movements in close-up, "
    "four finished watches lying in a flat work tray, one open machining centre and "
    "six bagged sample parts numbered 1001 to 1006. The next-day atelier view shows "
    "two dehumidifiers and one air mover after loose glass and instruments were removed.",
    "The torn insulation visible on the flat roof belongs to the opaque roof assembly, "
    "not the rooflight glazing. The atelier's opaque interior linings remain closed; "
    "water-damaged ceiling tiles have fallen in the lower-floor rooms. Rain and "
    "residual water continued entering and draining after the peak gusts. Emergency "
    "roof covering started at 14:30; the 14:32 photo shows work in progress, not "
    "completed sealing. The atelier's two damaged panes are covered in the next-day "
    "view. Drying equipment uses a separate protected supply. Room lighting is "
    "restored for the 31 August visit; the inspected machining centre remains isolated.",
    "Exterior droplets do not establish moisture inside sealed cases. The photos "
    "do not establish irreparability, precious-metal fineness or repair costs. "
    "The reported totals of 312 calibres, 186 finished watches and 24 workstations "
    "cover the wider inventory, not just the objects visible in these photos. "
    "Other stock, machines and business interruption are not fully photographed. "
    "The inventory lists and technical inspection reports, supplier quotes and "
    "business records must support the claimed quantities, repair scope and valuation; "
    "these records are available on request, not included in the attached files. "
    "The repair allowance, including the proposed watch revisions, remains subject "
    "to the loss adjuster's technical and financial review.",
)


def _amount_cell(amount: float, *, bold: bool = False) -> str:
    text = chf(amount).replace(" ", "&#160;")
    return f"<b>{text}</b>" if bold else text


# ── Claim form (Schadenmeldung) ──────────────────────────────────────────────


def claim_form_html() -> str:
    rows = [
        [f"{i}", label, _amount_cell(amount), note]
        for i, (label, _, amount, note, _) in enumerate(DAMAGES, 1)
    ]
    rows.append(["", "<b>Total geltend gemacht</b>", _amount_cell(TOTAL, bold=True), ""])
    photos = "".join(f"<li>{p.name} — {p.taken} — {p.caption}</li>" for p in PHOTOS)
    return (
        f"<h1>Schadenmeldung — KMU-Geschäftsversicherung</h1>"
        f"<p>{INSURER} · Schadenservice · {INSURER_EMAIL} · Schaden-Nr. {CLAIM_NO}</p>"
        + paragraphs(LOCATION_DE)
        + section(
            "1. Versicherungsnehmerin",
            table(
                ["Angabe", "Wert"],
                [
                    ["Firma", FIRM],
                    ["UID", UID],
                    ["Adresse", f"{STREET}, {TOWN}, Schweiz"],
                    [
                        "Tätigkeit",
                        "Manufaktur für mechanische Uhren mit Komplikationen, 128 Mitarbeitende",
                    ],
                    ["Kontaktperson", f"{COO}, {COO_TITLE}"],
                    ["Telefon", PHONE],
                    ["E-Mail", COO_EMAIL],
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
                    ["Versicherungsort", f"{STREET}, {TOWN} (Manufaktur, eigene Liegenschaft)"],
                    [
                        "Feuer und Elementar, Fahrhabe (Waren, Einrichtungen, Maschinen)",
                        f"{chf(SUM_INSURED_CONTENTS)} (Neuwert; Waren zu Herstellungskosten)",
                    ],
                    [
                        "Versicherungswert per 30.06.2026 (Inventar und Anlagenbuchhaltung)",
                        f"{chf(INSURABLE_VALUE)} — keine Unterversicherung",
                    ],
                    ["Wasser", chf(SUM_INSURED_CONTENTS)],
                    ["Diebstahl", chf(3_000_000)],
                    [
                        "Betriebsunterbruch (Ertragsausfall und Mehrkosten)",
                        f"{chf(SUM_INSURED_BI)}, Haftzeit 12 Monate",
                    ],
                    ["Kosten (Aufräumung, Notmassnahmen)", "Erstrisiko CHF 100'000"],
                    ["Glasbruch Mobiliar", "versichert"],
                    ["Gebäude", "<b>nicht Gegenstand der Police</b> (Kanton Schaffhausen: GVSH)"],
                    ["Selbstbehalt Elementar", "10 %, mindestens CHF 2'500, höchstens CHF 50'000"],
                ],
            ),
        )
        + section(
            "3. Schadenereignis",
            table(
                ["Angabe", "Wert"],
                [
                    ["Datum und Zeit", "Freitag, 28.08.2026, ca. 10:05–10:30 Uhr"],
                    ["Schadenort", f"{STREET}, {TOWN}"],
                    ["Ursache", "Sturm mit Orkanböen und Starkregen (Elementarschaden)"],
                    [
                        "Polizei / Behörden",
                        "Kein Polizeirapport (Naturereignis); Gebäude der "
                        f"GVSH gemeldet, Nr. {GVSH_REF}",
                    ],
                ],
            )
            + paragraphs(
                "Am Freitag, 28. August 2026, zog zwischen ca. 10:05 und 10:30 Uhr ein heftiger "
                "Sturm mit Orkanböen und Starkregen über Schaffhausen; die Messstation "
                "Schaffhausen verzeichnete eine Böenspitze von 142 km/h. Eine Böe riss auf dem "
                "Flachdach des Nordflügels rund 420 m² Dachhaut und Dämmung ab. Herumfliegende "
                "Dachteile zerschlugen 9 der 24 Scheiben des Oblichtbands über dem Atelier "
                "Grande Complication im 2. Obergeschoss.",
                "Während der stärksten Böen von ca. 10:05 bis 10:30 Uhr drang Regenwasser "
                "durch die Öffnungen ins Atelier ein. Auch danach gelangten weiterhin "
                "Regen und Restwasser durch die unverschlossenen Öffnungen und den "
                "Deckenhohlraum in den Reinraum und in die Endkontrolle im 1. Obergeschoss "
                "und über die Kabelkanäle in die Teilefertigung im Erdgeschoss. Betroffen sind "
                "die Uhrwerke in Montage, Komponenten und Halbfabrikate, die fertigen Uhren in der "
                "Endkontrolle, Zifferblätter, Maschinen, Werkbänke sowie Mess- und Prüfgeräte.",
                "Verletzt wurde niemand. Das Atelier wurde um 10:12 Uhr geräumt; die Werke in "
                "Montage wurden soweit möglich in die Tresore gebracht. Der Hauswart hat den "
                "Strom im Nordflügel um 10:20 Uhr aus Sicherheitsgründen abgeschaltet.",
            ),
        )
        + section(
            "4. Massnahmen zur Schadenminderung",
            paragraphs(
                "28.08.2026, ab 14:30 Uhr: Beginn der Notabdeckung des Daches und der "
                "Oblichter durch einen Dachdecker (über die GVSH). Das Foto von "
                "14:32 Uhr zeigt die laufenden Arbeiten. Bereits zuvor wurde an der "
                "isolierten Maschine eindringendes Wasser provisorisch abgeleitet.",
                "Ab 29.08.2026: Wasserabsaugung und Trocknung durch ein Sanierungsunternehmen. "
                "29.–30.08.2026: Inventur mit der Revisionsstelle; die beschädigten Teile sind "
                "nummeriert, verpackt und für die Besichtigung verschlossen gelagert.",
                "Ab 14.09.2026: Verlagerung der Endmontage ins Atelier Süd, um den "
                "Betriebsunterbruch zu mindern.",
            ),
        )
        + section(
            "5. Gebäudeschaden und kantonale Gebäudeversicherung",
            paragraphs(
                "Die Liegenschaft gehört der Versicherungsnehmerin. Dach, Oblichter, Decken und "
                "die Hülle des Reinraums wurden am 28.08.2026 der Gebäudeversicherung des "
                f"Kantons Schaffhausen (GVSH) gemeldet, GVSH-Schaden-Nr. {GVSH_REF}. Sie sind "
                "nicht Gegenstand dieser Schadenmeldung; die Notabdeckung des Daches wird der "
                "GVSH verrechnet."
            ),
        )
        + section(
            "6. Schadenaufstellung",
            table(["Pos.", "Bezeichnung", "Betrag", "Bemerkung"], rows)
            + paragraphs(
                f"Selbstbehalt Elementar gemäss Police: {chf(DEDUCTIBLE)} (10 %, höchstens "
                f"CHF 50'000). Bewertung: Waren zu Herstellungskosten, Maschinen und "
                "Einrichtungen zum Neuwert (AVB A3.1). Einzelheiten im beiliegenden "
                f"Kostenvoranschlag. Rechnerischer Nettobetrag: {chf(NET)}, "
                "vorbehaltlich der Prüfung von Deckung, Schadenumfang und Bewertung."
            ),
        )
        + section(
            "7. Beilagen",
            f"<ul><li>kostenvoranschlag-schadenbehebung.pdf — Kostenvoranschlag und Kalkulation "
            f"der Schadenbehebung (18.09.2026)</li>{photos}</ul>"
            + paragraphs(*PHOTO_EVIDENCE_DE)
            + paragraphs(
                "Auf Verlangen: Inventurlisten 29.–30.08.2026 mit Seriennummern, Offerten der "
                "Maschinenlieferanten, Rechnung des Sanierungsunternehmens, Budget 2026 und "
                "Jahresrechnungen 2024 und 2025."
            ),
        )
        + section(
            "8. Erklärung",
            paragraphs(
                "Die Unterzeichnenden bestätigen, dass die Angaben vollständig und "
                "wahrheitsgetreu sind, und ermächtigen die Versicherung, die zur Abklärung "
                "nötigen Auskünfte einzuholen.",
                f"Schaffhausen, 18.09.2026 — {COO}, {COO_TITLE}, und {CFO}, Finanzchefin "
                "(kollektiv zu zweien, elektronisch unterzeichnet)",
            ),
        )
    )


# ── Cost estimate (Kostenvoranschlag) ────────────────────────────────────────


def cost_estimate_html() -> str:
    rows = []
    for i, (label, _, amount, _, lines) in enumerate(DAMAGES, 1):
        rows.append([f"<b>{i}</b>", f"<b>{label}</b>", _amount_cell(amount, bold=True)])
        rows.extend(
            [f"{i}.{j}", text, _amount_cell(value)] for j, (text, value) in enumerate(lines, 1)
        )
    rows.append(["", "<b>Total</b>", _amount_cell(TOTAL, bold=True)])
    rows.append(["", "Selbstbehalt Elementar (AVB A5)", "– " + _amount_cell(DEDUCTIBLE)])
    rows.append(
        ["", "<b>Rechnerischer Nettobetrag (vor Prüfung)</b>", _amount_cell(NET, bold=True)]
    )
    return (
        "<h1>Kostenvoranschlag und Kalkulation der Schadenbehebung</h1>"
        f"<p>{FIRM} · {STREET}, {TOWN} · Schaden-Nr. {CLAIM_NO} · Police {POLICY}</p>"
        + paragraphs(LOCATION_DE)
        + section(
            "1. Grundlagen",
            paragraphs(
                "Inventur vom 29. und 30.08.2026 mit der Revisionsstelle; Rückverfolgung der "
                "Uhrwerke über die Seriennummern im ERP.",
                "Bewertung nach AVB A3.1: Waren (Uhrwerke, Komponenten, fertige Uhren, "
                "Zifferblätter) zu Herstellungskosten gemäss Betriebsabrechnung 2026, nicht zu "
                "Verkaufspreisen; Maschinen und Einrichtungen zum Neuwert gemäss Offerten der "
                "Lieferanten und Herstellerdiagnose vom 02.09.2026.",
                "Betriebsunterbruch nach AVB C3: Deckungsbeitrag gemäss Budget 2026, plausibilisiert "
                "mit den Jahresrechnungen 2024 und 2025; die Verlagerung der Endmontage ab "
                "14.09.2026 mindert den Ausfall, ihre Mehrkosten sind ausgewiesen.",
                "Nicht enthalten: Gebäude, Dach, Oblichter, Decken und Hülle des Reinraums "
                f"(GVSH, Schaden-Nr. {GVSH_REF}).",
            )
            + paragraphs(*PHOTO_EVIDENCE_DE),
        )
        + section("2. Kalkulation", table(["Pos.", "Gegenstand und Massnahme", "Betrag"], rows))
        + section(
            "3. Visum",
            paragraphs(
                f"Schaffhausen, 18.09.2026 — Controlling {FIRM}; geprüft von {CFO}, "
                "Finanzchefin. Die beschädigten Teile stehen dem Sachverständigen verpackt zur "
                "Verfügung."
            ),
        )
    )


# ── E-mails ──────────────────────────────────────────────────────────────────

EMAIL_1 = {
    "file": "email-01-schadenmeldung-de",
    "from": (COO, COO_EMAIL),
    "to": ("PrevaIQ Schadenservice", INSURER_EMAIL),
    "cc": (CFO, CFO_EMAIL),
    "date": "Fri, 28 Aug 2026 13:12:00 +0200",
    "date_label": "Freitag, 28. August 2026 13:12",
    "message_id": f"<20260828131200.0912@{DOMAIN}>",
    "subject": f"Schadenmeldung Sturm 28.08.2026 – Police {POLICY} – {FIRM}",
    "attachments": EMAIL_1_PHOTOS,
    "labels": ("Von", "Gesendet", "An", "Cc", "Betreff", "Anlagen"),
    "footer": FOOTER_DE,
    "body": f"""Sehr geehrte Damen und Herren

{LOCATION_DE}

Heute Vormittag, zwischen ca. 10:05 und 10:30 Uhr, hat der Sturm über Schaffhausen unsere Manufaktur am {STREET} schwer getroffen. Eine Böe hat auf dem Flachdach des Nordflügels rund 420 m² Dachhaut und Dämmung abgerissen; herumfliegende Dachteile haben 9 Scheiben des Oblichtbands über unserem Atelier Grande Complication zerschlagen. Der Regen ist ins Atelier eingedrungen und durch die Decke in den Reinraum, in die Endkontrolle und bis in die Teilefertigung gelaufen.

Nach den stärksten Böen dringt weiterhin Regen- und Restwasser durch die Öffnungen und den Deckenhohlraum ein. Die abgerissene Dämmung stammt aus der opaken Dachfläche, nicht aus den Oblichtscheiben.

Verletzt wurde niemand. Wir haben das Atelier um 10:12 Uhr geräumt und die Werke in Montage soweit möglich in die Tresore gebracht; der Strom im Nordflügel ist seit 10:20 Uhr abgeschaltet. Betroffen sind Uhrwerke in Montage, Komponenten, fertige Uhren in der Endkontrolle, Maschinen und Werkbänke. Nach einer ersten Einschätzung liegt der Schaden deutlich über CHF 10 Millionen.

Den Gebäudeschaden haben wir um 11:45 Uhr der GVSH gemeldet (Nr. {GVSH_REF}). Ein Dachdecker beginnt heute ab 14:30 Uhr mit der Notabdeckung, morgen früh beginnt ein Sanierungsunternehmen mit der Trocknung. Am Samstag und Sonntag führen wir mit unserer Revisionsstelle eine Inventur durch; die beschädigten Teile bewahren wir nummeriert und verpackt auf.

Im Anhang finden Sie sechs Fotos von heute Vormittag. Sie zeigen Ausschnitte: unter anderem drei Uhrwerke, vier fertige Uhren am Prüfplatz und ein Bearbeitungszentrum, nicht den gesamten betroffenen Bestand. Nasse Aussenflächen allein belegen keinen Innenschaden der Uhren. Die Mengen und Reparaturkosten müssen durch Inventur und technische Prüfung geklärt werden. Wegen der Grösse des Schadens bitten wir um eine möglichst rasche Besichtigung durch Ihren Sachverständigen.

Freundliche Grüsse

{COO}
{COO_TITLE}
{FIRM}
{STREET}, {TOWN}
Tel. {PHONE}
Police Nr. {POLICY}
""",
}

_estimate_lines = "\n".join(
    f"- {english}: {chf_en(amount)}" for _, english, amount, _, _ in DAMAGES
)
EMAIL_2 = {
    "file": "email-02-loss-estimate-en",
    "from": (CFO, CFO_EMAIL),
    "to": ("PrevaIQ Claims Service", INSURER_EMAIL),
    "cc": (COO, COO_EMAIL),
    "date": "Fri, 18 Sep 2026 17:40:00 +0200",
    "date_label": "Friday, 18 September 2026 17:40",
    "message_id": f"<20260918174000.0912@{DOMAIN}>",
    "subject": f"Claim {CLAIM_NO} – signed claim form, cost estimate and photos (windstorm 28 August 2026)",
    "attachments": [
        "schadenmeldung-geschaeftsversicherung.pdf",
        "kostenvoranschlag-schadenbehebung.pdf",
        *[p.name for p in PHOTOS],
    ],
    "labels": ("From", "Sent", "To", "Cc", "Subject", "Attachments"),
    "footer": FOOTER_EN,
    "body": f"""Dear Sir or Madam,

{LOCATION_EN}

Further to Martina Gerber's first notice of 28 August and the visit of your loss adjuster, Mr {ADJUSTER}, on 31 August (your claim no. {CLAIM_NO}, policy {POLICY}), please find attached our signed claim form, the cost estimate and the ten photos.

Our consolidated loss estimate amounts to {chf_en(TOTAL)}:
{_estimate_lines}

Photographic scope and limits:

{"\n\n".join(PHOTO_EVIDENCE_EN)}

For your assessment:

1. The building damage (roof, skylights, ceilings and the clean-room envelope) is handled by the cantonal building insurer GVSH under claim no. {GVSH_REF} and is not included. The emergency roof cover is invoiced to the GVSH.

2. Movements, components, finished watches and dials are valued at manufacturing cost under AVB A3.1, not at retail prices. Machines and equipment are valued at replacement cost based on the suppliers' quotes and their diagnosis of 2 September.

3. The inventory was counted with our statutory auditors on 29 and 30 August; every movement is traced by its serial number in our ERP. The damaged parts are kept numbered and packaged for your loss adjuster.

4. Our contents sum insured of {chf_en(SUM_INSURED_CONTENTS)} exceeds the insurable value of {chf_en(INSURABLE_VALUE)} at 30 June 2026, the business interruption estimate stays within the {chf_en(SUM_INSURED_BI)} sum insured, and the clean-up costs within the CHF 100,000 first-loss limit.

5. We note the Elementar deductible of {chf_en(DEDUCTIBLE)} (10 %, capped). The resulting estimated net is {chf_en(NET)}, subject to coverage, damage-scope and valuation review.

6. To limit the interruption, final assembly moved to our south workshop on 14 September; the haute complication workshop and the clean room are planned to restart on 30 November 2026.

The inventory lists, the suppliers' quotes, the restoration company's invoice, our 2026 budget and our 2024 and 2025 accounts are available on request.

Kind regards,

{CFO}
Chief Financial Officer
{FIRM}
{STREET}, {TOWN}, Switzerland
{PHONE}
""",
}


# ── Photos ───────────────────────────────────────────────────────────────────


def image_request_prompt(photo: Photo, instruction: str) -> str:
    if not photo.system_prompt:
        return instruction
    return f"{photo.system_prompt}\n\nSCENE REQUEST:\n{instruction}"


def generate_photos(names: list[str] | None = None) -> None:
    selected = set(names) if names else {photo.name for photo in PHOTOS}
    unknown = selected - {photo.name for photo in PHOTOS}
    if unknown:
        raise ValueError(f"Unknown photos: {', '.join(sorted(unknown))}")
    for photo in PHOTOS:
        if photo.name in selected and photo.reference and photo.reference not in selected:
            reference_path = SCENARIO_DIR / photo.reference
            if not reference_path.is_file():
                raise FileNotFoundError(f"Reference photo does not exist: {reference_path}")
    mai = MaiImages()
    originals: dict[str, bytes] = {}
    for photo in PHOTOS:
        if photo.name not in selected:
            continue
        print(f"Generating {photo.name} ({photo.caption})", flush=True)
        if photo.reference:
            reference = originals.get(photo.reference)
            if reference is None:
                reference = (SCENARIO_DIR / photo.reference).read_bytes()
            png = mai.edit(image_request_prompt(photo, photo.prompt), reference)
        else:
            png = mai.generate(image_request_prompt(photo, photo.prompt))
        for refinement in photo.refinements:
            png = mai.edit(image_request_prompt(photo, refinement), png)
        originals[photo.name] = png
        _save_jpeg(png, photo.name, SCENARIO_DIR)


def refine_photos(names: list[str]) -> None:
    """Apply the last refinement edit of each named photo to its existing file."""
    photos = {photo.name: photo for photo in PHOTOS}
    invalid = [name for name in names if name not in photos or not photos[name].refinements]
    if invalid:
        raise ValueError(f"No refinement defined for: {', '.join(invalid)}")
    for name in names:
        if not (SCENARIO_DIR / name).is_file():
            raise FileNotFoundError(f"Photo to refine does not exist: {SCENARIO_DIR / name}")
    mai = MaiImages()
    for photo in PHOTOS:
        if photo.name in names and photo.refinements:
            print(f"Refining {photo.name}", flush=True)
            _save_jpeg(
                mai.edit(
                    image_request_prompt(photo, photo.refinements[-1]),
                    (SCENARIO_DIR / photo.name).read_bytes(),
                ),
                photo.name,
                SCENARIO_DIR,
            )


DOCUMENTS = [
    ("schadenmeldung-geschaeftsversicherung.pdf", "claim form (German)"),
    ("kostenvoranschlag-schadenbehebung.pdf", "cost estimate (German)"),
    ("email-01-schadenmeldung-de.eml", "first notice e-mail (German)"),
    ("email-01-schadenmeldung-de.pdf", "print of the first notice e-mail"),
    ("email-02-loss-estimate-en.eml", "consolidated estimate e-mail (English)"),
    ("email-02-loss-estimate-en.pdf", "print of the consolidated estimate e-mail"),
]


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
            "system_instructions": photo.system_prompt,
            "edited_from": photo.reference,
            "refinement_prompts": list(photo.refinements),
        }
        if path.exists():
            entry["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        photos.append(entry)
    documents = [
        {
            "file": name,
            "kind": kind,
            "sha256": hashlib.sha256((SCENARIO_DIR / name).read_bytes()).hexdigest(),
        }
        for name, kind in DOCUMENTS
    ]
    manifest = {
        "scenario": "swiss-watch-storm",
        "title": f"Windstorm in Schaffhausen, 28.08.2026 — {FIRM}",
        "persona": "habitation_claims",
        "synthetic": True,
        "notice": "Business, people, policy, references, amounts, documents and photos are "
        "fictitious and created for the PrevaIQ demo. "
        + LOCATION_EN
        + " No real watch brand is used. The "
        "photos are AI-generated (MAI-Image-2.6), with minor localized status-indicator "
        "retouching in the two CNC photographs to match the machine-isolation timeline.",
        "generator": CREATOR,
        "policy_conditions": str(AVB_PATH.relative_to(ROOT)).replace("\\", "/"),
        "identity": {
            "company": FIRM,
            "uid": UID,
            "address": f"{STREET}, {TOWN}",
            "phone": PHONE,
            "iban": IBAN,
            "policy": POLICY,
            "claim": CLAIM_NO,
            "building_insurer_claim": GVSH_REF,
        },
        "identity_checks": IDENTITY_CHECKS,
        "map_anchor": MAP_ANCHOR,
        "event_sources": EVENT_SOURCES,
        "timeline": [{"when": when, "event": event} for when, event in TIMELINE],
        "amounts_chf": {english: amount for _, english, amount, _, _ in DAMAGES}
        | {"total": TOTAL, "deductible": DEDUCTIBLE, "net": NET},
        "attention_points": [],
        "photo_evidence_scope": {
            "de": list(PHOTO_EVIDENCE_DE),
            "en": list(PHOTO_EVIDENCE_EN),
        },
        "expected_outcome": EXPECTED_OUTCOME,
        "documents": documents,
        "photos": photos,
    }
    (SCENARIO_DIR / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--photos", nargs="*", metavar="PHOTO", help="generate all MAI photos or selected filenames"
    )
    parser.add_argument(
        "--refine",
        nargs="+",
        metavar="PHOTO",
        help="apply the last refinement edit to existing photos",
    )
    args = parser.parse_args()
    SCENARIO_DIR.mkdir(parents=True, exist_ok=True)

    if args.photos is not None:
        generate_photos(args.photos or None)
    if args.refine:
        refine_photos(args.refine)
    render_pdf(
        SCENARIO_DIR / "schadenmeldung-geschaeftsversicherung.pdf",
        claim_form_html(),
        FOOTER_DE,
        logo=True,
        title=f"Schadenmeldung {CLAIM_NO} — {FIRM}",
        author=COO,
        creator=CREATOR,
    )
    render_pdf(
        SCENARIO_DIR / "kostenvoranschlag-schadenbehebung.pdf",
        cost_estimate_html(),
        FOOTER_DE,
        logo=False,
        title=f"Kostenvoranschlag {CLAIM_NO} — {FIRM}",
        author=CFO,
        creator=CREATOR,
    )
    missing = write_email(EMAIL_1, SCENARIO_DIR, CREATOR) + write_email(
        EMAIL_2, SCENARIO_DIR, CREATOR
    )
    write_manifest()
    for path in sorted(SCENARIO_DIR.iterdir()):
        print(f"{path.relative_to(ROOT)}: {path.stat().st_size // 1024} KB")
    if missing:
        print(f"Not attached (run with --photos first): {', '.join(sorted(set(missing)))}")


if __name__ == "__main__":
    main()
