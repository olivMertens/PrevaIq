"""Demo files referenced by the seeded cases exist in the repo and are well-formed (offline)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import fitz
import pytest

from scripts.seed_data.claims import get_claims_apps
from scripts.seed_data.mortgage import get_mortgage_apps
from scripts.seed_data.underwriting import get_underwriting_apps

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "assets" / "demo-prevaiq" / "seeded" / "manifest.json"
SEEDED_PREFIX = "assets/demo-prevaiq/seeded/"
SIGNATURES = {
    ".pdf": b"%PDF",
    ".jpg": b"\xff\xd8\xff",
    ".jpeg": b"\xff\xd8\xff",
    ".zip": b"PK\x03\x04",
}
MAX_PHOTO_BYTES = 1_500_000


@pytest.fixture(scope="module")
def manifest() -> dict[str, Any]:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def _generated(manifest: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    entries = [e for e in manifest["files"] if e["kind"] == kind and e["origin"] == "generated"]
    assert entries, f"no generated {kind} in the manifest"
    return entries


def _assert_photo(label: str, data: bytes) -> None:
    assert data.startswith(SIGNATURES[".jpg"]), label
    assert len(data) < MAX_PHOTO_BYTES, f"{label}: {len(data)} bytes"
    pix = fitz.Pixmap(data)
    assert 768 <= max(pix.width, pix.height) <= 2000, f"{label}: {pix.width}x{pix.height}"


def test_every_seeded_file_resolves_to_a_repo_asset(manifest: dict[str, Any]) -> None:
    index = {(e["app_id"], e["filename"]): e for e in manifest["files"]}
    unresolved = [
        f"{case['id']}/{stored['filename']}"
        for case in get_underwriting_apps() + get_claims_apps() + get_mortgage_apps()
        for stored in case.get("files", [])
        if (case["id"], stored["filename"]) not in index
        or not (ROOT / index[(case["id"], stored["filename"])]["path"]).is_file()
    ]
    assert not unresolved


def test_manifest_entries_are_unique_and_exist(manifest: dict[str, Any]) -> None:
    keys = [(e["app_id"], e["filename"]) for e in manifest["files"]]
    assert manifest["version"] == 1
    assert len(keys) == len(set(keys))
    for entry in manifest["files"]:
        path = entry["path"]
        assert entry["origin"] in {"repo", "generated"}, path
        assert entry["kind"] in {"pdf", "photo", "archive"}, path
        assert "\\" not in path and not Path(path).is_absolute() and ".." not in path
        assert Path(path).name == entry["filename"]
        assert (ROOT / path).is_file(), path
        # Repo assets are referenced where they are, never copied under seeded/.
        assert path.startswith(SEEDED_PREFIX) == (entry["origin"] == "generated"), path


def test_file_signatures_match_extensions(manifest: dict[str, Any]) -> None:
    for entry in manifest["files"]:
        head = (ROOT / entry["path"]).read_bytes()[:8]
        assert head.startswith(SIGNATURES[Path(entry["filename"]).suffix.lower()]), entry["path"]


def test_generated_photos_are_reasonably_sized(manifest: dict[str, Any]) -> None:
    for entry in _generated(manifest, "photo"):
        _assert_photo(entry["path"], (ROOT / entry["path"]).read_bytes())
        provenance = entry["generated_with"]
        assert provenance["model"] == "MAI-Image-2.6" and provenance["version"]
        assert provenance["prompt"] and provenance["date"]


def test_archive_contains_three_jpegs(manifest: dict[str, Any]) -> None:
    for entry in _generated(manifest, "archive"):
        with zipfile.ZipFile(ROOT / entry["path"]) as archive:
            names = archive.namelist()
            assert len(names) == 3 and all(name.lower().endswith(".jpg") for name in names)
            for name in names:
                _assert_photo(f"{entry['path']}:{name}", archive.read(name))
        assert sorted(item["filename"] for item in entry["contents"]) == sorted(names)
        assert all(item["generated_with"]["prompt"] for item in entry["contents"])


def test_generated_pdfs_carry_the_fictitious_footer(manifest: dict[str, Any]) -> None:
    for entry in _generated(manifest, "pdf"):
        with fitz.open(ROOT / entry["path"]) as doc:
            assert 1 <= doc.page_count <= 2, entry["path"]
            for page in doc:
                assert "Document fictif" in page.get_text(), f"{entry['path']} p.{page.number + 1}"
