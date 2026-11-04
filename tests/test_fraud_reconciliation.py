"""Regression tests for deterministic fraud-assessment reconciliation.

The vision/assessment calls sometimes emit contradictory output — an image
scoring 0.24 still flagged ``is_likely_authentic: true`` (a red dot next to an
"Authentique" verdict), or an overall ``risk_score`` of 0 / LOW despite suspect images
and an inconsistent declaration. ``_reconcile_fraud_assessment`` makes the verdict, the
overall score and the band coherent before they reach the workbench UI.
"""

from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from app import openai_client
from app.agents.tools import (
    _assess_overall_fraud,
    _cross_check_declaration,
    _fraud_risk_band,
    _reconcile_fraud_assessment,
    _safe_float,
)


def _sample() -> dict:
    """Mirrors the incoherent production shape observed on dossier cc7d0d2a."""
    return {
        "application_id": "cc7d0d2a",
        "image_analyses": [
            {"filename": "img_132644.jpg", "authenticity_score": 0.93, "is_likely_authentic": True,
             "manipulation_indicators": []},
            # Contradiction: low score but model still says authentic.
            {"filename": "img_132943.jpg", "authenticity_score": 0.24, "is_likely_authentic": True,
             "manipulation_indicators": [{"type": "lighting_inconsistency", "severity": "medium"},
                                         {"type": "copy_paste", "severity": "high"}]},
            {"filename": "img_133219.jpg", "authenticity_score": 0.78, "is_likely_authentic": True,
             "manipulation_indicators": [{"type": "environmental_anomaly", "severity": "low"}]},
            {"filename": "img_132612.jpg", "authenticity_score": 0.34, "is_likely_authentic": False,
             "manipulation_indicators": [{"type": "suspicious_damage", "severity": "high"}]},
            {"filename": "bouteilles.jpg", "authenticity_score": 0.23, "is_likely_authentic": False,
             "manipulation_indicators": [{"type": "ai_generated", "severity": "high"}]},
        ],
        "declaration_verification": {
            "overall_consistent": False,
            "consistency_score": 0.7,
            "discrepancies": ["Objets incohérents avec un sinistre habitation"],
        },
        "overall_assessment": {
            "overall_fraud_risk": "LOW",
            "risk_score": 0.0,
            "siu_referral_recommended": False,
            "attention_items": [],
            "summary": "",
        },
    }


def test_safe_float_tolerates_bad_values() -> None:
    assert _safe_float(0.42) == 0.42
    assert _safe_float("0,42") == 0.42
    assert _safe_float("85%") == 85.0
    assert _safe_float(None, 1.0) == 1.0
    assert _safe_float("oops", 0.5) == 0.5


def test_fraud_risk_band_thresholds() -> None:
    assert _fraud_risk_band(0.0) == "LOW"
    assert _fraud_risk_band(0.34) == "LOW"
    assert _fraud_risk_band(0.35) == "MODERATE"
    assert _fraud_risk_band(0.69) == "MODERATE"
    assert _fraud_risk_band(0.70) == "HIGH"


def test_low_score_image_is_downgraded_to_suspect() -> None:
    """The core bug: authenticity_score 0.24 must not stay 'Authentique'."""
    result = _reconcile_fraud_assessment(_sample())
    by_name = {img["filename"]: img for img in result["image_analyses"]}

    assert by_name["img_132943.jpg"]["is_likely_authentic"] is False  # 0.24 → suspect
    assert by_name["img_132644.jpg"]["is_likely_authentic"] is True   # 0.93 stays authentic
    assert by_name["img_133219.jpg"]["is_likely_authentic"] is True   # 0.78 ≥ floor


def test_overall_score_floor_lifts_above_zero() -> None:
    """risk_score must not stay 0% when suspect images + inconsistent declaration exist."""
    result = _reconcile_fraud_assessment(_sample())
    overall = result["overall_assessment"]

    assert overall["risk_score"] > 0.3
    assert overall["overall_fraud_risk"] in ("MODERATE", "HIGH")
    assert overall["siu_referral_recommended"] is True
    assert overall["siu_referral_reason"]
    assert len(overall["attention_items"]) >= 1
    # The 0.24 suspect image must surface as a high-priority attention item.
    labels = " ".join(i["label"] for i in overall["attention_items"])
    assert "img_132943.jpg" in labels


