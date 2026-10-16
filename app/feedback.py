"""Feedback repository — PostgreSQL storage for feedback events and few-shot examples."""
from __future__ import annotations

from typing import Any, Optional
from app.database.pool import get_pool
from app.utils import setup_logging

logger = setup_logging()

SCHEMA = "workbenchiq"


async def insert_feedback_event(
    *,
    agent_type: str,
    feedback_type: str,
    original_query: str | None = None,
    agent_response: str | None = None,
    correction: str | None = None,
    persona: str | None = None,
    session_id: str | None = None,
    conversation_id: str | None = None,
    application_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str | None:
    """Insert a feedback event and return its UUID.

    routing_target is computed by the BEFORE INSERT trigger.
    """
    import json

    try:
        pool = await get_pool()
    except RuntimeError:
        logger.warning("Database pool not initialized — skipping feedback insert")
        return None

    sql = f"""
        INSERT INTO {SCHEMA}.feedback_events
            (session_id, conversation_id, application_id,
             agent_type, feedback_type,
             original_query, agent_response, correction,
             persona, metadata)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb)
        RETURNING feedback_id::text
    """
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                sql,
                session_id,
                conversation_id,
                application_id,
                agent_type,
                feedback_type,
                original_query,
                agent_response,
                correction,
                persona,
                json.dumps(metadata or {}),
            )
            feedback_id = row["feedback_id"] if row else None
            logger.info("Feedback stored: %s type=%s agent=%s", feedback_id, feedback_type, agent_type)
            return feedback_id
    except Exception:
        logger.exception("Failed to insert feedback event")
        return None


async def has_eligible_few_shots(persona: str, agent_type: str) -> bool:
    try:
        pool = await get_pool()
    except RuntimeError:
        return False

    try:
        async with pool.acquire() as conn:
            return bool(await conn.fetchval(
                f"""SELECT EXISTS (
                    SELECT 1 FROM {SCHEMA}.few_shot_store
                    WHERE persona = $1 AND agent_type = $2
                      AND active = true AND embedding IS NOT NULL
                )""",
                persona,
                agent_type,
            ))
    except Exception:
        logger.debug("Few-shot eligibility unavailable", exc_info=True)
        return False


async def get_relevant_few_shots(
    query: str,
    persona: str,
    agent_type: str,
    top_k: int = 3,
    similarity_threshold: float = 0.80,
    embedding: list[float] | None = None,
) -> list[dict[str, Any]]:
    """Retrieve the most relevant few-shot corrections for a given query.

    Uses pgvector cosine similarity on the embedding column.
    Falls back to empty list if no embedding or no pool.
    """
    if not embedding:
        return []

    try:
        pool = await get_pool()
    except RuntimeError:
        return []

    sql = f"""
        SELECT
            query,
            bad_response,
            good_response,
            1 - (embedding <=> $1::vector) AS similarity
        FROM {SCHEMA}.few_shot_store
        WHERE persona = $2
          AND agent_type = $3
          AND active = true
          AND embedding IS NOT NULL
          AND 1 - (embedding <=> $1::vector) >= $4
        ORDER BY embedding <=> $1::vector
        LIMIT $5
    """
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, embedding, persona, agent_type, similarity_threshold, top_k)
            return [
                {
                    "query": r["query"],
                    "bad_response": r["bad_response"],
                    "good_response": r["good_response"],
                    "similarity": float(r["similarity"]),
                }
                for r in rows
            ]
    except Exception:
        logger.exception("Failed to query few-shot store")
        return []


async def list_feedback_events(
    *,
    processed: bool | None = None,
    agent_type: str | None = None,
    persona: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """List feedback events with optional filters."""
    try:
        pool = await get_pool()
    except RuntimeError:
        return []

    conditions = []
    params: list[Any] = []
    idx = 1

    if processed is not None:
        conditions.append(f"processed = ${idx}")
        params.append(processed)
        idx += 1
    if agent_type:
        conditions.append(f"agent_type = ${idx}")
        params.append(agent_type)
        idx += 1
    if persona:
        conditions.append(f"persona = ${idx}")
        params.append(persona)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    sql = f"""
        SELECT feedback_id::text, created_at, session_id, conversation_id,
               application_id, agent_type, feedback_type, original_query,
               agent_response, correction, persona, routing_target, processed, metadata
        FROM {SCHEMA}.feedback_events
        {where}
        ORDER BY created_at DESC
        LIMIT ${idx}
    """
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
            return [dict(r) for r in rows]
    except Exception:
        logger.exception("Failed to list feedback events")
        return []


async def list_corrections(
    *,
    persona: str | None = None,
    agent_type: str | None = None,
    category: str | None = None,
    active: bool | None = True,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """List few-shot corrections from the few_shot_store table."""
    try:
        pool = await get_pool()
    except RuntimeError:
        return []

    conditions = []
    params: list[Any] = []
    idx = 1

    if persona:
        conditions.append(f"persona = ${idx}")
        params.append(persona)
        idx += 1
    if agent_type:
        conditions.append(f"agent_type = ${idx}")
        params.append(agent_type)
        idx += 1
    if category:
        conditions.append(f"metadata->>'category' = ${idx}")
        params.append(category)
        idx += 1
    if active is not None:
        conditions.append(f"active = ${idx}")
        params.append(active)
        idx += 1

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)

    sql = f"""
        SELECT example_id::text, persona, agent_type, query,
               bad_response, good_response, active, metadata,
               created_at, updated_at,
               (embedding IS NOT NULL) AS has_embedding
        FROM {SCHEMA}.few_shot_store
        {where}
        ORDER BY created_at DESC
        LIMIT ${idx}
    """
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, *params)
            return [dict(r) for r in rows]
    except Exception:
        logger.exception("Failed to list corrections")
        return []


