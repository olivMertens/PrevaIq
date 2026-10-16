#!/usr/bin/env python3
"""
CLI script for indexing PDF policy documents into PostgreSQL for RAG.

Uses Azure Content Understanding or MarkItDown to extract structured Markdown
from PDFs, then embeds semantic chunks via Azure OpenAI and stores them in the
same policy_chunks tables used by the JSON policy indexer.

Pipeline:
  1. Send PDF to Azure Content Understanding (prebuilt-documentSearch)
  2. Parse the returned markdown into semantic sections (headings, paragraphs, tables)
  3. Chunk sections with overlap for retrieval quality
  4. Generate embeddings via Azure OpenAI (text-embedding-3-small)
  5. Store as PolicyChunk objects in PostgreSQL with pgvector

Usage:
    # Index all PDFs in assets/pdf/
    python scripts/index_pdf_policies.py

    # Index a specific PDF
    python scripts/index_pdf_policies.py --file "assets/pdf/Conditions Gen Auto.pdf"

    # Force reindex (delete existing chunks first)
    python scripts/index_pdf_policies.py --force

    # Use MarkItDown conversion path with CU/local routing from MARKITDOWN_* settings
    python scripts/index_pdf_policies.py --markitdown

    # Use PyMuPDF fallback (if Content Understanding not provisioned yet)
    python scripts/index_pdf_policies.py --local
"""

import asyncio
import argparse
import hashlib
import re
import sys
import time
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import load_settings
from app.rag.chunker import PolicyChunk
from app.rag.embeddings import EmbeddingService
from app.markitdown_service import MarkItDownConversionError, convert_bytes_to_markdown
from app.utils import setup_logging

logger = setup_logging()

# ---------------------------------------------------------------------------
# Category → persona table routing
# Each policy PDF must be indexed into the table that its persona searches.
# ---------------------------------------------------------------------------
CATEGORY_TABLE_MAP = {
    "automotive": "claim_policy_chunks",  # Sinistres Auto persona
    "life_health": "health_claims_policy_chunks",  # Sinistres Santé persona
    "property_casualty": "policy_chunks",  # Souscription persona (default)
    "general": "policy_chunks",  # Fallback
}

# ---------------------------------------------------------------------------
# PDF category detection from filename
# ---------------------------------------------------------------------------
PDF_CATEGORY_MAP = {
    "habitation": {"category": "property_casualty", "subcategory": "habitation"},
    "santé": {"category": "life_health", "subcategory": "complementaire_sante"},
    "sante": {"category": "life_health", "subcategory": "complementaire_sante"},
    "complémentaire": {"category": "life_health", "subcategory": "complementaire_sante"},
    "flotte auto": {"category": "automotive", "subcategory": "flotte_auto"},
    "flotte": {"category": "automotive", "subcategory": "flotte_auto"},
    "auto": {"category": "automotive", "subcategory": "auto"},
}


def detect_category(filename: str) -> dict[str, str]:
    """Detect policy category from filename."""
    lower = filename.lower()
    # Check longer keys first to avoid 'auto' matching before 'flotte auto'
    for key in sorted(PDF_CATEGORY_MAP.keys(), key=len, reverse=True):
        if key in lower:
            return PDF_CATEGORY_MAP[key]
    return {"category": "general", "subcategory": "unknown"}


def make_policy_id(filename: str) -> str:
    """Generate a stable policy ID from filename."""
    return re.sub(r"[^a-zA-Z0-9]", "-", Path(filename).stem).strip("-").lower()


