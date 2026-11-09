"""Admin-only Aurora configuration and readiness endpoints."""

from __future__ import annotations

import asyncio
import re
from dataclasses import replace
from datetime import UTC, datetime
from typing import Literal

import requests
from azure.core.exceptions import AzureError, HttpResponseError
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.aurora import (
    AuroraConfigurationError,
    AuroraServiceError,
    AuroraSettings,
    _channel_sas_url,
    _download_initial_condition,
    _endpoint_token,
    _validate_initial_condition,
    status,
)
from app.aurora_config import AuroraAdminConfig, load_config, public_dict, save_config
from app.aurora_demo import (
    DEMO_SCENARIOS,
    DemoScenario,
    generate_demo_forecast,
    validate_demo_scenario,
)
from app.utils import setup_logging

logger = setup_logging()
router = APIRouter(prefix="/api/internal/aurora", tags=["aurora-admin"])


class AuroraConfigBody(BaseModel):
    enabled: bool = False
    demo_enabled: bool = False
    demo_scenario: DemoScenario = "swiss-chocolate-storm"
    disabled_reason: Literal["blob_access_denied"] | None = None
    endpoint: str = Field(default="", max_length=2048)
    deterministic_model: str = Field(default="aurora-0.25-v1.5", max_length=128)
    ensemble_model: str = Field(default="aurora-0.25-v1.5-ensemble", max_length=128)
    initial_condition_blob_url: str = Field(default="", max_length=2048)
    channel_container_url: str = Field(default="", max_length=2048)
    default_horizon_hours: int = Field(default=12, ge=6, le=240)
    endpoint_expires_at: str | None = Field(default=None, max_length=64)
    admin: str = Field(min_length=1, max_length=120)


def _settings_from_config(config: AuroraAdminConfig) -> AuroraSettings:
    environment = AuroraSettings.from_environment()
    return AuroraSettings(
        enabled=config.enabled,
        demo_enabled=config.demo_enabled,
        demo_scenario=config.demo_scenario,
        demo_validated_at=config.demo_validated_at,
        demo_validated_by=config.demo_validated_by,
        disabled_reason=config.disabled_reason,
        endpoint=config.endpoint,
        deterministic_model=config.deterministic_model,
        ensemble_model=config.ensemble_model,
        initial_condition_blob_url=config.initial_condition_blob_url,
        channel_container_url=config.channel_container_url,
        endpoint_token=environment.endpoint_token,
        token_scope=environment.token_scope,
        timeout_seconds=environment.timeout_seconds,
        poll_interval_seconds=environment.poll_interval_seconds,
        use_azure_ad=environment.use_azure_ad,
        default_horizon_hours=config.default_horizon_hours,
        endpoint_expires_at=config.endpoint_expires_at or environment.endpoint_expires_at,
        configuration_source="admin",
    )


def _checklist(settings: AuroraSettings) -> list[dict[str, object]]:
    if settings.demo_enabled:
        return [
            {"id": "demo_scenario", "ready": settings.demo_scenario in DEMO_SCENARIOS},
            {"id": "demo_contract", "ready": bool(settings.demo_validated_at)},
            {"id": "demo_audit", "ready": bool(settings.demo_validated_by)},
        ]
    return [
        {"id": "enabled", "ready": settings.enabled},
        {
            "id": "endpoint_authentication",
            "ready": settings.use_azure_ad or bool(settings.endpoint_token),
        },
        {"id": "endpoint", "ready": bool(settings.endpoint)},
        {"id": "initial_conditions", "ready": bool(settings.initial_condition_blob_url)},
        {
            "id": "blob_channel",
            "ready": bool(settings.channel_container_url or settings.channel_sas_url),
        },
    ]


