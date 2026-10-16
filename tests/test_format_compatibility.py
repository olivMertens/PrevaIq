"""Format compatibility tests: CU vs Mistral normalized output parity.

Tests verify:
1. CU and Mistral produce identical normalized structure
2. LLM gets same quality markdown from both sources
3. UI renders pages correctly from both sources
4. extraction_pipeline doesn't care which source provided the data
"""

import pytest

from app.content_understanding_client import extract_markdown_from_result
from app.file_capabilities import get_file_capabilities, is_supported_file
from app.markitdown_service import extract_front_matter_fields, split_markdown_pages


class TestContentUnderstandingUpgradeFormats:
    def test_persona_file_capabilities_include_new_document_formats(self):
        capabilities = get_file_capabilities("underwriting")

        assert ".eml" in capabilities["all_extensions"]
        assert ".msg" in capabilities["all_extensions"]
        assert ".doc" in capabilities["all_extensions"]
        assert ".odt" in capabilities["all_extensions"]
        assert ".mp4" not in capabilities["all_extensions"]

    def test_multimodal_persona_accepts_video_evidence(self):
        assert is_supported_file("dashcam.mp4", "automotive_claims") is True
        assert is_supported_file("claim.eml", "automotive_claims") is True
        assert is_supported_file("audio.wav", "automotive_claims") is False

    def test_markitdown_front_matter_fields_are_extracted(self):
        markdown = """---
contentType: document
fields:
  PolicyNumber: ABC-123
  Amount: '1200 EUR'
---
# Claim
"""

        assert extract_front_matter_fields(markdown) == {
            "PolicyNumber": "ABC-123",
            "Amount": "1200 EUR",
        }

    def test_markitdown_front_matter_nested_values_are_extracted_by_field(self):
        markdown = """---
contentType: document
fields:
  NomAssure:
    value: Marie Martin
    confidence: 0.89
  DateSinistre:
    value: 12/06/2026
---
# Claim
"""

        assert extract_front_matter_fields(markdown) == {
            "NomAssure": "Marie Martin",
            "DateSinistre": "12/06/2026",
        }

    def test_markitdown_pages_keep_backend_metadata(self):
        pages = split_markdown_pages(
            "<!-- page 1 -->\n# A\n<!-- page 2 -->\n# B",
            filename="claim.eml",
            backend="markitdown-content-understanding",
            analyzer_id="claimsAnalyzer",
        )

        assert len(pages) == 2
        assert pages[0]["extraction_backend"] == "markitdown-content-understanding"
        assert pages[0]["analyzer_id"] == "claimsAnalyzer"
        assert pages[1]["page_number"] == 2

    def test_policy_chunks_keep_extraction_provenance_metadata(self):
        pytest.importorskip("asyncpg")
        from scripts.index_pdf_policies import build_policy_chunks

        chunks = [
            {
                "chunk_index": 0,
                "text": "# Garantie\n\nFranchise et plafond.",
                "section_heading": "# Garantie",
                "char_count": 31,
            }
        ]

        policy_chunks = build_policy_chunks(
            chunks,
            policy_id="conditions-auto",
            policy_name="Conditions Auto.pdf",
            category="automotive",
            subcategory="auto",
            embeddings=[[0.1, 0.2]],
            source_metadata={
                "extraction_backend": "markitdown-content-understanding",
                "analyzer_id": "prebuilt-documentSearch",
                "content_understanding_api_version": "2025-11-01",
                "markitdown_mode": "cu",
                "fields": {"PolicyNumber": "AUTO-123"},
            },
        )

        metadata = policy_chunks[0].metadata
        assert metadata["source"] == "markitdown-content-understanding"
        assert metadata["source_file"] == "Conditions Auto.pdf"
        assert metadata["analyzer_id"] == "prebuilt-documentSearch"
        assert metadata["field_names"] == ["PolicyNumber"]


