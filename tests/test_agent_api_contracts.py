from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

import api_server
from app.agents import api_integration


def test_agent_status_reports_installed_framework(monkeypatch):
    monkeypatch.setattr(
        api_server,
        "load_settings",
        lambda: SimpleNamespace(webiq=SimpleNamespace(enabled=True)),
    )

    response = TestClient(api_server.app).get("/api/agents/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["framework"] == api_integration.FRAMEWORK_LABEL
    assert payload["framework"].startswith("Microsoft Agent Framework 1.")
    assert {workflow["id"] for workflow in payload["workflows"]} == {
        "express",
        "complet",
        "fraude",
    }


def test_workflow_endpoint_forwards_locale_and_review_status(monkeypatch):
    settings = SimpleNamespace(app=SimpleNamespace(storage_root="unused"))
    monkeypatch.setattr(api_server, "load_settings", lambda: settings)
    monkeypatch.setattr(
        api_server,
        "load_application",
        lambda root, app_id: SimpleNamespace(persona="automotive_claims"),
    )

    captured = {}

    async def fake_workflow(
        received_settings,
        app_id,
        workflow_id,
        persona,
        language="en",
    ):
        captured.update(
            settings=received_settings,
            app_id=app_id,
            workflow_id=workflow_id,
            persona=persona,
            language=language,
        )
        return {
            "workflow": workflow_id,
            "status": "needs_review",
            "steps": [{"agent": "FraudAgent", "text": "requires_human_review: true"}],
            "summary": "Review required",
        }

    monkeypatch.setattr(api_integration, "agent_workflow", fake_workflow)

    response = TestClient(api_server.app).post(
        "/api/applications/APP-1/workflow/complet",
        json={"language": "de"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "needs_review"
    assert captured == {
        "settings": settings,
        "app_id": "APP-1",
        "workflow_id": "complet",
        "persona": "automotive_claims",
        "language": "de",
    }
