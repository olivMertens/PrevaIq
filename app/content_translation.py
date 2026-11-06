"""On-demand translation of case content (page text, photo descriptions, batch summaries).

Source content keeps its own language as evidence; a translation is a presentation cache
keyed by the content hash and the target language, so it never goes stale silently.
"""

from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Final, Optional

from app.config import Settings
from app.languages import (
    SUPPORTED_LANGUAGES,
    base_language,
    language_instruction,
    language_name,
    require_language,
)
from app.openai_client import chat_completion
from app.storage import ApplicationMetadata, load_file, save_application_file
from app.utils import setup_logging

logger = setup_logging()

MAX_ITEMS_PER_REQUEST: Final = 8
MAX_TRANSLATABLE_CHARS: Final = 30_000
_MAX_WORKERS: Final = 4
# Bump when the prompt changes so cached translations are rebuilt.
_CACHE_VERSION: Final = "v2"

_STOPWORDS: Final = {
    "en": {
        "the",
        "and",
        "of",
        "to",
        "is",
        "with",
        "for",
        "this",
        "that",
        "are",
        "was",
        "on",
        "by",
        "be",
        "from",
        "it",
        "as",
        "at",
        "not",
        "or",
        "which",
        "has",
        "have",
        "were",
    },
    "fr": {
        "le",
        "la",
        "les",
        "du",
        "de",
        "et",
        "est",
        "une",
        "un",
        "pour",
        "avec",
        "dans",
        "sur",
        "par",
        "au",
        "aux",
        "pas",
        "qui",
        "que",
        "cette",
        "sont",
        "été",
        "ou",
        "ses",
    },
    "de": {
        "der",
        "die",
        "das",
        "und",
        "ist",
        "mit",
        "für",
        "von",
        "den",
        "dem",
        "ein",
        "eine",
        "nicht",
        "auf",
        "im",
        "zu",
        "bei",
        "wird",
        "sind",
        "auch",
        "oder",
        "aus",
        "sich",
    },
}
_WORD_RE: Final = re.compile(r"[a-zA-ZÀ-ÖØ-öø-ÿ]+")
_MARKUP_RE: Final = re.compile(r"<[^>]+>|https?://\S+|`[^`]*`")


def detect_language(text: str) -> Optional[str]:
    """Best-guess language of a text among the supported ones, None when unclear."""
    words = _WORD_RE.findall(_MARKUP_RE.sub(" ", text[:6000]).lower())
    hits = {
        lang: sum(1 for word in words if word in stopwords)
        for lang, stopwords in _STOPWORDS.items()
    }
    best = max(hits, key=hits.get)
    total = sum(hits.values())
    if hits[best] < 3 or hits[best] < 0.6 * total:
        return None
    return best


def _cache_name(text: str, target: str) -> str:
    digest = hashlib.sha256(f"{_CACHE_VERSION}|{target}|{text}".encode("utf-8")).hexdigest()[:32]
    return f".content-translation-{target}-{digest}.md"


def translate_markdown(settings: Settings, text: str, source: str, target: str) -> str:
    """Single bounded model call; raises on an empty, truncated or untranslated answer."""
    prompt = (
        f"Translate this insurance claim document from {language_name(source)} to "
        f"{language_name(target)}. Translate every heading, list label, bold or italic text "
        "and sentence. Return only the translated Markdown, with no preamble. Keep the "
        "Markdown and HTML structure exactly: headings, lists, tables, line breaks, HTML "
        "tags and attributes. Keep unchanged only personal and company names, addresses, "
        "e-mail addresses, URLs, file names, identifiers (contract, policy, claim or SIRET "
        "numbers), amounts, dates and codes. " + language_instruction(target)
    )
    result = chat_completion(
        settings.openai,
        [{"role": "system", "content": prompt}, {"role": "user", "content": text}],
        max_tokens=max(600, min(8000, len(text) // 2)),
        temperature=0.0,
        reasoning_effort="none",
        max_retries=2,
        timeout=90,
    )
    translated = str(result.get("content") or "").strip()
    if len(translated) < 0.3 * len(text.strip()):
        raise RuntimeError("Content translation returned an empty or truncated text.")
    if detect_language(translated) == source:
        raise RuntimeError("Content translation returned the text in its source language.")
    return translated


def translate_text_cached(
    settings: Settings,
    app_id: str,
    text: str,
    target: str,
) -> dict[str, Any]:
    """Translate one text into the target language, reusing the persisted cache."""
    source = detect_language(text)
    if source is None or base_language(source) == base_language(target):
        return {"text": text, "source_language": source, "translated": False}
    if len(text) > MAX_TRANSLATABLE_CHARS:
        return {"text": text, "source_language": source, "translated": False, "error": "too_long"}

    root = settings.app.storage_root
    name = _cache_name(text, target)
    cached = load_file(root, app_id, name)
    if cached:
        return {"text": cached.decode("utf-8"), "source_language": source, "translated": True}

    try:
        translated = translate_markdown(settings, text, source, target)
    except Exception as exc:
        logger.warning("Content translation failed for %s (%s→%s): %s", app_id, source, target, exc)
        return {
            "text": text,
            "source_language": source,
            "translated": False,
            "error": "translation_failed",
        }
    try:
        save_application_file(root, app_id, name, translated.encode("utf-8"))
    except Exception as exc:  # the translation is still returned
        logger.warning("Could not cache content translation for %s: %s", app_id, exc)
    return {"text": translated, "source_language": source, "translated": True}


def _case_pages(app_md: ApplicationMetadata) -> dict[int, str]:
    pages = {
        int(page["page_number"]): str(page.get("markdown") or "")
        for page in app_md.markdown_pages or []
        if isinstance(page, dict) and page.get("page_number") is not None
    }
    if not pages and app_md.document_markdown:
        pages[1] = app_md.document_markdown
    return pages


def translate_case_content(
    settings: Settings,
    app_md: ApplicationMetadata,
    language: str,
    page_numbers: list[int],
    batch_numbers: list[int],
) -> dict[str, Any]:
    """Translate the requested pages and batch summaries of a case, in parallel."""
    target = require_language(language)
    pages = _case_pages(app_md)
    batches = {
        int(batch["batch_num"]): str(batch.get("summary") or "")
        for batch in app_md.batch_summaries or []
        if isinstance(batch, dict) and batch.get("batch_num") is not None
    }
    items: list[tuple[str, int, str]] = [
        ("page", number, pages[number]) for number in dict.fromkeys(page_numbers) if number in pages
    ]
    items += [
        ("batch", number, batches[number])
        for number in dict.fromkeys(batch_numbers)
        if number in batches
    ]
    items = [item for item in items if item[2].strip()][:MAX_ITEMS_PER_REQUEST]

    def work(item: tuple[str, int, str]) -> dict[str, Any]:
        kind, number, text = item
        key = "page_number" if kind == "page" else "batch_num"
        return {key: number, **translate_text_cached(settings, app_md.id, text, target)}

    if len(items) > 1:
        with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(items))) as pool:
            results = list(pool.map(work, items))
    else:
        results = [work(item) for item in items]

    return {
        "language": target,
        "supported_languages": list(SUPPORTED_LANGUAGES),
        "pages": [result for result in results if "page_number" in result],
        "batches": [result for result in results if "batch_num" in result],
    }
