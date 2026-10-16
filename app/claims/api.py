"""
Claims API Router for Automotive Claims Multimodal Processing

FastAPI router providing endpoints for:
- Claim submission with multimodal file upload
- Claim assessment retrieval and adjuster decisions
- Claims policy search via RAG
- Media file access (keyframes, damage areas)
"""

from __future__ import annotations

import uuid
import re
from datetime import datetime, UTC
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, Query, BackgroundTasks
from pydantic import BaseModel, Field

from ..config import load_settings
from ..utils import setup_logging
from ..database.pool import get_pool
from .policies import ClaimsPolicyLoader
from .engine import ClaimsPolicyEngine, ClaimAssessment
from .search import ClaimsPolicySearchService, ClaimsSearchResult, get_claims_policy_context
from ..rag.persona_search import AutomotiveClaimsPolicySearchService
from ..multimodal import (
    MultimodalProcessor,
    FileInfo,
    ProcessingResult,
    BatchResult,
    ProcessingStatus,
    ClaimsMediaRepository,
    detect_media_type,
)
from ..multimodal.aggregator import aggregate_claim_results
from ..storage import load_application, load_cu_result
from .habitation_analyzer import HabitationClaimsAnalyzer, AlertLevel
import json
from pathlib import Path

logger = setup_logging()

# Create router with prefix
router = APIRouter(prefix="/api/claims", tags=["Automotive Claims"])


# ============================================================================
# File-based Fallback Helpers
# ============================================================================


def _canonical_claim_id(claim_id: str) -> str:
    settings = load_settings()
    app_md = load_application(settings.app.storage_root, claim_id)
    return app_md.id if app_md else claim_id

_DAMAGE_AREA_KEYS = (
    "damage_areas",
    "damages",
    "zones_endommagees",
    "zones_de_dommages",
    "dommages",
    "vehicle_damage",
    "detected_damage",
    "detected_damages",
)


def _humanize_filename(filename: str) -> str:
    stem = Path(filename).stem
    for prefix in ("crash_", "accident_", "sinistre_", "photo_", "image_"):
        if stem.lower().startswith(prefix):
            stem = stem[len(prefix):]
            break
    return re.sub(r"[_-]+", " ", stem).strip()


def _damage_area_from_evidence_file(filename: str, claim_id: str, index: int) -> Optional[dict]:
    ext = Path(filename).suffix.lower()
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif", ".mp4", ".mov", ".avi", ".mkv"}:
        return None

    label = _humanize_filename(filename)
    normalized = label.lower()
    if not re.search(
        r"dommage|crash|accident|choc|enfonc|fissur|rayur|cass|bris|porti[eè]re|pare.?chocs|aile|capot|coffre|phare|feu|vitr",
        normalized,
    ):
        return None

    location = "Zone endommagée"
    location_patterns = [
        (r"porti[eè]re|door", "Portière"),
        (r"pare.?chocs|bumper", "Pare-chocs"),
        (r"aile|fender", "Aile"),
        (r"capot|hood", "Capot"),
        (r"coffre|trunk", "Coffre"),
        (r"phare|feu", "Optique"),
        (r"pare.?brise|vitr", "Vitrage"),
    ]
    for pattern, candidate in location_patterns:
        if re.search(pattern, normalized):
            location = candidate
            break

    severity = "moderate"
    if re.search(r"cass|bris|fissur|grave|important|total", normalized):
        severity = "severe"
    elif re.search(r"rayur|leger|l[eé]ger", normalized):
        severity = "minor"

    return {
        "area_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{claim_id}-evidence-{index}-{filename}")),
        "location": location,
        "severity": severity,
        "confidence": 0.72,
        "estimated_cost": 0.0,
        "description": label or f"Dommage visible dans {filename}",
        "bounding_box": None,
        "source_media_id": None,
    }


