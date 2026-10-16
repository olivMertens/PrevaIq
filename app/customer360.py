"""
Customer 360 — Unified Data Layer.

Provides a cross-persona customer view by aggregating applications
linked via external_reference. Stores customer profiles as JSON in
data/brands/{brand_key}/customers/{customer_id}/profile.json.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.brands import current_brand_key, current_brand_name
from app.storage import load_application

logger = logging.getLogger(__name__)


# =============================================================================
# Data Models
# =============================================================================

@dataclass
class CustomerProfile:
    """Core customer profile linking applications across personas."""
    id: str
    name: str
    date_of_birth: str
    email: str
    phone: str
    address: str
    customer_since: str
    risk_tier: str  # "low", "medium", "high"
    brand: str = ""
    tags: List[str] = field(default_factory=list)
    notes: str = ""
    # Souscr'IA front-office client_id (e.g. "SOC-001"), internal seed data only —
    # never a free API input. When set, Customer 360 enriches the view with the
    # live acquisition context read from Souscr'IA's read-only MCP server.
    souscria_ref: str = ""


@dataclass
class CustomerJourneyEvent:
    """A single event in the customer journey timeline."""
    date: str
    persona: str
    application_id: str
    event_type: str  # application_submitted, claim_filed, underwriting_complete, etc.
    title: str
    summary: str
    status: str
    risk_level: Optional[str] = None
    key_metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PersonaSummary:
    """Aggregated summary for one persona's applications for a customer."""
    persona: str
    persona_label: str
    application_count: int
    latest_status: str
    risk_level: Optional[str] = None
    key_metrics: Dict[str, Any] = field(default_factory=dict)
    applications: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class RiskCorrelation:
    """Cross-persona risk correlation insight."""
    severity: str  # "info", "warning", "critical"
    title: str
    description: str
    personas_involved: List[str] = field(default_factory=list)


@dataclass
class SouscriaAcquisition:
    """Live front-office acquisition context read from Souscr'IA (read-only).

    Surfaced as a "Contexte acquisition Souscr'IA" card on Customer 360: the
    active contracts, the assigned advisor and the next-best-actions captured
    while the lead was acquired in the front-office.
    """
    available: bool
    client_id: str
    contracts: List[Dict[str, Any]] = field(default_factory=list)
    advisor: Optional[Dict[str, Any]] = None
    next_best_actions: List[Dict[str, Any]] = field(default_factory=list)
    source: str = "Souscr'IA"


@dataclass
class Customer360View:
    """Complete customer 360 view with profile, journey, and insights."""
    profile: CustomerProfile
    journey_events: List[CustomerJourneyEvent] = field(default_factory=list)
    persona_summaries: List[PersonaSummary] = field(default_factory=list)
    risk_correlations: List[RiskCorrelation] = field(default_factory=list)
    total_products: int = 0
    active_claims: int = 0
    overall_risk: str = "low"
    souscria_acquisition: Optional[SouscriaAcquisition] = None


# =============================================================================
# Persona display labels
# =============================================================================

PERSONA_LABELS = {
    "underwriting": "Souscription Vie & Santé",
    "life_health_claims": "Sinistres Santé",
    "automotive_claims": "Sinistres Auto",
    "habitation_claims": "Sinistres Habitation",
    "property_casualty_claims": "Sinistres Habitation",
    "mortgage_underwriting": "Souscription Hypothécaire",
    "mortgage": "Souscription Hypothécaire",
}


# =============================================================================
# Storage Functions (supports local filesystem and Azure Blob)
# =============================================================================

def _customers_dir(storage_root: str) -> Path:
    return Path(storage_root) / "brands" / current_brand_key() / "customers"


def _customer_blob_prefix(customer_id: str) -> str:
    return f"brands/{current_brand_key()}/customers/{customer_id}/"


