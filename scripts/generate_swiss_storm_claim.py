"""Generate the Swiss hailstorm demo claim: Winterthur chocolate maker, Friday 28.08.2026.

The business, people, policy, references and amounts are fictitious. A verified real address
is used only as a map anchor: neither the occupants nor the actual building are depicted or
reported as damaged. Identity checks are recorded in ``IDENTITY_CHECKS``. Writes:

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
CREATOR = "scripts/generate_swiss_storm_claim.py"
AVB_PATH = (
    ROOT / "assets" / "pdf" / "prevaiq" / "prevaiq-ch-avb-kmu-geschaeftsversicherung-2026.pdf"
)

# ── Fictitious identity (checked 05.11.2026, see IDENTITY_CHECKS) ────────────────
FIRM = "Schoggimanufaktur Eulachblick GmbH"
UID = "CHE-482.135.757"
STREET = "Steinberggasse 23"
TOWN = "8400 Winterthur"
LOCATION_DE = (
    "Demo-Kartenanker: Steinberggasse 23, 8400 Winterthur. Die Adresse ist real; Firma, "
    "Betriebsräume und Schaden sind erfunden. Die KI-Bilder zeigen nicht das reale Gebäude "
    "oder dessen Nutzer. Street View zeigt den realen Ort, nicht diese Schadensszenen."
)
LOCATION_EN = (
    "Demo map anchor: Steinberggasse 23, 8400 Winterthur. The address is real; the business, "
    "premises and loss are fictional. AI images do not depict the actual building or its "
    "occupants. Street View shows the real location, not these damage scenes."
)
MAP_ANCHOR = {
    "address": f"{STREET}, {TOWN}, Schweiz",
    "country": "CH",
    "purpose": "Real geocodable demo anchor only; fictional premises and loss",
    "official_source": "https://api3.geo.admin.ch/rest/services/ech/MapServer/"
    "ch.swisstopo.amtliches-gebaeudeadressverzeichnis/100820484",
    "official_coordinates": {"lat": 47.49821853637695, "lon": 8.729171752929688},
    "geocoder": "OpenStreetMap / Nominatim",
    "verified_result": {"lat": 47.4981698, "lon": 8.7292096, "level": "building"},
    "street_view": "External real-location view; coverage is provider-dependent, not damage evidence",
}
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
    "street": "Real demo anchor verified in the Swiss official building-address register and "
    "Nominatim; no claim about the actual occupants or building",
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
        "Als Verlust nach Kühlkettenunterbruch gemeldet; Temperatur- und Lebensmittelprüfung ausstehend",
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
        "Hailstorm (reported hail up to about 5 cm, gusts); retracted awning, retained cracked "
        "safety glazing, reported frame-joint leaks and short circuit; main fuse tripped",
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
    "Refrigerated goods (CHF 96,400) are reported lost through the power cut; the Kühlgut extension "
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
IMAGE_SYSTEM_INSTRUCTIONS = (
    "MANDATORY IMAGE INSTRUCTIONS. Create synthetic insurance-documentation photography, "
    "not disaster spectacle. The real map address is an anchor only: invent the premises, "
    "do not reproduce an actual occupant or identify a real damaged building. Gravity, "
    "structural support, contact shadows, object scale and water paths must be coherent. "
    "Show localized damage with a physically explicit cause, not an indoor hurricane. "
    "Wind-driven hail descends obliquely; an extended awning shelters glazing beneath it. "
    "Laminated safety glazing retains cracked fragments on its interlayer: no punched-out "
    "round holes, missing central chunks, projectile craters or suspended loose shards. "
    "In POST-STORM EXTERIOR scenes ONLY, hail is distributed over ALL exposed ground, "
    "with less beneath shelter and variable "
    "accumulation at drains and edges, never a decorative pile only below a broken window. "
    "Food in a working chocolate business is in closed showcases, packaging, lidded food "
    "containers or normal fitted machine covers; never stage open food under a roof leak. "
    "Intact glazing, frames, masonry and opaque roof layers remain distinct. Insulation "
    "never emerges from a window or glazed rooflight. Readable physical text must be "
    "German, except the fictional proper name Eulachblick and metric numerals/units. "
    "No invented English labels, gibberish, watermarks or overlays. "
)


@dataclass(frozen=True)
class Photo:
    name: str
    taken: str
    caption: str  # German, as listed in the claim form
    prompt: str
    reference: str | None = None  # earlier photo edited to keep the same shop
    refinements: tuple[str, ...] = ()  # edits applied after generation to remove AI artefacts
    system_prompt: str = ""


PHOTOS = [
    Photo(
        "IMG_20260826_183447.jpg",
        "26.08.2026 18:34",
        "Schaufenster am Mittwochabend (sichtbarer Bestandsausschnitt, vor dem Unwetter)",
        "26 August, 18:34. Eye-level view of an invented artisan chocolate shop in the level "
        "old-town setting of Winterthur. Ochre plaster frontage below two upper floors, "
        "dark-brown wooden shop window on the LEFT, 1.80 m wide and 2.10 m high, sill "
        "0.65 m above paving. Entrance door on the RIGHT, 0.95 m wide and 2.20 m high. "
        "Dark-green retractable fabric awning extended above both, visible articulated "
        "support arms bolted to masonry. Plain fixed sign Eulachblick above the awning "
        "cassette, no other writing. Two heavy 0.45 m planters on either side. "
        "The shop window is laminated safety glazing. Through intact glazing, a low "
        "display ledge holds CLOSED 0.20 m gift boxes, not exposed food. Pralines are "
        "in a separate CLOSED glass service showcase deeper inside the shop. "
        "A wood sales counter is perpendicular "
        "to the right return wall behind the window. Narrow level paved pedestrian street, "
        "opposite plastered urban buildings; no mountains, steep slope or invented landmark. "
        "Dry, ice-free paving, NO hail, snow, falling precipitation or damage: this is "
        "TWO DAYS BEFORE the storm. Warm interior lighting is ON before the storm." + STYLE,
        refinements=(
            "Preserve the complete shop photo, geometry, products, planters and evening "
            "lighting. Remove ALL writing from the glazing, entrance door, small facade "
            "plaque and boxes, leaving those surfaces blank and natural. The ONLY readable "
            "text is the Eulachblick name on the fixed sign above the awning cassette. "
            "Keep every gift box closed and the interior food showcase fully glazed. Do not invent text "
            "or alter the architecture. This photo is TWO DAYS BEFORE the storm: remove "
            "ALL hail, ice, snow and falling precipitation from the ENTIRE image, leaving "
            "ordinary dry stone paving and intact glass. Do not apply post-storm hail "
            "instructions here. Place a few closed chocolate gift boxes on the dry "
            "low window ledge, while actual pralines remain behind the inner showcase glass.",
        ),
        system_prompt="BEFORE-STORM EXTERIOR. Establish repeatable door/window/awning geometry. "
        "This is a stock sample, not the full reported inventory. All glazing and supports intact. "
        "ABSOLUTELY NO HAIL OR ICE: the storm has not happened. Dry weather and paving.",
    ),
    Photo(
        "IMG_20260828_104112.jpg",
        "28.08.2026 10:41",
        "Fassade: eingefahrene Markise, gerissenes Verbundsicherheitsglas ohne Durchbruch",
        "Edit the reference to 28 August, 10:41, overcast AFTER the storm. Preserve exact "
        "camera position, urban surroundings, door/window dimensions, wooden frames, sign "
        "and heavy planters. Interior electric lighting entirely OFF after main fuse trip. "
        "The awning was FULLY RETRACTED before the storm: folded support arms tucked "
        "against the wall, fabric rolled inside its cassette, only a short damaged "
        "valance visible. No projecting canopy shelters the large pane. Obliquely "
        "descending wind-driven hail has cracked the LEFT laminated shop pane at several "
        "separate impact sites, mainly its exposed lower-left and mid-left areas: "
        "asymmetric short radial cracks branching into longer irregular connecting "
        "fractures. Some small whitish impact bruises, but the interlayer holds ALL "
        "glass in the frame and the entire pane remains a continuous barrier. NO HOLE, "
        "no missing glass, no black void, no circular crater, no loose floor shards. "
        "Closed gift boxes and a second closed glass food showcase remain protected "
        "behind it. Melting hail of varied 0.5-2 cm sizes is scattered across the ENTIRE "
        "visible exposed pavement from foreground to distant street, both left and "
        "right of the shop and beneath both planters' surroundings. Modest irregular "
        "clusters at paving joints/drainage, a few larger stones, not one pile at the "
        "window. Ground remains mostly visible, no uniform snow blanket. Door glass, "
        "upper windows, masonry and heavy planters intact. Few wet leaves." + STYLE,
        reference="IMG_20260826_183447.jpg",
        refinements=(
            "Preserve the shop, retracted awning, retained laminated glazing and distributed "
            "hail. The fractured pane remains present everywhere: if any gap or black "
            "hole appeared, restore glass and show fine branching cracks at that location. "
            "Do not draw a circular impact ring. Hail remains scattered across all "
            "exposed foreground and street areas, not just beneath the window. Remove "
            "all writing except Eulachblick on the fixed sign. All food stays enclosed. "
            "ALL interior light sources must be OFF, including pendant bulbs and "
            "ceiling spots; no artificial pools of warm light. Natural overcast daylight "
            "can reflect on wood and glazing. Turn OFF the food-showcase LED strips "
            "and all back-counter strip lighting too. The unpowered interior is "
            "noticeably DIMMER than the outdoor facade; shelves and gold-coloured "
            "trim are not luminous. Do not remove the cracks or extend the awning.",
        ),
        system_prompt="AFTER-STORM EXTERIOR. Change damage, weather and lights only; preserve "
        "the before-photo architecture. Retract the awning BEFORE hail damage. "
        "Retained laminated safety glass, NO opening through the pane. Ground-wide hail distribution.",
    ),
    Photo(
        "IMG_20260828_104355.jpg",
        "28.08.2026 10:43",
        "Hagelkörner mit Massstab; gemeldete Grösse bis ca. 5 cm, keine kalibrierte Messung",
        "28 August 10:43, near-vertical close-up of wet grey small stone paving, stones "
        "approximately 10 by 10 cm with narrow mortar joints. One irregular melting hailstone "
        "about 4.5-5 cm across, several smaller 1-2 cm hailstones. A straight 15 cm metric "
        "steel ruler lies FLAT beside it, in the SAME plane, horizontal across the lower "
        "frame. One scale only, equal centimetre intervals numbered in increasing order "
        "0 through 15, millimetre ticks, no inch scale, no folding hinges. Largest ice piece "
        "beside the ruler spans about five centimetre intervals, not five millimetres. "
        "Thin meltwater film, soft overcast light, no people or hands, no labels." + STYLE,
        system_prompt="HAIL SCALE CLOSE-UP. The ice and straight ruler share one plane with "
        "no perspective size trick. Ice is irregular, translucent, melting, not oversized snowballs.",
    ),
    Photo(
        "IMG_20260828_105207.jpg",
        "28.08.2026 10:52",
        "Verkaufsraum: Glasrisse bleiben gebunden; lokale Nässe am unteren Rahmen",
        "Use the same reference shop but photograph the window from INSIDE at close "
        "range, looking slightly down from 1.5 m eye height. Tight composition includes "
        "ONLY the dark-brown window frame, continuous cracked laminated pane, low "
        "display plinth and adjacent tiled floor. No door, ceiling or lamps in frame. "
        "The pane is 1.80 by 2.10 m; its lower ledge is 0.65 m high and 0.40 m deep. "
        "From INSIDE the impact area reverses to the LOWER RIGHT and mid-right. Fine "
        "asymmetric radial cracks merge with irregular longer fractures, fragments "
        "still bonded to the interlayer. Entire glazing remains present, no hole or "
        "missing chunk, no loose shards inside. Outside view is seen THROUGH intact "
        "cracked glass, with faint reflections and rain droplets; scattered hail "
        "continues across exposed paving outside. A localized rainwater track starts "
        "at the storm-loosened lower frame/weather seal, runs down the plinth corner "
        "and forms a SMALL shallow patch below. No water crossing solid glass, no "
        "central-room flood. NO gift boxes, cartons, chocolates or food in this tight "
        "frame: the protected stock and service showcase are elsewhere, OUT OF VIEW. "
        "The interior stone ledge is completely empty. Through the pane show only "
        "outdoor stone paving, curb and scattered hail, never a shelf or food outside. "
        "natural grey daylight only, no artificial lighting or readable text." + STYLE,
        reference="IMG_20260828_104112.jpg",
        refinements=(
            "Keep the tight interior framing. The ENTIRE laminated pane stays physically "
            "present; retain realistic branching cracks but fill any accidentally "
            "missing glass with transparent cracked glazing. No circular crater or "
            "loose shards on ledge/floor. Keep only a localized wet track from the "
            "lower frame corner to the floor, not rain through the solid pane. REMOVE "
            "BOTH gift boxes completely; do NOT move or replace them. Remove ALL "
            "cartons, ribbons, food, trays and display items from the entire image. "
            "Leave the stone window ledge completely EMPTY. Protected stock is "
            "elsewhere outside this tight camera frame. Through the glass show "
            "only outdoor paving and hail, never an outdoor shelf or food. "
            "Outside hail is scattered across the "
            "exposed street, not concentrated at this window. Remove invented writing.",
        ),
        system_prompt="SHOP INTERIOR AT 10:52. Maintain front/rear and left/right geometry "
        "when reversing the camera. Cracked laminated glass stays retained. Limited "
        "frame-seal leakage, not rain through a hole. Food enclosed. Power is OFF.",
    ),
    Photo(
        "IMG_20260828_112604.jpg",
        "28.08.2026 11:26",
        "Atelier: undichter Oblichtrahmen, nasses Maschinengehäuse; Schokolade unter Deckeln",
        "28 August 11:26. Ground-floor workshop in a SINGLE-STOREY REAR ANNEX behind the "
        "multi-storey street shop, not a skylight through occupied upper floors. Room "
        "6 by 8 m, ceiling 3.1 m; intact white opaque roof soffit surrounds a raised glazed "
        "rooflight 1.2 by 2.4 m, divided by supported aluminium mullions into four panes. "
        "One laminated safety-glass pane has branching impact fractures, all fragments "
        "retained, NO OPEN HOLE or hanging shards. A storm-loosened weather seal at "
        "one rooflight FRAME corner leaks residual water; droplets descend from that "
        "frame joint, not through solid glass, onto the OUTER SIDE casing of ONE "
        "floor-standing stainless chocolate tempering machine, 0.65 m wide, 0.85 m "
        "deep, 1.15 m high. Its small 25-litre round bowl has its NORMAL CLOSED fitted "
        "stainless food-protection lid, already in place during the interruption, "
        "not an improvised storm tarp. No uncovered chocolate underneath the leak. "
        "Water traces down the external casing to a shallow transparent local puddle "
        "on 0.20 m floor tiles. Clear water only: the indoor floor has NO ice, hail, "
        "glass, white fragments, plaster debris or foam. Nothing has fallen through "
        "the retained rooflight. This is a working hygienic professional chocolate kitchen: "
        "stainless workbench 0.90 m high, GN food containers with FULLY CLOSED FLAT "
        "STAINLESS LIDS covering their entire openings, covered chocolate "
        "storage tubs, stacked clean polycarbonate praline moulds, bowl scrapers, "
        "an unplugged digital scale, a stainless wash sink with ordinary mixer tap. "
        "The lower bench shelf holds ONLY closed white food-storage tubs, no open "
        "pans, no brown exposed ingredients. All small utensils on dry bench AWAY "
        "from the dripping corner, not scattered "
        "on the floor. A CLOSED glass-lidded tray of small chocolate pralines on that "
        "dry bench shows what is made here, not a row of exposed food. Enrober 1.0 m wide and "
        "cooling tunnel in background, stable and correctly supported, 0.9 m access aisle. "
        "All screens, lamps, belts and indicators OFF after fuse trip; no exposed live "
        "wiring. No tarp yet: emergency covering occurs only at 14:00. No people under "
        "broken glass, no hazardous staging. Daylight through rooflight." + STYLE,
        refinements=(
            "Keep this professional chocolate kitchen geometry, retained cracked safety "
            "rooflight glazing, intact white opaque soffit, supported machines, real "
            "kitchen utensils and covered food. Water drips from ONE FRAME JOINT onto "
            "external casing only, never through unbroken glass or into open chocolate. "
            "Keep the normal stainless bowl lid CLOSED, all GN containers lidded, any "
            "visible pralines under a closed transparent food cover. Correct the "
            "power-isolated state: every machine screen is "
            "opaque matte BLACK; every tiny blue, green, red or amber status LED is DARK "
            "and unlit, including the front tempering machine and right-side enrober. "
            "Keep physical buttons and housings, but no coloured glow. Remove the wall "
            "clock, the left framed slogans, the right handwritten slogan and all other "
            "writing except the German door label LAGER. Leave clean plain walls. "
            "The floor has ONLY a shallow CLEAR WATER puddle: remove every white "
            "fragment, glass shard, ice pellet, foam patch and plaster crumb beneath "
            "the machine. The retained pane sheds no glass into the kitchen. On the "
            "bench and lower shelf, fit flat stainless lids to EVERY GN pan; do not "
            "leave open chocolate or ingredients in the storage pans. Transparent "
            "food covers stay shut. No new damage, no tarp, no insulation in glazing.",
        ),
        system_prompt="REAR-ANNEX WORKSHOP AT 11:26. Opaque roof construction and glazed "
        "rooflight are separate; drainage follows gravity. Equipment is not powered. "
        "Photo supports external wetting of one machine, not a diagnosis of every machine.",
    ),
    Photo(
        "IMG_20260829_150418.jpg",
        "29.08.2026 15:04",
        "Kühlraum nach Stromrückkehr: Anzeige 23,8 °C; Teilbestand, kein Verderbnachweis",
        "29 August 15:04, four minutes AFTER power restoration. A dry intact walk-in cold "
        "room at the rear of the workshop, 2.4 by 3.0 m, ceiling 2.3 m. View from open "
        "0.85 m door, light from doorway. Insulated metal wall panels, intact ceiling, "
        "dry non-slip floor, correctly mounted evaporator, refrigeration only just "
        "restarting. Wall thermometer at eye level displays exactly '23,8 °C', one "
        "decimal comma, no duplicate readouts or other writing. Metal shelves 0.45 m "
        "deep on left and right, four shelves each, stable plain dry cardboard cartons "
        "0.30 by 0.20 by 0.15 m, bottom shelf 0.15 m clear of floor, 1.0 m clear central "
        "aisle. One 0.40 by 0.30 m tray fully supported on shelf holds small 2.5 cm "
        "truffles, mostly retaining shape with slight softened glossy edges only. "
        "No puddles, dripping chocolate, soaking or sagging cartons, frost or dramatic "
        "condensation. Warmed food may be unsafe without spectacular visible melting." + STYLE,
        system_prompt="COLD ROOM AT 15:04 NEXT DAY. Warming during an outage does not cause "
        "rain damage in this intact room. This is a temperature/stock sample, not visual "
        "proof of microbiological spoilage or total inventory loss. Correct human-scale storage.",
    ),
]
EMAIL_1_PHOTOS = [photo.name for photo in PHOTOS if photo.taken.startswith("28.08.2026")]
FOOTER_DE = (
    "Fiktives Dokument — Demonstration PrevaIQ. Firma, Personen, Police und Beträge sind erfunden."
)
FOOTER_EN = "Fictitious document — PrevaIQ demonstration. Business, people, policy and amounts are invented."
PHOTO_EVIDENCE_DE = (
    "Die Fotos zeigen nur Ausschnitte des gemeldeten Bestands und Schadens, nicht die "
    "vollständigen Mengen oder den Wert. Im Szenario wurde die Markise vor dem Unwetter "
    "eingefahren. Windgetriebener Hagel traf die ungeschützte Fassade schräg von oben. "
    "Das Verbundsicherheitsglas an Schaufenster und Oblicht ist gerissen, bleibt aber "
    "in der Zwischenschicht gebunden: keine ausgestanzten Löcher oder offenen Glasdurchbrüche.",
    "Der gemeldete Wassereintritt erfolgt an sturmbedingt gelockerten Rahmenanschlüssen, "
    "nicht durch geschlossene Glasscheiben. Feuchte Spuren liegen lokal an der "
    "Schaufensterecke und unter einem Oblichtrahmen des eingeschossigen rückwärtigen "
    "Anbaus; Ursache und Umfang der Undichtigkeiten sind technisch zu prüfen. Am 28.08. "
    "um 11:26 ist noch keine äussere Notabdeckung angebracht. Die Temperierschüssel "
    "hat ihren normalen geschlossenen Lebensmitteldeckel; Waren, Pralinés und Zutaten "
    "stehen in geschlossenen Verpackungen, Vitrinen oder abgedeckten Behältern. "
    "Glasrisse allein belegen keine Kontamination aller Waren.",
    "Die Temperiermaschine ist äusserlich nass; der gemeldete Kurzschluss und der "
    "Reparaturumfang aller Anlagen müssen technisch geprüft werden. Der Massstab beim "
    "Hagel ist eine illustrative Grössenreferenz, keine kalibrierte Messung.",
    "Das Kühlraumfoto zeigt einen Teilbestand und die Anzeige 23,8 °C kurz nach "
    "Stromrückkehr, nicht den gesamten Temperaturverlauf oder einen mikrobiologischen "
    "Verderbnachweis. Die Verpackungen im intakten Kühlraum sind trocken. Den Verlust "
    "der Kühlware meldet die Versicherungsnehmerin aufgrund der unterbrochenen Kühlkette; "
    "Temperaturprotokolle und lebensmitteltechnische Prüfung bleiben erforderlich.",
    "Alle Beträge sind vorläufige Forderungen. Inventarlisten, technische Berichte, "
    "Temperaturprotokolle, Offerten und Geschäftsunterlagen sind nicht beigefügt.",
)
PHOTO_EVIDENCE_EN = (
    "The photos show selected stock and damage, not the full inventory or its value. "
    "In the scenario the awning was retracted before the storm. Wind-driven hail struck "
    "the exposed facade obliquely from above. The laminated glazing in the shop window "
    "and rooflight is cracked but retained on its interlayer: no punched-out holes "
    "or open glass breaches.",
    "Reported water ingress is through storm-loosened frame joints, not solid glazing. "
    "Wet tracks are local to the shop-window corner and one rooflight-frame joint in the "
    "single-storey rear annex; the cause and extent of leaks require technical assessment. "
    "No external emergency cover is present at 11:26. The tempering bowl has its normal "
    "closed food-protection lid; stock, pralines and ingredients are in closed packaging, "
    "showcases or covered containers. Cracked glass alone does not establish contamination "
    "of all stock.",
    "One tempering machine is externally wet; the reported short circuit and repair scope "
    "of all equipment require technical assessment. The hail ruler is an illustrative "
    "size reference, not a calibrated measurement.",
    "The cold-room photo shows selected stock and a 23.8 °C readout shortly after power "
    "restoration, not the temperature history or microbiological proof of spoilage. "
    "Cartons in the intact cold room are dry. The insured reports refrigerated-stock loss "
    "because of the interrupted cold chain; temperature records and food-safety assessment "
    "remain necessary.",
    "All amounts are provisional demands. Inventory lists, technical reports, temperature "
    "records, quotes and business records are not attached.",
)


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
        + paragraphs(LOCATION_DE)
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
                "ca. 5 cm Durchmesser wurden gemeldet. Das Schaufenster unseres Ladens und "
                "ein Teil des Oblichts über dem Atelier im eingeschossigen rückwärtigen "
                "Anbau wurden beschädigt. Die Markise war vor dem Unwetter eingefahren; "
                "ihr kurzer Volant wurde lokal zerrissen. Windgetriebener Hagel traf die "
                "Fassade schräg von oben. Die gerissenen Verbundsicherheitsscheiben bleiben "
                "gebunden, ohne offene Durchbrüche. Regenwasser trat nach unserer Beobachtung "
                "an gelockerten Rahmenanschlüssen in den Verkaufsraum und ins Atelier ein; "
                "der genaue Eintrittsweg muss technisch geprüft werden. Die Schokolade "
                "war durch geschlossene Vitrinen, Verpackungen und normale Behälter- "
                "beziehungsweise Maschinendeckel geschützt.",
                "Nach Angaben der Betreiberin entstand an der Temperiermaschine ein Kurzschluss, "
                "die Hauptsicherung löste aus; ein technischer Bericht steht noch aus. "
                "Der Elektro-Notdienst hat die Stromversorgung um 11:30 Uhr aus "
                "Sicherheitsgründen abgestellt; sie wurde erst am Samstag, 29. August 2026, um "
                "15:00 Uhr wieder eingeschaltet. In dieser Zeit stieg die Temperatur im Kühlraum "
                "auf 23,8 °C; die dort gelagerten Pralinés, Truffes und Ganache-Halbfabrikate "
                "werden wegen der unterbrochenen Kühlkette als Verlust gemeldet. "
                "Der einzelne Temperaturwert belegt nicht allein Verderb und Gesamtverlust.",
                "Ein grosser Teil des Warenvorrats für die Herbst- und Weihnachtssaison, die "
                "Ladeneinrichtung und mehrere Produktionsmaschinen sind beschädigt. Der Betrieb "
                "ist bis auf Weiteres geschlossen.",
            ),
        )
        + section(
            "4. Massnahmen zur Schadenminderung",
            paragraphs(
                "28.08.2026, 14:00 Uhr: Notverglasung durch einen Glaser-Notdienst, Abdeckung des "
                "Oblichts mit einer äusseren Plane, zusätzliche äussere Abdeckung der Maschinen. "
                "Normale Lebensmitteldeckel waren bereits zuvor geschlossen.",
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
            "7a. Aussagegrenzen der fotografischen Belege",
            paragraphs(*PHOTO_EVIDENCE_DE),
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

{LOCATION_DE}

Heute Morgen, zwischen ca. 09:50 und 10:20 Uhr, hat ein heftiges Hagelgewitter unser Geschäft an der {STREET} in Winterthur schwer beschädigt. Die Markise war zuvor eingefahren; der kurze Volant wurde beschädigt. Windgetriebener Hagel traf die Fassade schräg von oben. Das Verbundsicherheitsglas am Schaufenster und an einem Teil des Oblichts über dem Atelier im eingeschossigen rückwärtigen Anbau ist gerissen, bleibt aber gebunden, ohne offene Glasdurchbrüche. An gelockerten Rahmenanschlüssen beobachten wir Regenwassereintritt; der genaue Eintrittsweg ist noch zu prüfen. Waren und Lebensmittel waren in geschlossenen Vitrinen, Verpackungen oder unter normalen Deckeln geschützt. Das Maschinengehäuse ist dennoch äusserlich nass. An der Temperiermaschine vermuten wir einen Kurzschluss; die Hauptsicherung löste aus. Der Elektro-Notdienst hat den Strom um 11:30 Uhr zusätzlich aus Sicherheitsgründen abgestellt. Ein technischer Bericht steht aus. Wann der Strom wieder eingeschaltet werden kann, ist noch offen – im Kühlraum lagern Pralinés und Truffes für den Herbstverkauf.

Um 14:00 Uhr wurden die Notverglasung, die äussere Notabdeckung des Oblichts und zusätzliche äussere Maschinenabdeckungen durchgeführt. Die normalen Lebensmitteldeckel waren bereits zuvor geschlossen. Die vier Vormittagsfotos zeigen den Zustand vor diesen äusseren Notmassnahmen. Sie belegen weder Kontamination aller Waren noch den gesamten Reparaturumfang. Die Liegenschaftsverwaltung meldet den Gebäudeschaden der GVZ.

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

{LOCATION_EN}

Our provisional consolidated loss estimate amounts to {chf_en(TOTAL)}:
{_estimate_lines}

A few points for your assessment:

1. The main fuse tripped during the storm; the emergency electrician additionally isolated the supply on 28 August at 11:30. Power was restored on 29 August at 15:00. The photo at 15:04 shows a 23.8 °C readout shortly after restoration. We report the refrigerated contents as lost because of the interrupted cold chain, subject to temperature-record and food-safety review. We understand that our policy may not include the refrigerated goods extension; as the power cut was a direct consequence of the hailstorm, we ask you to consider this loss as part of the storm damage.

2. The property management has also reported the building damage to the GVZ (GVZ claim no. {GVZ_REF}). We renewed the shop window and the skylight ourselves in 2019 as tenant improvements, which is why we include them here.

3. The photo dated Wednesday 26 August (18:34) shows selected shop-window stock two days before the storm. It is not damage evidence or proof of the complete inventory.

Photographic evidence and limits:
{chr(10).join(PHOTO_EVIDENCE_EN)}

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


def _mail_attachment(name: str, scenario_dir: Path = SCENARIO_DIR) -> tuple[bytes, str, str] | None:
    """Attachment as sent by a phone mail client: photos downscaled to 1024 px."""
    path = scenario_dir / name
    if not path.exists():
        return None
    if path.suffix == ".pdf":
        return path.read_bytes(), "application", "pdf"
    pixmap = fitz.Pixmap(path.read_bytes())
    scale = min(1.0, 1024 / max(pixmap.width, pixmap.height))
    if scale < 1.0:
        pixmap = fitz.Pixmap(pixmap, round(pixmap.width * scale), round(pixmap.height * scale))
    return pixmap.tobytes("jpg", jpg_quality=78), "image", "jpeg"


def write_email(mail: dict, scenario_dir: Path = SCENARIO_DIR, creator: str = CREATOR) -> list[str]:
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
        attachment = _mail_attachment(name, scenario_dir)
        if attachment is None:
            missing.append(name)
            continue
        content, maintype, subtype = attachment
        message.add_attachment(content, maintype=maintype, subtype=subtype, filename=name)
        attached.append((name, len(content)))
    (scenario_dir / f"{mail['file']}.eml").write_bytes(message.as_bytes(policy=policy.SMTP))

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
        scenario_dir / f"{mail['file']}.pdf",
        html,
        mail["footer"],
        logo=False,
        title=mail["subject"],
        author=mail["from"][0],
        creator=creator,
    )
    return missing


# ── Rendering ────────────────────────────────────────────────────────────────


def render_pdf(
    path: Path,
    html: str,
    footer: str,
    *,
    logo: bool,
    title: str,
    author: str,
    creator: str = CREATOR,
) -> None:
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
            "creator": creator,
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


def _save_jpeg(png: bytes, name: str, scenario_dir: Path = SCENARIO_DIR) -> None:
    pixmap = fitz.Pixmap(png)
    if pixmap.alpha:
        pixmap = fitz.Pixmap(pixmap, 0)
    (scenario_dir / name).write_bytes(pixmap.tobytes("jpg", jpg_quality=86))
    print(f"  {pixmap.width}x{pixmap.height}", flush=True)


def image_request_prompt(photo: Photo, instruction: str) -> str:
    return f"{IMAGE_SYSTEM_INSTRUCTIONS}\n{photo.system_prompt}\n\nSCENE REQUEST:\n{instruction}"


def generate_photos(names: list[str] | None = None) -> None:
    selected = set(names) if names else {photo.name for photo in PHOTOS}
    unknown = selected - {photo.name for photo in PHOTOS}
    if unknown:
        raise ValueError(f"Unknown photos: {', '.join(sorted(unknown))}")
    for photo in PHOTOS:
        if photo.name in selected and photo.reference and photo.reference not in selected:
            path = SCENARIO_DIR / photo.reference
            if not path.is_file():
                raise FileNotFoundError(f"Reference photo does not exist: {path}")
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
        _save_jpeg(png, photo.name)


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
            "system_instructions": IMAGE_SYSTEM_INSTRUCTIONS + photo.system_prompt,
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
        "fictitious and created for the PrevaIQ demo. "
        + LOCATION_EN
        + " The photos are AI-generated (MAI-Image-2.6).",
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
        "map_anchor": MAP_ANCHOR,
        "photo_evidence_scope": {"de": list(PHOTO_EVIDENCE_DE), "en": list(PHOTO_EVIDENCE_EN)},
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
    parser.add_argument(
        "--photos",
        nargs="*",
        metavar="PHOTO",
        help="(re)generate all MAI photos, or only the named photos",
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
        generate_photos(args.photos)
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
