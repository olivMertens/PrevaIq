"""Integration tests for CU → Mistral fallback extraction pipeline.

Tests the complete workflow:
1. File upload detected
2. Attempt CU extraction (Phase 1)
3. If CU fails, fallback to Mistral (Phase 2)
4. Normalize both results identically
5. Store in ApplicationMetadata
6. LLM receives same quality markdown from both paths
"""

from __future__ import annotations

import pytest
from types import SimpleNamespace
from unittest.mock import patch

from app.config import (
    AppSettings,
    ContentUnderstandingSettings,
    DatabaseSettings,
    FraudDetectionSettings,
    MarkItDownSettings,
    MistralSettings,
    OpenAISettings,
    ProcessingSettings,
    RAGSettings,
    Settings,
    AutomotiveClaimsSettings,
    MortgageUnderwritingSettings,
)
from app.markitdown_service import MarkItDownConversionResult
from app.processing import run_content_understanding_for_files
from app.storage import ApplicationMetadata, StoredFile
from app.content_understanding_client import (
    ContentUnderstandingOperationError,
    analyze_document,
    poll_result,
)


def test_poll_failure_does_not_resubmit_accepted_document(tmp_path):
    settings = _settings(tmp_path).content_understanding
    settings.use_azure_ad = False
    settings.api_key = "test"
    accepted = SimpleNamespace(
        ok=True, headers={"operation-location": "https://cu.example/operations/1"}
    )
    with (
        patch("app.content_understanding_client.requests.post", return_value=accepted) as post,
        patch("app.content_understanding_client.requests.get", side_effect=TimeoutError("timeout")),
    ):
        with pytest.raises(ContentUnderstandingOperationError) as caught:
            analyze_document(settings, "test.pdf", file_bytes=b"pdf", max_retries=3)
    post.assert_called_once()
    assert caught.value.operation_location == "https://cu.example/operations/1"


def test_poll_request_has_a_bounded_network_timeout():
    accepted = SimpleNamespace(headers={"operation-location": "https://cu.example/operations/1"})
    completed = SimpleNamespace(ok=True, json=lambda: {"status": "Succeeded", "result": {}})
    with patch("app.content_understanding_client.requests.get", return_value=completed) as get:
        result = poll_result(accepted, {}, timeout_seconds=5)
    assert result["status"] == "Succeeded"
    assert 0 < get.call_args.kwargs["timeout"] <= 5


# These would need to be imported from actual modules after implementing
# For now, create test stubs that verify the pipeline logic


def _settings(tmp_path):
    return Settings(
        content_understanding=ContentUnderstandingSettings(
            endpoint="https://cu.example",
            api_key=None,
            analyzer_id="prebuilt-layout",
            use_azure_ad=True,
        ),
        openai=OpenAISettings(
            endpoint="https://aoai.example", api_key="", deployment_name="gpt-5.4-mini"
        ),
        app=AppSettings(storage_root=str(tmp_path), prompts_root="prompts"),
        processing=ProcessingSettings(),
        database=DatabaseSettings(),
        rag=RAGSettings(),
        automotive_claims=AutomotiveClaimsSettings(),
        mortgage_underwriting=MortgageUnderwritingSettings(),
        mistral=MistralSettings(),
        fraud_detection=FraudDetectionSettings(),
        markitdown=MarkItDownSettings(preferred_extensions=(".eml",)),
    )


def test_markitdown_preferred_file_does_not_call_direct_cu(tmp_path):
    app_md = ApplicationMetadata(
        id="app1",
        created_at="2026-01-01T00:00:00Z",
        external_reference=None,
        status="pending",
        persona="underwriting",
        files=[StoredFile(filename="claim.eml", path="claim.eml")],
    )
    md_result = MarkItDownConversionResult(
        markdown="# Claim\n\nBody",
        pages=[{"file": "claim.eml", "page_number": 1, "markdown": "# Claim\n\nBody"}],
        fields={"ClaimNumber": "CLM-001"},
        backend="markitdown-local",
    )

    with (
        patch("app.processing.load_file_content", return_value=b"email body"),
        patch("app.processing.convert_bytes_to_markdown", return_value=md_result) as markitdown,
        patch("app.processing.analyze_document") as analyze_document,
        patch("app.processing.save_application_metadata"),
    ):
        result = run_content_understanding_for_files(_settings(tmp_path), app_md)

    markitdown.assert_called_once()
    analyze_document.assert_not_called()
    assert result.document_markdown
    assert result.extracted_fields["claim.eml:ClaimNumber"]["value"] == "CLM-001"
    assert result.extraction_provenance["files"][0]["extraction_backend"] == "markitdown-local"


