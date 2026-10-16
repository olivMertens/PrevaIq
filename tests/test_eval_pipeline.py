from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

_spec = importlib.util.spec_from_file_location(
    "eval_pipeline", Path(__file__).resolve().parents[1] / "scripts" / "eval_pipeline.py"
)
eval_pipeline = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(eval_pipeline)


def test_score_case_measures_quality_completeness_citations():
    case = {
        "expected_values": ["SIN-2026-HAB-04837", "1 556,50", "Durand Plomberie"],
        "expected_citations": ["franchise", "Article 12"],
    }
    app_md = SimpleNamespace(
        document_markdown="Réf SIN-2026-HAB-04837 — Total TTC : 1\u00a0556,50 € — DURAND PLOMBERIE",
        extracted_fields={"a": {"value": "SIN-2026-HAB-04837"}},
        llm_outputs={"s": {"x": {"parsed": {"text": "La franchise de 250 € s'applique"}}}},
        orchestration={
            "review": {"status": "needs_review", "reasons": [{"code": "low_confidence"}]}
        },
    )
    score = eval_pipeline.score_case(case, app_md)
    assert score["quality"] == 1.0
    assert score["completeness"] == 0.333
    assert score["citations"] == 0.5
    assert score["review_reasons"] == ["low_confidence"]


def test_cost_requires_configured_price():
    usage = {"prompt_tokens": 1_000_000, "completion_tokens": 500_000}
    prices = {"models": {"m": {"input_per_1m": 1.0, "output_per_1m": 4.0}, "z": {}}}
    assert eval_pipeline._cost(usage, "m", prices) == 3.0
    assert eval_pipeline._cost(usage, "z", prices) is None


def test_summary_reports_deltas_against_baseline():
    results = {
        "baseline": [{"quality": 0.8, "tokens": 1000}],
        "candidate": [{"quality": 0.9, "tokens": 1200}],
    }
    summary = eval_pipeline.summarize(results)
    assert "| candidate | 0.9 (+0.1)" in summary
    assert "1200 (+200)" in summary
