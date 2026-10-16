from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from api_server import application_to_dict
from app.config import ProcessingSettings
from app.orchestration import (
    REVIEW_AUTO_OK,
    REVIEW_DONE,
    REVIEW_NEEDED,
    StageBudget,
    assess_analysis,
    assess_extraction,
    mark_reviewed,
    record_stage,
)
from app.processing import run_content_understanding_for_files
from app.storage import ApplicationMetadata, StoredFile
from tests.test_extraction_pipeline import _settings


def _app(**kwargs) -> ApplicationMetadata:
    base = dict(
        id="app1",
        created_at="2026-01-01T00:00:00Z",
        external_reference=None,
        status="pending",
        persona="underwriting",
        files=[StoredFile(filename="claim.pdf", path="claim.pdf")],
    )
    base.update(kwargs)
    return ApplicationMetadata(**base)


def test_budget_charges_tokens_and_caps_reextractions():
    budget = StageBudget(stage="analysis", max_seconds=0, max_tokens=100, max_reextractions=1)
    budget.charge({"prompt_tokens": 60, "completion_tokens": 30})
    assert budget.tokens_used == 90 and not budget.exhausted()
    budget.charge({"total_tokens": 20})
    assert budget.tokens_exhausted()
    assert budget.can_reextract()
    budget.reextractions = 1
    assert not budget.can_reextract()


def test_time_budget_exhaustion():
    budget = StageBudget(stage="extraction", max_seconds=1)
    budget.started -= 5
    assert budget.time_exhausted() and not budget.can_reextract()


@pytest.mark.parametrize("cap,expected_calls", [(0, 0), (1, 1)])
def test_targeted_reextraction_is_bounded(tmp_path, cap, expected_calls):
    settings = _settings(tmp_path)
    settings.mistral.enabled = True
    settings.processing.max_reextractions = cap
    payload = {"result": {"contents": [{"kind": "document", "markdown": "# Claim\n\nShort"}]}}
    field = SimpleNamespace(
        field_name="ClaimNumber",
        value="CLM-001",
        confidence=0.9,
        page_number=1,
        bounding_box=None,
        source_text=None,
    )
    with (
        patch("app.processing.load_file_content", return_value=b"%PDF mock"),
        patch("app.processing.analyze_document", return_value=payload),
        patch("app.processing.extract_fields_with_confidence", return_value={"ClaimNumber": field}),
        patch("app.processing._try_mistral_document_fallback", return_value=None) as mistral,
        patch("app.processing.save_cu_raw_result", return_value="raw.json"),
        patch("app.processing.save_application_metadata"),
    ):
        result = run_content_understanding_for_files(settings, _app())

    assert mistral.call_count == expected_calls
    trace = result.orchestration["stages"]["extraction"]
    assert trace["reextractions"] == expected_calls
    assert result.orchestration["review"]["status"] == REVIEW_NEEDED
    codes = {r["code"] for r in result.orchestration["review"]["reasons"]}
    assert "low_extraction_quality" in codes


def test_exhausted_extraction_budget_skips_files_and_requires_review(tmp_path):
    settings = _settings(tmp_path)
    with (
        patch.object(StageBudget, "time_exhausted", return_value=True),
        patch("app.processing.analyze_document") as analyze,
        patch("app.processing.save_application_metadata"),
    ):
        result = run_content_understanding_for_files(settings, _app())
    analyze.assert_not_called()
    assert result.orchestration["stages"]["extraction"]["skipped"] == ["claim.pdf"]
    codes = {r["code"] for r in result.orchestration["review"]["reasons"]}
    assert {"no_content", "extraction_budget_exhausted"} <= codes


def test_clean_extraction_is_auto_ok():
    cfg = ProcessingSettings()
    budget = StageBudget.for_extraction(cfg)
    reasons = assess_extraction(
        budget=budget,
        file_provenance=[{"file": "a.pdf", "media_type": "document", "quality_score": 90}],
        confidence_summary={"average_confidence": 0.92},
        has_content=True,
        composite_review_required=False,
        cfg=cfg,
    )
    app_md = _app()
    record_stage(app_md, budget, reasons)
    assert app_md.orchestration["review"]["status"] == REVIEW_AUTO_OK


def test_analysis_errors_and_review_completion():
    budget = StageBudget(stage="analysis", max_seconds=0)
    reasons = assess_analysis(
        budget=budget,
        results={"summary": {"a": {"parsed": {"_error": "boom"}}, "b": {"parsed": {}}}},
    )
    assert reasons == [{"code": "analysis_errors", "detail": ["summary.a"]}]
    app_md = _app()
    record_stage(app_md, budget, reasons)
    assert app_md.orchestration["review"]["status"] == REVIEW_NEEDED
    mark_reviewed(app_md, decision="approve", decided_at="2026-01-02T00:00:00Z")
    assert app_md.orchestration["review"]["status"] == REVIEW_DONE
    assert app_md.orchestration["review"]["reasons"]


# Stable API/UI contract: new keys may be added, existing keys must never disappear.
_CONTRACT_KEYS = {
    "id",
    "created_at",
    "external_reference",
    "status",
    "persona",
    "files",
    "document_markdown",
    "markdown_pages",
    "cu_raw_result_path",
    "llm_outputs",
    "extracted_fields",
    "confidence_summary",
    "analyzer_id_used",
    "extraction_provenance",
    "risk_analysis",
    "processing_status",
    "processing_error",
    "sentiment_analysis",
    "fraud_analysis",
    "context_labels",
    "context_tasks",
    "processing_mode",
    "condensed_context",
    "document_stats",
    "batch_summaries",
    "orchestration",
}


def test_application_contract_keys_are_stable():
    payload = application_to_dict(_app())
    assert _CONTRACT_KEYS <= set(payload)