def _parse_amount(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return 0.0
    text = str(value)
    matches = re.findall(r"\d+(?:[.,]\d+)?", text.replace("\u202f", "").replace(" ", ""))
    if not matches:
        return 0.0
    try:
        return float(matches[0].replace(",", "."))
    except ValueError:
        return 0.0


def _normalize_damage_area(raw: Any, claim_id: str, index: int) -> Optional[dict]:
    if isinstance(raw, str):
        description = raw.strip()
        if not description:
            return None
        raw_dict: dict[str, Any] = {"description": description}
    elif isinstance(raw, dict):
        raw_dict = raw
    else:
        return None

    location = (
        raw_dict.get("location")
        or raw_dict.get("area")
        or raw_dict.get("zone")
        or raw_dict.get("part")
        or raw_dict.get("component")
        or raw_dict.get("body_panel")
        or "unknown"
    )
    severity = str(
        raw_dict.get("severity")
        or raw_dict.get("gravite")
        or raw_dict.get("damage_severity")
        or "moderate"
    ).lower()
    if severity in {"mineur", "minor"}:
        severity = "minor"
    elif severity in {"grave", "heavy", "severe", "eleve", "élevé"}:
        severity = "severe"
    elif severity in {"perte totale", "total loss", "total_loss"}:
        severity = "total_loss"
    else:
        severity = "moderate" if severity not in {"minor", "moderate", "severe", "total_loss"} else severity

    components = raw_dict.get("components")
    if isinstance(components, list):
        component_text = ", ".join(str(c) for c in components if c)
    else:
        component_text = str(components or "").strip()
    damage_type = raw_dict.get("damage_type") or raw_dict.get("type") or raw_dict.get("nature")
    repair = raw_dict.get("repair_method") or raw_dict.get("recommended_repair") or raw_dict.get("reparation")
    description = (
        raw_dict.get("description")
        or raw_dict.get("details")
        or " - ".join(str(v) for v in (damage_type, component_text, repair) if v)
        or str(location)
    )
    estimated_cost = (
        _parse_amount(raw_dict.get("estimated_cost"))
        or _parse_amount(raw_dict.get("cost"))
        or _parse_amount(raw_dict.get("estimated_cost_range"))
        or _parse_amount(raw_dict.get("cout_estime"))
    )

    return {
        "area_id": raw_dict.get("area_id") or str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{claim_id}-damage-{index}-{location}")),
        "location": str(location),
        "severity": severity,
        "confidence": _parse_amount(raw_dict.get("confidence")) or 0.85,
        "estimated_cost": estimated_cost,
        "description": str(description),
        "bounding_box": raw_dict.get("bounding_box"),
        "source_media_id": raw_dict.get("source_media_id"),
    }


def _collect_damage_candidates(node: Any) -> list[Any]:
    candidates: list[Any] = []
    if isinstance(node, dict):
        for key, value in node.items():
            normalized = key.lower().replace("-", "_")
            if normalized in _DAMAGE_AREA_KEYS and isinstance(value, list):
                candidates.extend(value)
            elif normalized in {"visual_damage_analysis", "visual_damage_assessment", "damage_assessment"}:
                candidates.extend(_collect_damage_candidates(value))
            elif isinstance(value, (dict, list)):
                candidates.extend(_collect_damage_candidates(value))
    elif isinstance(node, list):
        for item in node:
            candidates.extend(_collect_damage_candidates(item))
    return candidates


def _extract_damage_areas_from_metadata(app_metadata, claim_id: str) -> list[dict]:
    damage_areas: list[dict] = []
    seen: set[str] = set()

    def add_candidates(candidates: list[Any]) -> None:
        for raw in candidates:
            area = _normalize_damage_area(raw, claim_id, len(damage_areas))
            if not area:
                continue
            dedupe_key = f"{area['location']}|{area['description']}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            damage_areas.append(area)

    llm_outputs = app_metadata.llm_outputs or {}
    add_candidates(_collect_damage_candidates(llm_outputs))

    extracted_fields = app_metadata.extracted_fields or {}
    for key, entry in extracted_fields.items():
        field_name = str(key).split(":")[-1].lower()
        if field_name not in _DAMAGE_AREA_KEYS and "damage" not in field_name and "dommage" not in field_name:
            continue
        value = entry.get("value") if isinstance(entry, dict) and "value" in entry else entry
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("[") or stripped.startswith("{"):
                try:
                    value = json.loads(stripped)
                except json.JSONDecodeError:
                    pass
        add_candidates(value if isinstance(value, list) else [value])

    if not damage_areas:
        for file_index, stored_file in enumerate(app_metadata.files or []):
            area = _damage_area_from_evidence_file(stored_file.filename, claim_id, file_index)
            if area:
                damage_areas.append(area)

    return damage_areas


def _get_assessment_from_files(claim_id: str) -> Optional[dict]:
    """
    Generate assessment data from metadata.json with LLM outputs.
    This provides backward compatibility for claims created through the
    traditional application flow.
    Returns data matching ClaimAssessmentResponse structure.
    
    Uses storage provider abstraction to support both local and Azure Blob storage.
    """
    settings = load_settings()
    root = settings.app.storage_root
    
    # Use storage provider to load metadata (supports both local and blob storage)
    app_metadata = load_application(root, claim_id)
    
    if not app_metadata:
        return None
    
    try:
        # Convert ApplicationMetadata to dict for processing
        metadata = {
            "id": app_metadata.id,
            "persona": app_metadata.persona,
            "llm_outputs": app_metadata.llm_outputs or {},
            "created_at": app_metadata.created_at,
        }
        
        # Get LLM outputs from metadata
        llm_outputs = metadata.get("llm_outputs", {})
        
        # Extract damage assessment
        damage_data = llm_outputs.get("damage_assessment", {})
        visual_analysis = damage_data.get("visual_damage_analysis", {})
        visual_parsed = visual_analysis.get("parsed", {})
        
        # Extract liability assessment
        liability_data = llm_outputs.get("liability_assessment", {})
        fault_determination = liability_data.get("fault_determination", {})
        fault_parsed = fault_determination.get("parsed", {})
        
        # Extract fraud detection
        fraud_data = llm_outputs.get("fraud_detection", {})
        red_flag_analysis = fraud_data.get("red_flag_analysis", {})
        fraud_parsed = red_flag_analysis.get("parsed", {})
        
        # Extract payout recommendation
        payout_data = llm_outputs.get("payout_recommendation", {})
        settlement_analysis = payout_data.get("settlement_analysis", {})
        payout_parsed = settlement_analysis.get("parsed", {})
        
        # Build detailed damage areas list from LLM and CU variants.
        damage_areas = _extract_damage_areas_from_metadata(app_metadata, claim_id)
        total_estimated_damage = sum(area.get("estimated_cost", 0.0) for area in damage_areas)
        
        # Parse payout amounts
        payout_amount = 0.0
        if payout_parsed:
            recommended = payout_parsed.get(
                "recommended_settlement",
                payout_parsed.get("recommended_amount",
                payout_parsed.get("recommended_payout", 0))
            )
            if isinstance(recommended, (int, float)):
                payout_amount = float(recommended)
            elif isinstance(recommended, str):
                try:
                    payout_amount = float(recommended.replace(",", "").replace("$", "").replace("€", "").replace("\u202f", ""))
                except Exception:
                    pass
        
        # Build fraud indicators
        fraud_indicators = []
        for indicator in fraud_parsed.get("red_flags", fraud_parsed.get("indicators", [])):
            if isinstance(indicator, dict):
                fraud_indicators.append({
                    "indicator_type": indicator.get("category", indicator.get("type", "general")),
                    "severity": "low",  # Default to low
                    "description": indicator.get("indicator", indicator.get("description", str(indicator))),
                    "confidence": 0.7,
                })
            elif isinstance(indicator, str):
                fraud_indicators.append({
                    "indicator_type": "general",
                    "severity": "low",
                    "description": indicator,
                    "confidence": 0.7,
                })
        
        # Build policy citations
        policy_citations = []
        for citation in payout_parsed.get("policy_citations", []):
            if isinstance(citation, dict):
                policy_citations.append({
                    "policy_id": citation.get("policy_id", "AC-001"),
                    "policy_name": citation.get("title", citation.get("policy_name", "")),
                    "section": citation.get("section", ""),
                    "citation_text": citation.get("text", citation.get("citation_text", "")),
                    "relevance_score": citation.get("relevance", citation.get("relevance_score", 0.9)),
                    "supports_coverage": True,
                })
        
        if not policy_citations:
            policy_citations = [{
                "policy_id": "AC-DMG-001",
                "policy_name": "Damage Assessment Standards",
                "section": "Assessment",
                "citation_text": "Standard damage assessment applied",
                "relevance_score": 0.9,
                "supports_coverage": True,
            }]
        
        created_at = metadata.get("created_at", datetime.now(UTC).isoformat())
        
        return {
            "claim_id": claim_id,
            "status": "completed",
            "overall_severity": visual_parsed.get("overall_severity", "moderate").lower(),
            "total_estimated_damage": total_estimated_damage if total_estimated_damage > 0 else payout_amount,
            "damage_areas": damage_areas,
            "liability": {
                "fault_determination": fault_parsed.get("fault_determination", fault_parsed.get("primary_fault", "Pending")),
                "fault_percentage": fault_parsed.get("fault_percentage", fault_parsed.get("liability_percentage", 0)),
                "contributing_factors": _extract_string_list(fault_parsed.get("contributing_factors", [])),
                "liability_notes": fault_parsed.get("rationale", fault_parsed.get("summary", "Based on submitted incident documentation")),
            },
            "fraud_indicators": fraud_indicators,
            "policy_citations": policy_citations,
            "payout_recommendation": {
                "recommended_amount": payout_amount,
                "min_amount": payout_amount * 0.8 if payout_amount > 0 else 0,
                "max_amount": payout_amount * 1.2 if payout_amount > 0 else 0,
                "breakdown": {},
                "adjustments": payout_parsed.get("adjustments", []),
            },
            "adjuster_decision": None,
            "created_at": created_at,
            "updated_at": created_at,
        }
    except Exception as e:
        logger.error(f"Failed to read metadata for {claim_id}: {e}")
        return None


def _get_field_value(fields: dict, field_name: str, default: str = "") -> str:
    """Extract field value from content understanding fields."""
    field = fields.get(field_name, {})
    return field.get("valueString", field.get("valueDate", default)) or default


def _extract_string_list(items: List[Any]) -> List[str]:
    """Convert a list of items (possibly dicts) to a list of strings."""
    result = []
    for item in items:
        if isinstance(item, str):
            result.append(item)
        elif isinstance(item, dict):
            # Try to extract a meaningful string from the dict
            text = item.get("indicator", item.get("description", item.get("text", item.get("name", ""))))
            if text:
                result.append(str(text))
            else:
                # Fallback: use the first string value found
                for v in item.values():
                    if isinstance(v, str) and v:
                        result.append(v)
                        break
        else:
            result.append(str(item))
    return result


def _extract_damage_areas(fields: dict) -> List[str]:
    """Extract damage areas from fields."""
    areas = []
    damage_areas_field = fields.get("DamageAreas", {})
    if isinstance(damage_areas_field, dict):
        value = damage_areas_field.get("valueString", "")
        if value:
            areas = [a.strip() for a in value.split(",") if a.strip()]
    return areas if areas else ["Front bumper", "Left fender"]


def _get_media_from_files(claim_id: str) -> List[dict]:
    """
    Generate media list from storage (supports both local and Azure Blob storage).
    """
    settings = load_settings()
    root = settings.app.storage_root
    
    # Use storage provider to load metadata (supports both local and blob storage)
    app_metadata = load_application(root, claim_id)
    
    media_list = []
    
    if not app_metadata or not app_metadata.files:
        return media_list
    
    # Content type mapping
    content_types = {
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
    
    for stored_file in app_metadata.files:
        filename = stored_file.filename
        ext = Path(filename).suffix.lower()
        if ext in content_types:
            # Determine media type from extension
            if ext in [".mp4", ".mov", ".avi", ".mkv", ".webm"]:
                media_type = "video"
            elif ext in [".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"]:
                media_type = "image"
            else:
                media_type = "document"
            
            # Always use proxy URL — direct blob URLs fail when public access is disabled
            url = f"/api/applications/{claim_id}/files/{filename}"
            
            media_list.append({
                "media_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{claim_id}/{filename}")),
                "filename": filename,
                "content_type": content_types.get(ext, "application/octet-stream"),
                "media_type": media_type,
                "size": 0,  # Size not available from metadata
                "thumbnail_url": url if media_type == "image" else None,
                "url": url,
                "processed": True,
                "analysis_summary": None,
                "uploaded_at": datetime.now(UTC).isoformat(),
            })
    
    return media_list


