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
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Optional

from app.brands import current_brand_key
from app.customer360 import _get_blob_container, _load_blob_json, _save_blob_json

Status = Literal["pending", "approved", "refused"]
Decision = Literal["approve", "refuse"]

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_lock = threading.Lock()


@dataclass
class AccessEntry:
    id: str
    email: Optional[str]
    name: Optional[str]
    status: Status
    requested_at: str
    decided_at: Optional[str] = None
    decided_by: Optional[str] = None


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


def _load() -> dict[str, AccessEntry]:
    if _get_blob_container() is not None:
        raw: Any = _load_blob_json(_blob_path()) or []
    else:
        path = _local_path()
        raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    return {item["id"]: AccessEntry(**item) for item in raw}


def _save(entries: dict[str, AccessEntry]) -> None:
    data = [asdict(entry) for entry in entries.values()]
    if _get_blob_container() is not None:
        if not _save_blob_json(_blob_path(), data):
            raise RuntimeError("access requests could not be saved")
        return
    path = _local_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _preapproved() -> set[str]:
    return {normalize(e) for e in os.getenv("ACCESS_ALLOWED_EMAILS", "").split(",") if e.strip()}


def status_of(email: str) -> Status | None:
    """Authorization status for an Entra e-mail (``None`` when never requested)."""
    key = normalize(email)
    if key in _preapproved():
        return "approved"
    with _lock:
        entry = _load().get(key)
    return entry.status if entry else None


def request(email: str, name: Optional[str]) -> AccessEntry:
    """Record (or re-open) a request; an approved entry is returned unchanged."""
    key = normalize(email)
    with _lock:
        entries = _load()
        entry = entries.get(key)
        if entry and entry.status == "approved":
            return entry
        entry = AccessEntry(id=key, email=key, name=(name or "").strip()[:120] or None,
                            status="pending", requested_at=_now())
        entries[key] = entry
        _save(entries)
    return entry


def list_entries() -> list[AccessEntry]:
    order = {"pending": 0, "approved": 1, "refused": 2}
    with _lock:
        entries = list(_load().values())
    return sorted(entries, key=lambda e: (order[e.status], e.requested_at), reverse=False)


def decide(entry_id: str, decision: Decision, admin: str) -> AccessEntry:
    key = normalize(entry_id)
    with _lock:
        entries = _load()
        if key not in entries:
            raise KeyError(key)
        entry = entries[key]
        entry.status = "approved" if decision == "approve" else "refused"
        entry.decided_at = _now()
        entry.decided_by = admin
        _save(entries)
    return entry


def authorize(email: str, admin: str) -> AccessEntry:
    """Pre-authorize an e-mail address before its first Entra sign-in."""
    key = normalize(email)
    now = _now()
    with _lock:
        entries = _load()
        previous = entries.get(key)
        entry = AccessEntry(id=key, email=key, name=previous.name if previous else None,
                            status="approved", requested_at=previous.requested_at if previous
                            else now, decided_at=now, decided_by=admin)
        entries[key] = entry
        _save(entries)
    return entry