def _get_blob_container():
    """Get Azure Blob container client if provider is Azure, else None."""
    try:
        from app.storage_providers import get_storage_provider
        from app.storage_providers.azure_blob import AzureBlobStorageProvider
        provider = get_storage_provider()
        if isinstance(provider, AzureBlobStorageProvider):
            return provider._container_client
    except Exception:
        pass
    return None


def _load_blob_json(blob_path: str) -> Optional[Any]:
    """Load JSON from Azure Blob. Returns None if not found."""
    container = _get_blob_container()
    if not container:
        return None
    try:
        data = container.download_blob(blob_path).readall()
        return json.loads(data)
    except Exception as e:
        logger.debug("Blob read failed for %s: %s", blob_path, e)
        return None


def _save_blob_json(blob_path: str, data: Any) -> bool:
    """Save JSON to Azure Blob. Returns True on success."""
    container = _get_blob_container()
    if not container:
        return False
    try:
        content = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        blob_client = container.get_blob_client(blob_path)
        blob_client.upload_blob(content, overwrite=True)
        return True
    except Exception as e:
        logger.warning("Blob write failed for %s: %s", blob_path, e)
        return False


def _list_blob_prefixes(prefix: str) -> List[str]:
    """List unique sub-prefixes under a blob prefix (simulates directory listing)."""
    container = _get_blob_container()
    if not container:
        return []
    try:
        names = set()
        for blob in container.list_blobs(name_starts_with=prefix):
            rest = blob.name[len(prefix):]
            parts = rest.split("/")
            if parts[0]:
                names.add(parts[0])
        return sorted(names)
    except Exception as e:
        logger.debug("Blob list failed for prefix %s: %s", prefix, e)
        return []


def save_customer_profile(storage_root: str, profile: CustomerProfile) -> None:
    """Save a customer profile (blob + local)."""
    data = asdict(profile)
    data["brand"] = data.get("brand") or current_brand_name()
    # Persist to Azure Blob (survives container redeployments)
    _save_blob_json(f"{_customer_blob_prefix(profile.id)}profile.json", data)
    # Also save locally for fast reads
    customer_dir = _customers_dir(storage_root) / profile.id
    customer_dir.mkdir(parents=True, exist_ok=True)
    profile_path = customer_dir / "profile.json"
    profile_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved customer profile: %s", profile.id)


def save_customer_journey(
    storage_root: str,
    customer_id: str,
    events: List[CustomerJourneyEvent],
) -> None:
    """Save pre-computed journey events for a customer (blob + local)."""
    data = [asdict(e) for e in events]
    _save_blob_json(f"{_customer_blob_prefix(customer_id)}journey.json", data)
    customer_dir = _customers_dir(storage_root) / customer_id
    customer_dir.mkdir(parents=True, exist_ok=True)
    journey_path = customer_dir / "journey.json"
    journey_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    logger.info("Saved %d journey events for customer %s", len(events), customer_id)


def save_customer_risk_correlations(
    storage_root: str,
    customer_id: str,
    correlations: List[RiskCorrelation],
) -> None:
    """Save risk correlations for a customer (blob + local)."""
    data = [asdict(c) for c in correlations]
    _save_blob_json(f"{_customer_blob_prefix(customer_id)}risk_correlations.json", data)
    customer_dir = _customers_dir(storage_root) / customer_id
    customer_dir.mkdir(parents=True, exist_ok=True)
    path = customer_dir / "risk_correlations.json"
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def load_customer_profile(storage_root: str, customer_id: str) -> Optional[CustomerProfile]:
    """Load a customer profile (blob-first, local fallback)."""
    # Try Azure Blob
    blob_data = _load_blob_json(f"{_customer_blob_prefix(customer_id)}profile.json")
    if blob_data:
        blob_data.setdefault("brand", current_brand_name())
        profile = CustomerProfile(**blob_data)
        if profile.brand != current_brand_name():
            logger.warning(
                "Rejected customer %s for brand %s while running brand %s",
                customer_id,
                profile.brand,
                current_brand_name(),
            )
            return None
        return profile
    # Local fallback
    profile_path = _customers_dir(storage_root) / customer_id / "profile.json"
    if not profile_path.exists():
        return None
    data = json.loads(profile_path.read_text(encoding="utf-8"))
    data.setdefault("brand", current_brand_name())
    profile = CustomerProfile(**data)
    if profile.brand != current_brand_name():
        logger.warning(
            "Rejected customer %s for brand %s while running brand %s",
            customer_id,
            profile.brand,
            current_brand_name(),
        )
        return None
    return profile


