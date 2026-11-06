"""Generate an unofficial Microsoft/GitHub luxury wristwatch concept, not claim evidence.

Usage:
    python scripts/generate_luxury_watch_concept.py --microsoft-logo PATH --github-logo PATH
    Add --reference-watch PATH to use a product screenshot for construction, not branding.

Supply the original logo files from the sources below. Uses the same MAI-Image-2.6
deployment and Entra authentication as the Swiss claim photo generator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import fitz

from generate_swiss_storm_claim import MAI_MODEL, MAI_VERSION, MaiImages, _save_jpeg

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "assets" / "design-concepts" / "rheinkaliber"
NAME = "rheinkaliber-microsoft-github-wrist.jpg"
LOGO_SOURCES = {
    "microsoft": "https://uhf.microsoft.com/images/microsoft/RE1Mu3b.png",
    "github": "https://github.githubassets.com/images/modules/logos_page/GitHub-Mark.png",
}
PROMPT = (
    "The reference image contains the authentic Microsoft and GitHub logos. Use those exact "
    "symbol geometries as reference for two exquisitely crafted dial inlays, not as background "
    "graphics. Create a single photorealistic luxury editorial wrist shot of an original "
    "Swiss haute horlogerie wristwatch worn naturally on an adult's left wrist. This is an "
    "unofficial fictional design concept, not a real Microsoft or GitHub product. "
    "A 40 mm warm rose-gold round case with very fine brushed sides, polished slim bezel, "
    "elegant slender lugs, anti-reflective sapphire crystal, midnight navy blue guilloche dial, "
    "exactly twelve evenly spaced applied rose-gold baton hour markers, a complete regular "
    "60-division minute track, exactly THREE central hands on ONE shared central pinion: "
    "a short broad hour hand just past 10, a longer minute hand pointing at 2, and one fine "
    "seconds hand pointing at 7. The displayed time is 10:10:35. NO subdials, NO small "
    "seconds, NO additional hands, NO date aperture. Deep brown hand-stitched leather strap and "
    "a glimpse of an ivory shirt cuff under a dark navy tailored jacket. "
    "Integrate the Microsoft four-square symbol just below the 12 o'clock marker as a small "
    "cloisonne enamel inlay: four equal squares, authentic red upper left, green upper right, "
    "blue lower left, yellow lower right, thin regular cross-shaped negative space. "
    "Just above the 6 o'clock marker integrate the authentic black GitHub Invertocat inside a small "
    "ivory enamel medallion. Both emblems are flush-set into the dial, with accurate shapes, "
    "subtle material reflections and the same perspective as the dial; not stickers, "
    "not floating graphics, not huge logos; neither emblem replaces, overlaps or displaces "
    "any hour marker or the minute track. Both emblems share the dial's vertical 12-to-6 axis. "
    "The only dial word is the fictional maker "
    "'RHEINKALIBER' in small refined uppercase lettering under the Microsoft inlay. "
    "Do not add real watch brand names or copy the example's distinctive dial design. "
    "If the reference sheet includes a real product photograph, use it ONLY to understand "
    "ordinary watch construction: circular dial, rational concentric hands, correctly "
    "attached crown at the dial's 3 o'clock axis, four coherent lugs, spring bars and strap. "
    "Keep our own rose-gold, navy and brown design and the two technology emblems. "
    "A plausible 40 mm case, about 10 mm thick, with 20 mm lug spacing and a restrained bezel. "
    "View almost straight on to the dial with a restrained three-quarter angle; the two "
    "emblems must be unobstructed by the hands, sharp and clearly recognizable. "
    "Wrist anatomically plausible with natural skin pores and fine arm hair, case and strap "
    "properly wrapping the wrist without passing through skin, four lugs joined to the case, "
    "two spring bars each joining one pair of lugs, each leather strap end actually held "
    "between its corresponding lugs, a snug but not constricting fit, a case smaller than "
    "the wrist width, realistic scale and contact shadows. Wrist and watch fill "
    "most of the square frame, focus precisely on the dial, soft neutral charcoal studio "
    "background, warm softbox lighting with elegant controlled highlights, subtle depth of "
    "field but both emblems and the entire dial sharp. Quiet luxury, authentic expensive "
    "materials, premium macro product photography, no text overlay, no border, no watermark."
)


def reference_sheet(microsoft: Path, github: Path, watch: Path | None = None) -> bytes:
    with fitz.open() as document:
        if watch is None:
            page = document.new_page(width=1024, height=1024)
            page.insert_image(fitz.Rect(112, 80, 912, 300), filename=str(microsoft))
            page.insert_image(fitz.Rect(272, 444, 752, 924), filename=str(github))
        else:
            page = document.new_page(width=1400, height=1400)
            with fitz.open(watch) as example:
                source = example[0]
                crop = fitz.Rect(0, 0, source.rect.width * 0.39, source.rect.height)
                image = source.get_pixmap(clip=crop).tobytes("png")
            page.insert_image(fitz.Rect(40, 100, 710, 1300), stream=image)
            page.insert_image(fitz.Rect(770, 250, 1360, 450), filename=str(microsoft))
            page.insert_image(fitz.Rect(850, 700, 1280, 1130), filename=str(github))
        return page.get_pixmap().tobytes("png")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--microsoft-logo", type=Path, required=True)
    parser.add_argument("--github-logo", type=Path, required=True)
    parser.add_argument(
        "--reference-watch", type=Path, help="product screenshot; left watch column is read only"
    )
    args = parser.parse_args()
    references = reference_sheet(args.microsoft_logo, args.github_logo, args.reference_watch)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    print("Generating unofficial luxury wristwatch concept", flush=True)
    image = MaiImages().edit(PROMPT, references)
    _save_jpeg(image, NAME, OUTPUT)
    manifest = {
        "title": "Rheinkaliber luxury wristwatch: unofficial Microsoft/GitHub design concept",
        "synthetic": True,
        "claim_evidence": False,
        "notice": "AI-generated fictional design study. Not an actual product, partnership "
        "or endorsement by Microsoft or GitHub. Logos belong to their respective owners. "
        "Do not upload this promotional image as insurance claim evidence.",
        "model": MAI_MODEL,
        "model_version": MAI_VERSION,
        "generator": "scripts/generate_luxury_watch_concept.py",
        "prompt": PROMPT,
        "construction": {
            "case_diameter_mm": 40,
            "case_thickness_mm": 10,
            "lug_spacing_mm": 20,
            "central_hands": 3,
            "subdials": 0,
            "hour_markers": 12,
            "minute_divisions": 60,
            "crown_clock_position": 3,
            "display_time": "10:10:35",
        },
        "logo_references": {
            key: {
                "source": LOGO_SOURCES[key],
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for key, path in (
                ("microsoft", args.microsoft_logo),
                ("github", args.github_logo),
            )
        },
        "file": NAME,
        "sha256": hashlib.sha256((OUTPUT / NAME).read_bytes()).hexdigest(),
    }
    if args.reference_watch:
        manifest["construction_reference"] = {
            "source": "User-supplied product screenshot; construction only, not branding",
            "sha256": hashlib.sha256(args.reference_watch.read_bytes()).hexdigest(),
        }
    (OUTPUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT / NAME)


if __name__ == "__main__":
    main()