# ---------------------------------------------------------------------------
# Document Intelligence extraction (primary path)
# ---------------------------------------------------------------------------
def extract_with_document_intelligence(
    pdf_path: Path,
    settings: Any,
) -> str:
    """
    Extract structured markdown from PDF using Azure Content Understanding.

    The prebuilt-documentSearch analyzer returns high-quality markdown with
    headings, tables, lists, and paragraph structure preserved.

    Returns:
        Markdown string of the full document.
    """
    from app.content_understanding_client import analyze_document

    logger.info(f"   Sending to Document Intelligence: {pdf_path.name}")
    file_bytes = pdf_path.read_bytes()
    result = analyze_document(
        settings.content_understanding,
        file_path=str(pdf_path),
        file_bytes=file_bytes,
        output_markdown=True,
    )

    # Extract markdown from the result
    # Content Understanding returns result.contents[].markdown or result.result.contents
    markdown = ""
    if "result" in result:
        r = result["result"]
        # Try contents array (prebuilt-documentSearch returns this)
        if "contents" in r:
            for content in r["contents"]:
                if "markdown" in content:
                    markdown += content["markdown"] + "\n\n"
                elif "text" in content:
                    markdown += content["text"] + "\n\n"
        # Fallback to analyzedDocument markdown
        elif "analyzedDocument" in r and "markdown" in r["analyzedDocument"]:
            markdown = r["analyzedDocument"]["markdown"]
    # Another possible shape
    elif "contents" in result:
        for content in result["contents"]:
            md = content.get("markdown") or content.get("text", "")
            markdown += md + "\n\n"

    if not markdown.strip():
        logger.warning("   No markdown extracted, falling back to raw text fields")
        # Last resort: concat any text fields found
        markdown = _extract_text_fallback(result)

    logger.info(f"   Extracted {len(markdown):,} chars of structured markdown")
    return markdown


def _extract_text_fallback(result: dict) -> str:
    """Walk the result tree and collect any text content."""
    texts = []

    def _walk(obj: Any) -> None:
        if isinstance(obj, dict):
            for key in ("text", "content", "markdown", "value"):
                if key in obj and isinstance(obj[key], str) and len(obj[key]) > 20:
                    texts.append(obj[key])
            for v in obj.values():
                _walk(v)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item)

    _walk(result)
    return "\n\n".join(texts)


# ---------------------------------------------------------------------------
# Local PyMuPDF extraction (fallback)
# ---------------------------------------------------------------------------
# Typographic ligatures break keyword search ("ﬂotte" != "flotte")
_LIGATURES = str.maketrans({
    "\ufb00": "ff", "\ufb01": "fi", "\ufb02": "fl", "\ufb03": "ffi", "\ufb04": "ffl",
    "\ufb05": "st", "\ufb06": "st",
})


def extract_with_pymupdf(pdf_path: Path) -> str:
    """
    Extract text from PDF using PyMuPDF (local, no Azure required).
    Lower quality than Document Intelligence — no table/heading structure.
    """
    import fitz  # PyMuPDF

    logger.info(f"   Extracting with PyMuPDF (local): {pdf_path.name}")
    doc = fitz.open(str(pdf_path))
    pages = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text").strip()
        if text:
            pages.append(f"## Page {page_num + 1}\n\n{text}")
    doc.close()

    markdown = "\n\n".join(pages)
    logger.info(f"   Extracted {len(markdown):,} chars from {len(pages)} pages")
    return markdown


def extract_with_markitdown(pdf_path: Path, settings: Any) -> tuple[str, dict[str, Any]]:
    """Extract layout-aware Markdown through MarkItDown."""
    logger.info(f"   Extracting with MarkItDown: {pdf_path.name}")
    result = convert_bytes_to_markdown(
        pdf_path.read_bytes(),
        pdf_path.name,
        settings.markitdown,
        content_understanding_settings=settings.content_understanding,
        analyzer_id=(
            settings.content_understanding.analyzer_id
            if settings.markitdown.use_content_understanding
            else None
        ),
    )
    metadata = {
        "extraction_backend": result.backend,
        "analyzer_id": result.analyzer_id,
        "markitdown_mode": settings.markitdown.mode,
        "markitdown_use_content_understanding": settings.markitdown.use_content_understanding,
        "fields": result.fields,
        "page_count": len(result.pages),
    }
    logger.info(f"   Extracted {len(result.markdown):,} chars via MarkItDown")
    return result.markdown, metadata


