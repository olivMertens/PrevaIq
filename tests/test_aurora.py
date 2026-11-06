from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import numpy as np
import pytest
import xarray as xr

import app.aurora as aurora
from app.aurora import AuroraConfigurationError, AuroraSettings, status, submit_forecast


def test_aurora_status_is_safe_when_disabled():
    result = status(AuroraSettings())

    assert result == {
        "enabled": False,
        "configured": False,
        "model": "aurora-0.25-v1.5",
        "ensemble_model": "aurora-0.25-v1.5-ensemble",
        "provider": "Microsoft Foundry",
        "mode": "managed_foundry",
        "human_review_required": True,
        "requires_initial_conditions": True,
        "default_horizon_hours": 12,
        "endpoint_expires_at": None,
        "endpoint_expired": False,
        "endpoint_seconds_remaining": None,
        "configuration_source": "environment",
        "missing": ["endpoint", "initial_condition", "blob_channel"],
    }


def test_disabled_aurora_fails_explicitly():
    with pytest.raises(AuroraConfigurationError, match="Aurora is not ready"):
        asyncio.run(
            submit_forecast(
                latitude=46.2,
                longitude=6.1,
                settings=AuroraSettings(),
            )
        )


def test_expired_endpoint_is_not_configured():
    settings = AuroraSettings(
        enabled=True,
        endpoint="https://aurora.westeurope.inference.ml.azure.com/score",
        initial_condition_blob_url="https://weather.blob.core.windows.net/input/current.nc",
        channel_container_url="https://weather.blob.core.windows.net/tasks",
        endpoint_token="key",
        use_azure_ad=False,
        endpoint_expires_at="2020-01-01T00:00:00Z",
    )

    result = status(settings)

    assert result["configured"] is False
    assert result["endpoint_expired"] is True
    assert result["endpoint_seconds_remaining"] == 0
    assert "endpoint_expired" in result["missing"]


def test_aurora_rejects_invalid_coordinates():
    with pytest.raises(ValueError, match="Latitude"):
        asyncio.run(
            submit_forecast(
                latitude=100,
                longitude=6.1,
                settings=AuroraSettings(enabled=True),
            )
        )


def test_aurora_requires_six_hour_horizon_steps():
    with pytest.raises(ValueError, match="multiple of 6"):
        asyncio.run(
            submit_forecast(
                latitude=46.2,
                longitude=6.1,
                horizon_hours=7,
                settings=AuroraSettings(enabled=True),
            )
        )


@pytest.mark.parametrize(
    ("gust", "rain", "severity", "priority"),
    [
        (8.0, 2.0, "low", "standard"),
        (18.0, 5.0, "moderate", "standard"),
        (25.0, 5.0, "high", "priority"),
        (10.0, 55.0, "critical", "urgent"),
    ],
)
def test_decision_support_is_bounded_and_advisory(gust, rain, severity, priority):
    support = aurora._decision_support(
        {
            "max_wind_gust_ms": gust,
            "total_precipitation_mm": rain,
            "series": [
                {
                    "valid_at": "2026-11-06T01:00:00Z",
                    "wind_gust_ms": gust,
                    "precipitation_mm": rain,
                }
            ],
        }
    )

    assert support["severity"] == severity
    assert support["triage_priority"] == priority
    assert support["advisory_only"] is True
    assert support["human_review_required"] is True
    assert "deny_claim" not in support["recommended_actions"]


def test_channel_sas_requires_official_read_write_create_permissions():
    settings = AuroraSettings(
        channel_sas_url=(
            "https://storage.blob.core.windows.net/weather/aurora?sv=2025-01-05&sp=rwc&sig=test"
        )
    )

    assert aurora._channel_sas_url(settings) == settings.channel_sas_url

    with pytest.raises(AuroraConfigurationError, match="read, write, and create"):
        aurora._channel_sas_url(
            AuroraSettings(
                channel_sas_url=(
                    "https://storage.blob.core.windows.net/weather/aurora"
                    "?sv=2025-01-05&sp=r&sig=test"
                )
            )
        )


