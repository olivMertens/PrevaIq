"""Regression coverage for incomplete, but valid, auto assessment metadata."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.claims.api import router


@pytest.mark.parametrize("optional_notes", [{}, {"liability_notes": None}])
def test_assessment_returns_absent_optional_values_as_null(optional_notes: dict) -> None:
    application = FastAPI()
    application.include_router(router)
    assessment = {
        "status": "pending_review",
        "overall_severity": "moderate",
        "liability": {
            "fault_determination": "pending",
            "fault_percentage": 0,
            "contributing_factors": [],
            **optional_notes,
        },
        "policy_citations": [{"policy_id": "AUTO-001", "citation_text": "Review required"}],
        "payout_recommendation": {"recommended_amount": 0},
        "created_at": "2026-01-29T14:05:00Z",
    }
    repository = AsyncMock()
    repository.get_claim_assessment.return_value = assessment
    with (
        patch("app.claims.api.load_settings"),
        patch("app.claims.api.ClaimsMediaRepository", return_value=repository),
    ):
        response = TestClient(application).get("/api/claims/demo-auto/assessment")
    assert response.status_code == 200
    result = response.json()
    assert result["liability"]["liability_notes"] is None
    assert result["payout_recommendation"]["min_amount"] is None
    assert result["payout_recommendation"]["max_amount"] is None
    assert result["policy_citations"][0]["section"] is None
    assert result["updated_at"] is None
    assert result["status"] == "pending_review"