# ---------------------------------------------------------------------------
# Markdown → semantic chunks
# ---------------------------------------------------------------------------
def chunk_markdown(
    markdown: str,
    chunk_size: int = 1500,
    overlap: int = 200,
) -> list[dict[str, Any]]:
    """
    Split structured markdown into semantic chunks for embedding.

    Strategy:
    1. Split on heading boundaries (##, ###) to preserve section context
    2. If a section exceeds chunk_size, split at paragraph breaks
    3. Keep overlap between chunks for retrieval continuity
    4. Prepend the current heading hierarchy to each chunk for context

    Returns:
        List of chunk dicts: {chunk_index, text, section_heading, char_count}
    """
    # Split into sections by headings
    sections = _split_by_headings(markdown)

    chunks: list[dict[str, Any]] = []
    idx = 0

    for section in sections:
        heading = section["heading"]
        body = section["body"].strip()
        if not body or len(body) < 30:
            continue

        # If section fits in one chunk, keep it together
        if len(body) <= chunk_size:
            text = f"{heading}\n\n{body}" if heading else body
            chunks.append(
                {
                    "chunk_index": idx,
                    "text": text.strip(),
                    "section_heading": heading,
                    "char_count": len(text.strip()),
                }
            )
            idx += 1
        else:
            # Split long sections at paragraph boundaries
            paragraphs = re.split(r"\n\s*\n", body)
            current = ""
            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue

                if len(current) + len(para) + 2 > chunk_size and current:
                    text = f"{heading}\n\n{current}" if heading else current
                    chunks.append(
                        {
                            "chunk_index": idx,
                            "text": text.strip(),
                            "section_heading": heading,
                            "char_count": len(text.strip()),
                        }
                    )
                    idx += 1
                    # Keep overlap from the end of current chunk
                    if overlap > 0 and len(current) > overlap:
                        current = current[-overlap:]
                    else:
                        current = ""

                current = f"{current}\n\n{para}" if current else para

            # Flush remaining
            if current.strip() and len(current.strip()) >= 30:
                text = f"{heading}\n\n{current}" if heading else current
                chunks.append(
                    {
                        "chunk_index": idx,
                        "text": text.strip(),
                        "section_heading": heading,
                        "char_count": len(text.strip()),
                    }
                )
                idx += 1

    return chunks


def _split_by_headings(markdown: str) -> list[dict[str, str]]:
    """Split markdown by heading lines (## or ###), preserving hierarchy."""
    lines = markdown.split("\n")
    sections: list[dict[str, str]] = []
    current_heading = ""
    current_body_lines: list[str] = []

    for line in lines:
        if re.match(r"^#{1,4}\s+", line):
            # Save previous section
            if current_body_lines:
                sections.append(
                    {
                        "heading": current_heading,
                        "body": "\n".join(current_body_lines),
                    }
                )
            current_heading = line.strip()
            current_body_lines = []
        else:
            current_body_lines.append(line)

    # Flush last section
    if current_body_lines:
        sections.append(
            {
                "heading": current_heading,
                "body": "\n".join(current_body_lines),
            }
        )

    # If no headings were found, treat the entire document as one section
    if not sections and markdown.strip():
        sections.append({"heading": "", "body": markdown})

    return sections


# ---------------------------------------------------------------------------
# Embedding + storage
# ---------------------------------------------------------------------------
def compute_content_hash(text: str) -> str:
    """SHA-256 hash prefix for deduplication."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def build_policy_chunks(
    chunks: list[dict[str, Any]],
    policy_id: str,
    policy_name: str,
    category: str,
    subcategory: str,
    embeddings: list[list[float]],
    source_metadata: dict[str, Any] | None = None,
) -> list[PolicyChunk]:
    """Convert raw chunks + embeddings into PolicyChunk objects.

    Returns PolicyChunk which is compatible with both policy_chunks and
    claim_policy_chunks tables (the claims table has extra nullable columns).
    """
    result: list[PolicyChunk] = []
    source_metadata = source_metadata or {}
    for i, chunk in enumerate(chunks):
        pc = PolicyChunk(
            policy_id=policy_id,
            policy_version="1.0",
            policy_name=policy_name,
            chunk_type="pdf_section",
            chunk_sequence=i,
            category=category,
            subcategory=subcategory,
            criteria_id=f"chunk-{chunk['chunk_index']}",
            risk_level=None,
            action_recommendation=None,
            content=chunk["text"],
            content_hash=compute_content_hash(chunk["text"]),
            token_count=chunk["char_count"] // 4,
            metadata={
                "source": source_metadata.get("extraction_backend", "content-understanding"),
                "source_file": policy_name,
                "section_heading": chunk.get("section_heading", ""),
                "language": "fr",
                "analyzer_id": source_metadata.get("analyzer_id"),
                "content_understanding_api_version": source_metadata.get(
                    "content_understanding_api_version"
                ),
                "markitdown_mode": source_metadata.get("markitdown_mode"),
                "markitdown_use_content_understanding": source_metadata.get(
                    "markitdown_use_content_understanding"
                ),
                "field_names": sorted((source_metadata.get("fields") or {}).keys()),
            },
            embedding=embeddings[i] if i < len(embeddings) else None,
        )
        result.append(pc)
    return result


def get_target_table(category: str, schema: str = "workbenchiq") -> str:
    """Return the fully-qualified table name for a PDF's category."""
    table = CATEGORY_TABLE_MAP.get(category, "policy_chunks")
    return f"{schema}.{table}"


