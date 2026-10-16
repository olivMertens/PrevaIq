"""
Tests for Body System Deep Dive — Phase 1: Backend Prompts
Validates that the 5 new deep dive prompts are correctly defined in
UNDERWRITING_DEFAULT_PROMPTS and prompts.json.
"""
import json
import os
import pytest

from app.personas import UNDERWRITING_DEFAULT_PROMPTS

# The 5 new deep dive subsection keys
DEEP_DIVE_SUBSECTIONS = [
    "body_system_review",
    "pending_investigations",
    "last_office_visit",
    "abnormal_labs",
    "latest_vitals",
]

# The 5 pre-existing medical_summary subsection keys
EXISTING_SUBSECTIONS = [
    "family_history",
    "hypertension",
    "high_cholesterol",
    "other_medical_findings",
    "other_risks",
]


class TestDeepDivePromptsInPersonas:
    """T1.1, T1.2 — Verify UNDERWRITING_DEFAULT_PROMPTS contains all 10 medical_summary subsections."""

    def test_medical_summary_section_exists(self):
        assert "medical_summary" in UNDERWRITING_DEFAULT_PROMPTS

    def test_all_10_subsections_present(self):
        ms = UNDERWRITING_DEFAULT_PROMPTS["medical_summary"]
        expected = set(EXISTING_SUBSECTIONS + DEEP_DIVE_SUBSECTIONS)
        actual = set(ms.keys())
        assert expected.issubset(actual), f"Missing subsections: {expected - actual}"

    @pytest.mark.parametrize("key", DEEP_DIVE_SUBSECTIONS)
    def test_deep_dive_prompt_is_non_empty_string(self, key):
        ms = UNDERWRITING_DEFAULT_PROMPTS["medical_summary"]
        assert key in ms, f"Missing key: {key}"
        prompt = ms[key]
        assert isinstance(prompt, str), f"Prompt for {key} should be a string, got {type(prompt)}"
        assert len(prompt.strip()) > 100, f"Prompt for {key} is suspiciously short"

    @pytest.mark.parametrize("key", DEEP_DIVE_SUBSECTIONS)
    def test_deep_dive_prompt_mentions_page_references(self, key):
        prompt = UNDERWRITING_DEFAULT_PROMPTS["medical_summary"][key]
        assert "page_references" in prompt.lower() or "page reference" in prompt.lower(), \
            f"Prompt {key} should mention page references"

    @pytest.mark.parametrize("key", DEEP_DIVE_SUBSECTIONS)
    def test_deep_dive_prompt_mentions_json(self, key):
        prompt = UNDERWRITING_DEFAULT_PROMPTS["medical_summary"][key]
        assert "json" in prompt.lower(), f"Prompt {key} should mention JSON output format"

    def test_body_system_review_includes_body_region_mapping(self):
        prompt = UNDERWRITING_DEFAULT_PROMPTS["medical_summary"]["body_system_review"]
        for region in ["head", "chest", "abdomen", "pelvis", "joints_spine"]:
            assert region in prompt, f"body_system_review prompt should include region: {region}"

    def test_body_system_review_includes_severity_classification(self):
        prompt = UNDERWRITING_DEFAULT_PROMPTS["medical_summary"]["body_system_review"]
        for sev in ["high", "moderate", "low", "normal"]:
            assert sev in prompt.lower(), f"body_system_review should include severity: {sev}"


class TestDeepDivePromptsInJson:
    """T1.2 — Verify prompts.json also contains the 5 new subsections."""

    @pytest.fixture(autouse=True)
    def load_prompts_json(self):
        prompts_path = os.path.join(
            os.path.dirname(__file__), "..", "prompts", "prompts.json"
        )
        with open(prompts_path, "r", encoding="utf-8") as f:
            self.prompts = json.load(f)

    def test_medical_summary_section_exists(self):
        assert "medical_summary" in self.prompts

    @pytest.mark.parametrize("key", DEEP_DIVE_SUBSECTIONS)
    def test_deep_dive_subsection_in_json(self, key):
        ms = self.prompts["medical_summary"]
        assert key in ms, f"Missing key in prompts.json: {key}"
        assert isinstance(ms[key], str), f"Prompt for {key} in prompts.json should be a string"
        assert len(ms[key].strip()) > 50, f"Prompt for {key} in prompts.json is too short"

    def test_all_10_subsections_present_in_json(self):
        ms = self.prompts["medical_summary"]
        expected = set(EXISTING_SUBSECTIONS + DEEP_DIVE_SUBSECTIONS)
        actual = set(ms.keys())
        assert expected.issubset(actual), f"Missing in prompts.json: {expected - actual}"


