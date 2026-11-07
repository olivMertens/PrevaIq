from __future__ import annotations

import json
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
@pytest.mark.parametrize(
    ("language", "signature"),
    [
        ("en", "Your adviser at PrevaIQ"),
        ("fr", "Votre conseiller PrevaIQ"),
        ("de", "Ihre Ansprechperson bei PrevaIQ"),
        ("de-CH", "Ihre Ansprechperson bei PrevaIQ"),
    ],
)
def test_communications_localize_signature_and_preserve_channel(
    monkeypatch, channel, language, signature
):
    settings = SimpleNamespace(app=SimpleNamespace(storage_root="unused"), openai=object())
    metadata = SimpleNamespace(
        persona="habitation_claims",
        status="completed",
        extracted_fields={"NomAssure": {"value": "Marie Lefèvre"}},
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
        json={"language": language, "channel": channel, "tone": "formal"},
    )
    assert response.status_code == 200
    assert response.json()["language"] == language
    assert response.json()["channel"] == channel
    assert response.json()["tone"] == "formal"
    if language == "de-CH":
        assert "Schweizer Hochdeutsch" in captured[0]["content"]
    assert f"Signature: {signature}" in captured[1]["content"]
    assert "Recipient name: Marie Lefèvre" in captured[1]["content"]
    if language != "fr":
        assert "Signature: Votre conseiller" not in captured[1]["content"]
    assert "including SMS" in captured[0]["content"]


def test_workflow_stream_emits_lifecycle_events_and_final_result(monkeypatch):
    settings = SimpleNamespace(app=SimpleNamespace(storage_root="unused"))
    monkeypatch.setattr(api_server, "load_settings", lambda: settings)
    monkeypatch.setattr(
        api_server, "load_application", lambda *_: SimpleNamespace(persona="habitation_claims")
    )

    async def fake_workflow(*args, on_event=None, **kwargs):
        assert kwargs["language"] == "de-CH"
        await on_event({"type": "step", "agent": "ExtractAgent", "status": "running"})
        await on_event({"type": "step", "agent": "ExtractAgent", "status": "completed"})
        return {
            "workflow": "express",
            "status": "completed",
            "steps": [{"agent": "ExtractAgent", "text": "Geprüft"}],
            "summary": "Geprüft",
        }

    monkeypatch.setattr(api_integration, "agent_workflow", fake_workflow)
    response = TestClient(api_server.app).post(
        "/api/applications/APP-1/workflow/express", json={"language": "de-CH", "stream": True}
    )
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert response.headers["content-type"].startswith("text/event-stream")
    assert [event["type"] for event in events] == ["step", "step", "done"]
    assert events[-1]["result"]["summary"] == "Geprüft"


def test_workflow_stream_surfaces_failure_without_a_success_event(monkeypatch):
    monkeypatch.setattr(
        api_server,
        "load_settings",
        lambda: SimpleNamespace(app=SimpleNamespace(storage_root="unused")),
    )
    monkeypatch.setattr(
        api_server, "load_application", lambda *_: SimpleNamespace(persona="habitation_claims")
    )

    async def failing(*args, **kwargs):
        raise RuntimeError("private diagnostic")

    monkeypatch.setattr(api_integration, "agent_workflow", failing)
    response = TestClient(api_server.app).post(
        "/api/applications/APP-1/workflow/express", json={"stream": True}
    )
    assert '"type": "error"' in response.text
    assert '"type": "done"' not in response.text
    assert "private diagnostic" not in response.text


def test_workflow_stream_disconnect_cancels_producer(monkeypatch):
    import asyncio

    cancelled = False

    async def workflow(*args, on_event=None, **kwargs):
        nonlocal cancelled
        try:
            await on_event({"type": "step", "agent": "ExtractAgent", "status": "running"})
            await asyncio.sleep(60)
        finally:
            cancelled = True

    monkeypatch.setattr(api_integration, "agent_workflow", workflow)

    async def disconnect():
        stream = api_server._stream_workflow(None, "APP-1", "express", "habitation_claims", "en")
        iterator = stream.body_iterator
        assert "connected" in await anext(iterator)
        assert '"running"' in await anext(iterator)
        await iterator.aclose()

    asyncio.run(disconnect())
    assert cancelled
