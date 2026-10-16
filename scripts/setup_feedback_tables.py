"""Create feedback loop tables for Fabric Mirror integration.

Tables created in workbenchiq schema:
  - feedback_events     — Central feedback capture (👍/👎/correction)
  - few_shot_store      — Dynamic few-shot examples for FoundryIQ agents
  - data_agent_nl_sql_examples — NL→SQL corrections for Fabric Data Agent

Prerequisites:
  - PostgreSQL 16 with pgvector extension
  - workbenchiq schema (created by setup_postgresql_rag.py)
  - For Fabric Mirroring: wal_level=logical on the server

Usage:
  python scripts/setup_feedback_tables.py
  python scripts/setup_feedback_tables.py --seed   # Include sample data
"""
from __future__ import annotations

import argparse
import asyncio
import sys

sys.path.insert(0, ".")
from app.database.pool import init_pool, get_pool
from app.config import load_settings

# ---------------------------------------------------------------------------
# DDL statements
# ---------------------------------------------------------------------------

TRIGGER_FUNCTION_SQL = """
CREATE OR REPLACE FUNCTION workbenchiq.compute_routing_target()
RETURNS TRIGGER AS $$
BEGIN
    NEW.routing_target := CASE
        WHEN NEW.agent_type = 'data_agent' THEN 'fabric_agent'
        ELSE 'foundry'
    END;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

FEEDBACK_EVENTS_SQL = """
CREATE TABLE IF NOT EXISTS workbenchiq.feedback_events (
    feedback_id      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at       TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    session_id       VARCHAR(255),
    conversation_id  VARCHAR(255),
    application_id   VARCHAR(255),
    agent_type       VARCHAR(50) NOT NULL,
    feedback_type    VARCHAR(50) NOT NULL,
    original_query   TEXT,
    agent_response   TEXT,
    correction       TEXT,
    persona          VARCHAR(100),
    routing_target   VARCHAR(50) NOT NULL DEFAULT 'foundry',
    processed        BOOLEAN NOT NULL DEFAULT false,
    metadata         JSONB DEFAULT '{}'::jsonb
)
"""

FEEDBACK_EVENTS_TRIGGER_SQL = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_feedback_routing'
    ) THEN
        CREATE TRIGGER trg_feedback_routing
            BEFORE INSERT ON workbenchiq.feedback_events
            FOR EACH ROW EXECUTE FUNCTION workbenchiq.compute_routing_target();
    END IF;
END $$;
"""

FEEDBACK_EVENTS_INDEXES_SQL = [
    """CREATE INDEX IF NOT EXISTS idx_feedback_events_unprocessed
       ON workbenchiq.feedback_events (processed, routing_target)
       WHERE processed = false""",
    """CREATE INDEX IF NOT EXISTS idx_feedback_events_analytics
       ON workbenchiq.feedback_events (agent_type, persona, created_at)""",
    """CREATE INDEX IF NOT EXISTS idx_feedback_events_metadata
       ON workbenchiq.feedback_events USING gin (metadata)""",
]

FEW_SHOT_STORE_SQL = """
CREATE TABLE IF NOT EXISTS workbenchiq.few_shot_store (
    example_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feedback_id  UUID REFERENCES workbenchiq.feedback_events(feedback_id),
    persona      VARCHAR(100) NOT NULL,
    agent_type   VARCHAR(50) NOT NULL,
    query        TEXT NOT NULL,
    bad_response TEXT,
    good_response TEXT NOT NULL,
    embedding    vector(1536),
    active       BOOLEAN NOT NULL DEFAULT true,
    metadata     JSONB DEFAULT '{}'::jsonb,
    created_at   TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
)
"""

FEW_SHOT_STORE_INDEXES_SQL = [
    """CREATE INDEX IF NOT EXISTS idx_few_shot_embedding
       ON workbenchiq.few_shot_store
       USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)""",
    """CREATE INDEX IF NOT EXISTS idx_few_shot_filter
       ON workbenchiq.few_shot_store (persona, agent_type, active)""",
]