async def _store_chunks_to_table(
    chunks: list[PolicyChunk],
    target_table: str,
    category: str,
    brand: str = "PrevaIQ",
) -> int:
    """
    Store chunks in the correct persona table.

    The claims tables (claim_policy_chunks, health_claims_policy_chunks) have
    extra columns (severity, liability_determination) vs policy_chunks.
    We use a query that works for both schemas by including these as NULLs.
    """
    from app.database.pool import get_pool

    pool = await get_pool()

    is_claims_table = "claim" in target_table or "health" in target_table

    if is_claims_table:
        # Claims table schema — includes severity + liability_determination
        insert_query = f"""
            INSERT INTO {target_table} (
                policy_id, policy_version, policy_name,
                chunk_type, chunk_sequence, category, subcategory,
                criteria_id, severity, risk_level, liability_determination,
                action_recommendation, content, content_hash, token_count,
                embedding, embedding_model, metadata, brand
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11,
                $12, $13, $14, $15, $16::vector, $17, $18, $19
            )
            ON CONFLICT (policy_id, chunk_type, COALESCE(criteria_id, ''), content_hash, brand)
            DO UPDATE SET
                content = EXCLUDED.content,
                embedding = EXCLUDED.embedding,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
        """
    else:
        # Standard policy_chunks table schema
        insert_query = f"""
            INSERT INTO {target_table} (
                policy_id, policy_version, policy_name,
                chunk_type, chunk_sequence, category, subcategory,
                criteria_id, risk_level, action_recommendation,
                content, content_hash, token_count,
                embedding, embedding_model, metadata, brand
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14::vector, $15, $16, $17
            )
            ON CONFLICT (policy_id, chunk_type, COALESCE(criteria_id, ''), content_hash, brand)
            DO UPDATE SET
                content = EXCLUDED.content,
                embedding = EXCLUDED.embedding,
                metadata = EXCLUDED.metadata,
                updated_at = NOW()
        """

    import json as _json

    def _vec_str(embedding) -> str:
        """Format embedding list as pgvector string '[0.1,0.2,...]'."""
        if isinstance(embedding, str):
            return embedding
        # Handle nested list [[float, ...]]
        if (
            isinstance(embedding, (list, tuple))
            and len(embedding) == 1
            and isinstance(embedding[0], (list, tuple))
        ):
            embedding = embedding[0]
        # Handle list of single-char strings (bug: list(str(list)))
        if (
            isinstance(embedding, (list, tuple))
            and len(embedding) > 10
            and isinstance(embedding[0], str)
            and len(embedding[0]) == 1
        ):
            return "".join(embedding)
        return "[" + ",".join(str(f) for f in embedding) + "]"

    stored = 0
    async with pool.acquire() as conn:
        for chunk in chunks:
            if chunk.embedding is None:
                continue
            meta_json = _json.dumps(chunk.metadata) if chunk.metadata else "{}"
            emb = chunk.embedding
            # Ensure flat list[float] — asyncpg vector codec handles encoding
            if (
                isinstance(emb, (list, tuple))
                and len(emb) == 1
                and isinstance(emb[0], (list, tuple))
            ):
                emb = emb[0]
            vec = emb  # pass raw list[float]; asyncpg codec encodes it correctly
            if is_claims_table:
                await conn.execute(
                    insert_query,
                    chunk.policy_id,
                    chunk.policy_version,
                    chunk.policy_name,
                    chunk.chunk_type,
                    chunk.chunk_sequence,
                    chunk.category,
                    chunk.subcategory,
                    chunk.criteria_id,
                    None,  # severity
                    chunk.risk_level,
                    None,  # liability_determination
                    chunk.action_recommendation,
                    chunk.content,
                    chunk.content_hash,
                    chunk.token_count,
                    vec,
                    "text-embedding-3-small",
                    meta_json,
                    brand,
                )
            else:
                await conn.execute(
                    insert_query,
                    chunk.policy_id,
                    chunk.policy_version,
                    chunk.policy_name,
                    chunk.chunk_type,
                    chunk.chunk_sequence,
                    chunk.category,
                    chunk.subcategory,
                    chunk.criteria_id,
                    chunk.risk_level,
                    chunk.action_recommendation,
                    chunk.content,
                    chunk.content_hash,
                    chunk.token_count,
                    vec,
                    "text-embedding-3-small",
                    meta_json,
                    brand,
                )
            stored += 1
    return stored


