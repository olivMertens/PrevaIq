from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import api_server
from app.agents import api_integration
from app.languages import require_language


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


@pytest.mark.parametrize("language", ["de", "de-CH"])
def test_workflow_endpoint_forwards_locale_and_review_status(monkeypatch, language):
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
        json={"language": language},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "needs_review"
    assert captured == {
        "settings": settings,
        "app_id": "APP-1",
        "workflow_id": "complet",
        "persona": "automotive_claims",
        "language": require_language(language),
    }


def test_swiss_ui_chat_normalizes_language_without_changing_agent_or_corrections(monkeypatch):
    settings = SimpleNamespace(app=SimpleNamespace(storage_root="unused"))
    monkeypatch.setattr(api_server, "load_settings", lambda: settings)
    monkeypatch.setattr(
        api_server,
        "load_application",
        lambda *_args: SimpleNamespace(persona="habitation_claims"),
    )
    captured = {}

    async def fake_chat(*args, **kwargs):
        captured.update(kwargs)
        return {"response": "Die Deckung ist zu prüfen."}

    monkeypatch.setattr(api_integration, "agent_chat", fake_chat)
    response = TestClient(api_server.app).post(
        "/api/applications/APP-1/chat",
        json={
            "message": "Welche Deckung gilt?",
            "language": "de-CH",
            "agent_type": "policy",
            "use_corrections": False,
        },
    )
    assert response.status_code == 200
    assert captured == {"agent_type": "policy", "use_corrections": False, "language": "de-CH"}


@pytest.mark.parametrize("channel", ["email", "sms", "letter"])
def test_swiss_ui_communications_accept_the_locale_and_preserve_channel(monkeypatch, channel):
    settings = SimpleNamespace(app=SimpleNamespace(storage_root="unused"), openai=object())
    metadata = SimpleNamespace(
        persona="habitation_claims",
        status="completed",
        extracted_fields={},
        llm_outputs={},
        sentiment_analysis=None,
        fraud_analysis=None,
        files=[],
    )
    monkeypatch.setattr(api_server, "load_settings", lambda: settings)
    monkeypatch.setattr(api_server, "load_application", lambda *_args: metadata)
    captured = []

    def fake_completion(_settings, messages, **_kwargs):
        captured.extend(messages)
        return {"content": '{"subject": "Ihr Schadenfall", "body": "Wir prüfen die Belege."}'}

    monkeypatch.setattr("app.openai_client.chat_completion", fake_completion)
    response = TestClient(api_server.app).post(
        "/api/applications/APP-1/generate-communication",
        json={"language": "de-CH", "channel": channel, "tone": "formal"},
    )
    assert response.status_code == 200
    assert response.json()["language"] == "de-CH"
    assert response.json()["channel"] == channel
    assert response.json()["tone"] == "formal"
    assert "Schweizer Hochdeutsch" in captured[0]["content"]