NL_SQL_EXAMPLES_SQL = """
CREATE TABLE IF NOT EXISTS workbenchiq.data_agent_nl_sql_examples (
    example_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    feedback_id      UUID REFERENCES workbenchiq.feedback_events(feedback_id),
    natural_language TEXT NOT NULL,
    correct_sql      TEXT NOT NULL,
    description      TEXT,
    persona          VARCHAR(100),
    active           BOOLEAN NOT NULL DEFAULT true,
    metadata         JSONB DEFAULT '{}'::jsonb,
    created_at       TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
)
"""

NL_SQL_EXAMPLES_INDEXES_SQL = [
    """CREATE INDEX IF NOT EXISTS idx_nl_sql_export
       ON workbenchiq.data_agent_nl_sql_examples (persona, active, created_at DESC)""",
]

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SEED_FEEDBACK_SQL = """
INSERT INTO workbenchiq.feedback_events
    (session_id, conversation_id, application_id, agent_type, feedback_type,
     original_query, agent_response, persona, metadata)
VALUES
    ('sess-demo-001', 'conv-abc', 'app-12345', 'chat', 'positive',
     'Quels sont les plafonds de garantie pour un dégât des eaux ?',
     'Selon l''article HAB-003 des Conditions Générales Habitation, le plafond de garantie pour les dégâts des eaux est de 150 000 € pour les dommages immobiliers.',
     'habitation', '{"user_id": "groupIqUser1", "confidence": 0.92}'::jsonb)
ON CONFLICT DO NOTHING
"""

SEED_CORRECTION_SQL = """
INSERT INTO workbenchiq.feedback_events
    (session_id, conversation_id, application_id, agent_type, feedback_type,
     original_query, agent_response, correction, persona, metadata)
VALUES
    ('sess-demo-002', 'conv-def', 'app-67890', 'risk', 'correction',
     'Évaluer le risque pour un sinistre auto avec 3 véhicules impliqués',
     'Score de risque : 7/10. Responsabilité partagée à 50/50.',
     'Score corrigé : 4/10. La responsabilité est clairement établie à 100%% tiers selon le constat amiable (case 2 cochée). Réf: art. AUTO-012.',
     'auto', '{"user_id": "groupIqAdmin", "original_score": 7, "corrected_score": 4}'::jsonb)
ON CONFLICT DO NOTHING
"""

SEED_DATA_AGENT_SQL = """
INSERT INTO workbenchiq.feedback_events
    (session_id, conversation_id, application_id, agent_type, feedback_type,
     original_query, agent_response, correction, persona, metadata)
VALUES
    ('sess-demo-003', 'conv-ghi', NULL, 'data_agent', 'correction',
     'Montant total des sinistres habitation payés supérieurs à 5000€ en 2025',
     'SELECT SUM(amount) FROM claims WHERE type = ''water'' AND amount > 5000',
     'SELECT SUM(montant_paye) FROM workbenchiq.sinistres WHERE type_sinistre = ''habitation'' AND montant_paye > 5000 AND EXTRACT(YEAR FROM date_sinistre) = 2025',
     'habitation', '{"user_id": "groupIqAdmin"}'::jsonb)
ON CONFLICT DO NOTHING
"""

SEED_FEW_SHOT_SQL = """
INSERT INTO workbenchiq.few_shot_store
    (feedback_id, persona, agent_type, query, bad_response, good_response, metadata)
SELECT
    fe.feedback_id, 'auto', 'risk',
    'Évaluer le risque pour un sinistre auto avec 3 véhicules impliqués',
    'Score de risque : 7/10. Responsabilité partagée à 50/50.',
    'Score de risque : 4/10. Responsabilité 100%% tiers établie par constat amiable (case 2). Réf: art. AUTO-012, Conditions Générales Auto.',
    '{"source": "gestionnaire_correction", "validated": true}'::jsonb
FROM workbenchiq.feedback_events fe
WHERE fe.session_id = 'sess-demo-002'
AND NOT EXISTS (
    SELECT 1 FROM workbenchiq.few_shot_store fs WHERE fs.feedback_id = fe.feedback_id
)
"""

