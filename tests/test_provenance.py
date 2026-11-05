"""C2PA provenance of claim photos: read locally, shown to the user, weighed only on request."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import fitz
import pytest

from app import provenance
from app.agents import tools as agent_tools

ROOT = Path(__file__).resolve().parents[1]
MAI_PNG = ROOT / "assets/demo-prevaiq/property-claims/water-damage/cave-inondee-vue-generale.png"


@pytest.fixture(autouse=True)
def _clear_cache():
    provenance._cache.clear()
    yield
    provenance._cache.clear()


def _plain_jpeg() -> bytes:
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 32, 24), False)
    pixmap.clear_with(200)
    return pixmap.tobytes("jpg", jpg_quality=80)


@pytest.mark.skipif(not MAI_PNG.exists(), reason="demo photo not available")
def test_ai_generated_photo_is_identified_from_its_content_credentials() -> None:
    result = provenance.detect_provenance(MAI_PNG.read_bytes(), MAI_PNG.name)

    assert result["status"] == "c2pa"
    assert result["ai_generated"] is True
    assert result["issuer"] == "Microsoft Corporation"
    assert result["generator"]


def test_photo_without_manifest_and_unsupported_files() -> None:
    assert provenance.detect_provenance(_plain_jpeg(), "IMG_20260828_104112.jpg") == {
        "status": "none"
    }
    assert provenance.detect_provenance(b"%PDF-1.7", "declaration.pdf") == {"status": "unsupported"}


def test_results_are_cached_by_content(monkeypatch) -> None:
    calls = []

    def fake_read(content, mime):
        calls.append(mime)
        return {"status": "none"}

    monkeypatch.setattr(provenance, "_read_manifest", fake_read)
    jpeg = _plain_jpeg()

    first = provenance.detect_provenance(jpeg, "a.jpg")
    first["status"] = "changed by the caller"
    second = provenance.detect_provenance(jpeg, "copy-of-a.jpeg")

    assert second == {"status": "none"} and calls == ["image/jpeg"]


@pytest.mark.parametrize(("mode", "kept"), [("inform", False), ("score", True)])
def test_fraud_model_only_weighs_provenance_in_score_mode(mode: str, kept: bool) -> None:
    settings = SimpleNamespace(provenance_mode=mode)
    images = [
        agent_tools._image_with_provenance(
            {"filename": "IMG.jpg", "authenticity_score": 0.9}, _plain_jpeg(), "IMG.jpg", settings
        )
    ]

    reasoning = agent_tools._images_for_reasoning(images, settings)

    assert images[0]["provenance"] == {"status": "none", "used_in_score": kept}
    assert ("provenance" in reasoning[0]) is kept
    assert reasoning[0]["authenticity_score"] == 0.9


def test_provenance_can_be_switched_off() -> None:
    entry = agent_tools._image_with_provenance(
        {"filename": "IMG.jpg"}, _plain_jpeg(), "IMG.jpg", SimpleNamespace(provenance_mode="off")
    )

    assert "provenance" not in entry