def _snapshot(config: AuroraAdminConfig | None) -> dict:
    settings = _settings_from_config(config) if config else AuroraSettings.from_env()
    readiness = status(settings)
    checks = _checklist(settings)
    configuration = {
        **public_dict(config),
        "endpoint_expires_at": settings.endpoint_expires_at,
    }
    if config is None:
        configuration = {
            **public_dict(None),
            "enabled": settings.enabled,
            "disabled_reason": settings.disabled_reason,
            "endpoint": settings.endpoint,
            "deterministic_model": settings.deterministic_model,
            "ensemble_model": settings.ensemble_model,
            "initial_condition_blob_url": settings.initial_condition_blob_url,
            "channel_container_url": settings.channel_container_url,
            "default_horizon_hours": settings.default_horizon_hours,
            "endpoint_expires_at": settings.endpoint_expires_at,
            "updated_at": None,
            "updated_by": None,
        }
    return {
        "configuration": configuration,
        "source": "admin" if config else "environment",
        "runtime": readiness,
        "live_runtime": status(replace(settings, demo_enabled=False)),
        "checklist": checks,
        "ready_count": sum(bool(item["ready"]) for item in checks),
        "total_count": len(checks),
        "input_contract": {
            "history_steps": 2,
            "surface_variables": 19,
            "atmospheric_variables": 5,
            "format": "NetCDF",
            "cadence": "hourly",
        },
        "security": {
            "endpoint_authentication": (
                "not_used"
                if settings.demo_enabled
                else "managed_identity"
                if settings.use_azure_ad
                else "key_vault_secret"
            ),
            "storage_authentication": "managed_identity",
            "secrets_persisted": False,
            "sas_persisted": False,
        },
    }


@router.get("")
def get_aurora_admin_config() -> dict:
    try:
        return _snapshot(load_config())
    except (AzureError, OSError, TimeoutError, ValueError) as error:
        logger.error("Aurora configuration load failed: %s", type(error).__name__)
        raise HTTPException(
            status_code=503, detail="Aurora configuration storage unavailable"
        ) from error


@router.put("")
def update_aurora_admin_config(body: AuroraConfigBody) -> dict:
    try:
        if body.demo_enabled:
            validate_demo_scenario(body.demo_scenario)
        saved = save_config(
            AuroraAdminConfig(
                enabled=body.enabled,
                demo_enabled=body.demo_enabled,
                demo_scenario=body.demo_scenario,
                demo_validated_at=datetime.now(UTC).isoformat() if body.demo_enabled else None,
                demo_validated_by=body.admin if body.demo_enabled else None,
                disabled_reason=body.disabled_reason,
                endpoint=body.endpoint,
                deterministic_model=body.deterministic_model,
                ensemble_model=body.ensemble_model,
                initial_condition_blob_url=body.initial_condition_blob_url,
                channel_container_url=body.channel_container_url,
                default_horizon_hours=body.default_horizon_hours,
                endpoint_expires_at=body.endpoint_expires_at,
            ),
            body.admin,
        )
        return _snapshot(saved)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (AzureError, OSError, TimeoutError) as error:
        logger.error("Aurora configuration save failed: %s", type(error).__name__)
        raise HTTPException(
            status_code=503, detail="Aurora configuration storage unavailable"
        ) from error


def _endpoint_probe(settings: AuroraSettings, token: str) -> tuple[bool, str]:
    wrapped = {
        "input_data": {"data": ('{"type":"task_info","msg":{"task_id":"prevaiq-readiness-probe"}}')}
    }
    response = requests.post(
        settings.endpoint,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=wrapped,
        timeout=30,
    )
    if response.status_code in {401, 403}:
        return False, "authentication_failed"
    if response.status_code >= 500:
        return False, "service_unavailable"
    return True, "reachable"


def _failure_diagnostics(error: BaseException) -> dict[str, str | int]:
    cause = error.__cause__ if isinstance(error.__cause__, AzureError) else error
    if not isinstance(cause, HttpResponseError):
        return {}
    diagnostics: dict[str, str | int] = {}
    if isinstance(cause.status_code, int):
        diagnostics["http_status"] = cause.status_code
    headers = cause.response.headers if cause.response is not None else {}
    for field, value in (
        ("error_code", getattr(cause, "error_code", None) or headers.get("x-ms-error-code")),
        ("request_id", headers.get("x-ms-request-id")),
    ):
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", value):
            diagnostics[field] = value
    return diagnostics


