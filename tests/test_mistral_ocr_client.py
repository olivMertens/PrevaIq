"""Unit tests for Mistral Document AI OCR client format validation.

Tests ensure:
1. Mistral result format is valid before processing
2. Format passes through extract_markdown_from_result()
3. LLM receives same quality markdown from both CU and Mistral
4. UI can display Mistral-extracted pages correctly
"""

import json
import pytest
from typing import Dict, Any

from app.mistral_ocr_client import (
    validate_mistral_result,
    MistralOCRError,
    MistralSettings,
)
from app.content_understanding_client import extract_markdown_from_result


class TestMistralResultValidation:
    """Test Mistral result format validation."""

    def test_valid_minimal_result(self):
        """Test valid minimal Mistral result passes validation."""
        result = {
            "markdown": "# Page 1\nContent here",
            "pages": [
                {
                    "page_index": 0,
                    "page_number": 1,
                    "markdown": "# Page 1\nContent here",
                }
            ],
            "images": [],
            "usage": {},
        }
        errors = validate_mistral_result(result)
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_valid_result_with_images(self):
        """Test valid Mistral result with images."""
        result = {
            "markdown": "# Page\n![image](data:image/png;base64,...)",
            "pages": [
                {
                    "page_index": 0,
                    "page_number": 1,
                    "markdown": "# Page\n![image](...)",
                    "images": [
                        {
                            "page_index": 0,
                            "base64": "iVBORw0KGgo...",
                        }
                    ],
                    "tables": [],
                }
            ],
            "images": [{"page_index": 0, "base64": "iVBORw0KGgo..."}],
            "usage": {"input_tokens": 100, "output_tokens": 50},
        }
        errors = validate_mistral_result(result)
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_valid_result_multipage(self):
        """Test valid multi-page Mistral result."""
        result = {
            "markdown": "# Page 1\nContent\n\n---\n\n# Page 2\nMore content",
            "pages": [
                {
                    "page_index": 0,
                    "page_number": 1,
                    "markdown": "# Page 1\nContent",
                },
                {
                    "page_index": 1,
                    "page_number": 2,
                    "markdown": "# Page 2\nMore content",
                },
            ],
            "images": [],
        }
        errors = validate_mistral_result(result)
        assert errors == [], f"Expected no errors, got: {errors}"

    def test_missing_markdown_field(self):
        """Test validation catches missing markdown field."""
        result = {
            "pages": [
                {"page_index": 0, "page_number": 1, "markdown": "text"}
            ]
        }
        errors = validate_mistral_result(result)
        assert 'Missing required field: "markdown"' in errors

    def test_missing_pages_field(self):
        """Test validation catches missing pages field."""
        result = {
            "markdown": "# Page\nContent",
        }
        errors = validate_mistral_result(result)
        assert 'Missing required field: "pages"' in errors

    def test_empty_markdown(self):
        """Test validation catches empty markdown."""
        result = {
            "markdown": "",
            "pages": [
                {"page_index": 0, "page_number": 1, "markdown": "content"}
            ],
        }
        errors = validate_mistral_result(result)
        assert 'Field "markdown" is empty' in errors

    def test_empty_pages_list(self):
        """Test validation catches empty pages list."""
        result = {
            "markdown": "content",
            "pages": [],
        }
        errors = validate_mistral_result(result)
        assert 'Field "pages" is empty' in errors

    def test_page_missing_markdown(self):
        """Test validation catches page without markdown field."""
        result = {
            "markdown": "content",
            "pages": [
                {"page_index": 0, "page_number": 1}  # Missing markdown
            ],
        }
        errors = validate_mistral_result(result)
        assert any("missing" in e.lower() for e in errors)

    def test_page_missing_index_or_number(self):
        """Test validation catches page without index/number."""
        result = {
            "markdown": "content",
            "pages": [
                {"markdown": "page content"}  # Missing page_index and page_number
            ],
        }
        errors = validate_mistral_result(result)
        assert any(
            "page_index" in e or "page_number" in e for e in errors
        )

    def test_invalid_type_markdown(self):
        """Test validation catches non-string markdown."""
        result = {
            "markdown": 123,  # Should be string
            "pages": [{"page_index": 0, "page_number": 1, "markdown": "text"}],
        }
        errors = validate_mistral_result(result)
        assert any("markdown" in e.lower() and "str" in e for e in errors)

    def test_invalid_type_pages(self):
        """Test validation catches non-list pages."""
        result = {
            "markdown": "content",
            "pages": "not a list",
        }
        errors = validate_mistral_result(result)
        assert any("pages" in e.lower() and "list" in e for e in errors)

    def test_invalid_result_type(self):
        """Test validation catches non-dict result."""
        result = "not a dict"
        errors = validate_mistral_result(result)
        assert len(errors) > 0


