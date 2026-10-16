from __future__ import annotations

import json
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime
from html import unescape
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from app.brands import current_brand_key, current_brand_name

logger = logging.getLogger(__name__)


# =============================================================================
# Application List Cache (Performance Optimization)
# =============================================================================


class ApplicationCache:
    """Thread-safe in-memory cache for application listings."""

    def __init__(self, ttl_seconds: int = 30):
        self._cache: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def get(self, key: str) -> Optional[List[Dict[str, Any]]]:
        """Get cached value if not expired."""
        with self._lock:
            if key in self._cache:
                timestamp, data = self._cache[key]
                if time.time() - timestamp < self._ttl:
                    logger.debug("Cache hit for key: %s", key)
                    return data
                else:
                    del self._cache[key]
            return None

    def set(self, key: str, data: List[Dict[str, Any]]) -> None:
        """Store value in cache."""
        with self._lock:
            self._cache[key] = (time.time(), data)
            logger.debug("Cached data for key: %s", key)

    def invalidate(self, key: Optional[str] = None) -> None:
        """Invalidate cache entry or all entries."""
        with self._lock:
            if key is None:
                self._cache.clear()
                logger.debug("Invalidated entire cache")
            elif key in self._cache:
                del self._cache[key]
                logger.debug("Invalidated cache key: %s", key)


# Global cache instance (30 second TTL)
_applications_cache = ApplicationCache(ttl_seconds=30)


@dataclass
class StoredFile:
    filename: str
    path: str
    url: Optional[str] = None
    content_type: Optional[str] = None
    media_type: Optional[str] = None  # 'image', 'video', 'document'
    extracted: bool = False  # True after Content Understanding has processed this file
    original_name: Optional[str] = None  # Original upload filename


@dataclass
class ExtractedFieldConfidence:
    """Represents an extracted field with confidence score and source grounding."""

    field_name: str
    value: Any
    confidence: float
    page_number: Optional[int] = None
    bounding_box: Optional[List[float]] = None
    source_text: Optional[str] = None


@dataclass
class ConfidenceSummary:
    """Summary of confidence scores across all extracted fields."""

    total_fields: int = 0
    average_confidence: float = 0.0
    high_confidence_count: int = 0
    medium_confidence_count: int = 0
    low_confidence_count: int = 0
    high_confidence_fields: List[Dict[str, Any]] = field(default_factory=list)
    medium_confidence_fields: List[Dict[str, Any]] = field(default_factory=list)
    low_confidence_fields: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class ApplicationMetadata:
    id: str
    created_at: str
    external_reference: Optional[str]
    status: str
    files: List[StoredFile]
    persona: Optional[str] = None  # Persona this application belongs to
    document_markdown: Optional[str] = None
    markdown_pages: Optional[List[Dict[str, Any]]] = None
    cu_raw_result_path: Optional[str] = None
    llm_outputs: Optional[Dict[str, Any]] = None
    # New fields for confidence scoring
    extracted_fields: Optional[Dict[str, Any]] = None  # Raw extracted fields with confidence
    confidence_summary: Optional[Dict[str, Any]] = None  # Aggregated confidence statistics
    analyzer_id_used: Optional[str] = None  # Which analyzer was used for extraction
    extraction_provenance: Optional[Dict[str, Any]] = (
        None  # Extraction backend/model/source metadata
    )
    # Risk analysis results (separate from main LLM outputs)
    risk_analysis: Optional[Dict[str, Any]] = None  # Policy-based risk assessment
    # Fraud analysis results (persisted across page reloads)
    fraud_analysis: Optional[Dict[str, Any]] = None
    # Sentiment analysis (computed by the Sentiment Agent)
    sentiment_analysis: Optional[Dict[str, Any]] = None
    # Action history (persisted handler and orchestrator actions)
    action_history: Optional[List[Dict[str, Any]]] = None
    # Brand owning this dossier. Missing metadata defaults to the current brand.
    brand: Optional[str] = None
    # Background processing status tracking
    processing_status: Optional[str] = None  # idle, extracting, analyzing, error
    processing_error: Optional[str] = None  # Error message if processing failed
    # Context labels (backend-driven badges/alerts generated by LLM analysis)
    context_labels: Optional[List[Dict[str, Any]]] = None
    # Context tasks (backend-driven action items generated from analysis)
    context_tasks: Optional[List[Dict[str, Any]]] = None
    # Large document processing fields
    processing_mode: Optional[str] = None  # 'standard' or 'large_document'
    condensed_context: Optional[str] = None  # Summarized context for large docs
    document_stats: Optional[Dict[str, Any]] = None  # Document size/page stats
    batch_summaries: Optional[List[Dict[str, Any]]] = None  # Batch summaries for large docs UI
    # Controlled orchestration: per-stage budget trace + human-review status
    orchestration: Optional[Dict[str, Any]] = None


