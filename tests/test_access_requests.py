"""Access requests for Microsoft Entra ID sign-in (local storage backend)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import access_requests
from app.access_api import router


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("UW_APP_STORAGE_ROOT", str(tmp_path))
    monkeypatch.delenv("ACCESS_ALLOWED_EMAILS", raising=False)
    monkeypatch.setattr(access_requests, "_get_blob_container", lambda: None)
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_request_then_approve_flow(client) -> None:
    base = "/api/internal/access"
    assert client.get(f"{base}/status", params={"email": "A.User@Contoso.com"}).json() == {
        "status": None
    }
    entry = client.post(f"{base}/request", json={"email": "A.User@Contoso.com", "name": "A"}).json()
    assert entry["id"] == "a.user@contoso.com" and entry["status"] == "pending"

    listing = client.get(base).json()
    assert listing["pending"] == 1

    decided = client.post(
        f"{base}/a.user@contoso.com/decision", json={"decision": "approve", "admin": "prevaIqAdmin"}
    ).json()
    assert decided["status"] == "approved" and decided["decided_by"] == "prevaIqAdmin"
    # A new request from an approved user does not downgrade it.
    assert client.post(f"{base}/request", json={"email": "a.user@contoso.com"}).json()[
        "status"
    ] == "approved"


def test_authorize_and_validation(client, monkeypatch) -> None:
    base = "/api/internal/access"
    ok = client.post(f"{base}/authorize", json={"email": "b@contoso.com", "admin": "admin"})
    assert ok.json()["status"] == "approved"
    assert client.post(f"{base}/authorize", json={"email": "nope", "admin": "a"}).status_code == 422
    assert client.post(
        f"{base}/missing@contoso.com/decision", json={"decision": "refuse", "admin": "a"}
    ).status_code == 404

    monkeypatch.setenv("ACCESS_ALLOWED_EMAILS", "vip@contoso.com")
    assert client.get(f"{base}/status", params={"email": "VIP@contoso.com"}).json() == {
        "status": "approved"
    }
