"""Persisted, non-secret Aurora configuration managed from the admin UI."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse

from azure.core.exceptions import HttpResponseError, ResourceExistsError, ResourceNotFoundError
from filelock import FileLock

from app.brands import current_brand_key
from app.aurora_demo import DEMO_SCENARIOS, DemoScenario
from app.storage_providers import get_storage_provider
from app.storage_providers.azure_blob import AzureBlobStorageProvider

_MODEL_RE = re.compile(r"^(?:[A-Za-z0-9][A-Za-z0-9._-]{0,127}|azureml://[A-Za-z0-9._/-]{1,240})$")
_lock = threading.Lock()


@dataclass(frozen=True)
class AuroraAdminConfig:
    enabled: bool = False
    demo_enabled: bool = False
    demo_scenario: DemoScenario = "swiss-chocolate-storm"
    demo_validated_at: str | None = None
    demo_validated_by: str | None = None
    disabled_reason: Literal["blob_access_denied"] | None = None
    endpoint: str = ""
    deterministic_model: str = "aurora-0.25-v1.5"
    ensemble_model: str = "aurora-0.25-v1.5-ensemble"
    initial_condition_blob_url: str = ""
    channel_container_url: str = ""
    default_horizon_hours: int = 12
    endpoint_expires_at: str | None = None
    updated_at: str | None = None
    updated_by: str | None = None


def _blob_path() -> str:
    return f"brands/{current_brand_key()}/configuration/aurora.json"


def _local_path() -> Path:
    root = os.getenv("UW_APP_STORAGE_ROOT") or "data"
    return Path(root) / "brands" / current_brand_key() / "configuration" / "aurora.json"


def _get_blob_container():
    provider = get_storage_provider()
    return provider._container_client if isinstance(provider, AzureBlobStorageProvider) else None


@contextmanager
def _locked():
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
            raise TimeoutError("Aurora configuration lease acquisition timed out")
        try:
            yield
        finally:
            lease.release(retry_total=0)


def _validate_url(value: str, field: str, allowed_suffixes: tuple[str, ...]) -> str:
    normalized = value.strip()
    if not normalized:
        return ""
    parsed = urlparse(normalized)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError(f"{field} must be an absolute HTTPS URL")
    if parsed.username or parsed.password or parsed.fragment:
        raise ValueError(f"{field} contains unsupported URL components")
    if parsed.query:
        raise ValueError(f"{field} must not contain credentials or a SAS query")
    hostname = parsed.hostname.lower()
    if not any(
        hostname == suffix or hostname.endswith(f".{suffix}") for suffix in allowed_suffixes
    ):
        raise ValueError(f"{field} must target an approved Azure service hostname")
    return normalized.rstrip("/")


def validate_config(config: AuroraAdminConfig) -> AuroraAdminConfig:
    if config.demo_scenario not in DEMO_SCENARIOS:
        raise ValueError("Unknown synthetic weather scenario")
    if config.demo_enabled:
        if not config.demo_validated_at or not config.demo_validated_by:
            raise ValueError("Demo mode must be validated by an administrator")
        validated_at = datetime.fromisoformat(config.demo_validated_at.replace("Z", "+00:00"))
        if validated_at.tzinfo is None:
            raise ValueError("Demo validation timestamp must include a timezone")
    if config.disabled_reason not in (None, "blob_access_denied"):
        raise ValueError("disabled_reason must be blob_access_denied or null")
    endpoint = _validate_url(
        config.endpoint,
        "endpoint",
        ("inference.ml.azure.com", "api.azureml.ms"),
    )
    initial_condition = _validate_url(
        config.initial_condition_blob_url,
        "initial_condition_blob_url",
        ("blob.core.windows.net",),
    )
    channel = _validate_url(
        config.channel_container_url,
        "channel_container_url",
        ("blob.core.windows.net",),
    )
    for field, value in (
        ("deterministic_model", config.deterministic_model),
        ("ensemble_model", config.ensemble_model),
    ):
        if not _MODEL_RE.fullmatch(value.strip()):
            raise ValueError(f"{field} contains unsupported characters")
    if not 6 <= config.default_horizon_hours <= 240 or config.default_horizon_hours % 6:
        raise ValueError("default_horizon_hours must be a multiple of 6 between 6 and 240")
    endpoint_expires_at = config.endpoint_expires_at
    if endpoint_expires_at:
        try:
            expiration = datetime.fromisoformat(endpoint_expires_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("endpoint_expires_at must be an ISO 8601 timestamp") from error
        if expiration.tzinfo is None:
            raise ValueError("endpoint_expires_at must include a timezone")
        endpoint_expires_at = expiration.astimezone(UTC).isoformat()
    if config.enabled and not (endpoint and initial_condition and channel):
        raise ValueError("endpoint, initial condition, and Blob channel are required when enabled")
    return AuroraAdminConfig(
        enabled=config.enabled,
        demo_enabled=config.demo_enabled,
        demo_scenario=config.demo_scenario,
        demo_validated_at=config.demo_validated_at if config.demo_enabled else None,
        demo_validated_by=config.demo_validated_by if config.demo_enabled else None,
        disabled_reason=None if config.enabled else config.disabled_reason,
        endpoint=endpoint,
        deterministic_model=config.deterministic_model.strip(),
        ensemble_model=config.ensemble_model.strip(),
        initial_condition_blob_url=initial_condition,
        channel_container_url=channel,
        default_horizon_hours=config.default_horizon_hours,
        endpoint_expires_at=endpoint_expires_at,
        updated_at=config.updated_at,
        updated_by=config.updated_by,
    )


def _load_unlocked() -> AuroraAdminConfig | None:
    container = _get_blob_container()
    if container is not None:
        try:
            payload: Any = json.loads(
                container.download_blob(
                    _blob_path(), connection_timeout=5, read_timeout=5, retry_total=0
                ).readall()
            )
        except ResourceNotFoundError:
            return None
    else:
        path = _local_path()
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Persisted Aurora configuration must be a JSON object")
    return validate_config(AuroraAdminConfig(**payload))


def load_config() -> AuroraAdminConfig | None:
    with _locked():
        return _load_unlocked()


def save_config(config: AuroraAdminConfig, admin: str) -> AuroraAdminConfig:
    validated = validate_config(config)
    saved = AuroraAdminConfig(
        **{
            **asdict(validated),
            "updated_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "updated_by": admin.strip()[:120],
        }
    )
    payload = json.dumps(asdict(saved), indent=2, ensure_ascii=False).encode("utf-8")
    with _locked():
        container = _get_blob_container()
        if container is not None:
            container.get_blob_client(_blob_path()).upload_blob(
                payload,
                overwrite=True,
                connection_timeout=5,
                read_timeout=5,
                retry_total=0,
            )
        else:
            path = _local_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_suffix(".json.new")
            temporary.write_bytes(payload)
            temporary.replace(path)
    return saved


def public_dict(config: AuroraAdminConfig | None) -> dict[str, Any]:
    return asdict(config or AuroraAdminConfig())
