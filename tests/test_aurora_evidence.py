from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

import app.aurora as aurora
from app.agents.tools import get_application_summary, get_weather_evidence
from app.storage import ApplicationMetadata


@pytest.fixture
def weather():
    return {
        "model": "aurora-0.25-v1.5",
        "task_id": "saved-test-task",
        "requested_at": "2026-11-06T10:00:00Z",
        "initial_condition_at": "2026-08-28T06:00:00Z",
        "horizon_hours": 6,
        "ensemble": False,
        "ensemble_members": 1,
        "forecast": {
            "series": [
                {
                    "valid_at": "2026-08-28T07:00:00Z",
                    "wind_gust_ms": 8.0,
                    "precipitation_mm": 1.0,
                    "temperature_c": 21.1,
                },
                {
                    "valid_at": "2026-08-28T08:00:00Z",
                    "wind_gust_ms": 9.7,
                    "precipitation_mm": 2.359,
                    "temperature_c": 22.2,
                },
            ],
            "max_wind_gust_ms": 9.7,
            "total_precipitation_mm": 3.359,
        },
        "provenance": {
            "provider": "Microsoft Foundry",
            "source": "ERA5 historical initial conditions",
            "initial_condition_blob": "https://weather.blob.core.windows.net/input/initial.nc?sig=TEST_ONLY#TEST_ONLY",
        },
    }


def test_evidence_scope_does_not_use_request_time_as_weather_time(weather):
    context = aurora.weather_evidence_context(weather, now=datetime(2026, 11, 6, tzinfo=UTC))
    assert context["kind"] == "historical_simulation"
    assert context["covers_present"] is False
    assert context["window"] == {
        "starts_at": "2026-08-28T07:00:00+00:00",
        "ends_at": "2026-08-28T08:00:00+00:00",
    }
    assert context["point_count"] == 2
    assert context["kpis"]["gust_change_ms"] == pytest.approx(1.7)
    assert context["kpis"]["min_temperature_c"] == 21.1
    assert context["kpis"]["max_temperature_c"] == 22.2
    assert context["source"]["initial_condition_blob"].endswith("/initial.nc")
    assert context["usage_limits"]["observed_weather"] is False
    assert context["usage_limits"]["long_range_or_current_extrapolation"] is False


@pytest.mark.parametrize(
    ("date", "precision", "overlaps", "fully"),
    [
        ("2026-08-28", "day", True, False),
        ("2026-08-28T09:00:00+02:00", "instant", True, True),
        ("2026-08-28T09:00:00Z", "instant", False, False),
        ("2030-08-28", "day", False, False),
    ],
)
def test_requested_scope_is_explicit(weather, date, precision, overlaps, fully):
    scope = aurora.weather_evidence_context(weather, date)["requested_scope"]
    assert scope["precision"] == precision
    assert scope["overlaps"] is overlaps
    assert scope["fully_covered"] is fully


@pytest.mark.parametrize(
    ("hour", "kind", "covers"),
    [
        (6, "model_forecast", False),
        (7, "model_forecast", True),
        (8, "model_forecast", True),
        (9, "historical_simulation", False),
    ],
)
def test_present_coverage_uses_returned_points(weather, hour, kind, covers):
    context = aurora.weather_evidence_context(weather, now=datetime(2026, 8, 28, hour, tzinfo=UTC))
    assert context["kind"] == kind
    assert context["covers_present"] is covers


@pytest.mark.parametrize("date", ["2026-02-31", "2026-08", "28/08/2026", "2026-08-28T07:00:00"])
def test_invalid_requested_dates_fail_explicitly(weather, date):
    with pytest.raises(ValueError):
        aurora.weather_evidence_context(weather, date)


def test_naive_reference_clock_is_rejected(weather):
    with pytest.raises(ValueError, match="timezone"):
        aurora.weather_evidence_context(weather, now=datetime(2026, 11, 6))


@pytest.mark.parametrize("timestamp", ["2026-08-28T07:00:00Z", "2026-08-28T08:00:00", None])
def test_invalid_time_axis_is_rejected(weather, timestamp):
    weather["forecast"]["series"][1]["valid_at"] = timestamp
    with pytest.raises(ValueError):
        aurora.weather_evidence_context(weather)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), "hot", True])
