"""Access requests for Microsoft Entra ID sign-in (local storage backend)."""

from __future__ import annotations

import pytest
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

from requests import Timeout
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import access_requests
from app.access_api import router


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("UW_APP_STORAGE_ROOT", str(tmp_path))
    monkeypatch.delenv("ACCESS_ALLOWED_EMAILS", raising=False)
    monkeypatch.setattr(access_requests, "_get_blob_container", lambda: None)
    monkeypatch.setattr(
        access_requests.access_notifications, "submit", Mock(return_value="operation")
    )
    monkeypatch.setattr(
        access_requests.access_notifications,
        "submit_approval",
        Mock(return_value="approval-operation"),
    )
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
    assert listing["items"][0]["notification_status"] == "submitted"

    decided = client.post(
        f"{base}/a.user@contoso.com/decision", json={"decision": "approve", "admin": "prevaIqAdmin"}
    ).json()
    assert decided["status"] == "approved" and decided["decided_by"] == "prevaIqAdmin"
    assert decided["approval_notification_status"] == "submitted"
    access_requests.access_notifications.submit_approval.assert_called_once_with(
        "a.user@contoso.com", "A", decided["decided_at"]
    )
    # A new request from an approved user does not downgrade it.
    assert (
        client.post(f"{base}/request", json={"email": "a.user@contoso.com"}).json()["status"]
        == "approved"
    )


def test_authorize_and_validation(client, monkeypatch) -> None:
    base = "/api/internal/access"
    ok = client.post(f"{base}/authorize", json={"email": "b@contoso.com", "admin": "admin"})
    assert ok.json()["status"] == "approved"
    assert client.post(f"{base}/authorize", json={"email": "nope", "admin": "a"}).status_code == 422
    assert (
        client.post(
            f"{base}/missing@contoso.com/decision", json={"decision": "refuse", "admin": "a"}
        ).status_code
        == 404
    )

    monkeypatch.setenv("ACCESS_ALLOWED_EMAILS", "vip@contoso.com")
    assert client.get(f"{base}/status", params={"email": "VIP@contoso.com"}).json() == {
        "status": "approved"
    }


def test_pending_signins_are_idempotent_and_do_not_reset_history(client) -> None:
    base = "/api/internal/access"
    first = client.post(f"{base}/request", json={"email": "a@example.com"}).json()
    second = client.post(f"{base}/request", json={"email": "a@example.com"}).json()
    assert first == second
    access_requests.access_notifications.submit.assert_called_once()
    client.post(f"{base}/a@example.com/decision", json={"decision": "refuse", "admin": "owner"})
    assert (
        client.post(f"{base}/request", json={"email": "a@example.com"}).json()["status"]
        == "refused"
    )


def test_notification_failure_retains_pending_request_and_approval(client, monkeypatch) -> None:
    monkeypatch.setattr(
        access_requests.access_notifications, "submit", Mock(side_effect=Timeout("timeout"))
    )
    base = "/api/internal/access"
    response = client.post(f"{base}/request", json={"email": "colleague@example.com"})
    assert response.status_code == 200
    entry = response.json()
    assert entry["notification_status"] == "failed"
    assert entry["notification_error"] == "Timeout"
    assert client.get(base).json()["pending"] == 1
    approved = client.post(
        f"{base}/colleague@example.com/decision", json={"decision": "approve", "admin": "owner"}
    ).json()
    assert approved["status"] == "approved"
    assert approved["notification_status"] == "failed"


def test_historical_requests_remain_readable(client) -> None:
    path = access_requests._local_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            [
                {
                    "id": "old@example.com",
                    "email": "old@example.com",
                    "name": None,
                    "status": "pending",
                    "requested_at": "2026-01-01T00:00:00+00:00",
                }
            ]
        ),
        encoding="utf-8",
    )
    entry = client.get("/api/internal/access").json()["items"][0]
    assert entry["notification_status"] == "not_requested"
    assert entry["notification_operation_id"] is None
    assert entry["approval_notification_status"] == "not_requested"