def _get_keyframes_from_files(claim_id: str, media_id: str) -> tuple[List[dict], float]:
    """
    Generate synthetic keyframes for video files based on video analysis data.
    Returns tuple of (keyframes list, video duration in seconds).
    
    Uses storage provider abstraction to support both local and Azure Blob storage.
    """
    settings = load_settings()
    root = settings.app.storage_root
    
    keyframes = []
    video_duration = 30.0  # Default duration in seconds
    
    # Use storage provider to load metadata (supports both local and blob storage)
    app_metadata = load_application(root, claim_id)
    
    if not app_metadata:
        return keyframes, video_duration
    
    try:
        # Find video file info
        video_filename = None
        for file_info in app_metadata.files or []:
            filename = file_info.filename
            if filename.lower().endswith(('.mp4', '.mov', '.avi', '.webm')):
                video_filename = filename
                break
        
        if not video_filename:
            return keyframes, video_duration
        
        # Extract video analysis fields from metadata
        # extracted_fields can be either a dict (key = "filename:fieldname") or a list
        extracted_fields = app_metadata.extracted_fields or {}
        video_fields = {}
        
        if isinstance(extracted_fields, dict):
            # New format: dict with "filename:FieldName" keys
            for field_key, field_data in extracted_fields.items():
                if field_key.startswith(video_filename + ":"):
                    key = field_key.split(":", 1)[1]
                    if isinstance(field_data, dict):
                        video_fields[key] = field_data.get("value")
                    else:
                        video_fields[key] = field_data
        elif isinstance(extracted_fields, list):
            # Old format: list of {"name": "filename:FieldName", "value": ...}
            for field in extracted_fields:
                field_name = field.get("name", "")
                if field_name.startswith(video_filename + ":"):
                    key = field_name.split(":", 1)[1]
                    video_fields[key] = field.get("value")
        
        # Parse incident timestamp (e.g., "00:00:05.600")
        incident_timestamp_str = video_fields.get("IncidentTimestamp", "00:00:00")
        incident_timestamp = 0.0
        if incident_timestamp_str:
            parts = incident_timestamp_str.replace(",", ".").split(":")
            try:
                if len(parts) == 3:
                    h, m, s = parts
                    incident_timestamp = float(h) * 3600 + float(m) * 60 + float(s)
                elif len(parts) == 2:
                    m, s = parts
                    incident_timestamp = float(m) * 60 + float(s)
            except ValueError:
                incident_timestamp = 5.0
        
        incident_type = video_fields.get("IncidentType", "collision")
        incident_detected = video_fields.get("IncidentDetected", True)
        pre_behavior = video_fields.get("PreIncidentBehavior", "")
        post_behavior = video_fields.get("PostIncidentBehavior", "")
        weather = video_fields.get("WeatherConditions", "")
        road_type = video_fields.get("RoadType", "")
        
        # Estimate video duration based on incident timestamp
        if incident_timestamp > 0:
            video_duration = max(incident_timestamp * 2, 20.0)  # Assume incident is roughly in middle
        
        # Generate keyframes at key moments
        keyframe_times = []
        
        # Keyframe before incident (pre-incident context)
        if incident_timestamp > 2:
            keyframe_times.append((incident_timestamp - 2, "Pre-incident", False, pre_behavior or "Vehicle approaching"))
        
        # Keyframe at incident
        if incident_detected:
            keyframe_times.append((
                incident_timestamp, 
                f"Incident: {incident_type}", 
                True, 
                f"Impact detected - {incident_type}"
            ))
        
        # Keyframe after incident
        keyframe_times.append((
            incident_timestamp + 2, 
            "Post-incident", 
            True, 
            post_behavior or "Post-collision assessment"
        ))
        
        # Additional context keyframes
        if incident_timestamp > 5:
            keyframe_times.insert(0, (0.5, "Video start", False, f"Recording begins - {road_type or 'road'}"))
        
        # Generate keyframe objects
        for i, (timestamp, label, damage_detected, description) in enumerate(keyframe_times):
            minutes = int(timestamp // 60)
            seconds = timestamp % 60
            timestamp_formatted = f"{minutes:02d}:{seconds:05.2f}"
            
            keyframes.append({
                "keyframe_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{claim_id}-{media_id}-kf-{i}")),
                "timestamp": timestamp,
                "timestamp_formatted": timestamp_formatted,
                "thumbnail_url": None,  # No actual thumbnail available
                "description": description,
                "damage_detected": damage_detected,
                "damage_areas": [],
                "confidence": 0.85 if damage_detected else 0.75,
            })
        
        return keyframes, video_duration
        
    except Exception as e:
        logger.error(f"Failed to get keyframes from files: {e}")
        return [], video_duration


def _get_damage_areas_from_files(claim_id: str, media_id: str) -> List[dict]:
    """
    Generate damage areas from content understanding data.
    
    Uses storage provider abstraction to support both local and Azure Blob storage.
    """
    settings = load_settings()
    root = settings.app.storage_root
    
    # Use storage provider to load CU result (supports both local and blob storage)
    cu_data = load_cu_result(root, claim_id)
    
    if not cu_data:
        return []
    
    try:
        result = cu_data.get("result", {})
        contents = result.get("contents", [])
        if not contents:
            return []
        
        fields = contents[0].get("fields", {})
        damage_areas = _extract_damage_areas(fields)
        
        return [
            {
                "area_id": str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{claim_id}-{i}")),
                "location": area,
                "severity": "moderate",
                "confidence": 0.85,
                "bounding_box": None,
                "source_media_id": media_id,
            }
            for i, area in enumerate(damage_areas)
        ]
    except Exception as e:
        logger.error(f"Failed to get damage areas from files: {e}")
        return []


# ============================================================================
# Pydantic Models
# ============================================================================

class ClaimSubmitRequest(BaseModel):
    """Request model for claim submission."""
    external_reference: Optional[str] = Field(None, description="External claim reference ID")
    claimant_name: Optional[str] = None
    vehicle_info: Optional[dict] = None
    incident_description: Optional[str] = None
    incident_date: Optional[str] = None


class ClaimSubmitResponse(BaseModel):
    """Response from claim submission."""
    claim_id: str
    status: str
    created_at: str
    file_count: int
    message: str


class FileUploadResponse(BaseModel):
    """Response from file upload."""
    file_id: str
    filename: str
    media_type: str
    content_type: str
    size_bytes: int


class ProcessingStatusResponse(BaseModel):
    """Response for processing status."""
    claim_id: str
    status: str
    total_files: int
    completed: int
    failed: int
    progress_percent: float


class DamageAreaItem(BaseModel):
    """Response for a damage area item."""
    area_id: str
    location: str
    severity: str  # minor, moderate, severe, total_loss
    confidence: float
    estimated_cost: float = 0.0
    description: str = ""
    bounding_box: Optional[dict] = None
    source_media_id: Optional[str] = None


class LiabilityAssessmentResponse(BaseModel):
    """Response for liability assessment."""
    fault_determination: str
    fault_percentage: int
    contributing_factors: List[str]
    liability_notes: str


class FraudIndicatorItem(BaseModel):
    """Response for fraud indicator."""
    indicator_type: str
    severity: str  # low, medium, high
    description: str
    confidence: float = 0.85


class PayoutRecommendationResponse(BaseModel):
    """Response for payout recommendation."""
    recommended_amount: float
    min_amount: float = 0.0
    max_amount: float = 0.0
    breakdown: dict = {}
    adjustments: List[dict] = []


class PolicyCitationItem(BaseModel):
    """Response for policy citation."""
    policy_id: str
    policy_name: str = ""
    section: str = ""
    citation_text: str = ""
    relevance_score: float = 0.9
    supports_coverage: bool = True


class ClaimAssessmentResponse(BaseModel):
    """Full claim assessment response - aligned with frontend expectations."""
    claim_id: str
    status: str
    overall_severity: str  # minor, moderate, severe, total_loss
    total_estimated_damage: float = 0.0
    damage_areas: List[DamageAreaItem] = []
    liability: LiabilityAssessmentResponse
    fraud_indicators: List[FraudIndicatorItem] = []
    policy_citations: List[PolicyCitationItem] = []
    payout_recommendation: PayoutRecommendationResponse
    adjuster_decision: Optional[dict] = None
    created_at: str = ""
    updated_at: str = ""