def test_non_numeric_weather_is_not_presented_as_evidence(weather, value):
    weather["forecast"]["series"][0]["temperature_c"] = value
    with pytest.raises(ValueError):
        aurora.weather_evidence_context(weather)


def test_member_count_alone_does_not_establish_uncertainty(weather):
    weather.update(ensemble=True, ensemble_members=2)
    assert aurora.weather_evidence_context(weather)["uncertainty_available"] is False


def test_non_object_provenance_is_rejected_explicitly(weather):
    weather["provenance"] = "invalid"
    with pytest.raises(ValueError, match="provenance"):
        aurora.weather_evidence_context(weather)


def test_saved_api_returns_the_same_read_only_context(monkeypatch, weather):
    import asyncio
    import api_server

    monkeypatch.setattr(aurora, "status", lambda: {"mode": "managed_foundry"})

    monkeypatch.setattr(
        api_server,
        "load_settings",
        lambda: SimpleNamespace(app=SimpleNamespace(storage_root="unused")),
    )
    monkeypatch.setattr(
        api_server,
        "load_application",
        lambda *args: SimpleNamespace(llm_outputs={"aurora": weather}),
    )
    monkeypatch.setattr(
        api_server,
        "submit_forecast",
        lambda *args, **kwargs: pytest.fail("Saved GET must not run inference"),
    )
    response = asyncio.run(api_server.get_aurora_forecast("weather-case"))
    assert response["result"] is weather
    assert response["context"] == aurora.weather_evidence_context(weather)
    assert response["human_review_required"] is True


def test_agent_reader_and_summary_use_saved_evidence_without_inference(monkeypatch, weather):
    app = ApplicationMetadata(
        id="weather-case",
        created_at="2026-08-28T06:00:00Z",
        external_reference=None,
        status="completed",
        files=[],
        llm_outputs={"aurora": weather},
    )
    monkeypatch.setattr(
        "app.config.load_settings",
        lambda: SimpleNamespace(app=SimpleNamespace(storage_root="unused"), brand_name="PrevaIQ"),
    )
    monkeypatch.setattr("app.storage.load_application", lambda root, application_id: app)
    monkeypatch.setattr(
        aurora,
        "status",
        lambda: {
            "enabled": False,
            "configured": True,
            "disabled_reason": "blob_access_denied",
        },
    )
    monkeypatch.setattr(
        aurora, "_submit_forecast", lambda *a, **kw: pytest.fail("Read submitted inference")
    )
    result = json.loads(get_weather_evidence("weather-case", "2030-08-28"))
    assert result["status"] == "outside_window"
    assert result["inference_triggered"] is False
    assert result["generation_configuration"]["enabled"] is False
    assert result["generation_configuration"]["live_readiness_verified"] is False
    summary = get_application_summary("weather-case")
    assert "Saved Aurora weather evidence" in summary
    assert '"observed_weather": false' in summary
    assert "2026-08-28T07:00:00" in summary


def test_missing_and_invalid_evidence_are_explicit(monkeypatch, weather):
    app = SimpleNamespace(llm_outputs={})
    monkeypatch.setattr(
        "app.config.load_settings",
        lambda: SimpleNamespace(app=SimpleNamespace(storage_root="unused")),
    )
    monkeypatch.setattr("app.storage.load_application", lambda root, application_id: app)
    monkeypatch.setattr(
        aurora, "status", lambda: {"enabled": False, "configured": False, "disabled_reason": None}
    )
    assert json.loads(get_weather_evidence("weather-case"))["status"] == "not_recorded"
    app.llm_outputs = {"aurora": weather}
    assert (
        json.loads(get_weather_evidence("weather-case", "invalid"))["status"]
        == "invalid_evidence_or_date"
    )
    monkeypatch.setattr("app.storage.load_application", lambda root, application_id: None)
    assert json.loads(get_weather_evidence("missing"))["status"] == "application_not_found"
