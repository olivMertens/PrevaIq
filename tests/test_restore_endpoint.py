from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api_server
from app.storage import StoredFile, load_application, new_metadata, save_application_metadata

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
PDF = b"%PDF-1.4\n%demo\n"


@pytest.fixture
def local_case(tmp_path, monkeypatch):
    """A seeded case in local storage that references files whose content is missing."""
    monkeypatch.setattr("app.storage._get_provider", lambda: None)
    settings = SimpleNamespace(app=SimpleNamespace(storage_root=str(tmp_path)))
    monkeypatch.setattr(api_server, "load_settings", lambda: settings)
    app_md = new_metadata(str(tmp_path), "app-hab-004", [], external_reference="SIN-2026-0001")
    app_md.persona = "habitation_claims"
    app_md.status = "completed"
    app_md.files = [
        StoredFile(filename="photo toiture.png", path="applications/app-hab-004/photo toiture.png"),
        StoredFile(filename="declaration.pdf", path="applications/app-hab-004/declaration.pdf"),
        StoredFile(filename="photos_dommages.zip", path="applications/app-hab-004/photos.zip"),
    ]
    save_application_metadata(str(tmp_path), app_md)
    return tmp_path


def test_restore_writes_where_the_viewer_reads(local_case) -> None:
    client = TestClient(api_server.app)
    url = "/api/applications/app-hab-004/files/photo%20toiture.png"
    assert client.get(url).status_code == 404

    response = client.put(url, content=PNG, headers={"Content-Type": "application/octet-stream"})

    assert response.status_code == 200
    assert response.json() == {
        "application_id": "app-hab-004",
        "filename": "photo toiture.png",
        "bytes": len(PNG),
        "path_updated": True,
    }
    assert client.get(url).content == PNG
    restored = load_application(str(local_case), "app-hab-004")
    assert restored.status == "completed"
    assert [f.filename for f in restored.files] == [
        "photo toiture.png",
        "declaration.pdf",
        "photos_dommages.zip",
    ]
    assert Path(restored.files[0].path).parts[-2:] == ("files", "photo toiture.png")


def test_restore_accepts_referenced_archives(local_case) -> None:
    response = TestClient(api_server.app).put(
        "/api/applications/app-hab-004/files/photos_dommages.zip", content=b"PK\x03\x04demo"
    )
    assert response.status_code == 200


@pytest.mark.parametrize(
    ("filename", "content", "status"),
    [
        ("unknown.png", PNG, 404),
        ("declaration.pdf", PNG, 400),
        ("declaration.pdf", b"", 400),
        ("script.sh", b"#!/bin/sh", 400),
        (".preview-thumb-abc.jpg", PNG, 403),
    ],
)
def test_restore_rejects_unreferenced_or_mismatched_files(
    local_case, filename: str, content: bytes, status: int
) -> None:
    response = TestClient(api_server.app).put(
        f"/api/applications/app-hab-004/files/{filename}", content=content
    )
    assert response.status_code == status


def test_restore_rejects_unknown_cases(local_case) -> None:
    response = TestClient(api_server.app).put(
        "/api/applications/missing/files/declaration.pdf", content=PDF
    )
    assert response.status_code == 404