def test_entra_token_uses_configured_scope(monkeypatch):
    observed: list[str] = []

    class Credential:
        def get_token(self, scope: str):
            observed.append(scope)
            return type("Token", (), {"token": "entra-token"})()

    monkeypatch.setattr(aurora, "_credential", lambda: Credential())

    token = aurora._endpoint_token(AuroraSettings(token_scope="https://ml.azure.com/.default"))

    assert token == "entra-token"
    assert observed == ["https://ml.azure.com/.default"]


def test_endpoint_request_sends_bearer_token(monkeypatch):
    observed: dict[str, object] = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"task_id": "task-123"}

    def post(url, *, headers, json, timeout):
        observed.update(url=url, headers=headers, json=json, timeout=timeout)
        return Response()

    monkeypatch.setattr(aurora.requests, "post", post)

    result = aurora._foundry_request(
        AuroraSettings(endpoint="https://aurora.example.inference.ml.azure.com/score"),
        "endpoint-key",
        "task_info",
        {"task_id": "task-123"},
    )

    assert result == {"task_id": "task-123"}
    assert observed["headers"] == {
        "Authorization": "Bearer endpoint-key",
        "Content-Type": "application/json",
    }


def test_persisted_admin_config_keeps_secret_auth_mode_from_environment(monkeypatch):
    class Persisted:
        enabled = True
        endpoint = "https://aurora.example.inference.ml.azure.com/score"
        deterministic_model = "aurora-0.25-v1.5"
        ensemble_model = "aurora-0.25-v1.5-ensemble"
        initial_condition_blob_url = "https://storage.blob.core.windows.net/input/current.nc"
        channel_container_url = "https://storage.blob.core.windows.net/channel"
        default_horizon_hours = 12

    monkeypatch.setenv("AURORA_USE_AZURE_AD", "false")
    monkeypatch.setenv("AURORA_ENDPOINT_TOKEN", "endpoint-key")
    monkeypatch.setattr("app.aurora_config.load_config", lambda: Persisted())

    settings = AuroraSettings.from_env()

    assert settings.use_azure_ad is False
    assert settings.endpoint_token == "endpoint-key"


def test_initial_condition_validation_and_location_summary(tmp_path):
    latitude = np.array([47.0, 46.0], dtype=np.float32)
    longitude = np.array([5.0, 6.0], dtype=np.float32)
    history = np.array([0, 1])
    times = np.array(["2026-11-06T00:00:00"], dtype="datetime64[s]")
    variables = {
        f"surf_{name}": (
            ("batch", "history", "latitude", "longitude"),
            np.ones((1, 2, 2, 2), dtype=np.float32),
        )
        for name in aurora._REQUIRED_SURFACE_INPUTS
    }
    variables.update(
        {
            f"atmos_{name}": (
                ("batch", "history", "level", "latitude", "longitude"),
                np.ones((1, 2, 1, 2, 2), dtype=np.float32),
            )
            for name in aurora._REQUIRED_ATMOS_INPUTS
        }
    )
    initial = xr.Dataset(
        variables,
        coords={
            "batch": [0],
            "history": history,
            "latitude": latitude,
            "longitude": longitude,
            "level": [1000],
            "time": times,
        },
    )
    initial_path = tmp_path / "initial.nc"
    initial.to_netcdf(initial_path, engine="h5netcdf")

    timestamp = aurora._validate_initial_condition(initial_path.read_bytes())

    assert timestamp == datetime(2026, 11, 6, 0, tzinfo=UTC)

    prediction = xr.Dataset(
        {
            "surf_2t": (
                ("batch", "history", "latitude", "longitude"),
                np.full((1, 1, 2, 2), 280.15, dtype=np.float32),
            ),
            "surf_10u": (
                ("batch", "history", "latitude", "longitude"),
                np.full((1, 1, 2, 2), 3.0, dtype=np.float32),
            ),
            "surf_10v": (
                ("batch", "history", "latitude", "longitude"),
                np.full((1, 1, 2, 2), 4.0, dtype=np.float32),
            ),
            "surf_i10fg": (
                ("batch", "history", "latitude", "longitude"),
                np.full((1, 1, 2, 2), 8.0, dtype=np.float32),
            ),
            "surf_scaled_tp_1h": (
                ("batch", "history", "latitude", "longitude"),
                np.full((1, 1, 2, 2), 0.002, dtype=np.float32),
            ),
            "surf_tcc": (
                ("batch", "history", "latitude", "longitude"),
                np.full((1, 1, 2, 2), 0.75, dtype=np.float32),
            ),
        },
        coords={
            "batch": [0],
            "history": [0],
            "latitude": latitude,
            "longitude": longitude,
            "time": times,
        },
    )
    prediction_path = tmp_path / "prediction.nc"
    prediction.to_netcdf(prediction_path, engine="h5netcdf")

    summary = aurora._summarize_predictions(
        [prediction_path.read_bytes()], latitude=46.1, longitude=5.9
    )

    assert summary["max_wind_speed_ms"] == 5.0
    assert summary["max_wind_gust_ms"] == 8.0
    assert summary["total_precipitation_mm"] == 2.0
    assert summary["series"][0]["temperature_c"] == 7.0
    assert summary["series"][0]["cloud_cover_percent"] == 75.0


