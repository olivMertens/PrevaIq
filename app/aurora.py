"""Aurora 1.5 Foundry integration for weather-aware insurance decisions.

Aurora is a batch Earth-system model. Its Foundry endpoint accepts task
messages while NetCDF initial conditions and predictions move through a
read/write Azure Blob Storage channel.
"""

from __future__ import annotations

import asyncio
import io
import json
import math
import os
import re
import time
import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryFile
from typing import Any, BinaryIO
from urllib.parse import parse_qs, urlparse, urlunparse

import numpy as np
import requests
import xarray as xr
from azure.core.credentials import TokenCredential
from azure.core.exceptions import AzureError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import (
    BlobClient,
    BlobServiceClient,
    ContainerSasPermissions,
    generate_container_sas,
)

from app.telemetry import record_span_error, start_span
from app.utils import setup_logging

logger = setup_logging()


@contextmanager
def _aurora_stage(name: str, **attributes: Any) -> Iterator[Any]:
    """Trace stage outcomes without recording credentials from SDK exception messages."""
    started = time.monotonic()
    with start_span(
        f"aurora.{name}", attributes, tracer_name="workbenchiq.aurora", record_exception=False
    ) as span:
        context = span.get_span_context()
        trace_id = f"{context.trace_id:032x}" if context is not None else "unrecorded"
        logger.info("aurora.stage.started stage=%s trace_id=%s", name, trace_id)
        try:
            yield span
        except Exception as error:
            record_span_error(span, f"Aurora {name} failed", error_type=type(error).__name__)
            logger.error(
                "aurora.stage.failed stage=%s trace_id=%s error_type=%s elapsed_ms=%d",
                name,
                trace_id,
                type(error).__name__,
                (time.monotonic() - started) * 1000,
            )
            raise
        else:
            logger.info(
                "aurora.stage.completed stage=%s trace_id=%s elapsed_ms=%d",
                name,
                trace_id,
                (time.monotonic() - started) * 1000,
            )


class AuroraConfigurationError(RuntimeError):
    """Raised when Aurora is requested but not configured."""


class AuroraServiceError(RuntimeError):
    """Raised when the managed Aurora service cannot be called."""


_DETERMINISTIC_MODEL = "aurora-0.25-v1.5"
_ENSEMBLE_MODEL = "aurora-0.25-v1.5-ensemble"
_REQUIRED_SURFACE_INPUTS = {
    "2t",
    "10u",
    "10v",
    "msl",
    "2d",
    "tcwv",
    "tcc",
    "100u",
    "100v",
    "sp",
    "lcc",
    "mcc",
    "hcc",
    "skt",
    "stl1",
    "swvl1",
    "ci",
    "scaled_sd",
    "insolation",
}
_REQUIRED_ATMOS_INPUTS = {"z", "u", "v", "t", "q"}
_REQUIRED_STATIC_INPUTS = {
    "lsm",
    "z",
    "anor",
    "isor",
    "cvh",
    "cl",
    "dl",
    "cvl",
    "slor",
    "slt_0",
    "slt_1",
    "slt_2",
    "slt_3",
    "slt_4",
    "slt_5",
    "slt_6",
    "slt_7",
    "sdfor",
    "sdor",
    "tvh_0",
    "tvh_18",
    "tvh_19",
    "tvh_3",
    "tvh_4",
    "tvh_5",
    "tvh_6",
    "tvl_0",
    "tvl_1",
    "tvl_10",
    "tvl_11",
    "tvl_13",
    "tvl_16",
    "tvl_17",
    "tvl_2",
    "tvl_7",
    "tvl_9",
}
_SUMMARY_SURFACE_VARIABLES = (
    "2t",
    "10u",
    "10v",
    "i10fg",
    "scaled_tp_1h",
    "scaled_sf_1h",
    "tcc",
)
_WIND_MODERATE_MS = 17.2
_WIND_HIGH_MS = 24.5
_WIND_CRITICAL_MS = 32.7
_RAIN_MODERATE_MM = 10.0
_RAIN_HIGH_MM = 30.0
_RAIN_CRITICAL_MM = 50.0