# =============================================================================
# Storage Provider Integration
# =============================================================================


def _get_provider():
    """Get the storage provider if initialized, or None for legacy fallback."""
    try:
        from app.storage_providers import get_storage_provider

        return get_storage_provider()
    except RuntimeError:
        # Provider not initialized - use legacy local storage
        return None


def load_file_content(stored_file: StoredFile) -> Optional[bytes]:
    """Load file content from storage.

    This function handles both local filesystem and Azure Blob Storage.
    It uses the storage provider if initialized, otherwise falls back to
    reading directly from the filesystem path.

    Args:
        stored_file: StoredFile object containing path information.

    Returns:
        File content as bytes, or None if file not found.
    """
    provider = _get_provider()

    if provider:
        # Use storage provider to load file
        content = provider.load_file_by_path(stored_file.path)
        if content is None:
            logger.warning("File not found via provider: %s", stored_file.path)
        return content
    else:
        # Legacy fallback: read directly from filesystem
        path = Path(stored_file.path)
        if not path.exists():
            logger.warning("File not found on filesystem: %s", path)
            return None
        return path.read_bytes()


def load_file(root: str, app_id: str, filename: str) -> Optional[bytes]:
    """Load a file from an application's files directory.

    Uses storage provider abstraction to support both local and Azure Blob storage.

    Args:
        root: Storage root path (used for legacy local storage).
        app_id: Application ID.
        filename: Name of the file to load.

    Returns:
        File content as bytes, or None if file not found.
    """
    provider = _get_provider()

    if provider:
        return provider.load_file(app_id, filename)
    else:
        # Legacy local storage
        brand_file_path = (
            get_storage_root(root)
            / "brands"
            / current_brand_key()
            / "applications"
            / app_id
            / "files"
            / filename
        )
        if not brand_file_path.exists():
            logger.warning("File not found on filesystem: %s", brand_file_path)
            return None
        return brand_file_path.read_bytes()


# =============================================================================
# Legacy Local Storage Helpers
# =============================================================================


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def get_storage_root(root: str) -> Path:
    p = Path(root)
    _ensure_dir(p)
    return p


def get_application_dir(root: str, app_id: str) -> Path:
    base = get_storage_root(root) / "brands" / current_brand_key() / "applications" / app_id
    _ensure_dir(base)
    return base


def save_uploaded_files(
    root: str,
    app_id: str,
    uploaded_files: List[Any],
    public_base_url: Optional[str] = None,
) -> List[StoredFile]:
    """Save uploaded files and return metadata.

    Delegates to storage provider if initialized, otherwise uses local filesystem.
    Accepts dicts with 'name' and 'content' keys (from FastAPI after async read).
    """
    provider = _get_provider()
    stored: List[StoredFile] = []

    for f in uploaded_files:
        # Handle dict format from FastAPI (pre-read content)
        if isinstance(f, dict):
            filename = f.get("name", f"upload-{len(stored)}.bin")
            data = f.get("content", b"")
        else:
            # Legacy support for objects with .name and .read()
            filename = getattr(f, "name", f"upload-{len(stored)}.bin")
            data = f.read() if hasattr(f, "read") else f

        if provider:
            # Use storage provider
            path = provider.save_file(app_id, filename, data)
            url = provider.get_file_url(app_id, filename)
        else:
            # Legacy local storage
            app_dir = get_application_dir(root, app_id)
            files_dir = app_dir / "files"
            _ensure_dir(files_dir)
            target_path = files_dir / filename
            with open(target_path, "wb") as out:
                out.write(data)
            path = str(target_path)
            url = None
            if public_base_url:
                url = (
                    f"{public_base_url.rstrip('/')}/brands/{current_brand_key()}"
                    f"/applications/{app_id}/files/{filename}"
                )

        stored.append(StoredFile(filename=filename, path=path, url=url))

    return stored