def test_submit_uses_official_foundry_task_and_blob_channel(monkeypatch):
    channel_url = (
        "https://storage.blob.core.windows.net/weather/aurora?sv=2025-01-05&sp=rwc&sig=test"
    )
    settings = AuroraSettings(
        enabled=True,
        endpoint="https://aurora.example.inference.ml.azure.com/score",
        initial_condition_blob_url=(
            "https://storage.blob.core.windows.net/weather/initial/current.nc?sig=input"
        ),
        channel_sas_url=channel_url,
        endpoint_token="endpoint-token",
        use_azure_ad=False,
        timeout_seconds=60,
        poll_interval_seconds=0,
    )
    requests: list[tuple[str, dict]] = []
    uploads: list[tuple[str, str, bytes]] = []
    downloads: list[str] = []

    monkeypatch.setattr(aurora, "_download_initial_condition", lambda _: b"netcdf")
    monkeypatch.setattr(
        aurora,
        "_validate_initial_condition",
        lambda _: datetime(2026, 11, 6, 0, tzinfo=UTC),
    )

    def foundry_request(_settings, token, message_type, message):
        assert token == "endpoint-token"
        requests.append((message_type, message))
        if message_type == "submission":
            return {"task_id": "task-123"}
        return {
            "task_id": "task-123",
            "completed": True,
            "success": True,
            "status": "Completed",
        }

    monkeypatch.setattr(aurora, "_foundry_request", foundry_request)
    monkeypatch.setattr(
        aurora,
        "_upload_channel_file",
        lambda folder, name, payload: uploads.append((folder, name, payload)),
    )

    def download_prediction(_folder, _task_id, name, _deadline, _poll_interval):
        downloads.append(name)
        return b"prediction"

    monkeypatch.setattr(aurora, "_download_prediction", download_prediction)
    monkeypatch.setattr(
        aurora,
        "_summarize_predictions",
        lambda predictions, latitude, longitude: {
            "count": len(predictions),
            "latitude": latitude,
            "longitude": longitude,
        },
    )

    result = asyncio.run(
        submit_forecast(
            latitude=46.2,
            longitude=6.1,
            horizon_hours=12,
            ensemble=True,
            application_id="claim-1",
            settings=settings,
        )
    )

    submission = requests[0]
    assert submission[0] == "submission"
    assert submission[1] == {
        "model_name": "aurora-0.25-v1.5-ensemble",
        "num_steps": 2,
        "data_folder_uri": channel_url,
        "fine_lead_times": [1, 2, 3, 4, 5, 6],
        "saved_surf_vars": [
            "2t",
            "10u",
            "10v",
            "i10fg",
            "scaled_tp_1h",
            "scaled_sf_1h",
            "tcc",
        ],
        "saved_atmos_vars": [],
        "saved_atmos_levels": [],
        "saved_static_vars": [],
        "async_upload_workers": 2,
    }
    assert requests[1] == ("task_info", {"task_id": "task-123"})
    assert uploads == [(channel_url, "task-123/input.nc", b"netcdf")]
    assert downloads == [f"prediction-{index:03d}.nc" for index in range(12)]
    assert result["task_id"] == "task-123"
    assert result["model"] == "aurora-0.25-v1.5-ensemble"
    assert result["forecast"]["count"] == 12
    assert "sig=" not in result["provenance"]["initial_condition_blob"]