class AdjusterDecisionRequest(BaseModel):
    """Request for adjuster decision update."""
    decision: str = Field(..., description="approved, denied, pending_review")
    approved_amount: Optional[float] = None
    notes: Optional[str] = None


class PolicySearchRequest(BaseModel):
    """Request for policy search."""
    query: str = Field(..., description="Natural language query")
    category: Optional[str] = Field(None, description="Filter by category")
    top_k: int = Field(5, ge=1, le=20)


class PolicySearchResponse(BaseModel):
    """Response from policy search."""
    query: str
    results: List[dict]
    total_results: int


class MediaItemResponse(BaseModel):
    """Response for a media item."""
    media_id: str
    filename: str
    content_type: str
    media_type: str
    size: int = 0
    thumbnail_url: Optional[str] = None
    url: str
    processed: bool
    analysis_summary: Optional[str] = None
    uploaded_at: str


class MediaListResponse(BaseModel):
    """Response for media list."""
    claim_id: str
    media_items: List[MediaItemResponse]
    total_count: int


class KeyframeResponse(BaseModel):
    """Response for video keyframe."""
    keyframe_id: str
    timestamp: float
    timestamp_formatted: str
    thumbnail_url: Optional[str] = None
    description: Optional[str] = None
    damage_detected: bool
    damage_areas: List[dict] = Field(default_factory=list)
    confidence: float = 0.8


class KeyframesListResponse(BaseModel):
    """Response for keyframes list."""
    media_id: str
    duration: float
    keyframes: List[KeyframeResponse]
    total_keyframes: int


class DamageAreaResponse(BaseModel):
    """Response for detected damage area."""
    area_id: str
    location: str
    severity: str
    confidence: float
    bounding_box: Optional[dict] = None
    source_media_id: str


# ============================================================================
# Claim Submission Endpoints
# ============================================================================

