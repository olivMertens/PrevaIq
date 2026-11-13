from __future__ import annotations

import json
from contextlib import nullcontext
from dataclasses import asdict
from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from azure.core.exceptions import HttpResponseError

import app.aurora_admin_api as admin_api
import app.aurora_config as aurora_config
from app.aurora import AuroraServiceError, AuroraSettings, status
from app.aurora_config import AuroraAdminConfig


@pytest.fixture
def local_config_store(monkeypatch, tmp_path):
    monkeypatch.setattr(aurora_config, "_get_blob_container", lambda: None)
    monkeypatch.setenv("UW_APP_STORAGE_ROOT", str(tmp_path))
    return tmp_path


def valid_config(**overrides) -> AuroraAdminConfig:
    values = {
        "enabled": True,
        "endpoint": "https://aurora.westeurope.inference.ml.azure.com/score",
        "deterministic_model": "aurora-0.25-v1.5",
        "ensemble_model": "aurora-0.25-v1.5-ensemble",
        "initial_condition_blob_url": (
            "https://weather.blob.core.windows.net/aurora-input/initial.nc"
        ),
        "channel_container_url": "https://weather.blob.core.windows.net/aurora-tasks",
        "default_horizon_hours": 12,
        "endpoint_expires_at": "2026-11-13T05:59:39.304Z",
    }
    values.update(overrides)
    return AuroraAdminConfig(**values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        (
            "endpoint",
            "https://aurora.westeurope.inference.ml.azure.com/score?token=secret",
        ),
        (
            "initial_condition_blob_url",
            "https://weather.blob.core.windows.net/input/initial.nc?sig=secret",
        ),
        (
            "channel_container_url",
            "https://weather.blob.core.windows.net/tasks?sv=1&sig=secret",
        ),
        ("endpoint", "https://example.com/score"),
    ],
)
def test_config_rejects_credentials_and_unapproved_hosts(field, value):
    with pytest.raises(ValueError):
        aurora_config.validate_config(valid_config(**{field: value}))


def test_local_configuration_round_trip_is_audited(local_config_store):
    saved = aurora_config.save_config(valid_config(), "admin@example.com")
    loaded = aurora_config.load_config()

    assert loaded == saved
    assert loaded is not None
    assert loaded.updated_by == "admin@example.com"
    assert loaded.updated_at is not None
    assert loaded.endpoint_expires_at == "2026-11-13T05:59:39.304000+00:00"
    assert (
        "secret"
        not in (
            local_config_store / "brands" / "prevaiq" / "configuration" / "aurora.json"
        ).read_text()
    )


def test_suspension_reason_is_persisted_and_exposed_without_changing_endpoint(
    local_config_store, monkeypatch
):
    # A future expiry: an expired endpoint would be reported as missing.
    config = valid_config(
        enabled=False,
        disabled_reason="blob_access_denied",
        endpoint_expires_at="2099-01-01T00:00:00Z",
    )
    saved = aurora_config.save_config(config, "admin@example.com")
    assert aurora_config.load_config() == saved
    monkeypatch.setattr(aurora_config, "load_config", lambda: saved)

    snapshot = admin_api._snapshot(saved)
    runtime = status(AuroraSettings.from_env())

    assert snapshot["configuration"]["disabled_reason"] == "blob_access_denied"
    assert runtime["disabled_reason"] == "blob_access_denied"
    assert runtime["enabled"] is False
    assert runtime["configured"] is False
    assert runtime["missing"] == []
    assert saved.endpoint == config.endpoint


def test_unspecified_suspension_does_not_claim_a_blob_failure():
    assert status(AuroraSettings())["disabled_reason"] is None


class _Container:
    """Blob container whose configuration lock is leased by another writer."""

    def __init__(self, payload: bytes = b"") -> None:
        self.payload = payload
        self.leases = 0

    def download_blob(self, path, **kwargs):
        return Mock(readall=lambda: self.payload)

    def get_blob_client(self, path):
        def leased_upload(*args, **kwargs):
            error = HttpResponseError(message="There is currently a lease on the blob.")
            error.error_code = "LeaseIdMissing"
            raise error

        def acquire_lease(**kwargs):
            self.leases += 1
            return Mock()

        return Mock(upload_blob=leased_upload, acquire_lease=acquire_lease)