def load_customer_journey(
    storage_root: str, customer_id: str
) -> List[CustomerJourneyEvent]:
    """Load pre-computed journey events (blob-first, local fallback)."""
    blob_data = _load_blob_json(f"{_customer_blob_prefix(customer_id)}journey.json")
    if blob_data and isinstance(blob_data, list):
        return [CustomerJourneyEvent(**e) for e in blob_data]
    path = _customers_dir(storage_root) / customer_id / "journey.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [CustomerJourneyEvent(**e) for e in data]


def load_customer_risk_correlations(
    storage_root: str, customer_id: str
) -> List[RiskCorrelation]:
    """Load risk correlations (blob-first, local fallback)."""
    blob_data = _load_blob_json(f"{_customer_blob_prefix(customer_id)}risk_correlations.json")
    if blob_data and isinstance(blob_data, list):
        return [RiskCorrelation(**c) for c in blob_data]
    path = _customers_dir(storage_root) / customer_id / "risk_correlations.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [RiskCorrelation(**c) for c in data]


def list_customers(storage_root: str) -> List[CustomerProfile]:
    """List all customer profiles (blob-first, local fallback)."""
    # Try Azure Blob
    customer_ids = _list_blob_prefixes(f"brands/{current_brand_key()}/customers/")
    if customer_ids:
        profiles: List[CustomerProfile] = []
        for cid in customer_ids:
            profile = load_customer_profile(storage_root, cid)
            if profile:
                profiles.append(profile)
        return profiles
    # Local fallback
    customers_dir = _customers_dir(storage_root)
    if not customers_dir.exists():
        return []
    profiles = []
    for customer_dir in sorted(customers_dir.iterdir()):
        if not customer_dir.is_dir():
            continue
        profile = load_customer_profile(storage_root, customer_dir.name)
        if profile:
            profiles.append(profile)
    return profiles


def get_customer_360(storage_root: str, customer_id: str) -> Optional[Customer360View]:
    """Build the full Customer 360 view.
    
    Filters out journey events that reference applications that no longer exist
    (e.g. deleted dossiers) to keep the view accurate.
    """
    profile = load_customer_profile(storage_root, customer_id)
    if not profile:
        return None

    journey_events = load_customer_journey(storage_root, customer_id)
    risk_correlations = load_customer_risk_correlations(storage_root, customer_id)

    # Filter out events referencing deleted applications
    valid_events: List[CustomerJourneyEvent] = []
    for event in journey_events:
        if event.application_id:
            app = load_application(storage_root, event.application_id)
            if app is None:
                logger.debug("Filtering out journey event for deleted app %s", event.application_id)
                continue
        valid_events.append(event)

    # Build persona summaries from valid journey events only
    persona_apps: Dict[str, List[CustomerJourneyEvent]] = {}
    for event in valid_events:
        persona_apps.setdefault(event.persona, []).append(event)

    persona_summaries: List[PersonaSummary] = []
    active_claims = 0
    for persona, events in persona_apps.items():
        latest = max(events, key=lambda e: e.date)
        summary = PersonaSummary(
            persona=persona,
            persona_label=PERSONA_LABELS.get(persona, persona),
            application_count=len(set(e.application_id for e in events)),
            latest_status=latest.status,
            risk_level=latest.risk_level,
            key_metrics=latest.key_metrics,
            applications=[asdict(e) for e in events],
        )
        persona_summaries.append(summary)
        if persona in ("life_health_claims", "automotive_claims") and latest.status not in (
            "closed",
            "denied",
        ):
            active_claims += 1

    return Customer360View(
        profile=profile,
        journey_events=sorted(valid_events, key=lambda e: e.date, reverse=True),
        persona_summaries=persona_summaries,
        risk_correlations=risk_correlations,
        total_products=len(persona_summaries),
        active_claims=active_claims,
        overall_risk=profile.risk_tier,
    )