@router.post("/submit", response_model=ClaimSubmitResponse)
async def submit_claim(
    files: List[UploadFile] = File(...),
    external_reference: Optional[str] = Form(None),
    claimant_name: Optional[str] = Form(None),
    vehicle_info: Optional[str] = Form(None),  # JSON string
    incident_description: Optional[str] = Form(None),
    incident_date: Optional[str] = Form(None),
) -> ClaimSubmitResponse:
    """
    Submit a new automotive claim with multimodal files.
    
    Accepts PDF documents, images (JPEG, PNG), and videos (MP4, MOV).
    Files are automatically routed to appropriate Azure Content Understanding analyzers.
    """
    claim_id = str(uuid.uuid4())[:8]
    created_at = datetime.now(UTC).isoformat()
    
    # Validate files
    if not files:
        raise HTTPException(status_code=400, detail="At least one file is required")
    
    file_infos = []
    for upload_file in files:
        content = await upload_file.read()
        detection = detect_media_type(content, upload_file.filename)
        
        if not detection.is_supported:
            logger.warning(f"Unsupported file type: {upload_file.filename}")
            continue
        
        file_infos.append(FileInfo(
            file_id=str(uuid.uuid4()),
            filename=upload_file.filename,
            file_bytes=content,
            content_type=detection.mime_type,
            claim_id=claim_id,
            metadata={
                "media_type": detection.media_type.value,
                "external_reference": external_reference,
                "claimant_name": claimant_name,
                "incident_date": incident_date,
            }
        ))
    
    if not file_infos:
        raise HTTPException(status_code=400, detail="No valid files were uploaded")
    
    # Store claim metadata in database
    try:
        settings = load_settings()
        repository = ClaimsMediaRepository(settings)
        await repository.initialize_tables()
        
        # Save initial claim record
        pool = await get_pool()
        async with pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO workbenchiq.claims (
                    claim_id, external_reference, claimant_name,
                    incident_description, incident_date, status, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (claim_id) DO UPDATE SET
                    external_reference = EXCLUDED.external_reference,
                    updated_at = CURRENT_TIMESTAMP
                """,
                claim_id,
                external_reference,
                claimant_name,
                incident_description,
                incident_date,
                "pending_processing",
                created_at,
            )
    except Exception as e:
        logger.error(f"Failed to save claim: {e}")
        # Continue without database - files will still be processed
    
    return ClaimSubmitResponse(
        claim_id=claim_id,
        status="pending_processing",
        created_at=created_at,
        file_count=len(file_infos),
        message=f"Claim submitted successfully with {len(file_infos)} files",
    )


@router.post("/{claim_id}/upload", response_model=List[FileUploadResponse])
async def upload_claim_files(
    claim_id: str,
    files: List[UploadFile] = File(...),
) -> List[FileUploadResponse]:
    """
    Upload additional files to an existing claim.

    Persists files to application storage and updates metadata so the
    files appear in the media list and can be served via the file endpoint.
    """
    from ..storage import (
        save_uploaded_files,
        load_application as load_app,
        save_application_metadata,
    )

    settings = load_settings()
    claim_id = _canonical_claim_id(claim_id)
    responses = []
    file_data = []

    for upload_file in files:
        content = await upload_file.read()
        detection = detect_media_type(content, upload_file.filename)

        if not detection.is_supported:
            logger.warning("Skipping unsupported file: %s", upload_file.filename)
            continue

        file_data.append({"name": upload_file.filename, "content": content})

        file_id = str(uuid.uuid4())
        responses.append(FileUploadResponse(
            file_id=file_id,
            filename=upload_file.filename,
            media_type=detection.media_type.value,
            content_type=detection.mime_type,
            size_bytes=len(content),
        ))

    # Persist files to storage and update application metadata
    if file_data:
        stored_files = save_uploaded_files(
            settings.app.storage_root,
            claim_id,
            file_data,
            public_base_url=settings.app.public_files_base_url,
        )
        app_md = load_app(settings.app.storage_root, claim_id)
        if app_md:
            existing_names = {f.filename for f in app_md.files}
            for sf in stored_files:
                if sf.filename not in existing_names:
                    app_md.files.append(sf)
            app_md.file_count = len(app_md.files)
            save_application_metadata(settings.app.storage_root, app_md)
            logger.info(
                "Persisted %d files for claim %s (total %d)",
                len(stored_files), claim_id, app_md.file_count,
            )

    return responses


@router.post("/{claim_id}/process", response_model=ProcessingStatusResponse)
async def process_claim(
    claim_id: str,
    background_tasks: BackgroundTasks,
) -> ProcessingStatusResponse:
    """
    Trigger multimodal processing for all uploaded claim files.
    
    Processing happens asynchronously. Use the status endpoint to check progress.
    """
    # In a real implementation, this would:
    # 1. Retrieve uploaded files from storage
    # 2. Queue them for processing
    # 3. Return immediately with a status
    
    return ProcessingStatusResponse(
        claim_id=claim_id,
        status="processing",
        total_files=0,
        completed=0,
        failed=0,
        progress_percent=0.0,
    )


@router.get("/{claim_id}/status", response_model=ProcessingStatusResponse)
async def get_processing_status(claim_id: str) -> ProcessingStatusResponse:
    """
    Get the processing status for a claim.
    """
    # Query database for actual status
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT status, 
                       (SELECT COUNT(*) FROM workbenchiq.claim_media WHERE claim_id = $1) as total,
                       (SELECT COUNT(*) FROM workbenchiq.claim_media WHERE claim_id = $1 AND status = 'completed') as completed,
                       (SELECT COUNT(*) FROM workbenchiq.claim_media WHERE claim_id = $1 AND status = 'failed') as failed
                FROM workbenchiq.claims
                WHERE claim_id = $1
                """,
                claim_id,
            )
            
            if not row:
                raise HTTPException(status_code=404, detail="Claim not found")
            
            total = row["total"] or 0
            completed = row["completed"] or 0
            failed = row["failed"] or 0
            progress = (completed + failed) / total * 100 if total > 0 else 0
            
            return ProcessingStatusResponse(
                claim_id=claim_id,
                status=row["status"],
                total_files=total,
                completed=completed,
                failed=failed,
                progress_percent=progress,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get status: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve status")


# ============================================================================
# Assessment Endpoints
# ============================================================================

@router.get("/{claim_id}/assessment", response_model=ClaimAssessmentResponse)
async def get_claim_assessment(claim_id: str) -> ClaimAssessmentResponse:
    """
    Get the policy-based assessment for a claim.
    
    Returns damage severity, liability determination, fraud risk, and payout recommendation
    with policy citations.
    
    Falls back to file-based storage if database has no data (backward compatibility).
    """
    claim_id = _canonical_claim_id(claim_id)
    assessment_data = None
    
    # Try database first (if available)
    try:
        settings = load_settings()
        repository = ClaimsMediaRepository(settings)
        assessment_data = await repository.get_claim_assessment(claim_id)
    except Exception as db_error:
        logger.debug(f"Database access failed for {claim_id}, using file fallback: {db_error}")
    
    # Fallback to file-based storage
    if not assessment_data:
        logger.info(f"Using file-based fallback for assessment {claim_id}")
        assessment_data = _get_assessment_from_files(claim_id)
    
    if not assessment_data:
        raise HTTPException(status_code=404, detail="Assessment not found")
    
    try:
        # Build damage areas
        damage_areas = []
        for area in assessment_data.get("damage_areas", []):
            if isinstance(area, dict):
                damage_areas.append(DamageAreaItem(
                    area_id=area.get("area_id", str(uuid.uuid4())),
                    location=area.get("location", "unknown"),
                    severity=area.get("severity", "moderate"),
                    confidence=area.get("confidence", 0.8),
                    estimated_cost=area.get("estimated_cost", 0.0),
                    description=area.get("description"),
                    bounding_box=area.get("bounding_box"),
                    source_media_id=area.get("source_media_id"),
                ))
        
        # Build liability
        liability_data = assessment_data.get("liability", {})
        liability = LiabilityAssessmentResponse(
            fault_determination=liability_data.get("fault_determination", "Pending"),
            fault_percentage=liability_data.get("fault_percentage", 0),
            contributing_factors=liability_data.get("contributing_factors", []),
            liability_notes=liability_data.get("liability_notes"),
        )
        
        # Build fraud indicators
        fraud_indicators = []
        for indicator in assessment_data.get("fraud_indicators", []):
            if isinstance(indicator, dict):
                fraud_indicators.append(FraudIndicatorItem(
                    indicator_type=indicator.get("indicator_type", "general"),
                    severity=indicator.get("severity", "low"),
                    description=indicator.get("description", ""),
                    confidence=indicator.get("confidence", 0.7),
                ))
        
        # Build policy citations
        policy_citations = []
        for citation in assessment_data.get("policy_citations", []):
            if isinstance(citation, dict):
                policy_citations.append(PolicyCitationItem(
                    policy_id=citation.get("policy_id", ""),
                    policy_name=citation.get("policy_name", citation.get("title", "")),
                    section=citation.get("section"),
                    citation_text=citation.get("citation_text", citation.get("text", "")),
                    relevance_score=citation.get("relevance_score", citation.get("relevance", 0.9)),
                    supports_coverage=citation.get("supports_coverage", True),
                ))
        
        # Build payout recommendation
        payout_data = assessment_data.get("payout_recommendation", {})
        payout = PayoutRecommendationResponse(
            recommended_amount=payout_data.get("recommended_amount", 0.0),
            min_amount=payout_data.get("min_amount"),
            max_amount=payout_data.get("max_amount"),
            breakdown=payout_data.get("breakdown", {}),
            adjustments=payout_data.get("adjustments", []),
        )
        
        return ClaimAssessmentResponse(
            claim_id=claim_id,
            status=assessment_data.get("status", "pending"),
            overall_severity=assessment_data.get("overall_severity", "moderate"),
            total_estimated_damage=assessment_data.get("total_estimated_damage", 0.0),
            damage_areas=damage_areas,
            liability=liability,
            fraud_indicators=fraud_indicators,
            policy_citations=policy_citations,
            payout_recommendation=payout,
            adjuster_decision=assessment_data.get("adjuster_decision"),
            created_at=assessment_data.get("created_at", ""),
            updated_at=assessment_data.get("updated_at"),
        )
    except Exception as e:
        logger.error(f"Failed to build assessment response: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve assessment")


@router.put("/{claim_id}/assessment/decision")
async def update_adjuster_decision(
    claim_id: str,
    request: AdjusterDecisionRequest,
) -> dict:
    """
    Update the adjuster's decision on a claim.
    """
    settings = load_settings()
    repository = ClaimsMediaRepository(settings)
    
    try:
        await repository.update_adjuster_decision(
            claim_id=claim_id,
            decision=request.decision,
            approved_amount=request.approved_amount,
            notes=request.notes,
        )
        
        return {
            "claim_id": claim_id,
            "decision": request.decision,
            "updated_at": datetime.now(UTC).isoformat(),
            "message": "Decision updated successfully",
        }
    except Exception as e:
        logger.error(f"Failed to update decision: {e}")
        raise HTTPException(status_code=500, detail="Failed to update decision")


@router.get("/pending", response_model=List[dict])
async def list_pending_claims(
    limit: int = Query(50, ge=1, le=100),
) -> List[dict]:
    """
    List claims pending adjuster review.
    """
    settings = load_settings()
    repository = ClaimsMediaRepository(settings)
    
    try:
        pending = await repository.list_pending_assessments(limit=limit)
        return pending
    except Exception as e:
        logger.error(f"Failed to list pending claims: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve pending claims")


# ============================================================================
# Policy Search Endpoints
# ============================================================================

@router.post("/policies/search", response_model=PolicySearchResponse)
async def search_policies(request: PolicySearchRequest) -> PolicySearchResponse:
    """
    Search claims policies using semantic search.
    
    Returns relevant policy sections based on natural language query.
    """
    settings = load_settings()
    # Use unified indexer-compatible search service
    search_service = AutomotiveClaimsPolicySearchService(settings)
    
    try:
        # Use lower threshold for policy search UI (single keywords often score lower)
        results = await search_service.hybrid_search(
            query=request.query,
            top_k=request.top_k,
            similarity_threshold=0.3,  # Lower threshold for keyword searches
        )
        
        return PolicySearchResponse(
            query=request.query,
            results=[
                {
                    "chunk_id": str(r.chunk_id),
                    "policy_id": r.policy_id,
                    "policy_name": r.policy_name,
                    "category": r.category,
                    "content": r.content,
                    "similarity": r.similarity,
                    "severity": r.risk_level,  # Map risk_level to severity for API compatibility
                    "criteria_id": r.criteria_id,
                }
                for r in results
            ],
            total_results=len(results),
        )
    except Exception as e:
        logger.error(f"Policy search failed: {e}")
        raise HTTPException(status_code=500, detail="Policy search failed")


@router.get("/policies/context")
async def get_policy_context(
    query: str = Query(..., description="Query for policy context"),
    category: Optional[str] = Query(None),
    top_k: int = Query(5, ge=1, le=20),
) -> dict:
    """
    Get formatted policy context for RAG-based chat.
    """
    settings = load_settings()
    
    try:
        context = await get_claims_policy_context(
            settings=settings,
            query=query,
            category=category,
            top_k=top_k,
        )
        
        return {"query": query, "context": context}
    except Exception as e:
        logger.error(f"Failed to get policy context: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve policy context")


# ============================================================================
# Media Endpoints
# ============================================================================

@router.get("/{claim_id}/media", response_model=MediaListResponse)
async def list_claim_media(claim_id: str) -> MediaListResponse:
    """
    List all media files for a claim.
    
    Falls back to file-based storage if database has no data (backward compatibility).
    """
    claim_id = _canonical_claim_id(claim_id)
    media_list = None
    
    # Try database first (if available)
    try:
        settings = load_settings()
        repository = ClaimsMediaRepository(settings)
        media_list = await repository.get_claim_media(claim_id)
    except Exception as db_error:
        logger.debug(f"Database access failed for media {claim_id}, using file fallback: {db_error}")
    
    # Fallback to file-based storage
    if not media_list:
        logger.info(f"Using file-based fallback for media {claim_id}")
        media_list = _get_media_from_files(claim_id)
    
    items = [
        MediaItemResponse(
            media_id=m["media_id"],
            filename=m["filename"],
            content_type=m.get("content_type", "application/octet-stream"),
            media_type=m["media_type"],
            size=m.get("size", 0),
            thumbnail_url=m.get("thumbnail_url"),
            url=m.get("url", ""),
            processed=m.get("processed", True),
            analysis_summary=m.get("analysis_summary"),
            uploaded_at=m["uploaded_at"],
        )
        for m in media_list
    ]
    
    return MediaListResponse(
        claim_id=claim_id,
        media_items=items,
        total_count=len(items),
    )


@router.get("/{claim_id}/media/{media_id}/keyframes", response_model=KeyframesListResponse)
async def get_media_keyframes(claim_id: str, media_id: str) -> KeyframesListResponse:
    """
    Get extracted keyframes from a video file.
    
    Falls back to file-based storage if database has no data.
    """
    claim_id = _canonical_claim_id(claim_id)
    keyframes = None
    
    # Try database first (if available)
    try:
        settings = load_settings()
        repository = ClaimsMediaRepository(settings)
        keyframes = await repository.get_keyframes(claim_id)
        # Filter by media_id if needed
        if keyframes:
            keyframes = [kf for kf in keyframes if str(kf.get("media_id", "")) == media_id]
    except Exception as db_error:
        logger.debug(f"Database access failed for keyframes {claim_id}, using fallback: {db_error}")
    
    # Fallback to file-based storage
    video_duration = 30.0  # Default duration
    if keyframes is None:
        keyframes, video_duration = _get_keyframes_from_files(claim_id, media_id)
    
    def format_timestamp(seconds: float) -> str:
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins:02d}:{secs:05.2f}"
    
    items = [
        KeyframeResponse(
            keyframe_id=str(kf.get("id", kf.get("keyframe_id", ""))),
            timestamp=kf.get("timestamp_seconds", kf.get("timestamp", 0.0)),
            timestamp_formatted=kf.get("timestamp_formatted", format_timestamp(kf.get("timestamp_seconds", kf.get("timestamp", 0.0)))),
            thumbnail_url=kf.get("frame_url", kf.get("url", kf.get("thumbnail_url"))),
            description=kf.get("description"),
            damage_detected=kf.get("damage_detected", False),
            damage_areas=kf.get("damage_areas", []),
            confidence=kf.get("confidence", 0.8),
        )
        for kf in keyframes
    ]
    
    return KeyframesListResponse(
        media_id=media_id,
        duration=video_duration,
        keyframes=items,
        total_keyframes=len(items),
    )