SEED_NL_SQL_SQL = """
INSERT INTO workbenchiq.data_agent_nl_sql_examples
    (feedback_id, natural_language, correct_sql, description, persona, metadata)
SELECT
    fe.feedback_id,
    'Montant total des sinistres habitation payés supérieurs à 5000€ en 2025',
    'SELECT SUM(montant_paye) FROM workbenchiq.sinistres WHERE type_sinistre = ''habitation'' AND montant_paye > 5000 AND EXTRACT(YEAR FROM date_sinistre) = 2025',
    'Correction gestionnaire — utiliser montant_paye (pas amount), type_sinistre (pas type), date_sinistre, schéma workbenchiq',
    'habitation',
    '{"source": "gestionnaire_correction"}'::jsonb
FROM workbenchiq.feedback_events fe
WHERE fe.session_id = 'sess-demo-003'
AND NOT EXISTS (
    SELECT 1 FROM workbenchiq.data_agent_nl_sql_examples ex WHERE ex.feedback_id = fe.feedback_id
)
"""


async def main(seed: bool = False):
    s = load_settings()
    await init_pool(s.database)
    pool = await get_pool()

    async with pool.acquire() as conn:
        # Ensure prerequisites
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute("CREATE SCHEMA IF NOT EXISTS workbenchiq")

        # Create trigger function
        await conn.execute(TRIGGER_FUNCTION_SQL)
        print("  Created: workbenchiq.compute_routing_target() trigger function")

        # Create tables
        await conn.execute(FEEDBACK_EVENTS_SQL)
        print("  Created: workbenchiq.feedback_events")

        await conn.execute(FEEDBACK_EVENTS_TRIGGER_SQL)
        print("  Created: trg_feedback_routing trigger")

        for idx_sql in FEEDBACK_EVENTS_INDEXES_SQL:
            await conn.execute(idx_sql)
        print("  Created: feedback_events indexes")

        await conn.execute(FEW_SHOT_STORE_SQL)
        print("  Created: workbenchiq.few_shot_store")

        for idx_sql in FEW_SHOT_STORE_INDEXES_SQL:
            await conn.execute(idx_sql)
        print("  Created: few_shot_store indexes (HNSW + filter)")

        await conn.execute(NL_SQL_EXAMPLES_SQL)
        print("  Created: workbenchiq.data_agent_nl_sql_examples")

        for idx_sql in NL_SQL_EXAMPLES_INDEXES_SQL:
            await conn.execute(idx_sql)
        print("  Created: data_agent_nl_sql_examples indexes")

        # Seed sample data
        if seed:
            print("\n  Seeding sample data...")
            await conn.execute(SEED_FEEDBACK_SQL)
            await conn.execute(SEED_CORRECTION_SQL)
            await conn.execute(SEED_DATA_AGENT_SQL)
            await conn.execute(SEED_FEW_SHOT_SQL)
            await conn.execute(SEED_NL_SQL_SQL)
            print("  Seeded: 3 feedback events + 1 few-shot + 1 NL→SQL example")

        # Verify
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='workbenchiq' ORDER BY tablename"
        )
        print(f"\n  All workbenchiq tables: {[r['tablename'] for r in rows]}")

        # Verify trigger
        if seed:
            targets = await conn.fetch(
                "SELECT agent_type, routing_target FROM workbenchiq.feedback_events ORDER BY created_at"
            )
            for r in targets:
                print(f"  Trigger check: agent_type={r['agent_type']} → routing_target={r['routing_target']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Setup feedback tables for Fabric Mirror")
    parser.add_argument("--seed", action="store_true", help="Insert sample data for testing")
    args = parser.parse_args()
    asyncio.run(main(seed=args.seed))