async def _ensure_tables(schema: str) -> None:
    """Ensure all persona policy chunk tables exist with pgvector."""
    from app.database.pool import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")

        # Check which tables already exist
        existing = await conn.fetch(
            "SELECT table_name FROM information_schema.tables " "WHERE table_schema = $1", schema
        )
        existing_names = {r["table_name"] for r in existing}

        # Standard policy_chunks table (underwriting + habitation)
        if "policy_chunks" not in existing_names:
            await conn.execute(f"""
                CREATE TABLE {schema}.policy_chunks (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    policy_id VARCHAR(50) NOT NULL,
                    policy_version VARCHAR(20),
                    policy_name VARCHAR(255) NOT NULL,
                    chunk_type VARCHAR(50) NOT NULL,
                    chunk_sequence INT NOT NULL DEFAULT 0,
                    category VARCHAR(100) NOT NULL,
                    subcategory VARCHAR(100),
                    criteria_id VARCHAR(50),
                    risk_level VARCHAR(50),
                    action_recommendation TEXT,
                    content TEXT NOT NULL,
                    content_hash VARCHAR(64) NOT NULL,
                    token_count INT NOT NULL DEFAULT 0,
                    embedding vector(1536),
                    embedding_model VARCHAR(100),
                    metadata JSONB DEFAULT '{{}}'::jsonb,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute(f"""
                CREATE UNIQUE INDEX policy_chunks_unique
                ON {schema}.policy_chunks
                (policy_id, chunk_type, COALESCE(criteria_id, ''), content_hash)
            """)

        # Claims tables (auto + health) — have extra severity + liability columns
        for tbl in ["claim_policy_chunks", "health_claims_policy_chunks"]:
            if tbl in existing_names:
                continue
            await conn.execute(f"""
                CREATE TABLE {schema}.{tbl} (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    policy_id VARCHAR(50) NOT NULL,
                    policy_version VARCHAR(20),
                    policy_name VARCHAR(255) NOT NULL,
                    chunk_type VARCHAR(50) NOT NULL,
                    chunk_sequence INT NOT NULL DEFAULT 0,
                    category VARCHAR(100) NOT NULL,
                    subcategory VARCHAR(100),
                    criteria_id VARCHAR(50),
                    severity VARCHAR(50),
                    risk_level VARCHAR(50),
                    liability_determination TEXT,
                    action_recommendation TEXT,
                    content TEXT NOT NULL,
                    content_hash VARCHAR(64) NOT NULL,
                    token_count INT NOT NULL DEFAULT 0,
                    embedding vector(1536),
                    embedding_model VARCHAR(100),
                    metadata JSONB DEFAULT '{{}}'::jsonb,
                    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
                )
            """)
            await conn.execute(f"""
                CREATE UNIQUE INDEX {tbl}_unique
                ON {schema}.{tbl}
                (policy_id, chunk_type, COALESCE(criteria_id, ''), content_hash)
            """)

        logger.info(f"   Tables verified in schema {schema}")


# ---------------------------------------------------------------------------
# Main indexing pipeline
# ---------------------------------------------------------------------------
async def index_pdf(
    pdf_path: Path,
    settings: Any,
    embedding_service: EmbeddingService,
    force: bool = False,
    chunk_size: int = 1500,
    use_local: bool = False,
    use_markitdown: bool = False,
    schema: str = "workbenchiq",
    brand: str = "PrevaIQ",
) -> dict[str, Any]:
    """Index a single PDF file into the correct persona table via Document Intelligence."""
    filename = pdf_path.name
    policy_id = make_policy_id(filename)
    cat_info = detect_category(filename)
    category = cat_info["category"]
    target_table = get_target_table(category, schema)

    logger.info(f"\n{'='*60}")
    logger.info(f"📄 Processing: {filename}")
    logger.info(f"   Policy ID : {policy_id}")
    logger.info(f"   Category  : {category} / {cat_info['subcategory']}")
    logger.info(f"   Target    : {target_table}")

    # Delete existing chunks if force reindex
    if force:
        from app.database.pool import get_pool

        pool = await get_pool()
        result = await pool.execute(
            f"DELETE FROM {target_table} WHERE policy_id = $1 AND brand = $2", policy_id, brand
        )
        deleted = int(result.split()[-1]) if result else 0
        if deleted:
            logger.info(f"   🗑️  Cleared {deleted} existing chunks")

    # Step 1: Extract structured content
    source_metadata: dict[str, Any] = {
        "source_file": filename,
        "content_understanding_api_version": settings.content_understanding.api_version,
    }
    if use_local:
        markdown = extract_with_pymupdf(pdf_path)
        source_metadata["extraction_backend"] = "pymupdf-local"
    elif use_markitdown:
        try:
            markdown, source_metadata = extract_with_markitdown(pdf_path, settings)
            source_metadata["content_understanding_api_version"] = (
                settings.content_understanding.api_version
            )
        except MarkItDownConversionError as exc:
            logger.warning(
                f"   MarkItDown failed for {pdf_path.name}, falling back to direct CU: {exc}"
            )
            markdown = extract_with_document_intelligence(pdf_path, settings)
            source_metadata["extraction_backend"] = "content-understanding"
            source_metadata["analyzer_id"] = settings.content_understanding.analyzer_id
    else:
        markdown = extract_with_document_intelligence(pdf_path, settings)
        source_metadata["extraction_backend"] = "content-understanding"
        source_metadata["analyzer_id"] = settings.content_understanding.analyzer_id

    markdown = (markdown or "").translate(_LIGATURES)
    if not markdown or len(markdown) < 50:
        logger.warning("   ⚠️  Insufficient content extracted, skipping")
        return {"file": filename, "policy_id": policy_id, "status": "skipped"}

    # Step 2: Chunk into semantic sections
    chunks = chunk_markdown(markdown, chunk_size=chunk_size)
    logger.info(f"   ✂️  Created {len(chunks)} semantic chunks")

    if not chunks:
        return {"file": filename, "policy_id": policy_id, "status": "no_chunks"}

    # Step 3: Generate embeddings (batch, with retry)
    texts = [c["text"] for c in chunks]
    logger.info(f"   🔢 Generating embeddings for {len(texts)} chunks...")

    # Process in batches of MAX_BATCH_SIZE
    all_embeddings: list[list[float]] = []
    batch_size = min(2, EmbeddingService.MAX_BATCH_SIZE)  # Small batches for low TPM
    for batch_start in range(0, len(texts), batch_size):
        batch = texts[batch_start : batch_start + batch_size]
        batch_embeddings = embedding_service.get_embeddings_batch(batch)
        all_embeddings.extend(batch_embeddings)
        if batch_start + batch_size < len(texts):
            logger.info(f"      Embedded {batch_start + len(batch)}/{len(texts)}...")
            import time

            time.sleep(5)  # Throttle to stay within TPM

    # Step 4: Build PolicyChunk objects and store in the correct table
    policy_chunks = build_policy_chunks(
        chunks,
        policy_id=policy_id,
        policy_name=filename,
        category=cat_info["category"],
        subcategory=cat_info["subcategory"],
        embeddings=all_embeddings,
        source_metadata=source_metadata,
    )

    stored = await _store_chunks_to_table(
        policy_chunks, target_table=target_table, category=category, brand=brand
    )
    logger.info(f"   ✅ Stored {stored} chunks in {target_table}")

    return {
        "file": filename,
        "policy_id": policy_id,
        "category": cat_info["category"],
        "subcategory": cat_info["subcategory"],
        "markdown_chars": len(markdown),
        "chunks": len(chunks),
        "stored": stored,
        "extraction_backend": source_metadata.get("extraction_backend"),
        "status": "ok",
    }


async def main():
    parser = argparse.ArgumentParser(
        description="Index PDF policy documents for RAG search",
    )
    parser.add_argument(
        "--dir",
        default="assets/pdf",
        help="Directory containing PDF files (default: assets/pdf)",
    )
    parser.add_argument(
        "--file",
        help="Index a single PDF file instead of a directory",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force reindex (delete existing chunks first)",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1500,
        help="Target chunk size in characters (default: 1500)",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use PyMuPDF locally instead of Azure Document Intelligence",
    )
    parser.add_argument(
        "--markitdown",
        action="store_true",
        help="Use MarkItDown conversion before chunking (uses MARKITDOWN_* settings)",
    )
    parser.add_argument(
        "--brand",
        default="PrevaIQ",
        help="Brand name for tenant isolation (default: PrevaIQ)",
    )
    args = parser.parse_args()

    # Load settings and init DB
    settings = load_settings()
    if settings.database.backend != "postgresql":
        logger.error("DATABASE_BACKEND must be 'postgresql' for RAG indexing")
        sys.exit(1)

    requires_content_understanding = not args.local and (
        not args.markitdown or settings.markitdown.use_content_understanding
    )
    if requires_content_understanding and not settings.content_understanding.endpoint:
        logger.error(
            "AZURE_CONTENT_UNDERSTANDING_ENDPOINT not set. "
            "Set it, use --local, or use --markitdown with MARKITDOWN_MODE=local."
        )
        sys.exit(1)

    from app.database.pool import init_pool

    await init_pool(settings.database)

    # Init embedding service
    embedding_service = EmbeddingService(settings.openai, settings.rag)
    schema = settings.database.schema or "workbenchiq"

    # Ensure all target tables exist (claims tables may not be created yet)
    await _ensure_tables(schema)

    # Collect PDFs
    if args.file:
        pdf_files = [Path(args.file)]
    else:
        pdf_dir = Path(args.dir)
        pdf_files = sorted(pdf_dir.glob("*.pdf"))

    if not pdf_files:
        logger.error(f"No PDF files found in {args.dir}")
        sys.exit(1)

    mode = (
        "PyMuPDF (local)"
        if args.local
        else "MarkItDown"
        if args.markitdown
        else "Azure Content Understanding"
    )

    logger.info("=" * 60)
    logger.info("WorkbenchIQ PDF Policy Indexer")
    logger.info(f"Mode        : {mode}")
    logger.info(f"PDFs        : {len(pdf_files)}")
    logger.info(f"Brand       : {args.brand}")
    logger.info(f"Chunk size  : {args.chunk_size} chars")
    logger.info(f"Force       : {args.force}")
    logger.info("=" * 60)

    start = time.time()
    results = []
    for pdf_path in pdf_files:
        if not pdf_path.exists():
            logger.error(f"File not found: {pdf_path}")
            continue
        result = await index_pdf(
            pdf_path,
            settings,
            embedding_service,
            force=args.force,
            chunk_size=args.chunk_size,
            use_local=args.local,
            use_markitdown=args.markitdown,
            schema=schema,
            brand=args.brand,
        )
        results.append(result)

    elapsed = time.time() - start

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("INDEXING COMPLETE")
    logger.info("=" * 60)
    ok_results = [r for r in results if r.get("status") == "ok"]
    total_chunks = sum(r.get("stored", 0) for r in ok_results)
    total_chars = sum(r.get("markdown_chars", 0) for r in ok_results)
    for r in results:
        status = r.get("status", "unknown")
        if status == "ok":
            logger.info(
                f"  ✅ {r['file']}: {r['markdown_chars']:,} chars → "
                f"{r['stored']} chunks ({r['category']}/{r['subcategory']})"
            )
        else:
            logger.info(f"  ⚠️  {r['file']}: {status}")

    logger.info(f"\nTotal: {len(ok_results)}/{len(results)} PDFs indexed")
    logger.info(f"       {total_chars:,} chars extracted → {total_chunks} chunks stored")
    logger.info(f"Time : {elapsed:.1f}s")


if __name__ == "__main__":
    asyncio.run(main())
