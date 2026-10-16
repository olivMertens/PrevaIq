"""Setup the applications_summary PostgreSQL table.

This lightweight summary table mirrors key dossier fields to PostgreSQL
so they appear in Fabric via CDC mirroring. The full metadata stays in
Blob Storage — this table only holds searchable/aggregatable fields.

Usage:
    python scripts/setup_applications_summary.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

SCHEMA = "workbenchiq"

CREATE_TABLE_SQL = f"""
CREATE TABLE IF NOT EXISTS {SCHEMA}.applications_summary (
    app_id              VARCHAR(64) NOT NULL,
    brand               VARCHAR(50) NOT NULL DEFAULT 'PrevaIQ',
    persona             VARCHAR(50),
    status              VARCHAR(30) NOT NULL DEFAULT 'pending',
    nom_assure          VARCHAR(255),
    nature_sinistre     VARCHAR(500),
    montant_estime      NUMERIC(12,2),
    franchise           NUMERIC(12,2),
    indemnisation       NUMERIC(12,2),
    numero_contrat      VARCHAR(100),
    date_sinistre       DATE,
    date_declaration    DATE,
    date_cloture        DATE,
    file_count          INT DEFAULT 0,
    sentiment_score     INT,
    sentiment_level     VARCHAR(20),
    sentiment_tone      VARCHAR(20),
    fraud_risk_level    VARCHAR(20),
    fraud_risk_score    INT,
    siu_recommended     BOOLEAN DEFAULT FALSE,
    processing_status   VARCHAR(30),
    external_reference  VARCHAR(100),
    adjuster_decision   VARCHAR(50),
    decided_at          TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (app_id, brand)
);
"""

CREATE_INDEXES_SQL = [
    f"CREATE INDEX IF NOT EXISTS idx_appsummary_brand ON {SCHEMA}.applications_summary (brand)",
    f"CREATE INDEX IF NOT EXISTS idx_appsummary_brand_persona ON {SCHEMA}.applications_summary (brand, persona)",
    f"CREATE INDEX IF NOT EXISTS idx_appsummary_persona ON {SCHEMA}.applications_summary (persona)",
    f"CREATE INDEX IF NOT EXISTS idx_appsummary_status ON {SCHEMA}.applications_summary (status)",
    f"CREATE INDEX IF NOT EXISTS idx_appsummary_nom ON {SCHEMA}.applications_summary (nom_assure)",
    f"CREATE INDEX IF NOT EXISTS idx_appsummary_sentiment ON {SCHEMA}.applications_summary (sentiment_score)",
    f"CREATE INDEX IF NOT EXISTS idx_appsummary_fraud ON {SCHEMA}.applications_summary (fraud_risk_level)",
    f"CREATE INDEX IF NOT EXISTS idx_appsummary_date ON {SCHEMA}.applications_summary (date_sinistre)",
    f"CREATE INDEX IF NOT EXISTS idx_appsummary_date_cloture ON {SCHEMA}.applications_summary (date_cloture)",
    f"CREATE INDEX IF NOT EXISTS idx_appsummary_updated ON {SCHEMA}.applications_summary (updated_at DESC)",
]

# Columns added after the first release: upgrades tables created by older versions.
ADD_COLUMNS_SQL = [
    f"ALTER TABLE {SCHEMA}.applications_summary ADD COLUMN IF NOT EXISTS adjuster_decision VARCHAR(50)",
    f"ALTER TABLE {SCHEMA}.applications_summary ADD COLUMN IF NOT EXISTS decided_at TIMESTAMPTZ",
]

COMMENT_SQL = f"""
COMMENT ON TABLE {SCHEMA}.applications_summary IS
'Lightweight summary of dossier applications — mirrored to Fabric via CDC.
Full metadata stays in Azure Blob Storage. This table provides SQL search,
Fabric Data Agent queries, and cross-app aggregation.';
"""


async def setup():
    from app.database.pool import init_pool, close_pool
    from app.database.settings import DatabaseSettings

    settings = DatabaseSettings(
        host=os.getenv("POSTGRESQL_HOST", ""),
        port=int(os.getenv("POSTGRESQL_PORT", "5432")),
        database=os.getenv("POSTGRESQL_DATABASE", "workbenchiq"),
        user=os.getenv("POSTGRESQL_USER", ""),
        password=os.getenv("POSTGRESQL_PASSWORD", ""),
        ssl_mode=os.getenv("POSTGRESQL_SSL_MODE", "require"),
    )

    if not settings.host:
        print("ERROR: POSTGRESQL_HOST not set. Set PostgreSQL env vars.")
        sys.exit(1)

    pool = await init_pool(settings)

    async with pool.acquire() as conn:
        # Ensure schema exists
        await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

        # Create table
        await conn.execute(CREATE_TABLE_SQL)
        print(f"✓ Table {SCHEMA}.applications_summary created")

        for alter_sql in ADD_COLUMNS_SQL:
            await conn.execute(alter_sql)

        # Create indexes
        for idx_sql in CREATE_INDEXES_SQL:
            await conn.execute(idx_sql)
        print(f"✓ {len(CREATE_INDEXES_SQL)} indexes created")

        # Add comment
        await conn.execute(COMMENT_SQL)
        print("✓ Table comment added")

        # Count existing rows
        count = await conn.fetchval(
            f"SELECT COUNT(*) FROM {SCHEMA}.applications_summary"
        )
        print(f"✓ Current rows: {count}")

    await close_pool()
    print("\nDone! Table ready for Fabric CDC mirroring.")


if __name__ == "__main__":
    asyncio.run(setup())