@router.get("/{claim_id}/media/{media_id}/damage-areas", response_model=List[DamageAreaResponse])
async def get_media_damage_areas(claim_id: str, media_id: str) -> List[DamageAreaResponse]:
    """
    Get detected damage areas from an image or video frame.
    
    Falls back to file-based storage if database has no data.
    """
    claim_id = _canonical_claim_id(claim_id)
    damage_areas = None
    
    # Try database first (if available)
    try:
        settings = load_settings()
        repository = ClaimsMediaRepository(settings)
        damage_areas = await repository.get_damage_areas(claim_id, media_id)
    except Exception as db_error:
        logger.debug(f"Database access failed for damage areas {claim_id}, using fallback: {db_error}")
    
    # Fallback to file-based storage
    if damage_areas is None:
        damage_areas = _get_damage_areas_from_files(claim_id, media_id)
    
    return [
        DamageAreaResponse(
            area_id=da.get("area_id", str(uuid.uuid4())),
            location=da.get("location", "Unknown"),
            severity=da.get("severity", "moderate"),
            confidence=da.get("confidence", 0.85),
            bounding_box=da.get("bounding_box"),
            source_media_id=media_id,
        )
        for da in damage_areas
    ]


@router.get("/{claim_id}/damage-summary", response_model=List[DamageAreaResponse])
async def get_claim_damage_summary(claim_id: str) -> List[DamageAreaResponse]:
    """
    Get aggregated damage summary across all media for a claim.
    """
    claim_id = _canonical_claim_id(claim_id)
    settings = load_settings()
    repository = ClaimsMediaRepository(settings)
    
    try:
        # Get all damage areas from all media
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT da.*, cm.media_id
                FROM workbenchiq.damage_areas da
                JOIN workbenchiq.claim_media cm ON da.media_id = cm.id
                WHERE cm.claim_id = $1
                ORDER BY da.confidence DESC
                """,
                claim_id,
            )
        
        return [
            DamageAreaResponse(
                area_id=str(row["id"]),
                location=row["location"],
                severity=row["severity"],
                confidence=row["confidence"],
                bounding_box=row.get("bounding_box"),
                source_media_id=str(row["media_id"]),
            )
            for row in rows
        ]
    except Exception as e:
        logger.error(f"Failed to get damage summary: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve damage summary")


# ============================================================================
# Habitation Claims Enhanced Analysis
# ============================================================================

class HabitationAnalysisResponse(BaseModel):
    """Enhanced habitation claim analysis with alerts, timeline, and responsibility."""
    
    class DossierInfoResponse(BaseModel):
        """Dossier identification information"""
        claim_id: str
        customer_name: Optional[str] = None
        claim_date: Optional[str] = None  # DD/MM/YYYY or ISO format
        claim_type: str  # "Tempête", "Inondation", "Dégâts des eaux", etc.
        policy_number: Optional[str] = None
        location: Optional[str] = None
    
    class AlertSignalResponse(BaseModel):
        signal_type: str  # "tempête", "inondation", "grêle", "neige", "other"
        level: str  # "high", "medium", "low"
        description: str
        evidence: str  # Text from document supporting this signal
        policy_ref: Optional[str] = None  # Policy section reference
    
    class TimelineEventResponse(BaseModel):
        event_type: str  # "notification", "damage_report", "assessment", "expert_visit", "call"
        date: str  # ISO format or readable string
        description: str
        evidence: str  # Supporting text from document
        document_section: Optional[str] = None  # Where in document this was found
    
    class ResponsibilityResponse(BaseModel):
        is_covered: bool  # Whether claim is covered by policy
        confidence: float  # 0.0 to 1.0 confidence score
        policy_id: str  # Matching policy condition ID
        policy_name: str  # Human-readable policy name
        reason: str  # Explanation of determination
        exceptions: Optional[List[str]] = None  # Any exceptions or caveats
        supporting_clauses: Optional[List[str]] = None  # Policy clauses supporting determination
    
    class PDFReferenceResponse(BaseModel):
        section_title: str  # Section name in PDF
        page_number: int
        page_offset: Optional[int] = None  # Offset within page
        indicator_text: str  # Text that led to reference
        context: Optional[str] = None  # Surrounding context
    
    class DamageImageAnalysisResponse(BaseModel):
        image_count: int  # Number of damage photos analyzed
        images: List[Dict[str, Any]] = []  # List of analyzed images
        # Each image: {"filename": str, "description": str, "detected_damage": str, 
        #             "validation_status": str, "matches_description": bool, "notes": str}
        overall_assessment: str  # Summary of damage photos analysis
        validation_against_description: str  # How images match written description
    
    information_dossier: Dict[str, str]  # Policy holder info with proper French labels
    dommages_constates: Dict[str, Any]  # Damage details with proper French labels
    dossier_info: DossierInfoResponse  # Claim file identification
    claim_id: str
    alert_signals: List[AlertSignalResponse]
    timeline: List[TimelineEventResponse]
    responsibility_evaluation: Optional[ResponsibilityResponse]
    analyse_images: Optional[DamageImageAnalysisResponse]  # Mistral vision analysis
    policy_links: List[PDFReferenceResponse]
    data_quality: dict  # {"field_name": confidence_score, ...}
    analysis_timestamp: str


def _field_label_mapping() -> Dict[str, str]:
    """Map CamelCase field names to proper French labels"""
    return {
        "AssuréNom": "Nom de l'assuré",
        "AssuréPrenom": "Prénom de l'assuré",
        "EmailAssure": "Email de l'assuré",
        "TelephoneAssure": "Téléphone de l'assuré",
        "AdresseAssure": "Adresse de l'assuré",
        "NumeroContrat": "Numéro de contrat",
        "NumeroPolice": "Numéro de police",
        "NumeroSociétaire": "Numéro sociétaire",
        "FormuleContrat": "Formule de contrat",
        "DateSinistre": "Date du sinistre",
        "NatureSinistre": "Nature du sinistre",
        "LieuSinistre": "Lieu du sinistre",
        "DescriptionSinistre": "Description du sinistre",
        "MontantEstime": "Montant estimé",
        "DateConstat": "Date de constat",
        "ExpertNom": "Nom de l'expert",
        "ExpertContact": "Contact expert",
    }


def _extract_field_value(fields_dict: dict, field_name: str) -> Optional[str]:
    """Extract value from extracted fields, handling both dict and string formats"""
    field = fields_dict.get(field_name)
    if not field:
        return None
    # If it's a dict with 'value' key (from CU API)
    if isinstance(field, dict):
        return field.get("value")
    # If it's a string
    if isinstance(field, str):
        return field if field.strip() else None
    return None


def _organize_fields_by_category(extracted_fields: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Organize extracted fields into logical categories"""
    label_map = _field_label_mapping()
    
    # Define which fields go in each category
    dossier_fields = {
        "AssuréNom", "AssuréPrenom", "EmailAssure", "TelephoneAssure",
        "AdresseAssure", "NumeroContrat", "NumeroPolice", "NumeroSociétaire",
        "FormuleContrat"
    }
    
    dommages_fields = {
        "DateSinistre", "NatureSinistre", "LieuSinistre", "DescriptionSinistre",
        "MontantEstime", "DateConstat", "ExpertNom", "ExpertContact"
    }
    
    info_dossier = {}
    dommages_constates = {}
    
    for field_name in dossier_fields:
        value = _extract_field_value(extracted_fields, field_name)
        if value:
            label = label_map.get(field_name, field_name)
            info_dossier[label] = value
    
    for field_name in dommages_fields:
        value = _extract_field_value(extracted_fields, field_name)
        if value:
            label = label_map.get(field_name, field_name)
            dommages_constates[label] = value
    
    return {
        "information_dossier": info_dossier,
        "dommages_constates": dommages_constates,
    }