async def get_correction_stats() -> dict[str, Any]:
    """Get summary statistics for the corrections store."""
    try:
        pool = await get_pool()
    except RuntimeError:
        return {}

    sql = f"""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE active) AS active,
            COUNT(*) FILTER (WHERE embedding IS NOT NULL) AS with_embedding,
            COUNT(DISTINCT persona) AS personas,
            COUNT(DISTINCT agent_type) AS agent_types,
            jsonb_object_agg(
                COALESCE(metadata->>'category', 'unknown'),
                cat_count
            ) AS by_category
        FROM {SCHEMA}.few_shot_store,
        LATERAL (
            SELECT COUNT(*) AS cat_count
            FROM {SCHEMA}.few_shot_store fs2
            WHERE fs2.metadata->>'category' = few_shot_store.metadata->>'category'
        ) sub
    """
    # Simpler version that avoids the lateral complexity:
    sql = f"""
        SELECT
            COUNT(*) AS total,
            COUNT(*) FILTER (WHERE active) AS active,
            COUNT(*) FILTER (WHERE embedding IS NOT NULL) AS with_embedding,
            COUNT(DISTINCT persona) AS personas,
            COUNT(DISTINCT agent_type) AS agent_types
        FROM {SCHEMA}.few_shot_store
    """
    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(sql)
            if not row:
                return {}
            stats = dict(row)

            # Category breakdown
            cat_rows = await conn.fetch(f"""
                SELECT COALESCE(metadata->>'category', 'unknown') AS category, COUNT(*) AS count
                FROM {SCHEMA}.few_shot_store
                GROUP BY 1 ORDER BY 2 DESC
            """)
            stats["by_category"] = {r["category"]: r["count"] for r in cat_rows}

            return stats
    except Exception:
        logger.exception("Failed to get correction stats")
        return {}


async def get_correction_impact() -> dict[str, Any]:
    """Compute HITL impact metrics: feedback trends before/after corrections.

    Returns:
        Dict with positive/negative counts, correction coverage, and per-persona breakdown.
    """
    try:
        pool = await get_pool()
    except RuntimeError:
        return {}

    try:
        async with pool.acquire() as conn:
            # Total feedback by type
            fb_rows = await conn.fetch(f"""
                SELECT feedback_type, COUNT(*) AS cnt
                FROM {SCHEMA}.feedback_events
                GROUP BY 1
            """)
            feedback_by_type = {r["feedback_type"]: r["cnt"] for r in fb_rows}

            # Corrections per persona
            persona_rows = await conn.fetch(f"""
                SELECT persona, COUNT(*) AS corrections,
                       COUNT(*) FILTER (WHERE active) AS active
                FROM {SCHEMA}.few_shot_store
                GROUP BY 1 ORDER BY 2 DESC
            """)

            # First correction date vs latest feedback
            timeline = await conn.fetchrow(f"""
                SELECT
                    (SELECT MIN(created_at) FROM {SCHEMA}.few_shot_store) AS first_correction,
                    (SELECT MAX(created_at) FROM {SCHEMA}.feedback_events) AS latest_feedback,
                    (SELECT COUNT(*) FROM {SCHEMA}.few_shot_store WHERE active) AS active_corrections,
                    (SELECT COUNT(DISTINCT COALESCE(metadata->>'category', 'unknown'))
                     FROM {SCHEMA}.few_shot_store) AS categories_covered
            """)

            # Feedback trend: positive vs negative ratio
            positive = feedback_by_type.get("positive", 0)
            negative = feedback_by_type.get("negative", 0)
            corrections = feedback_by_type.get("correction", 0)
            total = positive + negative + corrections
            satisfaction_rate = round(positive / total * 100, 1) if total > 0 else None

            return {
                "feedback_summary": {
                    "total": total,
                    "positive": positive,
                    "negative": negative,
                    "corrections_submitted": corrections,
                    "satisfaction_rate_pct": satisfaction_rate,
                },
                "corrections_store": {
                    "active_corrections": timeline["active_corrections"] if timeline else 0,
                    "categories_covered": timeline["categories_covered"] if timeline else 0,
                    "first_correction": str(timeline["first_correction"]) if timeline and timeline["first_correction"] else None,
                    "latest_feedback": str(timeline["latest_feedback"]) if timeline and timeline["latest_feedback"] else None,
                },
                "per_persona": [
                    {
                        "persona": r["persona"],
                        "corrections": r["corrections"],
                        "active": r["active"],
                    }
                    for r in persona_rows
                ],
            }
    except Exception:
        logger.exception("Failed to compute correction impact")
        return {}
