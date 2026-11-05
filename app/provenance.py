"""Content provenance of claim photos, read from embedded C2PA Content Credentials.

Shown next to each photo by default (``FRAUD_PROVENANCE_MODE=inform``); only ``score`` lets
the fraud model weigh it. Reading is local: the cloud Content Provenance Detection API also
finds invisible watermarks, but it only reads Azure Blob URIs, which the private storage
account does not expose.
"""

from __future__ import annotations

import hashlib
import io
import json
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import PurePosixPath
from typing import Any

from .utils import setup_logging

logger = setup_logging()

_MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".heic": "image/heic",
    ".heif": "image/heif",
    ".avif": "image/avif",
}
# IPTC digital source types of AI-generated or AI-composited media.
_AI_SOURCE_TYPES = ("trainedAlgorithmicMedia", "compositeWithTrainedAlgorithmicMedia")
_READ_TIMEOUT_SECONDS = 5
_MAX_BYTES = 50 * 1024 * 1024
_CACHE_MAX_ENTRIES = 512
_cache: dict[str, dict[str, Any]] = {}
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="c2pa")


def detect_provenance(content: bytes, filename: str) -> dict[str, Any]:
    """C2PA provenance of an image; ``status`` is c2pa, none, unsupported or error.

    ``ai_generated`` follows the IPTC digital source type declared in the manifest. The
    signature is not checked against a trust list: ``validation`` is the reader's raw state.
    """
    mime = _MIME_TYPES.get(PurePosixPath(filename).suffix.lower())
    if not mime or not content or len(content) > _MAX_BYTES:
        return {"status": "unsupported"}
    digest = hashlib.sha256(content).hexdigest()
    if digest in _cache:
        return dict(_cache[digest])
    try:
        result = _executor.submit(_read_manifest, content, mime).result(
            timeout=_READ_TIMEOUT_SECONDS
        )
    except FutureTimeoutError:
        logger.warning("C2PA reading timed out for %s", filename)
        return {"status": "error"}
    except Exception as exc:
        logger.info("C2PA reading failed for %s: %r", filename, exc)
        result = {"status": "error"}
    if len(_cache) >= _CACHE_MAX_ENTRIES:
        _cache.pop(next(iter(_cache)))
    _cache[digest] = result
    return dict(result)


def _read_manifest(content: bytes, mime: str) -> dict[str, Any]:
    import c2pa

    try:
        with c2pa.Reader(mime, io.BytesIO(content)) as reader:
            store = json.loads(reader.json())
    except c2pa.C2paError as exc:
        kind = f"{type(exc).__name__} {exc}"
        if "ManifestNotFound" in kind:
            return {"status": "none"}
        if "NotSupported" in kind:
            return {"status": "unsupported"}
        raise

    manifests = store.get("manifests") or {}
    manifest = manifests.get(store.get("active_manifest") or "") or {}
    actions = [
        action
        for assertion in manifest.get("assertions") or []
        if str(assertion.get("label", "")).startswith("c2pa.actions")
        for action in (assertion.get("data") or {}).get("actions") or []
        if isinstance(action, dict)
    ]
    created = next((a for a in actions if a.get("action") == "c2pa.created"), {})
    agent = created.get("softwareAgent")
    generator = agent.get("name") if isinstance(agent, dict) else agent
    if not generator:
        generator_info = manifest.get("claim_generator_info") or [{}]
        generator = (generator_info[0] or {}).get("name") or manifest.get("claim_generator")
    source = str(created.get("digitalSourceType") or "")
    signature = manifest.get("signature_info") or {}
    return {
        "status": "c2pa",
        "ai_generated": source.rsplit("/", 1)[-1] in _AI_SOURCE_TYPES if source else None,
        "generator": generator or None,
        "issuer": signature.get("issuer"),
        "created_at": created.get("when") or signature.get("time"),
        "watermark_declared": any(a.get("action") == "c2pa.watermarked" for a in actions),
        "validation": store.get("validation_state"),
    }