def test_reading_the_configuration_takes_no_lease(monkeypatch):
    expected = aurora_config.validate_config(valid_config())
    container = _Container(json.dumps(asdict(expected)).encode())
    monkeypatch.setattr(aurora_config, "_get_blob_container", lambda: container)

    assert aurora_config.load_config() == expected
    assert container.leases == 0


def test_writer_waits_for_the_lease_when_the_lock_blob_is_leased(monkeypatch):
    container = _Container()
    monkeypatch.setattr(aurora_config, "_get_blob_container", lambda: container)

    with aurora_config._locked():
        pass

    assert container.leases == 1


def test_reenabling_clears_the_suspension_reason():
    config = aurora_config.validate_config(valid_config(disabled_reason="blob_access_denied"))

    assert config.disabled_reason is None
    assert admin_api._snapshot(config)["runtime"]["disabled_reason"] is None


def test_config_rejects_unrecognized_suspension_reasons():
    with pytest.raises(ValueError, match="disabled_reason"):
        aurora_config.validate_config(valid_config(enabled=False, disabled_reason="unknown"))


@pytest.mark.parametrize(
    "value",
    ["not-a-timestamp", "2026-11-13T05:59:39"],
)
def test_config_rejects_invalid_endpoint_expiration(value):
    with pytest.raises(ValueError, match="endpoint_expires_at"):
        aurora_config.validate_config(valid_config(endpoint_expires_at=value))


def test_persisted_configuration_takes_precedence(monkeypatch):
    persisted = valid_config(default_horizon_hours=24)
    monkeypatch.setattr(aurora_config, "load_config", lambda: persisted)
    monkeypatch.setenv("AURORA_DEFAULT_HORIZON_HOURS", "48")
    monkeypatch.setenv("AURORA_DEPLOYMENT_NAME", "environment-model")

    settings = AuroraSettings.from_env()

    assert settings.default_horizon_hours == 24
    assert settings.deterministic_model == persisted.deterministic_model
    assert settings.configuration_source == "admin"
    assert settings.endpoint_token == ""
    assert settings.channel_sas_url == ""
    assert settings.endpoint_expires_at == persisted.endpoint_expires_at


def test_environment_expiration_is_retained_when_admin_config_omits_it(monkeypatch):
    monkeypatch.setenv("AURORA_ENDPOINT_EXPIRES_AT", "2026-11-13T05:59:39Z")

    snapshot = admin_api._snapshot(valid_config(endpoint_expires_at=None))

    assert snapshot["configuration"]["endpoint_expires_at"] == "2026-11-13T05:59:39Z"
    assert snapshot["runtime"]["endpoint_expires_at"] == "2026-11-13T05:59:39Z"


def test_admin_snapshot_exposes_non_secret_managed_identity_readiness(monkeypatch):
    monkeypatch.delenv("AURORA_ENDPOINT_TOKEN", raising=False)
    monkeypatch.setenv("AURORA_USE_AZURE_AD", "true")
    snapshot = admin_api._snapshot(valid_config())

    assert snapshot["source"] == "admin"
    assert snapshot["ready_count"] == snapshot["total_count"] == 5
    assert [item["id"] for item in snapshot["checklist"]] == [
        "enabled",
        "endpoint_authentication",
        "endpoint",
        "initial_conditions",
        "blob_channel",
    ]
    assert snapshot["security"] == {
        "endpoint_authentication": "managed_identity",
        "storage_authentication": "managed_identity",
        "secrets_persisted": False,
        "sas_persisted": False,
    }
    assert "endpoint_token" not in snapshot["configuration"]
    assert "channel_sas_url" not in snapshot["configuration"]


def test_admin_snapshot_uses_key_auth_without_exposing_key(monkeypatch):
    monkeypatch.setenv("AURORA_USE_AZURE_AD", "false")
    monkeypatch.setenv("AURORA_ENDPOINT_TOKEN", "endpoint-key")

    snapshot = admin_api._snapshot(valid_config())

    assert snapshot["ready_count"] == snapshot["total_count"] == 5
    assert snapshot["security"] == {
        "endpoint_authentication": "key_vault_secret",
        "storage_authentication": "managed_identity",
        "secrets_persisted": False,
        "sas_persisted": False,
    }
    assert "endpoint-key" not in repr(snapshot)


