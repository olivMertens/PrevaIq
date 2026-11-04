from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents import tools as agent_tools
from app.claims import api as claims_api


@pytest.fixture
def client(monkeypatch):
    settings = SimpleNamespace(
        fraud_detection=SimpleNamespace(enabled=True),
        app=SimpleNamespace(storage_root="unused"),
    )
    monkeypatch.setattr(claims_api, "load_settings", lambda: settings)
    monkeypatch.setattr(claims_api, "load_application", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.storage.load_application", lambda *_args, **_kwargs: None)
    app = FastAPI()
    app.include_router(claims_api.router)
    return TestClient(app)


def test_fraud_analysis_generates_content_in_the_ui_language(client, monkeypatch):
    calls = []

    def fake_analyze(**kwargs):
        calls.append(kwargs)
        return json.dumps(
            {
                "web_intelligence": {
                    "overall_assessment": "Unwetter in Bordeaux bestätigt.",
                    "search_queries": ["météo Bordeaux 27 mars 2026 pluie vent orage"],
                }
            }
        )

    monkeypatch.setattr(agent_tools, "analyze_image_fraud", fake_analyze)

    response = client.post("/api/claims/APP-1/fraud-analysis?language=de-DE")

    assert response.status_code == 200
    assert calls[0]["language"] == "de"
    assert response.json()["web_intelligence"]["search_queries"] == [
        "météo Bordeaux 27 mars 2026 pluie vent orage"
    ]


def test_fraud_analysis_rejects_unsupported_language(client, monkeypatch):
    def fail_analyze(**_kwargs):
        pytest.fail("analysis must not run for an unsupported language")

    monkeypatch.setattr(agent_tools, "analyze_image_fraud", fail_analyze)

    response = client.post("/api/claims/APP-1/fraud-analysis?language=es")

    assert response.status_code == 400
    assert "Unsupported language" in response.json()["detail"]
