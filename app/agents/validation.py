"""Validation Agent — compares human decisions against AI recommendations.

Detects divergences, requests justification for high-risk overrides,
and escalates to manager when the pattern is unusual.
"""
from __future__ import annotations

from typing import Any

from ..utils import setup_logging

logger = setup_logging()

# Decision distance matrix — higher = bigger divergence
_DECISION_ORDER = ["approve", "approve_with_conditions", "defer", "decline"]


def _divergence_level(ai: str | None, human: str) -> str:
    """Return 'aligned', 'moderate', or 'high' based on decision distance."""
    if not ai or ai == human:
        return "aligned"
    try:
        dist = abs(_DECISION_ORDER.index(ai) - _DECISION_ORDER.index(human))
    except ValueError:
        return "moderate"
    if dist <= 1:
        return "moderate"
    return "high"


async def validate_decision(
    application_id: str,
    persona: str,
    human_decision: str,
    ai_recommendation: str | None,
    risk_level: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Validate a human decision against the AI recommendation.

    Persists the result in workbenchiq.decision_validations and returns
    a summary dict with divergence analysis.
    """
    div = _divergence_level(ai_recommendation, human_decision)

    justification = None
    escalated = False
    escalation_reason = None

    if div == "high":
        escalated = True
        escalation_reason = (
            f"High divergence: AI recommended '{ai_recommendation}' "
            f"but human decided '{human_decision}' on a {risk_level or 'unknown'}-risk application."
        )
        if not notes:
            justification = "No justification provided — escalation required."
        else:
            justification = notes

    elif div == "moderate":
        justification = notes or "Moderate divergence — no additional justification provided."

    # Persist to PostgreSQL
    persisted = False
    try:
        from ..database.pool import get_pool

        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO workbenchiq.decision_validations
                    (application_id, persona, ai_recommendation, human_decision,
                     divergence_level, risk_level, justification, escalated, escalation_reason)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                application_id,
                persona,
                ai_recommendation,
                human_decision,
                div,
                risk_level,
                justification,
                escalated,
                escalation_reason,
            )
            persisted = True
    except Exception as e:
        logger.warning("Could not persist decision validation for %s: %s", application_id, e)

    result = {
        "application_id": application_id,
        "ai_recommendation": ai_recommendation,
        "human_decision": human_decision,
        "divergence_level": div,
        "escalated": escalated,
        "escalation_reason": escalation_reason,
        "justification": justification,
        "persisted": persisted,
    }
    logger.info(
        "Decision validation for %s: %s (div=%s, escalated=%s)",
        application_id,
        human_decision,
        div,
        escalated,
    )
    return result


async def get_divergence_stats(persona: str | None = None) -> dict[str, Any]:
    """Return aggregated divergence statistics for the dashboard."""
    try:
        from ..database.pool import get_pool

        pool = await get_pool()
        async with pool.acquire() as conn:
            where = "WHERE persona = $1" if persona else ""
            params = [persona] if persona else []

            rows = await conn.fetch(
                f"""
                SELECT divergence_level, COUNT(*) as cnt,
                       COUNT(*) FILTER (WHERE escalated) as escalated_cnt
                FROM workbenchiq.decision_validations
                {where}
                GROUP BY divergence_level
                """,
                *params,
            )

            total = sum(r["cnt"] for r in rows)
            stats = {
                r["divergence_level"]: {
                    "count": r["cnt"],
                    "escalated": r["escalated_cnt"],
                }
                for r in rows
            }
            alignment_rate = (
                stats.get("aligned", {}).get("count", 0) / total * 100
                if total > 0
                else 0
            )
            return {
                "total_decisions": total,
                "alignment_rate": round(alignment_rate, 1),
                "by_level": stats,
            }
    except Exception as e:
        logger.warning("Could not fetch divergence stats: %s", e)
        return {"total_decisions": 0, "alignment_rate": 0, "by_level": {}}
