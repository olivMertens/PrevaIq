from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

import app.aurora as aurora
import app.aurora_admin_api as admin_api
import app.aurora_config as config_store
from app.aurora_demo import DEMO_SCENARIOS, PROFILES, generate_demo_forecast


@pytest.fixture
def local_store(monkeypatch, tmp_path):
    monkeypatch.setattr(config_store, "_get_blob_container", lambda: None)
    monkeypatch.setenv("UW_APP_STORAGE_ROOT", str(tmp_path))
    return tmp_path


def demo_settings(**overrides):
    values = {
        "demo_enabled": True,
        "demo_validated_at": datetime.now(UTC).isoformat(),
        "demo_validated_by": "local-admin",
        "endpoint_expires_at": "2020-01-01T00:00:00Z",
    }
    values.update(overrides)
    return aurora.AuroraSettings(**values)


@pytest.mark.parametrize("scenario", DEMO_SCENARIOS)
@pytest.mark.parametrize("horizon", [6, 12])
def test_synthetic_scenarios_have_exact_hourly_points_and_consistent_kpis(scenario, horizon):
    result = generate_demo_forecast(scenario, horizon_hours=horizon)
    repeated = generate_demo_forecast(scenario, horizon_hours=horizon)
    forecast = result["forecast"]
    points = forecast["series"]
    start = datetime.fromisoformat(PROFILES[scenario].starts_at)
    assert len(points) == horizon
    assert points == repeated["forecast"]["series"]
    for index, point in enumerate(points, 1):
        assert datetime.fromisoformat(point["valid_at"]) == start + timedelta(hours=index)
        assert 0 <= point["cloud_cover_percent"] <= 100
        assert 0 <= point["wind_speed_ms"] <= point["wind_gust_ms"]
        assert point["precipitation_mm"] >= 0
    assert forecast["max_wind_gust_ms"] == max(p["wind_gust_ms"] for p in points)
    assert forecast["total_precipitation_mm"] == pytest.approx(
        sum(p["precipitation_mm"] for p in points)
    )
    assert result["provenance"]["synthetic"] is True
    assert result["artifacts"] == []
    assert "initial_condition_blob" not in result["provenance"]
    assert "initial_condition_at" not in result
    assert result["decision_support"]["human_review_required"] is True
    assert result["decision_support"]["advisory_only"] is True
    context = aurora.weather_evidence_context(result, now=start)
    assert context["kind"] == "demo_simulation"
    assert context["usage_limits"]["synthetic_data"] is True
    assert context["usage_limits"]["observed_weather"] is False
    assert context["usage_limits"]["coverage_or_payment_decision"] is False


