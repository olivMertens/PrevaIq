"""Verify the auto and underwriting upload sets without calling AI services."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import fitz
import pytest

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "assets" / "demo-prevaiq"
AUTO = DEMO / "automotive-claims" / "parking-impact"
UNDERWRITING = DEMO / "health-underwriting"
AUTO_FILES = {
    "thread2-01-client-accident-auto.pdf",
    "thread2-02-prevaiq-reponse-auto.pdf",
    "crash_portière_enfoncée.png",
}


def _text(path: Path) -> str:
    with fitz.open(path) as document:
        assert not document.is_encrypted
        assert document.embfile_count() == 0
        return "\n".join(page.get_text() for page in document)


def test_auto_upload_set_is_exact_and_readable() -> None:
    assert {path.name for path in AUTO.iterdir() if path.is_file()} == AUTO_FILES
    initial = _text(AUTO / "thread2-01-client-accident-auto.pdf")
    reply = _text(AUTO / "thread2-02-prevaiq-reponse-auto.pdf")
    assert "29 janvier 2026" in initial
    assert "crash_portière_enfoncée.png" in initial
    assert "SIN-2026-AUTO-00142" in reply
    assert "Service Sinistres Auto" in reply
    assert "Service Sinistres Habitation" not in reply
    assert "non incluses dans cette demo" in reply
    photo = fitz.Pixmap(AUTO / "crash_portière_enfoncée.png")
    assert min(photo.width, photo.height) >= 768


def test_underwriting_upload_contains_questionnaire_and_labs() -> None:
    path = UNDERWRITING / "souscription-sante-lefevre.pdf"
    assert {item.name for item in UNDERWRITING.iterdir() if item.is_file()} == {path.name}
    with fitz.open(path) as document:
        assert len(document) == 3
        assert "LEFEVRE Antoine" in document[0].get_text()
        assert "QUESTIONNAIRE DE SANTE" in document[1].get_text()
        labs = document[2].get_text()
        assert "HbA1c" in labs
        assert "5,4" in labs
        assert "mmol/L" in labs
    text = _text(path)
    assert "Amlodipine" in text
    assert "178 cm / 86 kg" in text
    assert "01/05/2026" in text


@pytest.mark.parametrize("locale", ["en", "fr", "de"])
def test_guide_upload_names_resolve_exactly(locale: str) -> None:
    content = json.loads((ROOT / "frontend" / "messages" / f"{locale}.json").read_text("utf-8"))
    scenarios = content["demoGuide"]["scenarios"]
    for filename in AUTO_FILES:
        assert filename in scenarios["auto"]["steps"][1]["detail"]
        assert (AUTO / filename).is_file()
    assert "souscription-sante-lefevre.pdf" in scenarios["sante"]["steps"][1]["detail"]
    assert len(scenarios["auto"]["steps"]) == len(scenarios["sante"]["steps"]) == 6


def test_underwriting_generator_uses_the_canonical_folder(tmp_path: Path) -> None:
    from scripts.generate_demo_underwriting import generate_underwriting_pdf, get_brand

    generate_underwriting_pdf(replace(get_brand("prevaiq"), demo_output_dir=str(tmp_path)))
    output = tmp_path / "health-underwriting" / "souscription-sante-lefevre.pdf"
    assert output.is_file()
    assert not (tmp_path / "sante").exists()
    assert "Amlodipine" in _text(output)