@pytest.mark.parametrize(
    ("use_azure_ad", "endpoint_token", "expected_detail"),
    [
        ("true", "", "managed_identity_token_acquired"),
        ("false", "endpoint-key", "endpoint_key_loaded"),
    ],
)
@pytest.mark.parametrize("enabled", [True, False])
def test_readiness_checks_validate_each_live_dependency(
    monkeypatch,
    use_azure_ad,
    endpoint_token,
    expected_detail,
    enabled,
):
    config = valid_config(enabled=enabled)
    observed: list[str] = []
    monkeypatch.setenv("AURORA_USE_AZURE_AD", use_azure_ad)
    monkeypatch.setenv("AURORA_ENDPOINT_TOKEN", endpoint_token)
    monkeypatch.setattr(
        admin_api,
        "_endpoint_token",
        lambda settings: settings.endpoint_token or "managed-token",
    )
    monkeypatch.setattr(
        admin_api,
        "_endpoint_probe",
        lambda settings, token: (observed.append(token) or True, "reachable"),
    )
    monkeypatch.setattr(
        admin_api, "_download_initial_condition", lambda settings: nullcontext(b"netcdf")
    )
    monkeypatch.setattr(
        admin_api,
        "_validate_initial_condition",
        lambda payload: datetime(2026, 1, 1, tzinfo=UTC),
    )
    channel_sas = "https://weather.blob.core.windows.net/aurora-tasks?sig=private-test-signature"
    monkeypatch.setattr(admin_api, "_channel_sas_url", lambda settings: channel_sas)

    result = admin_api._run_readiness_checks(config)

    assert result["ok"] is enabled
    assert observed == [endpoint_token or "managed-token"]
    assert [item["id"] for item in result["checks"]] == [
        "enabled",
        "endpoint_authentication",
        "endpoint",
        "initial_conditions",
        "blob_channel",
    ]
    assert result["checks"][1]["detail"] == expected_detail
    assert result["checks"][-1]["detail"] == "delegated_sas_created"
    assert result["checks"][-1]["origin"] == "prevaiq_backend"
    assert result["checks"][-1]["operation"] == "get_user_delegation_key"
    assert datetime.fromisoformat(result["checks"][-1]["checked_at"]).tzinfo is not None
    assert channel_sas not in repr(result)
    assert "private-test-signature" not in repr(result)
    if endpoint_token:
        assert endpoint_token not in repr(result)


@pytest.mark.parametrize("wrapped", [False, True])
def test_storage_diagnostics_expose_safe_correlation_fields_only(wrapped):
    error = HttpResponseError(
        message="private failure https://weather.blob.core.windows.net/?sig=secret"
    )
    error.status_code = 403
    error.response = Mock(
        headers={
            "x-ms-error-code": "AuthorizationFailure",
            "x-ms-request-id": "d5dfd98a-801e-0000-0000-000000000000",
            "Authorization": "Bearer private-token",
        }
    )
    if wrapped:
        outer = AuroraServiceError("Unable to download initial conditions")
        outer.__cause__ = error
    else:
        outer = error

    assert admin_api._failure_diagnostics(outer) == {
        "http_status": 403,
        "error_code": "AuthorizationFailure",
        "request_id": "d5dfd98a-801e-0000-0000-000000000000",
    }


def test_storage_diagnostics_reject_unexpected_header_contents():
    error = HttpResponseError(message="private")
    error.response = Mock(
        headers={"x-ms-error-code": "https://example.com/?sig=secret", "x-ms-request-id": "a\nb"}
    )

    assert admin_api._failure_diagnostics(error) == {}


@pytest.mark.asyncio
async def test_admin_can_diagnose_without_reenabling_or_submitting_forecast(monkeypatch):
    config = valid_config(enabled=False, disabled_reason="blob_access_denied")
    monkeypatch.setattr(admin_api, "load_config", lambda: config)
    observed = []
    monkeypatch.setattr(
        admin_api, "_run_readiness_checks", lambda value: observed.append(value) or {"ok": False}
    )

    response = await admin_api.test_aurora_admin_config()

    assert observed == [config]
    assert response["configuration"]["enabled"] is False
    assert response["configuration"]["disabled_reason"] == "blob_access_denied"
