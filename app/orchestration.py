"""Controlled document orchestration: explicit stage budgets and human-review gating.

Pipeline: extraction -> validation -> at most one targeted re-extraction per file ->
analysis -> human review. No open-ended agentic loop: every retry is bounded by the
stage budget (wall-clock seconds, tokens, re-extraction count).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Dict, Iterable, List, Optional

from .config import ProcessingSettings

REVIEW_NEEDED = "needs_review"
REVIEW_AUTO_OK = "auto_ok"
REVIEW_DONE = "reviewed"

_LLM_FALLBACK_BACKENDS = {"llm-markdown-fallback"}


@dataclass
class StageBudget:
    stage: str
    max_seconds: float
    max_tokens: int = 0  # 0 = no token cap
    max_reextractions: int = 0
    started: float = field(default_factory=time.monotonic)
    tokens_used: int = 0
    reextractions: int = 0
    skipped: List[str] = field(default_factory=list)

    @classmethod
    def for_extraction(cls, cfg: ProcessingSettings) -> "StageBudget":
        return cls(
            stage="extraction",
            max_seconds=cfg.extraction_budget_seconds,
            max_reextractions=cfg.max_reextractions,
        )

    @classmethod
    def for_analysis(cls, cfg: ProcessingSettings) -> "StageBudget":
        return cls(
            stage="analysis",
            max_seconds=cfg.analysis_budget_seconds,
            max_tokens=cfg.analysis_token_budget,
        )

    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def charge(self, usage: Optional[Dict[str, Any]]) -> None:
        if not usage:
            return
        total = usage.get("total_tokens")
        if total is None:
            total = (usage.get("prompt_tokens") or 0) + (usage.get("completion_tokens") or 0)
        self.tokens_used += int(total or 0)

    def time_exhausted(self) -> bool:
        return self.max_seconds > 0 and self.elapsed() >= self.max_seconds

    def tokens_exhausted(self) -> bool:
        return self.max_tokens > 0 and self.tokens_used >= self.max_tokens

    def exhausted(self) -> bool:
        return self.time_exhausted() or self.tokens_exhausted()

    def can_reextract(self) -> bool:
        return self.reextractions < self.max_reextractions and not self.time_exhausted()

    def to_trace(self, reasons: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "elapsed_seconds": round(self.elapsed(), 2),
            "max_seconds": self.max_seconds,
            "tokens_used": self.tokens_used,
            "max_tokens": self.max_tokens,
            "reextractions": self.reextractions,
            "max_reextractions": self.max_reextractions,
            "skipped": list(self.skipped),
            "budget_exhausted": self.exhausted(),
            "review_reasons": reasons,
            "completed_at": datetime.now(UTC).isoformat(),
        }


def _reason(code: str, detail: Any = None) -> Dict[str, Any]:
    return {"code": code, "detail": detail} if detail is not None else {"code": code}


def assess_extraction(
    *,
    budget: StageBudget,
    file_provenance: Iterable[Dict[str, Any]],
    confidence_summary: Optional[Dict[str, Any]],
    has_content: bool,
    composite_review_required: bool,
    cfg: ProcessingSettings,
) -> List[Dict[str, Any]]:
    """Validation step: return the reasons a human must review the extraction."""
    reasons: List[Dict[str, Any]] = []
    if not has_content:
        reasons.append(_reason("no_content"))

    low_quality = sorted(
        {
            item["file"]
            for item in file_provenance
            if item.get("file")
            and item.get("media_type", "document") == "document"
            and item.get("extraction_backend") not in _LLM_FALLBACK_BACKENDS
            and isinstance(item.get("quality_score"), (int, float))
            and item["quality_score"] < cfg.reextraction_quality_threshold
        }
    )
    if low_quality:
        reasons.append(_reason("low_extraction_quality", low_quality))

    if any(item.get("extraction_backend") in _LLM_FALLBACK_BACKENDS for item in file_provenance):
        reasons.append(_reason("unverified_llm_fields"))

    average = (confidence_summary or {}).get("average_confidence")
    if isinstance(average, (int, float)) and 0 < average < cfg.review_confidence_threshold:
        reasons.append(_reason("low_confidence", round(average, 2)))

    if composite_review_required:
        reasons.append(_reason("composite_conflict"))
    if budget.skipped or budget.time_exhausted():
        reasons.append(_reason("extraction_budget_exhausted", list(budget.skipped) or None))
    return reasons


def assess_analysis(
    *, budget: StageBudget, results: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Validation step for LLM analysis outputs."""
    reasons: List[Dict[str, Any]] = []
    failed = sorted(
        f"{section}.{sub}"
        for section, subs in results.items()
        if isinstance(subs, dict)
        for sub, out in subs.items()
        if isinstance(out, dict)
        and isinstance(out.get("parsed"), dict)
        and "_error" in out["parsed"]
    )
    if failed:
        reasons.append(_reason("analysis_errors", failed))
    if budget.skipped or budget.exhausted():
        reasons.append(_reason("analysis_budget_exhausted", list(budget.skipped) or None))
    return reasons


def record_stage(app_md: Any, budget: StageBudget, reasons: List[Dict[str, Any]]) -> None:
    """Persist the stage trace and recompute the dossier review status."""
    orchestration = dict(app_md.orchestration or {})
    stages = dict(orchestration.get("stages") or {})
    stages[budget.stage] = budget.to_trace(reasons)
    all_reasons = [r for trace in stages.values() for r in trace.get("review_reasons", [])]
    orchestration["stages"] = stages
    orchestration["review"] = {
        "status": REVIEW_NEEDED if all_reasons else REVIEW_AUTO_OK,
        "reasons": all_reasons,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    app_md.orchestration = orchestration


def mark_reviewed(app_md: Any, *, decision: str, decided_at: str) -> None:
    orchestration = dict(app_md.orchestration or {})
    review = dict(orchestration.get("review") or {})
    review.update({"status": REVIEW_DONE, "decision": decision, "updated_at": decided_at})
    orchestration["review"] = review
    app_md.orchestration = orchestration
