from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import ContentUnderstandingSettings, MarkItDownSettings
from .utils import setup_logging

logger = setup_logging()


class MarkItDownConversionError(Exception):
    pass


@dataclass
class MarkItDownConversionResult:
    markdown: str
    pages: list[dict[str, Any]]
    fields: dict[str, Any] = field(default_factory=dict)
    backend: str = "markitdown-local"
    analyzer_id: str | None = None


def is_markitdown_preferred(filename: str, settings: MarkItDownSettings) -> bool:
    """Return whether MarkItDown should be tried before direct CU for this file."""
    if not settings.enabled:
        return False
    ext = Path(filename.lower()).suffix
    return ext in settings.preferred_extensions


def convert_bytes_to_markdown(
    file_bytes: bytes,
    filename: str,
    markitdown_settings: MarkItDownSettings,
    content_understanding_settings: ContentUnderstandingSettings | None = None,
    analyzer_id: str | None = None,
) -> MarkItDownConversionResult:
    """Convert controlled file bytes to Markdown through MarkItDown.

    This intentionally uses convert_stream() instead of convert() so user input
    cannot be interpreted as a path or URL.
    """
    if not markitdown_settings.enabled:
        raise MarkItDownConversionError("MarkItDown is disabled")

    try:
        from markitdown import MarkItDown
        from markitdown._stream_info import StreamInfo
    except ImportError as exc:
        raise MarkItDownConversionError(
            "MarkItDown is not installed. Install markitdown[az-content-understanding]."
        ) from exc

    use_cu = markitdown_settings.mode == "cu" or markitdown_settings.use_content_understanding
    kwargs: dict[str, Any] = {"enable_plugins": False}
    backend = "markitdown-local"

    if use_cu:
        if not content_understanding_settings or not content_understanding_settings.endpoint:
            raise MarkItDownConversionError(
                "MarkItDown CU mode requires AZURE_CONTENT_UNDERSTANDING_ENDPOINT"
            )
        kwargs["cu_endpoint"] = content_understanding_settings.endpoint
        if analyzer_id:
            kwargs["cu_analyzer_id"] = analyzer_id
        credential = _build_cu_credential(content_understanding_settings)
        if credential is not None:
            kwargs["cu_credential"] = credential
        backend = "markitdown-content-understanding"

    stream = io.BytesIO(file_bytes)
    stream_info = StreamInfo(filename=filename, extension=Path(filename).suffix.lower())

    try:
        converter = MarkItDown(**kwargs)
        result = converter.convert_stream(stream, stream_info=stream_info)
    except Exception as exc:
        raise MarkItDownConversionError(
            f"MarkItDown conversion failed for {filename}: {exc}"
        ) from exc

    markdown = (
        getattr(result, "markdown", None) or getattr(result, "text_content", "") or ""
    ).strip()
    if not markdown:
        raise MarkItDownConversionError(f"MarkItDown returned empty markdown for {filename}")

    fields = extract_front_matter_fields(markdown)
    pages = split_markdown_pages(
        markdown, filename=filename, backend=backend, analyzer_id=analyzer_id
    )
    logger.info(
        "MarkItDown converted %s with backend=%s, chars=%d, fields=%d",
        filename,
        backend,
        len(markdown),
        len(fields),
    )

    return MarkItDownConversionResult(
        markdown=markdown,
        pages=pages,
        fields=fields,
        backend=backend,
        analyzer_id=analyzer_id,
    )


def _build_cu_credential(settings: ContentUnderstandingSettings) -> Any | None:
    if settings.use_azure_ad:
        try:
            from azure.identity import DefaultAzureCredential
        except ImportError as exc:
            raise MarkItDownConversionError(
                "azure-identity is required for MarkItDown CU mode"
            ) from exc
        return DefaultAzureCredential()

    if settings.api_key:
        try:
            from azure.core.credentials import AzureKeyCredential
        except ImportError as exc:
            raise MarkItDownConversionError(
                "azure-core is required for key-based MarkItDown CU mode"
            ) from exc
        return AzureKeyCredential(settings.api_key)
    return None


def split_markdown_pages(
    markdown: str,
    filename: str,
    backend: str,
    analyzer_id: str | None,
) -> list[dict[str, Any]]:
    """Split MarkItDown markdown into page-like chunks for the existing source UI."""
    markers = ("<!-- page ", "<!-- Page ")
    pages: list[dict[str, Any]] = []
    if any(marker in markdown for marker in markers):
        current: list[str] = []
        page_number = 1
        for line in markdown.splitlines():
            if line.strip().lower().startswith("<!-- page ") and current:
                pages.append(
                    _page_dict(filename, page_number, "\n".join(current), backend, analyzer_id)
                )
                page_number += 1
                current = [line]
            else:
                current.append(line)
        if current:
            pages.append(
                _page_dict(filename, page_number, "\n".join(current), backend, analyzer_id)
            )

    if not pages:
        pages.append(_page_dict(filename, 1, markdown, backend, analyzer_id))
    return pages


def _page_dict(
    filename: str,
    page_number: int,
    markdown: str,
    backend: str,
    analyzer_id: str | None,
) -> dict[str, Any]:
    return {
        "file": filename,
        "page_number": page_number,
        "markdown": markdown.strip(),
        "extraction_backend": backend,
        "analyzer_id": analyzer_id,
    }


def extract_front_matter_fields(markdown: str) -> dict[str, Any]:
    """Parse simple MarkItDown CU YAML front matter fields without adding PyYAML."""
    lines = markdown.splitlines()
    if len(lines) < 3 or lines[0].strip() != "---":
        return {}

    end = next((idx for idx, line in enumerate(lines[1:], start=1) if line.strip() == "---"), -1)
    if end <= 1:
        return {}

    fields: dict[str, Any] = {}
    in_fields = False
    current_field: str | None = None
    for line in lines[1:end]:
        stripped = line.rstrip()
        if stripped == "fields:":
            in_fields = True
            continue
        if in_fields and stripped and not line.startswith(" "):
            break
        if in_fields and ":" in stripped:
            indent = len(line) - len(line.lstrip(" "))
            key, value = stripped.split(":", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            if not key:
                continue
            if indent <= 2 and key not in {"value", "content", "text", "confidence", "source"}:
                current_field = key
                fields[key] = value
                continue
            if current_field and key in {"value", "content", "text"} and value:
                fields[current_field] = value
    return fields