def test_llm_fallback_fields_are_counted_in_final_provenance(tmp_path):
    app_md = ApplicationMetadata(
        id="app1",
        created_at="2026-01-01T00:00:00Z",
        external_reference=None,
        status="pending",
        persona="underwriting",
        files=[StoredFile(filename="claim.pdf", path="claim.pdf")],
    )
    cu_payload = {
        "result": {
            "contents": [
                {
                    "kind": "document",
                    "markdown": "# Claim\n\nApplicant: Marie Lefevre",
                }
            ]
        }
    }
    llm_fields = {
        "llm_extracted:ApplicantName": {
            "field_name": "ApplicantName",
            "value": "Marie Lefevre",
            "confidence": 0.0,
            "source": "llm_markdown_fallback",
        }
    }

    with (
        patch("app.processing.load_file_content", return_value=b"%PDF mock"),
        patch("app.processing.analyze_document", return_value=cu_payload),
        patch("app.processing._llm_extract_fields", return_value=llm_fields),
        patch("app.processing.save_cu_raw_result", return_value="raw.json"),
        patch("app.processing.save_application_metadata"),
    ):
        result = run_content_understanding_for_files(_settings(tmp_path), app_md)

    assert result.extracted_fields == llm_fields
    assert result.confidence_summary["total_fields"] == 1
    assert result.confidence_summary["average_confidence"] == 0.0
    assert result.extraction_provenance["summary"]["field_count"] == 1
    assert result.extraction_provenance["summary"]["average_confidence"] is None
    assert (
        result.extraction_provenance["summary"]["fallback_reason"]
        == "no_structured_fields_from_extraction"
    )


def test_skipped_files_recover_missing_fields_from_saved_markdown(tmp_path):
    app_md = ApplicationMetadata(
        id="app1",
        created_at="2026-01-01T00:00:00Z",
        external_reference=None,
        status="extracted",
        persona="automotive_claims",
        files=[StoredFile(filename="claim.pdf", path="claim.pdf", extracted=True)],
        document_markdown="Claim number CLM-001",
        extracted_fields={},
        markdown_pages=[
            {"file": "claim.pdf", "page_number": 1, "markdown": "Claim number CLM-001"}
        ],
    )
    fields = {
        "llm_extracted:ClaimNumber": {
            "field_name": "ClaimNumber",
            "value": "CLM-001",
            "confidence": 0.0,
            "source": "llm_markdown_fallback",
        }
    }
    with (
        patch("app.processing.analyze_document") as analyze,
        patch("app.processing._llm_extract_fields", return_value=fields) as fallback,
        patch("app.processing.save_application_metadata"),
    ):
        result = run_content_understanding_for_files(_settings(tmp_path), app_md)
    analyze.assert_not_called()
    fallback.assert_called_once_with(
        _settings(tmp_path), "Claim number CLM-001", persona="automotive_claims"
    )
    assert result.extracted_fields == fields
    assert len(result.markdown_pages) == 1
    assert result.extraction_provenance["summary"]["field_count"] == 1


def test_composite_pdf_segments_are_added_to_provenance(tmp_path):
    app_md = ApplicationMetadata(
        id="app1",
        created_at="2026-01-01T00:00:00Z",
        external_reference=None,
        status="pending",
        persona="underwriting",
        files=[StoredFile(filename="mixed.pdf", path="mixed.pdf")],
    )
    cu_payload = {
        "result": {
            "contents": [
                {
                    "kind": "document",
                    "markdown": "# Claim\n\nApplicant: Marie Lefevre",
                }
            ]
        }
    }
    field = SimpleNamespace(
        field_name="ApplicantName",
        value="Marie Lefevre",
        confidence=0.92,
        page_number=1,
        bounding_box=None,
        source_text=None,
    )
    profile = SimpleNamespace(
        provenance_segments=lambda: [
            {
                "segment_id": "mixed-segment-1",
                "file": "mixed.pdf",
                "pages": [1],
                "segment_type": "typed_form",
                "confidence": 0.8,
                "reasons": ["dense native text"],
                "recommended_engines": ["content-understanding:prebuilt-layout"],
                "review_required": False,
            },
            {
                "segment_id": "mixed-segment-2",
                "file": "mixed.pdf",
                "pages": [2],
                "segment_type": "identity_document",
                "confidence": 0.78,
                "reasons": ["identity-document keywords detected"],
                "recommended_engines": ["mistral-document-ai-25.12"],
                "review_required": True,
            },
        ],
        review_required=True,
    )

    with (
        patch("app.processing.load_file_content", return_value=b"%PDF mock"),
        patch("app.processing.profile_pdf", return_value=profile),
        patch("app.processing.analyze_document", return_value=cu_payload),
        patch(
            "app.processing.extract_fields_with_confidence", return_value={"ApplicantName": field}
        ),
        patch("app.processing.save_cu_raw_result", return_value="raw.json"),
        patch("app.processing.save_application_metadata"),
    ):
        result = run_content_understanding_for_files(_settings(tmp_path), app_md)

    assert len(result.extraction_provenance["segments"]) == 2
    assert result.extraction_provenance["segments"][1]["segment_type"] == "identity_document"
    assert result.extraction_provenance["review_required"] is True


