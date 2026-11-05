from __future__ import annotations

import os
import time
from types import SimpleNamespace

import fitz
import pytest
from fastapi.testclient import TestClient

import api_server
from app.media_previews import (
    content_etag,
    etag_matches,
    is_previewable,
    preview_cache_name,
    render_preview,
)


def _noise_png(width: int, height: int) -> bytes:
    """Incompressible PNG, like a large photo."""
    pixmap = fitz.Pixmap(fitz.csRGB, width, height, os.urandom(width * height * 3), False)
    return pixmap.tobytes("png")


def test_render_preview_fits_the_box_and_shrinks_the_file() -> None:
    original = _noise_png(1200, 900)

    thumb = render_preview(original, "thumb")
    screen = render_preview(original, "screen")

    assert thumb is not None and screen is not None
    thumb_pixmap = fitz.Pixmap(thumb)
    assert (thumb_pixmap.width, thumb_pixmap.height) == (480, 360)
    # Never upscaled: the screen box (1600) is larger than the image.
    assert (fitz.Pixmap(screen).width, fitz.Pixmap(screen).height) == (1200, 900)
    assert len(thumb) < len(screen) < len(original)
    assert thumb[:3] == b"\xff\xd8\xff"  # JPEG


def test_render_preview_keeps_the_original_when_not_decodable() -> None:
    assert render_preview(b"not an image", "thumb") is None
    with pytest.raises(ValueError):
        render_preview(_noise_png(10, 10), "huge")


def test_previewable_names_and_storage_names() -> None:
    assert is_previewable("Photo 1.PNG")
    assert is_previewable("constat.jpeg")
    assert not is_previewable("declaration.pdf")
    assert not is_previewable(".preview-thumb-abc.jpg")

    name = preview_cache_name("dossier/2026 photo é.png", "thumb")
    assert name.startswith(".preview-thumb-") and name.endswith(".jpg")
    assert " " not in name and "/" not in name
    assert name != preview_cache_name("dossier/2026 photo é.png", "screen")


def test_etag_matching_follows_if_none_match_rules() -> None:
    etag = content_etag(b"abc")
    assert etag_matches(etag, etag)
    assert etag_matches(f'"other", W/{etag}', etag)
    assert etag_matches("*", etag)
    assert not etag_matches(None, etag)
    assert not etag_matches('"other"', etag)


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch) -> dict[str, bytes]:
    files: dict[str, bytes] = {
        "photo.png": _noise_png(1000, 800),
        "declaration.pdf": b"%PDF-1.4 test",
    }
    monkeypatch.setattr(
        api_server,
        "load_settings",
        lambda: SimpleNamespace(app=SimpleNamespace(storage_root="root")),
    )
    monkeypatch.setattr(api_server, "load_file", lambda root, app_id, name: files.get(name))

    def save(root: str, app_id: str, name: str, content: bytes) -> str:
        files[name] = content
        return name

    monkeypatch.setattr("app.storage.save_application_file", save)
    return files


def test_file_endpoint_serves_cached_jpeg_previews(storage: dict[str, bytes]) -> None:
    client = TestClient(api_server.app)

    response = client.get("/api/applications/APP-1/files/photo.png?preview=thumb")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.headers["cache-control"] == "private, max-age=600"
    assert len(response.content) < len(storage["photo.png"]) / 5
    cache_name = preview_cache_name("photo.png", "thumb")
    deadline = time.monotonic() + 2
    while cache_name not in storage and time.monotonic() < deadline:
        time.sleep(0.02)
    assert storage[cache_name] == response.content

    revalidated = client.get(
        "/api/applications/APP-1/files/photo.png?preview=thumb",
        headers={"If-None-Match": response.headers["etag"]},
    )
    assert revalidated.status_code == 304
    assert revalidated.content == b""


def test_file_endpoint_keeps_originals_and_rejects_unknown_sizes(
    storage: dict[str, bytes],
) -> None:
    client = TestClient(api_server.app)

    original = client.get("/api/applications/APP-1/files/photo.png")
    assert original.headers["content-type"] == "image/png"
    assert original.content == storage["photo.png"]
    assert original.headers["etag"] == content_etag(storage["photo.png"])

    pdf = client.get("/api/applications/APP-1/files/declaration.pdf?preview=thumb")
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content == storage["declaration.pdf"]

    assert client.get("/api/applications/APP-1/files/photo.png?preview=huge").status_code == 422
    assert client.get("/api/applications/APP-1/files/missing.png?preview=thumb").status_code == 404


def test_reupload_resets_cached_previews(monkeypatch: pytest.MonkeyPatch) -> None:
    saved: dict[str, bytes] = {}
    monkeypatch.setattr(
        "app.storage.save_application_file",
        lambda root, app_id, name, content: saved.setdefault(name, content),
    )

    api_server._invalidate_previews("root", "APP-1", ["photo.png", "declaration.pdf"])

    assert saved == {
        preview_cache_name("photo.png", "thumb"): b"",
        preview_cache_name("photo.png", "screen"): b"",
    }