@dataclass(frozen=True)
class AuroraSettings:
    enabled: bool = False
    disabled_reason: str | None = None
    endpoint: str = ""
    deterministic_model: str = _DETERMINISTIC_MODEL
    ensemble_model: str = _ENSEMBLE_MODEL
    initial_condition_blob_url: str = ""
    channel_container_url: str = ""
    channel_sas_url: str = ""
    endpoint_token: str = ""
    token_scope: str = "https://ml.azure.com/.default"
    timeout_seconds: int = 900
    poll_interval_seconds: float = 2.0
    use_azure_ad: bool = True
    default_horizon_hours: int = 12
    endpoint_expires_at: str | None = None
    configuration_source: str = "environment"

    @classmethod
    def from_environment(cls) -> "AuroraSettings":
        return cls(
            enabled=os.getenv("AURORA_ENABLED", "false").lower() == "true",
            endpoint=os.getenv("AURORA_FOUNDRY_ENDPOINT", "").strip(),
            deterministic_model=os.getenv("AURORA_DEPLOYMENT_NAME", _DETERMINISTIC_MODEL).strip(),
            ensemble_model=os.getenv("AURORA_ENSEMBLE_DEPLOYMENT_NAME", _ENSEMBLE_MODEL).strip(),
            initial_condition_blob_url=os.getenv("AURORA_INITIAL_CONDITION_BLOB_URL", "").strip(),
            channel_container_url=os.getenv("AURORA_CHANNEL_CONTAINER_URL", "").strip(),
            channel_sas_url=os.getenv("AURORA_BLOB_CHANNEL_SAS_URL", "").strip(),
            endpoint_token=os.getenv("AURORA_ENDPOINT_TOKEN", "").strip(),
            token_scope=os.getenv("AURORA_TOKEN_SCOPE", "https://ml.azure.com/.default").strip(),
            timeout_seconds=int(os.getenv("AURORA_TIMEOUT_SECONDS", "900")),
            poll_interval_seconds=float(os.getenv("AURORA_POLL_INTERVAL_SECONDS", "2")),
            use_azure_ad=os.getenv("AURORA_USE_AZURE_AD", "true").lower() == "true",
            default_horizon_hours=int(os.getenv("AURORA_DEFAULT_HORIZON_HOURS", "12")),
            endpoint_expires_at=os.getenv("AURORA_ENDPOINT_EXPIRES_AT", "").strip() or None,
        )

    @classmethod
    def from_env(cls) -> "AuroraSettings":
        environment = cls.from_environment()
        from app.aurora_config import load_config

        persisted = load_config()
        if persisted is None:
            return environment
        return cls(
            enabled=persisted.enabled,
            disabled_reason=persisted.disabled_reason,
            endpoint=persisted.endpoint,
            deterministic_model=persisted.deterministic_model,
            ensemble_model=persisted.ensemble_model,
            initial_condition_blob_url=persisted.initial_condition_blob_url,
            channel_container_url=persisted.channel_container_url,
            channel_sas_url="",
            endpoint_token=environment.endpoint_token,
            token_scope=environment.token_scope,
            timeout_seconds=environment.timeout_seconds,
            poll_interval_seconds=environment.poll_interval_seconds,
            use_azure_ad=environment.use_azure_ad,
            default_horizon_hours=persisted.default_horizon_hours,
            endpoint_expires_at=(
                getattr(persisted, "endpoint_expires_at", None) or environment.endpoint_expires_at
            ),
            configuration_source="admin",
        )

    @property
    def configured(self) -> bool:
        has_channel = bool(self.channel_sas_url or self.channel_container_url)
        has_auth = self.use_azure_ad or bool(self.endpoint_token)
        return (
            self.enabled
            and not self.endpoint_expired
            and bool(self.endpoint)
            and bool(self.initial_condition_blob_url)
            and has_channel
            and has_auth
        )

    @property
    def endpoint_expiration(self) -> datetime | None:
        if not self.endpoint_expires_at:
            return None
        try:
            expiration = datetime.fromisoformat(self.endpoint_expires_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise AuroraConfigurationError(
                "AURORA_ENDPOINT_EXPIRES_AT must be an ISO 8601 timestamp."
            ) from error
        if expiration.tzinfo is None:
            raise AuroraConfigurationError("AURORA_ENDPOINT_EXPIRES_AT must include a timezone.")
        return expiration.astimezone(UTC)

    @property
    def endpoint_expired(self) -> bool:
        expiration = self.endpoint_expiration
        return expiration is not None and expiration <= datetime.now(UTC)


def _credential() -> DefaultAzureCredential:
    return DefaultAzureCredential(exclude_interactive_browser_credential=True)


def _validate_https_url(value: str, name: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.netloc:
        raise AuroraConfigurationError(f"{name} must be an absolute HTTPS URL.")


def _endpoint_token(settings: AuroraSettings) -> str:
    if not settings.use_azure_ad:
        if not settings.endpoint_token:
            raise AuroraConfigurationError(
                "AURORA_ENDPOINT_TOKEN is required when Azure AD authentication is disabled."
            )
        return settings.endpoint_token
    return _credential().get_token(settings.token_scope).token


def _channel_sas_url(settings: AuroraSettings) -> str:
    if settings.channel_sas_url:
        _validate_https_url(settings.channel_sas_url, "AURORA_BLOB_CHANNEL_SAS_URL")
        query = parse_qs(urlparse(settings.channel_sas_url).query)
        permissions = "".join(query.get("sp", []))
        if not {"r", "w", "c"}.issubset(set(permissions)):
            raise AuroraConfigurationError(
                "AURORA_BLOB_CHANNEL_SAS_URL must grant read, write, and create permissions."
            )
        return settings.channel_sas_url

    _validate_https_url(settings.channel_container_url, "AURORA_CHANNEL_CONTAINER_URL")
    parsed = urlparse(settings.channel_container_url)
    path_parts = parsed.path.strip("/").split("/", 1)
    if not path_parts[0]:
        raise AuroraConfigurationError(
            "AURORA_CHANNEL_CONTAINER_URL must include a Blob container name."
        )
    account_name = parsed.netloc.split(".", 1)[0]
    container_name = path_parts[0]
    prefix = path_parts[1].strip("/") if len(path_parts) == 2 else ""
    now = datetime.now(UTC)
    service = BlobServiceClient(
        account_url=f"{parsed.scheme}://{parsed.netloc}",
        credential=_credential(),
    )
    delegation_key = service.get_user_delegation_key(
        key_start_time=now - timedelta(minutes=5),
        key_expiry_time=now + timedelta(seconds=settings.timeout_seconds + 600),
    )
    sas = generate_container_sas(
        account_name=account_name,
        container_name=container_name,
        user_delegation_key=delegation_key,
        permission=ContainerSasPermissions(read=True, write=True, create=True, list=True),
        start=now - timedelta(minutes=5),
        expiry=now + timedelta(seconds=settings.timeout_seconds + 600),
    )
    base_path = f"/{container_name}"
    if prefix:
        base_path = f"{base_path}/{prefix}"
    return urlunparse((parsed.scheme, parsed.netloc, base_path, "", sas, ""))


def _blob_url(folder_sas_url: str, name: str) -> str:
    parsed = urlparse(folder_sas_url)
    path = f"{parsed.path.rstrip('/')}/{name.lstrip('/')}"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", parsed.query, ""))


@contextmanager
def _download_initial_condition(settings: AuroraSettings) -> Iterator[BinaryIO]:
    _validate_https_url(settings.initial_condition_blob_url, "AURORA_INITIAL_CONDITION_BLOB_URL")
    parsed = urlparse(settings.initial_condition_blob_url)
    credential = None if parsed.query else _credential()
    folder = Path(".tmp") / "aurora"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        payload = TemporaryFile(mode="w+b", dir=folder)
    except OSError as exc:
        raise AuroraServiceError("Unable to create the Aurora initial-condition workspace") from exc
    with payload:
        try:
            (
                BlobClient.from_blob_url(settings.initial_condition_blob_url, credential=credential)
                .download_blob(max_concurrency=1)
                .readinto(payload)
            )
            payload.seek(0)
        except (AzureError, OSError, ValueError) as exc:
            raise AuroraServiceError(
                f"Unable to download Aurora initial conditions: {exc}"
            ) from exc
        yield payload


def _validate_initial_condition(payload: bytes | BinaryIO) -> datetime:
    try:
        source = io.BytesIO(payload) if isinstance(payload, bytes) else payload
        with xr.open_dataset(source, engine="h5netcdf") as dataset:
            surface = {name.removeprefix("surf_") for name in dataset if name.startswith("surf_")}
            atmos = {name.removeprefix("atmos_") for name in dataset if name.startswith("atmos_")}
            static = {
                name.removeprefix("static_") for name in dataset if name.startswith("static_")
            }
            missing_surface = sorted(_REQUIRED_SURFACE_INPUTS - surface)
            missing_atmos = sorted(_REQUIRED_ATMOS_INPUTS - atmos)
            missing_static = sorted(_REQUIRED_STATIC_INPUTS - static)
            if missing_surface or missing_atmos or missing_static:
                missing = ", ".join(
                    [
                        *missing_surface,
                        *missing_atmos,
                        *(f"static_{name}" for name in missing_static),
                    ]
                )
                raise AuroraConfigurationError(
                    f"Aurora initial conditions are missing required variables: {missing}."
                )
            if dataset.sizes.get("history", 0) < 2:
                raise AuroraConfigurationError(
                    "Aurora initial conditions must contain at least two history time steps."
                )
            if "time" not in dataset.coords or dataset["time"].size == 0:
                raise AuroraConfigurationError(
                    "Aurora initial conditions must contain a time coordinate."
                )
            timestamp = dataset["time"].values[-1].astype("datetime64[s]").astype(datetime)
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=UTC)
            return timestamp
    except AuroraConfigurationError:
        raise
    except Exception as exc:
        raise AuroraConfigurationError(
            f"Aurora initial conditions are not a valid Aurora NetCDF batch: {exc}"
        ) from exc


def _foundry_request(
    settings: AuroraSettings,
    token: str,
    message_type: str,
    message: dict[str, Any],
) -> dict[str, Any]:
    wrapped = {"data": json.dumps({"type": message_type, "msg": message})}
    try:
        response = requests.post(
            settings.endpoint,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={"input_data": wrapped},
            timeout=min(settings.timeout_seconds, 60),
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise AuroraServiceError(f"Aurora endpoint request failed: {exc}") from exc
    except ValueError as exc:
        raise AuroraServiceError("Aurora endpoint returned a non-JSON response.") from exc
    if not isinstance(data, dict):
        raise AuroraServiceError("Aurora endpoint returned an invalid response shape.")
    return data


def _channel_blob_client(
    folder_sas_url: str, name: str, *, credential: TokenCredential | None = None
) -> BlobClient:
    url = _blob_url(folder_sas_url, name)
    if credential is not None:
        url = urlunparse(urlparse(url)._replace(query=""))
    return BlobClient.from_blob_url(url, credential=credential)


def _upload_channel_file(
    folder_sas_url: str,
    name: str,
    payload: bytes | BinaryIO,
    *,
    credential: TokenCredential | None = None,
) -> None:
    try:
        _channel_blob_client(folder_sas_url, name, credential=credential).upload_blob(
            payload, overwrite=True, max_concurrency=1
        )
        _channel_blob_client(folder_sas_url, f"{name}.finished", credential=credential).upload_blob(
            b"File is available", overwrite=True
        )
    except Exception as exc:
        raise AuroraServiceError(f"Unable to upload Aurora channel input: {exc}") from exc


def _download_prediction(
    folder_sas_url: str,
    task_id: str,
    name: str,
    deadline: float,
    poll_interval: float,
    *,
    credential: TokenCredential | None = None,
) -> bytes:
    marker = _channel_blob_client(
        folder_sas_url, f"{task_id}/{name}.finished", credential=credential
    )
    while True:
        try:
            if marker.exists():
                return (
                    _channel_blob_client(folder_sas_url, f"{task_id}/{name}", credential=credential)
                    .download_blob()
                    .readall()
                )
        except Exception as exc:
            raise AuroraServiceError(f"Unable to download Aurora prediction {name}: {exc}") from exc
        if time.monotonic() >= deadline:
            raise AuroraServiceError(f"Timed out waiting for Aurora prediction {name}.")
        time.sleep(poll_interval)


def _nearest_index(values: np.ndarray, target: float) -> int:
    return int(np.abs(values.astype(float) - target).argmin())


def _surface_value(dataset: xr.Dataset, name: str, lat_index: int, lon_index: int) -> float | None:
    variable = dataset.get(f"surf_{name}")
    if variable is None:
        return None
    value = np.asarray(variable.values)[..., lat_index, lon_index].reshape(-1)[-1]
    return float(value) if np.isfinite(value) else None


def _summarize_predictions(
    predictions: Iterable[bytes], latitude: float, longitude: float
) -> dict[str, Any]:
    series: list[dict[str, Any]] = []
    for payload in predictions:
        with xr.open_dataset(io.BytesIO(payload), engine="h5netcdf") as dataset:
            latitudes = np.asarray(dataset["latitude"].values)
            longitudes = np.asarray(dataset["longitude"].values)
            model_longitude = longitude % 360 if longitudes.min() >= 0 else longitude
            lat_index = _nearest_index(latitudes, latitude)
            lon_index = _nearest_index(longitudes, model_longitude)
            values = {
                name: _surface_value(dataset, name, lat_index, lon_index)
                for name in _SUMMARY_SURFACE_VARIABLES
            }
            u10 = values["10u"]
            v10 = values["10v"]
            timestamp = dataset["time"].values[-1].astype("datetime64[s]")
            series.append(
                {
                    "valid_at": str(timestamp) + "Z",
                    "temperature_c": (
                        round(values["2t"] - 273.15, 2) if values["2t"] is not None else None
                    ),
                    "wind_speed_ms": (
                        round(math.hypot(u10, v10), 2)
                        if u10 is not None and v10 is not None
                        else None
                    ),
                    "wind_gust_ms": (
                        round(values["i10fg"], 2) if values["i10fg"] is not None else None
                    ),
                    "precipitation_mm": (
                        round(values["scaled_tp_1h"] * 1000, 3)
                        if values["scaled_tp_1h"] is not None
                        else None
                    ),
                    "snowfall_mm": (
                        round(values["scaled_sf_1h"] * 1000, 3)
                        if values["scaled_sf_1h"] is not None
                        else None
                    ),
                    "cloud_cover_percent": (
                        round(values["tcc"] * 100, 1) if values["tcc"] is not None else None
                    ),
                }
            )
    return {
        "series": series,
        "max_wind_speed_ms": max(
            (item["wind_speed_ms"] for item in series if item["wind_speed_ms"] is not None),
            default=None,
        ),
        "max_wind_gust_ms": max(
            (item["wind_gust_ms"] for item in series if item["wind_gust_ms"] is not None),
            default=None,
        ),
        "total_precipitation_mm": round(
            sum(
                item["precipitation_mm"] for item in series if item["precipitation_mm"] is not None
            ),
            3,
        ),
    }


def _decision_support(forecast: dict[str, Any]) -> dict[str, Any]:
    """Translate weather metrics into bounded, advisory insurance workflow signals."""
    gust = forecast.get("max_wind_gust_ms")
    precipitation = forecast.get("total_precipitation_mm")
    gust_value = float(gust) if isinstance(gust, int | float) else 0.0
    rain_value = float(precipitation) if isinstance(precipitation, int | float) else 0.0

    if gust_value >= _WIND_CRITICAL_MS or rain_value >= _RAIN_CRITICAL_MM:
        severity = "critical"
        triage_priority = "urgent"
    elif gust_value >= _WIND_HIGH_MS or rain_value >= _RAIN_HIGH_MM:
        severity = "high"
        triage_priority = "priority"
    elif gust_value >= _WIND_MODERATE_MS or rain_value >= _RAIN_MODERATE_MM:
        severity = "moderate"
        triage_priority = "standard"
    else:
        severity = "low"
        triage_priority = "standard"

    signals: list[str] = []
    if gust_value >= _WIND_MODERATE_MS:
        signals.append("strong_wind")
    if rain_value >= _RAIN_MODERATE_MM:
        signals.append("heavy_rain")
    if not signals:
        signals.append("limited_weather_signal")

    if severity in {"critical", "high"}:
        actions = [
            "contact_customer",
            "confirm_safety",
            "preserve_evidence",
            "expedite_adjuster",
            "review_policy_terms",
        ]
        customer_talking_points = [
            "safety_first",
            "confirm_damage_timing",
            "emergency_mitigation",
            "photos_before_repairs",
            "keep_receipts",
        ]
    elif severity == "moderate":
        actions = [
            "contact_customer",
            "preserve_evidence",
            "monitor_conditions",
            "review_policy_terms",
        ]
        customer_talking_points = [
            "confirm_damage_timing",
            "photos_before_repairs",
            "emergency_mitigation",
            "keep_receipts",
        ]
    else:
        actions = ["monitor_conditions", "verify_claim_evidence"]
        customer_talking_points = ["confirm_damage_timing", "photos_before_repairs"]

    hazardous_points = [
        item
        for item in forecast.get("series", [])
        if (item.get("wind_gust_ms") or 0) >= _WIND_MODERATE_MS
        or (item.get("precipitation_mm") or 0) >= 5.0
    ]
    return {
        "severity": severity,
        "triage_priority": triage_priority,
        "signals": signals,
        "recommended_actions": actions,
        "customer_talking_points": customer_talking_points,
        "hazard_window": (
            {
                "starts_at": hazardous_points[0]["valid_at"],
                "ends_at": hazardous_points[-1]["valid_at"],
            }
            if hazardous_points
            else None
        ),
        "thresholds": {
            "wind_gust_ms": {
                "moderate": _WIND_MODERATE_MS,
                "high": _WIND_HIGH_MS,
                "critical": _WIND_CRITICAL_MS,
            },
            "total_precipitation_mm": {
                "moderate": _RAIN_MODERATE_MM,
                "high": _RAIN_HIGH_MM,
                "critical": _RAIN_CRITICAL_MM,
            },
        },
        "advisory_only": True,
        "human_review_required": True,
    }


def _submit_forecast(
    settings: AuroraSettings,
    *,
    latitude: float,
    longitude: float,
    horizon_hours: int,
    ensemble: bool,
    application_id: str | None,
) -> dict[str, Any]:
    if not settings.configured:
        raise AuroraConfigurationError(
            "Aurora is not ready. Configure the Foundry scoring endpoint, a current Aurora "
            "NetCDF initial-condition blob, and a read/write Blob channel."
        )
    _validate_https_url(settings.endpoint, "AURORA_FOUNDRY_ENDPOINT")
    if settings.timeout_seconds < 30:
        raise AuroraConfigurationError("AURORA_TIMEOUT_SECONDS must be at least 30.")

    with _aurora_stage("authentication"):
        token = _endpoint_token(settings)
    with _aurora_stage("blob_delegation"):
        try:
            channel_sas_url = _channel_sas_url(settings)
        except AzureError as error:
            raise AuroraServiceError(
                "Aurora Blob channel is unavailable. Run the administrator readiness test."
            ) from error
    channel_credential = None if settings.channel_sas_url else _credential()
    model = settings.ensemble_model if ensemble else settings.deterministic_model
    num_steps = math.ceil(horizon_hours / 6)
    fine_lead_times = [1, 2, 3, 4, 5, 6]
    task = {
        "model_name": model,
        "num_steps": num_steps,
        "data_folder_uri": channel_sas_url,
        "fine_lead_times": fine_lead_times,
        "saved_surf_vars": list(_SUMMARY_SURFACE_VARIABLES),
        "saved_atmos_vars": [],
        "saved_atmos_levels": [],
        "saved_static_vars": [],
        "async_upload_workers": 2,
    }
    with (
        _aurora_stage("initial_conditions"),
        _download_initial_condition(settings) as initial_condition,
    ):
        initial_condition_at = _validate_initial_condition(initial_condition)
        with _aurora_stage("submission"):
            creation = _foundry_request(settings, token, "submission", task)
        task_id = creation.get("task_id")
        if not isinstance(task_id, str) or not task_id:
            raise AuroraServiceError(f"Aurora did not return a task_id: {creation}")
        initial_condition.seek(0)
        with _aurora_stage("input_upload", **{"aurora.task_id": task_id}):
            _upload_channel_file(
                channel_sas_url,
                f"{task_id}/input.nc",
                initial_condition,
                credential=channel_credential,
            )
    deadline = time.monotonic() + settings.timeout_seconds
    with _aurora_stage("task_poll", **{"aurora.task_id": task_id}) as poll_span:
        polls = 0
        while True:
            progress = _foundry_request(settings, token, "task_info", {"task_id": task_id})
            polls += 1
            poll_span.set_attribute("aurora.poll_count", polls)
            if progress.get("completed"):
                if not progress.get("success"):
                    raise AuroraServiceError(f"Aurora task {task_id} failed.")
                break
            if time.monotonic() >= deadline:
                raise AuroraServiceError(f"Aurora task {task_id} timed out.")
            time.sleep(settings.poll_interval_seconds)

    prediction_count = num_steps * len(fine_lead_times)
    predictions = (
        _download_prediction(
            channel_sas_url,
            task_id,
            f"prediction-{index:03d}.nc",
            deadline,
            settings.poll_interval_seconds,
            credential=channel_credential,
        )
        for index in range(prediction_count)
    )
    requested_at = datetime.now(UTC).isoformat()
    with _aurora_stage("prediction_read", **{"aurora.task_id": task_id}) as output_span:
        forecast = _summarize_predictions(predictions, latitude, longitude)
        output_span.set_attribute("aurora.output_count", prediction_count)
    return {
        "request_id": str(uuid.uuid4()),
        "task_id": task_id,
        "model": model,
        "requested_at": requested_at,
        "initial_condition_at": initial_condition_at.isoformat(),
        "latitude": latitude,
        "longitude": longitude,
        "horizon_hours": horizon_hours,
        "ensemble": ensemble,
        "ensemble_members": 1,
        "forecast": forecast,
        "decision_support": _decision_support(forecast),
        "artifacts": [f"{task_id}/prediction-{index:03d}.nc" for index in range(prediction_count)],
        "metadata": {"application_id": application_id},
        "provenance": {
            "provider": "Microsoft Foundry",
            "model": model,
            "source": "managed_foundry",
            "initial_condition_blob": urlunparse(
                urlparse(settings.initial_condition_blob_url)._replace(query="")
            ),
        },
    }


async def submit_forecast(
    *,
    latitude: float,
    longitude: float,
    horizon_hours: int = 48,
    ensemble: bool = True,
    application_id: str | None = None,
    settings: AuroraSettings | None = None,
) -> dict[str, Any]:
    """Submit one bounded Aurora forecast without blocking the event loop."""
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Latitude must be between -90 and 90 and longitude between -180 and 180.")
    if not 1 <= horizon_hours <= 240:
        raise ValueError("Horizon must be between 1 and 240 hours.")
    if horizon_hours % 6:
        raise ValueError("Horizon must be a multiple of 6 hours.")
    active_settings = settings or AuroraSettings.from_env()
    with _aurora_stage(
        "forecast",
        **{
            "claim.id": application_id,
            "aurora.horizon_hours": horizon_hours,
            "aurora.ensemble": ensemble,
        },
    ) as span:
        result = await asyncio.to_thread(
            _submit_forecast,
            active_settings,
            latitude=latitude,
            longitude=longitude,
            horizon_hours=horizon_hours,
            ensemble=ensemble,
            application_id=application_id,
        )
        span.set_attribute("aurora.task_id", result["task_id"])
        span.set_attribute("aurora.request_id", result["request_id"])
        return result


def weather_evidence_context(
    result: dict[str, Any], requested_date: str = "", *, now: datetime | None = None
) -> dict[str, Any]:
    """Describe saved model evidence without running inference or extending its time window."""
    if not isinstance(result, dict):
        raise ValueError("Saved Aurora evidence must be an object")
    forecast = result.get("forecast")
    if not isinstance(forecast, dict) or not isinstance(forecast.get("series"), list):
        raise ValueError("Saved Aurora evidence has no forecast series")
    series = forecast["series"]
    if not series:
        raise ValueError("Saved Aurora evidence has no hourly points")

    def instant(value: str) -> datetime:
        if not isinstance(value, str):
            raise ValueError("Weather evidence timestamps must be ISO strings")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Weather evidence timestamps must include a timezone")
        return parsed.astimezone(UTC)

    def number(value: Any) -> float | None:
        if value is None:
            return None
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
        ):
            raise ValueError("Weather evidence metrics must be finite numbers")
        return float(value)

    for point in series:
        if not isinstance(point, dict):
            raise ValueError("Weather evidence points must be objects")
        for metric in ("temperature_c", "wind_gust_ms", "precipitation_mm"):
            number(point.get(metric))
    times = [instant(point["valid_at"]) for point in series]
    if any(a >= b for a, b in zip(times, times[1:])):
        raise ValueError("Weather evidence timestamps must be strictly increasing")
    current = now or datetime.now(UTC)
    if current.utcoffset() is None:
        raise ValueError("Weather reference clock must include a timezone")
    current = current.astimezone(UTC)
    start, end = times[0], times[-1]
    scope: dict[str, Any] = {"requested": None, "precision": None, "overlaps": None}
    if requested_date:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", requested_date):
            target = datetime.fromisoformat(requested_date).replace(tzinfo=UTC)
            target_end = target + timedelta(days=1)
            overlaps = target <= end and target_end > start
            precision = "day"
        else:
            target = instant(requested_date)
            target_end = target
            overlaps = start <= target <= end
            precision = "instant"
        scope = {
            "requested": requested_date,
            "precision": precision,
            "overlaps": overlaps,
            "fully_covered": start <= target and target_end <= end,
        }
    temperatures = [p["temperature_c"] for p in series if p.get("temperature_c") is not None]
    first_gust, last_gust = series[0].get("wind_gust_ms"), series[-1].get("wind_gust_ms")
    source = result.get("provenance") or {}
    if not isinstance(source, dict):
        raise ValueError("Weather evidence provenance must be an object")
    source_url = source.get("initial_condition_blob")
    return {
        "kind": "historical_simulation" if end < current else "model_forecast",
        "model": result.get("model"),
        "task_id": result.get("task_id"),
        "initial_condition_at": result.get("initial_condition_at"),
        "requested_at": result.get("requested_at"),
        "window": {"starts_at": start.isoformat(), "ends_at": end.isoformat()},
        "point_count": len(series),
        "horizon_hours": result.get("horizon_hours"),
        "covers_present": start <= current <= end,
        "requested_scope": scope,
        "kpis": {
            "max_wind_gust_ms": number(forecast.get("max_wind_gust_ms")),
            "total_precipitation_mm": number(forecast.get("total_precipitation_mm")),
            "min_temperature_c": min(temperatures) if temperatures else None,
            "max_temperature_c": max(temperatures) if temperatures else None,
            "gust_change_ms": last_gust - first_gust
            if first_gust is not None and last_gust is not None
            else None,
        },
        "source": {
            "provider": source.get("provider"),
            "type": source.get("source"),
            "initial_condition_blob": urlunparse(
                urlparse(source_url)._replace(query="", fragment="")
            )
            if isinstance(source_url, str)
            else None,
        },
        # The normalizer does not persist a validated ensemble distribution.
        "uncertainty_available": False,
        "usage_limits": {
            "advisory_only": True,
            "human_review_required": True,
            "observed_weather": False,
            "worsening_scope": "returned_window_only",
            "long_range_or_current_extrapolation": False,
            "coverage_or_payment_decision": False,
        },
    }


def status(settings: AuroraSettings | None = None) -> dict[str, Any]:
    active_settings = settings or AuroraSettings.from_env()
    missing: list[str] = []
    if not active_settings.endpoint:
        missing.append("endpoint")
    if not active_settings.initial_condition_blob_url:
        missing.append("initial_condition")
    if not (active_settings.channel_sas_url or active_settings.channel_container_url):
        missing.append("blob_channel")
    if not active_settings.use_azure_ad and not active_settings.endpoint_token:
        missing.append("endpoint_token")
    if active_settings.endpoint_expired:
        missing.append("endpoint_expired")
    expiration = active_settings.endpoint_expiration
    seconds_remaining = (
        max(0, int((expiration - datetime.now(UTC)).total_seconds())) if expiration else None
    )
    return {
        "enabled": active_settings.enabled,
        "disabled_reason": (
            active_settings.disabled_reason if not active_settings.enabled else None
        ),
        "configured": active_settings.configured,
        "model": active_settings.deterministic_model,
        "ensemble_model": active_settings.ensemble_model,
        "provider": "Microsoft Foundry",
        "mode": "managed_foundry",
        "human_review_required": True,
        "requires_initial_conditions": True,
        "default_horizon_hours": active_settings.default_horizon_hours,
        "endpoint_expires_at": active_settings.endpoint_expires_at,
        "endpoint_expired": active_settings.endpoint_expired,
        "endpoint_seconds_remaining": seconds_remaining,
        "configuration_source": active_settings.configuration_source,
        "missing": missing,
    }