def _run_readiness_checks(config: AuroraAdminConfig) -> dict:
    settings = _settings_from_config(config)
    checks: list[dict[str, str | int | bool]] = [
        {"id": "enabled", "ok": settings.enabled, "detail": "enabled"},
    ]

    def record(
        check_id: str,
        action,
        success_detail: str,
        expected: tuple[type[BaseException], ...],
        *,
        operation: str,
        use_result_detail: bool = True,
    ):
        context = {
            "origin": "prevaiq_backend",
            "operation": operation,
            "checked_at": datetime.now(UTC).isoformat(),
        }
        try:
            result = action()
            detail = result if use_result_detail and isinstance(result, str) else success_detail
            checks.append({"id": check_id, "ok": True, "detail": detail, **context})
            return result
        except expected as error:
            diagnostics = {**context, **_failure_diagnostics(error)}
            logger.warning(
                "Aurora readiness check %s failed: %s %s",
                check_id,
                type(error).__name__,
                diagnostics,
            )
            checks.append(
                {"id": check_id, "ok": False, "detail": type(error).__name__, **diagnostics}
            )
            return None

    token = record(
        "endpoint_authentication",
        lambda: _endpoint_token(settings),
        "managed_identity_token_acquired" if settings.use_azure_ad else "endpoint_key_loaded",
        (AuroraConfigurationError, AzureError),
        operation="acquire_endpoint_credential",
        use_result_detail=False,
    )
    if isinstance(token, str):
        endpoint_result = record(
            "endpoint",
            lambda: _endpoint_probe(settings, token),
            "reachable",
            (requests.RequestException, AuroraConfigurationError),
            operation="endpoint_task_info",
        )
        if isinstance(endpoint_result, tuple):
            checks[-1] = {
                **checks[-1],
                "ok": endpoint_result[0],
                "detail": endpoint_result[1],
            }
    else:
        checks.append({"id": "endpoint", "ok": False, "detail": "authentication_required"})

    def validate_initial_conditions() -> str:
        with _download_initial_condition(settings) as payload:
            return _validate_initial_condition(payload).isoformat()

    record(
        "initial_conditions",
        validate_initial_conditions,
        "valid",
        (AuroraConfigurationError, AuroraServiceError, AzureError),
        operation="download_initial_condition",
    )

    record(
        "blob_channel",
        lambda: _channel_sas_url(settings),
        "delegated_sas_created",
        (AuroraConfigurationError, AuroraServiceError, AzureError),
        operation="get_user_delegation_key",
        use_result_detail=False,
    )
    return {
        "ok": all(bool(item["ok"]) for item in checks),
        "checks": checks,
    }


@router.post("/test")
async def test_aurora_admin_config(mode: Literal["active", "live"] = "active") -> dict:
    config = load_config()
    if config is None:
        raise HTTPException(status_code=409, detail="Save Aurora configuration before testing")
    try:
        if config.demo_enabled and mode != "live":
            validate_demo_scenario(config.demo_scenario)
            preview = generate_demo_forecast(config.demo_scenario)
            return {
                "ok": True,
                "mode": "demo_simulation",
                "checks": [
                    {"id": item["id"], "ok": item["ready"], "detail": "synthetic_demo_only"}
                    for item in _checklist(_settings_from_config(config))
                ],
                "preview": preview,
                "configuration": public_dict(config),
            }
        config = replace(config, demo_enabled=False)
        result = await asyncio.to_thread(_run_readiness_checks, config)
        return {**result, "mode": "managed_foundry", "configuration": public_dict(config)}
    except (AzureError, OSError, TimeoutError, ValueError) as error:
        logger.error("Aurora readiness test failed: %s", type(error).__name__)
        raise HTTPException(status_code=503, detail="Aurora readiness test unavailable") from error