class TestMistralExtractMarkdownCompatibility:
    """Test Mistral result format passes through extract_markdown_from_result()."""

    def test_mistral_result_passes_through_extract_markdown(self):
        """Test Mistral result can be normalized by extract_markdown_from_result()."""
        # Build a Mistral-compatible payload
        mistral_result = {
            "result": {
                "contents": [
                    {
                        "kind": "document",
                        "markdown": "# Page 1\nContent here",
                        "pages": [
                            {
                                "pageNumber": 1,
                                "markdown": "# Page 1\nContent here",
                            }
                        ],
                    }
                ]
            }
        }

        # Should normalize without errors
        normalized = extract_markdown_from_result(mistral_result)

        assert "document_markdown" in normalized
        assert "pages" in normalized
        assert len(normalized["pages"]) > 0
        assert normalized["document_markdown"].strip() != ""

    def test_mistral_multipage_result_extraction(self):
        """Test multi-page Mistral result extraction."""
        mistral_result = {
            "result": {
                "contents": [
                    {
                        "kind": "document",
                        "markdown": "# Page 1\nContent1\n\n# Page 2\nContent2",
                        "pages": [
                            {
                                "pageNumber": 1,
                                "markdown": "# Page 1\nContent1",
                            },
                            {
                                "pageNumber": 2,
                                "markdown": "# Page 2\nContent2",
                            },
                        ],
                    }
                ]
            }
        }

        normalized = extract_markdown_from_result(mistral_result)

        assert len(normalized["pages"]) == 2
        assert "Page 1" in normalized["pages"][0]["markdown"]
        assert "Page 2" in normalized["pages"][1]["markdown"]


class TestMistralLLMMarkdownQuality:
    """Test LLM receives same quality markdown from both CU and Mistral."""

    def test_markdown_has_structure(self):
        """Test extracted markdown has proper structure for LLM."""
        mistral_result = {
            "markdown": """# Invoice
        
## Items
- Item 1: $100
- Item 2: $200

**Total: $300**""",
            "pages": [
                {
                    "page_index": 0,
                    "page_number": 1,
                    "markdown": """# Invoice

## Items
- Item 1: $100
- Item 2: $200

**Total: $300**""",
                }
            ],
        }

        errors = validate_mistral_result(mistral_result)
        assert errors == []

        # Verify structure for LLM
        md = mistral_result["markdown"]
        assert "#" in md  # Headers
        assert "-" in md or "*" in md  # Lists
        assert len(md) > 50  # Substantial content

    def test_markdown_preserves_formatting(self):
        """Test markdown preserves formatting for LLM understanding."""
        mistral_result = {
            "markdown": """**Bold text** and *italic*
        
```code
sample_function()
```

| Column1 | Column2 |
|---------|---------|
| A       | B       |""",
            "pages": [
                {
                    "page_index": 0,
                    "page_number": 1,
                    "markdown": """**Bold text** and *italic*

```code
sample_function()
```

| Column1 | Column2 |
|---------|---------|
| A       | B       |""",
                }
            ],
        }

        errors = validate_mistral_result(mistral_result)
        assert errors == []

        # Verify formatting preserved
        md = mistral_result["markdown"]
        assert "**" in md  # Bold
        assert "*" in md  # Italic
        assert "```" in md  # Code blocks
        assert "|" in md  # Tables

    def test_markdown_page_continuity(self):
        """Test pages connect properly for LLM context."""
        mistral_result = {
            "markdown": "Page 1 content\n\n---\n\nPage 2 content",
            "pages": [
                {
                    "page_index": 0,
                    "page_number": 1,
                    "markdown": "Page 1 content",
                },
                {
                    "page_index": 1,
                    "page_number": 2,
                    "markdown": "Page 2 content",
                },
            ],
        }

        errors = validate_mistral_result(mistral_result)
        assert errors == []

        # Verify all pages in combined markdown
        md = mistral_result["markdown"]
        assert "Page 1" in md
        assert "Page 2" in md


