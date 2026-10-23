"""Demo access requests for Microsoft Entra ID sign-in.

An Entra user who is not yet authorized gets a ``pending`` request; an
administrator approves or refuses it from the admin panel, or pre-authorizes an
e-mail address. Approval only opens the *user* demo: administration stays
reserved to admin accounts (enforced by the frontend session role).

Requests are stored as one JSON document per brand, in Azure Blob Storage when
it is the active backend, otherwise under the local storage root.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional
from uuid import uuid4

from azure.core.exceptions import (
    AzureError,
    HttpResponseError,
    ResourceExistsError,
    ResourceNotFoundError,
)
from filelock import FileLock
from requests import RequestException

from app import access_notifications
from app.brands import current_brand_key
from app.storage_providers import get_storage_provider
from app.storage_providers.azure_blob import AzureBlobStorageProvider
from app.utils import setup_logging

Status = Literal["pending", "approved", "refused"]
Decision = Literal["approve", "refuse"]
NotificationStatus = Literal["not_requested", "sending", "submitted", "failed"]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_lock = threading.Lock()
logger = setup_logging()


@dataclass
class AccessEntry:
    id: str
    email: Optional[str]
    name: Optional[str]
    status: Status
    requested_at: str
    decided_at: Optional[str] = None
    decided_by: Optional[str] = None
    notification_status: NotificationStatus = "not_requested"
    notification_at: Optional[str] = None
    notification_operation_id: Optional[str] = None
    notification_error: Optional[str] = None
    approval_notification_status: NotificationStatus = "not_requested"
    approval_notification_at: Optional[str] = None
    approval_notification_operation_id: Optional[str] = None
    approval_notification_error: Optional[str] = None
    approval_notification_attempt_id: Optional[str] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize(value: Optional[str]) -> str:
    return (value or "").strip().lower()


def is_valid_email(value: str) -> bool:
    return bool(_EMAIL_RE.match(value)) and len(value) <= 254


def _blob_path() -> str:
    return f"brands/{current_brand_key()}/access/requests.json"


def _local_path() -> Path:
    root = os.getenv("UW_APP_STORAGE_ROOT") or "data"
    return Path(root) / "brands" / current_brand_key() / "access" / "requests.json"


def _get_blob_container():
    provider = get_storage_provider()
    return provider._container_client if isinstance(provider, AzureBlobStorageProvider) else None


@contextmanager
def _locked():
    """Serialize workers/replicas, not just threads, before editing the JSON document."""
    with _lock:
        container = _get_blob_container()
        if container is None:
            path = _local_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            with FileLock(str(path) + ".lock", timeout=5):
                yield
            return
        blob = container.get_blob_client(_blob_path() + ".lock")
        try:
            blob.upload_blob(b"", overwrite=False, retry_total=0)
        except ResourceExistsError:
            pass
        for attempt in range(10):
            try:
                lease = blob.acquire_lease(lease_duration=60, retry_total=0)
                break
            except HttpResponseError as error:
                if getattr(error, "error_code", None) != "LeaseAlreadyPresent" or attempt == 9:
                    raise
                time.sleep(0.1)
        else:
            raise TimeoutError("Access request lease acquisition timed out")
        try:
            yield
        finally:
            lease.release(retry_total=0)


def _load() -> dict[str, AccessEntry]:
    container = _get_blob_container()
    if container is not None:
        try:
            raw: Any = json.loads(
                container.download_blob(
                    _blob_path(), connection_timeout=5, read_timeout=5, retry_total=0
                ).readall()
            )
        except ResourceNotFoundError:
            raw = []
    else:
        path = _local_path()
        raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    return {item["id"]: AccessEntry(**item) for item in raw}


def _save(entries: dict[str, AccessEntry]) -> None:
    data = [asdict(entry) for entry in entries.values()]
    container = _get_blob_container()
    if container is not None:
        container.get_blob_client(_blob_path()).upload_blob(
            json.dumps(data, ensure_ascii=False).encode("utf-8"),
            overwrite=True,
            connection_timeout=5,
            read_timeout=5,
            retry_total=0,
        )
        return
    path = _local_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.new")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def _preapproved() -> set[str]:
    return {normalize(e) for e in os.getenv("ACCESS_ALLOWED_EMAILS", "").split(",") if e.strip()}


def status_of(email: str) -> Status | None:
    """Authorization status for an Entra e-mail (``None`` when never requested)."""
    key = normalize(email)
    if key in _preapproved():
        return "approved"
    with _locked():
        entry = _load().get(key)
    return entry.status if entry else None


def request(email: str, name: Optional[str]) -> AccessEntry:
    """Record once, then submit email outside the persistence lock."""
    key = normalize(email)
    with _locked():
        entries = _load()
        entry = entries.get(key)
        if entry:
            return entry
        entry = AccessEntry(
            id=key,
            email=key,
            name=(name or "").strip()[:120] or None,
            status="pending",
            requested_at=_now(),
            notification_status="sending",
        )
        entries[key] = entry
        _save(entries)
    try:
        operation_id = access_notifications.submit(key, entry.name, entry.requested_at)
    except (AzureError, RequestException, ValueError) as error:
        logger.error("Access notification failed: %s", type(error).__name__)
        notification_status: Literal["failed", "submitted"] = "failed"
        notification_error = type(error).__name__
        operation_id = None
    else:
        notification_status = "submitted"
        notification_error = None
    with _locked():
        entries = _load()
        entry = entries[key]
        entry.notification_status = notification_status
        entry.notification_at = _now()
        entry.notification_operation_id = operation_id
        entry.notification_error = notification_error
        _save(entries)
    return entry


def list_entries() -> list[AccessEntry]:
    order = {"pending": 0, "approved": 1, "refused": 2}
    with _locked():
        entries = list(_load().values())
    return sorted(entries, key=lambda e: (order[e.status], e.requested_at), reverse=False)


def decide(entry_id: str, decision: Decision, admin: str) -> AccessEntry:
    key = normalize(entry_id)
    with _locked():
        entries = _load()
        if key not in entries:
            raise KeyError(key)
        entry = entries[key]
        status = "approved" if decision == "approve" else "refused"
        if entry.status == status:
            return entry
        entry.status = status
        entry.decided_at = _now()
        entry.decided_by = admin
        if decision == "approve":
            entry.approval_notification_status = "sending"
            entry.approval_notification_attempt_id = str(uuid4())
            entry.approval_notification_error = None
            entry.approval_notification_operation_id = None
        _save(entries)
    return _notify_approval(entry) if decision == "approve" else entry


def _notify_approval(approved: AccessEntry) -> AccessEntry:
    try:
        operation_id = access_notifications.submit_approval(
            approved.email or approved.id, approved.name, approved.decided_at or _now()
        )
    except (AzureError, RequestException, ValueError) as error:
        logger.error("Access approval notification failed: %s", type(error).__name__)
        status: NotificationStatus = "failed"
        notification_error = type(error).__name__
        operation_id = None
    else:
        status = "submitted"
        notification_error = None
    with _locked():
        entries = _load()
        entry = entries[approved.id]
        if entry.approval_notification_attempt_id == approved.approval_notification_attempt_id:
            entry.approval_notification_status = status
            entry.approval_notification_at = _now()
            entry.approval_notification_operation_id = operation_id
            entry.approval_notification_error = notification_error
            _save(entries)
    return entry


def authorize(email: str, admin: str) -> AccessEntry:
    """Pre-authorize an e-mail address before its first Entra sign-in."""
    key = normalize(email)
    now = _now()
    with _locked():
        entries = _load()
        previous = entries.get(key)
        if previous and previous.status == "approved":
            return previous
        entry = previous or AccessEntry(
            id=key, email=key, name=None, status="approved", requested_at=now
        )
        entry.status = "approved"
        entry.decided_at = now
        entry.decided_by = admin
        entry.approval_notification_status = "sending"
        entry.approval_notification_attempt_id = str(uuid4())
        entry.approval_notification_error = None
        entry.approval_notification_operation_id = None
        entries[key] = entry
        _save(entries)
    return _notify_approval(entry)