# =============================================================================
# Souscr'IA acquisition enrichment (read-only, graceful)
# =============================================================================

# Human-readable titles for Souscr'IA interaction types.
_SOUSCRIA_EVENT_TITLES = {
    "souscription": "Souscription",
    "appel": "Appel conseiller",
    "chat": "Conversation web",
    "email": "Échange e-mail",
}
# Map Souscr'IA interaction outcomes onto the Customer 360 timeline status palette
# (must stay within the frontend STATUS_CONFIG keys).
_SOUSCRIA_OUTCOME_STATUS = {
    "souscrit": "approved",
    "informé": "completed",
    "qualifié": "pending",
    "résolu": "closed",
}


def _souscria_interaction_to_event(interaction: Dict[str, Any]) -> CustomerJourneyEvent:
    """Map a Souscr'IA business interaction onto a Customer 360 journey event."""
    itype = (interaction.get("type") or "").lower()
    outcome = interaction.get("outcome") or ""
    channel = interaction.get("channel") or ""
    return CustomerJourneyEvent(
        date=interaction.get("date") or "",
        persona="souscria_acquisition",
        application_id="",  # not a workbench dossier → rendered as a non-clickable event
        event_type="souscria_interaction",
        title=_SOUSCRIA_EVENT_TITLES.get(itype, itype.capitalize() or "Interaction"),
        summary=interaction.get("summary") or "",
        status=_SOUSCRIA_OUTCOME_STATUS.get(outcome.lower(), "completed"),
        key_metrics={
            k: v
            for k, v in (("Source", "Souscr'IA"), ("Canal", channel), ("Issue", outcome))
            if v
        },
    )


def apply_souscria_acquisition(
    view: Customer360View, raw: Optional[Dict[str, Any]]
) -> Customer360View:
    """Inject live Souscr'IA acquisition context into a Customer 360 view (in place).

    ``raw`` is the dict returned by ``fetch_acquisition_context`` (or ``None``).
    No-op when the connector is off / unavailable so the view is unchanged. Sets
    the ``souscria_acquisition`` card and merges business interactions into the
    journey timeline (re-sorted most-recent first).
    """
    if not raw or not raw.get("available"):
        return view

    view.souscria_acquisition = SouscriaAcquisition(
        available=True,
        client_id=raw.get("client_id") or "",
        contracts=raw.get("contracts") or [],
        advisor=raw.get("advisor"),
        next_best_actions=raw.get("next_best_actions") or [],
    )

    events = [
        _souscria_interaction_to_event(i)
        for i in (raw.get("interactions") or [])
        if isinstance(i, dict)
    ]
    if events:
        view.journey_events = sorted(
            view.journey_events + events, key=lambda e: e.date, reverse=True
        )
    return view


def delete_customer(storage_root: str, customer_id: str) -> bool:
    """Delete a customer profile and all associated data (blob + local)."""
    import shutil

    deleted = False
    # Delete from Azure Blob
    container = _get_blob_container()
    if container:
        try:
            blobs = container.list_blobs(name_starts_with=_customer_blob_prefix(customer_id))
            for blob in blobs:
                container.delete_blob(blob.name)
                deleted = True
        except Exception as e:
            logger.warning("Blob delete failed for %s: %s", customer_id, e)

    # Delete from local filesystem
    customer_dir = _customers_dir(storage_root) / customer_id
    if customer_dir.exists():
        shutil.rmtree(customer_dir)
        deleted = True

    if deleted:
        logger.info("Deleted customer: %s", customer_id)
    return deleted
