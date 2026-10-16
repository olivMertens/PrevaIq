"""Index corrections into Azure AI Search.

Creates the 'corrections' index and uploads all entries from
corrections/ai_search_examples.json with embeddings.

Usage:
  python scripts/index_corrections_search.py
  python scripts/index_corrections_search.py --check   # Check index only
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, ".")
from app.config import load_settings
from app.rag.embeddings import EmbeddingService
from app.utils import setup_logging

logger = setup_logging()

SEARCH_ENDPOINT = os.environ.get(
    "AZURE_SEARCH_ENDPOINT", "https://srch-prevaiq-demo.search.windows.net"
)
SEARCH_API_KEY = os.environ.get("AZURE_SEARCH_API_KEY", "")
INDEX_NAME = "corrections"
API_VERSION = "2024-07-01"
JSON_PATH = Path("corrections/ai_search_examples.json")

INDEX_SCHEMA = {
    "name": INDEX_NAME,
    "fields": [
        {"name": "id", "type": "Edm.String", "key": True, "filterable": True},
        {"name": "persona", "type": "Edm.String", "filterable": True, "facetable": True},
        {"name": "agent_type", "type": "Edm.String", "filterable": True, "facetable": True},
        {"name": "category", "type": "Edm.String", "filterable": True, "facetable": True},
        {"name": "query", "type": "Edm.String", "searchable": True},
        {"name": "bad_response", "type": "Edm.String", "searchable": True},
        {"name": "good_response", "type": "Edm.String", "searchable": True},
        {"name": "policy_ref", "type": "Edm.String", "filterable": True},
        {"name": "risk_level", "type": "Edm.String", "filterable": True, "facetable": True},
        {"name": "corrected_by", "type": "Edm.String", "filterable": True},
        {"name": "correction_date", "type": "Edm.String", "filterable": True, "sortable": True},
        {"name": "embedding_text", "type": "Edm.String", "searchable": True},
        {
            "name": "embedding",
            "type": "Collection(Edm.Single)",
            "searchable": True,
            "dimensions": 1536,
            "vectorSearchProfile": "default-profile",
        },
    ],
    "vectorSearch": {
        "algorithms": [{"name": "hnsw-algo", "kind": "hnsw", "hnswParameters": {"m": 4, "efConstruction": 400, "efSearch": 500, "metric": "cosine"}}],
        "profiles": [{"name": "default-profile", "algorithm": "hnsw-algo"}],
    },
}


def _headers():
    return {"Content-Type": "application/json", "api-key": SEARCH_API_KEY}


def create_index():
    """Create or update the corrections index."""
    url = f"{SEARCH_ENDPOINT}/indexes/{INDEX_NAME}?api-version={API_VERSION}"
    r = requests.put(url, json=INDEX_SCHEMA, headers=_headers())
    if r.status_code in (200, 201, 204):
        logger.info("Index '%s' created/updated", INDEX_NAME)
    else:
        logger.error("Failed to create index: %s %s", r.status_code, r.text)
        raise RuntimeError(f"Index creation failed: {r.status_code}")


def check_index():
    """Check if index exists and return doc count."""
    url = f"{SEARCH_ENDPOINT}/indexes/{INDEX_NAME}/docs/$count?api-version={API_VERSION}"
    r = requests.get(url, headers=_headers())
    if r.status_code == 200:
        return int(r.text)
    return -1


def upload_documents(docs: list[dict], batch_size: int = 50):
    """Upload documents to the index in batches."""
    url = f"{SEARCH_ENDPOINT}/indexes/{INDEX_NAME}/docs/index?api-version={API_VERSION}"
    total = 0
    for i in range(0, len(docs), batch_size):
        batch = docs[i : i + batch_size]
        payload = {"value": [{"@search.action": "mergeOrUpload", **doc} for doc in batch]}
        r = requests.post(url, json=payload, headers=_headers())
        if r.status_code in (200, 207):
            results = r.json().get("value", [])
            ok = sum(1 for v in results if v.get("status"))
            total += ok
            logger.info("  Batch %d-%d: %d/%d indexed", i + 1, i + len(batch), ok, len(batch))
        else:
            logger.error("  Batch %d failed: %s", i, r.text[:200])
    return total


def main(check_only: bool = False):
    # Check
    count = check_index()
    if count >= 0:
        print(f"Index '{INDEX_NAME}' exists: {count} documents")
        if check_only:
            return
    elif check_only:
        print(f"Index '{INDEX_NAME}' does not exist")
        return

    # Create index
    print("Creating index...")
    create_index()

    # Load JSON
    with open(JSON_PATH, encoding="utf-8") as f:
        data = json.load(f)
    examples = data.get("examples", [])
    print(f"Loaded {len(examples)} corrections from JSON")

    # Generate embeddings
    settings = load_settings()
    svc = EmbeddingService(settings.openai, settings.rag)

    docs = []
    texts = [ex.get("embedding_text", ex["query"]) for ex in examples]

    print("Generating embeddings (batches of 50)...")
    all_embeddings = []
    for i in range(0, len(texts), 50):
        batch = texts[i : i + 50]
        embs = svc.get_embeddings_batch(batch)
        all_embeddings.extend(embs)
        print(f"  Embedded {i + len(batch)}/{len(texts)}")

    for ex, emb in zip(examples, all_embeddings):
        docs.append({
            "id": ex["id"].replace("-", "_"),  # AI Search IDs can't have hyphens in some contexts
            "persona": ex["persona"],
            "agent_type": ex["agent_type"],
            "category": ex.get("category", ""),
            "query": ex["query"],
            "bad_response": ex.get("bad_response", ""),
            "good_response": ex["good_response"],
            "policy_ref": ex.get("policy_ref", ""),
            "risk_level": ex.get("risk_level", ""),
            "corrected_by": ex.get("corrected_by", ""),
            "correction_date": ex.get("correction_date", ""),
            "embedding_text": ex.get("embedding_text", ""),
            "embedding": emb,
        })

    # Upload
    print("Uploading to AI Search...")
    indexed = upload_documents(docs)
    print(f"\nDone: {indexed}/{len(docs)} documents indexed in '{INDEX_NAME}'")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index corrections into Azure AI Search")
    parser.add_argument("--check", action="store_true", help="Check index status only")
    args = parser.parse_args()
    main(check_only=args.check)
