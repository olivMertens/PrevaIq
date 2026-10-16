#!/usr/bin/env python3
"""Migration: Add 'brand' column to all RAG policy_chunks tables.

Adds brand-based segmentation so multiple brands can share the same
PostgreSQL database but query only their own policy documents.

Usage:
    python scripts/migrate_add_brand_column.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import load_settings
from app.database.pool import init_pool, get_pool
from app.utils import setup_logging

logger = setup_logging()

TABLES = [
    "policy_chunks",
    "health_claims_policy_chunks",
    "claim_policy_chunks",
    "pc_claims_policy_chunks",
    "mortgage_policy_chunks",
]

SCHEMA = "workbenchiq"


async def migrate():
    settings = load_settings()
    await init_pool(settings.database)
    pool = await get_pool()

    async with pool.acquire() as conn:
        for table in TABLES:
            fqn = f"{SCHEMA}.{table}"

            # Check if table exists
            table_exists = await conn.fetchval(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema=$1 AND table_name=$2",
                SCHEMA, table,
            )
            if not table_exists:
                logger.info(f"  {fqn}: table does not exist — skipping")
                continue

            # Check if column already exists
            exists = await conn.fetchval(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_schema=$1 AND table_name=$2 AND column_name='brand'",
                SCHEMA, table,
            )
            if exists:
                logger.info(f"  {fqn}: brand column already exists — skipping")
                continue

            logger.info(f"  {fqn}: adding brand column...")
            await conn.execute(f"ALTER TABLE {fqn} ADD COLUMN brand TEXT NOT NULL DEFAULT 'PrevaIQ'")
            await conn.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_brand ON {fqn} (brand)")

            # Update unique index to include brand
            # Drop old unique index and recreate with brand
            await conn.execute(f"DROP INDEX IF EXISTS {SCHEMA}.idx_{table}_unique")
            await conn.execute(
                f"CREATE UNIQUE INDEX idx_{table}_unique ON {fqn} "
                f"(policy_id, chunk_type, COALESCE(criteria_id, ''), content_hash, brand)"
            )

            count = await conn.fetchval(f"SELECT COUNT(*) FROM {fqn}")
            logger.info(f"  {fqn}: brand column added, {count} existing rows set to 'PrevaIQ'")

    logger.info("Migration complete — all tables have brand column")


if __name__ == "__main__":
    asyncio.run(migrate())
