"""Compressed previews of case images (thumbnails and screen-size views).

Originals stay untouched as evidence; previews are a presentation cache stored next to
them as dot-files, like the localized analysis cache.
"""

from __future__ import annotations

import hashlib
from pathlib import PurePosixPath
from typing import Final, Optional

from app.utils import setup_logging

logger = setup_logging()

# Longest side in pixels and JPEG quality for each preview size.
PREVIEW_SIZES: Final = {
    "thumb": (480, 72),
    "screen": (1600, 82),
}
PREVIEWABLE_SUFFIXES: Final = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
PREVIEW_MEDIA_TYPE: Final = "image/jpeg"


def is_previewable(filename: str) -> bool:
    """Images can be previewed; internal dot-files (caches) never are."""
    path = PurePosixPath(filename)
    return not path.name.startswith(".") and path.suffix.lower() in PREVIEWABLE_SUFFIXES


def preview_cache_name(filename: str, size: str) -> str:
    """Storage name of a preview, independent of characters in the original name."""
    digest = hashlib.sha256(filename.encode("utf-8")).hexdigest()[:24]
    return f".preview-{size}-{digest}.jpg"


def preview_cache_names(filename: str) -> list[str]:
    return [preview_cache_name(filename, size) for size in PREVIEW_SIZES]


def render_preview(content: bytes, size: str) -> Optional[bytes]:
    """Resize to fit the preview box and re-encode as JPEG.

    Returns None when the image cannot be decoded or when the preview would not be
    smaller than the original, so callers can serve the original instead.
    """
    if size not in PREVIEW_SIZES:
        raise ValueError(f"Unknown preview size: {size}")
    box, quality = PREVIEW_SIZES[size]
    try:
        import fitz  # PyMuPDF

        pixmap = fitz.Pixmap(content)
        if pixmap.alpha:
            pixmap = fitz.Pixmap(pixmap, 0)
        if pixmap.colorspace is None or pixmap.colorspace.n not in (1, 3):
            pixmap = fitz.Pixmap(fitz.csRGB, pixmap)
        scale = min(1.0, box / max(pixmap.width, pixmap.height))
        if scale < 1.0:
            width = max(1, round(pixmap.width * scale))
            height = max(1, round(pixmap.height * scale))
            pixmap = fitz.Pixmap(pixmap, width, height)
        preview = pixmap.tobytes("jpg", jpg_quality=quality)
    except Exception as exc:  # unsupported or corrupt image: keep the original
        logger.info("Image preview unavailable (%s): %s", size, exc)
        return None
    return preview if len(preview) < len(content) else None


def content_etag(content: bytes) -> str:
    return '"' + hashlib.sha256(content).hexdigest()[:32] + '"'


def etag_matches(if_none_match: Optional[str], etag: str) -> bool:
    if not if_none_match:
        return False
    candidates = {value.strip().removeprefix("W/") for value in if_none_match.split(",")}
    return "*" in candidates or etag in candidates