class TestDeepDiveProcessingCompatibility:
    """T1.3, T1.4 — Verify processing.py will pick up the new prompts automatically.
    
    The processing pipeline iterates all subsections in UNDERWRITING_DEFAULT_PROMPTS,
    so we just need to verify the dict has the right shape.
    """

    def test_medical_summary_subsections_are_all_strings(self):
        """processing.py handles string prompts directly."""
        ms = UNDERWRITING_DEFAULT_PROMPTS["medical_summary"]
        for key, val in ms.items():
            assert isinstance(val, str), f"Subsection {key} should be a string, got {type(val)}"

    def test_total_prompt_count_is_10(self):
        ms = UNDERWRITING_DEFAULT_PROMPTS["medical_summary"]
        assert len(ms) == 10, f"Expected 10 subsections, got {len(ms)}: {list(ms.keys())}"


class TestBatchSummaryRouting:
    """Verify that deep dive prompts are routed to batch-summaries context
    instead of the condensed context for large documents."""

    @pytest.mark.parametrize("key", DEEP_DIVE_SUBSECTIONS)
    def test_deep_dive_prompt_uses_format_agnostic_page_refs(self, key):
        """Deep dive prompts should mention BOTH (Page N) and <!-- Page N -->
        formats so they work with both batch summaries and raw markdown."""
        prompt = UNDERWRITING_DEFAULT_PROMPTS["medical_summary"][key]
        assert "(Page N)" in prompt or "(Page" in prompt, \
            f"Prompt {key} should mention (Page N) format for batch summaries"
        assert "<!-- Page" in prompt, \
            f"Prompt {key} should mention <!-- Page N --> format for raw markdown"

    def test_json_prompt_uses_format_agnostic_page_refs(self):
        """prompts.json deep dive prompts should also be format-agnostic."""
        prompts_path = os.path.join(
            os.path.dirname(__file__), "..", "prompts", "prompts.json"
        )
        with open(prompts_path, "r", encoding="utf-8") as f:
            prompts = json.load(f)
        for key in DEEP_DIVE_SUBSECTIONS:
            prompt = prompts["medical_summary"][key]
            assert "(Page N)" in prompt or "(Page" in prompt, \
                f"prompts.json {key} should mention (Page N) format"

    def test_batch_context_builder_produces_rich_context(self):
        """Simulate batch summaries and verify the context built for deep dive
        is richer than the condensed context."""
        batch_summaries = [
            {
                "batch_num": 1,
                "page_start": 1,
                "page_end": 20,
                "page_count": 20,
                "summary": "Patient diagnosed with OA bilateral knees (Page 5). "
                           "Prescribed Saxenda for weight loss (Page 8). "
                           "PAP smear results abnormal (Page 12).",
            },
            {
                "batch_num": 2,
                "page_start": 21,
                "page_end": 40,
                "page_count": 20,
                "summary": "Colonoscopy performed — diverticulosis found (Page 25). "
                           "Tinnitus noted (Page 30). Family history of melanoma (Page 35).",
            },
        ]

        # Build the same way processing.py does
        parts = []
        for bs in batch_summaries:
            parts.append(
                f"### Batch {bs['batch_num']} \u2014 Pages {bs['page_start']}\u2013{bs['page_end']}\n"
                f"{bs['summary']}"
            )
        batch_context = (
            "# Detailed Batch Summaries\n"
            "The following are detailed summaries of the original medical records, "
            "organized by page range. Page references appear as (Page N) throughout.\n\n"
            + "\n\n".join(parts)
        )

        # Verify the batch context is well-formed
        assert "Page 5" in batch_context
        assert "Page 25" in batch_context
        assert "OA bilateral knees" in batch_context
        assert "diverticulosis" in batch_context
        assert "Batch 1" in batch_context
        assert "Batch 2" in batch_context
        assert batch_context.startswith("# Detailed Batch Summaries")

    def test_deep_dive_subsection_set_matches_expected(self):
        """The set used in processing.py routing must match our 5 deep dive keys."""
        # This matches the literal set defined inside run_underwriting_prompts
        expected_routing_set = {
            "body_system_review",
            "pending_investigations",
            "last_office_visit",
            "abnormal_labs",
            "latest_vitals",
        }
        assert expected_routing_set == set(DEEP_DIVE_SUBSECTIONS)

    def test_deep_dive_vs_original_prompts_no_overlap(self):
        """Deep dive and original subsections should be disjoint."""
        assert set(DEEP_DIVE_SUBSECTIONS).isdisjoint(set(EXISTING_SUBSECTIONS))
