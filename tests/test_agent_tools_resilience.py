"""Resilience tests for agent data-access tools.

These guard against heterogeneous LLM output shapes (e.g. a nested object where a
string is expected) crashing the tools that agents and multi-agent workflows rely
on. A crash here makes agents like ExtractAgent report a spurious "erreur" and
fall back, which the user observed in the workbench chat.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from app.agents.tools import (
    _coerce_text,
    _pct,
    get_application_summary,
    get_risk_analysis,
    search_policies,
)
from app.storage import ApplicationMetadata


def _make_settings():
    class _AppCfg:
        storage_root = "/tmp/does-not-matter"

    class _Settings:
        app = _AppCfg()
        brand_name = "PrevaIQ"

    return _Settings()


def test_search_policies_merges_persona_tables(monkeypatch) -> None:
    """Auto/health PDFs live in their own tables; the chat must search them all."""
    import app.config
    import app.rag.search

    settings = SimpleNamespace(
        rag=SimpleNamespace(enabled=True), database=SimpleNamespace(schema="workbenchiq")
    )
    monkeypatch.setattr(app.config, "load_settings", lambda: settings)

    def hit(name: str, sim: float):
        return SimpleNamespace(policy_name=name, chunk_type="section", category="c",
                               similarity=sim, content=f"texte {name}")

    by_table = {
        "workbenchiq.policy_chunks": [hit("Habitation", 0.40)],
        "workbenchiq.claim_policy_chunks": [hit("Auto Art. 7.1", 0.82)],
        "workbenchiq.health_claims_policy_chunks": RuntimeError("table missing"),
    }

    class FakeService:
        def __init__(self, _settings):
            self.table = "workbenchiq.policy_chunks"

        async def semantic_search(self, query, top_k):
            result = by_table[self.table]
            if isinstance(result, Exception):
                raise result
            return result

    monkeypatch.setattr(app.rag.search, "PolicySearchService", FakeService)
    text = asyncio.run(search_policies("bris de glace", top_k=2))
    assert text.index("Auto Art. 7.1") < text.index("Habitation")


def test_coerce_text_handles_non_strings() -> None:
    assert _coerce_text(None) == ""
    assert _coerce_text("hello") == "hello"
    assert _coerce_text({"summary": "nested"}) == "nested"
    assert _coerce_text({"a": 1}).startswith("{")
    assert _coerce_text(["a", "b"]) == "a; b"
    assert _coerce_text(42) == "42"


def test_pct_tolerates_bad_values() -> None:
    assert _pct(0.5) == 50
    assert _pct(1) == 100
    assert _pct(80) == 80
    assert _pct(None) == 0
    assert _pct("oops") == 0


def test_get_application_summary_survives_dict_shaped_synthese(monkeypatch) -> None:
    """Regression: liability_assessment.coverage_verification.parsed.synthese was a
    dict in production, and ``synthese[:300]`` raised TypeError, breaking the tool."""
    app_md = ApplicationMetadata(
        id="dossier-1",
        created_at="2026-01-01T00:00:00Z",
        external_reference=None,
        status="completed",
        files=[],
        persona="habitation_claims",
        extracted_fields={
            "doc.pdf:NomAssure": {"field_name": "NomAssure", "value": "MERTENS Olivier"},
        },
        llm_outputs={
            "liability_assessment": {
                "coverage_verification": {
                    "parsed": {"synthese": {"verdict": "couvert", "details": "..."}},
                }
            }
        },
    )
    monkeypatch.setattr("app.config.load_settings", lambda: _make_settings())
    monkeypatch.setattr("app.storage.load_application", lambda root, app_id: app_md)

    result = get_application_summary("dossier-1")

    assert "introuvable" not in result
    assert "MERTENS Olivier" in result
    assert "liability_assessment.coverage_verification" in result


def test_get_application_summary_survives_bad_fraud_scores(monkeypatch) -> None:
    """Regression: round(None * 100) and slicing dict summaries in the fraud block."""
    app_md = ApplicationMetadata(
        id="dossier-3",
        created_at="2026-01-01T00:00:00Z",
        external_reference=None,
        status="completed",
        files=[],
        persona="automotive_claims",
        fraud_analysis={
            "overall_assessment": {
                "overall_fraud_risk": "low",
                "risk_score": None,
                "summary": {"text": "résumé objet"},
                "attention_items": [{"priority": "high", "label": "x", "detail": {"k": "v"}}],
            },
            "image_analyses": [{"filename": "a.png", "authenticity_score": None}],
        },
    )
    monkeypatch.setattr("app.config.load_settings", lambda: _make_settings())
    monkeypatch.setattr("app.storage.load_application", lambda root, app_id: app_md)

    result = get_application_summary("dossier-3")

    assert "Analyse anti-fraude" in result
    assert "Score** : 0%" in result


def test_get_risk_analysis_survives_dict_summary(monkeypatch) -> None:
    app_md = ApplicationMetadata(
        id="dossier-2",
        created_at="2026-01-01T00:00:00Z",
        external_reference=None,
        status="completed",
        files=[],
        persona="underwriting",
        risk_analysis={
            "risk_level": "Moderate",
            "risk_score": 55,
            "confidence": "n/a",
            "summary": {"text": "résumé objet"},
        },
    )
    monkeypatch.setattr("app.config.load_settings", lambda: _make_settings())
    monkeypatch.setattr("app.storage.load_application", lambda root, app_id: app_md)

    result = get_risk_analysis("dossier-2")

    assert "Analyse de risque" in result
    assert "Moderate" in result
