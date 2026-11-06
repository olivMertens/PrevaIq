"""The persona glossary in the reader's language.

Each glossary is written in one language, declared as ``language`` in glossary.json (French
for the property and mortgage glossaries, English for the others). For another UI language,
category names, meanings and contexts are translated once by the model and kept in memory,
keyed by their content: an edited term is translated again. Abbreviations never change.
When the translation fails, the glossary is shown in its own language and retried next time.
"""

from __future__ import annotations

import copy
import hashlib
import json
import threading
from collections import OrderedDict
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Final, Optional

from app.config import Settings
from app.content_translation import detect_language
from app.glossary import get_glossary_for_persona
from app.languages import SUPPORTED_LANGUAGES, language_name, require_language
from app.openai_client import chat_completion
from app.utils import setup_logging

logger = setup_logging()

_CHUNK: Final = 40
_MAX_WORKERS: Final = 4
_MAX_CACHED: Final = 32
# Bump when the prompt changes so cached translations are rebuilt.
_CACHE_VERSION: Final = "v1"

# (texts, source, target) -> translations, in the same order.
Translate = Callable[[Sequence[str], str, str], list[str]]

_cache: OrderedDict[str, dict[str, str]] = OrderedDict()
_locks: dict[str, threading.Lock] = {}
_guard = threading.Lock()


def glossary_language(glossary: dict[str, Any]) -> Optional[str]:
    """Declared language of a glossary, else the one its terms are written in."""
    declared = str(glossary.get("language") or "").lower()
    if declared in SUPPORTED_LANGUAGES:
        return declared
    sample = " ".join(
        f"{term.get('meaning', '')} {term.get('context', '')}"
        for category in glossary.get("categories", [])
        for term in category.get("terms", [])
    )
    return detect_language(sample)


def _texts(categories: list[dict[str, Any]]) -> list[str]:
    """The displayed texts to translate: category names, meanings and contexts."""
    texts = []
    for category in categories:
        texts.append(str(category.get("name") or ""))
        for term in category.get("terms", []):
            texts += [str(term.get("meaning") or ""), str(term.get("context") or "")]
    return list(dict.fromkeys(text for text in texts if text.strip()))


def translate_entries(
    settings: Settings, texts: Sequence[str], source: str, target: str
) -> list[str]:
    """One bounded model call; raises unless it returns one translation per text."""
    prompt = (
        f"Translate each entry of this insurance glossary JSON array from {language_name(source)} "
        f"to {language_name(target)}. Answer with a JSON object "
        f'{{"translations": [...]}} holding exactly {len(texts)} strings, in the same order. '
        "Keep unchanged abbreviations and acronyms (DDE, IRSI, LTV, BP...), references to laws, "
        "articles and decrees, names of organisations and products, amounts, percentages and "
        "codes. Translate a short label as a short label."
    )
    result = chat_completion(
        settings.openai,
        [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(list(texts), ensure_ascii=False)},
        ],
        max_tokens=max(800, min(6000, sum(len(text) for text in texts) // 3 + 400)),
        temperature=0.0,
        reasoning_effort="none",
        max_retries=2,
        timeout=90,
        response_format="json_object",
    )
    answer = json.loads(str(result.get("content") or "{}"))
    translations = answer.get("translations") if isinstance(answer, dict) else None
    if (
        not isinstance(translations, list)
        or len(translations) != len(texts)
        or not all(isinstance(text, str) and text.strip() for text in translations)
    ):
        raise RuntimeError("Glossary translation returned a malformed answer.")
    return [text.strip() for text in translations]


def _translations(
    texts: list[str], source: str, target: str, translate: Translate
) -> dict[str, str]:
    """Translation of every text, from the cache or in parallel batches."""
    key = hashlib.sha256(
        json.dumps([_CACHE_VERSION, source, target, texts], ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    with _guard:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:  # concurrent requests for the same glossary wait for one translation
        with _guard:
            if key in _cache:
                _cache.move_to_end(key)
                return _cache[key]
        chunks = [texts[start : start + _CHUNK] for start in range(0, len(texts), _CHUNK)]
        with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(chunks))) as pool:
            results = list(pool.map(lambda chunk: translate(chunk, source, target), chunks))
        translated = {
            text: result
            for chunk, chunk_results in zip(chunks, results)
            for text, result in zip(chunk, chunk_results)
        }
        with _guard:
            _cache[key] = translated
            while len(_cache) > _MAX_CACHED:
                _cache.popitem(last=False)
        return translated


def localized_glossary(
    settings: Settings,
    persona: str,
    language: str,
    translate: Optional[Translate] = None,
) -> dict[str, Any]:
    """A persona glossary with its categories, meanings and contexts in ``language``.

    ``language`` is the language of the returned texts: the requested one, or the glossary's
    own language when it cannot be translated (``translated`` is then false).
    """
    target = require_language(language)
    glossary = get_glossary_for_persona(settings.app.prompts_root, persona)
    source = glossary_language(glossary)
    original = {**glossary, "language": source, "source_language": source, "translated": False}
    texts = _texts(glossary.get("categories", []))
    if source is None or source == target or not texts:
        return original

    translate = translate or (lambda chunk, src, dst: translate_entries(settings, chunk, src, dst))
    try:
        translations = _translations(texts, source, target, translate)
    except Exception as exc:  # model unavailable or malformed answer: show the original terms
        logger.warning(
            "Glossary translation failed for %s (%s→%s): %s", persona, source, target, exc
        )
        return original

    categories = copy.deepcopy(glossary.get("categories", []))
    for category in categories:
        name = str(category.get("name") or "")
        category["name"] = translations.get(name, name)
        for term in category.get("terms", []):
            for field in ("meaning", "context"):
                value = str(term.get(field) or "")
                if value:
                    term[field] = translations.get(value, value)
    return {
        **glossary,
        "categories": categories,
        "language": target,
        "source_language": source,
        "translated": True,
    }
