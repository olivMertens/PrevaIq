"""Mistral Document AI OCR client — fallback for Azure Content Understanding.

Provides reliable fallback extraction when CU fails, with format validation
to ensure compatibility with extract_markdown_from_result() and downstream LLM/UI.

Features:
- Validates Mistral result format before returning
- Auto-chunks large PDFs (>30 pages)
- Retries with exponential backoff
- Returns CU-compatible format for seamless integration
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

try:
    import httpx
except ImportError:
    httpx = None

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

logger = logging.getLogger(__name__)


class MistralOCRError(Exception):
    """Raised when Mistral OCR processing fails."""
    pass


class MistralSettings:
    """Mistral Document AI configuration."""

    def __init__(
        self,
        endpoint: str | None = None,
        api_key: str | None = None,
        deployment: str | None = None,
        api_version: str = "2024-05-01-preview",
    ):
        self.endpoint = (endpoint or os.getenv("MISTRAL_ENDPOINT", "")).rstrip("/")
        self.api_key = api_key or os.getenv("MISTRAL_API_KEY", "")
        self.deployment = deployment or os.getenv(
            "MISTRAL_DEPLOYMENT_2512", "mistral-document-ai-2512"
        )
        self.api_version = api_version

    def validate(self) -> list[str]:
        """Validate configuration. Returns list of errors (empty if valid)."""
        errors = []
        if not self.endpoint:
            errors.append("MISTRAL_ENDPOINT not set")
        if not self.api_key:
            errors.append("MISTRAL_API_KEY not set")
        if not self.deployment:
            errors.append("MISTRAL_DEPLOYMENT_2512 not set")
        return errors


def validate_mistral_result(result: Dict[str, Any]) -> list[str]:
    """Validate Mistral OCR result format.

    Ensures result has required fields for downstream processing:
    - markdown (required)
    - pages (required)
    - images (optional)

    Args:
        result: Result dict from extract_with_mistral()

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Check top-level structure
    if not isinstance(result, dict):
        errors.append(f"Result must be dict, got {type(result)}")
        return errors

    # Validate markdown field (required by extract_markdown_from_result)
    if "markdown" not in result:
        errors.append('Missing required field: "markdown"')
    elif not isinstance(result["markdown"], str):
        errors.append(f'Field "markdown" must be str, got {type(result["markdown"])}')
    elif len(result["markdown"]) == 0:
        errors.append('Field "markdown" is empty')

    # Validate pages field (required by extract_markdown_from_result)
    if "pages" not in result:
        errors.append('Missing required field: "pages"')
    elif not isinstance(result["pages"], list):
        errors.append(f'Field "pages" must be list, got {type(result["pages"])}')
    elif len(result["pages"]) == 0:
        errors.append('Field "pages" is empty')
    else:
        # Validate each page
        for i, page in enumerate(result["pages"]):
            if not isinstance(page, dict):
                errors.append(f'Page {i} must be dict, got {type(page)}')
            else:
                if "page_index" not in page and "page_number" not in page:
                    errors.append(
                        f'Page {i} missing "page_index" or "page_number"'
                    )
                if "markdown" not in page:
                    errors.append(f'Page {i} missing "markdown" field')
                elif not isinstance(page["markdown"], str):
                    errors.append(
                        f'Page {i} "markdown" must be str, '
                        f'got {type(page["markdown"])}'
                    )

    # Validate usage field (optional but informative)
    if "usage" in result and not isinstance(result["usage"], dict):
        errors.append(f'Field "usage" must be dict, got {type(result["usage"])}')

    return errors


