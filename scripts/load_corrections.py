"""Load corrections from CSV and JSON files into the few_shot_store table.

Reads corrections/few_shot_examples.csv and corrections/ai_search_examples.json,
generates embeddings via Azure OpenAI, and inserts into workbenchiq.few_shot_store.

Prerequisites:
  - PostgreSQL 16 with pgvector and workbenchiq.few_shot_store table
  - Azure OpenAI embedding deployment (text-embedding-3-small)
  - Environment: AZURE_OPENAI_ENDPOINT, EMBEDDING_DEPLOYMENT (or defaults from config)

Usage:
  python scripts/load_corrections.py                     # Load CSV only
  python scripts/load_corrections.py --json               # Load JSON only
  python scripts/load_corrections.py --all                # Load both CSV + JSON
  python scripts/load_corrections.py --all --dry-run      # Preview without inserting
  python scripts/load_corrections.py --all --skip-embeddings  # Insert without embeddings (faster, no similarity search)
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, ".")
from app.config import load_settings
from app.database.pool import init_pool, get_pool, close_pool
from app.utils import setup_logging

logger = setup_logging()

SCHEMA = "workbenchiq"
CSV_PATH = Path("corrections/few_shot_examples.csv")
JSON_PATH = Path("corrections/ai_search_examples.json")

# Fields stored in metadata JSONB (not as direct columns)
METADATA_FIELDS = ("category", "policy_ref", "risk_level", "corrected_by", "correction_date")


def parse_csv(path: Path) -> list[dict]:
    """Parse CSV into list of row dicts."""
    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "source_id": row["id"],
                "source_file": "few_shot_examples.csv",
                "persona": row["persona"],
                "agent_type": row["agent_type"],
                "query": row["query"],
                "bad_response": row["bad_response"],
                "good_response": row["good_response"],
                "metadata": {
                    "source_id": row["id"],
                    "source": "csv_import",
                    "category": row.get("category", ""),
                    "policy_ref": row.get("policy_ref", ""),
                    "risk_level": row.get("risk_level", ""),
                    "corrected_by": row.get("corrected_by", ""),
                    "correction_date": row.get("correction_date", ""),
                },
            })
    return rows


def parse_json(path: Path) -> list[dict]:
    """Parse JSON into list of row dicts."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    rows = []
    for ex in data.get("examples", []):
        rows.append({
            "source_id": ex["id"],
            "source_file": "ai_search_examples.json",
            "persona": ex["persona"],
            "agent_type": ex["agent_type"],
            "query": ex["query"],
            "bad_response": ex.get("bad_response", ""),
            "good_response": ex["good_response"],
            "metadata": {
                "source_id": ex["id"],
                "source": "json_import",
                "category": ex.get("category", ""),
                "policy_ref": ex.get("policy_ref", ""),
                "risk_level": ex.get("risk_level", ""),
                "corrected_by": ex.get("corrected_by", ""),
                "correction_date": ex.get("correction_date", ""),
                "embedding_text": ex.get("embedding_text", ""),
            },
        })
    return rows


async def generate_embeddings(
    rows: list[dict],
    settings,
    batch_size: int = 50,
) -> list[list[float] | None]:
    """Generate embeddings in batches using Azure OpenAI."""
    from app.rag.embeddings import EmbeddingService

    svc = EmbeddingService(settings.openai, settings.rag)
    embeddings: list[list[float] | None] = []

    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        texts = [r["query"] for r in batch]
        logger.info("Embedding batch %d-%d / %d ...", i + 1, i + len(batch), len(rows))

        try:
            batch_embs = await asyncio.to_thread(svc.get_embeddings_batch, texts)
            embeddings.extend(batch_embs)
        except Exception as e:
            logger.error("Embedding failed for batch %d: %s", i, e)
            embeddings.extend([None] * len(batch))

        # Respect rate limits
        if i + batch_size < len(rows):
            time.sleep(1)

    return embeddings


async def insert_rows(
    rows: list[dict],
    embeddings: list[list[float] | None] | None,
    dry_run: bool = False,
) -> tuple[int, int]:
    """Insert rows into few_shot_store. Returns (inserted, skipped)."""
    pool = await get_pool()
    inserted = 0
    skipped = 0

    async with pool.acquire() as conn:
        for i, row in enumerate(rows):
            source_id = row["source_id"]

            # Check for existing record (idempotent by source_id)
            exists = await conn.fetchval(
                f"SELECT 1 FROM {SCHEMA}.few_shot_store WHERE metadata->>'source_id' = $1",
                source_id,
            )
            if exists:
                skipped += 1
                continue

            if dry_run:
                logger.info("[DRY RUN] Would insert: %s (%s / %s)", source_id, row["persona"], row["agent_type"])
                inserted += 1
                continue

            emb = embeddings[i] if embeddings else None

            await conn.execute(
                f"""
                INSERT INTO {SCHEMA}.few_shot_store
                    (persona, agent_type, query, bad_response, good_response, embedding, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                """,
                row["persona"],
                row["agent_type"],
                row["query"],
                row["bad_response"],
                row["good_response"],
                emb,
                json.dumps(row["metadata"]),
            )
            inserted += 1

    return inserted, skipped


async def main(
    load_csv: bool = True,
    load_json: bool = False,
    dry_run: bool = False,
    skip_embeddings: bool = False,
):
    settings = load_settings()
    await init_pool(settings.database)

    all_rows: list[dict] = []

    if load_csv:
        if not CSV_PATH.exists():
            logger.error("CSV file not found: %s", CSV_PATH)
            return
        csv_rows = parse_csv(CSV_PATH)
        logger.info("Parsed %d rows from CSV", len(csv_rows))
        all_rows.extend(csv_rows)

    if load_json:
        if not JSON_PATH.exists():
            logger.error("JSON file not found: %s", JSON_PATH)
            return
        json_rows = parse_json(JSON_PATH)
        logger.info("Parsed %d rows from JSON", len(json_rows))
        all_rows.extend(json_rows)

    if not all_rows:
        logger.warning("No rows to load.")
        return

    logger.info("Total rows to process: %d", len(all_rows))

    # Generate embeddings
    embeddings = None
    if not skip_embeddings and not dry_run:
        logger.info("Generating embeddings via Azure OpenAI ...")
        embeddings = await generate_embeddings(all_rows, settings)
        embedded_count = sum(1 for e in embeddings if e is not None)
        logger.info("Embeddings generated: %d / %d", embedded_count, len(all_rows))
    elif skip_embeddings:
        logger.info("Skipping embedding generation (--skip-embeddings)")

    # Insert
    inserted, skipped = await insert_rows(all_rows, embeddings, dry_run=dry_run)

    action = "Would insert" if dry_run else "Inserted"
    logger.info("%s: %d | Skipped (existing): %d | Total: %d", action, inserted, skipped, len(all_rows))

    await close_pool()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Load corrections into few_shot_store")
    parser.add_argument("--json", action="store_true", help="Load JSON file (ai_search_examples.json)")
    parser.add_argument("--all", action="store_true", help="Load both CSV and JSON files")
    parser.add_argument("--dry-run", action="store_true", help="Preview without inserting")
    parser.add_argument("--skip-embeddings", action="store_true", help="Insert without embeddings")
    args = parser.parse_args()

    load_csv = not args.json or args.all
    load_json = args.json or args.all

    asyncio.run(main(
        load_csv=load_csv,
        load_json=load_json,
        dry_run=args.dry_run,
        skip_embeddings=args.skip_embeddings,
    ))