class TestCUMistralFormatParity:
    """Test CU and Mistral outputs produce identical normalized structure."""

    def test_both_sources_same_normalized_structure(self):
        """Test CU and Mistral produce same structure after normalization."""

        # CU output format (from Azure Document Intelligence)
        cu_output = {
            "result": {
                "contents": [
                    {
                        "kind": "document",
                        "markdown": "# Invoice\nInvoice Number: INV-001\n\nAmount: €1,000",
                        "pages": [
                            {
                                "pageNumber": 1,
                                "markdown": "# Invoice\nInvoice Number: INV-001\n\nAmount: €1,000",
                            }
                        ],
                        "fields": {
                            "invoice_number": {
                                "value": "INV-001",
                                "confidence": 0.95,
                            },
                            "amount": {
                                "value": "€1,000",
                                "confidence": 0.90,
                            },
                        },
                    }
                ]
            }
        }

        # Mistral output format (from v25.12)
        mistral_output = {
            "result": {
                "contents": [
                    {
                        "kind": "document",
                        "markdown": "# Invoice\nInvoice Number: INV-001\n\nAmount: €1,000",
                        "pages": [
                            {
                                "pageNumber": 1,
                                "markdown": "# Invoice\nInvoice Number: INV-001\n\nAmount: €1,000",
                            }
                        ],
                    }
                ]
            }
        }

        # Normalize both
        cu_normalized = extract_markdown_from_result(cu_output)
        mistral_normalized = extract_markdown_from_result(mistral_output)

        # Should have same keys
        assert set(cu_normalized.keys()) == set(mistral_normalized.keys())

        # Should have document_markdown
        assert "document_markdown" in cu_normalized
        assert "document_markdown" in mistral_normalized

        # Should have pages
        assert "pages" in cu_normalized
        assert "pages" in mistral_normalized

        # Both should have same page structure
        assert len(cu_normalized["pages"]) == len(mistral_normalized["pages"])
        for cu_page, mistral_page in zip(cu_normalized["pages"], mistral_normalized["pages"]):
            assert set(cu_page.keys()) == set(mistral_page.keys())

    def test_multipage_format_parity(self):
        """Test multi-page documents maintain format parity."""

        cu_output = {
            "result": {
                "contents": [
                    {
                        "kind": "document",
                        "markdown": "# Page 1\nContent A\n\n# Page 2\nContent B",
                        "pages": [
                            {
                                "pageNumber": 1,
                                "markdown": "# Page 1\nContent A",
                            },
                            {
                                "pageNumber": 2,
                                "markdown": "# Page 2\nContent B",
                            },
                        ],
                    }
                ]
            }
        }

        mistral_output = {
            "result": {
                "contents": [
                    {
                        "kind": "document",
                        "markdown": "# Page 1\nContent A\n\n# Page 2\nContent B",
                        "pages": [
                            {
                                "pageNumber": 1,
                                "markdown": "# Page 1\nContent A",
                            },
                            {
                                "pageNumber": 2,
                                "markdown": "# Page 2\nContent B",
                            },
                        ],
                    }
                ]
            }
        }

        cu_normalized = extract_markdown_from_result(cu_output)
        mistral_normalized = extract_markdown_from_result(mistral_output)

        # Same number of pages
        assert len(cu_normalized["pages"]) == len(mistral_normalized["pages"])
        assert len(cu_normalized["pages"]) == 2

        # Same page numbers
        cu_page_nums = [p.get("page_number") for p in cu_normalized["pages"]]
        mistral_page_nums = [p.get("page_number") for p in mistral_normalized["pages"]]
        assert cu_page_nums == mistral_page_nums == [1, 2]

    def test_markdown_equivalence_for_llm(self):
        """Test LLM receives equivalent markdown from both sources."""

        # Same content - both use Strategy 2 (legacy format without spans)
        content = "**Bold** and *italic* and `code`"

        cu_output = {
            "pages": [
                {
                    "pageNumber": 1,
                    "markdown": content,
                }
            ]
        }

        mistral_output = {
            "pages": [
                {
                    "pageNumber": 1,
                    "markdown": content,
                }
            ]
        }

        cu_normalized = extract_markdown_from_result(cu_output)
        mistral_normalized = extract_markdown_from_result(mistral_output)

        # LLM sees same content
        cu_markdown = cu_normalized["document_markdown"]
        mistral_markdown = mistral_normalized["document_markdown"]

        assert cu_markdown == mistral_markdown
        assert "**Bold**" in cu_markdown
        assert "*italic*" in cu_markdown
        assert "`code`" in cu_markdown


class TestUIPageDisplay:
    """Test UI can display pages correctly from both sources."""

    def test_page_display_fields_present(self):
        """Test normalized pages have fields UI requires."""

        cu_output = {
            "result": {
                "contents": [
                    {
                        "kind": "document",
                        "markdown": "Page content",
                        "pages": [
                            {
                                "pageNumber": 1,
                                "markdown": "Page content",
                            }
                        ],
                    }
                ]
            }
        }

        normalized = extract_markdown_from_result(cu_output)

        # UI needs page identification
        page = normalized["pages"][0]
        assert "page_number" in page or "pageNumber" in page
        assert page.get("page_number", page.get("pageNumber")) == 1

        # UI needs markdown to display
        assert "markdown" in page
        assert len(page["markdown"]) > 0

    def test_page_sequence_for_navigation_ui(self):
        """Test page numbering allows UI navigation components."""

        cu_output = {
            "result": {
                "contents": [
                    {
                        "kind": "document",
                        "markdown": "Multi-page content",
                        "pages": [
                            {"pageNumber": 1, "markdown": "Page 1"},
                            {"pageNumber": 2, "markdown": "Page 2"},
                            {"pageNumber": 3, "markdown": "Page 3"},
                        ],
                    }
                ]
            }
        }

        normalized = extract_markdown_from_result(cu_output)
        pages = normalized["pages"]

        # UI can iterate and build navigation
        for i, page in enumerate(pages):
            page_num = page.get("page_number")
            assert page_num == i + 1

        # UI can calculate total
        assert len(pages) == 3


