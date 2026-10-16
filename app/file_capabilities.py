from __future__ import annotations

from pathlib import Path
from typing import Any


DOCUMENT_EXTENSIONS = {
    ".pdf",
    ".tif",
    ".tiff",
    ".docx",
    ".xlsx",
    ".pptx",
    ".doc",
    ".xls",
    ".ppt",
    ".odt",
    ".ods",
    ".odp",
    ".txt",
    ".rtf",
    ".html",
    ".htm",
    ".md",
    ".eml",
    ".msg",
    ".xml",
    ".csv",
    ".json",
}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".jpe", ".png", ".bmp", ".heif", ".heic", ".gif", ".webp"}
VIDEO_EXTENSIONS = {".mp4", ".m4v", ".flv", ".wmv", ".asf", ".avi", ".mkv", ".mov", ".webm"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".wma", ".aac", ".amr", ".m4a", ".spx"}

ALL_SUPPORTED_EXTENSIONS = (
    DOCUMENT_EXTENSIONS | IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS
)

PERSONA_EXTENSION_GROUPS: dict[str, tuple[str, ...]] = {
    "underwriting": ("document", "image"),
    "life_health_claims": ("document", "image"),
    "automotive_claims": ("document", "image", "video"),
    "property_casualty_claims": ("document", "image", "video"),
    "habitation_claims": ("document", "image", "video"),
    "mortgage": ("document", "image"),
    "mortgage_underwriting": ("document", "image"),
    "customer360": ("document", "image"),
}

EXTENSIONS_BY_GROUP = {
    "document": DOCUMENT_EXTENSIONS,
    "image": IMAGE_EXTENSIONS,
    "video": VIDEO_EXTENSIONS,
    "audio": AUDIO_EXTENSIONS,
}


def detect_media_type(filename: str) -> str:
    """Detect media type from filename extension."""
    ext = Path(filename.lower()).suffix
    for media_type, extensions in EXTENSIONS_BY_GROUP.items():
        if ext in extensions:
            return media_type
    return "unknown"


def get_supported_extensions_for_persona(persona: str | None) -> set[str]:
    """Return supported extensions for a persona."""
    groups = PERSONA_EXTENSION_GROUPS.get(persona or "underwriting", ("document", "image"))
    extensions: set[str] = set()
    for group in groups:
        extensions.update(EXTENSIONS_BY_GROUP[group])
    return extensions


def is_supported_file(filename: str, persona: str | None = None) -> bool:
    """Return whether a file extension is supported for the persona."""
    ext = Path(filename.lower()).suffix
    if not ext:
        return False
    return ext in get_supported_extensions_for_persona(persona)


def get_file_capabilities(persona: str | None = None) -> dict[str, Any]:
    """Return UI/API-friendly file capability metadata."""
    extensions = sorted(get_supported_extensions_for_persona(persona))
    groups = {
        group: sorted(values)
        for group, values in EXTENSIONS_BY_GROUP.items()
        if set(values).intersection(extensions)
    }
    return {
        "persona": persona or "underwriting",
        "extensions": extensions,
        "all_extensions": extensions,
        "accept": ",".join(extensions),
        "groups": groups,
        "categories": groups,
    }