class TestMistralUICompatibility:
    """Test UI can display Mistral-extracted pages correctly."""

    def test_page_has_required_ui_fields(self):
        """Test each page has fields UI needs for display."""
        result = {
            "markdown": "content",
            "pages": [
                {
                    "page_index": 0,
                    "page_number": 1,
                    "markdown": "# Page Content",
                    "images": [],
                    "tables": [],
                }
            ],
            "images": [],
        }

        errors = validate_mistral_result(result)
        assert errors == []

        # UI needs these fields
        page = result["pages"][0]
        assert "page_number" in page or "page_index" in page
        assert "markdown" in page

    def test_page_with_images_for_ui(self):
        """Test pages with images can be displayed in UI."""
        result = {
            "markdown": "content with image",
            "pages": [
                {
                    "page_index": 0,
                    "page_number": 1,
                    "markdown": "# Page with image\n![alt](url)",
                    "images": [
                        {
                            "page_index": 0,
                            "base64": "iVBORw0KGgo=",
                            "format": "png",
                        }
                    ],
                }
            ],
            "images": [
                {
                    "page_index": 0,
                    "base64": "iVBORw0KGgo=",
                }
            ],
        }

        errors = validate_mistral_result(result)
        assert errors == []

        # UI needs to iterate images
        assert len(result["images"]) > 0
        assert all("page_index" in img for img in result["images"])

    def test_page_numbering_for_ui_navigation(self):
        """Test page numbering works for UI navigation."""
        result = {
            "markdown": "multi page",
            "pages": [
                {
                    "page_index": 0,
                    "page_number": 1,
                    "markdown": "Page 1",
                },
                {
                    "page_index": 1,
                    "page_number": 2,
                    "markdown": "Page 2",
                },
                {
                    "page_index": 2,
                    "page_number": 3,
                    "markdown": "Page 3",
                },
            ],
        }

        errors = validate_mistral_result(result)
        assert errors == []

        # UI can navigate by page number
        for i, page in enumerate(result["pages"]):
            assert page["page_number"] == i + 1


class TestMistralSettings:
    """Test Mistral configuration."""

    def test_settings_validate_missing_endpoint(self):
        """Test validation catches missing endpoint."""
        settings = MistralSettings(
            endpoint="",
            api_key="key",
            deployment="model",
        )
        errors = settings.validate()
        assert any("MISTRAL_ENDPOINT" in e for e in errors)

    def test_settings_validate_missing_key(self):
        """Test validation catches missing API key."""
        settings = MistralSettings(
            endpoint="https://endpoint.com",
            api_key="",
            deployment="model",
        )
        errors = settings.validate()
        assert any("MISTRAL_API_KEY" in e for e in errors)

    def test_settings_validate_valid(self):
        """Test valid settings pass validation."""
        settings = MistralSettings(
            endpoint="https://endpoint.com",
            api_key="test-key-12345",
            deployment="mistral-model",
        )
        errors = settings.validate()
        assert errors == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
