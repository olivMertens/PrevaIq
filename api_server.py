"""
FastAPI backend server for the Underwriting Assistant.
This provides REST API endpoints for the Next.js frontend.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, UTC
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from pydantic import BaseModel

from app.brands import DEFAULT_BRAND, get_brand_profile, get_current_brand_profile
from app.agents.errors import AgentServiceError
from app.config import load_settings, validate_settings
from app.database.settings import DatabaseSettings
from app.database.pool import init_pool
from app.telemetry import configure_telemetry, install_claim_correlation_middleware
from app.storage import (
    list_applications,
    load_application,
    load_file,
    new_metadata,
    save_uploaded_files,
    save_application_metadata,
    ApplicationMetadata,
)
from app.processing import (
    run_content_understanding_for_files,
    run_underwriting_prompts,
)
from app.orchestration import mark_reviewed
from app.file_capabilities import get_file_capabilities, is_supported_file
from app.prompts import load_prompts, save_prompts
from app.content_understanding_client import (
    get_analyzer,
    create_or_update_custom_analyzer,
    delete_analyzer,
)
from app.config import UNDERWRITING_FIELD_SCHEMA
from app.personas import list_personas, get_persona_config, get_field_schema
from app.utils import setup_logging

# Setup logging
logger = setup_logging()

# Configure OpenTelemetry → Azure Monitor (must be before FastAPI init)
configure_telemetry()

brand_profile = get_current_brand_profile()

# Initialize FastAPI app
# NOTE: API key auth is applied per-router (not app-level) because
# WebSocket connections don't support the APIKeyHeader dependency.
app = FastAPI(
    title=f"{brand_profile.app_name} API",
    description=f"REST API for {brand_profile.app_name} - Multi-persona document processing workbench",
    version="0.3.0",
)

# Configure CORS for frontend access
# In production, replace with your actual frontend domain(s)
allowed_origins = [
    "http://localhost:3000",  # Next.js dev server
    "http://127.0.0.1:3000",
]

# Add Azure frontend URL(s) from environment variable if configured
import os
azure_frontend_url = os.getenv("FRONTEND_URL")
if azure_frontend_url:
    allowed_origins.append(azure_frontend_url)

# Support CORS_ORIGINS env var (comma-separated list of allowed origins)
cors_origins = os.getenv("CORS_ORIGINS")
if cors_origins:
    for origin in cors_origins.split(","):
        origin = origin.strip()
        if origin and origin not in allowed_origins:
            allowed_origins.append(origin)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

install_claim_correlation_middleware(app)


# Health check + API key middleware — runs on HTTP only (not WebSocket).
# WebSocket endpoints handle their own auth via query parameters.
@app.middleware("http")
async def auth_and_health_middleware(request: Request, call_next):
    # Health check — always allowed
    if request.url.path == "/":
        current_profile = get_current_brand_profile()
        return JSONResponse({"status": "ok", "version": "0.3.0", "name": current_profile.app_name})

    # API key check for all other HTTP requests
    expected_key = os.getenv("API_KEY") or None
    if expected_key:
        import hmac
        provided = request.headers.get("x-api-key") or request.query_params.get("api_key") or ""
        if not provided or not hmac.compare_digest(provided, expected_key):
            return JSONResponse(
                {"detail": "Clé API invalide ou manquante"},
                status_code=401,
            )

    return await call_next(request)


# Include modular routers (lazy loading to avoid circular imports)
from app.access_api import router as access_api_router  # noqa: E402

app.include_router(access_api_router)

try:
    from app.claims.api import router as claims_api_router
    app.include_router(claims_api_router)
    logger.info("Claims API router registered")
except ImportError as e:
    logger.warning("Claims API router not available: %s", e)

# Initialize storage provider and database pool on startup
@app.on_event("startup")
async def startup_event():
    """Initialize application components on startup."""
    from app.storage_providers import init_storage_provider, StorageSettings
    try:
        storage_settings = StorageSettings.from_env()
        init_storage_provider(storage_settings)
        logger.info(
            "Storage provider initialized: backend=%s  auth_mode=%s  "
            "allow_create_container=%s",
            storage_settings.backend.value,
            storage_settings.azure_storage_auth_mode,
            storage_settings.azure_storage_allow_create_container,
        )
    except Exception as e:
        logger.error("Failed to initialize storage provider: %s", e)
        raise

    # Log API key authentication status
    api_key = os.getenv("API_KEY") or None
    if api_key:
        if len(api_key) < 32:
            logger.error(
                "API_KEY is set but too short (%d chars). "
                "Use at least 32 characters for adequate security.",
                len(api_key),
            )
            raise RuntimeError("API_KEY must be at least 32 characters")
        logger.info("API key authentication enabled")
    else:
        logger.warning("API_KEY not set — backend endpoints are UNPROTECTED")

    # Initialize database pool if using PostgreSQL
    settings = load_settings()

    # One-shot diagnostic snapshot of CU + OpenAI config that this revision actually sees.
    # Helps triage per-revision config drift.
    try:
        from urllib.parse import urlparse

        cu = settings.content_understanding
        oa = settings.openai
        cu_host = urlparse(cu.endpoint).hostname if cu.endpoint else "<unset>"
        oa_host = urlparse(oa.endpoint).hostname if oa.endpoint else "<unset>"
        logger.info(
            "[CU-CONFIG] brand=%s cu_host=%s api_version=%s analyzer_id=%s custom_analyzer_id=%s "
            "completion_deployment=%s embedding_deployment=%s use_azure_ad=%s confidence_scores=%s "
            "| oa_host=%s oa_deployment=%s oa_api_version=%s oa_use_azure_ad=%s",
            settings.brand_name,
            cu_host,
            cu.api_version,
            cu.analyzer_id,
            cu.custom_analyzer_id,
            cu.completion_deployment or "<resource-default>",
            cu.embedding_deployment or "<resource-default>",
            cu.use_azure_ad,
            cu.enable_confidence_scores,
            oa_host,
            oa.deployment_name,
            oa.api_version,
            oa.use_azure_ad,
        )
    except Exception as _snap_exc:  # noqa: BLE001
        logger.warning("[CU-CONFIG] Failed to emit startup config snapshot: %s", _snap_exc)

    if settings.database.backend == "postgresql":
        try:
            await init_pool(settings.database)
            logger.info("Database pool initialized (PostgreSQL)")
        except Exception as e:
            logger.error("Failed to initialize database pool: %s", e)
            raise

    # Auto-seed Customer 360 data if no customers exist yet
    try:
        from app.customer360 import list_customers as _list_all_customers
        existing = _list_all_customers(settings.app.storage_root)
        if not existing:
            logger.info("No customers found — auto-seeding Customer 360 data for %s...", settings.brand_name)
            from app.seed_data_customers import create_brand_customers
            _link_apps_to_customers(settings.app.storage_root)
            count = create_brand_customers(settings.app.storage_root)
            logger.info("Auto-seeded %d customers on startup", count)
        else:
            logger.info("Found %d existing customers — skipping auto-seed", len(existing))
            # Remediate wrongly-affiliated apps (fix leaks from the old loose matcher)
            _remediate_external_references(settings.app.storage_root)
    except Exception as e:
        logger.warning("Customer 360 auto-seed failed (non-fatal): %s", e)

    from app.agents.runtime import warmup_chat

    app.state.chat_runtime = await warmup_chat(settings)


@app.on_event("shutdown")
async def shutdown_event():
    from app.agents.runtime import shutdown_chat

    app.state.chat_runtime = None
    await shutdown_chat()


@app.get("/api/health/chat")
async def health_check_chat():
    ready = getattr(app.state, "chat_runtime", None) is not None
    return JSONResponse(
        status_code=200 if ready else 503,
        content={"status": "ready" if ready else "not_ready"},
    )


# Pydantic models for API responses
class ApplicationListItem(BaseModel):
    id: str
    created_at: Optional[str]
    external_reference: Optional[str]
    status: str
    persona: Optional[str] = None
    summary_title: Optional[str] = None
    processing_status: Optional[str] = None
    protected: bool = False
    file_count: int = 0
    key_fields: Optional[Dict[str, str]] = None


class AnalyzeRequest(BaseModel):
    sections: Optional[List[str]] = None
    processing_mode: Optional[str] = None  # 'auto', 'standard', or 'large_document'
    language: Optional[str] = None  # UI locale (fr/en) — controls LLM response language


class ChatMessage(BaseModel):
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: Optional[str] = None


class ChatRequest(BaseModel):
    stream: bool = False
    message: str
    history: Optional[List[ChatMessage]] = None
    application_id: Optional[str] = None
    conversation_id: Optional[str] = None  # If provided, continues existing conversation
    persona: Optional[str] = None  # Persona for RAG context (underwriting, life_health_claims, automotive_claims, property_casualty_claims)
    agent_type: Optional[str] = "auto"  # UI routing hint (auto, data, policy, analysis, dashboard, fraud)
    use_corrections: Optional[bool] = True  # Enable/disable few-shot corrections injection
    language: Optional[str] = "en"  # UI locale (fr/en) — controls agent response language


class ConversationSummary(BaseModel):
    id: str
    application_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int
    preview: Optional[str] = None


class Conversation(BaseModel):
    id: str
    application_id: str
    title: str
    created_at: str
    updated_at: str
    messages: List[ChatMessage]


# =============================================================================
# Mortgage Underwriting API Models
# =============================================================================

class MortgageBorrowerInfo(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    sin_hash: Optional[str] = None


class MortgageIncomeInfo(BaseModel):
    employment_type: Optional[str] = None
    annual_salary: Optional[float] = None


class MortgagePropertyInfo(BaseModel):
    address: Optional[str] = None
    purchase_price: Optional[float] = None
    property_type: Optional[str] = None


class MortgageLoanInfo(BaseModel):
    amount: Optional[float] = None
    amortization_years: Optional[int] = None
    rate: Optional[float] = None


class MortgageAnalyzeRequest(BaseModel):
    application_id: str
    borrower: Optional[MortgageBorrowerInfo] = None
    income: Optional[MortgageIncomeInfo] = None
    property: Optional[MortgagePropertyInfo] = None
    loan: Optional[MortgageLoanInfo] = None


class MortgageQueryRequest(BaseModel):
    application_id: Optional[str] = None
    query: str
    persona: Optional[str] = "mortgage_underwriting"


class MortgageApplicationCreate(BaseModel):
    borrower: Optional[MortgageBorrowerInfo] = None


class MortgageChatRequest(BaseModel):
    query: str
    persona: Optional[str] = "mortgage_underwriting"
    stream: Optional[bool] = False
    language: Optional[str] = "en"  # UI locale (fr/en) — controls LLM response language


class DecisionRequest(BaseModel):
    decision: str  # approve, approve_with_conditions, defer, decline
    notes: Optional[str] = None
    conditions: Optional[str] = None
    risk_level: Optional[str] = None


def application_to_dict(app_md: ApplicationMetadata) -> dict:
    """Convert ApplicationMetadata to JSON-serializable dict."""
    return {
        "id": app_md.id,
        "created_at": app_md.created_at,
        "external_reference": app_md.external_reference,
        "status": app_md.status,
        "persona": app_md.persona,
        "files": [
            {"filename": f.filename, "path": f.path, "url": f.url}
            for f in app_md.files
        ],
        "document_markdown": app_md.document_markdown,
        "markdown_pages": app_md.markdown_pages,
        "cu_raw_result_path": app_md.cu_raw_result_path,
        "llm_outputs": app_md.llm_outputs,
        "extracted_fields": app_md.extracted_fields,
        "confidence_summary": app_md.confidence_summary,
        "analyzer_id_used": app_md.analyzer_id_used,
        "extraction_provenance": app_md.extraction_provenance,
        "risk_analysis": app_md.risk_analysis,
        "processing_status": app_md.processing_status,
        "processing_error": app_md.processing_error,
        # Sentiment analysis (Sentiment Agent)
        "sentiment_analysis": app_md.sentiment_analysis,
        # Fraud analysis
        "fraud_analysis": app_md.fraud_analysis,
        # Context labels (backend-driven badges/alerts)
        "context_labels": app_md.context_labels,
        # Context tasks (backend-driven action items)
        "context_tasks": app_md.context_tasks,
        # Large document processing fields
        "processing_mode": app_md.processing_mode,
        "condensed_context": app_md.condensed_context,
        "document_stats": app_md.document_stats,
        "batch_summaries": app_md.batch_summaries,
        "orchestration": app_md.orchestration,
    }


# ============================================================================
# Background Processing Helpers
# ============================================================================

# Limit concurrent CU/LLM processing to avoid rate-limiting the shared
# completion deployment used by the Content Understanding analyzer.
_processing_semaphore = asyncio.Semaphore(1)

# Processing progress tracking for SSE (app_id -> progress dict)
_processing_progress: Dict[str, Dict[str, Any]] = {}


@app.get("/api/applications/{app_id}/progress")
async def stream_processing_progress(app_id: str, request: Request):
    """SSE endpoint for real-time processing progress.

    Streams events as the processing pipeline progresses through stages:
    extracting, file-extracted, analyzing, completed, error.
    Client connects once and receives events until processing completes.
    """
    async def event_generator():
        last_status = None
        last_progress = None
        idle_count = 0
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break
            # Check progress dict first, then fall back to metadata
            progress = _processing_progress.get(app_id)
            if progress:
                status = progress.get("status")
                if progress != last_progress:
                    last_progress = progress.copy()
                    yield f"data: {json.dumps(progress)}\n\n"
                if status in ("completed", "error"):
                    break
            else:
                # Fallback: check metadata on disk
                try:
                    app_md = load_application(load_settings().app.storage_root, app_id)
                    if app_md:
                        status = app_md.processing_status or ("completed" if app_md.status == "completed" else "idle")
                        if status != last_status:
                            last_status = status
                            yield f"data: {json.dumps({'status': status, 'app_status': app_md.status})}\n\n"
                        if status in (None, "completed", "error") and app_md.status in ("completed", "error"):
                            idle_count += 1
                            if idle_count >= 2:
                                yield f"data: {json.dumps({'status': 'done'})}\n\n"
                                break
                except Exception:
                    pass
            await asyncio.sleep(1.5)
        # Cleanup
        _processing_progress.pop(app_id, None)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _try_auto_affiliate_customer(app_md: ApplicationMetadata, storage_root: str) -> None:
    """Try to auto-affiliate an application to a Customer 360 profile.

    Matches by insured name extracted from the dossier against existing
    customer profiles. Only sets external_reference if currently empty.
    Also adds a journey event to the matched customer.
    """
    if app_md.external_reference:
        return  # Already affiliated

    ef = app_md.extracted_fields or {}
    # Extract insured name from extracted fields
    name_fields = ["NomAssure", "AssuréNom", "NomSouscripteur", "InsuredName",
                   "ApplicantName", "PatientName", "assure", "beneficiaire",
                   "emprunteur", "Conducteur"]
    insured_name = ""
    for target in name_fields:
        entry = ef.get(target)
        if not entry:
            for fk, fv in ef.items():
                if fk.endswith(f":{target}"):
                    entry = fv
                    break
        if entry:
            insured_name = str(entry.get("value", entry) if isinstance(entry, dict) else entry).strip()
            if insured_name:
                break

    if not insured_name or len(insured_name) < 3:
        return

    try:
        from app.customer360 import list_customers, load_customer_journey, save_customer_journey, CustomerJourneyEvent
        customers = list_customers(storage_root)
        name_parts = [p.lower() for p in insured_name.split() if len(p) > 2]
        if not name_parts:
            return

        matched_customer = None
        for c in customers:
            c_name = (c.name if hasattr(c, 'name') else c.get("name", "")).lower()
            # Strict match: ALL name parts (≥3 chars) must appear in customer name
            matches = sum(1 for p in name_parts if p in c_name)
            if len(name_parts) >= 2 and matches == len(name_parts):
                matched_customer = c
                break

        if not matched_customer:
            return

        customer_id = matched_customer.id if hasattr(matched_customer, 'id') else matched_customer.get("id", "")
        if not customer_id:
            return

        # Set external_reference on the application
        app_md.external_reference = customer_id
        save_application_metadata(storage_root, app_md)
        logger.info("Auto-affiliated app %s to customer %s (matched name: %s)",
                     app_md.id, customer_id, insured_name)

        # Add journey event to the customer
        existing_events = load_customer_journey(storage_root, customer_id)
        # Check if this app_id already has a journey event
        if any(e.application_id == app_md.id for e in existing_events):
            return

        persona_event_map = {
            "habitation_claims": ("sinistre_habitation", "Sinistre habitation"),
            "automotive_claims": ("sinistre_auto", "Sinistre auto"),
            "life_health_claims": ("sinistre_sante", "Sinistre santé"),
            "underwriting": ("souscription", "Souscription"),
            "mortgage_underwriting": ("demande_pret", "Demande prêt immobilier"),
        }
        event_type, title_prefix = persona_event_map.get(app_md.persona or "", ("dossier", "Dossier"))

        # Try to get nature from extracted fields
        nature = ""
        for nt in ["NatureSinistre", "CauseOfLoss", "CauseDuSinistre"]:
            n_entry = ef.get(nt)
            if not n_entry:
                for fk, fv in ef.items():
                    if fk.endswith(f":{nt}"):
                        n_entry = fv
                        break
            if n_entry:
                nature = str(n_entry.get("value", n_entry) if isinstance(n_entry, dict) else n_entry).strip()
                if nature:
                    break

        title = f"{title_prefix} — {nature}" if nature else title_prefix

        new_event = CustomerJourneyEvent(
            date=app_md.created_at[:10] if app_md.created_at else datetime.now(UTC).strftime("%Y-%m-%d"),
            persona=app_md.persona or "",
            application_id=app_md.id,
            event_type=event_type,
            title=title,
            summary=f"Dossier {app_md.id} — {len(app_md.files or [])} fichier(s).",
            status=app_md.status or "en_cours",
            risk_level="medium",
        )
        existing_events.append(new_event)
        save_customer_journey(storage_root, customer_id, existing_events)
        logger.info("Added journey event for app %s to customer %s", app_md.id, customer_id)

    except Exception as e:
        logger.warning("Auto-affiliation failed for %s: %s", app_md.id, e)


def _handle_task_exception(task: asyncio.Task):
    """Callback to log exceptions from background tasks."""
    try:
        exc = task.exception()
        if exc:
            logger.error("Background task failed with exception: %s", exc, exc_info=exc)
    except asyncio.CancelledError:
        pass


async def run_extraction_background(app_id: str, language: Optional[str] = None):
    """Run content extraction in background and update status."""
    async with _processing_semaphore:
        # Capture diagnostic context up-front so the except block can include it in
        # the user-facing processing_error even if loading settings later fails.
        diag_ctx: Dict[str, Any] = {
            "brand": os.getenv("BRAND_NAME", "?"),
            "cu_completion": os.getenv("AZURE_CONTENT_UNDERSTANDING_COMPLETION_DEPLOYMENT") or "<default:gpt-5.4-mini>",
            "cu_embedding": os.getenv("AZURE_CONTENT_UNDERSTANDING_EMBEDDING_DEPLOYMENT") or "<default:text-embedding-3-large>",
            "cu_api_version": os.getenv("AZURE_CONTENT_UNDERSTANDING_API_VERSION") or "<default:2025-11-01>",
            "analyzer_id": None,
            "persona": None,
            "file_count": 0,
        }
        try:
            logger.info("Starting background extraction for application %s", app_id)
            settings = load_settings()
            app_md = load_application(settings.app.storage_root, app_id)
            if not app_md:
                logger.error("Background extraction: Application %s not found", app_id)
                return

            # Enrich diagnostic context now that we have settings + app_md.
            diag_ctx["persona"] = app_md.persona
            diag_ctx["file_count"] = len(app_md.files or [])
            diag_ctx["analyzer_id"] = settings.content_understanding.analyzer_id
            try:
                if app_md.persona:
                    persona_config = get_persona_config(app_md.persona)
                    persona_analyzer = getattr(persona_config, "custom_analyzer_id", None)
                    if persona_analyzer:
                        diag_ctx["analyzer_id"] = persona_analyzer
            except Exception:  # noqa: BLE001
                pass

            # Per-extraction breadcrumb: what we are about to send to CU. Logged on a
            # single INFO line so it shows up alongside any failure that follows it.
            try:
                file_summary = [
                    {
                        "name": getattr(f, "filename", "?"),
                        "size_kb": round((getattr(f, "size_bytes", 0) or 0) / 1024, 1),
                    }
                    for f in (app_md.files or [])
                ]
            except Exception:  # noqa: BLE001
                file_summary = []
            logger.info(
                "[CU-EXTRACT] app_id=%s persona=%s brand=%s file_count=%d analyzer_id=%s "
                "completion=%s embedding=%s api_version=%s files=%s",
                app_id,
                diag_ctx["persona"],
                settings.brand_name,
                diag_ctx["file_count"],
                diag_ctx["analyzer_id"],
                diag_ctx["cu_completion"],
                diag_ctx["cu_embedding"],
                diag_ctx["cu_api_version"],
                json.dumps(file_summary, ensure_ascii=False)[:1000],
            )

            # Update status to extracting
            app_md.processing_status = "extracting"
            app_md.processing_error = None
            app_md.status = "extracting"
            save_application_metadata(settings.app.storage_root, app_md)

            # Run extraction in thread pool
            logger.info("Running content understanding for application %s", app_id)
            app_md = await asyncio.to_thread(
                run_content_understanding_for_files, settings, app_md, language=language
            )
            
            # Update status and save
            app_md.processing_status = None
            app_md.processing_error = None
            app_md.status = "extracted"
            save_application_metadata(settings.app.storage_root, app_md)

            # Auto-affiliate to Customer 360 if a matching profile exists
            _try_auto_affiliate_customer(app_md, settings.app.storage_root)

            logger.info("Background extraction completed for application %s", app_id)

        except Exception as e:
            logger.error(
                "[CU-EXTRACT] FAILED app_id=%s persona=%s brand=%s analyzer=%s completion=%s embedding=%s: %s",
                app_id,
                diag_ctx.get("persona"),
                diag_ctx.get("brand"),
                diag_ctx.get("analyzer_id"),
                diag_ctx.get("cu_completion"),
                diag_ctx.get("cu_embedding"),
                e,
                exc_info=True,
            )
            try:
                settings = load_settings()
                app_md = load_application(settings.app.storage_root, app_id)
                if app_md:
                    # Prefix processing_error with analyzer/deployment context so the
                    # red ProcessingBanner becomes self-diagnosing instead of opaque.
                    raw_err = str(e)
                    if len(raw_err) > 400:
                        raw_err = raw_err[:400] + " …[truncated]"
                    prefix = (
                        f"[analyzer={diag_ctx.get('analyzer_id') or '?'} "
                        f"completion={diag_ctx.get('cu_completion')} "
                        f"embedding={diag_ctx.get('cu_embedding')}] "
                    )
                    app_md.processing_status = "error"
                    app_md.processing_error = prefix + raw_err
                    app_md.status = "error"
                    save_application_metadata(settings.app.storage_root, app_md)
            except Exception:
                pass


async def run_analysis_background(app_id: str, sections: Optional[List[str]] = None, processing_mode: Optional[str] = None, language: Optional[str] = None):
    """Run analysis in background and update status."""
    async with _processing_semaphore:
        try:
            logger.info("Starting background analysis for application %s (mode: %s)", app_id, processing_mode or "auto")
            settings = load_settings()
            app_md = load_application(settings.app.storage_root, app_id)
            if not app_md:
                logger.error("Background analysis: Application %s not found", app_id)
                return

            # Update status to analyzing
            app_md.processing_status = "analyzing"
            app_md.processing_error = None
            app_md.status = "analyzing"
            save_application_metadata(settings.app.storage_root, app_md)

            # Run analysis in thread pool
            logger.info("Running underwriting prompts for application %s", app_id)
            app_md = await asyncio.to_thread(
                run_underwriting_prompts,
                settings,
                app_md,
                sections_to_run=sections,
                max_workers_per_section=4,
                processing_mode_override=processing_mode,
                language=language,
            )
            
            # Update status and save
            app_md.processing_status = None
            app_md.processing_error = None
            app_md.status = "completed"

            # Generate context labels + tasks from analysis output
            try:
                from app.processing import generate_context_labels, generate_context_tasks
                app_md.context_labels = generate_context_labels(app_md)
                app_md.context_tasks = generate_context_tasks(app_md)
            except Exception:
                logger.debug("Context label generation failed in re-analysis for %s", app_id, exc_info=True)

            save_application_metadata(settings.app.storage_root, app_md)

            # Re-run Sentiment Agent after re-analysis (score may change with new data)
            try:
                from app.openai_client import chat_completion
                import json as _json

                ef = app_md.extracted_fields or {}
                llm = app_md.llm_outputs or {}
                context_parts = ["=== DOSSIER ==="]
                for ek, ev in list(ef.items())[:20]:
                    fn = ek.split(":")[-1] if ":" in ek else ek
                    val = ev.get("value", ev) if isinstance(ev, dict) else ev
                    context_parts.append(f"{fn}: {val}")
                if llm:
                    context_parts.append("\n=== ANALYSE IA ===")
                    for section, subsections in llm.items():
                        if not subsections or not isinstance(subsections, dict):
                            continue
                        for sub, output in subsections.items():
                            parsed = output.get("parsed", {}) if output else {}
                            for fld in ("summary", "synthese", "conclusion"):
                                val_ = parsed.get(fld, "")
                                if val_ and isinstance(val_, str):
                                    context_parts.append(f"{section}/{sub}: {val_[:200]}")
                                    break
                if app_md.fraud_analysis:
                    fa_oa = app_md.fraud_analysis.get("overall_assessment", {})
                    context_parts.append(f"\nFraude: {fa_oa.get('overall_fraud_risk', 'N/A')} ({round(fa_oa.get('risk_score', 0) * 100)}%)")
                context_parts.append(f"\nPersona: {app_md.persona}")
                context_parts.append(f"Fichiers: {len(app_md.files or [])}")

                brand = settings.brand_name
                sentiment_prompt = (
                    f"Tu es l'Agent Sentiment. Analyse le dossier pour conseiller le gestionnaire "
                    f"{brand} sur le ton et l'accompagnement. Valeurs : proximité, contact humain, entraide.\n"
                    "Réponds en JSON: {score:int 0-100, level:calm|moderate|stressed|critical, "
                    "suggestedTone:empathetic|standard|formal, daysSinceClaim:int|null, "
                    "contextSummary:str, factors:[str], suggestions:[str]}"
                )
                raw = chat_completion(
                    settings.openai,
                    [{"role": "system", "content": sentiment_prompt},
                     {"role": "user", "content": "\n".join(context_parts)}],
                    max_tokens=600, temperature=0.1, response_format="json_object",
                )
                content = raw.get("content", "")
                if content:
                    sa = _json.loads(content)
                    app_md.sentiment_analysis = {
                        **sa, "agent": f"Sentiment Agent ({brand})",
                        "computed_at": datetime.now(UTC).isoformat(),
                    }
                    save_application_metadata(settings.app.storage_root, app_md)
                    logger.info("Sentiment re-computed after analysis for %s: score=%s", app_id, sa.get("score"))
            except Exception as se:
                logger.warning("Sentiment re-computation failed for %s: %s", app_id, se)

            logger.info("Background analysis completed for application %s (mode: %s)", app_id, app_md.processing_mode)

        except Exception as e:
            logger.error("Background analysis failed for %s: %s", app_id, e, exc_info=True)
            try:
                settings = load_settings()
                app_md = load_application(settings.app.storage_root, app_id)
                if app_md:
                    app_md.processing_status = "error"
                    app_md.processing_error = str(e)
                    app_md.status = "error"
                    save_application_metadata(settings.app.storage_root, app_md)
            except Exception:
                pass


async def run_extract_and_analyze_background(app_id: str, processing_mode: Optional[str] = None, language: Optional[str] = None):
    """Run both extraction and analysis in background."""
    logger.info("Starting full background processing for application %s (mode: %s)", app_id, processing_mode or "auto")
    await run_extraction_background(app_id, language=language)
    
    # Check if extraction succeeded before continuing
    settings = load_settings()
    app_md = load_application(settings.app.storage_root, app_id)
    if app_md and app_md.processing_status != "error" and app_md.document_markdown:
        # Bridge status to "analyzing" immediately to prevent null gap
        # that stops frontend polling between extraction and analysis
        app_md.processing_status = "analyzing"
        save_application_metadata(settings.app.storage_root, app_md)
        await run_analysis_background(app_id, processing_mode=processing_mode)
    else:
        logger.warning("Skipping analysis for %s - extraction failed or no content", app_id)


# =============================================================================
# Persona-Aware Chat Prompts
# =============================================================================

PERSONA_CHAT_CONFIG = {
    "underwriting": {
        "role": "expert life insurance underwriter assistant",
        "context_type": "underwriting policies",
        "item_type": "application",
        "decision_type": "underwriting decisions",
        "example_policy_id": "CVD-BP-001",
    },
    "life_health_claims": {
        "role": "expert life and health insurance claims analyst",
        "context_type": "claims processing policies",
        "item_type": "claim",
        "decision_type": "claims processing decisions",
        "example_policy_id": "HC-COV-001",
    },
    "automotive_claims": {
        "role": "expert automotive insurance claims analyst",
        "context_type": "auto claims policies",
        "item_type": "claim",
        "decision_type": "claims processing decisions",
        "example_policy_id": "DMG-SEV-001",
    },
    "property_casualty_claims": {
        "role": "expert property and casualty claims analyst",
        "context_type": "property & casualty policies",
        "item_type": "claim",
        "decision_type": "claims processing decisions",
        "example_policy_id": "PC-COV-001",
    },
    "habitation_claims": {
        "role": "expert en sinistres habitation spécialisé dans les dégâts des eaux et tempêtes en France",
        "context_type": "politiques sinistres habitation MRH",
        "item_type": "sinistre habitation",
        "decision_type": "décisions de règlement sinistre",
        "example_policy_id": "HAB-DDE-001",
    },
    "mortgage_underwriting": {
        "role": "expert en souscription de crédit immobilier français, spécialiste des recommandations HCSF",
        "context_type": "politiques de souscription hypothécaire incluant les recommandations HCSF et la réglementation ACPR",
        "item_type": "dossier de prêt immobilier",
        "decision_type": "décisions de souscription hypothécaire",
        "example_policy_id": "HCSF-ENDETT-001",
    },
}


# ============================================================================
# Persona APIs
# ============================================================================


# ============================================================================
# Persona APIs
# ============================================================================

@app.get("/api/personas")
async def get_personas():
    """List all available personas."""
    try:
        personas = list_personas()
        return {"personas": personas}
    except Exception as e:
        logger.error("Failed to list personas: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/personas/{persona_id}")
async def get_persona(persona_id: str):
    """Get configuration for a specific persona."""
    try:
        config = get_persona_config(persona_id)
        return {
            "id": config.id,
            "name": config.name,
            "description": config.description,
            "icon": config.icon,
            "color": config.color,
            "enabled": config.enabled,
            "prompt_sections": list(config.default_prompts.keys()) if config.default_prompts else [],
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to get persona %s: %s", persona_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/applications")
async def get_applications(
    persona: Optional[str] = None,
    page: Optional[int] = None,
    limit: Optional[int] = None,
):
    """List all applications, optionally filtered by persona.
    
    Supports optional pagination:
    - Without page/limit: Returns all applications (backward compatible)
    - With page/limit: Returns paginated response with metadata
    
    Query Parameters:
        persona: Filter by persona ID
        page: Page number (1-indexed, requires limit)
        limit: Items per page (requires page)
    """
    try:
        settings = load_settings()
        apps = list_applications(settings.app.storage_root, persona=persona)
        
        # Convert to response items
        PROTECTED_APP_IDS = {"f6001447", "259db12b"}
        items = [
            ApplicationListItem(
                id=a["id"],
                created_at=a.get("created_at"),
                external_reference=a.get("external_reference"),
                status=a.get("status", "unknown"),
                persona=a.get("persona"),
                summary_title=a.get("summary_title"),
                processing_status=a.get("processing_status"),
                protected=a["id"] in PROTECTED_APP_IDS,
                file_count=a.get("file_count", 0),
                key_fields=a.get("key_fields"),
            )
            for a in apps
        ]
        
        # If pagination params provided, return paginated response
        if page is not None and limit is not None:
            if page < 1:
                page = 1
            if limit < 1:
                limit = 10
            
            total = len(items)
            start = (page - 1) * limit
            end = start + limit
            paginated_items = items[start:end]
            
            return {
                "items": paginated_items,
                "page": page,
                "limit": limit,
                "total": total,
                "hasMore": end < total,
            }
        
        # No pagination - return full list (backward compatible)
        return items
    except Exception as e:
        logger.error("Failed to list applications: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/applications/{app_id}")
async def get_application(app_id: str):
    """Get detailed application metadata."""
    try:
        settings = load_settings()
        app_md = load_application(settings.app.storage_root, app_id)
        if not app_md:
            raise HTTPException(status_code=404, detail="Dossier introuvable")

        # Lazy-generate context labels/tasks if missing (dossiers processed before this feature)
        # Note: runs in a try/except to never crash the GET endpoint
        if app_md.status in ("extracted", "completed") and not app_md.context_labels:
            try:
                from app.processing import generate_context_labels, generate_context_tasks
                labels = generate_context_labels(app_md)
                tasks = generate_context_tasks(app_md)
                if labels:
                    app_md.context_labels = labels
                    app_md.context_tasks = tasks or []
                    try:
                        save_application_metadata(settings.app.storage_root, app_md)
                    except Exception:
                        pass  # Non-critical — labels will regenerate next time
            except Exception as label_err:
                logger.warning("Lazy context label generation failed for %s: %s", app_id, label_err)

        payload = application_to_dict(app_md)

        # Enrich with live Souscr'IA front-office context when this dossier
        # originated from a Souscr'IA conversation (external_reference == thread_id).
        # Read-only and best-effort: never blocks the event loop or breaks the GET.
        try:
            from app.souscria_mcp_client import fetch_risk_context

            souscria_context = await asyncio.to_thread(
                fetch_risk_context, app_md.external_reference
            )
            if souscria_context is not None:
                payload["souscria_context"] = souscria_context
        except Exception as sc_err:
            logger.warning("Souscr'IA context enrichment failed for %s: %s", app_id, sc_err)

        return payload
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to load application %s: %s", app_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/applications/{app_id}/souscria-context")
async def get_application_souscria_context(app_id: str):
    """Live-refresh the Souscr'IA front-office risk context for a dossier.

    Reuses the same read-only ``fetch_risk_context`` path as the detail endpoint
    but on demand (the "Rafraîchir" button). Returns ``null`` when the dossier has
    no Souscr'IA thread reference or the connector is not configured.
    """
    settings = load_settings()
    app_md = load_application(settings.app.storage_root, app_id)
    if not app_md:
        raise HTTPException(status_code=404, detail="Dossier introuvable")
    try:
        from app.souscria_mcp_client import fetch_risk_context

        return await asyncio.to_thread(fetch_risk_context, app_md.external_reference)
    except Exception as sc_err:
        logger.warning("Souscr'IA context refresh failed for %s: %s", app_id, sc_err)
        return None


@app.delete("/api/applications/{app_id}")
async def delete_application_endpoint(app_id: str):
    """Delete an application and all its associated files.
    
    This permanently removes the application, uploaded files, and all
    processing results. This action cannot be undone.
    Protected demo applications cannot be deleted.
    """
    # Demo applications that must never be deleted
    PROTECTED_APP_IDS = {"f6001447", "259db12b"}
    
    if app_id in PROTECTED_APP_IDS:
        raise HTTPException(
            status_code=403,
            detail="Ce dossier est protégé (démo). Il ne peut pas être supprimé."
        )
    
    from app.storage import delete_application
    
    try:
        settings = load_settings()
        
        # Check if application exists first
        app_md = load_application(settings.app.storage_root, app_id)
        if not app_md:
            raise HTTPException(status_code=404, detail="Dossier introuvable")
        
        # Delete the application
        success = delete_application(settings.app.storage_root, app_id)
        if not success:
            raise HTTPException(status_code=500, detail="Échec de la suppression du dossier")
        
        # Clean up journey events referencing this app in Customer 360
        if app_md.external_reference:
            try:
                from app.customer360 import load_customer_journey, save_customer_journey
                events = load_customer_journey(settings.app.storage_root, app_md.external_reference)
                cleaned = [e for e in events if e.application_id != app_id]
                if len(cleaned) < len(events):
                    save_customer_journey(settings.app.storage_root, app_md.external_reference, cleaned)
                    logger.info("Removed %d journey event(s) for deleted app %s from customer %s",
                                len(events) - len(cleaned), app_id, app_md.external_reference)
            except Exception as je:
                logger.warning("Failed to clean journey events for deleted app %s: %s", app_id, je)

        logger.info("Deleted application: %s", app_id)
        return {"message": "Application deleted", "id": app_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete application %s: %s", app_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


VALID_DECISIONS = {"approve", "approve_with_conditions", "defer", "decline"}


@app.put("/api/applications/{app_id}/decision")
async def submit_application_decision(app_id: str, body: DecisionRequest):
    """Record an underwriter/adjuster decision for an application.

    This stores the decision (approve / approve_with_conditions / defer / decline)
    together with optional notes and conditions on the application metadata,
    and — when a claim_assessment row exists — also persists in PostgreSQL.
    """
    if body.decision not in VALID_DECISIONS:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid decision '{body.decision}'. Must be one of: {', '.join(sorted(VALID_DECISIONS))}",
        )

    try:
        settings = load_settings()
        app_md = load_application(settings.app.storage_root, app_id)
        if not app_md:
            raise HTTPException(status_code=404, detail="Dossier introuvable")

        # Persist decision in application metadata (JSON/Blob)
        if app_md.llm_outputs is None:
            app_md.llm_outputs = {}

        decided_at = datetime.now(UTC).isoformat()
        app_md.llm_outputs["decision"] = {
            "decision": body.decision,
            "notes": body.notes,
            "conditions": body.conditions,
            "risk_level": body.risk_level,
            "decided_at": decided_at,
        }
        mark_reviewed(app_md, decision=body.decision, decided_at=decided_at)
        save_application_metadata(settings.app.storage_root, app_md)

        # Also persist in claim_assessments if the row exists (claims personas)
        pg_updated = False
        try:
            from app.multimodal.repository import ClaimsMediaRepository
            repo = ClaimsMediaRepository()
            pg_updated = await repo.update_adjuster_decision(
                claim_id=app_id,
                decision=body.decision,
                notes=body.notes,
            )
        except Exception as pg_err:
            logger.debug("No PG claim_assessment to update for %s: %s", app_id, pg_err)

        # Run validation agent — compare human decision vs AI recommendation
        validation_result = None
        ai_rec = None
        try:
            from app.agents.validation import validate_decision
            if app_md.llm_outputs:
                # Try claim assessment recommendation first, then risk analysis
                ai_rec = app_md.llm_outputs.get("overall_recommendation")
                if not ai_rec and app_md.risk_analysis:
                    parsed = app_md.risk_analysis.get("parsed", {})
                    ai_rec = parsed.get("overall_risk_level")
            validation_result = await validate_decision(
                application_id=app_id,
                persona=app_md.persona or "unknown",
                human_decision=body.decision,
                ai_recommendation=ai_rec,
                risk_level=body.risk_level,
                notes=body.notes,
            )
        except Exception as val_err:
            logger.debug("Validation agent skipped for %s: %s", app_id, val_err)

        # ── Append decision to action_history for timeline audit trail ──
        decision_labels = {
            "approve": "Décision : Approuvé",
            "approve_with_conditions": "Décision : Approuvé sous conditions",
            "defer": "Décision : Différé",
            "decline": "Décision : Refusé",
        }
        divergence = None
        if validation_result and isinstance(validation_result, dict):
            divergence = validation_result.get("divergence_level")

        workbench_system = get_current_brand_profile().app_name
        action_entry = {
            "action_id": str(uuid.uuid4()),
            "label": decision_labels.get(body.decision, f"Décision : {body.decision}"),
            "performed": "HITL",
            "at": decided_at,
            "source": workbench_system,
            "systems": [workbench_system] + (["Validation Agent"] if validation_result else []),
            "decision": body.decision,
            "notes": body.notes,
            "conditions": body.conditions if body.decision == "approve_with_conditions" else None,
            "risk_level": body.risk_level,
            "ai_recommendation": ai_rec,
            "validation_divergence": divergence,
        }
        if app_md.action_history is None:
            app_md.action_history = []
        app_md.action_history.append(action_entry)
        save_application_metadata(settings.app.storage_root, app_md)

        # Sync decision columns to applications_summary for Fabric CDC
        try:
            from app.database.pool import get_pool
            pool = await get_pool()
            async with pool.acquire() as conn:
                await conn.execute(
                    """UPDATE workbenchiq.applications_summary
                       SET adjuster_decision = $2, decided_at = $3, updated_at = CURRENT_TIMESTAMP
                       WHERE app_id = $1 AND brand = $4""",
                    app_id,
                    body.decision,
                    datetime.now(UTC),
                    settings.brand_name,
                )
        except Exception as pg_sync_err:
            logger.debug("applications_summary decision sync skipped for %s: %s", app_id, pg_sync_err)

        logger.info("Decision '%s' recorded for application %s (pg=%s, action_history=%d)",
                     body.decision, app_id, pg_updated, len(app_md.action_history))
        return {
            "application_id": app_id,
            "decision": body.decision,
            "persisted_pg": pg_updated,
            "validation": validation_result,
            "action_history_entry": action_entry,
            "message": "Decision recorded",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to save decision for %s: %s", app_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/validation/stats")
async def get_validation_stats(persona: Optional[str] = None):
    """Return aggregated decision validation statistics."""
    try:
        from app.agents.validation import get_divergence_stats
        stats = await get_divergence_stats(persona)
        return stats
    except Exception as e:
        logger.error("Failed to get validation stats: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/applications/{app_id}/files/{filename:path}")
async def get_application_file(app_id: str, filename: str, request: Request):
    """Serve a file from an application's files directory.
    
    Supports HTTP Range requests for video/audio streaming.
    """
    from fastapi.responses import Response
    
    try:
        settings = load_settings()
        
        # Security: prevent path traversal
        if ".." in filename or filename.startswith("/"):
            raise HTTPException(status_code=403, detail="Accès refusé")
        
        # Load file using storage provider (supports both local and Azure Blob)
        file_content = load_file(settings.app.storage_root, app_id, filename)
        
        if file_content is None:
            raise HTTPException(status_code=404, detail="Fichier introuvable")
        
        # Determine media type from filename
        suffix = Path(filename).suffix.lower()
        media_types = {
            ".pdf": "application/pdf",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".tiff": "image/tiff",
            ".webp": "image/webp",
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".avi": "video/x-msvideo",
            ".mkv": "video/x-matroska",
            ".webm": "video/webm",
        }
        media_type = media_types.get(suffix, "application/octet-stream")
        total_size = len(file_content)
        
        # Base headers for all file types
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(total_size),
        }
        
        if suffix == ".pdf":
            headers["Content-Disposition"] = f"inline; filename=\"{filename}\""
            headers["X-Content-Type-Options"] = "nosniff"
        
        # Handle Range requests (required for video/audio streaming)
        range_header = request.headers.get("range")
        if range_header:
            try:
                range_spec = range_header.replace("bytes=", "").split("-")
                start = int(range_spec[0]) if range_spec[0] else 0
                end = int(range_spec[1]) if range_spec[1] else total_size - 1
                end = min(end, total_size - 1)
                
                if start >= total_size:
                    raise HTTPException(status_code=416, detail="Plage non satisfaisable")
                
                headers["Content-Range"] = f"bytes {start}-{end}/{total_size}"
                headers["Content-Length"] = str(end - start + 1)
                
                return Response(
                    content=file_content[start:end + 1],
                    status_code=206,
                    media_type=media_type,
                    headers=headers,
                )
            except (ValueError, IndexError):
                pass  # Invalid range, fall through to full response
        
        return Response(
            content=file_content,
            media_type=media_type,
            headers=headers,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to serve file %s for app %s: %s", filename, app_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/applications")
async def create_application(
    files: List[UploadFile] = File(...),
    external_reference: Optional[str] = Form(None),
    persona: Optional[str] = Form(None),
):
    """Create a new application with uploaded PDF files."""
    try:
        if not files:
            raise HTTPException(status_code=400, detail="Aucun fichier fourni")

        # Validate file extensions against persona-supported formats
        target_persona = persona or "underwriting"
        for f in files:
            if f.filename:
                if not is_supported_file(f.filename, target_persona):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Unsupported file type for {target_persona}: {f.filename}",
                    )

        settings = load_settings()
        app_id = str(uuid.uuid4())[:8]

        # Read file contents asynchronously before passing to sync storage function
        file_data = []
        for f in files:
            content = await f.read()
            file_data.append({"name": f.filename, "content": content})

        # Save uploaded files
        stored_files = save_uploaded_files(
            settings.app.storage_root,
            app_id,
            file_data,
            public_base_url=settings.app.public_files_base_url,
        )

        # Create metadata with persona
        app_md = new_metadata(
            settings.app.storage_root,
            app_id,
            stored_files,
            external_reference=external_reference,
            persona=persona or "underwriting",  # Default to underwriting for backward compat
        )

        logger.info("Created application %s with %d files for persona %s", app_id, len(files), persona)
        return application_to_dict(app_md)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create application: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/applications/{app_id}/files")
async def add_files_to_application(
    app_id: str,
    files: List[UploadFile] = File(...),
    auto_process: bool = True,
):
    """Add files to an existing application.

    Appends new files to the application's file list and optionally
    re-triggers Content Understanding extraction + LLM analysis.

    Args:
        app_id: Application ID
        files: Files to upload
        auto_process: If True (default), re-run extraction + analysis in background
    """
    try:
        if not files:
            raise HTTPException(status_code=400, detail="Aucun fichier fourni")

        settings = load_settings()
        app_md = load_application(settings.app.storage_root, app_id)
        if not app_md:
            raise HTTPException(status_code=404, detail=f"Application {app_id} not found")

        # Validate file extensions
        for f in files:
            if f.filename:
                if not is_supported_file(f.filename, app_md.persona):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Unsupported file type for {app_md.persona or 'underwriting'}: {f.filename}",
                    )

        # Read file contents
        file_data = []
        for f in files:
            content = await f.read()
            file_data.append({"name": f.filename, "content": content})

        # Save new files to storage
        new_stored = save_uploaded_files(
            settings.app.storage_root,
            app_id,
            file_data,
            public_base_url=settings.app.public_files_base_url,
        )

        # Append to existing files list
        app_md.files.extend(new_stored)
        app_md.status = "uploaded"  # Reset status to trigger re-processing
        save_application_metadata(settings.app.storage_root, app_md)

        logger.info(
            "Added %d files to application %s (total: %d)",
            len(new_stored), app_id, len(app_md.files),
        )

        # Auto-trigger processing in background
        if auto_process:
            import asyncio
            asyncio.create_task(_process_background(app_id))

        return {
            "app_id": app_id,
            "new_files": len(new_stored),
            "total_files": len(app_md.files),
            "files": [{"name": sf.filename, "path": sf.path} for sf in app_md.files],
            "processing": auto_process,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to add files to %s: %s", app_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _process_background(app_id: str):
    """Run full processing pipeline in background after file addition.

    Pipeline: Extract → Analyze (LLM) → Sentiment Agent → PG sync
    Fraud analysis is NOT auto-triggered (requires explicit user action).
    Emits SSE progress events via _processing_progress dict.
    """
    def _emit(status: str, **extra):
        _processing_progress[app_id] = {"status": status, "app_id": app_id, **extra}

    try:
        logger.info("Background processing started for %s", app_id)
        settings = load_settings()
        app_md = load_application(settings.app.storage_root, app_id)
        if not app_md:
            return
        total_files = len(app_md.files)
        app_md.processing_status = "extracting"
        save_application_metadata(settings.app.storage_root, app_md)
        _emit("extracting", total_files=total_files, files_done=0,
              message=f"Extraction de {total_files} fichier(s)…")

        # Step 1: Content Understanding extraction (incremental — skips already-extracted files)
        from app.processing import run_content_understanding_for_files, run_underwriting_prompts

        # Count already-extracted files to report accurate progress
        already_done = sum(1 for f in app_md.files if getattr(f, 'extracted', False))
        _emit("extracting", total_files=total_files, files_done=already_done,
              message=f"Extraction : {already_done}/{total_files} fichier(s)")

        await asyncio.to_thread(run_content_understanding_for_files, settings, app_md)

        # Save extraction results
        app_md.status = "extracted"
        app_md.processing_status = "analyzing"
        save_application_metadata(settings.app.storage_root, app_md)
        _emit("analyzing", total_files=total_files, files_done=total_files,
              message="Analyse IA en cours…")

        # Step 2: LLM analysis (damage, liability, payout, risk)
        await asyncio.to_thread(run_underwriting_prompts, settings, app_md)

        # Step 2b: Generate context labels + tasks from analysis output
        from app.processing import generate_context_labels, generate_context_tasks
        app_md.context_labels = generate_context_labels(app_md)
        app_md.context_tasks = generate_context_tasks(app_md)

        # Save LLM results
        app_md.status = "completed"
        save_application_metadata(settings.app.storage_root, app_md)
        _emit("sentiment", message="Agent Sentiment en cours…")

        # Step 3: Sentiment Agent (contextual analysis)
        try:
            from app.openai_client import chat_completion
            import json as _json

            ef = app_md.extracted_fields or {}
            llm = app_md.llm_outputs or {}
            context_parts = ["=== DOSSIER ==="]
            for ek, ev in list(ef.items())[:20]:
                fn = ek.split(":")[-1] if ":" in ek else ek
                val = ev.get("value", ev) if isinstance(ev, dict) else ev
                context_parts.append(f"{fn}: {val}")
            if llm:
                context_parts.append("\n=== ANALYSE IA ===")
                for section, subsections in llm.items():
                    if not subsections or not isinstance(subsections, dict):
                        continue
                    for sub, output in subsections.items():
                        parsed = output.get("parsed", {}) if output else {}
                        for field in ("summary", "synthese", "conclusion"):
                            val_ = parsed.get(field, "")
                            if val_ and isinstance(val_, str):
                                context_parts.append(f"{section}/{sub}: {val_[:200]}")
                                break
            if app_md.fraud_analysis:
                fa_oa = app_md.fraud_analysis.get("overall_assessment", {})
                context_parts.append(f"\nFraude: {fa_oa.get('overall_fraud_risk', 'N/A')} ({round(fa_oa.get('risk_score', 0) * 100)}%)")
            context_parts.append(f"\nPersona: {app_md.persona}")
            context_parts.append(f"Fichiers: {len(app_md.files or [])}")

            brand = settings.brand_name
            system_prompt = (
                f"Tu es l'Agent Sentiment. Analyse le dossier pour conseiller le gestionnaire "
                f"{brand} sur le ton et l'accompagnement. Valeurs : proximité, contact humain, entraide.\n"
                "Réponds en JSON: {score:int 0-100, level:calm|moderate|stressed|critical, "
                "suggestedTone:empathetic|standard|formal, daysSinceClaim:int|null, "
                "contextSummary:str, factors:[str], suggestions:[str]}"
            )
            raw = chat_completion(
                settings.openai,
                [{"role": "system", "content": system_prompt},
                 {"role": "user", "content": "\n".join(context_parts)}],
                max_tokens=600, temperature=0.1, response_format="json_object",
            )
            content = raw.get("content", "")
            if content:
                sa = _json.loads(content)
                app_md.sentiment_analysis = {
                    **sa, "agent": f"Sentiment Agent ({brand})",
                    "computed_at": datetime.now(UTC).isoformat(),
                }
                logger.info("Sentiment updated for %s: score=%s", app_id, sa.get("score"))
        except Exception as se:
            logger.warning("Sentiment auto-update failed for %s: %s", app_id, se)

        # Step 4: Final save + PG sync
        app_md.processing_status = None
        save_application_metadata(settings.app.storage_root, app_md)
        _emit("completed", message="Traitement terminé")
        logger.info("Background processing completed for %s", app_id)
    except Exception as e:
        logger.error("Background processing failed for %s: %s", app_id, e, exc_info=True)
        _emit("error", message=str(e))
        try:
            settings = load_settings()
            app_md = load_application(settings.app.storage_root, app_id)
            if app_md:
                app_md.processing_status = "error"
                app_md.processing_error = str(e)
                save_application_metadata(settings.app.storage_root, app_md)
        except Exception:
            pass


@app.post("/api/applications/{app_id}/extract")
async def extract_content(app_id: str, background: bool = False, language: Optional[str] = None):
    """Run Content Understanding extraction on an application.
    
    Args:
        app_id: Application ID
        background: If True, start extraction in background and return immediately.
                   Client should poll GET /api/applications/{app_id} for status.
    """
    try:
        settings = load_settings()
        app_md = load_application(settings.app.storage_root, app_id)
        if not app_md:
            raise HTTPException(status_code=404, detail="Dossier introuvable")

        if background:
            # Check if already processing
            if app_md.processing_status in ("extracting", "analyzing"):
                raise HTTPException(
                    status_code=409,
                    detail=f"Application is already being processed: {app_md.processing_status}"
                )
            
            # Start background task and return immediately
            task = asyncio.create_task(run_extraction_background(app_id, language=language))
            task.add_done_callback(_handle_task_exception)
            
            # Update status immediately so client sees it
            app_md.processing_status = "extracting"
            app_md.processing_error = None
            save_application_metadata(settings.app.storage_root, app_md)
            
            logger.info("Started background extraction for application %s", app_id)
            return {
                **application_to_dict(app_md),
                "message": "Extraction lanc\u00e9e en arri\u00e8re-plan. Interrogez GET /api/applications/{app_id} pour le statut."
            }
        
        # Synchronous mode (backward compatible)
        # Run content understanding in thread pool to avoid blocking event loop
        app_md = await asyncio.to_thread(
            run_content_understanding_for_files, settings, app_md, language=language
        )
        
        logger.info("Extraction completed for application %s", app_id)
        return application_to_dict(app_md)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Extraction failed for %s: %s", app_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/applications/{app_id}/analyze")
async def analyze_application(app_id: str, request: AnalyzeRequest = None, background: bool = False):
    """Run underwriting prompts analysis on an application.
    
    Args:
        app_id: Application ID
        request: Optional request with sections to analyze
        background: If True, start analysis in background and return immediately.
                   Client should poll GET /api/applications/{app_id} for status.
    """
    try:
        settings = load_settings()
        app_md = load_application(settings.app.storage_root, app_id)
        if not app_md:
            raise HTTPException(status_code=404, detail="Dossier introuvable")

        if not app_md.document_markdown:
            # Try to build from existing data (seed dossiers without CU extraction)
            parts = []
            ef = app_md.extracted_fields or {}
            for key, val in ef.items():
                fn = key.split(":")[-1] if ":" in key else key
                fv = val.get("value", val) if isinstance(val, dict) else val
                if fv:
                    parts.append(f"{fn}: {fv}")
            llm = app_md.llm_outputs or {}
            for section, subsections in llm.items():
                if not subsections or not isinstance(subsections, dict):
                    continue
                for sub, output in subsections.items():
                    raw = output.get("raw", "") if output else ""
                    if raw:
                        parts.append(f"\n## {section}/{sub}\n{raw}")
            if parts:
                app_md.document_markdown = "\n".join(parts)
                save_application_metadata(settings.app.storage_root, app_md)
                logger.info("Built document_markdown from existing data for %s", app_id)
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Aucun contenu disponible. Lancez l'extraction d'abord."
                )

        sections_to_run = request.sections if request else None
        processing_mode = request.processing_mode if request else None
        language = request.language if request else None

        if background:
            # Check if already processing
            if app_md.processing_status in ("extracting", "analyzing"):
                raise HTTPException(
                    status_code=409,
                    detail=f"Application is already being processed: {app_md.processing_status}"
                )
            
            # Start background task and return immediately
            task = asyncio.create_task(run_analysis_background(app_id, sections_to_run, processing_mode, language))
            task.add_done_callback(_handle_task_exception)
            
            # Update status immediately so client sees it
            app_md.processing_status = "analyzing"
            app_md.processing_error = None
            save_application_metadata(settings.app.storage_root, app_md)
            
            logger.info("Started background analysis for application %s", app_id)
            return {
                **application_to_dict(app_md),
                "message": "Analyse lanc\u00e9e en arri\u00e8re-plan. Interrogez GET /api/applications/{app_id} pour le statut."
            }

        # Synchronous mode (backward compatible)
        # Run underwriting prompts in thread pool to avoid blocking event loop
        app_md = await asyncio.to_thread(
            run_underwriting_prompts,
            settings,
            app_md,
            sections_to_run=sections_to_run,
            max_workers_per_section=4,
            processing_mode_override=processing_mode,
            language=language,
        )

        logger.info("Analysis completed for application %s", app_id)
        return application_to_dict(app_md)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Analysis failed for %s: %s", app_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/applications/{app_id}/sentiment")
async def analyze_sentiment(app_id: str, force: bool = False):
    """Run the Sentiment Agent on a dossier.

    The Sentiment Agent analyzes the full dossier context — extracted fields,
    AI analysis, fraud detection, documents — to determine the client's
    emotional state and recommend tone/accompaniment for the advisor.

    The result is stored in ``app_md.sentiment_analysis`` and persists across
    reloads. The frontend reads this stored result.

    Args:
        app_id: Application ID
        force: Re-analyze even if sentiment already computed
    """
    try:
        settings = load_settings()
        app_md = load_application(settings.app.storage_root, app_id)
        if not app_md:
            raise HTTPException(status_code=404, detail=f"Application {app_id} not found")

        # Skip if already computed (unless force=True)
        if app_md.sentiment_analysis and not force:
            return app_md.sentiment_analysis

        # Build the dossier context for the agent
        ef = app_md.extracted_fields or {}
        llm = app_md.llm_outputs or {}
        context_parts = []

        # Key extracted fields
        context_parts.append("=== INFORMATIONS DU DOSSIER ===")
        for ek, ev in list(ef.items())[:20]:
            fn = ek.split(":")[-1] if ":" in ek else ek
            val = ev.get("value", ev) if isinstance(ev, dict) else ev
            conf = ev.get("confidence", "") if isinstance(ev, dict) else ""
            context_parts.append(f"{fn}: {val}" + (f" (confiance: {conf})" if conf else ""))

        # AI analysis summaries
        if llm:
            context_parts.append("\n=== ANALYSES IA RÉALISÉES ===")
            for section, subsections in llm.items():
                if not subsections or not isinstance(subsections, dict):
                    continue
                for sub, output in subsections.items():
                    parsed = output.get("parsed", {}) if output else {}
                    for field in ("summary", "synthese", "conclusion", "analyse"):
                        val = parsed.get(field, "")
                        if val and isinstance(val, str):
                            context_parts.append(f"{section}/{sub}: {val[:250]}")
                            break

        # Fraud analysis context
        if app_md.fraud_analysis:
            fa = app_md.fraud_analysis
            oa = fa.get("overall_assessment", {})
            context_parts.append("\n=== ANALYSE ANTI-FRAUDE ===")
            context_parts.append(f"Risque fraude: {oa.get('overall_fraud_risk', 'N/A')} ({round(oa.get('risk_score', 0) * 100)}%)")
            if oa.get("siu_referral_recommended"):
                context_parts.append("⚠ Renvoi SIU recommandé")
            for item in oa.get("attention_items", [])[:3]:
                context_parts.append(f"- [{item.get('priority', '')}] {item.get('label', '')}: {item.get('detail', '')}")
            dv = fa.get("declaration_verification", {})
            if dv.get("consistency_score") is not None:
                context_parts.append(f"Concordance déclaration: {round(dv['consistency_score'] * 100)}%")

        # Files info
        n_files = len(app_md.files or [])
        context_parts.append(f"\n=== FICHIERS ({n_files} pièces) ===")
        for f in (app_md.files or [])[:8]:
            name = f.original_name if hasattr(f, "original_name") else (f.get("original_name", "") if isinstance(f, dict) else str(f))
            context_parts.append(f"- {name}")

        context_parts.append(f"\nPersona: {app_md.persona}")
        context_parts.append(f"Statut: {app_md.status}")

        dossier_context = "\n".join(context_parts)

        # Call Sentiment Agent
        from app.openai_client import chat_completion

        brand = settings.brand_name
        system_prompt = (
            f"Tu es l'Agent Sentiment, la plateforme agentique de traitement des sinistres {brand}.\n\n"
            "Tu analyses le dossier sinistre complet pour comprendre la situation du client et conseiller "
            f"le gestionnaire {brand} sur le ton et l'approche d'accompagnement.\n\n"
            "Tu dois analyser le CONTENU RÉEL du dossier — pas appliquer des règles fixes. "
            "Comprends la situation humaine derrière les données :\n"
            "- Un sinistre cave inondée avec photos de biens détruits → détresse matérielle et émotionnelle\n"
            "- Un écart devis/facture de +25% → risque de frustration administrative\n"
            "- Un risque fraude élevé → prudence dans la communication, ton neutre mais respectueux\n"
            "- Un sinistre ancien non résolu (>30j) → impatience, besoin de réassurance\n"
            "- Un sinistre Cat-Nat avec arrêté publié → contexte collectif, solidarité\n\n"
            f"Valeurs {brand} : proximité, contact humain, responsabilité dans l'entraide.\n"
            "L'accompagnement doit être personnalisé au contexte détecté dans les documents.\n\n"
            "Réponds UNIQUEMENT en JSON valide :\n"
            "{\n"
            '  "score": <int 0-100, 0=serein 100=critique>,\n'
            '  "level": "calm|moderate|stressed|critical",\n'
            '  "suggestedTone": "empathetic|standard|formal",\n'
            '  "daysSinceClaim": <int ou null>,\n'
            '  "contextSummary": "<résumé en 1-2 phrases de la situation client détectée>",\n'
            '  "factors": ["emoji + facteur détecté dans le contenu du dossier", ...],\n'
            '  "suggestions": ["emoji + recommandation d\'accompagnement pour le conseiller", ...]\n'
            "}\n"
            "Maximum 6 facteurs et 4 suggestions. Chaque facteur doit être spécifique au dossier analysé."
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Analyse le contexte client de ce dossier et recommande le ton d'accompagnement :\n\n{dossier_context}"},
        ]

        raw = chat_completion(
            settings.openai,
            messages,
            max_tokens=800,
            temperature=0.1,
            response_format="json_object",
        )

        content = raw.get("content", "")
        if not content:
            raise ValueError("Réponse vide du Sentiment Agent")

        import json
        result = json.loads(content)

        # Validate and normalize
        sentiment_data = {
            "score": max(0, min(100, int(result.get("score", 50)))),
            "level": result.get("level", "moderate"),
            "suggestedTone": result.get("suggestedTone", "standard"),
            "daysSinceClaim": result.get("daysSinceClaim"),
            "contextSummary": result.get("contextSummary", ""),
            "factors": result.get("factors", [])[:6],
            "suggestions": result.get("suggestions", [])[:4],
            "agent": f"Sentiment Agent ({brand})",
            "computed_at": datetime.now(UTC).isoformat(),
        }

        # Persist in application metadata
        app_md.sentiment_analysis = sentiment_data
        save_application_metadata(settings.app.storage_root, app_md)
        logger.info("Sentiment analysis stored for %s: score=%d level=%s", app_id, sentiment_data["score"], sentiment_data["level"])

        return sentiment_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Sentiment analysis failed for %s: %s", app_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/applications/{app_id}/generate-communication")
async def generate_communication(app_id: str, body: dict):
    """Generate a contextual communication (email/SMS/letter) with the chat model.

    The Communication Agent reads the full dossier context — extracted fields,
    AI analysis, fraud detection, sentiment — and generates a personalized
    message adapted to the client's situation and the brand's values.

    The workbench frontend calls this endpoint.

    Body:
        channel: "email" | "sms" | "letter"
        tone: "empathetic" | "standard" | "formal" | "auto"
              "auto" uses sentiment_analysis.suggestedTone
    """
    import json as _json

    channel = body.get("channel", "email")
    tone = body.get("tone", "auto")

    if channel not in ("email", "sms", "letter"):
        raise HTTPException(status_code=400, detail=f"Invalid channel: {channel}")

    try:
        settings = load_settings()
        app_md = load_application(settings.app.storage_root, app_id)
        if not app_md:
            raise HTTPException(status_code=404, detail=f"Application {app_id} not found")

        # Resolve tone from sentiment if "auto"
        if tone == "auto":
            sa = app_md.sentiment_analysis or {}
            tone = sa.get("suggestedTone", "standard")

        # Build dossier context (same as sentiment agent)
        ef = app_md.extracted_fields or {}
        llm = app_md.llm_outputs or {}
        sa = app_md.sentiment_analysis or {}

        context_parts = []

        # Key extracted fields
        context_parts.append("=== INFORMATIONS CLIENT ===")
        name_fields = ["NomAssure", "InsuredName", "NomSouscripteur", "ApplicantName"]
        recipient_name = ""
        for nf in name_fields:
            for ek, ev in ef.items():
                fn = ek.split(":")[-1] if ":" in ek else ek
                val = ev.get("value", ev) if isinstance(ev, dict) else ev
                if fn.lower() == nf.lower() and val:
                    recipient_name = str(val)
                    break
            if recipient_name:
                break
        if not recipient_name:
            recipient_name = get_current_brand_profile().member_term.capitalize()

        for ek, ev in list(ef.items())[:15]:
            fn = ek.split(":")[-1] if ":" in ek else ek
            val = ev.get("value", ev) if isinstance(ev, dict) else ev
            if val:
                context_parts.append(f"{fn}: {val}")

        # Contract / claim ref
        contrat = ""
        for ek, ev in ef.items():
            fn = ek.split(":")[-1] if ":" in ek else ek
            val = ev.get("value", ev) if isinstance(ev, dict) else ev
            if fn.lower() in ("numerocontrat", "policynumber") and val:
                contrat = str(val)
                break

        # Montant
        montant = ""
        for ek, ev in ef.items():
            fn = ek.split(":")[-1] if ":" in ek else ek
            val = ev.get("value", ev) if isinstance(ev, dict) else ev
            if fn.lower() in ("montantestime", "totalincurred") and val:
                montant = str(val)
                break

        # AI analysis summaries
        if llm:
            context_parts.append("\n=== ANALYSES IA ===")
            for section, subsections in llm.items():
                if not subsections or not isinstance(subsections, dict):
                    continue
                for sub, output in subsections.items():
                    parsed = output.get("parsed", {}) if output else {}
                    for field in ("summary", "synthese", "conclusion"):
                        val = parsed.get(field, "")
                        if val and isinstance(val, str):
                            context_parts.append(f"{section}: {val[:200]}")
                            break

        # Fraud analysis
        fraud_risk_high = False
        if app_md.fraud_analysis:
            fa = app_md.fraud_analysis
            oa = fa.get("overall_assessment", {})
            risk_score = oa.get("risk_score", 0)
            fraud_risk_high = risk_score > 0.7
            context_parts.append(f"\n=== FRAUDE ===")
            context_parts.append(f"Risque: {oa.get('overall_fraud_risk', 'N/A')} ({round(risk_score * 100)}%)")
            if oa.get("siu_referral_recommended"):
                context_parts.append("⚠ SIU recommandé")

        # Sentiment
        if sa:
            context_parts.append(f"\n=== SENTIMENT CLIENT ===")
            context_parts.append(f"Score: {sa.get('score', 50)}/100 — Niveau: {sa.get('level', 'moderate')}")
            context_parts.append(f"Ton recommandé: {sa.get('suggestedTone', 'standard')}")
            for factor in sa.get("factors", [])[:4]:
                context_parts.append(f"- {factor}")

        context_parts.append(f"\nPersona: {app_md.persona}")
        context_parts.append(f"Statut: {app_md.status}")
        context_parts.append(f"Fichiers: {len(app_md.files or [])}")

        dossier_context = "\n".join(context_parts)

        # Load communication prompts
        import os
        prompts_path = os.path.join(os.path.dirname(__file__), "prompts", "communication-prompts.json")
        with open(prompts_path, "r", encoding="utf-8") as f:
            comm_prompts = _json.load(f)

        brand_profile = get_current_brand_profile()
        brand = brand_profile.brand_name
        system_prompt = comm_prompts["system_prompt"].replace("{brand}", brand)
        channel_desc = comm_prompts["channels"].get(channel, "").replace("{brand}", brand)

        # Brand-specific INSURER contact details — these MUST appear in the
        # generated message instead of the insured's own phone/email.
        insurer_phone = brand_profile.insurer_phone
        insurer_email = brand_profile.insurer_email
        insurer_portal = f"{brand_profile.portal_base_url}/dossier/{contrat or app_id[:12]}"
        insurer_signature = brand_profile.signature

        # Build user prompt
        user_prompt = (
            f"Génère une communication {channel.upper()} pour ce dossier.\n\n"
            f"Canal: {channel} — {channel_desc}\n"
            f"Ton demandé: {tone}\n"
            f"Nom du destinataire: {recipient_name}\n"
            f"Référence dossier: {contrat or app_id[:12]}\n"
            f"Montant estimé: {montant or 'N/A'}\n\n"
            f"=== COORDONNÉES ASSUREUR (à utiliser dans le message) ===\n"
            f"Téléphone service sinistres: {insurer_phone}\n"
            f"Email service sinistres: {insurer_email}\n"
            f"Espace assuré: {insurer_portal}\n"
            f"Signature: {insurer_signature}\n"
            f"⚠ RAPPEL: N'utilise JAMAIS le téléphone/email de l'assuré comme contact assureur. "
            f"Utilise UNIQUEMENT les coordonnées ci-dessus.\n"
        )
        if fraud_risk_high:
            user_prompt += "\n⚠ ATTENTION: Risque fraude élevé — NE PAS mentionner la fraude. Rester factuel et respectueux.\n"

        user_prompt += f"\n{dossier_context}"

        # Call the chat model
        from app.openai_client import chat_completion

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        raw = chat_completion(
            settings.openai,
            messages,
            max_tokens=800 if channel != "sms" else 200,
            temperature=0.3,
            response_format="json_object",
        )

        content = raw.get("content", "")
        if not content:
            raise ValueError("Empty response from Communication Agent")

        result = _json.loads(content)

        # Build response
        sentiment_score = sa.get("score", 50)
        sentiment_level = sa.get("level", "moderate")

        response = {
            "channel": channel,
            "tone": tone,
            "subject": result.get("subject"),
            "body": result.get("body", ""),
            "recipientName": recipient_name,
            "claimReference": contrat or app_id[:12],
            "montant": montant,
            "sentimentScore": sentiment_score,
            "sentimentLevel": sentiment_level,
            "agent": f"Communication Agent ({brand})",
            "generated_at": datetime.now(UTC).isoformat(),
        }

        logger.info(
            "Communication generated for %s: channel=%s tone=%s body_len=%d",
            app_id, channel, tone, len(response["body"]),
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Communication generation failed for %s: %s", app_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/applications/{app_id}/analyze/deep-dive")
async def analyze_deep_dive(app_id: str, background: bool = False, force: bool = False):
    """Run only the 5 deep-dive subsections within medical_summary.
    
    This is an incremental re-analysis that:
    1. Detects which deep-dive subsections are missing or have errors
    2. Runs only those subsections (or all 5 if force=True)
    3. Merges results with existing llm_outputs
    
    Useful for adding deep dive to applications analyzed before the feature existed.
    
    Args:
        app_id: Application ID
        background: If True, run in background and return immediately
        force: If True, re-run all 5 deep-dive subsections regardless of existing data
    """
    try:
        settings = load_settings()
        app_md = load_application(settings.app.storage_root, app_id)
        if not app_md:
            raise HTTPException(status_code=404, detail="Dossier introuvable")

        if not app_md.document_markdown:
            # Build document_markdown from existing extracted_fields + llm_outputs
            # Allows deep dive on seed data without Content Understanding extraction
            parts = []
            ef = app_md.extracted_fields or {}
            for key, val in ef.items():
                field_name = key.split(":")[-1] if ":" in key else key
                field_val = val.get("value", val) if isinstance(val, dict) else val
                if field_val:
                    parts.append(f"{field_name}: {field_val}")
            llm = app_md.llm_outputs or {}
            for section, subsections in llm.items():
                if not subsections or not isinstance(subsections, dict):
                    continue
                for sub, output in subsections.items():
                    raw = output.get("raw", "") if output else ""
                    if raw:
                        parts.append(f"\n## {section}/{sub}\n{raw}")
            if parts:
                app_md.document_markdown = "\n".join(parts)
                save_application_metadata(settings.app.storage_root, app_md)
                logger.info("Built document_markdown from existing data for %s (%d chars)", app_id, len(app_md.document_markdown))
            else:
                raise HTTPException(
                    status_code=400,
                    detail="Aucun contenu disponible. Lancez l'extraction (Relancer IA) d'abord."
                )

        # Deep dive subsections
        deep_dive_keys = [
            "body_system_review",
            "pending_investigations", 
            "last_office_visit",
            "abnormal_labs",
            "latest_vitals",
        ]
        
        # Check which are missing or have errors
        existing_ms = app_md.llm_outputs.get("medical_summary", {}) if app_md.llm_outputs else {}
        
        if force:
            missing = list(deep_dive_keys)
            errored = []
            logger.info("Force re-run requested — running all 5 deep dive subsections for %s", app_id)
        else:
            missing = []
            errored = []
            for k in deep_dive_keys:
                if k not in existing_ms:
                    missing.append(k)
                else:
                    # Also treat subsections with error data as needing re-run
                    parsed = (existing_ms[k] or {}).get("parsed") if isinstance(existing_ms[k], dict) else None
                    if isinstance(parsed, dict) and "_error" in parsed:
                        errored.append(k)
                        missing.append(k)
        
        if not missing:
            logger.info("All deep dive subsections already present for %s", app_id)
            return {
                **application_to_dict(app_md),
                "message": "Toutes les sous-sections deep dive sont d\u00e9j\u00e0 pr\u00e9sentes. Aucune r\u00e9-analyse n\u00e9cessaire."
            }
        
        if errored:
            logger.info("Deep dive subsections with errors that will be re-run for %s: %s", app_id, errored)
        
        logger.info("Running deep dive for %s: %d subsections missing", app_id, len(missing))
        
        # Build subsections_to_run list from missing subsections only (incremental)
        subsections_to_run = [("medical_summary", k) for k in missing]
        
        if background:
            # Check if already processing
            if app_md.processing_status in ("extracting", "analyzing"):
                raise HTTPException(
                    status_code=409,
                    detail=f"Application is already being processed: {app_md.processing_status}"
                )
            
            # Start background task
            async def run_deep_dive_bg():
                try:
                    updated = await asyncio.to_thread(
                        run_underwriting_prompts,
                        settings,
                        app_md,
                        sections_to_run=["medical_summary"],
                        subsections_to_run=subsections_to_run,
                        max_workers_per_section=4,
                    )
                    logger.info("Deep dive completed for %s", app_id)
                    # Reset processing status after successful completion
                    updated.processing_status = None
                    updated.processing_error = None
                    save_application_metadata(settings.app.storage_root, updated)
                except Exception as e:
                    logger.error("Deep dive failed for %s: %s", app_id, e, exc_info=True)
                    app_md.processing_status = "error"
                    app_md.processing_error = str(e)
                    save_application_metadata(settings.app.storage_root, app_md)
            
            task = asyncio.create_task(run_deep_dive_bg())
            task.add_done_callback(_handle_task_exception)
            
            app_md.processing_status = "analyzing"
            app_md.processing_error = None
            save_application_metadata(settings.app.storage_root, app_md)
            
            return {
                **application_to_dict(app_md),
                "message": f"Deep dive started for {len(deep_dive_keys)} subsections. Poll GET /api/applications/{{app_id}} for status."
            }
        
        # Synchronous mode
        app_md = await asyncio.to_thread(
            run_underwriting_prompts,
            settings,
            app_md,
            sections_to_run=["medical_summary"],
            subsections_to_run=subsections_to_run,
            max_workers_per_section=4,
        )

        logger.info("Deep dive completed for application %s", app_id)
        return application_to_dict(app_md)

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Deep dive failed for %s: %s", app_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/applications/{app_id}/reset-status")
async def reset_application_status(app_id: str):
    """Reset processing status to idle (use if stuck in processing state)."""
    try:
        settings = load_settings()
        app_md = load_application(settings.app.storage_root, app_id)
        if not app_md:
            raise HTTPException(status_code=404, detail="Dossier introuvable")
        
        app_md.processing_status = None
        app_md.processing_error = None
        save_application_metadata(settings.app.storage_root, app_md)
        
        logger.info("Reset processing status for application %s", app_id)
        return {"message": "Statut de traitement r\u00e9initialis\u00e9", "id": app_id}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/applications/{app_id}/process")
async def process_application(app_id: str, processing_mode: Optional[str] = Query(None)):
    """Start full processing (extraction + analysis) in background.
    
    This is the recommended endpoint for new uploads. It starts both
    extraction and analysis as background tasks and returns immediately.
    Client should poll GET /api/applications/{app_id} to check status.
    
    Args:
        app_id: Application ID
        processing_mode: 'auto', 'standard', or 'large_document' (default: auto)
    
    The processing_status field will be:
    - 'extracting': Currently running content extraction
    - 'analyzing': Extraction done, running analysis
    - null: Processing complete
    - 'error': Processing failed (check processing_error for details)
    """
    try:
        settings = load_settings()
        app_md = load_application(settings.app.storage_root, app_id)
        if not app_md:
            raise HTTPException(status_code=404, detail="Dossier introuvable")

        # Check if already processing
        if app_md.processing_status in ("extracting", "analyzing"):
            raise HTTPException(
                status_code=409,
                detail=f"Application is already being processed: {app_md.processing_status}"
            )
        
        # Start background task for full processing
        task = asyncio.create_task(run_extract_and_analyze_background(app_id, processing_mode))
        task.add_done_callback(_handle_task_exception)
        
        # Update status immediately so client sees it
        app_md.processing_status = "extracting"
        app_md.processing_error = None
        save_application_metadata(settings.app.storage_root, app_md)
        
        logger.info("Started background processing for application %s (mode: %s)", app_id, processing_mode or "auto")
        return {
            **application_to_dict(app_md),
            "message": "Traitement lanc\u00e9 en arri\u00e8re-plan. Interrogez GET /api/applications/{app_id} pour le statut."
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to start processing for %s: %s", app_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _risk_analysis_background(app_id: str):
    """Run policy-based risk analysis in the background.

    Runs the (blocking) LLM call off the event loop and persists the result to
    storage. The frontend polls ``processing_status`` to detect completion, so
    the original HTTP request can return immediately (202) instead of being held
    open long enough to trip the Azure Container Apps ingress timeout, which
    returns a plain-text ``stream timeout`` body that breaks JSON parsing.
    """
    from app.processing import run_risk_analysis

    try:
        settings = load_settings()
        app_md = load_application(settings.app.storage_root, app_id)
        if not app_md:
            logger.warning("Risk analysis background: application %s not found", app_id)
            return
        # run_risk_analysis mutates app_md, clears processing_status and saves on success.
        await asyncio.to_thread(run_risk_analysis, settings, app_md)
        logger.info("Risk analysis completed for application %s", app_id)
    except Exception as e:
        logger.error("Risk analysis failed for %s: %s", app_id, e, exc_info=True)
        # Mark processing status as error so the frontend stops polling and shows it.
        try:
            settings = load_settings()
            app_md = load_application(settings.app.storage_root, app_id)
            if app_md:
                app_md.processing_status = "error"
                app_md.processing_error = str(e)
                save_application_metadata(settings.app.storage_root, app_md)
        except Exception:
            logger.error("Failed to persist risk analysis error for %s", app_id, exc_info=True)


def _log_task_exception(task: "asyncio.Task") -> None:
    """done_callback to surface otherwise-swallowed background task exceptions."""
    try:
        exc = task.exception()
    except asyncio.CancelledError:
        return
    if exc is not None:
        logger.error("Background risk analysis task crashed: %s", exc, exc_info=exc)


@app.post("/api/applications/{app_id}/risk-analysis", status_code=202)
async def run_application_risk_analysis(app_id: str):
    """Start policy-based risk analysis on an already-analyzed application.

    This is a separate operation from extraction/summarization. It applies
    underwriting policies to the extracted data and generates a comprehensive
    risk assessment with policy citations.

    The work runs in the background and the endpoint returns 202 immediately;
    the client polls ``GET /api/applications/{id}`` (``processing_status``) for
    completion. This avoids the long-running request being killed by the
    ingress timeout.

    Prerequisites:
    - Application must have completed extraction and analysis
    - LLM outputs must be present
    """
    settings = load_settings()
    app_md = load_application(settings.app.storage_root, app_id)
    if not app_md:
        raise HTTPException(status_code=404, detail="Dossier introuvable")

    if not app_md.llm_outputs:
        raise HTTPException(
            status_code=400,
            detail="No analysis outputs found. Run standard analysis first."
        )

    if app_md.persona != "underwriting":
        raise HTTPException(
            status_code=400,
            detail="Risk analysis is only available for underwriting applications."
        )

    # Reject concurrent runs so double-clicks / multiple UI surfaces don't
    # trigger duplicate expensive Azure OpenAI calls.
    if app_md.processing_status in ("extracting", "analyzing"):
        raise HTTPException(
            status_code=409,
            detail="Une analyse est d\u00e9j\u00e0 en cours pour ce dossier."
        )

    # Mark as analyzing and persist BEFORE returning so the client's first poll
    # reliably observes the in-progress state.
    app_md.processing_status = "analyzing"
    app_md.processing_error = None
    save_application_metadata(settings.app.storage_root, app_md)

    task = asyncio.create_task(_risk_analysis_background(app_id))
    task.add_done_callback(_log_task_exception)

    return {
        "application_id": app_id,
        "status": "analyzing",
        "message": "Analyse de risque lanc\u00e9e",
    }


@app.get("/api/applications/{app_id}/risk-analysis")
async def get_application_risk_analysis(app_id: str):
    """Get the risk analysis results for an application."""
    try:
        settings = load_settings()
        app_md = load_application(settings.app.storage_root, app_id)
        if not app_md:
            raise HTTPException(status_code=404, detail="Dossier introuvable")

        if not app_md.risk_analysis:
            raise HTTPException(
                status_code=404,
                detail="No risk analysis found. Run risk analysis first."
            )

        return {
            "application_id": app_id,
            "risk_analysis": app_md.risk_analysis,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get risk analysis for %s: %s", app_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/config/status")
async def config_status():
    """Check configuration status."""
    try:
        settings = load_settings()
        errors = validate_settings(settings)
        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "openai": {
                "deployment": settings.openai.deployment_name,
                "model": settings.openai.model_name,
                "api_version": settings.openai.api_version,
                "reasoning_effort": settings.openai.reasoning_effort,
            },
            "content_understanding": {
                "api_version": settings.content_understanding.api_version,
                "analyzer_id": settings.content_understanding.analyzer_id,
                "completion_deployment": settings.content_understanding.completion_deployment,
                "embedding_deployment": settings.content_understanding.embedding_deployment,
            },
            "markitdown": {
                "enabled": settings.markitdown.enabled,
                "mode": settings.markitdown.mode,
                "use_content_understanding": settings.markitdown.use_content_understanding,
                "preferred_extensions": list(settings.markitdown.preferred_extensions),
            },
        }
    except Exception as e:
        return {
            "valid": False,
            "errors": [str(e)],
        }


@app.get("/api/capabilities/file-formats")
async def file_format_capabilities(persona: Optional[str] = Query(None)):
    """Return supported upload formats for a persona."""
    return get_file_capabilities(persona)


# ============================================================================
# Prompt Catalog APIs
# ============================================================================

class PromptUpdateRequest(BaseModel):
    """Request model for updating a single prompt."""
    text: str


class PromptsUpdateRequest(BaseModel):
    """Request model for bulk prompt updates."""
    prompts: dict


@app.get("/api/prompts")
async def get_prompts(persona: str = "underwriting"):
    """Get all prompts organized by section and subsection for a persona."""
    try:
        settings = load_settings()
        prompts = load_prompts(settings.app.prompts_root, persona)
        return {"prompts": prompts, "persona": persona}
    except Exception as e:
        logger.error("Failed to load prompts: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/prompts/{section}/{subsection}")
async def get_prompt(section: str, subsection: str, persona: str = "underwriting"):
    """Get a specific prompt by section and subsection."""
    try:
        settings = load_settings()
        prompts = load_prompts(settings.app.prompts_root, persona)
        
        if section not in prompts:
            raise HTTPException(status_code=404, detail=f"Section '{section}' not found")
        if subsection not in prompts[section]:
            raise HTTPException(status_code=404, detail=f"Subsection '{subsection}' not found in section '{section}'")
        
        return {
            "section": section,
            "subsection": subsection,
            "text": prompts[section][subsection]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get prompt %s/%s: %s", section, subsection, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/prompts/{section}/{subsection}")
async def update_prompt(section: str, subsection: str, request: PromptUpdateRequest, persona: str = "underwriting"):
    """Update a specific prompt."""
    try:
        settings = load_settings()
        prompts = load_prompts(settings.app.prompts_root, persona)
        
        if section not in prompts:
            prompts[section] = {}
        
        prompts[section][subsection] = request.text
        save_prompts(settings.app.prompts_root, prompts, persona)
        
        logger.info("Updated prompt %s/%s for persona %s", section, subsection, persona)
        return {
            "section": section,
            "subsection": subsection,
            "text": request.text,
            "message": "Prompt mis \u00e0 jour"
        }
    except Exception as e:
        logger.error("Failed to update prompt %s/%s: %s", section, subsection, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/prompts/{section}/{subsection}")
async def delete_prompt(section: str, subsection: str, persona: str = "underwriting"):
    """Delete a specific prompt (resets to default if available)."""
    try:
        settings = load_settings()
        prompts = load_prompts(settings.app.prompts_root, persona)
        
        if section in prompts and subsection in prompts[section]:
            del prompts[section][subsection]
            # Remove section if empty
            if not prompts[section]:
                del prompts[section]
            save_prompts(settings.app.prompts_root, prompts, persona)
            
        logger.info("Deleted prompt %s/%s for persona %s", section, subsection, persona)
        return {"message": f"Prompt {section}/{subsection} deleted"}
    except Exception as e:
        logger.error("Failed to delete prompt %s/%s: %s", section, subsection, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/prompts/{section}/{subsection}")
async def create_prompt(section: str, subsection: str, request: PromptUpdateRequest, persona: str = "underwriting"):
    """Create a new prompt."""
    try:
        settings = load_settings()
        prompts = load_prompts(settings.app.prompts_root, persona)
        
        if section not in prompts:
            prompts[section] = {}
        
        if subsection in prompts[section]:
            raise HTTPException(
                status_code=409, 
                detail=f"Prompt '{section}/{subsection}' already exists. Use PUT to update."
            )
        
        prompts[section][subsection] = request.text
        save_prompts(settings.app.prompts_root, prompts, persona)
        
        logger.info("Created prompt %s/%s for persona %s", section, subsection, persona)
        return {
            "section": section,
            "subsection": subsection,
            "text": request.text,
            "message": "Prompt cr\u00e9\u00e9"
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to create prompt %s/%s: %s", section, subsection, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Glossary APIs
# ============================================================================

from app.glossary import (
    list_glossaries,
    get_glossary_for_persona,
    search_glossary,
    add_term,
    update_term,
    delete_term,
    add_category,
    update_category,
    delete_category,
    format_glossary_for_prompt,
)


class GlossaryTermRequest(BaseModel):
    """Request model for adding/updating a glossary term."""
    abbreviation: str
    meaning: str
    context: Optional[str] = None
    examples: Optional[List[str]] = None
    category_id: Optional[str] = None  # For updates - move to different category


class GlossaryCategoryRequest(BaseModel):
    """Request model for adding/updating a category."""
    id: str
    name: str


class GlossaryCategoryUpdateRequest(BaseModel):
    """Request model for updating a category name."""
    name: str


# =============================================================================
# Policy PDF Assets — brand-aware
# =============================================================================

def _get_policy_pdfs(brand: str = DEFAULT_BRAND.brand_name) -> dict:
    """Return metadata for the policy PDFs shipped for the given brand (existing files only)."""
    profile = get_brand_profile(brand)
    prefix = profile.brand_key
    candidates = {
        "habitation": {
            "filename": f"{prefix}/{prefix}-conditions-generales-habitation.pdf",
            "title": f"CG Habitation {profile.brand_name}",
        },
        "sante": {
            "filename": f"{prefix}/{prefix}-complementaire-sante.pdf",
            "title": f"CG Complémentaire Santé {profile.brand_name}",
        },
        "auto": {
            "filename": f"{prefix}/{prefix}-conditions-generales-auto.pdf",
            "title": f"CG Auto {profile.brand_name}",
        },
        "flotte": {
            "filename": f"{prefix}/{prefix}-conditions-generales-flotte-auto.pdf",
            "title": f"CG Flotte Auto {profile.brand_name}",
        },
    }
    return {
        key: info
        for key, info in candidates.items()
        if (Path("assets/pdf") / info["filename"]).exists()
    }


@app.get("/api/policy-pdfs")
async def list_policy_pdfs():
    """List available policy PDF documents for the current brand."""
    settings = load_settings()
    policy_pdfs = _get_policy_pdfs(settings.brand_name)
    result = []
    for key, info in policy_pdfs.items():
        pdf_path = Path("assets/pdf") / info["filename"]
        result.append({
            "id": key,
            "title": info["title"],
            "filename": info["filename"],
            "url": f"/api/policy-pdfs/{key}",
            "available": pdf_path.exists(),
        })
    return result


@app.get("/api/policy-pdfs/{pdf_id}")
async def get_policy_pdf(pdf_id: str):
    """Serve a policy PDF document for the current brand."""
    settings = load_settings()
    policy_pdfs = _get_policy_pdfs(settings.brand_name)
    if pdf_id not in policy_pdfs:
        raise HTTPException(status_code=404, detail=f"Policy PDF '{pdf_id}' not found")

    info = policy_pdfs[pdf_id]
    pdf_path = Path("assets/pdf") / info["filename"]

    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"PDF file not found: {info['filename']}")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename=\"{info['filename']}\"",
            "X-Content-Type-Options": "nosniff",
        },
    )


@app.get("/api/glossary")
async def list_all_glossaries():
    """List all available glossaries with summary info."""
    try:
        settings = load_settings()
        glossaries = list_glossaries(settings.app.prompts_root)
        return {"glossaries": glossaries}
    except Exception as e:
        logger.error("Failed to list glossaries: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/glossary/{persona}")
async def get_persona_glossary(persona: str):
    """Get the full glossary for a specific persona."""
    try:
        settings = load_settings()
        glossary = get_glossary_for_persona(settings.app.prompts_root, persona)
        return glossary
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to get glossary for persona %s: %s", persona, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/glossary/{persona}/search")
async def search_persona_glossary(
    persona: str,
    q: str = Query(..., description="Search query"),
    category: Optional[str] = Query(None, description="Filter by category ID")
):
    """Search for terms matching a query."""
    try:
        settings = load_settings()
        results = search_glossary(settings.app.prompts_root, persona, q, category)
        return {"results": results, "count": len(results)}
    except Exception as e:
        logger.error("Failed to search glossary: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/glossary/{persona}/categories")
async def create_glossary_category(persona: str, request: GlossaryCategoryRequest):
    """Add a new category to a persona's glossary."""
    try:
        settings = load_settings()
        category = add_category(
            settings.app.prompts_root,
            persona,
            {"id": request.id, "name": request.name}
        )
        return {"category": category, "message": "Cat\u00e9gorie cr\u00e9\u00e9e"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to add category: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/glossary/{persona}/categories/{category_id}")
async def update_glossary_category(
    persona: str,
    category_id: str,
    request: GlossaryCategoryUpdateRequest
):
    """Update a category name."""
    try:
        settings = load_settings()
        category = update_category(
            settings.app.prompts_root,
            persona,
            category_id,
            {"name": request.name}
        )
        return {"category": category, "message": "Cat\u00e9gorie mise \u00e0 jour"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to update category: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/glossary/{persona}/categories/{category_id}")
async def delete_glossary_category(persona: str, category_id: str):
    """Delete a category (must be empty)."""
    try:
        settings = load_settings()
        delete_category(settings.app.prompts_root, persona, category_id)
        return {"message": "Cat\u00e9gorie supprim\u00e9e"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to delete category: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/glossary/{persona}/terms/{category_id}")
async def create_glossary_term(
    persona: str,
    category_id: str,
    request: GlossaryTermRequest
):
    """Add a new term to a category."""
    try:
        settings = load_settings()
        term = add_term(
            settings.app.prompts_root,
            persona,
            category_id,
            {
                "abbreviation": request.abbreviation,
                "meaning": request.meaning,
                "context": request.context,
                "examples": request.examples
            }
        )
        return {"term": term, "message": "Terme cr\u00e9\u00e9"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to add term: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/glossary/{persona}/terms/{abbreviation}")
async def update_glossary_term(
    persona: str,
    abbreviation: str,
    request: GlossaryTermRequest
):
    """Update an existing term."""
    try:
        settings = load_settings()
        updates = {"meaning": request.meaning}
        if request.context is not None:
            updates["context"] = request.context
        if request.examples is not None:
            updates["examples"] = request.examples
        if request.category_id is not None:
            updates["category_id"] = request.category_id
        
        term = update_term(
            settings.app.prompts_root,
            persona,
            abbreviation,
            updates
        )
        return {"term": term, "message": "Terme mis \u00e0 jour"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to update term: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/glossary/{persona}/terms/{abbreviation}")
async def delete_glossary_term(persona: str, abbreviation: str):
    """Delete a term from the glossary."""
    try:
        settings = load_settings()
        delete_term(settings.app.prompts_root, persona, abbreviation)
        return {"message": "Terme supprim\u00e9"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to delete term: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/glossary/{persona}/formatted")
async def get_formatted_glossary(
    persona: str,
    max_terms: int = Query(100, ge=1, le=500),
    categories: Optional[str] = Query(None, description="Comma-separated category IDs"),
    format_type: str = Query("markdown", pattern="^(markdown|list)$"),
    include_headers: bool = Query(False)
):
    """Get glossary formatted for prompt injection."""
    try:
        settings = load_settings()
        category_list = categories.split(",") if categories else None
        formatted = format_glossary_for_prompt(
            settings.app.prompts_root,
            persona,
            max_terms=max_terms,
            categories=category_list,
            format_type=format_type,
            include_category_headers=include_headers
        )
        return {"formatted": formatted}
    except Exception as e:
        logger.error("Failed to format glossary: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Content Understanding Analyzer APIs
# ============================================================================

class AnalyzerCreateRequest(BaseModel):
    """Request model for creating a custom analyzer."""
    analyzer_id: Optional[str] = None
    persona: Optional[str] = None
    description: Optional[str] = "Custom analyzer for document extraction"
    media_type: Optional[str] = None  # "document", "image", or "video"


@app.get("/api/analyzer/status")
async def get_analyzer_status(persona: Optional[str] = "underwriting"):
    """Get the current status of the custom analyzer for the specified persona."""
    try:
        settings = load_settings()
        
        # Get persona-specific analyzer ID
        try:
            persona_config = get_persona_config(persona)
            custom_analyzer_id = persona_config.custom_analyzer_id
        except ValueError:
            # Fallback to default if persona not found
            custom_analyzer_id = settings.content_understanding.custom_analyzer_id
        
        try:
            analyzer = get_analyzer(settings.content_understanding, custom_analyzer_id)
            return {
                "analyzer_id": custom_analyzer_id,
                "exists": analyzer is not None,
                "analyzer": analyzer,
                "confidence_scoring_enabled": settings.content_understanding.enable_confidence_scores,
                "default_analyzer_id": settings.content_understanding.analyzer_id,
                "api_version": settings.content_understanding.api_version,
                "completion_deployment": settings.content_understanding.completion_deployment,
                "embedding_deployment": settings.content_understanding.embedding_deployment,
                "markitdown": {
                    "enabled": settings.markitdown.enabled,
                    "mode": settings.markitdown.mode,
                    "use_content_understanding": settings.markitdown.use_content_understanding,
                },
                "persona": persona,
            }
        except (requests.exceptions.Timeout, requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout) as timeout_err:
            logger.warning("Timeout checking analyzer status for %s: %s", custom_analyzer_id, timeout_err)
            return {
                "analyzer_id": custom_analyzer_id,
                "exists": None,
                "analyzer": None,
                "confidence_scoring_enabled": settings.content_understanding.enable_confidence_scores,
                "default_analyzer_id": settings.content_understanding.analyzer_id,
                "api_version": settings.content_understanding.api_version,
                "completion_deployment": settings.content_understanding.completion_deployment,
                "embedding_deployment": settings.content_understanding.embedding_deployment,
                "markitdown": {
                    "enabled": settings.markitdown.enabled,
                    "mode": settings.markitdown.mode,
                    "use_content_understanding": settings.markitdown.use_content_understanding,
                },
                "persona": persona,
                "error": f"Request timeout ({timeout_err})",
            }
        except requests.exceptions.ConnectionError as conn_err:
            logger.warning("Connection error checking analyzer status: %s", conn_err)
            return {
                "analyzer_id": custom_analyzer_id,
                "exists": None,
                "analyzer": None,
                "confidence_scoring_enabled": settings.content_understanding.enable_confidence_scores,
                "default_analyzer_id": settings.content_understanding.analyzer_id,
                "api_version": settings.content_understanding.api_version,
                "completion_deployment": settings.content_understanding.completion_deployment,
                "embedding_deployment": settings.content_understanding.embedding_deployment,
                "markitdown": {
                    "enabled": settings.markitdown.enabled,
                    "mode": settings.markitdown.mode,
                    "use_content_understanding": settings.markitdown.use_content_understanding,
                },
                "persona": persona,
                "error": "Cannot connect to Azure Content Understanding service",
            }
    except Exception as e:
        logger.error("Failed to get analyzer status: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analyzer/schema")
async def get_analyzer_schema(persona: Optional[str] = "underwriting"):
    """Get the current field schema for the custom analyzer."""
    try:
        schema = get_field_schema(persona)
        return {
            "schema": schema,
            "field_count": len(schema.get("fields", {})),
            "persona": persona,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to get analyzer schema: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyzer/create")
async def create_custom_analyzer(request: AnalyzerCreateRequest = None):
    """Create or update the custom analyzer for confidence-scored extraction."""
    try:
        settings = load_settings()
        persona_id = request.persona if request and request.persona else "underwriting"
        media_type = request.media_type if request and request.media_type else "document"
        
        # Get the analyzer_id from persona config if not explicitly provided
        if request and request.analyzer_id:
            analyzer_id = request.analyzer_id
        else:
            try:
                persona_config = get_persona_config(persona_id)
                # Select analyzer based on media type
                if media_type == "image" and persona_config.image_analyzer_id:
                    analyzer_id = persona_config.image_analyzer_id
                elif media_type == "video" and persona_config.video_analyzer_id:
                    analyzer_id = persona_config.video_analyzer_id
                else:
                    analyzer_id = persona_config.custom_analyzer_id
            except ValueError:
                # Fallback to default if persona not found
                analyzer_id = settings.content_understanding.custom_analyzer_id
        
        description = request.description if request and request.description else f"Custom {persona_id} {media_type} analyzer for extraction with confidence scores"
        
        result = create_or_update_custom_analyzer(
            settings.content_understanding,
            analyzer_id=analyzer_id,
            persona_id=persona_id,
            description=description,
            media_type=media_type,
        )
        
        logger.info("Created/updated custom %s analyzer: %s", media_type, analyzer_id)
        return {
            "message": f"Analyzer '{analyzer_id}' created/updated successfully",
            "analyzer_id": analyzer_id,
            "result": result,
        }
    except Exception as e:
        logger.error("Failed to create analyzer: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/analyzer/{analyzer_id}")
async def delete_custom_analyzer(analyzer_id: str):
    """Delete a custom analyzer."""
    try:
        settings = load_settings()
        
        success = delete_analyzer(settings.content_understanding, analyzer_id)
        
        if success:
            logger.info("Deleted analyzer: %s", analyzer_id)
            return {"message": f"Analyzer '{analyzer_id}' deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail=f"Analyzer '{analyzer_id}' not found")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete analyzer %s: %s", analyzer_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/analyzer/list")
async def list_analyzers():
    """List available analyzers (custom and default)."""
    try:
        settings = load_settings()
        default_id = settings.content_understanding.analyzer_id
        
        analyzers = [
            {
                "id": default_id,
                "type": "prebuilt",
                "description": "Azure prebuilt document search analyzer",
                "exists": True,  # Prebuilt analyzers always exist
                "persona": None,
            },
        ]
        
        # Get all persona configurations
        personas = list_personas()
        
        # Helper function to check and add an analyzer
        def add_analyzer(analyzer_id: str, persona_id: str, persona_name: str, media_type: str = "document"):
            """Check if analyzer exists and add to list."""
            try:
                custom_analyzer = get_analyzer(settings.content_understanding, analyzer_id)
                if custom_analyzer:
                    analyzers.append({
                        "id": analyzer_id,
                        "type": "custom",
                        "media_type": media_type,
                        "description": custom_analyzer.get("description", f"Custom {persona_name} {media_type} analyzer"),
                        "exists": True,
                        "persona": persona_id,
                        "persona_name": persona_name,
                    })
                else:
                    analyzers.append({
                        "id": analyzer_id,
                        "type": "custom",
                        "media_type": media_type,
                        "description": f"Custom {persona_name} {media_type} analyzer (not created yet)",
                        "exists": False,
                        "persona": persona_id,
                        "persona_name": persona_name,
                    })
            except (requests.exceptions.Timeout, requests.exceptions.ReadTimeout, requests.exceptions.ConnectTimeout) as timeout_err:
                logger.warning("Timeout checking custom analyzer %s for persona %s: %s", analyzer_id, persona_id, timeout_err)
                analyzers.append({
                    "id": analyzer_id,
                    "type": "custom",
                    "media_type": media_type,
                    "description": f"Custom {persona_name} {media_type} analyzer (status unknown - timeout)",
                    "exists": None,
                    "persona": persona_id,
                    "persona_name": persona_name,
                    "error": f"Request timeout ({timeout_err})",
                })
            except requests.exceptions.ConnectionError as conn_err:
                logger.warning("Connection error checking custom analyzer %s for persona %s: %s", analyzer_id, persona_id, conn_err)
                analyzers.append({
                    "id": analyzer_id,
                    "type": "custom",
                    "media_type": media_type,
                    "description": f"Custom {persona_name} {media_type} analyzer (status unknown - connection error)",
                    "exists": None,
                    "persona": persona_id,
                    "persona_name": persona_name,
                    "error": "Cannot connect to Azure Content Understanding service",
                })
        
        # Check each persona's custom analyzers
        for persona in personas:
            if not persona.get("enabled", True):
                continue  # Skip disabled personas
                
            persona_id = persona["id"]
            try:
                persona_config = get_persona_config(persona_id)
                
                # Add document analyzer
                add_analyzer(persona_config.custom_analyzer_id, persona_id, persona["name"], "document")
                
                # Add image analyzer if configured (multimodal personas)
                if persona_config.image_analyzer_id:
                    add_analyzer(persona_config.image_analyzer_id, persona_id, persona["name"], "image")
                
                # Add video analyzer if configured (multimodal personas)
                if persona_config.video_analyzer_id:
                    add_analyzer(persona_config.video_analyzer_id, persona_id, persona["name"], "video")
                    
            except Exception as e:
                logger.warning("Error processing persona %s: %s", persona_id, e)
                continue
        
        return {"analyzers": analyzers}
    except Exception as e:
        logger.error("Failed to list analyzers: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Underwriting Policy Endpoints
# =============================================================================

@app.get("/api/policies")
async def get_policies(persona: str = "underwriting"):
    """Get policies for the specified persona.
    
    - For 'underwriting' persona: Returns underwriting policies from life-health-underwriting-policies.json
    - For 'automotive_claims' persona: Returns automotive claims policies from automotive-claims-policies.json
    - For 'life_health_claims': Returns both processing policies AND plan benefits from unified file
    - For other claims personas: Returns claims policies from their respective files
    """
    from app.underwriting_policies import load_policies as load_underwriting_policies
    
    try:
        settings = load_settings()
        
        # Special handling for automotive claims
        if persona == "automotive_claims":
            from app.claims.policies import ClaimsPolicyLoader
            loader = ClaimsPolicyLoader()
            loader.load_policies("prompts/automotive-claims-policies.json")
            policies = [
                {
                    "id": p.id,
                    "name": p.name,
                    "category": p.category,
                    "subcategory": p.subcategory,
                    "description": p.description,
                    "criteria": [
                        {
                            "id": c.id,
                            "condition": c.condition,
                            "severity": c.severity,
                            "action": c.action,
                            "rationale": c.rationale,
                        }
                        for c in p.criteria
                    ],
                    "modifying_factors": [
                        {"factor": mf.factor, "impact": mf.impact}
                        for mf in p.modifying_factors
                    ],
                    "references": p.references,
                }
                for p in loader.get_all_policies()
            ]
            return {
                "policies": policies,
                "total": len(policies),
                "persona": persona,
                "type": "automotive_claims",
            }
        
        # Life & Health Claims - load from unified file with both policies and plan benefits
        if persona == "life_health_claims":
            import json
            policy_file = Path(settings.app.prompts_root) / "life-health-claims-policies.json"
            if policy_file.exists():
                with open(policy_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                policies = []
                
                # Add processing policies
                for policy in data.get("policies", []):
                    policies.append(policy)
                
                # Add plan benefits as policies
                for plan_name, plan_data in data.get("plan_benefits", {}).items():
                    policies.append({
                        "id": f"PLAN-{plan_name.replace(' ', '-').upper()}",
                        "name": plan_name,
                        "category": "plan_benefits",
                        "subcategory": plan_data.get("plan_type", "Unknown"),
                        "description": f"{plan_data.get('plan_type', '')} plan with {plan_data.get('network', 'standard')} network",
                        **plan_data,
                    })
                
                return {
                    "policies": policies,
                    "total": len(policies),
                    "persona": persona,
                    "type": "life_health_claims",
                }
            else:
                return {
                    "policies": [],
                    "total": 0,
                    "persona": persona,
                    "type": "life_health_claims",
                    "error": "Policy file not found",
                }
        
        # Check if this is another claims persona (property_casualty_claims, etc.)
        is_claims_persona = "claims" in persona.lower()
        is_mortgage_persona = persona in ("mortgage", "mortgage_underwriting")
        
        if is_mortgage_persona:
            # Load mortgage underwriting policies (HCSF / internal bank rules)
            from app.underwriting_policies import load_policies_for_persona
            policies_data = load_policies_for_persona(settings.app.prompts_root, persona)
            policies = policies_data.get("policies", [])
            return {
                "policies": policies,
                "total": len(policies),
                "persona": persona,
                "type": "mortgage_underwriting",
            }
        elif is_claims_persona:
            # Load from persona-specific policy file
            from app.underwriting_policies import load_policies_for_persona
            policies_data = load_policies_for_persona(settings.app.prompts_root, persona)
            policies = policies_data.get("policies", [])
            return {
                "policies": policies,
                "total": len(policies),
                "persona": persona,
                "type": "claims",
            }
        else:
            # Load underwriting policies (risk assessment criteria)
            policies_data = load_underwriting_policies(settings.app.prompts_root)
            policies = policies_data.get("policies", [])
            return {
                "policies": policies,
                "total": len(policies),
                "persona": persona,
                "type": "underwriting",
            }
    except Exception as e:
        logger.error("Failed to get policies for persona %s: %s", persona, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/policies/{policy_id}")
async def get_policy_by_id(policy_id: str, persona: str = "underwriting"):
    """Get a specific policy by ID for the specified persona.
    
    Supports both policy IDs (e.g., FRD-001) and criteria IDs (e.g., FRD-001-B).
    For criteria IDs, returns the parent policy with the matching criteria highlighted.
    """
    import json
    from pathlib import Path
    
    # Mapping of personas to their policy files
    PERSONA_POLICY_FILES = {
        "underwriting": "prompts/life-health-underwriting-policies.json",
        "life_health_claims": "prompts/life-health-claims-policies.json",
        "automotive_claims": "prompts/automotive-claims-policies.json",
        "property_casualty_claims": "prompts/property-casualty-claims-policies.json",
        "mortgage_underwriting": "prompts/mortgage-underwriting-policies.json",
        "mortgage": "prompts/mortgage-underwriting-policies.json",
    }
    
    try:
        # Get the policy file for this persona
        policy_file = PERSONA_POLICY_FILES.get(persona.lower())
        if not policy_file:
            # Fall back to underwriting
            policy_file = PERSONA_POLICY_FILES["underwriting"]
        
        policy_path = Path(policy_file)
        if not policy_path.exists():
            raise HTTPException(status_code=404, detail=f"Policy file not found for persona: {persona}")
        
        with open(policy_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        policies = data.get("policies", [])
        
        # First, try to find an exact policy match
        for policy in policies:
            if policy.get("id") == policy_id:
                return policy
        
        # If not found, search within criteria (for criteria IDs like FRD-001-B)
        for policy in policies:
            for criteria in policy.get("criteria", []):
                if criteria.get("id") == policy_id:
                    # Return the parent policy with matched_criteria indicated
                    result = dict(policy)
                    result["matched_criteria_id"] = policy_id
                    result["matched_criteria"] = criteria
                    return result
        
        raise HTTPException(status_code=404, detail=f"Policy not found: {policy_id}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get policy %s: %s", policy_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/policies/category/{category}")
async def get_policies_by_category(category: str):
    """Get all policies in a specific category."""
    from app.underwriting_policies import get_policies_by_category as get_by_category
    
    try:
        settings = load_settings()
        policies = get_by_category(settings.app.prompts_root, category)
        
        return {
            "category": category,
            "policies": policies,
            "total": len(policies),
        }
    except Exception as e:
        logger.error("Failed to get policies for category %s: %s", category, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Background RAG Indexing Helpers
# =============================================================================

async def _background_reindex_policy(settings, policy_id: str):
    """Background task to reindex a policy after create/update."""
    try:
        from app.rag.indexer import PolicyIndexer
        
        logger.info("Background reindexing policy: %s", policy_id)
        indexer = PolicyIndexer(settings=settings)
        await indexer.reindex_policy(policy_id)
        logger.info("Background reindex complete for policy: %s", policy_id)
    except Exception as e:
        logger.error("Background reindex failed for policy %s: %s", policy_id, e)


async def _background_delete_policy_chunks(settings, policy_id: str):
    """Background task to delete policy chunks after policy deletion."""
    try:
        from app.rag.repository import PolicyChunkRepository
        
        logger.info("Deleting chunks for policy: %s", policy_id)
        repo = PolicyChunkRepository(schema=settings.database.schema or "workbenchiq")
        deleted = await repo.delete_chunks_by_policy(policy_id)
        logger.info("Deleted %d chunks for policy: %s", deleted, policy_id)
    except Exception as e:
        logger.error("Failed to delete chunks for policy %s: %s", policy_id, e)


class PolicyCreateRequest(BaseModel):
    """Request model for creating a policy."""
    id: str
    category: str
    subcategory: str
    name: str
    description: str
    criteria: List[dict] = []
    modifying_factors: List[dict] = []
    references: List[str] = []


class PolicyUpdateRequest(BaseModel):
    """Request model for updating a policy."""
    category: Optional[str] = None
    subcategory: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    criteria: Optional[List[dict]] = None
    modifying_factors: Optional[List[dict]] = None
    references: Optional[List[str]] = None


@app.post("/api/policies")
async def create_policy(request: PolicyCreateRequest):
    """Create a new underwriting policy."""
    from app.underwriting_policies import add_policy
    
    try:
        settings = load_settings()
        policy_data = request.model_dump()
        result = add_policy(settings.app.prompts_root, policy_data)
        
        logger.info("Created policy %s", request.id)
        
        # Trigger background reindex if PostgreSQL is enabled
        if settings.database.backend == "postgresql":
            import asyncio
            asyncio.create_task(_background_reindex_policy(settings, request.id))
        
        return {
            "message": "Police cr\u00e9\u00e9e",
            "policy": result["policy"]
        }
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except Exception as e:
        logger.error("Failed to create policy: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/policies/{policy_id}")
async def update_policy_endpoint(policy_id: str, request: PolicyUpdateRequest):
    """Update an existing underwriting policy."""
    from app.underwriting_policies import update_policy
    
    try:
        settings = load_settings()
        # Only include non-None values in the update
        update_data = {k: v for k, v in request.model_dump().items() if v is not None}
        result = update_policy(settings.app.prompts_root, policy_id, update_data)
        
        logger.info("Updated policy %s", policy_id)
        
        # Trigger background reindex if PostgreSQL is enabled
        if settings.database.backend == "postgresql":
            import asyncio
            asyncio.create_task(_background_reindex_policy(settings, policy_id))
        
        return {
            "message": "Police mise \u00e0 jour",
            "policy": result["policy"]
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to update policy %s: %s", policy_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/policies/{policy_id}")
async def delete_policy_endpoint(policy_id: str):
    """Delete an underwriting policy."""
    from app.underwriting_policies import delete_policy
    
    try:
        settings = load_settings()
        result = delete_policy(settings.app.prompts_root, policy_id)
        
        logger.info("Deleted policy %s", policy_id)
        
        # Delete from RAG index if PostgreSQL is enabled
        if settings.database.backend == "postgresql":
            import asyncio
            asyncio.create_task(_background_delete_policy_chunks(settings, policy_id))
        
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to delete policy %s: %s", policy_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Feedback API Endpoints
# =============================================================================

class FeedbackPayload(BaseModel):
    agent_type: str         # 'risk' | 'police' | 'data' | 'data_agent' | 'chat'
    feedback_type: str      # 'positive' | 'negative' | 'correction'
    original_query: Optional[str] = None
    agent_response: Optional[str] = None
    correction: Optional[str] = None
    persona: Optional[str] = None
    session_id: Optional[str] = None
    conversation_id: Optional[str] = None
    application_id: Optional[str] = None


@app.post("/api/feedback")
async def submit_feedback(payload: FeedbackPayload, background_tasks: BackgroundTasks):
    """Capture feedback (👍/👎/correction) for the feedback loop.

    Stores in PostgreSQL feedback_events table.
    Mirrored to Fabric via CDC for orchestration.
    """
    from app.feedback import insert_feedback_event

    # Validate agent_type and feedback_type
    valid_agent_types = {"risk", "police", "data", "data_agent", "chat"}
    valid_feedback_types = {"positive", "negative", "correction"}
    if payload.agent_type not in valid_agent_types:
        raise HTTPException(status_code=400, detail=f"Invalid agent_type. Must be one of: {valid_agent_types}")
    if payload.feedback_type not in valid_feedback_types:
        raise HTTPException(status_code=400, detail=f"Invalid feedback_type. Must be one of: {valid_feedback_types}")

    feedback_id = await insert_feedback_event(
        agent_type=payload.agent_type,
        feedback_type=payload.feedback_type,
        original_query=payload.original_query,
        agent_response=payload.agent_response,
        correction=payload.correction,
        persona=payload.persona,
        session_id=payload.session_id,
        conversation_id=payload.conversation_id,
        application_id=payload.application_id,
    )

    if feedback_id is None:
        raise HTTPException(status_code=503, detail="Base de données indisponible pour le stockage des retours")

    return {"status": "ok", "feedback_id": feedback_id}


@app.get("/api/feedback")
async def list_feedback(
    processed: Optional[bool] = Query(None),
    agent_type: Optional[str] = Query(None),
    persona: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """List feedback events with optional filters (admin/analytics)."""
    from app.feedback import list_feedback_events

    events = await list_feedback_events(
        processed=processed,
        agent_type=agent_type,
        persona=persona,
        limit=limit,
    )
    return {"events": events, "count": len(events)}


@app.get("/api/corrections")
async def list_corrections_endpoint(
    persona: Optional[str] = Query(None),
    agent_type: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    active: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    """List few-shot corrections from the correction store."""
    from app.feedback import list_corrections

    corrections = await list_corrections(
        persona=persona,
        agent_type=agent_type,
        category=category,
        active=active,
        limit=limit,
    )
    return {"corrections": corrections, "count": len(corrections)}


@app.get("/api/corrections/stats")
async def corrections_stats():
    """Get summary statistics for the corrections store."""
    from app.feedback import get_correction_stats

    stats = await get_correction_stats()
    return stats


@app.get("/api/corrections/impact")
async def corrections_impact():
    """Get HITL impact metrics: feedback trends, correction coverage, per-persona breakdown."""
    from app.feedback import get_correction_impact

    impact = await get_correction_impact()
    return impact


# =============================================================================
# Chat API Endpoints
# =============================================================================

@app.post("/api/applications/{app_id}/chat")
async def chat_with_application(app_id: str, request: ChatRequest):
    """Chat about an application using the Agent Framework with tool-calling."""
    try:
        settings = load_settings()
        
        # Load application data first to get its persona
        app_md = load_application(settings.app.storage_root, app_id)
        if not app_md:
            raise HTTPException(status_code=404, detail=f"Application {app_id} not found")
        
        # Determine persona - prefer request, then app's persona, then default to underwriting
        persona = request.persona or app_md.persona or "underwriting"
        
        from app.agents.api_integration import agent_chat
        history_dicts = None
        if request.history:
            history_dicts = [{"role": m.role, "content": m.content} for m in request.history]
        result = await agent_chat(
            settings,
            app_id,
            request.message,
            history_dicts,
            persona,
            agent_type=request.agent_type or "auto",
            use_corrections=request.use_corrections,
            language=request.language or "en",
        )
        return result
    
    except HTTPException:
        raise
    except AgentServiceError as exc:
        logger.error("Chat failed: code=%s request_id=%s", exc.code, exc.request_id)
        raise HTTPException(status_code=exc.status_code, detail=exc.public_detail()) from exc
    except Exception as e:
        logger.error("Chat failed for application %s: %s", app_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Chat could not be completed") from e


@app.post("/api/applications/{app_id}/chat/suggestions")
async def generate_chat_suggestions(app_id: str, body: dict | None = None):
    """Generate dossier-aware chat suggestion pills using the LLM.

    Returns 3-4 short French questions a claims/underwriting handler is likely
    to ask about THIS specific dossier, based on its persona, status, decision,
    context labels and tasks.

    Body (all optional):
        { "language": "fr", "agent": "auto|data|policy|analysis|dashboard" }
    """
    try:
        settings = load_settings()
        app_md = load_application(settings.app.storage_root, app_id)
        if not app_md:
            raise HTTPException(status_code=404, detail=f"Application {app_id} not found")

        _body = body or {}
        language = _body.get("language", "en")
        agent = _body.get("agent", "auto")

        # Build a compact, structured context for the LLM
        labels = app_md.context_labels or []
        tasks = app_md.context_tasks or []
        decision = None
        if isinstance(app_md.llm_outputs, dict):
            decision = app_md.llm_outputs.get("decision") or app_md.llm_outputs.get("recommandation")
        summary_text = None
        if isinstance(app_md.llm_outputs, dict):
            summary_text = (
                app_md.llm_outputs.get("summary")
                or app_md.llm_outputs.get("resume")
                or app_md.llm_outputs.get("synthese")
            )

        # Compact labels/tasks to just key + label/category to keep prompt small
        compact_labels = [
            {"key": l.get("key"), "type": l.get("type"), "label": l.get("label")}
            for l in labels[:20]
        ]
        compact_tasks = [
            {"category": t.get("category"), "label": t.get("label") or t.get("title")}
            for t in tasks[:10]
        ]

        dossier_ctx: dict[str, Any] = {
            "persona": app_md.persona,
            "status": app_md.status,
            "has_decision": bool(decision),
            "active_agent": agent,
            "labels": compact_labels,
            "tasks": compact_tasks,
        }
        if summary_text:
            dossier_ctx["summary"] = str(summary_text)[:600]

        brand = settings.brand_name
        system_prompt = (
            f"Tu génères des questions suggérées pour le chat conversationnel {brand}IQ. "
            "Ces questions seront affichées comme des pastilles cliquables sous la zone de saisie. "
            "Elles doivent aider un gestionnaire d'assurance à explorer rapidement le dossier ouvert.\n\n"
            "RÈGLES STRICTES :\n"
            "- 3 à 4 suggestions maximum, courtes (≤ 12 mots), formulées comme des questions ou ordres directs.\n"
            "- Spécifiques AU DOSSIER : exploite les labels, tâches, statut et persona fournis.\n"
            "- Pas de redondance : chaque suggestion doit ouvrir un angle distinct (couverture, pièces, fraude, recours, conformité, etc.).\n"
            f"- Ton professionnel, jargon assurance {brand} accepté (CG, IRSI, HCSF, Cat-Nat, LTV, franchise…).\n"
            f"- Langue : {language}.\n"
            "- Si le dossier n'a pas encore été analysé (status pending/processing), propose des questions sur l'avancement.\n"
            "- Si une décision a été prise, propose des questions sur les prochaines étapes.\n\n"
            "Réponds UNIQUEMENT en JSON valide :\n"
            '{ "suggestions": ["question 1", "question 2", "question 3"] }'
        )

        user_prompt = (
            "Contexte du dossier (JSON) :\n"
            f"{json.dumps(dossier_ctx, ensure_ascii=False)}\n\n"
            "Génère 3 à 4 questions suggérées adaptées."
        )

        from app.openai_client import chat_completion

        raw = await asyncio.to_thread(
            chat_completion,
            settings.openai,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=400,
            temperature=0.4,
            response_format="json_object",
            timeout=15,
            max_retries=1,
        )

        content = raw.get("content", "") or "{}"
        try:
            parsed = json.loads(content)
            suggestions = parsed.get("suggestions") or []
        except Exception:
            suggestions = []

        # Sanitize: keep strings, trim, dedupe, cap at 4
        cleaned: list[str] = []
        seen: set[str] = set()
        for s in suggestions:
            if not isinstance(s, str):
                continue
            s = s.strip().strip('"').strip()
            if not s or s.lower() in seen:
                continue
            seen.add(s.lower())
            cleaned.append(s)
            if len(cleaned) >= 4:
                break

        return {"suggestions": cleaned, "source": "llm" if cleaned else "empty"}

    except HTTPException:
        raise
    except Exception as e:
        logger.warning("Chat suggestions failed for %s: %s", app_id, e)
        # Soft-fail: frontend has a deterministic fallback
        return {"suggestions": [], "source": "error", "error": str(e)}


@app.get("/api/workflows")
async def list_workflows():
    """List available sinistre processing workflows."""
    from app.agents.workflows import WORKFLOWS
    settings = load_settings()
    return {"workflows": list(WORKFLOWS.values()), "brand": settings.brand_name}


@app.post("/api/applications/{app_id}/workflow/{workflow_id}")
async def run_workflow(app_id: str, workflow_id: str, body: dict | None = None):
    """Execute a named workflow on an application.

    Available workflows: express, complet, fraude.
    Body: { persona?: string, language?: string }
    """
    try:
        settings = load_settings()
        app_md = load_application(settings.app.storage_root, app_id)
        if not app_md:
            raise HTTPException(status_code=404, detail=f"Application {app_id} not found")

        _body = body or {}
        effective_persona = _body.get("persona") or app_md.persona or "habitation_claims"
        language = _body.get("language", "en")

        from app.agents.api_integration import agent_workflow
        result = await agent_workflow(settings, app_id, workflow_id, effective_persona, language=language)

        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Workflow %s failed for %s: %s", workflow_id, app_id, e, exc_info=True)
        if isinstance(e, AgentServiceError):
            raise HTTPException(status_code=e.status_code, detail=e.public_detail()) from e
        raise HTTPException(status_code=500, detail="Workflow could not be completed") from e


# =============================================================================
# Agent Framework API Endpoints
# =============================================================================

@app.get("/api/agents/status")
async def get_agent_status():
    """Return Agent Framework status, agents and workflows actually wired in the backend."""
    from app.agents.api_integration import FRAMEWORK_LABEL
    from app.agents.workflows import WORKFLOWS

    settings = load_settings()
    web_tools = ["webiq_web", "webiq_news", "webiq_browse"] if settings.webiq.enabled else ["web_search"]
    return {
        "enabled": True,
        "framework": FRAMEWORK_LABEL,
        "agents": [
            {
                "name": "ChatAgent",
                "description": "Interactive Q&A with policy search, dossier context and web grounding",
                "tools": ["search_policies", "get_application_summary", "get_glossary",
                          "query_fabric_data", "analyze_image_fraud", *web_tools],
            },
            {
                "name": "AnalysisAgent",
                "description": "Prompt-based document analysis with dynamic section selection",
                "tools": ["analyze_section", "list_available_analyses", "get_extracted_fields", "search_policies"],
            },
        ],
        "workflows": [
            {"id": w["id"], "pattern": w["pattern"], "agents": w["agents"]} for w in WORKFLOWS.values()
        ],
    }


# =============================================================================
# Conversation History API Endpoints
# =============================================================================

def get_conversations_dir(storage_root: str) -> Path:
    """Get the conversations directory path."""
    return Path(storage_root) / "conversations"


def get_app_conversations_dir(storage_root: str, app_id: str) -> Path:
    """Get the conversations directory for a specific application."""
    return get_conversations_dir(storage_root) / app_id


def load_conversation(storage_root: str, app_id: str, conversation_id: str) -> Optional[dict]:
    """Load a conversation from disk."""
    conv_file = get_app_conversations_dir(storage_root, app_id) / f"{conversation_id}.json"
    if conv_file.exists():
        try:
            return json.loads(conv_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error("Failed to load conversation %s: %s", conversation_id, e)
    return None


def save_conversation(storage_root: str, app_id: str, conversation: dict) -> None:
    """Save a conversation to disk."""
    conv_dir = get_app_conversations_dir(storage_root, app_id)
    conv_dir.mkdir(parents=True, exist_ok=True)
    conv_file = conv_dir / f"{conversation['id']}.json"
    conv_file.write_text(json.dumps(conversation, indent=2), encoding="utf-8")


def list_conversations(storage_root: str, app_id: str) -> List[dict]:
    """List all conversations for an application."""
    conv_dir = get_app_conversations_dir(storage_root, app_id)
    if not conv_dir.exists():
        return []
    
    conversations = []
    for conv_file in conv_dir.glob("*.json"):
        try:
            conv = json.loads(conv_file.read_text(encoding="utf-8"))
            # Create summary
            messages = conv.get("messages", [])
            preview = None
            if messages:
                # Get first user message as preview
                for msg in messages:
                    if msg.get("role") == "user":
                        preview = msg.get("content", "")[:100]
                        if len(msg.get("content", "")) > 100:
                            preview += "..."
                        break
            
            conversations.append({
                "id": conv["id"],
                "application_id": conv.get("application_id", app_id),
                "title": conv.get("title", "Untitled Conversation"),
                "created_at": conv.get("created_at", ""),
                "updated_at": conv.get("updated_at", ""),
                "message_count": len(messages),
                "preview": preview,
            })
        except Exception as e:
            logger.error("Failed to read conversation file %s: %s", conv_file, e)
    
    # Sort by updated_at descending
    conversations.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
    return conversations


def generate_conversation_title(first_message: str) -> str:
    """Generate a title from the first user message."""
    # Take first 50 chars and clean up
    title = first_message[:50].strip()
    if len(first_message) > 50:
        title += "..."
    return title or "New Conversation"


@app.get("/api/applications/{app_id}/conversations")
async def get_application_conversations(app_id: str):
    """List all conversations for an application."""
    try:
        settings = load_settings()
        conversations = list_conversations(settings.app.storage_root, app_id)
        return {"conversations": conversations}
    except Exception as e:
        logger.error("Failed to list conversations for %s: %s", app_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/conversations")
async def get_all_conversations(limit: int = 50):
    """List conversations across all applications."""
    try:
        settings = load_settings()
        storage_root = Path(settings.app.storage_root)
        
        all_conversations = []
        
        # Iterate through all application directories
        if storage_root.exists():
            # Check for conversations in data/conversations/ (legacy)
            conversations_dir = storage_root / "conversations"
            if conversations_dir.exists():
                for app_dir in conversations_dir.iterdir():
                    if app_dir.is_dir():
                        app_id = app_dir.name
                        convs = list_conversations(settings.app.storage_root, app_id)
                        all_conversations.extend(convs)
            
            # Check for conversations in data/applications/*/conversations/
            applications_dir = storage_root / "applications"
            if applications_dir.exists():
                for app_dir in applications_dir.iterdir():
                    if app_dir.is_dir():
                        app_id = app_dir.name
                        app_conv_dir = app_dir / "conversations"
                        if app_conv_dir.exists():
                            for conv_file in app_conv_dir.glob("*.json"):
                                try:
                                    conv = json.loads(conv_file.read_text(encoding="utf-8"))
                                    messages = conv.get("messages", [])
                                    preview = None
                                    if messages:
                                        for msg in messages:
                                            if msg.get("role") == "user":
                                                preview = msg.get("content", "")[:100]
                                                if len(msg.get("content", "")) > 100:
                                                    preview += "..."
                                                break
                                    
                                    all_conversations.append({
                                        "id": conv["id"],
                                        "application_id": app_id,
                                        "title": conv.get("title", "Untitled Conversation"),
                                        "created_at": conv.get("created_at", ""),
                                        "updated_at": conv.get("updated_at", ""),
                                        "message_count": len(messages),
                                        "preview": preview,
                                    })
                                except Exception as e:
                                    logger.error("Failed to read conversation file %s: %s", conv_file, e)
        
        # Sort by updated_at descending (most recent first)
        all_conversations.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
        
        # Apply limit
        all_conversations = all_conversations[:limit]
        
        return {"conversations": all_conversations}
    except Exception as e:
        logger.error("Failed to list all conversations: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/applications/{app_id}/conversations/{conversation_id}")
async def get_conversation(app_id: str, conversation_id: str):
    """Get a specific conversation with all messages."""
    try:
        settings = load_settings()
        conversation = load_conversation(settings.app.storage_root, app_id, conversation_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation introuvable")
        return conversation
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get conversation %s: %s", conversation_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/applications/{app_id}/conversations/{conversation_id}")
async def delete_conversation(app_id: str, conversation_id: str):
    """Delete a conversation."""
    try:
        settings = load_settings()
        conv_file = get_app_conversations_dir(settings.app.storage_root, app_id) / f"{conversation_id}.json"
        if not conv_file.exists():
            raise HTTPException(status_code=404, detail="Conversation introuvable")
        conv_file.unlink()
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete conversation %s: %s", conversation_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/applications/{app_id}/conversations")
async def create_or_continue_conversation(app_id: str, request: ChatRequest):
    if not request.stream:
        return await _complete_conversation(app_id, request)

    async def events():
        queue = asyncio.Queue(maxsize=32)

        async def on_delta(text: str):
            await queue.put({"type": "delta", "text": text})

        async def produce():
            try:
                result = await _complete_conversation(app_id, request, on_delta)
                await queue.put({"type": "done", "result": result})
            except HTTPException as exc:
                await queue.put({"type": "error", "status": exc.status_code, "detail": exc.detail})

        task = asyncio.create_task(produce())
        try:
            yield ": connected\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                if event["type"] in {"done", "error"}:
                    break
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )


async def _complete_conversation(app_id: str, request: ChatRequest, on_delta=None):
    """Create a new conversation or continue an existing one, using the Agent Framework."""
    from datetime import datetime
    from time import perf_counter
    import uuid
    
    started = perf_counter()
    try:
        settings = load_settings()
        now = datetime.utcnow().isoformat() + "Z"
        
        # Load application first to get its persona
        app_md = await asyncio.to_thread(load_application, settings.app.storage_root, app_id)
        if not app_md:
            raise HTTPException(status_code=404, detail=f"Application {app_id} not found")
        
        # Determine persona - use from request, then app's persona, then default
        persona = request.persona or app_md.persona or "underwriting"
        logger.info("Conversation for app %s using persona: %s (request=%s, app=%s)", 
                    app_id, persona, request.persona, app_md.persona)
        
        # Load or create conversation
        if request.conversation_id:
            conversation = await asyncio.to_thread(
                load_conversation, settings.app.storage_root, app_id, request.conversation_id
            )
            if not conversation:
                raise HTTPException(status_code=404, detail="Conversation introuvable")
        else:
            # Create new conversation
            conversation = {
                "id": str(uuid.uuid4())[:8],
                "application_id": app_id,
                "title": generate_conversation_title(request.message),
                "created_at": now,
                "updated_at": now,
                "messages": [],
                "persona": persona,
            }
        
        # Add user message
        user_message = {
            "role": "user",
            "content": request.message,
            "timestamp": now,
        }
        conversation["messages"].append(user_message)
        conversation["updated_at"] = now
        
        # Use Agent Framework with tool-calling
        from app.agents.api_integration import agent_chat
        history_dicts = None
        if len(conversation["messages"]) > 1:
            history_dicts = [{"role": m["role"], "content": m["content"]} for m in conversation["messages"][:-1]]
        load_ms = round((perf_counter() - started) * 1000, 1)
        result = await agent_chat(
            settings,
            app_id,
            request.message,
            history_dicts,
            persona,
            agent_type=request.agent_type or "auto",
            use_corrections=request.use_corrections,
            language=request.language or "en",
            **({"on_delta": on_delta} if on_delta is not None else {}),
        )
        
        # Save agent response into conversation
        assistant_message = {
            "role": "assistant",
            "content": result["response"],
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
        conversation["messages"].append(assistant_message)
        conversation["updated_at"] = assistant_message["timestamp"]
        save_started = perf_counter()
        await asyncio.to_thread(save_conversation, settings.app.storage_root, app_id, conversation)
        timings = result["agent"].setdefault("timings_ms", {})
        timings["conversation_load_ms"] = load_ms
        timings["conversation_save_ms"] = round((perf_counter() - save_started) * 1000, 1)
        timings["request_ms"] = round((perf_counter() - started) * 1000, 1)
        logger.info("conversation done: app_id=%s timings_ms=%s", app_id, timings)
        
        return {
            "conversation_id": conversation["id"],
            "response": result["response"],
            "usage": result.get("usage", {}),
            "title": conversation["title"],
            "agent": result.get("agent"),
        }
    
    except HTTPException:
        raise
    except AgentServiceError as exc:
        logger.error("Conversation failed: code=%s request_id=%s", exc.code, exc.request_id)
        raise HTTPException(status_code=exc.status_code, detail=exc.public_detail()) from exc
    except Exception as e:
        logger.error("Conversation failed for application %s: %s", app_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Conversation could not be completed") from e


# =============================================================================
# Health Check API Endpoints
# =============================================================================

@app.get("/api/health/database")
async def health_check_database():
    """Database health check endpoint."""
    from app.database.pool import get_pool
    settings = load_settings()
    if settings.database.backend != "postgresql":
        return {"status": "skipped", "message": "Backend PostgreSQL non utilis\u00e9."}
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            version = await conn.fetchval("SELECT version();")
            return {"status": "ok", "version": version}
    except Exception as e:
        return {"status": "error", "error": str(e)}


# =============================================================================
# RAG Indexing API Endpoints
# =============================================================================

class ReindexRequest(BaseModel):
    force: bool = True  # Whether to delete existing chunks first


class ReindexResponse(BaseModel):
    status: str
    policies_indexed: Optional[int] = None
    chunks_stored: Optional[int] = None
    total_time_seconds: Optional[float] = None
    error: Optional[str] = None


@app.post("/api/admin/policies/reindex", response_model=ReindexResponse)
async def reindex_all_policies(
    request: ReindexRequest = ReindexRequest(),
    persona: str = Query(default="underwriting", description="Persona to reindex policies for"),
):
    """
    Reindex all policies for a specific persona's RAG search.
    
    Supported personas:
    - underwriting: Life & health underwriting policies
    - life_health_claims: Health claims processing policies
    - automotive_claims: Automotive claims policies
    - property_casualty_claims: P&C claims policies
    
    This will:
    1. Load all policies from the persona's JSON file
    2. Chunk them into searchable segments
    3. Generate embeddings via Azure OpenAI
    4. Store in PostgreSQL with pgvector
    
    Use force=True (default) to delete existing chunks before reindexing.
    """
    settings = load_settings()
    
    # Check if RAG is enabled
    if settings.database.backend != "postgresql":
        return ReindexResponse(
            status="skipped",
            error="PostgreSQL backend not configured. Set DATABASE_BACKEND=postgresql."
        )
    
    try:
        from app.rag.persona_indexer import get_indexer_for_persona, persona_supports_rag
        
        if not persona_supports_rag(persona):
            return ReindexResponse(
                status="error",
                error=f"Persona '{persona}' does not support RAG indexing."
            )
        
        indexer = await get_indexer_for_persona(persona, settings)
        metrics = await indexer.index_policies(force_reindex=request.force)
        
        return ReindexResponse(
            status=metrics.get("status", "unknown"),
            policies_indexed=metrics.get("policies_indexed"),
            chunks_stored=metrics.get("chunks_stored"),
            total_time_seconds=metrics.get("total_time_seconds"),
        )
    except Exception as e:
        logger.error("Failed to reindex policies for %s: %s", persona, e, exc_info=True)
        return ReindexResponse(status="error", error=str(e))


@app.post("/api/admin/policies/{policy_id}/reindex", response_model=ReindexResponse)
async def reindex_single_policy(policy_id: str):
    """
    Reindex a single policy by ID.
    
    Useful after editing a policy in the UI.
    """
    settings = load_settings()
    
    if settings.database.backend != "postgresql":
        return ReindexResponse(
            status="skipped",
            error="PostgreSQL backend not configured."
        )
    
    try:
        from app.rag.indexer import PolicyIndexer
        
        indexer = PolicyIndexer(settings=settings)
        metrics = await indexer.reindex_policy(policy_id)
        
        if metrics.get("status") == "skipped":
            return ReindexResponse(
                status="not_found",
                error=f"Policy '{policy_id}' not found."
            )
        
        return ReindexResponse(
            status=metrics.get("status", "unknown"),
            policies_indexed=metrics.get("policies_indexed"),
            chunks_stored=metrics.get("chunks_stored"),
            total_time_seconds=metrics.get("total_time_seconds"),
        )
    except Exception as e:
        logger.error("Failed to reindex policy %s: %s", policy_id, e, exc_info=True)
        return ReindexResponse(status="error", error=str(e))


@app.get("/api/admin/policies/index-stats")
async def get_index_stats(
    persona: str = Query(default="underwriting", description="Persona to get index stats for"),
):
    """
    Get statistics about the current policy index for a persona.
    
    Supported personas:
    - underwriting: Life & health underwriting policies
    - life_health_claims: Health claims processing policies
    - automotive_claims: Automotive claims policies
    - property_casualty_claims: P&C claims policies
    """
    settings = load_settings()
    
    if settings.database.backend != "postgresql":
        return {"status": "skipped", "error": "PostgreSQL backend not configured."}
    
    try:
        from app.rag.persona_indexer import get_index_stats_for_persona, persona_supports_rag
        
        if not persona_supports_rag(persona):
            return {"status": "error", "error": f"Persona '{persona}' does not support RAG indexing."}
        
        stats = await get_index_stats_for_persona(persona, settings)
        return stats
    except Exception as e:
        logger.error("Failed to get index stats for %s: %s", persona, e, exc_info=True)
        return {"status": "error", "error": str(e)}


# ============================================================================
# Claims Policy Admin Endpoints (Deprecated - use /api/admin/policies/* with persona param)
# ============================================================================

@app.post("/api/admin/claims-policies/reindex", response_model=ReindexResponse)
async def reindex_all_claims_policies(request: ReindexRequest = ReindexRequest()):
    """
    [DEPRECATED] Reindex automotive claims policies.
    
    Use POST /api/admin/policies/reindex?persona=automotive_claims instead.
    This endpoint is maintained for backwards compatibility.
    """
    # Redirect to unified endpoint
    return await reindex_all_policies(request, persona="automotive_claims")


@app.get("/api/admin/claims-policies/index-stats")
async def get_claims_index_stats():
    """
    [DEPRECATED] Get automotive claims policy index stats.
    
    Use GET /api/admin/policies/index-stats?persona=automotive_claims instead.
    This endpoint is maintained for backwards compatibility.
    """
    # Redirect to unified endpoint
    return await get_index_stats(persona="automotive_claims")


# =============================================================================
# Mortgage Underwriting API Endpoints
# =============================================================================

@app.post("/api/mortgage/analyze")
async def mortgage_analyze(request: MortgageAnalyzeRequest):
    """
    Analyze a mortgage application against French HCSF / internal bank policies.
    
    Returns:
        - ratios: GDS, TDS, LTV calculations
        - decision: APPROVE, DECLINE, or REFER
        - findings: List of policy evaluation findings
        - conditions: Any conditions for approval
    """
    try:
        # Validate required fields
        if not request.borrower or not request.income or not request.property or not request.loan:
            raise HTTPException(
                status_code=422,
                detail="Missing required fields: borrower, income, property, and loan are required"
            )
        
        # Build case data for mortgage processing
        case_data = {
            "application_id": request.application_id,
            "borrower": request.borrower.model_dump() if request.borrower else {},
            "income": request.income.model_dump() if request.income else {},
            "property": request.property.model_dump() if request.property else {},
            "loan": request.loan.model_dump() if request.loan else {},
        }
        
        # Calculate ratios using mortgage calculator
        from app.mortgage.calculator import MortgageCalculator
        calculator = MortgageCalculator()
        
        purchase_price = case_data["property"].get("purchase_price", 0)
        loan_amount = case_data["loan"].get("amount", 0)
        down_payment = purchase_price - loan_amount
        annual_income = case_data["income"].get("annual_salary", 0)
        amortization = case_data["loan"].get("amortization_years", 25)
        rate = case_data["loan"].get("rate", 5.25) / 100
        
        # Calculate housing costs (simplified - PITI)
        monthly_payment = calculator.compute_mortgage_payment(
            principal=loan_amount,
            annual_rate=rate,
            amortization_years=amortization,
        )
        property_tax_monthly = purchase_price * 0.01 / 12  # Estimate 1% annual
        heating_monthly = 150  # Estimate
        
        total_housing_cost = monthly_payment + property_tax_monthly + heating_monthly
        monthly_income = annual_income / 12
        
        # Calculate ratios
        gds = total_housing_cost / monthly_income if monthly_income > 0 else 0
        tds = gds  # Simplified - would add other debts
        ltv = loan_amount / purchase_price if purchase_price > 0 else 0
        
        ratios = {"gds": round(gds, 4), "tds": round(tds, 4), "ltv": round(ltv, 4)}
        
        # Build case for policy evaluation
        case_for_eval = {
            "ratios": ratios,
            "deal": {
                "purchase_price": purchase_price,
                "down_payment": down_payment,
            },
            "loan": {
                "amount": loan_amount,
                "amortization_years": amortization,
                "contract_rate": rate,
                "loan_type": "insured" if ltv > 0.80 else "conventional",
            },
        }
        
        # Evaluate against policies
        from app.mortgage.policy_engine import MortgagePolicyEvaluator, RecommendationEngine
        evaluator = MortgagePolicyEvaluator()
        findings = evaluator.evaluate_all(case_for_eval)
        
        # Generate recommendation
        recommendation_engine = RecommendationEngine()
        recommendation = recommendation_engine.generate_recommendation(findings)
        
        return {
            "application_id": request.application_id,
            "ratios": ratios,
            "decision": recommendation.decision,
            "confidence": recommendation.confidence,
            "findings": [
                {
                    "rule_id": f.rule_id,
                    "severity": f.severity,
                    "category": f.category,
                    "message": f.message,
                }
                for f in findings
            ],
            "conditions": recommendation.conditions,
            "reasons": recommendation.reasons,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Mortgage analysis failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mortgage/upload")
async def mortgage_upload(
    file: UploadFile = File(...),
    application_id: str = Form(...),
    doc_type: str = Form("application"),
):
    """
    Upload a document for mortgage application processing.
    
    Supported doc_types:
        - application: Mortgage application form
        - paystub: Pay stub for income verification
        - t4: T4 tax slip
        - employment_letter: Employment verification letter
        - property_assessment: Property assessment/appraisal
    """
    try:
        settings = load_settings()
        
        # Read file content
        content = await file.read()
        
        # Store the file
        file_data = [{"name": file.filename, "content": content}]
        stored_files = save_uploaded_files(
            settings.app.storage_root,
            application_id,
            file_data,
            public_base_url=settings.app.public_files_base_url,
        )
        
        # Return basic response (full extraction would use Content Understanding)
        return {
            "doc_id": f"{application_id}-{doc_type}-001",
            "doc_type": doc_type,
            "filename": file.filename,
            "application_id": application_id,
            "extracted_fields": {},  # Would be populated by document processor
            "status": "uploaded",
        }
        
    except Exception as e:
        logger.error("Mortgage upload failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mortgage/query")
async def mortgage_query(request: MortgageQueryRequest):
    """
    Query mortgage policies using RAG.
    
    Returns relevant policy excerpts and sources for the query.
    """
    try:
        from app.rag.service import RAGService
        
        rag_service = RAGService(persona="mortgage_underwriting")
        await rag_service.initialize()
        
        result = await rag_service.query(
            user_query=request.query,
            top_k=5,
        )
        
        return {
            "answer": result.context,
            "sources": [
                {
                    "content": r.content[:200],
                    "source": r.source,
                    "score": r.similarity_score,
                }
                for r in result.results
            ],
            "query": request.query,
        }
        
    except Exception as e:
        logger.error("Mortgage query failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/mortgage/applications")
async def list_mortgage_applications():
    """List all mortgage applications."""
    try:
        settings = load_settings()
        apps = list_applications(settings.app.storage_root)
        
        # Filter to mortgage persona (match both 'mortgage' and 'mortgage_underwriting')
        mortgage_personas = {'mortgage', 'mortgage_underwriting'}
        mortgage_apps = [
            app for app in apps
            if (app.get('persona') if isinstance(app, dict) else getattr(app, 'persona', None)) in mortgage_personas
        ]
        
        return {
            "applications": [
                {
                    "id": app.get("id") if isinstance(app, dict) else app.id,
                    "created_at": app.get("created_at") if isinstance(app, dict) else app.created_at,
                    "status": app.get("status") if isinstance(app, dict) else app.status,
                    "external_reference": app.get("external_reference") if isinstance(app, dict) else app.external_reference,
                }
                for app in mortgage_apps
            ],
            "count": len(mortgage_apps),
        }
        
    except Exception as e:
        logger.error("Failed to list mortgage applications: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _get_field_value(extracted_fields: dict, field_name: str, default=None):
    """Extract a field value from extracted_fields dictionary.
    
    Keys are formatted as 'filename:FieldName', so we search for any key ending with the field name.
    Returns the first match found, or default if not found.
    """
    if field_name in extracted_fields:
        field_data = extracted_fields[field_name]
        if isinstance(field_data, dict):
            return field_data.get("value", default)
        return field_data

    for key, field_data in extracted_fields.items():
        if key.endswith(f":{field_name}"):
            if isinstance(field_data, dict):
                return field_data.get("value", default)
            return field_data
    return default


def _parse_currency(value) -> float:
    """Parse a currency string to float, handling commas and dollar signs."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, dict):
        # Handle nested dicts (e.g. Claimant objects) gracefully
        return 0.0
    if isinstance(value, str):
        # Handle localized formatting and common currency tokens
        cleaned = (
            value.replace("$", "")
            .replace("€", "")
            .replace("EUR", "")
            .replace("eur", "")
            .replace("CHF", "")
            .replace("chf", "")
            .replace("\u00a0", "")
            .replace(" ", "")
            .replace("/mois", "")
            .replace("/month", "")
            .replace(",", ".")
            .strip()
        )
        if cleaned.count(".") > 1:
            # Keep last dot as decimal separator and drop the others (e.g. 12.345.67)
            left, _, right = cleaned.rpartition(".")
            cleaned = left.replace(".", "") + "." + right
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return 0.0
    return 0.0


def _parse_percentage(value) -> float:
    """Parse a percentage string to float."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace("%", "").strip()
        try:
            return float(cleaned)
        except (ValueError, TypeError):
            return 0.0
    return 0.0


@app.get("/api/mortgage/applications/{app_id}")
async def get_mortgage_application(app_id: str):
    """Get a specific mortgage application with mortgage-specific data."""
    try:
        settings = load_settings()
        app_md = load_application(settings.app.storage_root, app_id)
        
        if not app_md:
            raise HTTPException(status_code=404, detail="Dossier introuvable")
        
        # Get base application data
        base_data = application_to_dict(app_md)
        
        # Extract data from extracted_fields (format: "filename:FieldName" -> {value, confidence, ...})
        ef = app_md.extracted_fields or {}
        
        # Helper to safely get a value from a field_data entry
        def _safe_field_value(field_data):
            """Extract value from field_data, handling dict, float, str, etc."""
            if isinstance(field_data, dict):
                return field_data.get("value")
            return field_data
        
        llm_outputs = app_md.llm_outputs or {}
        app_summary = llm_outputs.get("application_summary", {}) if isinstance(llm_outputs, dict) else {}
        borrower_profile = app_summary.get("borrower_profile", {}) if isinstance(app_summary, dict) else {}
        profile_parsed = borrower_profile.get("parsed", {}) if isinstance(borrower_profile, dict) else {}

        field_aliases = {
            "BorrowerName": ["emprunteur"],
            "CoBorrowerName": ["co_emprunteur"],
            "RequestedLoanAmount": ["montant_pret", "montant_total"],
            "DownPaymentAmount": ["apport"],
            "CreditScore": ["score_credit"],
            "PropertyAddress": ["adresse_bien"],
            "PurchasePrice": ["prix_bien", "valeur_bien"],
            "AppraisedValue": ["valeur_bien"],
            "OtherDebtsMonthly": ["charges_mensuelles"],
            "PropertyTaxesAnnual": ["taxe_fonciere_annuelle"],
            "PropertyTaxesMonthly": ["taxe_fonciere_mensuelle"],
            "HeatingMonthly": ["chauffage_mensuel"],
            "CondoFeesMonthly": ["charges_copro_mensuelles"],
            "HouseholdIncome": ["revenus"],
        }

        # Helper to get field value
        def get_field(field_name: str, default=None):
            value = _get_field_value(ef, field_name, None)
            if value is not None:
                return value

            for alias in field_aliases.get(field_name, []):
                alias_value = _get_field_value(ef, alias, None)
                if alias_value is not None:
                    return alias_value

            return default
        
        # Build borrower info
        borrower_name = get_field("BorrowerName", profile_parsed.get("summary") or "Unknown")
        co_borrower_name = get_field("CoBorrowerName")
        credit_score = get_field("CreditScore", 0)
        if isinstance(credit_score, str):
            try:
                credit_score = int(credit_score)
            except ValueError:
                credit_score = {"excellent": 780, "good": 720, "bon": 720, "fair": 660}.get(
                    credit_score.strip().lower(),
                    0,
                )
        
        borrower = {
            "name": borrower_name,
            "co_borrower_name": co_borrower_name,
            "credit_score": credit_score,
            "employment_type": get_field("EmploymentStatus", "Permanent"),
            "employer_name": get_field("EmployerName"),
            "occupation": get_field("OccupationTitle"),
        }
        
        # Build income info - sum up all base salaries and annual incomes
        base_salary_b1 = _parse_currency(get_field("BaseSalary"))  # First occurrence
        # Look for B1 and B2 salaries specifically
        b1_salary = 0.0
        b2_salary = 0.0
        for key, field_data in ef.items():
            if "B1" in key and ":BaseSalary" in key:
                b1_salary = _parse_currency(_safe_field_value(field_data))
            elif "B2" in key and ":BaseSalary" in key:
                b2_salary = _parse_currency(_safe_field_value(field_data))
        
        # Use T4 annual income if available for more accuracy
        b1_annual = 0.0
        b2_annual = 0.0
        for key, field_data in ef.items():
            if "T4_B1" in key and ":AnnualIncome" in key:
                b1_annual = _parse_currency(_safe_field_value(field_data))
            elif "T4_B2" in key and ":AnnualIncome" in key:
                b2_annual = _parse_currency(_safe_field_value(field_data))
        
        # Use T4 income if available, otherwise use base salary
        primary_income = b1_annual if b1_annual > 0 else b1_salary
        secondary_income = b2_annual if b2_annual > 0 else b2_salary
        total_annual_income = primary_income + secondary_income
        if total_annual_income <= 0:
            hh_income = profile_parsed.get("household_income") if isinstance(profile_parsed, dict) else None
            if isinstance(hh_income, (int, float)) and hh_income > 0:
                total_annual_income = float(hh_income) * 12
            else:
                monthly_income_raw = _parse_currency(get_field("HouseholdIncome", 0))
                if monthly_income_raw > 0:
                    total_annual_income = monthly_income_raw * 12
        
        income = {
            "primary_borrower_income": primary_income,
            "co_borrower_income": secondary_income,
            "total_annual_income": total_annual_income,
            "monthly_income": total_annual_income / 12 if total_annual_income else 0,
        }
        
        # Build property info
        purchase_price = _parse_currency(get_field("PurchasePrice", profile_parsed.get("property_value", 0)))
        appraised_value = _parse_currency(get_field("AppraisedValue", purchase_price))
        
        property_info = {
            "address": get_field("PropertyAddress", "Adresse non renseignée"),
            "purchase_price": purchase_price,
            "appraised_value": appraised_value,
            "property_type": get_field("PropertyType", "single_family"),
            "occupancy": get_field("PropertyOccupancy", "owner_occupied"),
        }
        
        # Build loan info
        loan_amount = _parse_currency(get_field("RequestedLoanAmount", profile_parsed.get("loan_amount", 0)))
        down_payment = _parse_currency(get_field("DownPaymentAmount", 0))
        if down_payment <= 0 and purchase_price > loan_amount > 0:
            down_payment = purchase_price - loan_amount
        amortization = get_field("AmortizationYears", 25)
        if isinstance(amortization, str):
            try:
                amortization = int(amortization)
            except ValueError:
                amortization = 25
        
        contract_rate = _parse_percentage(get_field("ContractRate", 5.25))
        qualifying_rate = _parse_percentage(get_field("QualifyingRate", max(contract_rate + 2, 5.25)))
        
        loan = {
            "amount": loan_amount,
            "down_payment": down_payment,
            "down_payment_source": get_field("DownPaymentSource", "Savings"),
            "amortization_years": amortization,
            "contract_rate": contract_rate,
            "qualifying_rate": qualifying_rate,
            "term": get_field("RateTerm", "5 years Fixed"),
        }
        
        # Build liabilities info - use extracted values when available, fall back to estimates
        other_debts_monthly = _parse_currency(get_field("OtherDebtsMonthly", 0))
        
        # Property taxes: prefer extracted value, else estimate ~1% annually
        extracted_property_tax = _parse_currency(get_field("PropertyTaxesAnnual", 0))
        if extracted_property_tax > 0:
            property_taxes_monthly = extracted_property_tax / 12
        else:
            extracted_property_tax_monthly = _parse_currency(get_field("PropertyTaxesMonthly", 0))
            if extracted_property_tax_monthly > 0:
                property_taxes_monthly = extracted_property_tax_monthly
            else:
                property_taxes_monthly = purchase_price * 0.01 / 12 if purchase_price else 0
        
        # Heating: prefer extracted value, else standard assumption
        extracted_heating = _parse_currency(get_field("HeatingMonthly", 0))
        heating_monthly = extracted_heating if extracted_heating > 0 else 150
        
        # Condo fees: prefer extracted value, else estimate if property type is condo
        extracted_condo_fees = _parse_currency(get_field("CondoFeesMonthly", 0))
        if extracted_condo_fees > 0:
            condo_fees = extracted_condo_fees
        elif "condo" in (property_info.get("property_type", "") or "").lower():
            condo_fees = 500
        else:
            condo_fees = 0
        
        liabilities = {
            "property_taxes_monthly": property_taxes_monthly,
            "heating_monthly": heating_monthly,
            "condo_fees_monthly": condo_fees,
            "other_debts_monthly": other_debts_monthly,
        }
        
        # Calculate mortgage payment (monthly)
        def calc_monthly_payment(principal: float, annual_rate: float, amort_years: int) -> float:
            if principal <= 0 or annual_rate <= 0:
                return 0
            monthly_rate = annual_rate / 100 / 12
            n_payments = amort_years * 12
            if monthly_rate == 0:
                return principal / n_payments
            return principal * (monthly_rate * (1 + monthly_rate)**n_payments) / ((1 + monthly_rate)**n_payments - 1)
        
        monthly_payment_contract = calc_monthly_payment(loan_amount, contract_rate, amortization)
        monthly_payment_stress = calc_monthly_payment(loan_amount, qualifying_rate, amortization)
        
        # Calculate ratios
        monthly_income = income["monthly_income"]
        
        # GDS = (PITH) / Gross Monthly Income
        pith = monthly_payment_contract + property_taxes_monthly + heating_monthly + (condo_fees * 0.5)  # 50% of condo fees
        gds = (pith / monthly_income * 100) if monthly_income > 0 else 0
        
        # TDS = (PITH + Other Debts) / Gross Monthly Income
        tds = ((pith + other_debts_monthly) / monthly_income * 100) if monthly_income > 0 else 0
        
        # LTV = Loan Amount / Lesser of (Purchase Price, Appraised Value)
        lesser_value = min(purchase_price, appraised_value) if appraised_value > 0 else purchase_price
        ltv = (loan_amount / lesser_value * 100) if lesser_value > 0 else 0
        
        ratios = {
            "gds": round(gds, 2),
            "tds": round(tds, 2),
            "ltv": round(ltv, 2),
            "monthly_payment": round(monthly_payment_contract, 2),
        }
        
        # Stress test ratios (using MQR qualifying rate)
        pith_stress = monthly_payment_stress + property_taxes_monthly + heating_monthly + (condo_fees * 0.5)
        gds_stress = (pith_stress / monthly_income * 100) if monthly_income > 0 else 0
        tds_stress = ((pith_stress + other_debts_monthly) / monthly_income * 100) if monthly_income > 0 else 0
        
        stress_ratios = {
            "gds": round(gds_stress, 2),
            "tds": round(tds_stress, 2),
            "qualifying_rate": qualifying_rate,
            "monthly_payment_stressed": round(monthly_payment_stress, 2),
        }
        
        # Determine decision based on French HCSF / internal bank rules
        # Taux d'effort max: 35%, Taux d'endettement max: 35%, LTV max: 90%
        findings = []
        risk_signals = []
        
        # Helper to get source citation for a field
        def get_field_citation(field_name: str) -> dict:
            for key, field_data in ef.items():
                if key.endswith(f":{field_name}") and isinstance(field_data, dict):
                    return {
                        "source_file": field_data.get("source_file"),
                        "confidence": field_data.get("confidence"),
                    }
            return {}
        
        if gds_stress > 35:
            findings.append({
                "type": "warning",
                "severity": "fail",
                "rule_id": "HCSF-EFFORT-001",
                "message": f"Taux d'effort sous sensibilit\u00e9 ({gds_stress:.1f}%) d\u00e9passe la limite HCSF de 35%",
                "category": "Taux d'effort",
                "sources": ["Avis d'imposition / Bulletin de salaire", "Demande de pr\u00eat"],
                "evidence": {"calculated_value": round(gds_stress, 2), "limit": 35},
            })
            risk_signals.append({"level": "high", "category": "income", "message": "Taux d'effort au-dessus de la limite HCSF"})
        elif gds_stress > 32:
            findings.append({
                "type": "info",
                "severity": "warning",
                "rule_id": "HCSF-EFFORT-001",
                "message": f"Taux d'effort sous sensibilit\u00e9 ({gds_stress:.1f}%) proche de la limite HCSF de 35%",
                "category": "Taux d'effort",
                "evidence": {"calculated_value": round(gds_stress, 2), "limit": 35},
            })
        else:
            findings.append({
                "type": "success",
                "severity": "pass",
                "rule_id": "HCSF-EFFORT-001",
                "message": f"Taux d'effort sous sensibilit\u00e9 ({gds_stress:.1f}%) dans la limite HCSF de 35%",
                "category": "Taux d'effort",
                "evidence": {"calculated_value": round(gds_stress, 2), "limit": 35},
            })
            
        if tds_stress > 35:
            findings.append({
                "type": "warning",
                "severity": "fail",
                "rule_id": "HCSF-ENDETT-001",
                "message": f"Taux d'endettement sous sensibilit\u00e9 ({tds_stress:.1f}%) d\u00e9passe la limite HCSF de 35%",
                "category": "Taux d'endettement",
                "sources": ["Relev\u00e9s bancaires", "Demande de pr\u00eat"],
                "evidence": {"calculated_value": round(tds_stress, 2), "limit": 35},
            })
            risk_signals.append({"level": "high", "category": "debt", "message": "Taux d'endettement au-dessus de la limite HCSF"})
        elif tds_stress > 33:
            findings.append({
                "type": "info",
                "severity": "warning",
                "rule_id": "HCSF-ENDETT-001",
                "message": f"Taux d'endettement sous sensibilit\u00e9 ({tds_stress:.1f}%) proche de la limite HCSF de 35%",
                "category": "Taux d'endettement",
                "evidence": {"calculated_value": round(tds_stress, 2), "limit": 35},
            })
        else:
            findings.append({
                "type": "success",
                "severity": "pass",
                "rule_id": "HCSF-ENDETT-001",
                "message": f"Taux d'endettement sous sensibilit\u00e9 ({tds_stress:.1f}%) dans la limite HCSF de 35%",
                "category": "Taux d'endettement",
                "evidence": {"calculated_value": round(tds_stress, 2), "limit": 35},
            })
            
        if ltv > 90:
            findings.append({
                "type": "warning",
                "severity": "warning",
                "rule_id": "BANK-LTV-001",
                "message": f"LTV ({ltv:.1f}%) d\u00e9passe 90% \u2014 assurance emprunteur renforc\u00e9e n\u00e9cessaire",
                "category": "LTV",
                "sources": ["Compromis de vente", "Demande de pr\u00eat"],
                "evidence": {"calculated_value": round(ltv, 2), "limit": 90},
            })
            risk_signals.append({"level": "medium", "category": "ltv", "message": "LTV \u00e9lev\u00e9 \u2014 garantie renforc\u00e9e"})
        else:
            findings.append({
                "type": "success",
                "severity": "pass",
                "rule_id": "BANK-LTV-001",
                "message": f"LTV ({ltv:.1f}%) dans la limite interne de 90%",
                "category": "LTV",
                "evidence": {"calculated_value": round(ltv, 2), "limit": 90},
            })
        
        # Score crédit (FICP / Banque de France equivalent)
        credit_citation = get_field_citation("CreditScore")
        if credit_score < 620:
            findings.append({
                "type": "warning",
                "severity": "warning",
                "rule_id": "BANK-CREDIT-001",
                "message": f"Score cr\u00e9dit ({credit_score}) sous le seuil interne (620)",
                "category": "Cr\u00e9dit",
                "source_file": credit_citation.get("source_file"),
                "confidence": credit_citation.get("confidence"),
                "evidence": {"calculated_value": credit_score, "limit": 620},
            })
            risk_signals.append({"level": "medium", "category": "credit", "message": "Score cr\u00e9dit \u00e0 examiner (FICP / incidents)"})
        elif credit_score >= 740:
            findings.append({
                "type": "success",
                "severity": "pass",
                "rule_id": "BANK-CREDIT-001",
                "message": f"Excellent profil de cr\u00e9dit ({credit_score})",
                "category": "Cr\u00e9dit",
                "source_file": credit_citation.get("source_file"),
                "confidence": credit_citation.get("confidence"),
                "evidence": {"calculated_value": credit_score, "limit": 620},
            })
        else:
            findings.append({
                "type": "success",
                "severity": "pass",
                "rule_id": "BANK-CREDIT-001",
                "message": f"Profil de cr\u00e9dit ({credit_score}) satisfaisant",
                "category": "Cr\u00e9dit",
                "source_file": credit_citation.get("source_file"),
                "confidence": credit_citation.get("confidence"),
                "evidence": {"calculated_value": credit_score, "limit": 620},
            })
            
        # Determine overall decision (French thresholds)
        if gds_stress > 35 or tds_stress > 35:
            decision = "DECLINE"
        elif gds_stress > 32 or tds_stress > 33 or ltv > 90 or credit_score < 620:
            decision = "REFER"
        else:
            decision = "APPROVE"
        
        # Get LLM analysis data
        llm_outputs = app_md.llm_outputs or {}
        app_summary = llm_outputs.get("application_summary", {})
        
        # Extract LLM-calculated ratios if available
        ratio_calc = app_summary.get("ratio_calculation", {})
        if ratio_calc:
            parsed = ratio_calc.get("parsed", {})
            if parsed and not parsed.get("_error"):
                calcs = parsed.get("calculations", {})
                if calcs and isinstance(calcs, dict):
                    # LLM may return ratios as {"GDS": {"value": 28.5}} or as {"GDS": 28.5}
                    def _extract_calc_value(calc_entry):
                        if isinstance(calc_entry, dict):
                            return calc_entry.get("value")
                        if isinstance(calc_entry, (int, float)):
                            return calc_entry
                        return None
                    
                    gds_val = _extract_calc_value(calcs.get("GDS"))
                    tds_val = _extract_calc_value(calcs.get("TDS"))
                    ltv_val = _extract_calc_value(calcs.get("LTV"))
                    ltv_pct = _extract_calc_value(calcs.get("LTV_percent"))
                    
                    if gds_val is not None:
                        ratios["gds"] = gds_val
                    if tds_val is not None:
                        ratios["tds"] = tds_val
                    if ltv_pct is not None:
                        ratios["ltv"] = ltv_pct
                    elif ltv_val is not None:
                        # Convert ratio to percentage if needed
                        ratios["ltv"] = ltv_val * 100 if ltv_val < 1 else ltv_val
                    
                    # Update stress ratios from LLM
                    stress_calc = calcs.get("stress_test")
                    if isinstance(stress_calc, dict):
                        stress_gds = _extract_calc_value(stress_calc.get("GDS"))
                        stress_tds = _extract_calc_value(stress_calc.get("TDS"))
                        if stress_gds is not None:
                            stress_ratios["gds"] = stress_gds
                        if stress_tds is not None:
                            stress_ratios["tds"] = stress_tds
        
        # Get risk assessment from LLM
        risk_data = app_summary.get("risk_assessment", {})
        if isinstance(risk_data, dict):
            risk_parsed = risk_data.get("parsed", {})
        else:
            risk_parsed = {}
        if risk_parsed and isinstance(risk_parsed, dict) and not risk_parsed.get("_error"):
            ra = risk_parsed.get("risk_assessment", {})
            if isinstance(ra, dict):
                overall_risk = ra.get("overall_risk_level", "Medium")
                aggregate = ra.get("aggregate_risk_signals", {})
                if isinstance(aggregate, dict):
                    for category, level in aggregate.items():
                        if isinstance(level, str) and "low" not in level.lower():
                            risk_signals.append({
                                "level": "high" if "high" in level.lower() else "medium",
                                "category": category,
                                "message": f"{category.replace('_', ' ').title()}: {level}"
                            })
        
        # Get recommendation from LLM
        recommendation = app_summary.get("recommendation", {})
        if isinstance(recommendation, dict):
            rec_parsed = recommendation.get("parsed", {})
        else:
            rec_parsed = {}
        if rec_parsed and isinstance(rec_parsed, dict) and not rec_parsed.get("_error"):
            llm_decision = rec_parsed.get("DECISION")
            if llm_decision and isinstance(llm_decision, str):
                decision = llm_decision.upper().strip()
                # Normalize common decision variations
                if "CONDITIONAL" in decision:
                    decision = "REFER"
                elif decision not in ("APPROVE", "DECLINE", "REFER"):
                    decision = "REFER"
            
            rationale = rec_parsed.get("RATIONALE", {})
            conditions = rec_parsed.get("CONDITIONS", [])
            
            # Add conditions as findings
            if isinstance(conditions, list):
                for condition in conditions:
                    if isinstance(condition, str):
                        findings.append({
                            "type": "condition",
                            "severity": "warning",
                            "category": "Conditions",
                            "message": condition,
                        })
        
        # Build AI narrative from recommendation rationale
        narrative_parts = []
        if rec_parsed and isinstance(rec_parsed, dict) and not rec_parsed.get("_error"):
            rationale = rec_parsed.get("RATIONALE", {})
            if isinstance(rationale, dict):
                details = rationale.get("Details", [])
                if isinstance(details, list) and details:
                    narrative_parts.append("**Observations clés :**")
                    for detail in details[:5]:  # Limit to 5
                        if isinstance(detail, str):
                            narrative_parts.append(f"• {detail}")
                
                refs = rationale.get("OSFI_B20_References", []) or rationale.get("HCSF_References", [])
                if isinstance(refs, list) and refs:
                    narrative_parts.append("")
                    narrative_parts.append(f"**Conformité HCSF :** {len(refs)} contrôles de politique réussis")
        
        narrative = "\n".join(narrative_parts) if narrative_parts else None
        
        # Count policy checks from HCSF references
        policy_checks_count = 0
        if rec_parsed and isinstance(rec_parsed, dict) and not rec_parsed.get("_error"):
            rationale_obj = rec_parsed.get("RATIONALE", {})
            if isinstance(rationale_obj, dict):
                refs = rationale_obj.get("OSFI_B20_References", []) or rationale_obj.get("HCSF_References", [])
                if isinstance(refs, list):
                    policy_checks_count = len(refs)
        
        # Merge mortgage-specific data with base data
        return {
            **base_data,
            "borrower": borrower,
            "income": income,
            "property": property_info,
            "loan": loan,
            "liabilities": liabilities,
            "ratios": ratios,
            "stress_ratios": stress_ratios,
            "decision": decision,
            "findings": findings,
            "risk_signals": risk_signals,
            "narrative": narrative,
            "policy_checks_count": policy_checks_count,
            # Include field-level citations for confidence indicators
            "field_citations": {
                field_data.get("field_name", key.split(":")[-1]): {
                    "field_name": field_data.get("field_name", key.split(":")[-1]),
                    "value": field_data.get("value"),
                    "confidence": field_data.get("confidence"),
                    "source_file": field_data.get("source_file"),
                    "page_number": field_data.get("page_number"),
                    "source_text": field_data.get("source_text"),
                    "bounding_box": field_data.get("bounding_box"),
                }
                for key, field_data in ef.items()
                if isinstance(field_data, dict) and "confidence" in field_data
            },
            "documents": [
                {
                    "id": f.filename,
                    "type": "application",
                    "filename": f.filename,
                    "uploaded_at": app_md.created_at,
                    "status": "processed" if ef else "pending",
                    "url": f"/api/applications/{app_id}/files/{f.filename}",
                    "fields_extracted": len([k for k in ef.keys() if f.filename.split('.')[0] in k]) if ef else 0,
                }
                for f in app_md.files
            ] if app_md.files else [],
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get mortgage application: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mortgage/applications")
async def create_mortgage_application(request: MortgageApplicationCreate):
    """Create a new mortgage application."""
    try:
        settings = load_settings()
        app_id = str(uuid.uuid4())[:8]
        
        # Create application metadata
        app_md = new_metadata(
            settings.app.storage_root,
            app_id,
            files=[],
            persona="mortgage_underwriting",
        )
        
        logger.info("Created mortgage application %s", app_id)
        return application_to_dict(app_md)
        
    except Exception as e:
        logger.error("Failed to create mortgage application: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
async def chat_endpoint(request: MortgageChatRequest):
    """
    General chat endpoint supporting multiple personas.
    
    For mortgage_underwriting persona, uses HCSF / internal bank policies as context.
    """
    try:
        from app.openai_client import chat_completion
        
        # Get persona-specific context
        persona = request.persona or "mortgage_underwriting"
        policies_context = ""
        
        if persona == "mortgage_underwriting":
            # Load mortgage policies
            try:
                import json
                from pathlib import Path
                policy_path = Path("prompts/mortgage-underwriting-policies.json")
                if policy_path.exists():
                    with open(policy_path) as f:
                        policies = json.load(f)
                    # Format for context
                    policies_context = json.dumps(policies.get("policies", [])[:5], indent=2)
            except Exception as e:
                logger.warning("Failed to load mortgage policies: %s", e)
        
        # Build system prompt
        config = PERSONA_CHAT_CONFIG.get(persona, PERSONA_CHAT_CONFIG["underwriting"])
        language = (request.language or "en").lower()
        language_directive = (
            "Respond in English." if language == "en" else "Répondez en français."
        )
        system_prompt = f"""You are an {config['role']}.

You have access to the following {config['context_type']}:

{policies_context[:8000] if policies_context else 'No policies loaded.'}

When answering questions:
1. Reference specific policies when applicable
2. Be precise about regulatory requirements
3. Explain ratios and calculations clearly
4. Cite sources for your answers

{language_directive}"""

        # Call LLM
        settings = load_settings()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.query},
        ]
        
        response = await asyncio.to_thread(
            chat_completion,
            settings.openai,
            messages,
        )
        
        return {
            "response": response,
            "persona": persona,
            "query": request.query,
        }
        
    except Exception as e:
        logger.error("Chat failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Property Deep Dive endpoints
# ---------------------------------------------------------------------------

@app.get("/api/mortgage/applications/{app_id}/property-deep-dive")
async def get_property_deep_dive(app_id: str):
    """Run property deep dive analysis for a mortgage application."""
    try:
        from app.mortgage.property_deep_dive import PropertyDeepDiveEngine

        settings = load_settings()
        app_md = load_application(settings.app.storage_root, app_id)
        if not app_md:
            raise HTTPException(status_code=404, detail="Dossier introuvable")

        ef = app_md.extracted_fields or {}

        address = _get_field_value(ef, "PropertyAddress", "")
        purchase_price = _parse_currency(_get_field_value(ef, "PurchasePrice", 0))
        appraised_value = _parse_currency(_get_field_value(ef, "AppraisedValue", 0))
        property_type = _get_field_value(ef, "PropertyType", "single_family_detached")

        if not address:
            raise HTTPException(
                status_code=400,
                detail="Property address not found in application data.",
            )

        engine = PropertyDeepDiveEngine(
            property_address=address,
            purchase_price=purchase_price,
            property_type=property_type or "single_family_detached",
            appraised_value=appraised_value,
        )

        result = await asyncio.to_thread(engine.analyze)
        return result.to_dict()

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Property deep dive failed for %s: %s", app_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/mortgage/applications/{app_id}/property-deep-dive")
async def run_property_deep_dive(app_id: str, force: bool = False):
    """Run (or force re-run) property deep dive analysis for a mortgage application."""
    try:
        from app.mortgage.property_deep_dive import PropertyDeepDiveEngine

        settings = load_settings()
        app_md = load_application(settings.app.storage_root, app_id)
        if not app_md:
            raise HTTPException(status_code=404, detail="Dossier introuvable")

        ef = app_md.extracted_fields or {}

        address = _get_field_value(ef, "PropertyAddress", "")
        purchase_price = _parse_currency(_get_field_value(ef, "PurchasePrice", 0))
        appraised_value = _parse_currency(_get_field_value(ef, "AppraisedValue", 0))
        property_type = _get_field_value(ef, "PropertyType", "single_family_detached")

        if not address:
            raise HTTPException(
                status_code=400,
                detail="Property address not found in application data.",
            )

        engine = PropertyDeepDiveEngine(
            property_address=address,
            purchase_price=purchase_price,
            property_type=property_type or "single_family_detached",
            appraised_value=appraised_value,
        )

        result = await asyncio.to_thread(engine.analyze)
        return {"force": force, **result.to_dict()}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Property deep dive (POST) failed for %s: %s", app_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Customer 360 — Unified Data Layer
# =============================================================================

from app.customer360 import (
    list_customers as _list_customers,
    get_customer_360 as _get_customer_360,
    load_customer_profile as _load_customer_profile,
)


@app.get("/api/customers")
async def list_customers():
    """List all customer profiles."""
    settings = load_settings()
    profiles = _list_customers(settings.app.storage_root)
    return [
        {
            "id": p.id,
            "name": p.name,
            "date_of_birth": p.date_of_birth,
            "email": p.email,
            "phone": p.phone,
            "address": p.address,
            "customer_since": p.customer_since,
            "risk_tier": p.risk_tier,
            "tags": p.tags,
            "notes": p.notes,
        }
        for p in profiles
    ]


@app.get("/api/customers/{customer_id}")
async def get_customer_360_view(customer_id: str):
    """Get full Customer 360 view with profile, journey, and risk correlations."""
    settings = load_settings()
    view = _get_customer_360(settings.app.storage_root, customer_id)
    if not view:
        raise HTTPException(status_code=404, detail="Client introuvable")

    # Enrich with live Souscr'IA acquisition context when this customer is mapped
    # to a Souscr'IA front-office client (profile.souscria_ref). Read-only and
    # best-effort: never blocks the event loop or breaks the GET.
    try:
        from app.customer360 import apply_souscria_acquisition
        from app.souscria_mcp_client import fetch_acquisition_context

        raw = await asyncio.to_thread(fetch_acquisition_context, view.profile.souscria_ref)
        apply_souscria_acquisition(view, raw)
    except Exception as sc_err:
        logger.warning("Souscr'IA acquisition enrichment failed for %s: %s", customer_id, sc_err)

    from dataclasses import asdict
    return asdict(view)


@app.post("/api/customers")
async def create_customer(body: dict):
    """Create a new Customer 360 profile.

    Accepts: {name, date_of_birth?, email?, phone?, address?, customer_since?, risk_tier?, tags?, notes?}
    Returns the created profile with an auto-generated brand-prefixed ID (e.g. PRV-xxx).
    """
    name = (body.get("name") or "").strip()
    if not name or len(name) < 2:
        raise HTTPException(status_code=400, detail="Le nom du client est obligatoire.")

    settings = load_settings()
    from app.customer360 import list_customers, save_customer_profile, CustomerProfile

    # Generate next brand-prefixed customer ID
    id_prefix = f"{get_current_brand_profile().brand_key[:3].upper()}-"
    existing = list_customers(settings.app.storage_root)
    existing_ids = [int(c.id.split("-")[1]) for c in existing if c.id.startswith(id_prefix) and c.id.split("-")[1].isdigit()]
    next_id = max(existing_ids, default=0) + 1
    customer_id = f"{id_prefix}{next_id:03d}"

    profile = CustomerProfile(
        id=customer_id,
        name=name,
        date_of_birth=body.get("date_of_birth", ""),
        email=body.get("email", ""),
        phone=body.get("phone", ""),
        address=body.get("address", ""),
        customer_since=body.get("customer_since", datetime.now(UTC).strftime("%Y-%m-%d")),
        risk_tier=body.get("risk_tier", "medium"),
        tags=body.get("tags", []),
        notes=body.get("notes", ""),
    )
    save_customer_profile(settings.app.storage_root, profile)
    logger.info("Created customer %s: %s", customer_id, name)

    from dataclasses import asdict
    return asdict(profile)


@app.post("/api/applications/{app_id}/affiliate")
async def affiliate_application(app_id: str, body: dict):
    """Affiliate an application to a Customer 360 profile.

    Accepts: {customer_id: "PRV-xxx"}
    Sets external_reference on the application and adds a journey event.
    """
    customer_id = (body.get("customer_id") or "").strip()
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id est obligatoire.")

    settings = load_settings()
    app_md = load_application(settings.app.storage_root, app_id)
    if not app_md:
        raise HTTPException(status_code=404, detail="Application non trouvée.")

    from app.customer360 import load_customer_profile
    profile = load_customer_profile(settings.app.storage_root, customer_id)
    if not profile:
        raise HTTPException(status_code=404, detail=f"Client {customer_id} non trouvé.")

    # Set external_reference
    app_md.external_reference = customer_id
    save_application_metadata(settings.app.storage_root, app_md)

    # Add journey event
    _try_auto_affiliate_customer(app_md, settings.app.storage_root)

    logger.info("Affiliated app %s to customer %s", app_id, customer_id)
    return {"message": f"Dossier affilié au client {profile.name}", "customer_id": customer_id, "customer_name": profile.name}


@app.post("/api/customers/seed")
async def seed_customer_360_data():
    """Seed sample customer 360 data (development/demo only)."""
    settings = load_settings()
    try:
        from app.seed_data_customers import create_brand_customers
        
        # Link existing apps to customer IDs via external_reference
        _link_apps_to_customers(settings.app.storage_root)
        
        # Seed customer profiles and journeys (discovers real app IDs)
        customer_count = create_brand_customers(settings.app.storage_root)
        
        # Try to seed rich application data (only available in dev, not in Docker)
        app_count = 0
        try:
            from scripts.seed_customer360 import seed_applications
            app_count = seed_applications(settings.app.storage_root)
        except ImportError:
            logger.info("scripts.seed_customer360 not available (Docker) — skipping application seeding")
        
        return {
            "status": "ok",
            "message": f"Seeded {customer_count} customer profiles and {app_count} applications"
        }
    except Exception as e:
        logger.error("Failed to seed customer 360 data: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


def _remediate_external_references(storage_root: str):
    """Fix wrongly-affiliated apps from the old loose name matcher.

    Scans all apps with an external_reference.  If the app is NOT in the
    seed dossier map, re-validates by running the strict name matcher.
    If no confident match → clears external_reference to None.
    Idempotent — safe to run on every startup.
    """
    from app.storage import list_applications as _list_apps
    from app.seed_data_customers import _SEEDED_DOSSIER_MAP

    # Build set of seeded app_ids for fast lookup
    seeded_app_ids: set[str] = set()
    for dossiers in _SEEDED_DOSSIER_MAP.values():
        for d in dossiers:
            seeded_app_ids.add(d["app_id"])

    fixed = 0
    try:
        all_apps = _list_apps(storage_root)
        for app_summary in all_apps:
            app_id = app_summary.get("id", "")
            if not app_id or app_id in seeded_app_ids:
                continue  # Seed dossiers keep their mapping
            app_md = load_application(storage_root, app_id)
            if not app_md or not app_md.external_reference:
                continue  # Not affiliated, nothing to fix

            # Re-validate: temporarily clear and run strict matcher
            old_ref = app_md.external_reference
            app_md.external_reference = None
            _try_auto_affiliate_customer(app_md, storage_root)
            if app_md.external_reference is None:
                # Strict matcher found no match → clear the wrong affiliation
                save_application_metadata(storage_root, app_md)
                logger.info("Remediated app %s: cleared wrong affiliation %s", app_id, old_ref)
                fixed += 1
            elif app_md.external_reference != old_ref:
                # Strict matcher found a DIFFERENT customer → already saved by _try_auto_affiliate
                logger.info("Remediated app %s: %s → %s", app_id, old_ref, app_md.external_reference)
                fixed += 1
            else:
                # Same match — affiliation was correct, restore silently
                pass
    except Exception as e:
        logger.warning("Remediation of external_references failed (non-fatal): %s", e)
    if fixed:
        logger.info("Remediated %d wrongly-affiliated applications", fixed)


def _link_apps_to_customers(storage_root: str):
    """Set external_reference on apps using the seed dossier map.

    Uses ``_SEEDED_DOSSIER_MAP`` (app_id → customer_id) to assign the correct
    customer to each seeded dossier.  For apps not in the seed map, falls back
    to name-matching via ``_try_auto_affiliate_customer``.
    """
    from app.storage import list_applications as _list_apps
    from app.seed_data_customers import _SEEDED_DOSSIER_MAP

    # Build inverted map: app_id → customer_id
    app_to_customer: dict[str, str] = {}
    for customer_id, dossiers in _SEEDED_DOSSIER_MAP.items():
        for d in dossiers:
            app_to_customer[d["app_id"]] = customer_id

    try:
        all_apps = _list_apps(storage_root)
        for app_summary in all_apps:
            app_id = app_summary.get("id", "")
            if not app_id:
                continue
            app_md = load_application(storage_root, app_id)
            if not app_md or app_md.external_reference:
                continue  # Already affiliated

            # Priority 1: seed dossier map (exact app_id match)
            if app_id in app_to_customer:
                app_md.external_reference = app_to_customer[app_id]
                save_application_metadata(storage_root, app_md)
                logger.info("Linked app %s to customer %s (seed map)", app_id, app_to_customer[app_id])
            else:
                # Priority 2: name-matching against Customer 360 profiles
                _try_auto_affiliate_customer(app_md, storage_root)
    except Exception as e:
        logger.warning("Failed to link apps to customers: %s", e)


# Entry point for running with uvicorn directly
def main():
    """Entry point for the API server."""
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
