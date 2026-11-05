from __future__ import annotations

import asyncio
import json
import threading
import warnings
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import async_bridge
from app.agents import tools as agent_tools
from app.claims import api as claims_api

PROMPTS_ROOT = Path(__file__).resolve().parents[1] / "prompts"


def _fields(**values: str) -> dict:
    return {key: {"field_name": key, "value": value} for key, value in values.items()}


def _app(persona: str, **fields: str) -> SimpleNamespace:
    return SimpleNamespace(id="APP-1", persona=persona, extracted_fields=_fields(**fields))


def _settings(rag: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        rag=SimpleNamespace(enabled=rag),
        app=SimpleNamespace(prompts_root=str(PROMPTS_ROOT)),
        brand_name="PrevaIQ",
    )


@pytest.fixture
def server_loop():
    """A running loop in a background thread, registered like the FastAPI server loop."""
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    previous = async_bridge._server_loop
    async_bridge.register_server_loop(loop)
    yield loop
    async_bridge._server_loop = previous
    loop.call_soon_threadsafe(loop.stop)
    thread.join(timeout=5)
    loop.close()


@pytest.mark.parametrize(
    ("persona", "category"),
    [
        ("automotive_claims", "automotive"),
        ("life_health_claims", "life_health"),
        ("habitation_claims", "property_casualty"),
        ("property_casualty_claims", "property_casualty"),
        ("unknown", "property_casualty"),
    ],
)
def test_policy_query_targets_the_persona_index(persona: str, category: str) -> None:
    found, query = agent_tools._fraud_policy_query(
        _app(persona, NatureSinistre="Dégât des eaux suite à tempête")
    )
    assert found == category
    assert "Dégât des eaux" in query
    assert "franchise" in query


def test_swiss_claims_search_in_german() -> None:
    category, query = agent_tools._fraud_policy_query(
        _app(
            "habitation_claims",
            NatureSinistre="Hagelsturm",
            LieuSinistre="8400 Winterthur",
            MontantEstime="CHF 1'697'400",
        )
    )
    assert category == "property_casualty_ch"
    assert "Selbstbehalt" in query and "franchise" not in query


def test_swiss_category_falls_back_to_the_swiss_policy_text() -> None:
    text = agent_tools._fallback_policy_search(_settings(), "Kühlgut", "property_casualty_ch")

    assert "CH-AVB-KUE-003" in text and "PC-COV-001" not in text


def test_rag_runs_on_the_server_loop_from_a_worker_thread(server_loop, monkeypatch) -> None:
    calls = []

    async def fake_search(query, category="", top_k=5):
        calls.append((asyncio.get_running_loop(), category, top_k))
        return "### Conditions générales — Art. 12\nFranchise 250 €"

    monkeypatch.setattr(agent_tools, "search_policies", fake_search)

    text = agent_tools._fraud_policy_context(_settings(), _app("habitation_claims"))

    assert text.startswith("### Conditions générales")
    assert calls == [(server_loop, "property_casualty", 5)]


def test_policy_context_is_never_a_coroutine_and_falls_back_to_policy_text(monkeypatch) -> None:
    async def never_called(*args, **kwargs):
        pytest.fail("RAG must not run without a server loop")

    monkeypatch.setattr(agent_tools, "search_policies", never_called)
    monkeypatch.setattr(async_bridge, "_server_loop", None)

    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        text = agent_tools._fraud_policy_context(_settings(), _app("habitation_claims"))

    assert text and "coroutine" not in text
    assert len(text) <= agent_tools._FRAUD_POLICY_MAX_CHARS


def test_empty_rag_result_uses_the_policy_text(server_loop, monkeypatch) -> None:
    async def no_hit(*args, **kwargs):
        return agent_tools._NO_POLICY_FOUND

    monkeypatch.setattr(agent_tools, "search_policies", no_hit)

    text = agent_tools._fraud_policy_context(_settings(), _app("habitation_claims"))

    assert text and text != agent_tools._NO_POLICY_FOUND


def test_policy_text_fallback_follows_the_claim_jurisdiction(monkeypatch) -> None:
    monkeypatch.setattr(async_bridge, "_server_loop", None)
    swiss = _app(
        "habitation_claims",
        NatureSinistre="Hagel / Sturm",
        AdresseAssure="Kakaogasse 7, 8400 Winterthur",
        MontantEstime="CHF 1'697'400.00",
    )
    french = _app("habitation_claims", AdresseAssure="42 rue des Vignobles, 33000 Bordeaux")

    swiss_text = agent_tools._fraud_policy_context(_settings(), swiss)
    french_text = agent_tools._fraud_policy_context(_settings(), french)

    assert "CH-AVB-KUE-003" in swiss_text and "GVZ" in swiss_text
    assert "PC-COV-001" not in swiss_text
    assert "PC-COV-001" in french_text and "CH-AVB" not in french_text


def test_bridge_refuses_to_wait_on_its_own_loop(server_loop) -> None:
    async def call_from_server_loop():
        async def inner():
            return 1

        with pytest.raises(async_bridge.ServerLoopUnavailable):
            async_bridge.run_on_server_loop(inner(), timeout=1)
        return async_bridge.server_loop_available()

    available = asyncio.run_coroutine_threadsafe(call_from_server_loop(), server_loop).result(5)
    assert available is False
    assert async_bridge.server_loop_available() is True


def test_bridge_times_out_and_cancels(server_loop) -> None:
    async def slow():
        await asyncio.sleep(5)

    with pytest.raises(TimeoutError):
        async_bridge.run_on_server_loop(slow(), timeout=0.2)


def test_fraud_endpoint_runs_the_analysis_off_the_event_loop(monkeypatch) -> None:
    seen = {}

    def fake_analyze(**kwargs):
        try:
            asyncio.get_running_loop()
            seen["on_loop"] = True
        except RuntimeError:
            seen["on_loop"] = False
        return json.dumps(
            {
                "overall_assessment": {"overall_fraud_risk": "LOW", "risk_score": 0.1},
                "image_analyses": [
                    {
                        "filename": "IMG.png",
                        "authenticity_score": 0.9,
                        "provenance": {"status": "c2pa", "ai_generated": True},
                    }
                ],
            }
        )

    settings = SimpleNamespace(
        fraud_detection=SimpleNamespace(enabled=True),
        app=SimpleNamespace(storage_root="unused"),
    )
    monkeypatch.setattr(claims_api, "load_settings", lambda: settings)
    monkeypatch.setattr(claims_api, "load_application", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.storage.load_application", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(agent_tools, "analyze_image_fraud", fake_analyze)
    app = FastAPI()
    app.include_router(claims_api.router)

    response = TestClient(app).post("/api/claims/APP-1/fraud-analysis?language=en")

    assert response.status_code == 200
    assert seen == {"on_loop": False}
    # The photo provenance reaches the UI (and the persisted analysis).
    assert response.json()["image_analyses"][0]["provenance"]["ai_generated"] is True
