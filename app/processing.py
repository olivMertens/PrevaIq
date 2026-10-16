from __future__ import annotations

import asyncio
import base64
import json
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

from .brands import DEFAULT_BRAND
from .config import Settings
from .content_understanding_client import (
    analyze_document,
    analyze_image,
    analyze_video,
    extract_markdown_from_result,
    extract_fields_with_confidence,
    get_confidence_summary,
)
from .composite_documents import CompositeDocumentError, profile_pdf
from .large_document_processor import (
    detect_processing_mode,
    build_condensed_context,
    get_document_stats,
)
from .file_capabilities import detect_media_type
from .markitdown_service import (
    MarkItDownConversionError,
    convert_bytes_to_markdown,
    is_markitdown_preferred,
)
from .mistral_ocr_client import MistralOCRError, extract_with_mistral
from .openai_client import chat_completion
from .orchestration import StageBudget, assess_analysis, assess_extraction, record_stage
from .prompts import load_prompts
from .storage import (
    ApplicationMetadata,
    save_application_metadata,
    save_cu_raw_result,
    load_file_content,
    sanitize_extracted_fields,
)
from .personas import get_persona_config
from .utils import setup_logging
from .underwriting_policies import format_all_policies_for_prompt, format_policies_for_persona
from .glossary import format_glossary_for_prompt

logger = setup_logging()

_LLM_FALLBACK_FIELD_SOURCES = {"llm_fallback", "llm_markdown_fallback"}


def _score_extraction_quality(
    *,
    markdown_length: int,
    page_count: int,
    field_count: int = 0,
    had_error: bool = False,
) -> float:
    """Return a small comparable quality score for extraction candidates."""
    if markdown_length <= 0 and page_count <= 0 and field_count <= 0:
        return 0.0

    text_score = min(markdown_length / 1500, 1.0) * 45
    page_score = min(page_count / 3, 1.0) * 25
    field_score = min(field_count / 5, 1.0) * 20
    reliability_score = 0 if had_error else 10
    return round(text_score + page_score + field_score + reliability_score, 2)


def _should_try_mistral_for_quality(
    settings: Settings,
    *,
    media_type: str,
    field_count: int,
    content_length: int,
    page_count: int,
) -> bool:
    """Detect document outputs weak enough to justify the Mistral OCR fallback."""
    if not settings.mistral.enabled or media_type != "document":
        return False
    if page_count == 0:
        return True
    if field_count == 0 and content_length < 500:
        return True
    return False


def _try_mistral_document_fallback(
    settings: Settings,
    *,
    file_content: bytes,
    filename: str,
    fallback_from: Optional[str],
    reason: str,
) -> Optional[Dict[str, Any]]:
    """Run Mistral Document AI v25.12 as a document OCR fallback."""
    if not settings.mistral.enabled:
        logger.info("Mistral fallback skipped for %s: MISTRAL_ENABLED is false", filename)
        return None

    logger.info(
        "Trying Mistral fallback for %s (from=%s reason=%s deployment=%s)",
        filename,
        fallback_from or "<none>",
        reason,
        settings.mistral.deployment,
    )
    try:
        result = asyncio.run(
            extract_with_mistral(
                file_bytes=file_content,
                filename=filename,
                settings=settings.mistral,
                media_type="document",
                include_images=False,
                max_retries=2,
                retry_backoff=1.5,
            )
        )
    except MistralOCRError as exc:
        logger.error("Mistral fallback failed for %s: %s", filename, exc)
        return None
    except Exception as exc:
        logger.error("Unexpected Mistral fallback failure for %s: %s", filename, exc)
        return None

    pages = result.get("pages") or []
    markdown = result.get("markdown") or "\n\n".join(
        p.get("markdown", "") for p in pages if isinstance(p, dict)
    )
    if not markdown.strip() and not pages:
        logger.warning("Mistral fallback produced no usable content for %s", filename)
        return None

    page_count = len(pages) or 1
    quality_score = _score_extraction_quality(
        markdown_length=len(markdown),
        page_count=page_count,
        had_error=False,
    )
    return {
        "backend": "mistral-document-ai-25.12",
        "analyzer_id": settings.mistral.deployment,
        "fallback_from": fallback_from,
        "fallback_reason": reason,
        "pages": pages or [{"page_number": 1, "markdown": markdown}],
        "markdown": markdown,
        "page_count": page_count,
        "content_length": len(markdown),
        "quality_score": quality_score,
        "usage": result.get("usage") or {},
    }


def _append_mistral_result(
    *,
    stored_filename: str,
    mistral_result: Dict[str, Any],
    page_counter: int,
    all_pages: List[Dict[str, Any]],
    all_markdown_parts: List[str],
) -> int:
    """Append normalized Mistral pages and return the updated global page counter."""
    for page in mistral_result["pages"]:
        page_counter += 1
        source_page_number = page.get("page_number") or page.get("pageIndex") or page_counter
        prefix = f"# File: {stored_filename} – Page {source_page_number}\n\n"
        page_markdown = page.get("markdown", "")
        all_pages.append(
            {
                **page,
                "file": stored_filename,
                "page_number": page_counter,
                "source_page_number": source_page_number,
                "markdown": prefix + page_markdown,
                "extraction_backend": mistral_result["backend"],
                "analyzer_id": mistral_result["analyzer_id"],
            }
        )
        all_markdown_parts.append(prefix + page_markdown)
    return page_counter


def _build_confidence_summary_from_fields(
    all_fields: Dict[str, Any],
) -> tuple[Optional[Dict[str, Any]], Optional[float]]:
    """Build backend confidence summary and UI-safe average confidence."""
    if not all_fields:
        return None, None

    from .content_understanding_client import FieldConfidence

    field_objects = {}
    trusted_confidence_values = []
    for key, field_data in all_fields.items():
        raw_confidence = field_data.get("confidence", 0.0)
        confidence = raw_confidence if isinstance(raw_confidence, (int, float)) else 0.0
        source = field_data.get("source")
        if confidence > 0 and source not in _LLM_FALLBACK_FIELD_SOURCES:
            trusted_confidence_values.append(confidence)
        field_objects[key] = FieldConfidence(
            field_name=field_data["field_name"],
            value=field_data["value"],
            confidence=confidence,
            page_number=field_data.get("page_number"),
            bounding_box=field_data.get("bounding_box"),
            source_text=field_data.get("source_text"),
        )

    confidence_summary = get_confidence_summary(field_objects)
    average_confidence = (
        confidence_summary.get("average_confidence") if trusted_confidence_values else None
    )
    return confidence_summary, average_confidence


