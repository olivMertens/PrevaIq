"""Explicit synthetic weather scenarios; never a fallback for failed model inference."""

from __future__ import annotations

import math
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

DemoScenario = Literal["swiss-chocolate-storm", "swiss-watch-storm", "wine-cellar"]
DEMO_SCENARIOS: tuple[DemoScenario, ...] = (
    "swiss-chocolate-storm",
    "swiss-watch-storm",
    "wine-cellar",
)
DEMO_MODEL = "prevaiq-synthetic-weather-v1"


@dataclass(frozen=True)
class DemoProfile:
    starts_at: str
    latitude: float
    longitude: float
    temperature_c: float
    gusts: tuple[float, ...]
    rain: tuple[float, ...]


PROFILES: dict[DemoScenario, DemoProfile] = {
    "swiss-chocolate-storm": DemoProfile(
        "2026-08-28T06:00:00+00:00",
        47.4981698,
        8.7292096,
        22.0,
        (12, 18, 25, 29, 27, 22, 19, 17, 15, 13, 11, 9),
        (1, 3, 6, 8, 7, 4, 2, 1, 0.8, 0.4, 0.2, 0),
    ),
    "swiss-watch-storm": DemoProfile(
        "2026-08-28T06:00:00+00:00",
        47.7086398,
        8.6305155,
        21.0,
        (14, 22, 31, 35, 30, 25, 21, 18, 16, 14, 12, 10),
        (1, 2, 5, 7, 6, 4, 2, 1, 0.5, 0.2, 0.1, 0),
    ),
    "wine-cellar": DemoProfile(
        "2026-03-27T06:00:00+00:00",
        48.8566,
        2.3522,
        11.0,
        (11, 16, 20, 23, 21, 18, 16, 14, 12, 10, 8, 7),
        (4, 6, 9, 11, 9, 6, 4, 3, 2, 1, 0.5, 0.2),
    ),
}


def generate_demo_forecast(
    scenario: DemoScenario,
    *,
    horizon_hours: int = 6,
    latitude: float | None = None,
    longitude: float | None = None,
    application_id: str | None = None,
) -> dict[str, Any]:
    from app.aurora import _decision_support, _summarize_series, weather_evidence_context

    if scenario not in PROFILES:
        raise ValueError("Unknown synthetic weather scenario")
    if horizon_hours not in (6, 12):
        raise ValueError("Synthetic demo horizons must be 6 or 12 hours")
    profile = PROFILES[scenario]
    lat = profile.latitude if latitude is None else latitude
    lon = profile.longitude if longitude is None else longitude
    if (
        not math.isfinite(lat)
        or not math.isfinite(lon)
        or not -90 <= lat <= 90
        or not -180 <= lon <= 180
    ):
        raise ValueError("Synthetic demo coordinates are invalid")
    start = datetime.fromisoformat(profile.starts_at)
    series = [
        {
            "valid_at": (start + timedelta(hours=index + 1)).isoformat(),
            "temperature_c": round(profile.temperature_c - min(index, 4) * 0.6, 2),
            "wind_speed_ms": round(profile.gusts[index] * 0.55, 2),
            "wind_gust_ms": profile.gusts[index],
            "precipitation_mm": profile.rain[index],
            "snowfall_mm": 0.0,
            "cloud_cover_percent": max(55.0, 100.0 - index * 3),
        }
        for index in range(horizon_hours)
    ]
    forecast = _summarize_series(series)
    result = {
        "request_id": str(uuid.uuid4()),
        "task_id": f"demo-{uuid.uuid4()}",
        "model": DEMO_MODEL,
        "requested_at": datetime.now(UTC).isoformat(),
        "latitude": lat,
        "longitude": lon,
        "horizon_hours": horizon_hours,
        "ensemble": False,
        "ensemble_members": 1,
        "forecast": forecast,
        "decision_support": _decision_support(forecast),
        "artifacts": [],
        "metadata": {"application_id": application_id, "inference_triggered": False},
        "provenance": {
            "provider": "PrevaIQ demo",
            "model": DEMO_MODEL,
            "source": "demo_simulation",
            "synthetic": True,
            "scenario_id": scenario,
            "scenario_version": 1,
            "scenario_started_at": profile.starts_at,
        },
    }
    weather_evidence_context(result)
    return result


def validate_demo_scenario(scenario: DemoScenario) -> None:
    for horizon in (6, 12):
        result = generate_demo_forecast(scenario, horizon_hours=horizon)
        points = result["forecast"]["series"]
        if len(points) != horizon or result["provenance"]["synthetic"] is not True:
            raise ValueError("Synthetic scenario output contract is invalid")
