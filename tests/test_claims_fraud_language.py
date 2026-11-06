from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agents import tools as agent_tools
from app.claims import api as claims_api
from app.languages import require_language

PROMPTS_ROOT = Path(__file__).resolve().parents[1] / "prompts"


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


@pytest.mark.parametrize("language", ["de", "de-DE", "de-CH"])
def test_fraud_analysis_generates_content_in_the_ui_language(client, monkeypatch, language):
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

    response = client.post(f"/api/claims/APP-1/fraud-analysis?language={language}")

    assert response.status_code == 200
    assert calls[0]["language"] == require_language(language)
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


def test_fraud_analysis_localizes_image_errors(client, monkeypatch):
    monkeypatch.setattr(
        agent_tools,
        "analyze_image_fraud",
        lambda **_kwargs: json.dumps(
            {"image_analyses": [{"filename": "toit.jpg", "error": "OpenAI API error 429"}]}
        ),
    )

    response = client.post("/api/claims/APP-1/fraud-analysis?language=de")

    assert response.json()["image_analyses"][0]["error"] == (
        "Ratenlimit erreicht — bitte gleich erneut versuchen"
    )


def test_saved_fraud_analysis_is_healed_in_the_ui_language(client, monkeypatch):
    saved = {
        "application_id": "APP-1",
        "image_analyses": [
            {"filename": "toit.jpg", "authenticity_score": 0.2, "is_likely_authentic": False}
        ],
        "overall_assessment": {"overall_fraud_risk": "LOW", "risk_score": 0.0},
    }
    app_md = SimpleNamespace(id="APP-1", fraud_analysis=saved)
    monkeypatch.setattr("app.storage.load_application", lambda *_args, **_kwargs: app_md)

    response = client.get("/api/claims/APP-1/fraud-analysis?language=fr")

    assert response.status_code == 200
    items = response.json()["overall_assessment"]["attention_items"]
    assert [item["label"] for item in items] == ["Image suspecte : toit.jpg"]
    assert client.get("/api/claims/APP-1/fraud-analysis?language=es").status_code == 400


def test_missing_image_file_is_reported_in_the_ui_language(monkeypatch):
    settings = SimpleNamespace(
        fraud_detection=SimpleNamespace(enabled=True),
        app=SimpleNamespace(storage_root="unused", prompts_root=str(PROMPTS_ROOT)),
        brand_name="PrevaIQ",
    )
    app_md = SimpleNamespace(
        id="APP-1",
        files=[SimpleNamespace(filename="toit.jpg")],
        persona="habitation_claims",
        document_markdown="",
        extracted_fields={},
        customer_id=None,
    )
    monkeypatch.setattr("app.config.load_settings", lambda: settings)
    monkeypatch.setattr("app.storage.load_application", lambda *_args, **_kwargs: app_md)
    monkeypatch.setattr(agent_tools, "_load_file_bytes", lambda *_args: None)
    monkeypatch.setattr(agent_tools, "get_application_summary", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(agent_tools, "search_policies", lambda *_args, **_kwargs: "")
    monkeypatch.setattr(agent_tools, "_web_intelligence_available", lambda _settings: False)
    monkeypatch.setattr(agent_tools, "_assess_overall_fraud", lambda *_args, **_kwargs: {})

    result = json.loads(agent_tools._fraud_orchestrator_sync("APP-1", "", "", "medium", "de"))

    assert result["image_analyses"] == [
        {"filename": "toit.jpg", "error": "Die Datei konnte nicht geladen werden"}
    ]


def test_merge_prompt_uses_web_evidence_and_ignores_technical_errors():
    prompts = agent_tools._load_fraud_prompts(str(PROMPTS_ROOT), brand="PrevaIQ")
    system_prompt = prompts["overall_assessment"]["system_prompt"]

    assert "Vérification web (Microsoft Web IQ)" in system_prompt
    assert "n'est pas un indicateur de fraude" in system_prompt