def save_cu_raw_result(root: str, app_id: str, payload: Dict[str, Any]) -> str:
    """Save Content Understanding raw result JSON."""
    provider = _get_provider()

    if provider:
        return provider.save_cu_result(app_id, payload)
    else:
        # Legacy local storage
        app_dir = get_application_dir(root, app_id)
        cu_path = app_dir / "content_understanding.json"
        with open(cu_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return str(cu_path)


def load_cu_result(root: str, app_id: str) -> Optional[Dict[str, Any]]:
    """Load Content Understanding result JSON.

    Uses storage provider abstraction to support both local and Azure Blob storage.
    """
    provider = _get_provider()

    if provider:
        return provider.load_cu_result(app_id)
    else:
        # Legacy local storage
        app_dir = get_storage_root(root) / "brands" / current_brand_key() / "applications" / app_id
        cu_path = app_dir / "content_understanding.json"
        if not cu_path.exists():
            return None
        with open(cu_path, "r", encoding="utf-8") as f:
            return json.load(f)


def _metadata_to_dict(metadata: ApplicationMetadata) -> Dict[str, Any]:
    """Convert ApplicationMetadata to a serializable dictionary."""
    if not metadata.brand:
        metadata.brand = current_brand_name()
    metadata.extracted_fields = sanitize_extracted_fields(metadata.extracted_fields)
    serializable = asdict(metadata)
    serializable["files"] = [asdict(f) for f in metadata.files]
    return serializable


_HTML_TAG_RE = re.compile(r"<[^>]+>")
_HTML_ONLY_RE = re.compile(r"^(?:</?(?:td|tr|th|table|tbody|thead|p|span|div|br)\s*/?>\s*)+$", re.I)


def _sanitize_extracted_value(value: Any) -> Any:
    if isinstance(value, str):
        cleaned = unescape(value).strip()
        if not cleaned or _HTML_ONLY_RE.fullmatch(cleaned):
            return None
        cleaned = _HTML_TAG_RE.sub("", cleaned).strip()
        return cleaned or None
    if isinstance(value, list):
        cleaned_items = [_sanitize_extracted_value(item) for item in value]
        return [item for item in cleaned_items if item not in (None, "", [], {})]
    if isinstance(value, dict):
        cleaned_dict = {}
        for key, nested in value.items():
            cleaned = _sanitize_extracted_value(nested)
            if cleaned not in (None, "", [], {}):
                cleaned_dict[key] = cleaned
        return cleaned_dict or None
    return value


def sanitize_extracted_fields(fields: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not fields:
        return fields
    sanitized: Dict[str, Any] = {}
    for key, entry in fields.items():
        if isinstance(entry, dict) and "value" in entry:
            cleaned_value = _sanitize_extracted_value(entry.get("value"))
            if cleaned_value in (None, "", [], {}):
                continue
            sanitized[key] = {**entry, "value": cleaned_value}
        else:
            cleaned_entry = _sanitize_extracted_value(entry)
            if cleaned_entry in (None, "", [], {}):
                continue
            sanitized[key] = cleaned_entry
    return sanitized


def _dict_to_metadata(data: Dict[str, Any]) -> ApplicationMetadata:
    """Convert a dictionary to ApplicationMetadata."""
    files = [StoredFile(**fd) for fd in data.get("files", [])]
    return ApplicationMetadata(
        id=data["id"],
        created_at=data.get("created_at"),
        external_reference=data.get("external_reference"),
        status=data.get("status", "unknown"),
        files=files,
        persona=data.get("persona"),
        document_markdown=data.get("document_markdown"),
        markdown_pages=data.get("markdown_pages"),
        cu_raw_result_path=data.get("cu_raw_result_path"),
        llm_outputs=data.get("llm_outputs"),
        extracted_fields=sanitize_extracted_fields(data.get("extracted_fields")),
        confidence_summary=data.get("confidence_summary"),
        analyzer_id_used=data.get("analyzer_id_used"),
        extraction_provenance=data.get("extraction_provenance"),
        risk_analysis=data.get("risk_analysis"),
        fraud_analysis=data.get("fraud_analysis"),
        sentiment_analysis=data.get("sentiment_analysis"),
        action_history=data.get("action_history"),
        brand=data.get("brand") or current_brand_name(),
        processing_status=data.get("processing_status"),
        processing_error=data.get("processing_error"),
        context_labels=data.get("context_labels"),
        context_tasks=data.get("context_tasks"),
        # Large document processing fields
        processing_mode=data.get("processing_mode"),
        condensed_context=data.get("condensed_context"),
        document_stats=data.get("document_stats"),
        batch_summaries=data.get("batch_summaries"),
        orchestration=data.get("orchestration"),
    )


def save_application_metadata(root: str, metadata: ApplicationMetadata) -> None:
    """Save application metadata."""
    provider = _get_provider()
    if not metadata.brand:
        metadata.brand = current_brand_name()
    serializable = _metadata_to_dict(metadata)

    if provider:
        provider.save_metadata(metadata.id, serializable)
    else:
        # Legacy local storage - use atomic write
        import os

        app_dir = get_application_dir(root, metadata.id)
        meta_path = app_dir / "metadata.json"
        temp_path = app_dir / "metadata.json.tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(serializable, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        temp_path.replace(meta_path)

    # Invalidate cache when metadata changes
    invalidate_applications_cache()

    # Sync summary to PostgreSQL (fire-and-forget, non-blocking)
    _sync_summary_to_pg(metadata)


def _sync_summary_to_pg(metadata: ApplicationMetadata) -> None:
    """Upsert key fields into workbenchiq.applications_summary for Fabric CDC.

    This is a fire-and-forget sync — failures are logged but do not block
    the main save operation. The summary table is a convenience layer for
    SQL search and Fabric mirroring, not the source of truth.
    """
    import asyncio

    async def _do_upsert():
        try:
            from app.database.pool import get_pool

            pool = await get_pool()
        except (RuntimeError, Exception):
            return  # DB not initialised — skip silently

        ef = metadata.extracted_fields or {}

        def _get_field(names: list[str]) -> str:
            """Extract a field value from extracted_fields by name list."""
            for name in names:
                # Direct key
                entry = ef.get(name)
                if not entry:
                    # Try filename:FieldName pattern
                    for fk, fv in ef.items():
                        if fk.endswith(f":{name}"):
                            entry = fv
                            break
                if entry:
                    if isinstance(entry, dict):
                        return str(entry.get("value", ""))
                    return str(entry)
            return ""

        nom = _get_field(
            [
                "NomAssure",
                "InsuredName",
                "NomSouscripteur",
                "ApplicantName",
                "PatientName",
                "assure",
                "beneficiaire",
                "emprunteur",
            ]
        )
        nature = _get_field(["NatureSinistre", "CauseOfLoss"])
        montant_raw = _get_field(["MontantEstime", "TotalIncurred", "MontantTotal"])
        franchise_raw = _get_field(["FranchiseApplicable"])
        contrat = _get_field(["NumeroContrat", "PolicyNumber"])
        date_sin = _get_field(["DateSinistre"])
        date_decl = _get_field(["DateDeclaration", "DateOuverture"])
        date_clot = _get_field(["DateCloture", "DateFermeture"])

        def _parse_amount(raw: str):
            """Parse '5 560,00 €' → 5560.00"""
            if not raw:
                return None
            clean = (
                raw.replace("€", "")
                .replace("\u20ac", "")
                .replace(" ", "")
                .replace(",", ".")
                .strip()
            )
            try:
                return float(clean)
            except ValueError:
                return None

        def _parse_date(raw: str):
            """Parse 'DD/MM/YYYY' or 'YYYY-MM-DD' → date string for PG."""
            if not raw:
                return None
            for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
                try:
                    return datetime.strptime(raw, fmt).date()
                except ValueError:
                    continue
            return None

        # Sentiment data
        sa = metadata.sentiment_analysis or {}
        sentiment_score = sa.get("score")
        sentiment_level = sa.get("level")
        sentiment_tone = sa.get("suggestedTone")

        # Fraud data
        fa = metadata.fraud_analysis or {}
        oa = fa.get("overall_assessment", {})
        fraud_risk = oa.get("overall_fraud_risk")
        fraud_score = round(oa.get("risk_score", 0) * 100) if oa.get("risk_score") else None
        siu = oa.get("siu_referral_recommended", False)

        # Indemnisation from LLM outputs
        indemnisation = None
        llm = metadata.llm_outputs or {}
        payout = llm.get("payout_recommendation", {})
        for sub, output in payout.items() if payout else []:
            parsed = output.get("parsed", {}) if output else {}
            val = parsed.get("montant_indemnisation_recommande", "")
            if val:
                indemnisation = _parse_amount(str(val))
                break

        sql = """
            INSERT INTO workbenchiq.applications_summary (
                app_id, brand, persona, status, nom_assure, nature_sinistre,
                montant_estime, franchise, indemnisation, numero_contrat,
                date_sinistre, date_declaration, date_cloture,
                file_count, sentiment_score, sentiment_level,
                sentiment_tone, fraud_risk_level, fraud_risk_score,
                siu_recommended, processing_status, external_reference,
                updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15, $16, $17, $18, $19,
                $20, $21, $22,
                CURRENT_TIMESTAMP
            )
            ON CONFLICT (app_id, brand) DO UPDATE SET
                persona = EXCLUDED.persona,
                status = EXCLUDED.status,
                nom_assure = EXCLUDED.nom_assure,
                nature_sinistre = EXCLUDED.nature_sinistre,
                montant_estime = EXCLUDED.montant_estime,
                franchise = EXCLUDED.franchise,
                indemnisation = EXCLUDED.indemnisation,
                numero_contrat = EXCLUDED.numero_contrat,
                date_sinistre = EXCLUDED.date_sinistre,
                date_declaration = EXCLUDED.date_declaration,
                date_cloture = EXCLUDED.date_cloture,
                file_count = EXCLUDED.file_count,
                sentiment_score = EXCLUDED.sentiment_score,
                sentiment_level = EXCLUDED.sentiment_level,
                sentiment_tone = EXCLUDED.sentiment_tone,
                fraud_risk_level = EXCLUDED.fraud_risk_level,
                fraud_risk_score = EXCLUDED.fraud_risk_score,
                siu_recommended = EXCLUDED.siu_recommended,
                processing_status = EXCLUDED.processing_status,
                external_reference = EXCLUDED.external_reference,
                updated_at = CURRENT_TIMESTAMP
        """

        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    sql,
                    metadata.id,
                    metadata.brand or current_brand_name(),
                    metadata.persona,
                    metadata.status or "pending",
                    nom[:255] if nom else None,
                    nature[:500] if nature else None,
                    _parse_amount(montant_raw),
                    _parse_amount(franchise_raw),
                    indemnisation,
                    contrat[:100] if contrat else None,
                    _parse_date(date_sin),
                    _parse_date(date_decl),
                    _parse_date(date_clot),
                    len(metadata.files or []),
                    sentiment_score,
                    sentiment_level,
                    sentiment_tone,
                    fraud_risk,
                    fraud_score,
                    siu,
                    metadata.processing_status,
                    metadata.external_reference,
                )
        except Exception as exc:
            logger.debug("applications_summary sync failed for %s: %s", metadata.id, exc)

    # Fire-and-forget: try to run in existing event loop, else skip
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_do_upsert())
    except RuntimeError:
        # No running loop — try to create one (sync context)
        try:
            asyncio.run(_do_upsert())
        except Exception:
            pass  # DB not available — skip silently