def test_content_mismatch_downgrades_even_high_score() -> None:
    data = {
        "image_analyses": [
            {"filename": "facade_maison.jpg", "authenticity_score": 0.95,
             "is_likely_authentic": True,
             "filename_concordance": {"filename_is_descriptive": True, "matches_content": False,
                                      "expected_content": "façade", "actual_content": "intérieur"}},
        ],
        "overall_assessment": {"overall_fraud_risk": "LOW", "risk_score": 0.0},
    }
    result = _reconcile_fraud_assessment(data)
    assert result["image_analyses"][0]["is_likely_authentic"] is False


def test_model_higher_score_is_preserved() -> None:
    """Raise-only floor: a model score already above the computed floor is kept."""
    data = _sample()
    data["overall_assessment"]["risk_score"] = 0.92
    data["overall_assessment"]["overall_fraud_risk"] = "HIGH"
    result = _reconcile_fraud_assessment(data)
    assert result["overall_assessment"]["risk_score"] == 0.92
    assert result["overall_assessment"]["overall_fraud_risk"] == "HIGH"


def test_reconciliation_is_idempotent() -> None:
    once = _reconcile_fraud_assessment(_sample())
    twice = _reconcile_fraud_assessment(copy.deepcopy(once))
    assert once == twice


def test_synthesised_items_follow_the_requested_language() -> None:
    german = _reconcile_fraud_assessment(_sample(), "de")["overall_assessment"]
    german_labels = [item["label"] for item in german["attention_items"]]
    assert "Verdächtiges Bild: img_132943.jpg" in german_labels
    assert "Widersprüchliche Schadenmeldung" in german_labels
    assert german["siu_referral_reason"] == (
        "3 verdächtige(s) Bild(er) und widersprüchliche Schadenmeldung — SIU-Prüfung empfohlen."
    )

    english = _reconcile_fraud_assessment(_sample())["overall_assessment"]
    assert "Suspicious image: img_132943.jpg" in [i["label"] for i in english["attention_items"]]
    serialized = json.dumps(english, ensure_ascii=False)
    assert "suspecte" not in serialized and "incohérente" not in serialized


@pytest.mark.parametrize(
    ("effort", "budget"),
    [("low", 6000), ("medium", 10000), ("high", 16000), ("unexpected", 10000)],
)
def test_reasoning_calls_leave_room_for_the_json_answer(monkeypatch, effort, budget) -> None:
    """A 4k budget let hidden reasoning consume everything (finish_reason=length, empty
    merge): the cross-check and merge budgets scale with the selected reasoning effort."""
    budgets = []

    def fake_chat_completion(_settings, _messages, **kwargs):
        budgets.append(kwargs["max_tokens"])
        return {"content": '{"summary": "ok"}'}

    monkeypatch.setattr(openai_client, "chat_completion", fake_chat_completion)
    settings = SimpleNamespace(openai=SimpleNamespace())
    fraud_settings = SimpleNamespace(deployment_name="fraud", model_name="fraud-model")

    merged = _assess_overall_fraud(settings, fraud_settings, {}, [], {}, reasoning_effort=effort)
    checked = _cross_check_declaration(
        settings, fraud_settings, {}, [], "Tempête", "sinistre", reasoning_effort=effort
    )

    assert merged == checked == {"summary": "ok"}
    assert budgets == [budget, budget]


def test_passthrough_for_non_dict() -> None:
    assert _reconcile_fraud_assessment("L'analyse anti-fraude est désactivée.") == (
        "L'analyse anti-fraude est désactivée."
    )
    assert _reconcile_fraud_assessment(None) is None


def test_clean_dossier_stays_low() -> None:
    """A genuinely clean dossier must not be inflated to a false positive."""
    data = {
        "image_analyses": [
            {"filename": "a.jpg", "authenticity_score": 0.95, "is_likely_authentic": True},
            {"filename": "b.jpg", "authenticity_score": 0.9, "is_likely_authentic": True},
        ],
        "declaration_verification": {"overall_consistent": True, "consistency_score": 0.95},
        "overall_assessment": {"overall_fraud_risk": "LOW", "risk_score": 0.05,
                               "attention_items": []},
    }
    result = _reconcile_fraud_assessment(data)
    overall = result["overall_assessment"]
    assert overall["overall_fraud_risk"] == "LOW"
    assert overall["risk_score"] < 0.35
    assert not overall.get("siu_referral_recommended")