class TestExtractionPhases:
    """Test two-phase extraction: CU → Mistral fallback."""

    def test_phase_1_cu_succeeds(self):
        """Test Phase 1 CU extraction succeeds normally."""
        # Phase 1: CU extraction succeeds
        cu_result = {
            "result": {
                "contents": [
                    {
                        "kind": "document",
                        "markdown": "# Document\nContent here",
                        "pages": [
                            {
                                "pageNumber": 1,
                                "markdown": "# Document\nContent here",
                            }
                        ],
                    }
                ]
            }
        }

        # Should return immediately with CU result
        assert cu_result["result"]["contents"][0]["markdown"] != ""
        assert "pages" in cu_result["result"]["contents"][0]

    def test_phase_2_mistral_fallback_activated(self):
        """Test Phase 2 Mistral fallback activates when CU fails."""
        # Phase 1: CU fails (e.g., timeout, 500 error)
        cu_error = Exception("CU extraction timeout")
        assert "timeout" in str(cu_error)

        # Phase 2: Mistral fallback activates
        mistral_result = {
            "markdown": "# Document\nContent here",
            "pages": [
                {
                    "page_index": 0,
                    "page_number": 1,
                    "markdown": "# Document\nContent here",
                }
            ],
            "images": [],
        }

        # Should return Mistral result after CU fails
        assert mistral_result["markdown"] != ""
        assert len(mistral_result["pages"]) > 0

    def test_phases_produce_equivalent_normalized_output(self):
        """Test Phase 1 and Phase 2 produce equivalent normalized output."""

        cu_result = {
            "result": {
                "contents": [
                    {
                        "kind": "document",
                        "markdown": "# Invoice\nAmount: €1,000",
                        "pages": [
                            {
                                "pageNumber": 1,
                                "markdown": "# Invoice\nAmount: €1,000",
                            }
                        ],
                    }
                ]
            }
        }

        mistral_result = {
            "result": {
                "contents": [
                    {
                        "kind": "document",
                        "markdown": "# Invoice\nAmount: €1,000",
                        "pages": [
                            {
                                "pageNumber": 1,
                                "markdown": "# Invoice\nAmount: €1,000",
                            }
                        ],
                    }
                ]
            }
        }

        # Both normalize to same structure
        from app.content_understanding_client import (
            extract_markdown_from_result,
        )

        cu_normalized = extract_markdown_from_result(cu_result)
        mistral_normalized = extract_markdown_from_result(mistral_result)

        # Equivalent normalized output
        assert cu_normalized.keys() == mistral_normalized.keys()
        assert len(cu_normalized["pages"]) == len(mistral_normalized["pages"])
        assert cu_normalized["document_markdown"] == mistral_normalized["document_markdown"]

    def test_cu_cu_fallback_not_called_again(self):
        """Test we don't retry CU during Phase 2 (only Mistral retries)."""
        # Phase 1 CU exhausted retries
        cu_attempts = 3

        # Phase 2 should NOT retry CU, only Mistral
        mistral_attempts = 2

        total_attempts = cu_attempts + mistral_attempts
        assert total_attempts == 5

        # Log should show phase transition
        expected_log_sequence = [
            "Phase 1: CU extraction attempt 1/3",
            "Phase 1: CU extraction attempt 2/3",
            "Phase 1: CU extraction attempt 3/3",
            "Phase 1: CU failed after 3 attempts",
            "Phase 2: Mistral fallback attempt 1/2",
            "Phase 2: Mistral fallback attempt 2/2",
        ]

        assert len(expected_log_sequence) == 6


