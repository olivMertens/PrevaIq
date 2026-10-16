"""Create decision validation tables for the Validation Agent.

Tables created in workbenchiq schema:
  - decision_validations   — Stores validation results comparing AI vs human decisions

Prerequisites:
  - PostgreSQL 16 with pgvector extension
  - workbenchiq schema (created by setup_postgresql_rag.py)
  - claim_assessments table (created by setup_claim_tables or repository.py)

Usage:
  python scripts/setup_validation_tables.py
  python scripts/setup_validation_tables.py --seed   # Include sample data
"""
from __future__ import annotations

import argparse
import asyncio
import sys

sys.path.insert(0, ".")
from app.database.pool import init_pool, get_pool
from app.config import load_settings

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------

DECISION_VALIDATIONS_SQL = """
CREATE TABLE IF NOT EXISTS workbenchiq.decision_validations (
    validation_id     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    application_id    VARCHAR(255) NOT NULL,
    persona           VARCHAR(100),
    ai_recommendation VARCHAR(50),
    human_decision    VARCHAR(50) NOT NULL,
    divergence_level  VARCHAR(20) NOT NULL DEFAULT 'aligned',
    risk_level        VARCHAR(50),
    justification     TEXT,
    escalated         BOOLEAN NOT NULL DEFAULT false,
    escalation_reason TEXT,
    manager_review    VARCHAR(50),
    manager_notes     TEXT,
    reviewed_at       TIMESTAMPTZ,
    metadata          JSONB DEFAULT '{}'::jsonb,
    created_at        TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
)
"""

DECISION_VALIDATIONS_INDEXES_SQL = [
    """CREATE INDEX IF NOT EXISTS idx_dv_application
       ON workbenchiq.decision_validations (application_id)""",
    """CREATE INDEX IF NOT EXISTS idx_dv_divergence
       ON workbenchiq.decision_validations (divergence_level, escalated)
       WHERE escalated = true""",
    """CREATE INDEX IF NOT EXISTS idx_dv_persona_date
       ON workbenchiq.decision_validations (persona, created_at DESC)""",
]

# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

SEED_VALIDATIONS_SQL = """
INSERT INTO workbenchiq.decision_validations
    (application_id, persona, ai_recommendation, human_decision,
     divergence_level, risk_level, justification, escalated)
VALUES
    ('app-demo-001', 'automotive_claims', 'approve', 'approve',
     'aligned', 'low', 'AI and adjuster agree — straightforward fender-bender claim.', false),
    ('app-demo-002', 'habitation_claims', 'approve', 'defer',
     'moderate', 'medium', 'AI recommended approval but adjuster deferred pending additional water damage assessment.', false),
    ('app-demo-003', 'underwriting', 'approve', 'decline',
     'high', 'high', 'AI recommended approval but underwriter declined due to undisclosed pre-existing condition not captured in extraction.', true)
ON CONFLICT DO NOTHING
"""


async def main(seed: bool = False):
    s = load_settings()
    await init_pool(s.database)
    pool = await get_pool()

    async with pool.acquire() as conn:
        await conn.execute("CREATE SCHEMA IF NOT EXISTS workbenchiq")

        await conn.execute(DECISION_VALIDATIONS_SQL)
        print("  Created: workbenchiq.decision_validations")

        for idx_sql in DECISION_VALIDATIONS_INDEXES_SQL:
            await conn.execute(idx_sql)
        print("  Created: decision_validations indexes")

        if seed:
            print("\n  Seeding sample data...")
            await conn.execute(SEED_VALIDATIONS_SQL)
            print("  Seeded: 3 decision validation examples")

        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='workbenchiq' ORDER BY tablename"
        )
        print(f"\n  workbenchiq tables: {[r['tablename'] for r in rows]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Setup decision validation tables")
    parser.add_argument("--seed", action="store_true", help="Insert sample data")
    args = parser.parse_args()
    asyncio.run(main(seed=args.seed))
