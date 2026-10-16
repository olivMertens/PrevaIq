"""Seed applications_summary from existing metadata.json files.

Reads all local application folders and inserts their summary into PostgreSQL.

Usage:
    python scripts/seed_applications_summary.py
    python scripts/seed_applications_summary.py --storage blob   # from Azure Blob
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


async def seed():
    from app.config import load_settings
    from app.storage import list_applications, load_application, _sync_summary_to_pg
    from app.database.pool import init_pool, close_pool
    from app.database.settings import DatabaseSettings

    settings = load_settings()

    # Init DB pool
    db_settings = DatabaseSettings(
        host=os.getenv("POSTGRESQL_HOST", ""),
        port=int(os.getenv("POSTGRESQL_PORT", "5432")),
        database=os.getenv("POSTGRESQL_DATABASE", "workbenchiq"),
        user=os.getenv("POSTGRESQL_USER", ""),
        password=os.getenv("POSTGRESQL_PASSWORD", ""),
        ssl_mode=os.getenv("POSTGRESQL_SSL_MODE", "require"),
    )

    if not db_settings.host:
        print("ERROR: POSTGRESQL_HOST not set.")
        sys.exit(1)

    await init_pool(db_settings)

    # Load all applications
    apps = list_applications(settings.app.storage_root)
    print(f"Found {len(apps)} applications")

    synced = 0
    errors = 0
    for app_summary in apps:
        app_id = app_summary.get("id", "")
        try:
            app_md = load_application(settings.app.storage_root, app_id)
            if app_md:
                _sync_summary_to_pg(app_md)
                # Wait for the async task to complete
                await asyncio.sleep(0.1)
                synced += 1
                persona = app_md.persona or "?"
                status = app_md.status or "?"
                print(f"  ✓ {app_id} ({persona} / {status})")
        except Exception as e:
            errors += 1
            print(f"  ✗ {app_id}: {e}")

    # Give async tasks time to complete
    await asyncio.sleep(2)

    # Check final count
    try:
        from app.database.pool import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            count = await conn.fetchval(
                "SELECT COUNT(*) FROM workbenchiq.applications_summary WHERE brand = $1",
                settings.brand_name,
            )
            print(f"\n✓ applications_summary ({settings.brand_name}): {count} rows")
    except Exception as e:
        print(f"\n⚠ Could not verify count: {e}")

    await close_pool()
    print(f"\nDone! Synced: {synced}, Errors: {errors}")


if __name__ == "__main__":
    asyncio.run(seed())