def test_expired_or_missing_model_never_contacts_azure_in_demo(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Simulation must not contact the model or weather Storage")

    for name in (
        "_submit_forecast",
        "_endpoint_token",
        "_channel_sas_url",
        "_download_initial_condition",
    ):
        monkeypatch.setattr(aurora, name, forbidden)
    settings = demo_settings()
    assert settings.endpoint_expired is True
    assert settings.configured is True
    availability = aurora.status(settings)
    assert availability["mode"] == "demo_simulation"
    assert availability["enabled"] is True
    assert availability["endpoint_expires_at"] is None
    assert availability["requires_initial_conditions"] is False
    result = asyncio.run(
        aurora.submit_forecast(
            latitude=47.49,
            longitude=8.72,
            horizon_hours=6,
            ensemble=False,
            settings=settings,
        )
    )
    assert result["metadata"]["inference_triggered"] is False


def test_unvalidated_demo_is_not_ready_or_usable():
    settings = demo_settings(demo_validated_at=None)
    assert aurora.status(settings)["configured"] is False
    with pytest.raises(aurora.AuroraConfigurationError, match="validation"):
        asyncio.run(
            aurora.submit_forecast(
                latitude=47,
                longitude=8,
                horizon_hours=6,
                ensemble=False,
                settings=settings,
            )
        )


@pytest.mark.parametrize(
    "changes", [{"horizon_hours": 24}, {"ensemble": True}, {"latitude": float("nan")}]
)
def test_invalid_simulation_requests_fail_explicitly(changes):
    args = dict(latitude=47, longitude=8, horizon_hours=6, ensemble=False, settings=demo_settings())
    args.update(changes)
    with pytest.raises(ValueError):
        asyncio.run(aurora.submit_forecast(**args))


def test_real_failure_is_not_converted_to_synthetic_success(monkeypatch):
    def fail(*args, **kwargs):
        raise aurora.AuroraServiceError("model is offline")

    monkeypatch.setattr(aurora, "_submit_forecast", fail)
    with pytest.raises(aurora.AuroraServiceError, match="offline"):
        asyncio.run(
            aurora.submit_forecast(
                latitude=47,
                longitude=8,
                horizon_hours=6,
                ensemble=False,
                settings=replace(demo_settings(), demo_enabled=False),
            )
        )


def test_admin_activation_is_validated_audited_and_reversible(local_store):
    body = admin_api.AuroraConfigBody(
        enabled=False,
        disabled_reason="blob_access_denied",
        demo_enabled=True,
        demo_scenario="swiss-watch-storm",
        admin="verified-admin",
        endpoint="https://old.swedencentral.inference.ml.azure.com/score",
        endpoint_expires_at="2020-01-01T00:00:00Z",
    )
    snapshot = admin_api.update_aurora_admin_config(body)
    saved = config_store.load_config()
    assert saved.demo_validated_by == "verified-admin"
    assert saved.demo_validated_at
    assert snapshot["runtime"]["mode"] == "demo_simulation"
    assert snapshot["live_runtime"]["enabled"] is False
    assert snapshot["live_runtime"]["endpoint_expired"] is True
    assert snapshot["ready_count"] == snapshot["total_count"] == 3
    assert aurora.AuroraSettings.from_env().demo_scenario == "swiss-watch-storm"
    assert saved.disabled_reason == "blob_access_denied"
    old_validation = saved.demo_validated_at
    admin_api.update_aurora_admin_config(body.model_copy(update={"demo_scenario": "wine-cellar"}))
    assert config_store.load_config().demo_validated_at != old_validation
    restored = admin_api.update_aurora_admin_config(body.model_copy(update={"demo_enabled": False}))
    assert restored["runtime"]["mode"] == "managed_foundry"
    assert restored["runtime"]["enabled"] is False
    assert restored["configuration"]["endpoint"] == body.endpoint
    assert restored["configuration"]["disabled_reason"] == body.disabled_reason
    assert restored["configuration"]["demo_validated_at"] is None


def test_demo_test_reports_simulation_not_azure_readiness(local_store, monkeypatch):
    admin_api.update_aurora_admin_config(
        admin_api.AuroraConfigBody(demo_enabled=True, admin="admin")
    )
    monkeypatch.setattr(
        admin_api, "_run_readiness_checks", lambda *args: pytest.fail("No Azure probe")
    )
    result = asyncio.run(admin_api.test_aurora_admin_config())
    assert result["mode"] == "demo_simulation"
    assert result["ok"] is True
    assert all(item["detail"] == "synthetic_demo_only" for item in result["checks"])
    assert result["preview"]["provenance"]["source"] == "demo_simulation"


def test_demo_forecast_persists_without_overwriting_real_evidence(local_store, monkeypatch):
    import api_server
    from app.agents.tools import get_weather_evidence

    admin_api.update_aurora_admin_config(
        admin_api.AuroraConfigBody(demo_enabled=True, admin="admin")
    )
    real = {"source": "existing real proof, unchanged"}
    app = SimpleNamespace(llm_outputs={"aurora": real})
    storage = SimpleNamespace(app=SimpleNamespace(storage_root="unused"))
    monkeypatch.setattr(api_server, "load_settings", lambda: storage)
    monkeypatch.setattr(api_server, "load_application", lambda *args: app)
    monkeypatch.setattr(api_server, "save_application_metadata", lambda *args: None)
    response = asyncio.run(
        api_server.create_aurora_forecast(
            "demo-case",
            api_server.AuroraForecastRequest(
                latitude=47.49,
                longitude=8.72,
                horizon_hours=6,
                ensemble=False,
            ),
        )
    )
    assert app.llm_outputs["aurora"] is real
    assert app.llm_outputs["aurora_demo"] is response["result"]
    saved = asyncio.run(api_server.get_aurora_forecast("demo-case"))
    assert saved["context"]["kind"] == "demo_simulation"
    monkeypatch.setattr("app.config.load_settings", lambda: storage)
    monkeypatch.setattr("app.storage.load_application", lambda *args: app)
    evidence = json.loads(get_weather_evidence("demo-case"))
    assert evidence["context"]["usage_limits"]["synthetic_data"] is True
    assert evidence["inference_triggered"] is False
    config_store.save_config(replace(config_store.load_config(), demo_enabled=False), "admin")
    assert aurora.saved_weather_result(app.llm_outputs) is real
    assert app.llm_outputs["aurora_demo"] is response["result"]