@router.get("/habitation/{claim_id}/analysis", response_model=HabitationAnalysisResponse)
async def get_habitation_claims_analysis(claim_id: str) -> dict:
    """
    Get enhanced habitation claims analysis including:
    - Information dossier (policy holder info, contract details)
    - Dommages constatés (damage details with proper field organization)
    - Alert signals (weather warnings, risk indicators)
    - Event chronology (timeline of facts, timestamps)
    - Responsibility evaluation (liability assessment per climate events)
    - Analyse images (Mistral vision analysis of damage photos)
    - PDF source references (indexed links to policy documents)
    
    This endpoint analyzes habitation claims against the brand's policy conditions
    and extracts comprehensive claim analysis with full traceability to source
    documents and policy sections.
    
    Args:
        claim_id: The application/claim ID
    
    Returns:
        Enhanced analysis with properly organized fields, alert signals, timeline,
        responsibility evaluation, image analysis, and PDF references
    
    Raises:
        404: Claim not found
        400: Claim is not a habitation_claims persona
    """
    settings = load_settings()
    
    claim_id = _canonical_claim_id(claim_id)
    # Load application metadata
    app_md = load_application(settings.app.storage_root, claim_id)
    if not app_md:
        raise HTTPException(
            status_code=404,
            detail=f"Claim {claim_id} not found"
        )
    
    # Verify this is a habitation claim
    if app_md.persona != "habitation_claims":
        raise HTTPException(
            status_code=400,
            detail=f"Enhanced analysis only available for habitation claims, got {app_md.persona}"
        )
    
    # Get extracted fields and document markdown
    extracted_fields = app_md.extracted_fields or {}
    document_markdown = app_md.document_markdown or ""
    
    if not document_markdown:
        raise HTTPException(
            status_code=400,
            detail="No document content available for analysis"
        )
    
    try:
        # Run enhanced analysis
        analyzer = HabitationClaimsAnalyzer()
        analysis = analyzer.analyze(
            claim_id=claim_id,
            extracted_fields=extracted_fields,
            document_markdown=document_markdown,
            persona_config=None,
        )
        
        # Format alert signals
        alert_signals = [
            {
                "signal_type": signal.signal_type,
                "level": signal.level.value if hasattr(signal.level, 'value') else str(signal.level),
                "description": signal.description,
                "evidence": signal.evidence,
                "policy_ref": signal.policy_ref,
            }
            for signal in analysis.alert_signals
        ]
        
        # Format timeline events
        timeline_events = [
            {
                "event_type": event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type),
                "date": event.date,
                "description": event.description,
                "evidence": event.evidence,
                "document_section": event.document_section,
            }
            for event in analysis.timeline
        ]
        
        # Format responsibility evaluation
        responsibility = None
        if analysis.responsibility_evaluation:
            resp = analysis.responsibility_evaluation
            responsibility = {
                "is_covered": resp.is_covered,
                "confidence": resp.confidence,
                "policy_id": resp.policy_id,
                "policy_name": resp.policy_name,
                "reason": resp.reason,
                "exceptions": resp.exceptions,
                "supporting_clauses": resp.supporting_clauses,
            }
        
        # Format PDF references
        pdf_references = [
            {
                "section_title": ref.section_title,
                "page_number": ref.page_number,
                "page_offset": ref.page_offset,
                "indicator_text": ref.indicator_text,
                "context": ref.context,
            }
            for ref in analysis.policy_links
        ]
        
        # Format data quality scores
        data_quality = {k: float(v) for k, v in analysis.extracted_data_quality.items()} if analysis.extracted_data_quality else {}
        
        # Extract dossier identification information
        customer_name = _extract_field_value(extracted_fields, "AssuréNom")
        claim_date = _extract_field_value(extracted_fields, "DateSinistre")
        claim_type = _extract_field_value(extracted_fields, "NatureSinistre")
        policy_number = _extract_field_value(extracted_fields, "NumeroPolice")
        location = _extract_field_value(extracted_fields, "LieuSinistre")
        
        dossier_info = {
            "claim_id": claim_id,
            "customer_name": customer_name,
            "claim_date": claim_date,
            "claim_type": claim_type or "Habitation",
            "policy_number": policy_number,
            "location": location,
        }
        
        # Organize fields into proper categories with French labels
        organized_fields = _organize_fields_by_category(extracted_fields)
        
        # Image analysis using Mistral (placeholder for future multimodal integration)
        image_analysis = None
        if app_md.documents:
            image_files = [d for d in app_md.documents if d.get("doc_type") == "damage_photo"]
            if image_files:
                image_analysis = {
                    "image_count": len(image_files),
                    "images": [
                        {
                            "filename": f.get("filename", f"unknown_{i}"),
                            "description": "Photos de dommages - à analyser avec Mistral",
                            "detected_damage": "En attente d'analyse Mistral vision",
                            "validation_status": "pending",
                            "matches_description": None,
                            "notes": f"Lien Mistral: Validation des photos vs description écrite ({claim_type})"
                        }
                        for i, f in enumerate(image_files)
                    ],
                    "overall_assessment": f"Nombre de photos: {len(image_files)} - À valider via Mistral vision API",
                    "validation_against_description": f"À comparer avec: {claim_type or 'description du sinistre'}"
                }
        
        # Return formatted response
        return {
            "information_dossier": organized_fields.get("information_dossier", {}),
            "dommages_constates": organized_fields.get("dommages_constates", {}),
            "dossier_info": dossier_info,
            "claim_id": claim_id,
            "alert_signals": alert_signals,
            "timeline": timeline_events,
            "responsibility_evaluation": responsibility,
            "analyse_images": image_analysis,
            "policy_links": pdf_references,
            "data_quality": data_quality,
            "analysis_timestamp": datetime.now(UTC).isoformat(),
        }
    
    except Exception as e:
        logger.error(f"Habitation claim analysis failed for {claim_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {str(e)}"
        )


# ============================================================================
# Fraud Detection Endpoint — 2-model pipeline (vision + reasoning)
# ============================================================================