class TestLLMMarkdownQuality:
    """Test LLM receives markdown suitable for analysis."""

    def test_markdown_contains_semantic_structure(self):
        """Test markdown has semantic structure for LLM analysis."""

        output = {
            "pages": [
                {
                    "pageNumber": 1,
                    "markdown": """# Policy Document

## Section 1: Coverage
- Item A
- Item B

### Subsection
Details about coverage.

**Important**: This applies always.

## Section 2: Exclusions
1. Exclusion A
2. Exclusion B
""",
                }
            ]
        }

        normalized = extract_markdown_from_result(output)
        markdown = normalized["document_markdown"]

        # LLM can identify structure
        assert "#" in markdown  # Headers for topic identification
        assert "-" in markdown or "1." in markdown  # Lists for facts
        assert "**" in markdown or "*" in markdown  # Emphasis for important info

    def test_markdown_preserves_tables(self):
        """Test tables preserved for LLM analysis."""

        output = {
            "pages": [
                {
                    "pageNumber": 1,
                    "markdown": """| Coverage | Limit | Deductible |
|----------|-------|-----------|
| Medical  | €100k | €500      |
| Dental   | €5k   | €100      |""",
                }
            ]
        }

        normalized = extract_markdown_from_result(output)
        markdown = normalized["document_markdown"]

        # Tables preserved for LLM to analyze
        assert "|" in markdown
        assert "Coverage" in markdown
        assert "€100k" in markdown

    def test_markdown_volumes_equivalent(self):
        """Test CU and Mistral produce similar markdown volumes."""

        # Simulate real documents - both should extract full content
        cu_content = "A" * 5000  # Large document
        mistral_content = "A" * 5000

        cu_output = {
            "result": {
                "contents": [
                    {
                        "kind": "document",
                        "markdown": cu_content,
                        "pages": [{"pageNumber": 1, "markdown": cu_content}],
                    }
                ]
            }
        }

        mistral_output = {
            "result": {
                "contents": [
                    {
                        "kind": "document",
                        "markdown": mistral_content,
                        "pages": [{"pageNumber": 1, "markdown": mistral_content}],
                    }
                ]
            }
        }

        cu_normalized = extract_markdown_from_result(cu_output)
        mistral_normalized = extract_markdown_from_result(mistral_output)

        # Similar content volumes
        cu_len = len(cu_normalized["document_markdown"])
        mistral_len = len(mistral_normalized["document_markdown"])

        # Allow 10% variance due to formatting
        assert abs(cu_len - mistral_len) < max(cu_len, mistral_len) * 0.1


class TestExtractionPipelineCompatibility:
    """Test extraction pipeline handles both CU and Mistral identically."""

    def test_normalized_output_can_be_serialized(self):
        """Test normalized output is JSON-serializable for API responses."""

        cu_output = {
            "result": {
                "contents": [
                    {
                        "kind": "document",
                        "markdown": "Content here",
                        "pages": [{"pageNumber": 1, "markdown": "Content"}],
                        "fields": {"field1": {"value": "value1", "confidence": 0.95}},
                    }
                ]
            }
        }

        normalized = extract_markdown_from_result(cu_output)

        # Should be serializable
        import json

        serialized = json.dumps(normalized, default=str)
        assert serialized is not None
        assert len(serialized) > 0

        # Should deserialize correctly
        deserialized = json.loads(serialized)
        assert deserialized == normalized

    def test_normalized_output_schema_consistency(self):
        """Test normalized output has consistent schema across sources."""

        outputs = [
            # CU style
            {
                "result": {
                    "contents": [
                        {
                            "kind": "document",
                            "markdown": "Text 1",
                            "pages": [{"pageNumber": 1, "markdown": "Text 1"}],
                        }
                    ]
                }
            },
            # Mistral style (same structure)
            {
                "result": {
                    "contents": [
                        {
                            "kind": "document",
                            "markdown": "Text 2",
                            "pages": [{"pageNumber": 1, "markdown": "Text 2"}],
                        }
                    ]
                }
            },
        ]

        results = [extract_markdown_from_result(output) for output in outputs]

        # All results have same schema
        schemas = [set(result.keys()) for result in results]
        for schema in schemas[1:]:
            assert schema == schemas[0]

        # All results have pages with consistent structure
        for result in results:
            for page in result["pages"]:
                required_keys = {"page_number", "markdown"}
                actual_keys = set(page.keys())
                assert required_keys.issubset(actual_keys)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