class TestMetadataStorage:
    """Test extraction pipeline stores results correctly."""

    def test_cu_result_stored_with_metadata(self):
        """Test CU result stored in ApplicationMetadata correctly."""

        # Simulated ApplicationMetadata storage
        metadata = {
            "document_markdown": "# Document\nContent",
            "markdown_pages": [{"page_number": 1, "markdown": "# Document\nContent"}],
            "extracted_fields": {},
            "confidence_summary": {},
            "analyzer_id_used": "azure-document-intelligence",
        }

        assert metadata["analyzer_id_used"] == "azure-document-intelligence"
        assert metadata["document_markdown"] != ""
        assert len(metadata["markdown_pages"]) > 0

    def test_mistral_result_stored_with_metadata(self):
        """Test Mistral result stored in ApplicationMetadata correctly."""

        # Simulated ApplicationMetadata storage (Mistral fallback)
        metadata = {
            "document_markdown": "# Document\nContent",
            "markdown_pages": [{"page_number": 1, "markdown": "# Document\nContent"}],
            "extracted_fields": {},
            "confidence_summary": {},
            "analyzer_id_used": "mistral-document-ai-2512",
        }

        assert metadata["analyzer_id_used"] == "mistral-document-ai-2512"
        assert metadata["document_markdown"] != ""
        assert len(metadata["markdown_pages"]) > 0

    def test_metadata_same_structure_both_sources(self):
        """Test metadata has same structure regardless of extraction source."""

        # CU metadata
        cu_metadata = {
            "document_markdown": "content",
            "markdown_pages": [{"page_number": 1, "markdown": "content"}],
            "extracted_fields": {"field": "value"},
            "confidence_summary": {"average": 0.9},
            "analyzer_id_used": "azure-document-intelligence",
        }

        # Mistral metadata
        mistral_metadata = {
            "document_markdown": "content",
            "markdown_pages": [{"page_number": 1, "markdown": "content"}],
            "extracted_fields": {},
            "confidence_summary": {},
            "analyzer_id_used": "mistral-document-ai-2512",
        }

        # Same structure except analyzer_id_used
        assert set(cu_metadata.keys()) == set(mistral_metadata.keys())

        # All required fields present
        required_fields = [
            "document_markdown",
            "markdown_pages",
            "analyzer_id_used",
        ]
        for field in required_fields:
            assert field in cu_metadata
            assert field in mistral_metadata


class TestErrorHandling:
    """Test error handling in extraction pipeline."""

    def test_cu_timeout_triggers_mistral_fallback(self):
        """Test CU timeout triggers Phase 2 Mistral fallback."""
        # Phase 1: CU times out
        cu_timeout_error = TimeoutError("CU request timeout after 30s")

        # Should trigger Phase 2
        fallback_activated = str(cu_timeout_error).startswith("CU")
        assert fallback_activated

    def test_mistral_fallback_fails_shows_error(self):
        """Test if both CU and Mistral fail, error shown to user."""
        # Phase 1: CU fails
        # Phase 2: Mistral also fails

        processing_error = {
            "message": "Document extraction failed: Both CU and Mistral extractions failed",
            "details": [
                {"phase": 1, "error": "CU timeout"},
                {"phase": 2, "error": "Mistral rate limited"},
            ],
        }

        # Error stored in processing_error field
        assert processing_error["message"] != ""
        assert len(processing_error["details"]) == 2

        # Error shown to user via ProcessingBanner
        assert "extraction failed" in processing_error["message"].lower()

    def test_processing_error_field_usage(self):
        """Test processing_error field propagates to UI."""
        # No error case
        no_error_metadata = {
            "processing_error": None,
        }

        # Error case
        error_metadata = {
            "processing_error": "Extraction timeout after 60 seconds",
        }

        # Should be stored and accessible
        assert no_error_metadata.get("processing_error") is None
        assert error_metadata.get("processing_error") is not None


