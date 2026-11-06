from __future__ import annotations

from datetime import UTC, datetime

import pytest

import app.aurora_admin_api as admin_api
import app.aurora_config as aurora_config
from app.aurora import AuroraSettings
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
def test_readiness_checks_validate_each_live_dependency(
    monkeypatch,
    use_azure_ad,
    endpoint_token,
    expected_detail,
):
    config = valid_config()
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
    monkeypatch.setattr(admin_api, "_download_initial_condition", lambda settings: b"netcdf")
    monkeypatch.setattr(
        admin_api,
        "_validate_initial_condition",
        lambda payload: datetime(2026, 1, 1, tzinfo=UTC),
    )
    monkeypatch.setattr(admin_api, "_channel_sas_url", lambda settings: "https://delegated")

    result = admin_api._run_readiness_checks(config)

    assert result["ok"] is True
    assert observed == [endpoint_token or "managed-token"]
    assert [item["id"] for item in result["checks"]] == [
        "enabled",
        "endpoint_authentication",
        "endpoint",
        "initial_conditions",
        "blob_channel",
    ]
    assert result["checks"][1]["detail"] == expected_detail
    if endpoint_token:
        assert endpoint_token not in repr(result)