async def extract_with_mistral(
    file_bytes: bytes,
    filename: str,
    settings: MistralSettings | None = None,
    media_type: str = "document",
    include_images: bool = True,
    table_format: str | None = "markdown",
    extract_header: bool = True,
    extract_footer: bool = True,
    max_retries: int = 3,
    retry_backoff: float = 1.5,
) -> Dict[str, Any]:
    """Extract content from document/image using Mistral Document AI v25.12.

    Args:
        file_bytes: Raw file content
        filename: Original filename
        settings: Mistral configuration (loads from env if None)
        media_type: 'document', 'image', or 'video'
        include_images: Include base64 image data in response
        table_format: 'markdown', 'html', or None
        extract_header: Extract page headers separately
        extract_footer: Extract page footers separately
        max_retries: Number of retry attempts
        retry_backoff: Exponential backoff multiplier

    Returns:
        Dict with:
        - markdown: Combined markdown from all pages
        - pages: List of page data with markdown, images, tables
        - images: All extracted images with base64
        - usage: Token usage (if available)

    Raises:
        MistralOCRError: If extraction fails or result format invalid
    """
    if httpx is None:
        raise MistralOCRError("httpx is required. Install with: pip install httpx")

    if settings is None:
        settings = MistralSettings()

    # Validate settings
    errors = settings.validate()
    if errors:
        raise MistralOCRError(f"Invalid Mistral configuration: {'; '.join(errors)}")

    # Check if PDF needs chunking
    chunks_b64: list[str] = []
    if filename.lower().endswith(".pdf") and len(file_bytes) > 0:
        if fitz is None:
            logger.warning(
                "PyMuPDF (fitz) not available; cannot check PDF size. Sending as single chunk."
            )
            chunks_b64 = [base64.b64encode(file_bytes).decode()]
        else:
            try:
                doc = fitz.open(stream=file_bytes, filetype="pdf")
                page_count = len(doc)
                doc.close()

                if page_count > 30:
                    logger.info(
                        f"PDF {filename} has {page_count} pages; "
                        f"chunking into 30-page segments"
                    )
                    chunks_b64 = _chunk_pdf_bytes(file_bytes, max_pages=30)
                else:
                    chunks_b64 = [base64.b64encode(file_bytes).decode()]
            except Exception as e:
                logger.warning(
                    f"Failed to check PDF page count: {e}. Sending as single chunk."
                )
                chunks_b64 = [base64.b64encode(file_bytes).decode()]
    else:
        chunks_b64 = [base64.b64encode(file_bytes).decode()]

    logger.info(
        f"Processing {filename} ({media_type}) with Mistral — "
        f"{len(chunks_b64)} chunk(s)"
    )

    # Build request URL
    endpoint = settings.endpoint.rstrip("/")
    url = f"{endpoint}/providers/mistral/azure/ocr?api-version={settings.api_version}"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.api_key}",
    }

    all_pages: list[Dict[str, Any]] = []
    all_images: list[Dict[str, Any]] = []
    all_markdown_parts: list[str] = []
    total_usage: Dict[str, int] = {}
    last_error: Exception | None = None

    async with httpx.AsyncClient(timeout=300) as client:
        for chunk_idx, chunk_b64 in enumerate(chunks_b64):
            # Build Mistral v25.12 request payload
            payload = {
                "model": settings.deployment,
                "document": {
                    "type": "document_url",
                    "document_url": f"data:application/pdf;base64,{chunk_b64}",
                },
                "include_image_base64": include_images,
            }

            # Add v25.12 optional features
            if table_format:
                payload["table_format"] = table_format
            if extract_header:
                payload["extract_header"] = True
            if extract_footer:
                payload["extract_footer"] = True

            # Retry loop for this chunk
            for attempt in range(1, max_retries + 1):
                try:
                    logger.info(
                        f"Mistral OCR chunk {chunk_idx + 1}/{len(chunks_b64)} "
                        f"attempt {attempt}/{max_retries}"
                    )

                    resp = await client.post(url, json=payload, headers=headers)
                    resp.raise_for_status()

                    result = resp.json()

                    # Extract pages and usage
                    pages_raw = result.get("pages", [])
                    usage = result.get("usage", {})

                    for k, v in usage.items():
                        total_usage[k] = total_usage.get(k, 0) + v

                    # Process pages
                    for pg_idx, page in enumerate(pages_raw):
                        global_idx = len(all_pages)
                        page_md = page.get("markdown", "")

                        page_data = {
                            "page_index": global_idx,
                            "page_number": global_idx + 1,  # 1-indexed for UI
                            "markdown": page_md,
                            "images": page.get("images", []),
                            "tables": page.get("tables", []),
                            "header": page.get("header"),
                            "footer": page.get("footer"),
                        }
                        all_pages.append(page_data)

                        # Collect images
                        for img in page.get("images", []):
                            img["page_index"] = global_idx
                            all_images.append(img)

                        all_markdown_parts.append(page_md)

                    logger.info(
                        f"Chunk {chunk_idx + 1} completed: "
                        f"{len(pages_raw)} pages extracted"
                    )
                    last_error = None
                    break  # Success, move to next chunk

                except httpx.HTTPStatusError as e:
                    last_error = e
                    status = e.response.status_code

                    if status in (429, 500, 502, 503, 504):
                        wait = retry_backoff ** attempt
                        logger.warning(
                            f"Mistral OCR transient error {status}, "
                            f"retrying in {wait}s..."
                        )
                        if attempt < max_retries:
                            await asyncio.sleep(wait)
                    else:
                        # Non-retryable error
                        try:
                            error_detail = e.response.json()
                        except Exception:
                            error_detail = e.response.text

                        logger.error(
                            f"Mistral OCR non-retryable error {status}: {error_detail}"
                        )
                        raise

                except httpx.TimeoutException as e:
                    last_error = e
                    wait = retry_backoff ** attempt
                    logger.warning(f"Mistral OCR timeout, retrying in {wait}s...")
                    if attempt < max_retries:
                        await asyncio.sleep(wait)

                except Exception as e:
                    last_error = e
                    logger.error(f"Mistral OCR unexpected error: {e}")
                    raise

            if last_error is not None:
                raise last_error

    # Combine all markdown
    combined_md = "\n\n".join(all_markdown_parts)

    # Build result in same format as extract_markdown_from_result()
    result = {
        "markdown": combined_md,
        "pages": all_pages,
        "images": all_images,
        "usage": total_usage,
    }

    # Validate result format before returning
    format_errors = validate_mistral_result(result)
    if format_errors:
        logger.error(f"Mistral result format invalid: {format_errors}")
        # Still return it, but log the issue
        logger.warning(
            f"Proceeding with invalid Mistral result (LLM may receive degraded input)"
        )

    return result