def test_concurrent_requests_submit_only_one_notification(client) -> None:
    with ThreadPoolExecutor(max_workers=8) as pool:
        entries = list(
            pool.map(lambda _: access_requests.request("same@example.com", "Colleague"), range(8))
        )
    assert {entry.id for entry in entries} == {"same@example.com"}
    access_requests.access_notifications.submit.assert_called_once()
    assert len(access_requests.list_entries()) == 1


def test_storage_failure_is_explicit_and_never_submits_email(client, monkeypatch) -> None:
    monkeypatch.setattr(access_requests, "_save", Mock(side_effect=OSError("unavailable")))
    response = client.post("/api/internal/access/request", json={"email": "a@example.com"})
    assert response.status_code == 503
    access_requests.access_notifications.submit.assert_not_called()


def test_blob_mutations_use_a_cross_replica_lease(client, monkeypatch) -> None:
    from azure.core.exceptions import ResourceExistsError

    blob = Mock()
    blob.upload_blob.side_effect = ResourceExistsError("lock already exists")
    container = Mock()
    container.get_blob_client.return_value = blob
    monkeypatch.setattr(access_requests, "_get_blob_container", lambda: container)
    with access_requests._locked():
        blob.acquire_lease.assert_called_once_with(lease_duration=60, retry_total=0)
    blob.acquire_lease.return_value.release.assert_called_once_with(retry_total=0)


def test_blob_read_failure_is_not_an_empty_store(client, monkeypatch) -> None:
    from azure.core.exceptions import HttpResponseError

    container = Mock()
    container.download_blob.side_effect = HttpResponseError("unavailable")
    monkeypatch.setattr(access_requests, "_get_blob_container", lambda: container)
    with pytest.raises(HttpResponseError):
        access_requests._load()


def test_preapproval_notifies_the_requester_once(client) -> None:
    base = "/api/internal/access"
    body = {"email": "Uros.Stojkic@example.com", "admin": "owner"}
    first = client.post(f"{base}/authorize", json=body).json()
    second = client.post(f"{base}/authorize", json=body).json()
    assert first == second
    assert first["status"] == "approved"
    assert first["approval_notification_operation_id"] == "approval-operation"
    access_requests.access_notifications.submit_approval.assert_called_once_with(
        "uros.stojkic@example.com", None, first["decided_at"]
    )
    access_requests.access_notifications.submit.assert_not_called()


def test_repeated_and_concurrent_approval_does_not_resend(client) -> None:
    access_requests.request("colleague@example.com", "Colleague")
    with ThreadPoolExecutor(max_workers=6) as pool:
        entries = list(
            pool.map(
                lambda _: access_requests.decide("colleague@example.com", "approve", "owner"),
                range(6),
            )
        )
    assert {entry.status for entry in entries} == {"approved"}
    access_requests.access_notifications.submit_approval.assert_called_once()


def test_failed_approval_email_never_reverts_access(client, monkeypatch) -> None:
    monkeypatch.setattr(
        access_requests.access_notifications, "submit_approval", Mock(side_effect=Timeout())
    )
    entry = client.post(
        "/api/internal/access/authorize",
        json={"email": "colleague@example.com", "admin": "owner"},
    ).json()
    assert entry["status"] == "approved"
    assert entry["approval_notification_status"] == "failed"
    assert entry["approval_notification_error"] == "Timeout"
    assert access_requests.status_of("colleague@example.com") == "approved"
    assert access_requests.list_entries()[0].approval_notification_status == "failed"


def test_refusal_does_not_send_approval_email(client) -> None:
    access_requests.request("colleague@example.com", "Colleague")
    entry = access_requests.decide("colleague@example.com", "refuse", "owner")
    assert entry.status == "refused"
    access_requests.access_notifications.submit_approval.assert_not_called()


def test_stale_notification_result_cannot_overwrite_a_new_approval(client, monkeypatch) -> None:
    calls = 0

    def send_approval(email, name, date):
        nonlocal calls
        calls += 1
        if calls == 1:
            access_requests.decide(email, "refuse", "owner")
            access_requests.authorize(email, "owner")
            return "old-operation"
        return "new-operation"

    monkeypatch.setattr(access_requests.access_notifications, "submit_approval", send_approval)
    entry = access_requests.authorize("colleague@example.com", "owner")
    assert entry.status == "approved"
    assert entry.approval_notification_operation_id == "new-operation"
    assert calls == 2