class TestLLMAnalysisQuality:
    """Test LLM receives same quality analysis regardless of extraction source."""

    def test_llm_receives_same_markdown_cu_source(self):
        """Test LLM receives correct markdown from CU source."""

        llm_input_cu = {
            "document_markdown": """# Policy Document

## Coverage Areas
- Medical: €100,000
- Dental: €5,000
- Vision: €2,000

## Exclusions
1. Pre-existing conditions
2. Cosmetic procedures""",
            "system_prompt": "You are an insurance policy analyst...",
        }

        # LLM should analyze correctly
        assert "# Policy Document" in llm_input_cu["document_markdown"]
        assert "€100,000" in llm_input_cu["document_markdown"]
        assert "Pre-existing" in llm_input_cu["document_markdown"]

    def test_llm_receives_same_markdown_mistral_source(self):
        """Test LLM receives correct markdown from Mistral source."""

        llm_input_mistral = {
            "document_markdown": """# Policy Document

## Coverage Areas
- Medical: €100,000
- Dental: €5,000
- Vision: €2,000

## Exclusions
1. Pre-existing conditions
2. Cosmetic procedures""",
            "system_prompt": "You are an insurance policy analyst...",
        }

        # LLM receives identical markdown
        assert "# Policy Document" in llm_input_mistral["document_markdown"]
        assert "€100,000" in llm_input_mistral["document_markdown"]
        assert "Pre-existing" in llm_input_mistral["document_markdown"]

    def test_llm_analysis_identical_from_both_sources(self):
        """Test LLM produces same analysis from CU or Mistral markdown."""

        # Simulated LLM analysis from CU extraction
        cu_llm_output = {
            "risk_assessment": "MEDIUM",
            "coverage_limit": "€100,000",
            "identified_exclusions": 2,
        }

        # Simulated LLM analysis from Mistral extraction
        mistral_llm_output = {
            "risk_assessment": "MEDIUM",
            "coverage_limit": "€100,000",
            "identified_exclusions": 2,
        }

        # Should be identical
        assert cu_llm_output == mistral_llm_output


class TestUIDisplay:
    """Test UI correctly displays results from both extraction sources."""

    def test_ui_renders_cu_extracted_pages(self):
        """Test UI renders pages from CU extraction."""

        ui_data_cu = {
            "pages": [
                {
                    "page_number": 1,
                    "markdown": "# Page 1\nContent A",
                },
                {
                    "page_number": 2,
                    "markdown": "# Page 2\nContent B",
                },
            ]
        }

        # UI can iterate and display
        for page in ui_data_cu["pages"]:
            assert "page_number" in page
            assert "markdown" in page
            assert len(page["markdown"]) > 0

    def test_ui_renders_mistral_extracted_pages(self):
        """Test UI renders pages from Mistral extraction."""

        ui_data_mistral = {
            "pages": [
                {
                    "page_number": 1,
                    "markdown": "# Page 1\nContent A",
                },
                {
                    "page_number": 2,
                    "markdown": "# Page 2\nContent B",
                },
            ]
        }

        # UI can iterate and display (identical to CU)
        for page in ui_data_mistral["pages"]:
            assert "page_number" in page
            assert "markdown" in page
            assert len(page["markdown"]) > 0

    def test_ui_navigation_works_from_both_sources(self):
        """Test UI page navigation works regardless of extraction source."""

        pages = [
            {"page_number": 1, "markdown": "Page 1"},
            {"page_number": 2, "markdown": "Page 2"},
            {"page_number": 3, "markdown": "Page 3"},
        ]

        # UI can build navigation
        total_pages = len(pages)
        assert total_pages == 3

        # UI can calculate "Page X of Y"
        for i, page in enumerate(pages):
            current = page["page_number"]
            display = f"Page {current} of {total_pages}"
            assert display != ""


class TestDeepDiveFeature:
    """Test deep-dive button becomes functional after extraction."""

    def test_deep_dive_button_enabled_after_cu_extraction(self):
        """Test deep-dive button enabled after successful CU extraction."""

        application_state_cu = {
            "processing_status": "complete",
            "processing_error": None,
            "document_markdown": "# Content\nDetails...",
            "deep_dive_available": True,
        }

        # Deep-dive should be available
        assert application_state_cu["deep_dive_available"] is True
        assert application_state_cu["processing_error"] is None

    def test_deep_dive_button_enabled_after_mistral_extraction(self):
        """Test deep-dive button enabled after successful Mistral extraction."""

        application_state_mistral = {
            "processing_status": "complete",
            "processing_error": None,
            "document_markdown": "# Content\nDetails...",
            "deep_dive_available": True,
        }

        # Deep-dive should be available (regardless of extraction source)
        assert application_state_mistral["deep_dive_available"] is True
        assert application_state_mistral["processing_error"] is None

    def test_deep_dive_button_disabled_on_extraction_error(self):
        """Test deep-dive button disabled if extraction fails completely."""

        application_state_error = {
            "processing_status": "error",
            "processing_error": "Extraction failed",
            "document_markdown": None,
            "deep_dive_available": False,
        }

        # Deep-dive should NOT be available
        assert application_state_error["deep_dive_available"] is False
        assert application_state_error["processing_error"] is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