def _chunk_pdf_bytes(pdf_data: bytes, max_pages: int = 30) -> list[str]:
    """Split PDF into base64-encoded chunks of ≤max_pages.

    Args:
        pdf_data: Raw PDF bytes
        max_pages: Maximum pages per chunk

    Returns:
        List of base64-encoded PDF chunks
    """
    if fitz is None:
        raise MistralOCRError("PyMuPDF (fitz) is required for PDF chunking")

    doc = fitz.open(stream=pdf_data, filetype="pdf")
    chunks: list[str] = []

    for start_page in range(0, len(doc), max_pages):
        end_page = min(start_page + max_pages, len(doc))

        # Create sub-document with pages [start, end)
        sub_doc = fitz.open()
        sub_doc.insert_pdf(doc, from_page=start_page, to_page=end_page - 1)

        chunk_bytes = sub_doc.write()
        chunk_b64 = base64.b64encode(chunk_bytes).decode()
        chunks.append(chunk_b64)

        sub_doc.close()

    doc.close()
    return chunks


async def extract_document_with_mistral(
    file_bytes: bytes,
    filename: str,
    settings: MistralSettings | None = None,
) -> Dict[str, Any]:
    """Extract document/PDF using Mistral (convenience function)."""
    return await extract_with_mistral(
        file_bytes,
        filename,
        settings=settings,
        media_type="document",
        include_images=True,
        table_format="markdown",
        extract_header=True,
        extract_footer=True,
    )


async def extract_image_with_mistral(
    file_bytes: bytes,
    filename: str,
    settings: MistralSettings | None = None,
) -> Dict[str, Any]:
    """Extract image using Mistral (convenience function)."""
    return await extract_with_mistral(
        file_bytes,
        filename,
        settings=settings,
        media_type="image",
        include_images=True,
    )


if __name__ == "__main__":
    # CLI test
    import sys

    if len(sys.argv) < 2:
        print("Usage: python mistral_ocr_client.py <file_path>")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"File not found: {file_path}")
        sys.exit(1)

    settings = MistralSettings()
    errors = settings.validate()
    if errors:
        print(f"Configuration errors: {errors}")
        sys.exit(1)

    print(f"Extracting {file_path.name} using Mistral Document AI...")

    result = asyncio.run(
        extract_document_with_mistral(
            file_path.read_bytes(),
            file_path.name,
            settings=settings,
        )
    )

    # Validate result
    format_errors = validate_mistral_result(result)
    if format_errors:
        print(f"\n❌ Format validation errors: {format_errors}")
        sys.exit(1)

    print(f"\n✅ Extraction complete:")
    print(f"  Pages: {len(result['pages'])}")
    print(f"  Images: {len(result['images'])}")
    print(f"  Markdown length: {len(result['markdown'])} chars")
    print(f"  Usage: {result['usage']}")

    # Write markdown
    out_md = file_path.stem + "_mistral.md"
    Path(out_md).write_text(result["markdown"])
    print(f"\n✅ Markdown saved to {out_md}")