def _metadata_matches_lookup(data: Dict[str, Any], lookup: str, storage_id: str) -> bool:
    lookup_norm = lookup.strip().lower()
    if not lookup_norm:
        return False
    candidates = [
        storage_id,
        data.get("id"),
        data.get("external_reference"),
    ]
    for candidate in candidates:
        if not candidate:
            continue
        candidate_norm = str(candidate).strip().lower()
        if candidate_norm == lookup_norm or candidate_norm.startswith(lookup_norm):
            return True
    return False


def _resolve_application_metadata(root: str, app_id: str) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
    """Resolve exact, short, or external-reference app lookups to metadata."""
    provider = _get_provider()
    current_brand = current_brand_name()

    if provider:
        data = provider.load_metadata(app_id)
        if data is not None:
            return app_id, data

        matches: list[tuple[str, Dict[str, Any]]] = []
        for candidate_id in provider.list_applications():
            candidate_data = provider.load_metadata(candidate_id)
            if candidate_data is None:
                continue
            app_brand = candidate_data.get("brand") or current_brand
            if app_brand != current_brand:
                continue
            if _metadata_matches_lookup(candidate_data, app_id, candidate_id):
                matches.append((candidate_id, candidate_data))

        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            logger.warning("Ambiguous application lookup %s matched %d dossiers", app_id, len(matches))
        return None, None

    # Legacy local storage
    meta_paths: list[tuple[str, Path]] = []
    app_dir = get_storage_root(root) / "brands" / current_brand_key() / "applications" / app_id
    meta_path = app_dir / "metadata.json"
    if meta_path.exists():
        meta_paths.append((app_id, meta_path))

    if not meta_paths:
        base = get_storage_root(root) / "brands" / current_brand_key() / "applications"
        if base.exists():
            for candidate_dir in base.iterdir():
                if not candidate_dir.is_dir():
                    continue
                candidate_meta = candidate_dir / "metadata.json"
                if not candidate_meta.exists():
                    continue
                try:
                    with open(candidate_meta, "r", encoding="utf-8") as f:
                        candidate_data = json.load(f)
                except (OSError, json.JSONDecodeError):
                    continue
                candidate_data.setdefault("brand", current_brand)
                if candidate_data.get("brand") != current_brand:
                    continue
                if _metadata_matches_lookup(candidate_data, app_id, candidate_dir.name):
                    meta_paths.append((candidate_dir.name, candidate_meta))

    if len(meta_paths) != 1:
        if len(meta_paths) > 1:
            logger.warning("Ambiguous application lookup %s matched %d local dossiers", app_id, len(meta_paths))
        return None, None

    resolved_id, resolved_meta_path = meta_paths[0]
    with open(resolved_meta_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    data.setdefault("brand", current_brand)
    return resolved_id, data


def load_application(root: str, app_id: str) -> Optional[ApplicationMetadata]:
    """Load application metadata by exact ID, short ID prefix, or external reference."""
    current_brand = current_brand_name()
    resolved_id, data = _resolve_application_metadata(root, app_id)
    if data is None:
        return None
    metadata = _dict_to_metadata(data)
    if metadata.brand != current_brand:
        logger.warning(
            "Rejected application %s for brand %s while running brand %s",
            app_id,
            metadata.brand,
            current_brand,
        )
        return None
    if metadata.id != resolved_id:
        metadata.id = resolved_id or metadata.id
    return metadata


def delete_application(root: str, app_id: str) -> bool:
    """Delete an application and all its files.

    Args:
        root: Storage root path
        app_id: Application ID to delete

    Returns:
        True if deleted, False if not found
    """
    import shutil

    provider = _get_provider()
    deleted = False

    if provider:
        # Use storage provider delete if available
        if hasattr(provider, "delete_application"):
            deleted = provider.delete_application(app_id)
        else:
            logger.warning("Storage provider does not support delete_application")
            return False
    else:
        # Legacy local storage
        app_dir = get_storage_root(root) / "brands" / current_brand_key() / "applications" / app_id
        if not app_dir.exists():
            return False

        try:
            shutil.rmtree(app_dir)
            logger.info("Deleted application directory: %s", app_dir)
            deleted = True
        except Exception as e:
            logger.error("Failed to delete application %s: %s", app_id, e)
            return False

    # Invalidate cache when application is deleted
    if deleted:
        invalidate_applications_cache()

    return deleted


# Keys to extract as summary info for the application list cards
_KEY_FIELD_NAMES = [
    "NomAssure",
    "AssuréNom",
    "InsuredName",
    "Assure",
    "Assuré",
    "NomClient",
    "ClientName",
    "PolicyholderName",
    "PatientName",  # insured name (claims)
    "NomSouscripteur",
    "ApplicantName",  # subscriber/applicant name (underwriting)
    "Claimant",
    "ClaimantName",
    "Conducteur",
    "DriverName",
    "NomConducteur",
    "Borrower",
    "BorrowerName",
    "BorrowerFullName",
    "Emprunteur",
    "NumeroContrat",
    "NumeroPolice",
    "PolicyNumber",  # policy/contract number
    "ClaimNumber",
    "DateSinistre",  # claim date
    "DateOfLoss",
    "NatureSinistre",  # claim type
    "CauseOfLoss",
    "ClaimType",
    "LossType",
    "IncidentDescription",
    "CoverageType",
    "OverallDamageSeverity",
    "EstimatedDamageCategory",
    "VehicleMake",
    "VehicleModel",
    "LicensePlate",
    "FormuleDemandee",
    "PolicyProduct",  # underwriting product type
]


def _normalize_field_label(value: str) -> str:
    """Normalize analyzer/LLM labels for stable key-field matching."""
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _field_matches(key: str, target: str) -> bool:
    """Return true when a raw extracted field key maps to target.

    Extracted fields may be stored as "filename.pdf:FieldName" or
    "llm_extracted:FieldName"; matching on the final segment keeps this robust.
    """
    return _normalize_field_label(key.split(":")[-1]) == _normalize_field_label(target)


def _stringify_key_field_value(value: Any) -> str:
    """Convert extracted values to compact display strings."""
    value = _sanitize_extracted_value(value)
    if value is None:
        return ""
    if isinstance(value, dict):
        for name_key in (
            "name",
            "fullName",
            "full_name",
            "nom",
            "label",
            "value",
            "vehicle",
            "description",
        ):
            nested = value.get(name_key)
            if nested:
                return _stringify_key_field_value(nested)
        parts = [
            _stringify_key_field_value(v)
            for v in value.values()
            if isinstance(v, (str, int, float))
        ]
        return " ".join(p for p in parts if p).strip()
    if isinstance(value, list):
        parts = [_stringify_key_field_value(item) for item in value[:3]]
        return ", ".join(p for p in parts if p).strip()
    return str(value).strip()


def _extract_entry_value(entry: Any) -> str:
    if isinstance(entry, dict) and "value" in entry:
        return _stringify_key_field_value(entry.get("value"))
    return _stringify_key_field_value(entry)


def _add_llm_key_fields(data: Dict[str, Any], result: Dict[str, str]) -> None:
    """Fill missing list-card fields from LLM parsed key_fields arrays."""
    llm_outputs = data.get("llm_outputs") or {}
    if not isinstance(llm_outputs, dict):
        return

    def classify(label: str) -> Optional[str]:
        normalized = _normalize_field_label(label)
        if any(
            token in normalized
            for token in (
                "applicantname",
                "candidate",
                "candidat",
                "nomduclient",
                "clientname",
                "nomclient",
                "souscripteur",
                "policyholder",
                "insuredname",
                "nomassure",
                "claimant",
                "conducteur",
                "driver",
                "borrower",
                "emprunteur",
                "patientname",
            )
        ):
            return "ApplicantName" if "underwriting" in (data.get("persona") or "") else "NomAssure"
        if any(
            token in normalized
            for token in ("product", "produit", "formule", "coverage", "garantie")
        ):
            return "PolicyProduct"
        if any(token in normalized for token in ("claimtype", "loss", "sinistre", "incident")):
            return "NatureSinistre"
        if any(token in normalized for token in ("policy", "police", "contrat")):
            return "PolicyNumber"
        return None

    for section in llm_outputs.values():
        if not isinstance(section, dict):
            continue
        for output in section.values():
            if not isinstance(output, dict):
                continue
            parsed = output.get("parsed") or {}
            if not isinstance(parsed, dict):
                continue
            key_fields = parsed.get("key_fields")
            if not isinstance(key_fields, list):
                continue
            for item in key_fields:
                if not isinstance(item, dict):
                    continue
                label = str(item.get("label") or item.get("name") or "")
                value = _stringify_key_field_value(item.get("value"))
                canonical = classify(label)
                if canonical and value and canonical not in result:
                    result[canonical] = value


def _add_markdown_key_fields(data: Dict[str, Any], result: Dict[str, str]) -> None:
    """Fill missing list-card fields from extracted markdown for extraction-only dossiers."""
    markdown = data.get("document_markdown")
    if not isinstance(markdown, str) or not markdown.strip():
        return

    patterns: list[tuple[str, str, re.Pattern[str]]] = [
        (
            "ApplicantName",
            "underwriting",
            re.compile(
                r"(?:nom\s*(?:du\s*)?(?:client|assur[ée]|souscripteur|candidat|demandeur)|"
                r"assur[ée]|souscripteur)\s*[:：]\s*([^\n|]{2,120})",
                re.I,
            ),
        ),
        (
            "NomAssure",
            "claims",
            re.compile(
                r"(?:nom\s*(?:de\s*l['’])?assur[ée]|assur[ée]|bénéficiaire|patient)\s*[:：]\s*([^\n|]{2,120})",
                re.I,
            ),
        ),
        (
            "PolicyProduct",
            "any",
            re.compile(
                r"(?:produit|formule|garantie|contrat|couverture)\s*[:：]\s*([^\n|]{2,120})",
                re.I,
            ),
        ),
        (
            "NatureSinistre",
            "any",
            re.compile(
                r"(?:nature|type|cause)\s*(?:du\s*)?(?:sinistre|incident|demande)?\s*[:：]\s*([^\n|]{2,120})",
                re.I,
            ),
        ),
    ]
    persona = data.get("persona") or "underwriting"
    for canonical, scope, regex in patterns:
        if canonical in result:
            continue
        if scope == "underwriting" and "underwriting" not in persona:
            continue
        if scope == "claims" and "claims" not in persona:
            continue
        match = regex.search(markdown)
        if not match:
            continue
        value = _stringify_key_field_value(match.group(1))
        if value:
            result[canonical] = value[:120]


def _extract_key_fields(data: Dict[str, Any]) -> Dict[str, str]:
    """Extract a small set of key fields from metadata for list display."""
    ef = data.get("extracted_fields") or {}
    result: Dict[str, str] = {}
    for target in _KEY_FIELD_NAMES:
        # Direct key
        entry = ef.get(target)
        if not entry:
            # Try filename:FieldName / llm_extracted:FieldName patterns.
            for fk, fv in ef.items():
                if _field_matches(str(fk), target):
                    entry = fv
                    break
        val = _extract_entry_value(entry) if entry else ""
        if val:
            result[target] = val
    _add_llm_key_fields(data, result)
    _add_markdown_key_fields(data, result)
    return result


def list_applications(root: str, persona: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return lightweight list of available applications, optionally filtered by persona.

    Uses caching and parallel loading for improved performance with cloud storage.
    """
    from app.personas import normalize_persona_id

    # Normalize the filter persona (handles legacy 'claims' -> 'life_health_claims')
    if persona is not None:
        persona = normalize_persona_id(persona)

    # Check cache first
    current_brand = current_brand_name()
    cache_key = f"apps:{current_brand}:{persona or 'all'}"
    cached = _applications_cache.get(cache_key)
    if cached is not None:
        return cached

    provider = _get_provider()
    apps: List[Dict[str, Any]] = []

    if provider:
        # Use storage provider with parallel metadata loading
        app_ids = provider.list_applications()

        def load_app_metadata(app_id: str) -> Optional[Dict[str, Any]]:
            """Load and format metadata for a single application."""
            data = provider.load_metadata(app_id)
            if data is None:
                return None

            app_brand = data.get("brand") or current_brand
            if app_brand != current_brand:
                logger.warning(
                    "Skipping application %s for brand %s while listing brand %s",
                    app_id,
                    app_brand,
                    current_brand,
                )
                return None

            # Filter by persona if specified
            app_persona = data.get("persona") or "underwriting"
            app_persona = normalize_persona_id(app_persona)

            if persona is not None and app_persona != persona:
                return None

            return {
                "id": app_id,
                "created_at": data.get("created_at"),
                "external_reference": data.get("external_reference"),
                "status": data.get("status", "unknown"),
                "persona": app_persona,
                "processing_status": data.get("processing_status"),
                "summary_title": data.get("llm_outputs", {})
                .get("application_summary", {})
                .get("customer_profile", {})
                .get("summary", "")
                or "",
                "file_count": len(data.get("files", [])),
                "key_fields": _extract_key_fields(data),
            }

        # Load metadata in parallel (up to 10 concurrent requests)
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(load_app_metadata, app_id): app_id for app_id in app_ids}
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result is not None:
                        apps.append(result)
                except Exception as e:
                    app_id = futures[future]
                    logger.warning("Failed to load metadata for %s: %s", app_id, e)
    else:
        # Legacy local storage
        bases = [get_storage_root(root) / "brands" / current_brand_key() / "applications"]

        seen_app_ids: set[str] = set()
        for base in bases:
            if not base.exists():
                continue
            for app_dir in sorted(base.iterdir()):
                if not app_dir.is_dir() or app_dir.name in seen_app_ids:
                    continue
                meta_path = app_dir / "metadata.json"
                if not meta_path.exists():
                    continue
                with open(meta_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                data.setdefault("brand", current_brand)

                if data.get("brand") != current_brand:
                    continue
                seen_app_ids.add(app_dir.name)

                # Filter by persona if specified
                # Legacy apps without persona are treated as "underwriting"
                app_persona = data.get("persona") or "underwriting"
                # Normalize app persona as well (handles legacy 'claims' in stored data)
                app_persona = normalize_persona_id(app_persona)

                if persona is not None and app_persona != persona:
                    continue

                apps.append(
                    {
                        "id": app_dir.name,
                        "created_at": data.get("created_at"),
                        "external_reference": data.get("external_reference"),
                        "status": data.get("status", "unknown"),
                        "persona": app_persona,
                        "processing_status": data.get("processing_status"),
                        "summary_title": data.get("llm_outputs", {})
                        .get("application_summary", {})
                        .get("customer_profile", {})
                        .get("summary", "")
                        or "",
                        "file_count": len(data.get("files", [])),
                        "key_fields": _extract_key_fields(data),
                    }
                )

    # Sort by created_at descending
    apps.sort(key=lambda a: a.get("created_at") or "", reverse=True)

    # Cache the result
    _applications_cache.set(cache_key, apps)

    return apps


def invalidate_applications_cache() -> None:
    """Invalidate the applications list cache.

    Call this when applications are created, updated, or deleted.
    """
    _applications_cache.invalidate()


def new_metadata(
    root: str,
    app_id: str,
    files: List[StoredFile],
    external_reference: Optional[str] = None,
    persona: Optional[str] = None,
) -> ApplicationMetadata:
    created_at = datetime.utcnow().isoformat() + "Z"
    md = ApplicationMetadata(
        id=app_id,
        created_at=created_at,
        external_reference=external_reference,
        status="pending",
        files=files,
        persona=persona,
        brand=current_brand_name(),
        document_markdown=None,
        markdown_pages=None,
        cu_raw_result_path=None,
        llm_outputs={},
    )
    save_application_metadata(root, md)
    return md