class ImageFraudResult(BaseModel):
    """Result for a single image authenticity analysis."""
    filename: str
    authenticity_score: float = 0.0
    is_likely_authentic: bool = True
    manipulation_indicators: List[dict] = []
    filename_concordance: Optional[dict] = None
    error: Optional[str] = None


class DeclarationVerification(BaseModel):
    """Result of declaration vs photo cross-check."""
    overall_consistent: bool = True
    consistency_score: float = 0.0
    discrepancies: List[dict] = []
    visual_observations: Any = []


class FraudOverallAssessment(BaseModel):
    """Overall fraud risk assessment."""
    overall_fraud_risk: str = "LOW"  # LOW, MODERATE, HIGH
    risk_score: float = 0.0
    siu_referral_recommended: bool = False
    siu_referral_reason: Optional[str] = None
    attention_items: List[dict] = []
    fraud_indicators: List[dict] = []
    dossier_concordance: Optional[dict] = None
    summary: str = ""


class FraudAnalysisResponse(BaseModel):
    """Full fraud analysis response."""
    application_id: str
    image_analyses: List[ImageFraudResult] = []
    declaration_verification: Optional[DeclarationVerification] = None
    overall_assessment: Optional[FraudOverallAssessment] = None
    web_intelligence: Optional[dict] = None
    analysis_timestamp: str = ""


@router.get("/{claim_id}/fraud-analysis", response_model=FraudAnalysisResponse)
async def get_fraud_analysis(claim_id: str) -> FraudAnalysisResponse:
    """Get previously saved fraud analysis results for a claim."""
    from ..storage import load_application
    from ..agents.tools import _reconcile_fraud_assessment
    settings = load_settings()
    claim_id = _canonical_claim_id(claim_id)
    app_md = load_application(settings.app.storage_root, claim_id)
    if not app_md or not app_md.fraud_analysis:
        raise HTTPException(status_code=404, detail="No fraud analysis found for this claim.")
    # Heal cached results saved before deterministic reconciliation existed so the
    # UI never shows an incoherent verdict (red dot / "Authentique") or a 0% score.
    healed = _reconcile_fraud_assessment(app_md.fraud_analysis)
    return FraudAnalysisResponse(**healed)


@router.post("/{claim_id}/fraud-analysis", response_model=FraudAnalysisResponse)
async def run_fraud_analysis(
    claim_id: str,
    filename: Optional[str] = Query(None, description="Specific image to analyze"),
    declaration_text: Optional[str] = None,
    reasoning_effort: Optional[str] = Query("medium", description="Reasoning effort: low, medium, high"),
) -> FraudAnalysisResponse:
    """
    Run fraud analysis on claim images (parallel orchestrator pipeline).

    Branch A (vision model): Image description and manipulation detection.
    Branch B (context): App summary, customer history, policy search, Fabric stats.
    Merge (reasoning model): Cross-reference all branches for fraud assessment.
    """
    from ..agents.tools import analyze_image_fraud

    settings = load_settings()
    claim_id = _canonical_claim_id(claim_id)

    if not settings.fraud_detection.enabled:
        raise HTTPException(
            status_code=503,
            detail="Fraud detection is not enabled on this instance.",
        )

    # Validate reasoning_effort
    effort = reasoning_effort if reasoning_effort in ("low", "medium", "high") else "medium"

    try:
        raw_result = analyze_image_fraud(
            application_id=claim_id,
            filename=filename or "",
            declaration_text=declaration_text or "",
            reasoning_effort=effort,
        )
    except Exception as exc:
        logger.error("Fraud analysis failed for %s: %s", claim_id, exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Fraud analysis failed: {exc}")

    # Parse the JSON result from the tool
    try:
        result = json.loads(raw_result)
    except json.JSONDecodeError:
        return FraudAnalysisResponse(
            application_id=claim_id,
            overall_assessment=FraudOverallAssessment(
                summary=raw_result,
            ),
            analysis_timestamp=datetime.now(UTC).isoformat(),
        )

    # Build typed response
    images = []
    for img in result.get("image_analyses", []):
        # Sanitize error field — extract meaningful category from raw exceptions
        raw_error = img.get("error")
        if raw_error and isinstance(raw_error, str):
            lower_err = raw_error.lower()
            # Classify known error types into user-friendly messages
            if "content_filter" in lower_err or "contentfilter" in lower_err or "responsibleai" in lower_err:
                raw_error = "Image rejetée par le filtre de contenu Azure"
            elif "404" in lower_err or "not_found" in lower_err or "deploymentnotfound" in lower_err:
                raw_error = "Déploiement vision introuvable — vérifier FRAUD_VISION_DEPLOYMENT"
            elif "429" in lower_err or "rate_limit" in lower_err or "ratelimit" in lower_err or "throttl" in lower_err:
                raw_error = "Limite de débit atteinte — réessayer dans quelques instants"
            elif "timeout" in lower_err or "timed out" in lower_err:
                raw_error = "Délai d'attente dépassé pour l'analyse"
            elif "401" in lower_err or "unauthorized" in lower_err or "authentication" in lower_err:
                raw_error = "Erreur d'authentification Azure OpenAI"
            else:
                stripped = raw_error.strip()
                if (stripped.startswith("'") or stripped.startswith('"')
                        or "\n" in stripped[:30] or stripped.startswith("{")):
                    # Log the actual error for debugging, show generic message
                    logger.warning("Image analysis raw error for %s: %s", img.get("filename", "?"), raw_error[:200])
                    raw_error = "Erreur d'analyse de l'image"
        # If parse_error flag is set but no explicit error, set generic error
        if not raw_error and img.get("parse_error"):
            raw_error = "Erreur d'analyse — résultat non structuré"

        # Extract authenticity_score robustly (could be float or str)
        score_raw = img.get("authenticity_score", 0.0)
        try:
            score = float(score_raw) if score_raw is not None else 0.0
        except (ValueError, TypeError):
            score = 0.0

        images.append(ImageFraudResult(
            filename=img.get("filename", "unknown"),
            authenticity_score=score,
            is_likely_authentic=img.get("is_likely_authentic", True),
            manipulation_indicators=img.get("manipulation_indicators", []),
            filename_concordance=img.get("filename_concordance"),
            error=raw_error,
        ))

    decl = result.get("declaration_verification", {})
    declaration = None
    if decl and not decl.get("parse_error"):
        decl_match = decl.get("declaration_match", decl)
        declaration = DeclarationVerification(
            overall_consistent=decl_match.get("overall_consistent", True),
            consistency_score=decl_match.get("consistency_score", 0.0),
            discrepancies=decl_match.get("discrepancies", []),
            visual_observations=decl.get("visual_observations", []),
        )

    overall_data = result.get("overall_assessment", {})
    overall = FraudOverallAssessment(
        overall_fraud_risk=overall_data.get("overall_fraud_risk", "LOW"),
        risk_score=overall_data.get("risk_score", 0.0),
        siu_referral_recommended=overall_data.get("siu_referral_recommended", False),
        siu_referral_reason=overall_data.get("siu_referral_reason"),
        attention_items=overall_data.get("attention_items", []),
        fraud_indicators=overall_data.get("fraud_indicators", []),
        dossier_concordance=overall_data.get("dossier_concordance"),
        summary=overall_data.get("summary", ""),
    ) if overall_data else None

    response = FraudAnalysisResponse(
        application_id=claim_id,
        image_analyses=images,
        declaration_verification=declaration,
        overall_assessment=overall,
        web_intelligence=result.get("web_intelligence"),
        analysis_timestamp=datetime.now(UTC).isoformat(),
    )

    # Persist results to application metadata so they survive page reloads
    try:
        from ..storage import load_application, save_application_metadata
        app_md = load_application(settings.app.storage_root, claim_id)
        if app_md:
            app_md.fraud_analysis = response.model_dump()
            # Regenerate context labels + tasks with fraud data
            from ..processing import generate_context_labels, generate_context_tasks
            app_md.context_labels = generate_context_labels(app_md)
            app_md.context_tasks = generate_context_tasks(app_md)
            save_application_metadata(settings.app.storage_root, app_md)
    except Exception as exc:
        logger.warning("Failed to persist fraud analysis for %s: %s", claim_id, exc)

    return response