def _summarize_extraction_engines(
    file_provenance: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Summarize selected and attempted extraction engines for UI provenance."""
    selected_engines = [
        item.get("extraction_backend")
        for item in file_provenance
        if item.get("extraction_backend")
        and item.get("extraction_backend") != "llm-markdown-fallback"
    ]
    unique_selected = list(dict.fromkeys(selected_engines))
    attempted = []
    for item in file_provenance:
        for engine in item.get("attempted_engines") or []:
            if engine not in attempted:
                attempted.append(engine)
        backend = item.get("extraction_backend")
        if backend and backend not in attempted:
            attempted.append(backend)

    fallback_reasons = [
        item.get("fallback_reason") for item in file_provenance if item.get("fallback_reason")
    ]
    quality_scores = {
        item["file"]: item.get("quality_score")
        for item in file_provenance
        if item.get("file") and item.get("quality_score") is not None
    }
    return {
        "selected_engine": (
            unique_selected[0]
            if len(unique_selected) == 1
            else ("mixed" if unique_selected else None)
        ),
        "attempted_engines": attempted,
        "fallback_used": any(item.get("fallback_from") for item in file_provenance),
        "fallback_reason": fallback_reasons[0] if fallback_reasons else None,
        "quality_scores": quality_scores,
    }


def load_policies(prompts_root: str, persona: str = None) -> Dict[str, Any]:
    """Load plan benefit definitions for claims processing.

    For claims personas, loads from the unified claims policy file which
    contains both plan_benefits and processing policies.

    Args:
        prompts_root: Path to the prompts directory
        persona: Optional persona to load persona-specific plan benefits

    Returns:
        Dictionary of plan benefit definitions (plan_name -> plan_data)
    """
    try:
        # For life_health_claims, load from the unified policy file
        if persona == "life_health_claims":
            policy_path = os.path.join(prompts_root, "life-health-claims-policies.json")
            if os.path.exists(policy_path):
                with open(policy_path, "r") as f:
                    data = json.load(f)
                    # Return plan_benefits section from unified file
                    return data.get("plan_benefits", {})

        # Fallback: try legacy policies.json (will be removed)
        policy_path = os.path.join(prompts_root, "policies.json")
        if os.path.exists(policy_path):
            with open(policy_path, "r") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load policies: {e}")
    return {}


def load_underwriting_policies(prompts_root: str) -> str:
    """Load and format underwriting policies for prompt injection.

    Returns a formatted string of all underwriting policies suitable
    for injection into LLM prompts.

    Args:
        prompts_root: Path to the prompts directory containing underwriting policies
    """
    try:
        return format_all_policies_for_prompt(prompts_root)
    except Exception as e:
        logger.warning(f"Failed to load underwriting policies: {e}")
        return ""


def load_policies_for_persona_prompts(
    prompts_root: str, persona: str, brand: str = DEFAULT_BRAND.brand_name
) -> str:
    """Load and format persona-specific policies for prompt injection.

    For claims personas, this loads claims processing rules.
    For underwriting persona, this loads underwriting policies.

    Args:
        prompts_root: Path to the prompts directory
        persona: The persona type (underwriting, life_health_claims, etc.)
        brand: Brand name for substitution in policy templates

    Returns:
        Formatted string of policies suitable for prompt injection
    """
    try:
        return format_policies_for_persona(prompts_root, persona, brand=brand)
    except Exception as e:
        logger.warning(f"Failed to load {persona} policies: {e}")
        return ""


def load_glossary_for_prompt(prompts_root: str, persona: str, max_terms: int = 100) -> str:
    """Load and format persona-specific glossary for prompt injection.

    This provides domain terminology reference to the LLM to help it
    understand medical abbreviations, financial terms, and industry jargon.

    Args:
        prompts_root: Path to the prompts directory
        persona: The persona type (underwriting, life_health_claims, etc.)
        max_terms: Maximum number of terms to include

    Returns:
        Formatted string of glossary terms suitable for prompt injection
    """
    try:
        glossary_text = format_glossary_for_prompt(
            prompts_root, persona, max_terms=max_terms, format_type="markdown"
        )
        if glossary_text:
            logger.info("Loaded glossary for %s: %d chars", persona, len(glossary_text))
        return glossary_text
    except Exception as e:
        logger.warning(f"Failed to load glossary for {persona}: {e}")
        return ""


def run_content_understanding_for_files(
    settings: Settings,
    app_md: ApplicationMetadata,
    use_confidence_scoring: bool = True,
    language: Optional[str] = None,
) -> ApplicationMetadata:
    """Run Content Understanding for each uploaded file and aggregate results.

    For automotive_claims persona, routes files to appropriate analyzers:
    - Documents (.pdf, .docx) → autoClaimsDocAnalyzer
    - Images (.jpg, .png) → autoClaimsImageAnalyzer
    - Videos (.mp4, .mov) → autoClaimsVideoAnalyzer

    Other personas use the document analyzer for all files.

    Args:
        settings: Application settings
        app_md: Application metadata with uploaded files
        use_confidence_scoring: Whether to use custom analyzer with confidence scores

    Returns:
        Updated ApplicationMetadata with extracted content and confidence data
    """
    all_pages: List[Dict[str, Any]] = []
    all_markdown_parts: List[str] = []
    cu_payloads: List[Tuple[str, Dict[str, Any]]] = []
    all_fields: Dict[str, Any] = {}
    file_provenance: List[Dict[str, Any]] = []
    composite_segments: List[Dict[str, Any]] = []
    composite_conflicts: List[Dict[str, Any]] = []
    composite_review_required = False
    analyzer_used = None
    page_counter = 0  # running counter for unique page numbers across all files
    budget = StageBudget.for_extraction(settings.processing)

    # Get persona-specific analyzer IDs
    # Default to prebuilt-layout (always available, no model deployment needed)
    doc_analyzer_id = settings.content_understanding.analyzer_id  # prebuilt-layout
    image_analyzer_id = None
    video_analyzer_id = None
    is_multimodal_persona = False

    if app_md.persona:
        try:
            persona_config = get_persona_config(app_md.persona)
            # Use persona-specific custom analyzer if configured
            custom_id = persona_config.custom_analyzer_id
            if custom_id:
                doc_analyzer_id = custom_id
            image_analyzer_id = getattr(persona_config, "image_analyzer_id", None)
            video_analyzer_id = getattr(persona_config, "video_analyzer_id", None)
            is_multimodal_persona = image_analyzer_id is not None or video_analyzer_id is not None
            logger.info(
                "Persona %s analyzers - doc: %s, image: %s, video: %s",
                app_md.persona,
                doc_analyzer_id,
                image_analyzer_id,
                video_analyzer_id,
            )
        except ValueError as e:
            logger.warning(
                "Failed to get persona config for %s: %s. Using default analyzer.",
                app_md.persona,
                e,
            )

    # Custom CU analyzers using prebuilt-document base are broken on the GA API
    # 2025-11-01 (swedencentral, AIServices S0) — they return InternalServerError.
    # Skip them to avoid wasting a failed CU round-trip before the prebuilt-layout
    # fallback. When Azure fixes prebuilt-document custom analyzers, remove this.
    # Note: prebuilt-image based analyzers (habitationClaimsImageAnalyzer) DO work.
    _BROKEN_ANALYZERS = {
        "healthUnderwritingAnalyzer",
        "lifeHealthClaimsAnalyzer",
        "habitationClaimsAnalyzer",
        "autoClaimsDocAnalyzer",
    }
    if doc_analyzer_id in _BROKEN_ANALYZERS:
        logger.info(
            "Skipping broken custom analyzer %s — using prebuilt-layout directly",
            doc_analyzer_id,
        )
        doc_analyzer_id = "prebuilt-layout"

    # Enable image processing for all personas using prebuilt analyzer as fallback
    if not image_analyzer_id:
        image_analyzer_id = "prebuilt-image"
    is_multimodal_persona = True  # All personas can now process images

    for idx, stored in enumerate(app_md.files):
        # Skip files already extracted (incremental processing) — but only when
        # we still hold the extracted content. If a prior run lost the markdown
        # (e.g. an empty re-extraction that the preserve-guard kept, or a clobber
        # from before that guard existed), the `extracted` flag would otherwise
        # trap the dossier in a permanently-empty state. Re-extract in that case.
        already_extracted = getattr(stored, "extracted", False)
        has_existing_content = bool(app_md.document_markdown) or bool(app_md.markdown_pages)
        if already_extracted and has_existing_content:
            logger.info("Skipping already-extracted file: %s", stored.filename)
            continue
        if already_extracted and not has_existing_content:
            logger.warning(
                "Re-extracting %s: marked extracted but dossier has no stored "
                "content (recovering from lost extraction)",
                stored.filename,
            )
        if budget.time_exhausted():
            # Left un-extracted so a later run can resume it; flagged for review.
            logger.warning("Extraction budget exhausted — skipping %s", stored.filename)
            budget.skipped.append(stored.filename)
            continue

        logger.info(
            "Analyzing file with Content Understanding: %s (%d/%d)",
            stored.filename,
            idx + 1,
            len(app_md.files),
        )

        # Load file content from storage (supports both local and cloud storage)
        file_content = load_file_content(stored)
        if file_content is None:
            logger.error("Failed to load file content for: %s", stored.path)
            continue

        # Detect media type for multimodal routing
        media_type = detect_media_type(stored.filename)
        logger.info("File %s detected as media type: %s", stored.filename, media_type)
        if media_type == "document" and stored.filename.lower().endswith(".pdf"):
            try:
                composite_profile = profile_pdf(file_content, stored.filename)
                composite_segments.extend(composite_profile.provenance_segments())
                composite_review_required = (
                    composite_review_required or composite_profile.review_required
                )
            except CompositeDocumentError as exc:
                logger.warning("Composite PDF profiling skipped for %s: %s", stored.filename, exc)

        # Route to appropriate analyzer based on media type (for multimodal personas)
        if is_multimodal_persona and media_type == "image" and image_analyzer_id:
            # Process as image with image analyzer
            try:
                logger.info(
                    "[CU-CALL] file=%s media=image analyzer=%s size_kb=%.1f "
                    "completion=%s embedding=%s",
                    stored.filename,
                    image_analyzer_id,
                    len(file_content) / 1024,
                    settings.content_understanding.completion_deployment or "<default>",
                    settings.content_understanding.embedding_deployment or "<default>",
                )
                payload = analyze_image(
                    settings.content_understanding,
                    file_bytes=file_content,
                    analyzer_id=image_analyzer_id,
                )
                analyzer_used = image_analyzer_id

                # Extract image-specific fields
                image_field_count = 0
                if payload.get("result", {}).get("contents"):
                    for content in payload["result"]["contents"]:
                        if content.get("fields"):
                            for field_name, field_data in content["fields"].items():
                                image_field_count += 1
                                all_fields[f"{stored.filename}:{field_name}"] = {
                                    "field_name": field_name,
                                    "value": field_data.get("value")
                                    or field_data.get("valueString"),
                                    "confidence": field_data.get("confidence", 0.0),
                                    "source_file": stored.filename,
                                    "media_type": "image",
                                }

                # Extract markdown content from image analysis result
                extracted = extract_markdown_from_result(payload)
                image_md = extracted.get("document_markdown", "")

                # Build image summary — use CU markdown if available
                summary = f"# Image Analysis: {stored.filename}\n\n"
                if image_md:
                    summary += image_md + "\n\n"

                # Also extract automotive-specific damage fields if present
                first_content = payload.get("result", {}).get("contents", [{}])[0]
                fields = first_content.get("fields", {})
                severity = fields.get("OverallDamageSeverity", {})
                damage_areas = fields.get("DamageAreas", {})
                if severity.get("valueString"):
                    summary += f"**Overall Damage Severity:** {severity['valueString']}\n\n"
                if damage_areas.get("valueArray"):
                    summary += "**Detected Damage Areas:**\n"
                    for area in damage_areas["valueArray"]:
                        props = area.get("valueObject", {})
                        location = props.get("location", {}).get("valueString", "Unknown")
                        damage_type = props.get("damageType", {}).get("valueString", "Unknown")
                        sev = props.get("severity", {}).get("valueString", "Unknown")
                        summary += f"- {location}: {damage_type} ({sev})\n"

                all_markdown_parts.append(summary)
                page_counter += 1
                all_pages.append(
                    {"file": stored.filename, "page_number": page_counter, "markdown": summary}
                )
                cu_payloads.append((stored.path, payload))
                file_provenance.append(
                    {
                        "file": stored.filename,
                        "media_type": "image",
                        "extraction_backend": "content-understanding",
                        "analyzer_id": image_analyzer_id,
                        "field_count": image_field_count,
                        "page_count": 1,
                    }
                )

            except Exception as e:
                logger.error("Image analysis failed for %s: %s", stored.filename, e)
                image_recovered = False
                # First fallback: CU prebuilt-image (handles missing custom analyzers
                # without depending on the GPT-vision deployment).
                if image_analyzer_id != "prebuilt-image":
                    try:
                        logger.info("Falling back to prebuilt-image for %s", stored.filename)
                        payload = analyze_image(
                            settings.content_understanding,
                            file_bytes=file_content,
                            analyzer_id="prebuilt-image",
                        )
                        extracted = extract_markdown_from_result(payload)
                        image_md = extracted.get("document_markdown", "")
                        if image_md:
                            summary = f"# Image Analysis: {stored.filename}\n\n{image_md}\n\n"
                            all_markdown_parts.append(summary)
                            page_counter += 1
                            all_pages.append(
                                {
                                    "file": stored.filename,
                                    "page_number": page_counter,
                                    "markdown": summary,
                                }
                            )
                            analyzer_used = "prebuilt-image"
                            file_provenance.append(
                                {
                                    "file": stored.filename,
                                    "media_type": "image",
                                    "extraction_backend": "content-understanding",
                                    "analyzer_id": "prebuilt-image",
                                    "fallback_from": image_analyzer_id,
                                    "field_count": 0,
                                    "page_count": 1,
                                }
                            )
                            image_recovered = True
                            logger.info(
                                "prebuilt-image fallback produced %d chars for %s",
                                len(image_md),
                                stored.filename,
                            )
                    except Exception as e_pi:
                        logger.warning(
                            "prebuilt-image fallback failed for %s: %s", stored.filename, e_pi
                        )
                # Second fallback: GPT vision description.
                if not image_recovered:
                    logger.info("Falling back to GPT vision for %s", stored.filename)
                    try:
                        vision_md = _gpt_vision_describe_image(
                            settings,
                            file_content,
                            stored.filename,
                            persona=app_md.persona or "automotive_claims",
                            language=language,
                        )
                        if vision_md:
                            all_markdown_parts.append(vision_md)
                            page_counter += 1
                            all_pages.append(
                                {
                                    "file": stored.filename,
                                    "page_number": page_counter,
                                    "markdown": vision_md,
                                }
                            )
                            analyzer_used = f"{settings.openai.model_name}-vision-fallback"
                            file_provenance.append(
                                {
                                    "file": stored.filename,
                                    "media_type": "image",
                                    "extraction_backend": "gpt-vision-fallback",
                                    "analyzer_id": analyzer_used,
                                    "fallback_from": image_analyzer_id,
                                    "field_count": 0,
                                    "page_count": 1,
                                }
                            )
                            logger.info(
                                "GPT vision fallback produced %d chars for %s",
                                len(vision_md),
                                stored.filename,
                            )
                    except Exception as e2:
                        logger.error(
                            "GPT vision fallback also failed for %s: %s", stored.filename, e2
                        )

        elif is_multimodal_persona and media_type == "video" and video_analyzer_id:
            # Process as video with video analyzer
            try:
                logger.info(
                    "[CU-CALL] file=%s media=video analyzer=%s size_kb=%.1f",
                    stored.filename,
                    video_analyzer_id,
                    len(file_content) / 1024,
                )
                payload = analyze_video(
                    settings.content_understanding,
                    file_bytes=file_content,
                    analyzer_id=video_analyzer_id,
                )
                analyzer_used = video_analyzer_id

                # Extract video-specific fields
                video_field_count = 0
                if payload.get("result", {}).get("contents"):
                    for content in payload["result"]["contents"]:
                        if content.get("fields"):
                            for field_name, field_data in content["fields"].items():
                                video_field_count += 1
                                all_fields[f"{stored.filename}:{field_name}"] = {
                                    "field_name": field_name,
                                    "value": field_data.get("value")
                                    or field_data.get("valueString")
                                    or field_data.get("valueBoolean"),
                                    "confidence": field_data.get("confidence", 0.0),
                                    "source_file": stored.filename,
                                    "media_type": "video",
                                }

                # Add video summary to markdown
                incident = (
                    payload.get("result", {})
                    .get("contents", [{}])[0]
                    .get("fields", {})
                    .get("IncidentDetected", {})
                )
                incident_type = (
                    payload.get("result", {})
                    .get("contents", [{}])[0]
                    .get("fields", {})
                    .get("IncidentType", {})
                )
                timestamp = (
                    payload.get("result", {})
                    .get("contents", [{}])[0]
                    .get("fields", {})
                    .get("IncidentTimestamp", {})
                )
                summary = f"# Video Analysis: {stored.filename}\n\n"
                summary += f"**Incident Detected:** {incident.get('valueBoolean', 'Unknown')}\n"
                summary += f"**Incident Type:** {incident_type.get('valueString', 'Unknown')}\n"
                summary += f"**Timestamp:** {timestamp.get('valueString', 'Unknown')}\n"
                all_markdown_parts.append(summary)
                cu_payloads.append((stored.path, payload))
                file_provenance.append(
                    {
                        "file": stored.filename,
                        "media_type": "video",
                        "extraction_backend": "content-understanding",
                        "analyzer_id": video_analyzer_id,
                        "field_count": video_field_count,
                        "page_count": 1,
                    }
                )

            except Exception as e:
                logger.error("Video analysis failed for %s: %s", stored.filename, e)
                # Skip video if it fails (don't try document analyzer on video)
                continue
        else:
            # Process as document (default path)
            if is_markitdown_preferred(stored.filename, settings.markitdown):
                try:
                    md_result = convert_bytes_to_markdown(
                        file_content,
                        stored.filename,
                        settings.markitdown,
                        content_understanding_settings=settings.content_understanding,
                        analyzer_id=doc_analyzer_id
                        if settings.markitdown.use_content_understanding
                        else None,
                    )
                    analyzer_used = md_result.analyzer_id or md_result.backend
                    markitdown_fields = 0
                    clean_md_fields = sanitize_extracted_fields(md_result.fields) or {}
                    for field_name, value in clean_md_fields.items():
                        markitdown_fields += 1
                        all_fields[f"{stored.filename}:{field_name}"] = {
                            "field_name": field_name,
                            "value": value,
                            "confidence": 0.75,
                            "source_text": "MarkItDown YAML front matter",
                            "source_file": stored.filename,
                            "media_type": "document",
                            "source": "markitdown_front_matter",
                        }
                    for p in md_result.pages:
                        page_counter += 1
                        prefix = f"# File: {stored.filename} – Page {p['page_number']}\n\n"
                        all_pages.append(
                            {
                                **p,
                                "file": stored.filename,
                                "page_number": page_counter,
                                "source_page_number": p["page_number"],
                                "markdown": prefix + p["markdown"],
                            }
                        )
                        all_markdown_parts.append(prefix + p["markdown"])
                    file_provenance.append(
                        {
                            "file": stored.filename,
                            "media_type": "document",
                            "extraction_backend": md_result.backend,
                            "analyzer_id": md_result.analyzer_id,
                            "field_count": markitdown_fields,
                            "page_count": len(md_result.pages),
                            "content_length": len(md_result.markdown),
                            "quality_score": _score_extraction_quality(
                                markdown_length=len(md_result.markdown),
                                page_count=len(md_result.pages),
                                field_count=markitdown_fields,
                            ),
                            "attempted_engines": [md_result.backend],
                        }
                    )
                    continue
                except MarkItDownConversionError as e:
                    logger.warning(
                        "MarkItDown preferred conversion failed for %s, falling back to Content Understanding: %s",
                        stored.filename,
                        e,
                    )

            # Use prebuilt analyzer for reliable extraction (custom analyzers require explicit creation)
            document_field_count = 0
            fallback_from = None
            try:
                logger.info(
                    "[CU-CALL] file=%s media=document analyzer=%s size_kb=%.1f "
                    "completion=%s embedding=%s api_version=%s",
                    stored.filename,
                    doc_analyzer_id,
                    len(file_content) / 1024,
                    settings.content_understanding.completion_deployment or "<default>",
                    settings.content_understanding.embedding_deployment or "<default>",
                    settings.content_understanding.api_version,
                )
                payload = analyze_document(
                    settings.content_understanding,
                    file_path=stored.path,
                    file_bytes=file_content,
                    analyzer_id=doc_analyzer_id,
                )
                analyzer_used = doc_analyzer_id

                # Extract fields with confidence if available
                fields = extract_fields_with_confidence(payload)
                for field_name, field_conf in fields.items():
                    document_field_count += 1
                    all_fields[f"{stored.filename}:{field_name}"] = {
                        "field_name": field_conf.field_name,
                        "value": field_conf.value,
                        "confidence": field_conf.confidence,
                        "page_number": field_conf.page_number,
                        "bounding_box": field_conf.bounding_box,
                        "source_text": field_conf.source_text,
                        "source_file": stored.filename,
                        "media_type": "document",
                    }
            except Exception as e:
                logger.error(
                    "Document analysis failed for %s with analyzer %s: %s",
                    stored.filename,
                    doc_analyzer_id,
                    e,
                )
                # Fallback to prebuilt-layout if custom analyzer failed
                fallback_id = "prebuilt-layout"
                if doc_analyzer_id != fallback_id:
                    fallback_from = doc_analyzer_id
                    logger.info("Falling back to %s for %s", fallback_id, stored.filename)
                    try:
                        payload = analyze_document(
                            settings.content_understanding,
                            file_path=stored.path,
                            file_bytes=file_content,
                            analyzer_id=fallback_id,
                        )
                        analyzer_used = fallback_id
                        fields = extract_fields_with_confidence(payload)
                        for field_name, field_conf in fields.items():
                            document_field_count += 1
                            all_fields[f"{stored.filename}:{field_name}"] = {
                                "field_name": field_conf.field_name,
                                "value": field_conf.value,
                                "confidence": field_conf.confidence,
                                "page_number": field_conf.page_number,
                                "bounding_box": field_conf.bounding_box,
                                "source_text": field_conf.source_text,
                                "source_file": stored.filename,
                                "media_type": "document",
                            }
                    except Exception as e2:
                        logger.error(
                            "Document fallback also failed for %s: %s", stored.filename, e2
                        )
                        if settings.markitdown.enabled:
                            try:
                                md_result = convert_bytes_to_markdown(
                                    file_content,
                                    stored.filename,
                                    settings.markitdown,
                                    content_understanding_settings=settings.content_understanding,
                                    analyzer_id=None,
                                )
                                analyzer_used = md_result.backend
                                for p in md_result.pages:
                                    page_counter += 1
                                    prefix = (
                                        f"# File: {stored.filename} – Page {p['page_number']}\n\n"
                                    )
                                    all_pages.append(
                                        {
                                            **p,
                                            "file": stored.filename,
                                            "page_number": page_counter,
                                            "source_page_number": p["page_number"],
                                            "markdown": prefix + p["markdown"],
                                        }
                                    )
                                    all_markdown_parts.append(prefix + p["markdown"])
                                file_provenance.append(
                                    {
                                        "file": stored.filename,
                                        "media_type": "document",
                                        "extraction_backend": md_result.backend,
                                        "analyzer_id": md_result.analyzer_id,
                                        "fallback_from": fallback_from or doc_analyzer_id,
                                        "field_count": len(
                                            sanitize_extracted_fields(md_result.fields) or {}
                                        ),
                                        "page_count": len(md_result.pages),
                                        "content_length": len(md_result.markdown),
                                        "quality_score": _score_extraction_quality(
                                            markdown_length=len(md_result.markdown),
                                            page_count=len(md_result.pages),
                                            field_count=len(
                                                sanitize_extracted_fields(md_result.fields) or {}
                                            ),
                                        ),
                                        "attempted_engines": [
                                            doc_analyzer_id,
                                            fallback_id,
                                            md_result.backend,
                                        ],
                                    }
                                )
                                continue
                            except MarkItDownConversionError as e3:
                                logger.error(
                                    "MarkItDown fallback also failed for %s: %s",
                                    stored.filename,
                                    e3,
                                )
                    mistral_result = _try_mistral_document_fallback(
                        settings,
                        file_content=file_content,
                        filename=stored.filename,
                        fallback_from=fallback_from or doc_analyzer_id,
                        reason="cu_and_markitdown_failed",
                    )
                    if mistral_result:
                        analyzer_used = mistral_result["analyzer_id"]
                        page_counter = _append_mistral_result(
                            stored_filename=stored.filename,
                            mistral_result=mistral_result,
                            page_counter=page_counter,
                            all_pages=all_pages,
                            all_markdown_parts=all_markdown_parts,
                        )
                        file_provenance.append(
                            {
                                "file": stored.filename,
                                "media_type": "document",
                                "extraction_backend": mistral_result["backend"],
                                "analyzer_id": mistral_result["analyzer_id"],
                                "fallback_from": mistral_result["fallback_from"],
                                "fallback_reason": mistral_result["fallback_reason"],
                                "field_count": 0,
                                "page_count": mistral_result["page_count"],
                                "content_length": mistral_result["content_length"],
                                "quality_score": mistral_result["quality_score"],
                                "attempted_engines": [
                                    doc_analyzer_id,
                                    fallback_id,
                                    "markitdown",
                                    mistral_result["backend"],
                                ],
                            }
                        )
                        continue
                    continue
                else:
                    if settings.markitdown.enabled:
                        try:
                            md_result = convert_bytes_to_markdown(
                                file_content,
                                stored.filename,
                                settings.markitdown,
                                content_understanding_settings=settings.content_understanding,
                                analyzer_id=None,
                            )
                            analyzer_used = md_result.backend
                            for p in md_result.pages:
                                page_counter += 1
                                prefix = f"# File: {stored.filename} – Page {p['page_number']}\n\n"
                                all_pages.append(
                                    {
                                        **p,
                                        "file": stored.filename,
                                        "page_number": page_counter,
                                        "source_page_number": p["page_number"],
                                        "markdown": prefix + p["markdown"],
                                    }
                                )
                                all_markdown_parts.append(prefix + p["markdown"])
                            file_provenance.append(
                                {
                                    "file": stored.filename,
                                    "media_type": "document",
                                    "extraction_backend": md_result.backend,
                                    "analyzer_id": md_result.analyzer_id,
                                    "fallback_from": doc_analyzer_id,
                                    "field_count": len(
                                        sanitize_extracted_fields(md_result.fields) or {}
                                    ),
                                    "page_count": len(md_result.pages),
                                    "content_length": len(md_result.markdown),
                                    "quality_score": _score_extraction_quality(
                                        markdown_length=len(md_result.markdown),
                                        page_count=len(md_result.pages),
                                        field_count=len(
                                            sanitize_extracted_fields(md_result.fields) or {}
                                        ),
                                    ),
                                    "attempted_engines": [
                                        doc_analyzer_id,
                                        md_result.backend,
                                    ],
                                }
                            )
                            continue
                        except MarkItDownConversionError as e3:
                            logger.error(
                                "MarkItDown fallback also failed for %s: %s", stored.filename, e3
                            )
                    mistral_result = _try_mistral_document_fallback(
                        settings,
                        file_content=file_content,
                        filename=stored.filename,
                        fallback_from=doc_analyzer_id,
                        reason="cu_and_markitdown_failed",
                    )
                    if mistral_result:
                        analyzer_used = mistral_result["analyzer_id"]
                        page_counter = _append_mistral_result(
                            stored_filename=stored.filename,
                            mistral_result=mistral_result,
                            page_counter=page_counter,
                            all_pages=all_pages,
                            all_markdown_parts=all_markdown_parts,
                        )
                        file_provenance.append(
                            {
                                "file": stored.filename,
                                "media_type": "document",
                                "extraction_backend": mistral_result["backend"],
                                "analyzer_id": mistral_result["analyzer_id"],
                                "fallback_from": mistral_result["fallback_from"],
                                "fallback_reason": mistral_result["fallback_reason"],
                                "field_count": 0,
                                "page_count": mistral_result["page_count"],
                                "content_length": mistral_result["content_length"],
                                "quality_score": mistral_result["quality_score"],
                                "attempted_engines": [
                                    doc_analyzer_id,
                                    "markitdown",
                                    mistral_result["backend"],
                                ],
                            }
                        )
                        continue
                    continue

            cu_payloads.append((stored.path, payload))

            extracted = extract_markdown_from_result(payload)
            pages = extracted["pages"]
            content_length = sum(len(p.get("markdown", "")) for p in pages)
            cu_quality_score = _score_extraction_quality(
                markdown_length=content_length,
                page_count=len(pages),
                field_count=document_field_count,
            )
            selected_backend = "content-understanding"
            selected_analyzer = analyzer_used
            selected_pages = pages
            selected_quality_score = cu_quality_score
            selected_content_length = content_length
            selected_fallback_from = fallback_from
            selected_fallback_reason = None
            attempted_engines = ["content-understanding"]
            weak_output = _should_try_mistral_for_quality(
                settings,
                media_type="document",
                field_count=document_field_count,
                content_length=content_length,
                page_count=len(pages),
            )
            below_threshold = (
                settings.mistral.enabled
                and cu_quality_score < settings.processing.reextraction_quality_threshold
            )
            if (weak_output or below_threshold) and budget.can_reextract():
                budget.reextractions += 1
                mistral_result = _try_mistral_document_fallback(
                    settings,
                    file_content=file_content,
                    filename=stored.filename,
                    fallback_from=analyzer_used,
                    reason="low_quality_cu_output" if weak_output else "below_quality_threshold",
                )
                if mistral_result:
                    attempted_engines.append(mistral_result["backend"])
                    if mistral_result["quality_score"] > cu_quality_score:
                        selected_backend = mistral_result["backend"]
                        selected_analyzer = mistral_result["analyzer_id"]
                        selected_pages = mistral_result["pages"]
                        selected_quality_score = mistral_result["quality_score"]
                        selected_content_length = mistral_result["content_length"]
                        selected_fallback_from = analyzer_used
                        selected_fallback_reason = mistral_result["fallback_reason"]
                        analyzer_used = selected_analyzer

            # Prefix each page with filename so underwriters see the source.
            for p in selected_pages:
                page_counter += 1
                source_page_number = p.get("page_number") or p.get("pageIndex") or page_counter
                prefix = f"# File: {stored.filename} – Page {source_page_number}\n\n"
                page_markdown = p.get("markdown", "")
                all_pages.append(
                    {
                        "file": stored.filename,
                        "page_number": page_counter,
                        "source_page_number": source_page_number,
                        "markdown": prefix + page_markdown,
                        "extraction_backend": selected_backend,
                        "analyzer_id": selected_analyzer,
                    }
                )
                all_markdown_parts.append(prefix + page_markdown)
            file_provenance.append(
                {
                    "file": stored.filename,
                    "media_type": "document",
                    "extraction_backend": selected_backend,
                    "analyzer_id": selected_analyzer,
                    "fallback_from": selected_fallback_from,
                    "fallback_reason": selected_fallback_reason,
                    "field_count": document_field_count,
                    "page_count": len(selected_pages),
                    "content_length": selected_content_length,
                    "quality_score": selected_quality_score,
                    "attempted_engines": attempted_engines,
                }
            )

    combined_md = "\n\n---\n\n".join(all_markdown_parts)

    if not all_markdown_parts and not all_pages and app_md.document_markdown:
        combined_md = app_md.document_markdown
        all_pages = list(app_md.markdown_pages or [])
        analyzer_used = app_md.analyzer_id_used

    # Mark newly-processed files as extracted
    for stored in app_md.files:
        if not getattr(stored, "extracted", False):
            # If this file contributed fields, mark it extracted
            prefix = f"{stored.filename}:"
            if any(k.startswith(prefix) for k in all_fields) or stored.filename in [
                p.get("file") for p in all_pages
            ]:
                stored.extracted = True

    # Merge with existing extracted fields (incremental mode)
    all_fields = sanitize_extracted_fields(all_fields) or {}
    existing_fields = sanitize_extracted_fields(app_md.extracted_fields) or {}
    existing_fields.update(all_fields)
    all_fields = sanitize_extracted_fields(existing_fields) or {}

    # Merge markdown: prepend existing if we're doing incremental
    if app_md.markdown_pages and all_markdown_parts and all_pages:
        # Keep existing pages + append new
        existing_pages = app_md.markdown_pages or []
        all_pages = existing_pages + all_pages
        if app_md.document_markdown:
            combined_md = app_md.document_markdown + "\n\n---\n\n" + combined_md

    # LLM fallback: extract structured fields from markdown when CU analyzer
    # did not produce any (e.g. underwriting with generic prebuilt-documentSearch)
    if (
        not all_fields
        and combined_md
        and app_md.persona
        in (
            "underwriting",
            "habitation_claims",
            "life_health_claims",
            "lifeHealthClaims",
            "property_casualty_claims",
            "automotive_claims",
        )
    ):
        logger.info(
            "No extracted fields from CU — running LLM field extraction fallback for %s (persona=%s)",
            app_md.id,
            app_md.persona,
        )
        llm_fields = _llm_extract_fields(settings, combined_md, persona=app_md.persona)
        if llm_fields:
            all_fields = llm_fields
            file_provenance.append(
                {
                    "file": "consolidated-markdown",
                    "media_type": "document",
                    "extraction_backend": "llm-markdown-fallback",
                    "analyzer_id": settings.openai.chat_deployment_name
                    or settings.openai.deployment_name,
                    "fallback_from": analyzer_used,
                    "fallback_reason": "no_structured_fields_from_extraction",
                    "field_count": len(llm_fields),
                    "page_count": len(all_pages or []),
                    "content_length": len(combined_md),
                    "quality_score": _score_extraction_quality(
                        markdown_length=len(combined_md),
                        page_count=len(all_pages or []),
                        field_count=len(llm_fields),
                    ),
                    "attempted_engines": ["llm-markdown-fallback"],
                }
            )
            logger.info("LLM fallback extracted %d fields", len(llm_fields))

    # Save raw CU payload (for first file only) for debugging
    if cu_payloads:
        cu_path = save_cu_raw_result(settings.app.storage_root, app_md.id, cu_payloads[0][1])
    else:
        cu_path = app_md.cu_raw_result_path if not all_markdown_parts else None

    confidence_summary, provenance_average_confidence = _build_confidence_summary_from_fields(
        all_fields
    )
    if confidence_summary:
        average_for_log = confidence_summary.get("average_confidence") or 0.0
        logger.info(
            "Extracted %d fields with average confidence %.2f",
            confidence_summary["total_fields"],
            average_for_log,
        )

    # Guard: a transient empty re-extraction (e.g. CU/MarkItDown hiccup) must
    # not wipe a dossier that already has good markdown/fields. Only overwrite
    # when this run produced content, or when there is nothing to preserve.
    extraction_yielded_content = bool(combined_md) or bool(all_fields)
    preserve_previous = not extraction_yielded_content and bool(app_md.document_markdown)
    if preserve_previous:
        logger.warning(
            "Re-extraction for %s produced no content; preserving previous "
            "markdown (%d chars) and %d extracted fields",
            app_md.id,
            len(app_md.document_markdown or ""),
            len(app_md.extracted_fields or {}),
        )
    else:
        app_md.document_markdown = combined_md
        app_md.markdown_pages = all_pages
        app_md.cu_raw_result_path = cu_path
        app_md.extracted_fields = all_fields
        app_md.confidence_summary = confidence_summary
        app_md.analyzer_id_used = analyzer_used
    existing_provenance = app_md.extraction_provenance or {}
    existing_files = existing_provenance.get("files", [])
    all_file_provenance = existing_files + file_provenance
    existing_segments = existing_provenance.get("segments", [])
    all_segments = existing_segments + composite_segments
    existing_conflicts = existing_provenance.get("conflicts", [])
    engine_summary = _summarize_extraction_engines(all_file_provenance)
    processed_file_count = len(
        {
            item.get("file")
            for item in all_file_provenance
            if item.get("file") and item.get("file") != "consolidated-markdown"
        }
    )
    pipeline_parts = ["content-understanding", "markitdown", "gpt"]
    if "mistral-document-ai-25.12" in engine_summary["attempted_engines"]:
        pipeline_parts.insert(2, "mistral")
    review_required = (
        bool(existing_provenance.get("review_required"))
        or composite_review_required
        or any(segment.get("review_required") for segment in all_segments)
    )
    new_provenance = {
        "pipeline": "-".join(pipeline_parts),
        "content_understanding": {
            "api_version": settings.content_understanding.api_version,
            "default_analyzer_id": settings.content_understanding.analyzer_id,
            "completion_deployment": settings.content_understanding.completion_deployment,
            "embedding_deployment": settings.content_understanding.embedding_deployment,
        },
        "openai": {
            "deployment": settings.openai.deployment_name,
            "model": settings.openai.model_name,
            "api_version": settings.openai.api_version,
            "reasoning_effort": settings.openai.reasoning_effort,
        },
        "markitdown": {
            "enabled": settings.markitdown.enabled,
            "mode": settings.markitdown.mode,
            "use_content_understanding": settings.markitdown.use_content_understanding,
        },
        "summary": {
            "file_count": len(app_md.files or []),
            "processed_file_count": processed_file_count,
            "field_count": len(all_fields or {}),
            "average_confidence": provenance_average_confidence,
            "page_count": len(all_pages or []),
            "last_analyzer_id": analyzer_used,
            **engine_summary,
        },
        "files": all_file_provenance,
        "segments": all_segments,
        "conflicts": existing_conflicts + composite_conflicts,
        "review_required": review_required,
    }
    if not preserve_previous:
        app_md.extraction_provenance = new_provenance

    record_stage(
        app_md,
        budget,
        assess_extraction(
            budget=budget,
            file_provenance=all_file_provenance,
            confidence_summary=app_md.confidence_summary,
            has_content=bool(app_md.document_markdown) or bool(app_md.extracted_fields),
            composite_review_required=review_required,
            cfg=settings.processing,
        ),
    )
    app_md.status = "extracted"
    save_application_metadata(settings.app.storage_root, app_md)
    logger.info("Content Understanding completed for application %s", app_md.id)
    return app_md


def _llm_extract_fields(
    settings: Settings, markdown: str, persona: str = "underwriting"
) -> Dict[str, Any]:
    """Use LLM to extract structured fields from document markdown.

    Persona-aware: extracts different field sets depending on the claim/underwriting type.
    Returns a dict compatible with ``extracted_fields`` format used elsewhere.
    """
    # Truncate to first 8000 chars to stay within token limits
    snippet = markdown[:8000]

    # Persona-specific field schemas
    if persona in ("habitation_claims", "property_casualty_claims"):
        json_spec = (
            "{\n"
            '  "NomAssure": "string (nom complet de l\'assuré)",\n'
            '  "AdresseAssure": "string (adresse de l\'assuré)",\n'
            '  "TelephoneAssure": "string",\n'
            '  "EmailAssure": "string",\n'
            '  "NumeroContrat": "string (numéro de contrat ou police)",\n'
            '  "NumeroSocietaire": "string",\n'
            '  "FormuleContrat": "string (formule ou niveau de garantie)",\n'
            '  "DateSinistre": "string (DD/MM/YYYY)",\n'
            '  "NatureSinistre": "string (ex: dégât des eaux, incendie, tempête, vol)",\n'
            '  "LieuSinistre": "string (adresse du sinistre)",\n'
            '  "DescriptionSinistre": "string (description des dommages)",\n'
            '  "MontantEstime": "string (montant estimé des dommages en euros)",\n'
            '  "MesuresConservatoires": "string (mesures prises pour limiter les dommages)",\n'
            '  "TiersImplique": "string (oui/non + détails)",\n'
            '  "NiveauUrgence": "string (faible, moyen, élevé, critique)"\n'
            "}"
        )
        doc_type = "sinistre habitation / dégât des eaux"
    elif persona == "automotive_claims":
        json_spec = (
            "{\n"
            '  "NomAssure": "string (nom complet du conducteur/assuré)",\n'
            '  "NumeroContrat": "string (numéro de contrat ou police auto)",\n'
            '  "Vehicule": "string (marque, modèle, immatriculation)",\n'
            '  "DateSinistre": "string (DD/MM/YYYY)",\n'
            '  "LieuSinistre": "string",\n'
            '  "NatureSinistre": "string (collision, vol, vandalisme, etc.)",\n'
            '  "DescriptionSinistre": "string",\n'
            '  "MontantEstime": "string (estimation dommages en euros)",\n'
            '  "TiersImplique": "string (oui/non + détails)",\n'
            '  "ConstatAmiable": "string (oui/non)",\n'
            '  "NiveauUrgence": "string (faible, moyen, élevé, critique)"\n'
            "}"
        )
        doc_type = "sinistre automobile"
    else:
        # Default: underwriting / life-health
        # Field names MUST match the CU schema in personas.py (UNDERWRITING_FIELD_SCHEMA)
        # and what the frontend components expect:
        #   - api.ts extractPatientInfo() → ApplicantName, Occupation, Height, Weight, etc.
        #   - OccupationPanel.tsx → Occupation, HazardousActivities, ForeignTravelPlans
        #   - AllergiesPanel.tsx → AllergiesConnues
        json_spec = (
            "{\n"
            '  "ApplicantName": "string (full name of the applicant/patient)",\n'
            '  "DateOfBirth": "string (DD/MM/YYYY)",\n'
            '  "Age": "number or null",\n'
            '  "Gender": "string (Male/Female)",\n'
            '  "Height": "string (e.g. 178 cm)",\n'
            '  "Weight": "string (e.g. 86 kg)",\n'
            '  "BMI": "string (e.g. 27.1)",\n'
            '  "BloodPressureReadings": "string (e.g. 135/82 mmHg)",\n'
            '  "SmokingStatus": "string (e.g. Non-fumeur, Ancien fumeur, Fumeur actif)",\n'
            '  "AlcoholUse": "string (e.g. Modéré, Aucun, Régulier)",\n'
            '  "CurrentMedications": "string (comma-separated list)",\n'
            '  "MedicalConditionsSummary": "string (comma-separated list)",\n'
            '  "AllergiesConnues": "string (semicolon-separated list, or null if none)",\n'
            '  "FamilyHistory": "string (brief summary)",\n'
            '  "Occupation": "string (job title / profession)",\n'
            '  "HazardousActivities": "string (sports or activities à risque, or null)",\n'
            '  "ForeignTravelPlans": "string (planned travel to risk zones, or null)",\n'
            '  "PolicyProduct": "string (plan/formula name)",\n'
            '  "PolicyNumber": "string"\n'
            "}"
        )
        doc_type = "assurance vie / santé"

    system_prompt = (
        f"You are a data-extraction assistant for French insurance documents ({doc_type}). "
        "Extract the following fields from the document text and return ONLY valid JSON "
        "(no markdown fences). Use null for missing fields.\n"
        f"Required JSON structure:\n{json_spec}"
    )
    try:
        field_deployment, field_model = settings.openai.get_deployment("chat")
        raw = chat_completion(
            settings.openai,
            [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": snippet},
            ],
            deployment_override=field_deployment,
            model_override=field_model,
            max_tokens=1024,
            temperature=0.0,
            response_format="json_object",
        )
        # chat_completion returns {"content": "...", "usage": {...}}
        text = raw.get("content", "") if isinstance(raw, dict) else str(raw)
        # Strip markdown code fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()
        parsed = json.loads(text)
        fields: Dict[str, Any] = {}
        for key, value in parsed.items():
            if value is not None:
                fields[f"llm_extracted:{key}"] = {
                    "field_name": key,
                    "value": value,
                    "confidence": 0.0,
                    "source": "llm_markdown_fallback",
                    "model": field_model,
                    "source_text": "LLM fallback from consolidated markdown",
                }
        return fields
    except Exception as exc:
        logger.warning("LLM field extraction fallback failed: %s", exc)
        return {}


def _gpt_vision_describe_image(
    settings: Settings,
    file_bytes: bytes,
    filename: str,
    persona: str = "automotive_claims",
    language: Optional[str] = None,
) -> str:
    """Use the vision model to describe an image when CU analyzers fail.

    Persona-aware prompts:
    - automotive_claims: Vehicle damage from driver perspective
    - habitation_claims: Property damage (water, fire, theft)
    - life_health_claims: Medical documents, test results
    - mortgage_underwriting: Property valuation, structures
    - underwriting: Generic financial/risk documents

    Returns a markdown summary suitable for inclusion in the analysis context.
    """
    b64 = base64.b64encode(file_bytes).decode("ascii")
    ext = os.path.splitext(filename)[1].lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }.get(ext, "image/png")

    # Persona-specific system prompts — {brand} substituted from settings
    brand = settings.brand_name
    prompts_by_persona = {
        "automotive_claims": (
            f"Tu es un expert en sinistres automobiles pour {brand}. "
            "Décris les dommages visibles sur cette photo de véhicule en français. "
            "**CRUCIAL: Les côtés gauche/droite doivent être déterminés du point de vue du conducteur assis dans le véhicule, "
            "PAS du point de vue du photographe.** "
            "Structure ta réponse en sections:\n"
            "- **Véhicule identifié** (marque, modèle, couleur, année estimée)\n"
            "- **Zone affectée** (avant, arrière, côté conducteur/passager, toit)\n"
            "- **Type de dommage** (collision, rayure, enfoncement, bris de glace, déformation)\n"
            "- **Gravité estimée** (mineure, modérée, importante, critique)\n"
            "- **Pièces visiblement endommagées** (pare-chocs, aile, portière, capot, glace, etc.)\n"
            "- **Éléments de sécurité** (airbag déployé, structure déformée, étanchéité compromise)"
        ),
        "habitation_claims": (
            f"Tu es un expert en sinistres habitation pour {brand}. "
            "Décris les dommages visibles sur cette photo en français. "
            "Structure ta réponse en sections:\n"
            "- **Type de bien** (appartement, maison, cave, garage, etc.)\n"
            "- **Zone affectée** (façade, intérieur, toit, fenêtres, fondations)\n"
            "- **Nature du sinistre** (dégât des eaux, incendie, tempête, vol, vandalisme, etc.)\n"
            "- **Étendue des dommages** (mineurs, localisés, généralisés, perte totale)\n"
            "- **Éléments affectés** (revêtements, structures, équipements, mobilier)\n"
            "- **Traces de remédiation** (déshumidification en cours, nettoyage, réparations temporaires)"
        ),
        "life_health_claims": (
            f"Tu es un expert médical en assurance santé pour {brand}. "
            "Décris le document ou la photo médicale visible en français. "
            "Structure ta réponse en sections:\n"
            "- **Type de document** (prescription, ordonnance, facture, radiographie, résultat de lab)\n"
            "- **Informations visibles** (date, professionnel, patient si visible)\n"
            "- **Détails cliniques** (diagnostic, traitements, montants, codes)\n"
            "- **Clarté et lisibilité** (acceptable pour traitement, points d'amélioration)\n"
            "- **Relevance pour la couverture** (si applicable)"
        ),
        "mortgage_underwriting": (
            f"Tu es un expert en expertise immobilière pour {brand}. "
            "Décris le bien et sa structure visibles sur cette photo en français. "
            "Structure ta réponse en sections:\n"
            "- **Type de propriété** (maison, appartement, terrain, commercial)\n"
            "- **État général** (bon, moyen, dégradé, ruine)\n"
            "- **Caractéristiques visibles** (surface approximative, étages, architecture)\n"
            "- **Matériaux et construction** (pierre, brique, béton, bois, toiture)\n"
            "- **Défauts ou points d'attention** (fissures, humidité, toiture endommagée, fondations)\n"
            "- **Estimation d'âge** et travaux apparents (rénovés, anciens, neufs)"
        ),
    }
    system_prompt = prompts_by_persona.get(persona, prompts_by_persona["automotive_claims"])
    if language and language.lower() == "en":
        system_prompt += " Write your entire response in English, translating every section title and all content."

    user_text = (
        f"Analyze this photo: {filename}"
        if language and language.lower() == "en"
        else f"Analyse cette photo: {filename}"
    )
    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_text},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime};base64,{b64}", "detail": "high"},
                },
            ],
        },
    ]
    raw = chat_completion(
        settings.openai,
        messages,
        max_tokens=1024,
        temperature=0.0,
    )
    if isinstance(raw, dict):
        text = raw.get("content", "") or str(raw)
    else:
        text = str(raw)
    header = "Photo analysis" if language and language.lower() == "en" else "Analyse photo"
    return f"# {header} : {filename}\n\n{text}"


def _try_repair_truncated_json(text: str) -> Dict[str, Any]:
    """Attempt to repair truncated JSON from max_tokens cut-off.

    Strategy:
    1. Close any open string literals.
    2. Trim trailing incomplete values/keys.
    3. Close open brackets/braces to produce valid JSON.
    4. Return parsed result or error dict.
    """
    import re

    s = text.rstrip()

    # If inside an open string, close it
    in_string = False
    escape = False
    for i, ch in enumerate(s):
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string

    if in_string:
        s += '"'

    # Trim any trailing comma / colon / partial key outside a string
    s = re.sub(r"[,:]\s*$", "", s)

    # Close unclosed brackets / braces
    stack: list[str] = []
    in_str = False
    esc = False
    for ch in s:
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in ("{", "["):
            stack.append(ch)
        elif ch == "}" and stack and stack[-1] == "{":
            stack.pop()
        elif ch == "]" and stack and stack[-1] == "[":
            stack.pop()

    closers = {"[": "]", "{": "}"}
    while stack:
        s += closers.get(stack.pop(), "")

    try:
        parsed = json.loads(s)
        parsed["_truncated"] = True
        logger.info("Truncated JSON repaired successfully (%d chars)", len(s))
        return parsed
    except json.JSONDecodeError as e:
        return {"_raw": text, "_error": f"JSON repair failed: {e}"}


# Per-subsection max_tokens overrides for prompts that produce large JSON.
# Subsections not listed here use the chat_completion default (1200).
_SUBSECTION_MAX_TOKENS: Dict[str, int] = {
    "body_system_review": 16000,  # Multi-system structured JSON for 100+ page docs
    "pending_investigations": 4000,  # Can be lengthy for large APS docs
    "abnormal_labs": 4000,  # Many abnormal labs in complex cases
    "last_office_visit": 2000,
}


def _run_single_prompt(
    settings: Settings,
    section: str,
    subsection: str,
    prompt_template: str,
    document_markdown: str,
    additional_context: str = "",
    underwriting_policies: str = "",
    max_tokens_override: int | None = None,
    language: Optional[str] = None,
) -> Dict[str, Any]:
    system_prompt = "You are an expert life insurance underwriter. Always return STRICT JSON."
    if language and language.lower() == "en":
        system_prompt += " Respond in English for all human-readable text fields."
    else:
        system_prompt += (
            " Répondez en français pour tous les champs textuels destinés à l'utilisateur."
        )

    # Inject underwriting policies into the prompt template
    if "{underwriting_policies}" in prompt_template:
        prompt_with_policies = prompt_template.replace(
            "{underwriting_policies}", underwriting_policies if underwriting_policies else ""
        )
    else:
        prompt_with_policies = prompt_template

    user_prompt = (
        prompt_with_policies.strip() + "\n\n---\n\nApplication Markdown:\n\n" + document_markdown
    )

    if additional_context:
        user_prompt += additional_context

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    # Determine max_tokens: explicit override > subsection map > default
    max_tokens = max_tokens_override or _SUBSECTION_MAX_TOKENS.get(subsection)
    kwargs: Dict[str, Any] = {}
    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    logger.info(
        "Running prompt: %s.%s (max_tokens=%s)", section, subsection, max_tokens or "default"
    )
    result = chat_completion(settings.openai, messages, response_format="json_object", **kwargs)
    raw_content = result["content"]

    # Strip markdown code fences that LLMs sometimes wrap around JSON.
    # Handle cases where the LLM adds commentary after the closing ```.
    content_to_parse = raw_content.strip()
    if content_to_parse.startswith("```"):
        first_newline = content_to_parse.find("\n")
        if first_newline != -1:
            content_to_parse = content_to_parse[first_newline + 1 :]
        # Find the LAST closing ``` (may not be at the very end if LLM added text after)
        closing_idx = content_to_parse.rfind("```")
        if closing_idx != -1:
            content_to_parse = content_to_parse[:closing_idx].strip()

    try:
        parsed = json.loads(content_to_parse)
    except json.JSONDecodeError:
        # Strip single-line JS-style comments (// ...) that LLMs sometimes add
        import re

        stripped = re.sub(r"//[^\n]*", "", content_to_parse)
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            # Check if this looks like truncated JSON (max_tokens hit)
            usage = result.get("usage", {})
            completion_tokens = usage.get("completion_tokens", 0)
            is_likely_truncated = max_tokens and completion_tokens >= max_tokens - 5
            if is_likely_truncated:
                logger.warning(
                    "Prompt %s.%s: response likely truncated at %d tokens "
                    "(max_tokens=%s). Attempting JSON repair.",
                    section,
                    subsection,
                    completion_tokens,
                    max_tokens,
                )
                parsed = _try_repair_truncated_json(content_to_parse)
                if "_error" in parsed:
                    parsed["_error"] = (
                        f"JSON truncated at {completion_tokens} tokens "
                        f"(max_tokens={max_tokens}). {parsed['_error']}"
                    )
            else:
                parsed = {"_raw": raw_content, "_error": "Failed to parse JSON response."}

    return {
        "section": section,
        "subsection": subsection,
        "raw": raw_content,
        "parsed": parsed,
        "usage": result.get("usage", {}),
    }


def _run_section_prompts(
    settings: Settings,
    section: str,
    subsections: Dict[str, str],
    document_markdown: str,
    subsections_to_run: List[Tuple[str, str]] | None = None,
    max_workers: int = 4,
    additional_context: str = "",
    underwriting_policies: str = "",
    language: Optional[str] = None,
) -> Dict[str, Any]:
    """Run all prompts for a single section in parallel.

    Args:
        settings: Application settings
        section: The section name (e.g., 'medical_summary')
        subsections: Dict of subsection name to prompt template
        document_markdown: The document content to analyze
        subsections_to_run: Optional filter for specific subsections
        max_workers: Maximum parallel workers for this section
        additional_context: Optional context to append to prompts
        underwriting_policies: Formatted underwriting policies for prompt injection

    Returns:
        Dict mapping subsection names to their results
    """
    work_items: List[Tuple[str, str]] = []

    for subsection, template in subsections.items():
        if subsections_to_run and (section, subsection) not in subsections_to_run:
            continue
        # Template should now be a string after normalization
        # But handle dict format for backward compatibility
        if isinstance(template, dict):
            if "prompt" in template:
                prompt_text = template["prompt"]
            else:
                continue
        else:
            prompt_text = str(template)
        work_items.append((subsection, prompt_text))

    if not work_items:
        return {}

    logger.info("Running %d prompts for section '%s'", len(work_items), section)
    section_results: Dict[str, Any] = {}

    # Run prompts in parallel with limited concurrency
    effective_workers = min(max_workers, len(work_items), 4)

    with ThreadPoolExecutor(max_workers=effective_workers) as executor:
        futures = {}
        for subsection, template in work_items:
            future = executor.submit(
                _run_single_prompt,
                settings=settings,
                section=section,
                subsection=subsection,
                prompt_template=template,
                document_markdown=document_markdown,
                additional_context=additional_context,
                underwriting_policies=underwriting_policies,
                language=language,
            )
            futures[future] = subsection

        for fut in as_completed(futures):
            subsection = futures[fut]
            try:
                output = fut.result()
            except Exception as exc:  # noqa: BLE001
                logger.error(
                    "Prompt %s.%s failed: %s", section, subsection, str(exc), exc_info=True
                )
                output = {
                    "section": section,
                    "subsection": subsection,
                    "raw": "",
                    "parsed": {"_error": str(exc)},
                    "usage": {},
                }
            section_results[subsection] = output

    return section_results


# ===========================================================================
# Context Labels & Tasks Generation (backend-driven badges/alerts/tasks)
# ===========================================================================


def generate_context_labels(app_md: ApplicationMetadata) -> List[Dict[str, Any]]:
    """Generate context labels from analysis results.

    Labels replace client-side regex heuristics with authoritative
    backend-driven badges. Each label has:
      key, label, type, urgency, color, icon?, tooltip?, source_url?
    """
    labels: List[Dict[str, Any]] = []
    ef = app_md.extracted_fields or {}
    llm = app_md.llm_outputs or {}
    persona = (app_md.persona or "").lower()

    # --- Helper to read extracted field values ---------------------------------
    def _fv(*keys: str, default: str = "") -> str:
        for k in keys:
            entry = ef.get(k)
            if not entry:
                for fk, fv in ef.items():
                    if fk.endswith(f":{k}"):
                        entry = fv
                        break
            if entry:
                val = entry.get("value", entry) if isinstance(entry, dict) else entry
                if val:
                    return str(val)
        return default

    def _parse_numeric(raw: str) -> float:
        if not raw:
            return 0.0
        import re

        s = str(raw)
        s = re.sub(r"[^\d,.-]", "", s)
        if s.count(",") == 1 and s.count(".") == 0:
            s = s.replace(",", ".")
        elif s.count(",") > 0 and s.count(".") > 0:
            s = s.replace(",", "")
        try:
            return float(s)
        except ValueError:
            return 0.0

    def _parse_ratio(raw: str) -> float:
        v = _parse_numeric(raw)
        if v <= 0:
            return 0.0
        if v <= 1:
            return v * 100
        return v

    if persona in ("mortgage", "mortgage_underwriting"):
        dti = _parse_ratio(_fv("DebtToIncomeRatio", "DTI", "taux_endettement"))
        ltv = _parse_ratio(_fv("LoanToValueRatio", "LTV"))
        apport = _parse_numeric(_fv("DownPaymentAmount", "apport"))
        loan = _parse_numeric(_fv("RequestedLoanAmount", "montant_total", "montant_pret"))
        credit_score = int(_parse_numeric(_fv("CreditScore")))

        llm_summary = llm.get("application_summary", {}) if isinstance(llm, dict) else {}
        if isinstance(llm_summary, dict):
            borrower_profile = llm_summary.get("borrower_profile", {})
            if isinstance(borrower_profile, dict):
                parsed = borrower_profile.get("parsed", {})
                if isinstance(parsed, dict):
                    if dti <= 0 and parsed.get("dti_ratio") is not None:
                        dti = _parse_ratio(str(parsed.get("dti_ratio")))
                    if ltv <= 0 and parsed.get("ltv_ratio") is not None:
                        ltv = _parse_ratio(str(parsed.get("ltv_ratio")))
                    if loan <= 0 and parsed.get("loan_amount") is not None:
                        loan = _parse_numeric(str(parsed.get("loan_amount")))
                    if apport <= 0 and parsed.get("down_payment") is not None:
                        apport = _parse_numeric(str(parsed.get("down_payment")))

                    if parsed.get("primo_accedant") is True:
                        labels.append(
                            {
                                "key": "primo_accedant",
                                "label": "Primo-accédant",
                                "type": "profile",
                                "urgency": "info",
                                "color": "cyan",
                            }
                        )
                    ptz_amount = _parse_numeric(str(parsed.get("ptz_amount", "0")))
                    if ptz_amount > 0:
                        labels.append(
                            {
                                "key": "ptz",
                                "label": "PTZ",
                                "type": "financial",
                                "urgency": "info",
                                "color": "blue",
                                "tooltip": f"PTZ détecté: {ptz_amount:,.0f}€",
                            }
                        )

        employment_text = f"{_fv('EmployerName')} {_fv('OccupationTitle')} {_fv('BaseSalary')}"
        if "suisse" in employment_text.lower() or "chf" in employment_text.lower():
            labels.append(
                {
                    "key": "frontalier",
                    "label": "Frontalier",
                    "type": "profile",
                    "urgency": "warning",
                    "color": "amber",
                    "tooltip": "Revenus transfrontaliers à justifier (CHF/EUR)",
                }
            )

        if dti > 35:
            labels.append(
                {
                    "key": "hcsf_endettement_critique",
                    "label": "HCSF endettement > 35%",
                    "type": "risk",
                    "urgency": "critical",
                    "color": "rose",
                    "tooltip": f"Taux d'endettement estimé: {dti:.1f}%",
                }
            )
        elif dti > 32:
            labels.append(
                {
                    "key": "hcsf_endettement_tendu",
                    "label": "HCSF endettement proche seuil",
                    "type": "risk",
                    "urgency": "warning",
                    "color": "amber",
                    "tooltip": f"Taux d'endettement estimé: {dti:.1f}%",
                }
            )
        elif dti > 0:
            labels.append(
                {
                    "key": "hcsf_endettement_ok",
                    "label": "HCSF endettement conforme",
                    "type": "verification",
                    "urgency": "success",
                    "color": "emerald",
                    "tooltip": f"Taux d'endettement estimé: {dti:.1f}%",
                }
            )

        if ltv > 95:
            labels.append(
                {
                    "key": "hcsf_ltv_critique",
                    "label": "LTV très élevé",
                    "type": "risk",
                    "urgency": "critical",
                    "color": "rose",
                    "tooltip": f"LTV estimé: {ltv:.1f}%",
                }
            )
        elif ltv > 80:
            labels.append(
                {
                    "key": "hcsf_ltv_tendu",
                    "label": "LTV élevé",
                    "type": "risk",
                    "urgency": "warning",
                    "color": "amber",
                    "tooltip": f"LTV estimé: {ltv:.1f}%",
                }
            )

        if loan > 0 and apport > 0:
            apport_ratio = (apport / (loan + apport)) * 100
            if apport_ratio < 10:
                labels.append(
                    {
                        "key": "hcsf_apport_faible",
                        "label": "Apport faible",
                        "type": "risk",
                        "urgency": "warning",
                        "color": "amber",
                        "tooltip": f"Apport estimé: {apport_ratio:.1f}%",
                    }
                )
            else:
                labels.append(
                    {
                        "key": "hcsf_apport_ok",
                        "label": "Apport conforme",
                        "type": "verification",
                        "urgency": "success",
                        "color": "emerald",
                        "tooltip": f"Apport estimé: {apport_ratio:.1f}%",
                    }
                )

        if credit_score and credit_score < 620:
            labels.append(
                {
                    "key": "credit_score_faible",
                    "label": "Score crédit faible",
                    "type": "risk",
                    "urgency": "critical",
                    "color": "rose",
                    "tooltip": f"Score estimé: {credit_score}",
                }
            )

        files = app_md.files or []
        if len(files) < 2 or app_md.status in ("pending", "pending_review", "error"):
            labels.append(
                {
                    "key": "pieces_manquantes",
                    "label": "Pièces à compléter",
                    "type": "documents",
                    "urgency": "warning",
                    "color": "amber",
                }
            )

        seen: set = set()
        unique: List[Dict[str, Any]] = []
        for lbl in labels:
            if lbl["key"] not in seen:
                seen.add(lbl["key"])
                unique.append(lbl)
        return unique

    cause = _fv("NatureSinistre", "CauseOfLoss").lower()
    desc = _fv("DescriptionSinistre", "Description").lower()
    combined = f"{cause} {desc}"

    # 1. Guarantee labels (from nature/cause) ----------------------------------
    import re

    if re.search(r"dégâts? des eaux|dde|fuite|infiltration|inondation", combined):
        labels.append(
            {
                "key": "convention_irsi",
                "label": "Convention IRSI",
                "type": "guarantee",
                "urgency": "info",
                "color": "blue",
                "icon": "flag",
                "tooltip": "Applicable aux DDE multi-lots (convention inter-assureurs)",
            }
        )
        labels.append(
            {
                "key": "garantie_dde",
                "label": "Garantie DDE",
                "type": "guarantee",
                "urgency": "info",
                "color": "emerald",
            }
        )
    if re.search(r"tempête|grêle|neige|vent|ouragan|tornade", combined):
        labels.append(
            {
                "key": "garantie_tempete",
                "label": "Garantie Tempête",
                "type": "guarantee",
                "urgency": "info",
                "color": "sky",
            }
        )
    if re.search(r"vol|cambriolage|effraction|vandalisme", combined):
        labels.append(
            {
                "key": "garantie_vol",
                "label": "Garantie Vol",
                "type": "guarantee",
                "urgency": "info",
                "color": "purple",
            }
        )
        if re.search(r"récidive|antécédent", combined):
            labels.append(
                {
                    "key": "recidive",
                    "label": "Récidive",
                    "type": "alert",
                    "urgency": "critical",
                    "color": "rose",
                }
            )
    if re.search(r"incendie|feu|explosion|fumée", combined):
        labels.append(
            {
                "key": "garantie_incendie",
                "label": "Garantie Incendie",
                "type": "guarantee",
                "urgency": "info",
                "color": "orange",
            }
        )
    if re.search(r"bris de glace|vitre|fenêtre|vitrage", combined):
        labels.append(
            {
                "key": "bris_glace",
                "label": "Bris de glace",
                "type": "guarantee",
                "urgency": "info",
                "color": "cyan",
            }
        )
    if re.search(r"responsabilité civile|rc|tiers|voisin", combined):
        labels.append(
            {
                "key": "rc_habitation",
                "label": "RC Habitation",
                "type": "guarantee",
                "urgency": "info",
                "color": "indigo",
            }
        )
    if re.search(
        r"cat.?nat|catastrophe naturelle|séisme|mouvement de terrain|sécheresse|avalanche|submersion|crue",
        combined,
    ):
        labels.append(
            {
                "key": "regime_catnat",
                "label": "Régime Cat-Nat",
                "type": "guarantee",
                "urgency": "warning",
                "color": "amber",
            }
        )
    if re.search(r"fraude|suspect", combined):
        labels.append(
            {
                "key": "fraude_suspectee",
                "label": "Fraude suspectée",
                "type": "fraud",
                "urgency": "critical",
                "color": "rose",
            }
        )

    # Fallback
    if not labels:
        if persona == "automotive_claims":
            labels.append(
                {
                    "key": "sinistre_auto",
                    "label": "Sinistre Auto",
                    "type": "guarantee",
                    "urgency": "info",
                    "color": "slate",
                }
            )
        elif persona == "life_health_claims":
            labels.append(
                {
                    "key": "sinistre_sante",
                    "label": "Sinistre Santé",
                    "type": "guarantee",
                    "urgency": "info",
                    "color": "slate",
                }
            )
        else:
            labels.append(
                {
                    "key": "sinistre_habitation",
                    "label": "Sinistre Habitation",
                    "type": "guarantee",
                    "urgency": "info",
                    "color": "slate",
                }
            )

    # 2. Severity labels (from amount) -----------------------------------------
    montant_str = _fv("MontantEstime", "TotalIncurred", "MontantTotal")
    montant_num = 0.0
    try:
        montant_num = float(re.sub(r"[^\d.,]", "", montant_str).replace(",", ".") or "0")
    except ValueError:
        pass
    if montant_num > 5000:
        labels.append(
            {
                "key": "sinistre_majeur",
                "label": "Sinistre majeur",
                "type": "severity",
                "urgency": "warning",
                "color": "amber",
                "tooltip": f"Montant {montant_num:,.0f}€ — expertise obligatoire au-delà de 5 000€",
            }
        )

    # 3. LLM-derived labels from analysis output --------------------------------
    for section_name, subsections in llm.items():
        if not isinstance(subsections, dict):
            continue
        for _sub, output in subsections.items():
            if not isinstance(output, dict):
                continue
            parsed = output.get("parsed", {})
            if not isinstance(parsed, dict):
                continue
            # Coverage status
            cov = parsed.get("coverage_status", "")
            if isinstance(cov, str) and "non" in cov.lower():
                labels.append(
                    {
                        "key": "couverture_non_confirmee",
                        "label": "Couverture non confirmée",
                        "type": "alert",
                        "urgency": "warning",
                        "color": "amber",
                    }
                )
            # Exclusions
            excl = parsed.get("exclusions") or parsed.get("applicable_exclusions")
            if excl and isinstance(excl, list) and len(excl) > 0:
                labels.append(
                    {
                        "key": "exclusions_possibles",
                        "label": "Exclusions possibles",
                        "type": "alert",
                        "urgency": "warning",
                        "color": "amber",
                        "tooltip": "; ".join(str(e) for e in excl[:3]),
                    }
                )
            # Fraud indicators
            fi = parsed.get("fraud_indicators") or parsed.get("fraud_flags")
            if fi and isinstance(fi, list) and len(fi) > 0:
                labels.append(
                    {
                        "key": "indicateurs_fraude",
                        "label": "Indicateurs de fraude",
                        "type": "fraud",
                        "urgency": "critical",
                        "color": "rose",
                        "tooltip": "; ".join(str(f) for f in fi[:3]),
                    }
                )

    # 4. Fraud analysis labels --------------------------------------------------
    fa = app_md.fraud_analysis
    if fa and isinstance(fa, dict):
        oa = fa.get("overall_assessment", {})
        risk_score = oa.get("risk_score", 0)
        fraud_level = oa.get("overall_fraud_risk", "")
        if risk_score > 0.6 or fraud_level.upper() in ("HIGH", "ÉLEVÉ"):
            labels.append(
                {
                    "key": "fraude_elevee",
                    "label": f"Fraude {round(risk_score * 100)}%",
                    "type": "fraud",
                    "urgency": "critical",
                    "color": "rose",
                    "tooltip": f"Score fraude {round(risk_score * 100)}% — {fraud_level}",
                }
            )
        elif risk_score > 0.3:
            labels.append(
                {
                    "key": "fraude_moderee",
                    "label": f"Fraude {round(risk_score * 100)}%",
                    "type": "fraud",
                    "urgency": "warning",
                    "color": "amber",
                }
            )
        if oa.get("siu_referral_recommended"):
            labels.append(
                {
                    "key": "siu_referral",
                    "label": "Renvoi SIU",
                    "type": "fraud",
                    "urgency": "critical",
                    "color": "rose",
                    "tooltip": oa.get("siu_referral_reason", "Renvoi SIU recommandé"),
                }
            )

        # Web intelligence enrichment (Cat-Nat verification)
        wi = fa.get("web_intelligence") or oa.get("web_intelligence", {})
        if isinstance(wi, dict) and wi.get("event_verified") is not None:
            verified = wi["event_verified"]
            # findings can be a list of dicts or a plain string — normalise to str
            raw_findings = wi.get("findings", "")
            if isinstance(raw_findings, list):
                findings = "; ".join(
                    f.get("summary", f.get("title", str(f))) if isinstance(f, dict) else str(f)
                    for f in raw_findings
                )
            else:
                findings = str(raw_findings) if raw_findings else ""
            # source URLs — key varies between implementations
            sources = wi.get("source_urls", wi.get("sources", []))
            source_url = ""
            if sources and isinstance(sources, list) and len(sources) > 0:
                first = sources[0]
                if isinstance(first, dict):
                    source_url = first.get("url", first.get("source_url", ""))
                elif isinstance(first, str):
                    source_url = first
            if verified:
                labels.append(
                    {
                        "key": "catnat_confirmee",
                        "label": "✓ Cat-Nat confirmée",
                        "type": "verification",
                        "urgency": "success",
                        "color": "emerald",
                        "tooltip": findings[:200] if findings else "Événement vérifié",
                        "source_url": source_url,
                    }
                )
            else:
                labels.append(
                    {
                        "key": "catnat_non_confirmee",
                        "label": "✗ Cat-Nat non confirmée",
                        "type": "verification",
                        "urgency": "warning",
                        "color": "amber",
                        "tooltip": findings[:200]
                        if findings
                        else "Vérification manuelle nécessaire",
                    }
                )

    # Deduplicate by key
    seen: set = set()
    unique: List[Dict[str, Any]] = []
    for lbl in labels:
        if lbl["key"] not in seen:
            seen.add(lbl["key"])
            unique.append(lbl)
    return unique


def generate_context_tasks(app_md: ApplicationMetadata) -> List[Dict[str, Any]]:
    """Generate actionable tasks from analysis results.

    Tasks replace hardcoded checklists with dynamic items derived
    from the actual analysis output.
    """
    import re

    tasks: List[Dict[str, Any]] = []
    ef = app_md.extracted_fields or {}
    fa = app_md.fraud_analysis
    persona = (app_md.persona or "").lower()

    def _fv(*keys: str, default: str = "") -> str:
        for k in keys:
            entry = ef.get(k)
            if not entry:
                for fk, fv in ef.items():
                    if fk.endswith(f":{k}"):
                        entry = fv
                        break
            if entry:
                val = entry.get("value", entry) if isinstance(entry, dict) else entry
                if val:
                    return str(val)
        return default

    def _parse_numeric(raw: str) -> float:
        if not raw:
            return 0.0
        import re

        s = str(raw)
        s = re.sub(r"[^\d,.-]", "", s)
        if s.count(",") == 1 and s.count(".") == 0:
            s = s.replace(",", ".")
        elif s.count(",") > 0 and s.count(".") > 0:
            s = s.replace(",", "")
        try:
            return float(s)
        except ValueError:
            return 0.0

    def _parse_ratio(raw: str) -> float:
        v = _parse_numeric(raw)
        if v <= 0:
            return 0.0
        if v <= 1:
            return v * 100
        return v

    if persona in ("mortgage", "mortgage_underwriting"):
        dti = _parse_ratio(_fv("DebtToIncomeRatio", "DTI", "taux_endettement"))
        ltv = _parse_ratio(_fv("LoanToValueRatio", "LTV"))
        credit_score = int(_parse_numeric(_fv("CreditScore")))
        files = app_md.files or []

        if dti > 35:
            tasks.append(
                {
                    "key": "verify_hcsf_endettement",
                    "task": f"Vérifier conformité HCSF endettement ({dti:.1f}%) et options d'ajustement",
                    "category": "verification",
                    "priority": "high",
                    "due_offset_days": 0,
                }
            )

        if ltv > 80:
            tasks.append(
                {
                    "key": "verify_ltv",
                    "task": f"Contrôler LTV ({ltv:.1f}%) et exigences de couverture/garantie",
                    "category": "risk",
                    "priority": "high",
                    "due_offset_days": 1,
                }
            )

        if credit_score and credit_score < 620:
            tasks.append(
                {
                    "key": "credit_review",
                    "task": f"Revue crédit renforcée (score {credit_score})",
                    "category": "risk",
                    "priority": "high",
                    "due_offset_days": 0,
                }
            )

        missing_docs: List[str] = []
        names = " ".join(f.filename.lower() for f in files)
        if "demande" not in names:
            missing_docs.append("demande de prêt signée")
        if "imposition" not in names and "t4" not in names:
            missing_docs.append("justificatif fiscal")
        if "compromis" not in names and "simulation" not in names:
            missing_docs.append("document bien / simulation")
        if "frontalier" in names or "suisse" in names or "chf" in names:
            if "contrat" not in names:
                missing_docs.append("contrat de travail frontalier")

        if missing_docs or app_md.status in ("pending", "pending_review", "error"):
            task_text = "Collecter pièces manquantes"
            if missing_docs:
                task_text += ": " + ", ".join(missing_docs)
            tasks.append(
                {
                    "key": "collect_missing_docs_mortgage",
                    "task": task_text,
                    "category": "documents",
                    "priority": "high",
                    "due_offset_days": 1,
                }
            )

        if any(x in names for x in ("ptz", "primo")):
            tasks.append(
                {
                    "key": "verify_ptz_eligibility",
                    "task": "Vérifier éligibilité PTZ et justificatifs primo-accédant",
                    "category": "verification",
                    "priority": "medium",
                    "due_offset_days": 2,
                }
            )

        return tasks

    cause = _fv("NatureSinistre", "CauseOfLoss").lower()
    montant_str = _fv("MontantEstime", "TotalIncurred", "MontantTotal")
    montant_num = 0.0
    try:
        montant_num = float(re.sub(r"[^\d.,]", "", montant_str).replace(",", ".") or "0")
    except ValueError:
        pass
    tiers = _fv("TiersImplique", "ThirdPartyInvolved").lower()

    # Task 1: Verify coverage
    if "dde" in cause or "dégât" in cause or "fuite" in cause or "inondation" in cause:
        tasks.append(
            {
                "key": "verify_dde_coverage",
                "task": "Vérifier couverture DDE — CG Habitation",
                "category": "coverage",
                "priority": "high",
                "due_offset_days": 0,
            }
        )
    elif "tempête" in cause or "grêle" in cause:
        tasks.append(
            {
                "key": "verify_tempete_coverage",
                "task": "Vérifier couverture tempête — CG Habitation",
                "category": "coverage",
                "priority": "high",
                "due_offset_days": 0,
            }
        )
    elif "vol" in cause or "cambriolage" in cause:
        tasks.append(
            {
                "key": "verify_vol_coverage",
                "task": "Vérifier couverture vol — CG Habitation",
                "category": "coverage",
                "priority": "high",
                "due_offset_days": 0,
            }
        )
    elif "incendie" in cause:
        tasks.append(
            {
                "key": "verify_incendie_coverage",
                "task": "Vérifier couverture incendie — CG Habitation",
                "category": "coverage",
                "priority": "high",
                "due_offset_days": 0,
            }
        )
    else:
        tasks.append(
            {
                "key": "verify_coverage",
                "task": "Vérifier couverture CG Habitation",
                "category": "coverage",
                "priority": "high",
                "due_offset_days": 0,
            }
        )

    # Task 2: Expert required if amount > 5000
    if montant_num > 5000:
        tasks.append(
            {
                "key": "mandate_expert",
                "task": f"Mandater expert — montant {montant_num:,.0f}€ > 5 000€",
                "category": "expertise",
                "priority": "high",
                "due_offset_days": 1,
            }
        )

    # Task 3: Franchise application
    franchise = _fv("FranchiseApplicable")
    if franchise:
        tasks.append(
            {
                "key": "apply_franchise",
                "task": f"Appliquer franchise ({franchise})",
                "category": "financial",
                "priority": "medium",
                "due_offset_days": 3,
            }
        )
    else:
        tasks.append(
            {
                "key": "apply_franchise",
                "task": "Vérifier et appliquer franchise contractuelle",
                "category": "financial",
                "priority": "medium",
                "due_offset_days": 3,
            }
        )

    # Task 4: Third party recourse
    if tiers in ("oui", "yes", "true"):
        tasks.append(
            {
                "key": "third_party_recourse",
                "task": "Engager recours tiers — convention IRSI / CIDE-COP",
                "category": "recourse",
                "priority": "medium",
                "due_offset_days": 5,
            }
        )

    # Task 5: Missing docs
    files = app_md.files or []
    file_names_lower = " ".join(f.filename.lower() for f in files)
    missing: List[str] = []
    if (
        "déclaration" not in file_names_lower
        and "declaration" not in file_names_lower
        and "sinistre" not in file_names_lower
    ):
        missing.append("Déclaration de sinistre")
    has_photos = any(
        f.filename.lower().endswith(ext)
        for f in files
        for ext in (".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp")
    )
    if not has_photos:
        missing.append("Photos des dommages (min. 3)")
    if "devis" not in file_names_lower and "facture" not in file_names_lower:
        missing.append("Devis ou facture de réparation")
    if tiers in ("oui", "yes", "true") and "constat" not in file_names_lower:
        missing.append("Constat amiable (tiers impliqué)")
    if missing:
        tasks.append(
            {
                "key": "collect_missing_docs",
                "task": f"Collecter pièces manquantes : {', '.join(missing)}",
                "category": "documents",
                "priority": "high",
                "due_offset_days": 2,
            }
        )

    # Task 6: Fraud investigation
    if fa and isinstance(fa, dict):
        oa = fa.get("overall_assessment", {})
        if oa.get("siu_referral_recommended"):
            tasks.append(
                {
                    "key": "siu_referral",
                    "task": "Transmettre au SIU — investigation fraude requise",
                    "category": "fraud",
                    "priority": "critical",
                    "due_offset_days": 0,
                }
            )
        elif oa.get("risk_score", 0) > 0.3:
            tasks.append(
                {
                    "key": "fraud_review",
                    "task": "Examiner indicateurs de fraude avant règlement",
                    "category": "fraud",
                    "priority": "high",
                    "due_offset_days": 1,
                }
            )

    # Task 7: Cat-Nat verification
    if re.search(r"cat.?nat|catastrophe|séisme|inondation", cause):
        wi = {}
        if fa and isinstance(fa, dict):
            wi = fa.get("web_intelligence") or fa.get("overall_assessment", {}).get(
                "web_intelligence", {}
            )
        if not isinstance(wi, dict) or wi.get("event_verified") is None:
            tasks.append(
                {
                    "key": "verify_catnat",
                    "task": "Vérifier arrêté Cat-Nat (Légifrance / préfecture)",
                    "category": "verification",
                    "priority": "high",
                    "due_offset_days": 1,
                }
            )

    # Task 8: Contact client if sentiment critical
    sa = app_md.sentiment_analysis
    if sa and isinstance(sa, dict) and sa.get("level") in ("stressed", "critical"):
        tasks.append(
            {
                "key": "contact_client",
                "task": "Contacter le client — niveau de préoccupation élevé",
                "category": "communication",
                "priority": "high",
                "due_offset_days": 0,
            }
        )

    return tasks


def run_underwriting_prompts(
    settings: Settings,
    app_md: ApplicationMetadata,
    prompts_override: Dict[str, Dict[str, str]] | None = None,
    sections_to_run: List[str] | None = None,
    subsections_to_run: List[Tuple[str, str]] | None = None,
    max_workers_per_section: int = 4,
    on_section_complete: Any | None = None,
    cu_result: Optional[Dict[str, Any]] = None,
    processing_mode_override: Optional[str] = None,
    language: Optional[str] = None,
) -> ApplicationMetadata:
    """Execute prompts section by section to avoid overwhelming the service.

    Each section (e.g., application_summary, medical_summary, requirements) is run
    sequentially, but prompts within a section are run in parallel with limited
    concurrency.

    For large documents (>100KB), automatically switches to condensed context mode
    to avoid rate limit errors.

    Args:
        settings: Application settings
        app_md: Application metadata with document markdown
        prompts_override: Optional custom prompts dict
        sections_to_run: Optional list of section names to run
        subsections_to_run: Optional list of (section, subsection) tuples to run
        max_workers_per_section: Max parallel prompts per section (default: 4)
        on_section_complete: Optional callback(section_name, results) called after each section
        cu_result: Optional CU result with extracted fields (for large doc mode)
        processing_mode_override: 'auto', 'standard', or 'large_document' (default: auto)

    Returns:
        Updated ApplicationMetadata with LLM outputs
    """
    if not app_md.document_markdown:
        raise ValueError("ApplicationMarkdown is empty; run Content Understanding first.")

    # Get persona for processing decisions
    persona = app_md.persona or "underwriting"

    # Large document mode only applies to underwriting persona (life & health)
    # Other personas (claims, mortgage, etc.) use standard processing
    large_doc_eligible_personas = ["underwriting"]

    # Detect or use override processing mode.
    # For incremental runs (e.g. deep-dive), honour the mode that was
    # recorded during the original full analysis so that large-document
    # apps keep using batch_summaries even when the markdown alone falls
    # below the auto-detection threshold.
    if persona not in large_doc_eligible_personas:
        # Non-underwriting personas always use standard mode
        mode = "standard"
        logger.info("Persona '%s' not eligible for large doc mode, using standard", persona)
    elif processing_mode_override and processing_mode_override != "auto":
        mode = processing_mode_override
    elif sections_to_run and app_md.processing_mode and app_md.processing_mode != "auto":
        # Incremental re-analysis — keep the original processing mode
        mode = app_md.processing_mode
        logger.info(
            "Incremental run — honouring stored processing_mode '%s'",
            mode,
        )
    elif settings.processing.auto_detect_mode:
        mode = detect_processing_mode(
            app_md.document_markdown, settings.processing.large_doc_threshold_kb
        )
    else:
        mode = "standard"

    doc_size_kb = len(app_md.document_markdown.encode("utf-8")) / 1024
    logger.info(
        "Processing mode: %s (doc size: %.1f KB, threshold: %d KB, persona: %s)",
        mode,
        doc_size_kb,
        settings.processing.large_doc_threshold_kb,
        persona,
    )

    # Build appropriate context for prompts
    batch_summaries_context: str | None = None  # Rich context for deep dive prompts
    if mode == "large_document":
        # For incremental runs (e.g. deep-dive endpoint), reuse existing
        # batch summaries and condensed context to avoid expensive re-
        # summarization that can fail via rate limits.
        reused_existing = False
        if sections_to_run and app_md.batch_summaries and app_md.condensed_context:
            logger.info(
                "Reusing existing batch summaries (%d batches) and condensed "
                "context for incremental re-analysis",
                len(app_md.batch_summaries),
            )
            document_context = app_md.condensed_context
            batch_summaries = app_md.batch_summaries
            reused_existing = True
        else:
            logger.info("Using large document mode - building condensed context...")
            document_context, batch_summaries = build_condensed_context(
                settings,
                app_md.document_markdown,
                cu_result,
            )
        app_md.processing_mode = "large_document"
        app_md.condensed_context = document_context
        app_md.document_stats = get_document_stats(app_md.document_markdown)
        if not reused_existing:
            app_md.batch_summaries = batch_summaries  # Store batch summaries for UI
        logger.info(
            "Condensed context ready: %d chars (~%d tokens), %d batch summaries%s",
            len(document_context),
            len(document_context) // 4,
            len(batch_summaries) if batch_summaries else 0,
            " (reused)" if reused_existing else "",
        )
        # Build rich batch-summaries context for deep dive prompts.
        # Batch summaries preserve per-page detail and (Page N) references
        # that the consolidated condensed context may have lost.
        if batch_summaries:
            parts = []
            for bs in batch_summaries:
                parts.append(
                    f"### Batch {bs['batch_num']} — Pages {bs['page_start']}–{bs['page_end']}\n"
                    f"{bs['summary']}"
                )
            batch_summaries_context = (
                "# Detailed Batch Summaries\n"
                "The following are detailed summaries of the original medical records, "
                "organized by page range. Page references appear as (Page N) throughout.\n\n"
                + "\n\n".join(parts)
            )
            logger.info(
                "Batch summaries context for deep dive: %d chars (~%d tokens)",
                len(batch_summaries_context),
                len(batch_summaries_context) // 4,
            )
    else:
        document_context = app_md.document_markdown
        app_md.processing_mode = "standard"
        app_md.document_stats = get_document_stats(app_md.document_markdown)
        # Only clear batch_summaries on a full (non-incremental) run.
        # Incremental runs (deep dive) should preserve existing summaries
        # so they remain visible in the Source Review UI.
        if not sections_to_run:
            app_md.batch_summaries = None

    # Load persona-specific prompts from prompts_root
    prompts = prompts_override or load_prompts(settings.app.prompts_root, persona)

    # Normalize prompts structure - convert single prompts to subsection format
    # Structure can be either:
    # 1. {"section": {"prompt": "...", "json_schema": {...}}} - single prompt section
    # 2. {"section": {"subsection": {"prompt": "...", "json_schema": {...}}}} - nested subsections
    normalized_prompts: Dict[str, Dict[str, str]] = {}
    for section, content in prompts.items():
        if isinstance(content, dict):
            if "prompt" in content:
                # Single prompt section - use section name as subsection too
                normalized_prompts[section] = {section: content["prompt"]}
            else:
                # Nested subsections
                subsections = {}
                for subsection, sub_content in content.items():
                    if isinstance(sub_content, dict) and "prompt" in sub_content:
                        subsections[subsection] = sub_content["prompt"]
                    elif isinstance(sub_content, str):
                        subsections[subsection] = sub_content
                if subsections:
                    normalized_prompts[section] = subsections

    # Determine which sections to run
    sections_to_process = []
    for section, subs in normalized_prompts.items():
        if sections_to_run and section not in sections_to_run:
            continue
        # Check if any subsections in this section should be run
        has_subsections = False
        for subsection in subs.keys():
            if subsections_to_run is None or (section, subsection) in subsections_to_run:
                has_subsections = True
                break
        if has_subsections:
            sections_to_process.append((section, subs))

    if not sections_to_process:
        logger.warning("No prompts selected to run.")
        return app_md

    total_prompts = sum(
        len(
            [
                s
                for s in subs.keys()
                if subsections_to_run is None or (section, s) in subsections_to_run
            ]
        )
        for section, subs in sections_to_process
    )
    logger.info(
        "Running %d prompts across %d sections for application %s",
        total_prompts,
        len(sections_to_process),
        app_md.id,
    )

    # Load policies and determine context
    policies = load_policies(settings.app.prompts_root, persona=app_md.persona)
    policy_context = ""

    if policies:
        # Try to find plan name in extracted fields
        plan_name = None
        if app_md.extracted_fields:
            for key, data in app_md.extracted_fields.items():
                if "PlanName" in key or "plan_name" in key:
                    val = data.get("value")
                    if val and isinstance(val, str):
                        plan_name = val
                        break

        if plan_name:
            # Try to match specific policy
            matched_policy = None
            for policy_name, details in policies.items():
                if (
                    policy_name.lower() in plan_name.lower()
                    or plan_name.lower() in policy_name.lower()
                ):
                    matched_policy = details
                    break

            if matched_policy:
                policy_context = f"\n\n---\n\nPOLICY REFERENCE DATA (Use this for benefits/coverage):\n{json.dumps(matched_policy, indent=2)}\n"
            else:
                # If plan name found but no match, provide all as reference
                policy_context = f"\n\n---\n\nAVAILABLE PLANS REFERENCE (Use if plan name matches):\n{json.dumps(policies, indent=2)}\n"
        else:
            # If no plan name found, provide all as reference
            policy_context = f"\n\n---\n\nAVAILABLE PLANS REFERENCE (Use if plan name matches):\n{json.dumps(policies, indent=2)}\n"

    # Load persona-specific policies for claims personas
    # Claims personas need claims processing rules injected during analysis
    # Underwriting policies are only injected during explicit risk analysis
    persona_policies = ""
    if app_md.persona and app_md.persona in [
        "life_health_claims",
        "automotive_claims",
        "property_casualty_claims",
    ]:
        persona_policies = load_policies_for_persona_prompts(
            settings.app.prompts_root, app_md.persona, brand=settings.brand_name
        )
        if persona_policies:
            logger.info(
                "Loaded %d chars of %s claims policies for prompt injection",
                len(persona_policies),
                app_md.persona,
            )
            # Append claims policies to the policy context
            policy_context += f"\n\n---\n\nCLAIMS PROCESSING POLICIES (Use for claim decisions):\n{persona_policies}\n"
        else:
            logger.warning("No claims policies found for persona %s", app_md.persona)
    else:
        logger.info(
            "Standard analysis - underwriting policies injected separately during risk analysis"
        )

    # Load glossary for the current persona to help LLM understand domain terminology
    glossary_context = ""
    if app_md.persona:
        glossary_text = load_glossary_for_prompt(
            settings.app.prompts_root, app_md.persona, max_terms=100
        )
        if glossary_text:
            glossary_context = f"\n\n---\n\n{glossary_text}\n"
            policy_context += glossary_context
            logger.info("Injected glossary for persona %s", app_md.persona)

    underwriting_policies = ""

    # Deep dive subsections that benefit from richer batch-summary context
    _DEEP_DIVE_SUBSECTIONS = {
        "body_system_review",
        "pending_investigations",
        "last_office_visit",
        "abnormal_labs",
        "latest_vitals",
    }

    results: Dict[str, Dict[str, Any]] = {}
    budget = StageBudget.for_analysis(settings.processing)

    # Run each section sequentially to avoid overwhelming the service
    for section, subs in sections_to_process:
        if budget.exhausted():
            logger.warning(
                "Analysis budget exhausted (%.0fs, %d tokens) — skipping section %s",
                budget.elapsed(),
                budget.tokens_used,
                section,
            )
            budget.skipped.append(section)
            continue
        logger.info("Starting section: %s", section)

        # For medical_summary in large-doc mode with batch summaries available,
        # route deep-dive subsections to the richer batch-summaries context so
        # they build on the earlier page-level extraction instead of re-analyzing
        # a lossy condensed summary.
        if section == "medical_summary" and batch_summaries_context is not None:
            deep_dive_subs = {k: v for k, v in subs.items() if k in _DEEP_DIVE_SUBSECTIONS}
            other_subs = {k: v for k, v in subs.items() if k not in _DEEP_DIVE_SUBSECTIONS}

            section_results: Dict[str, Any] = {}

            # Run original medical_summary prompts against condensed context
            if other_subs:
                section_results.update(
                    _run_section_prompts(
                        settings=settings,
                        section=section,
                        subsections=other_subs,
                        document_markdown=document_context,
                        subsections_to_run=subsections_to_run,
                        max_workers=max_workers_per_section,
                        additional_context=policy_context,
                        underwriting_policies=underwriting_policies,
                        language=language,
                    )
                )

            # Run deep-dive prompts against richer batch summaries
            if deep_dive_subs:
                logger.info(
                    "Routing %d deep-dive prompts to batch-summaries context",
                    len(deep_dive_subs),
                )
                section_results.update(
                    _run_section_prompts(
                        settings=settings,
                        section=section,
                        subsections=deep_dive_subs,
                        document_markdown=batch_summaries_context,
                        subsections_to_run=subsections_to_run,
                        max_workers=max_workers_per_section,
                        additional_context=policy_context,
                        underwriting_policies=underwriting_policies,
                        language=language,
                    )
                )
        else:
            section_results = _run_section_prompts(
                settings=settings,
                section=section,
                subsections=subs,
                document_markdown=document_context,
                subsections_to_run=subsections_to_run,
                max_workers=max_workers_per_section,
                additional_context=policy_context,
                underwriting_policies=underwriting_policies,
                language=language,
            )

        results[section] = section_results
        for output in section_results.values():
            if isinstance(output, dict):
                budget.charge(output.get("usage"))
        logger.info("Completed section: %s (%d prompts)", section, len(section_results))

        # Call optional callback after each section completes
        if on_section_complete:
            try:
                on_section_complete(section, section_results)
            except Exception as exc:  # noqa: BLE001
                logger.warning("on_section_complete callback failed: %s", exc)

    # Merge results with existing outputs if doing partial re-analysis
    if sections_to_run and app_md.llm_outputs:
        logger.info("Merging new results with existing llm_outputs (incremental re-analysis)")
        existing = app_md.llm_outputs.copy()
        # Perform per-section (and per-subsection) merge to avoid dropping existing subsections
        for section, section_results in results.items():
            if isinstance(section_results, dict) and isinstance(existing.get(section), dict):
                # Merge subsections within this section, but never let error
                # entries overwrite previously-good data.
                merged_section = existing[section].copy()
                for key, value in section_results.items():
                    is_error = (
                        isinstance(value, dict)
                        and isinstance(value.get("parsed"), dict)
                        and "_error" in value["parsed"]
                    )
                    if is_error and key in merged_section:
                        # Existing data present — keep it, log warning
                        logger.warning(
                            "Skipping error result for %s.%s — preserving existing data",
                            section,
                            key,
                        )
                        continue
                    merged_section[key] = value
                existing[section] = merged_section
            else:
                # If not both dicts, replace entire section
                existing[section] = section_results
        app_md.llm_outputs = existing
    else:
        app_md.llm_outputs = results

    record_stage(app_md, budget, assess_analysis(budget=budget, results=results))
    app_md.status = "completed"
    save_application_metadata(settings.app.storage_root, app_md)
    logger.info("Underwriting prompts completed for application %s (mode: %s)", app_md.id, mode)
    return app_md


def run_risk_analysis(
    settings: Settings,
    app_md: ApplicationMetadata,
) -> Dict[str, Any]:
    """Run policy-based risk analysis on an already-analyzed application.

    This is a SEPARATE operation from extraction/summarization.
    It applies underwriting policies to the extracted data and generates
    a comprehensive risk assessment with policy citations.

    Args:
        settings: Application settings
        app_md: Application metadata with completed LLM outputs

    Returns:
        Risk analysis results with policy citations
    """
    if not app_md.llm_outputs:
        raise ValueError("Application has no LLM outputs. Run analysis first.")

    # Load risk analysis prompts from prompts_root
    risk_prompts_path = os.path.join(settings.app.prompts_root, "risk-analysis-prompts.json")
    if not os.path.exists(risk_prompts_path):
        raise ValueError("Risk analysis prompts file not found")

    with open(risk_prompts_path, "r") as f:
        risk_prompts_config = json.load(f)

    risk_prompts = risk_prompts_config.get("prompts", {})

    # Load underwriting policies from prompts_root
    underwriting_policies = load_underwriting_policies(settings.app.prompts_root)
    if not underwriting_policies:
        raise ValueError("No underwriting policies found")

    # Load glossary for underwriting persona to help LLM understand medical terminology
    glossary_text = load_glossary_for_prompt(
        settings.app.prompts_root, "underwriting", max_terms=100
    )
    if glossary_text:
        underwriting_policies = f"{glossary_text}\n\n---\n\n{underwriting_policies}"
        logger.info("Injected glossary into risk analysis prompt")

    logger.info(
        "Running risk analysis for application %s with %d chars of policies",
        app_md.id,
        len(underwriting_policies),
    )

    # Build application data summary from LLM outputs
    application_data_parts = []

    for section, subsections in app_md.llm_outputs.items():
        if not subsections:
            continue
        for subsection, output in subsections.items():
            if output and output.get("parsed"):
                parsed = output["parsed"]
                if isinstance(parsed, dict):
                    # Format the extracted data
                    application_data_parts.append(
                        f"### {section} - {subsection}\n```json\n{json.dumps(parsed, indent=2)}\n```"
                    )

    application_data = "\n\n".join(application_data_parts)

    # Also include document markdown excerpt for context
    doc_context = ""
    if app_md.document_markdown:
        doc_preview = app_md.document_markdown[:6000]
        if len(app_md.document_markdown) > 6000:
            doc_preview += "\n\n[Document truncated...]"
        doc_context = f"\n\n### Original Document Excerpt\n{doc_preview}"

    full_application_data = application_data + doc_context

    # Run the overall risk assessment prompt
    overall_prompt_config = risk_prompts.get("overall_risk_assessment", {})
    if not overall_prompt_config:
        raise ValueError("No overall_risk_assessment prompt found")

    prompt_template = overall_prompt_config.get("prompt", "")

    # Inject policies and application data
    filled_prompt = prompt_template.replace("{underwriting_policies}", underwriting_policies)
    filled_prompt = filled_prompt.replace("{application_data}", full_application_data)

    system_message = "You are an expert life insurance underwriter. Always return STRICT JSON."
    messages = [
        {"role": "system", "content": system_message},
        {"role": "user", "content": filled_prompt},
    ]

    logger.info("Sending risk analysis prompt to LLM")
    result = chat_completion(
        settings.openai, messages, max_tokens=3000, response_format="json_object"
    )
    raw_content = result["content"]

    # Strip markdown code fences if present (e.g., ```json ... ```)
    content_to_parse = raw_content.strip()
    if content_to_parse.startswith("```"):
        # Find the end of the first line (e.g., "```json\n")
        first_newline = content_to_parse.find("\n")
        if first_newline != -1:
            content_to_parse = content_to_parse[first_newline + 1 :]
        # Remove trailing ``` (may not be at very end if LLM added text after)
        closing_idx = content_to_parse.rfind("```")
        if closing_idx != -1:
            content_to_parse = content_to_parse[:closing_idx].strip()

    try:
        parsed = json.loads(content_to_parse)
    except Exception:
        parsed = {"_raw": raw_content, "_error": "Failed to parse JSON response."}

    risk_analysis_result = {
        "timestamp": app_md.created_at,
        "raw": raw_content,
        "parsed": parsed,
        "usage": result.get("usage", {}),
    }

    # Store risk analysis separately in the application metadata
    if not hasattr(app_md, "risk_analysis") or app_md.risk_analysis is None:
        app_md.risk_analysis = {}
    app_md.risk_analysis = risk_analysis_result

    # Clear processing status after successful completion
    app_md.processing_status = None
    app_md.processing_error = None

    save_application_metadata(settings.app.storage_root, app_md)
    logger.info("Risk analysis completed for application %s", app_md.id)

    return risk_analysis_result
