"""Initialise the data of a fresh environment, run inside Azure (Container Apps Job).

Steps: PostgreSQL schema + tables, RAG indexing of the brand policies (JSON + PDF) and
demo dossiers. Idempotent: every step can be re-run (--force reindexing, IF NOT EXISTS DDL).

Usage (inside the ops image, env copied from the API app):
    python scripts/bootstrap_data.py [--skip-seed]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))


def run(*args: str) -> None:
    print(f"\n>>> {' '.join(args)}", flush=True)
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


async def create_rag_schema() -> None:
    import setup_postgresql_rag as rag

    config = {
        "server_name": os.environ["POSTGRESQL_HOST"].split(".")[0],
        "database_name": os.environ.get("POSTGRESQL_DATABASE", "workbenchiq"),
        "admin_user": os.environ["POSTGRESQL_USER"],
        "schema_name": os.environ.get("POSTGRESQL_SCHEMA", "workbenchiq"),
    }
    if not await rag.create_schema(config, os.environ["POSTGRESQL_PASSWORD"]):
        raise SystemExit("RAG schema creation failed")


async def create_claims_tables() -> None:
    """Create the claims chunk tables the PDF indexer writes to (before the brand migration)."""
    from app.config import load_settings
    from app.database.pool import close_pool, init_pool
    import index_pdf_policies

    settings = load_settings()
    await init_pool(settings.database)
    try:
        await index_pdf_policies._ensure_tables(settings.database.schema or "workbenchiq")
    finally:
        await close_pool()


async def chunk_stats() -> None:
    import asyncpg

    conn = await asyncpg.connect(
        host=os.environ["POSTGRESQL_HOST"], user=os.environ["POSTGRESQL_USER"],
        password=os.environ["POSTGRESQL_PASSWORD"],
        database=os.environ.get("POSTGRESQL_DATABASE", "workbenchiq"), ssl="require",
    )
    try:
        tables = await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'workbenchiq' AND table_name LIKE '%chunks%' ORDER BY 1"
        )
        for row in tables:
            name = row["table_name"]
            for stat in await conn.fetch(
                f"SELECT brand, category, count(*) AS n FROM workbenchiq.{name} GROUP BY 1, 2 ORDER BY 1, 2"
            ):
                print(f"  {name}: brand={stat['brand']} category={stat['category']} chunks={stat['n']}")
    finally:
        await conn.close()


def seed_dossiers() -> None:
    from app.storage_providers import StorageSettings, init_storage_provider
    from scripts.seed_customer360 import seed_applications

    init_storage_provider(StorageSettings.from_env())
    print(f"  seeded demo dossiers: {seed_applications('data')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-seed", action="store_true", help="Do not (re)write demo dossiers")
    args = parser.parse_args()
    brand = os.environ.get("BRAND_NAME", "PrevaIQ")
    pdf_dir = ROOT / "assets" / "pdf" / brand.lower()

    asyncio.run(create_rag_schema())
    asyncio.run(create_claims_tables())
    # The DDL above predates multi-brand: add the brand column + brand-aware unique indexes.
    run("scripts/migrate_add_brand_column.py")
    run("scripts/setup_feedback_tables.py")
    run("scripts/setup_validation_tables.py")
    run("scripts/setup_business_tables.py")
    run("scripts/setup_applications_summary.py")
    run("scripts/index_policies.py", "--policies", "prompts/life-health-underwriting-policies.json", "--force")
    run("scripts/index_policies.py", "--policies", "prompts/habitation-claims-policies.json", "--force")
    if pdf_dir.is_dir():
        run("scripts/index_pdf_policies.py", "--dir", str(pdf_dir), "--local", "--force", "--brand", brand)
    else:
        print(f"  no policy PDFs in {pdf_dir} — skipped")
    if not args.skip_seed:
        seed_dossiers()
    asyncio.run(chunk_stats())
    print("\nBOOTSTRAP DONE", flush=True)


if __name__ == "__main__":
    main()
