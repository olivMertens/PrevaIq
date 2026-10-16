"""Agent tools — functions wrapping existing workbench capabilities.

Each tool wraps an existing function from the workbench pipeline,
exposing it as a callable tool for Microsoft Agent Framework agents.

In Microsoft Agent Framework (1.7.x), plain Python functions with type hints
and docstrings are automatically detected as tools by the Agent.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from typing import Any

from ..telemetry import record_span_error, start_span
from ..utils import setup_logging

logger = setup_logging()


def _coerce_text(value: Any) -> str:
    """Coerce a tool-field value into a safe, sliceable string.

    LLM 'parsed' outputs sometimes place a nested object/list where a plain
    string is expected (e.g. ``synthese: {...}``). Slicing such a value with
    ``value[:300]`` raises ``TypeError`` and breaks the whole tool, which makes
    agents report a spurious "erreur" and fall back. Normalising here keeps the
    data-access tools resilient to heterogeneous model output shapes.
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("summary", "synthese", "text", "value", "description", "label"):
            nested = value.get(key)
            if isinstance(nested, str) and nested.strip():
                return nested
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    if isinstance(value, (list, tuple)):
        return "; ".join(_coerce_text(item) for item in value if item)
    return str(value)


def _pct(value: Any) -> int:
    """Convert a 0..1 (or 0..100) score to a whole-percent int, tolerating
    None/strings so a malformed score never breaks a data-access tool."""
    try:
        num = float(value)
    except (TypeError, ValueError):
        return 0
    if num <= 1.0:
        num *= 100
    return round(num)


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Parse a possibly None/string score into a float, tolerating ``%`` and commas."""
    if value is None:
        return default
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip().replace("%", "").replace(",", "."))
    except (TypeError, ValueError):
        return default


def _clamp01(value: float) -> float:
    """Clamp a float into the inclusive 0..1 range."""
    return max(0.0, min(1.0, value))


# Authenticity floor: an image scoring below this is treated as not authentic
# regardless of the model's boolean. Aligned with the frontend ConfidenceIndicator
# amber/red boundary (0.5) so a red dot never sits next to an "Authentique" verdict.
_IMG_AUTHENTIC_MIN_SCORE = 0.5


def _fraud_risk_band(score: float) -> str:
    """Map a 0..1 fraud score to the LOW/MODERATE/HIGH band the workbench UI expects."""
    if score >= 0.70:
        return "HIGH"
    if score >= 0.35:
        return "MODERATE"
    return "LOW"


def _reconcile_fraud_assessment(data: Any) -> Any:
    """Deterministically reconcile fraud output so verdicts, the overall risk score
    and the risk band stay coherent with the underlying evidence.

    The vision/assessment calls occasionally emit contradictory output — e.g.
    an image with ``authenticity_score`` 0.24 still flagged ``is_likely_authentic: true``,
    or an overall ``risk_score`` of 0 (LOW) despite suspect images and an inconsistent
    declaration. This layer, applied on top of the raw model JSON:

    * Per-image (downgrade-only): an image is authentic only when the model said so AND
      its score clears the authenticity floor AND its descriptive filename matches the
      content. It never upgrades an image the model already flagged, so genuine fraud
      signals are preserved while the glaring "red dot / Authentique" contradiction is
      removed.
    * Overall (raise-only floor): recompute a risk-score floor from the worst/mean image
      authenticity, the suspect ratio and the declaration consistency, then lift the
      overall score and band to at least that floor — so the UI never shows 0% when
      concerns exist. The model's own score/band is kept when it is already higher.
    * Synthesise an SIU referral and attention items when the reconciled risk is elevated
      but the model left them empty, so the case manager always has actionable context.

    The function is idempotent: re-running it on already-reconciled data is a no-op.
    """
    if not isinstance(data, dict):
        return data

    images = data.get("image_analyses")
    images = images if isinstance(images, list) else []

    scores: list[float] = []
    suspect_count = 0
    analysed_count = 0
    for img in images:
        if not isinstance(img, dict) or img.get("error"):
            continue
        analysed_count += 1
        score = _clamp01(_safe_float(img.get("authenticity_score"), 0.0))
        img["authenticity_score"] = score
        scores.append(score)

        llm_authentic = bool(img.get("is_likely_authentic", True))
        fc = img.get("filename_concordance")
        content_mismatch = bool(
            isinstance(fc, dict)
            and fc.get("filename_is_descriptive")
            and fc.get("matches_content") is False
        )
        authentic = llm_authentic and score >= _IMG_AUTHENTIC_MIN_SCORE and not content_mismatch
        img["is_likely_authentic"] = authentic
        if not authentic:
            suspect_count += 1

    overall = data.get("overall_assessment")
    if not isinstance(overall, dict):
        overall = {}
        data["overall_assessment"] = overall

    # Declaration consistency may be nested under ``declaration_match``.
    decl = data.get("declaration_verification")
    decl_consistency = 1.0
    decl_inconsistent = False
    if isinstance(decl, dict):
        decl_match = decl.get("declaration_match")
        decl_match = decl_match if isinstance(decl_match, dict) else decl
        decl_consistency = _clamp01(_safe_float(decl_match.get("consistency_score"), 1.0))
        decl_inconsistent = decl_match.get("overall_consistent") is False

    floor = 0.0
    if analysed_count:
        worst = 1.0 - min(scores)
        mean_score = sum(scores) / len(scores)
        image_auth_risk = max(worst, 1.0 - mean_score)
        suspect_ratio = suspect_count / analysed_count
        decl_risk = max(0.4, 1.0 - decl_consistency) if decl_inconsistent else (1.0 - decl_consistency)
        floor = _clamp01(0.45 * image_auth_risk + 0.25 * suspect_ratio + 0.30 * decl_risk)

    llm_score = _clamp01(_safe_float(overall.get("risk_score"), 0.0))
    final_score = max(llm_score, floor)
    overall["risk_score"] = round(final_score, 2)

    bands = {"LOW": 0, "MODERATE": 1, "HIGH": 2}
    llm_band = str(overall.get("overall_fraud_risk", "LOW")).upper()
    computed_band = _fraud_risk_band(final_score)
    overall["overall_fraud_risk"] = (
        computed_band if bands.get(computed_band, 0) >= bands.get(llm_band, 0) else llm_band
    )

    if final_score >= 0.6 and not overall.get("siu_referral_recommended"):
        overall["siu_referral_recommended"] = True
        if not overall.get("siu_referral_reason"):
            reason = f"{suspect_count} image(s) suspecte(s)" if suspect_count else "Risque élevé détecté"
            if decl_inconsistent:
                reason += " et déclaration incohérente"
            overall["siu_referral_reason"] = reason + " — contrôle SIU recommandé."

    existing_items = overall.get("attention_items")
    if not isinstance(existing_items, list) or not existing_items:
        synthesised: list[dict] = []
        for img in images:
            if not isinstance(img, dict) or img.get("error") or img.get("is_likely_authentic"):
                continue
            img_score = _safe_float(img.get("authenticity_score"))
            synthesised.append(
                {
                    "label": f"Image suspecte : {img.get('filename', 'image')}",
                    "priority": "high" if img_score < 0.35 else "medium",
                    "detail": (
                        f"Score d'authenticité {int(img_score * 100)}% — "
                        "vérification manuelle recommandée."
                    ),
                }
            )
        if decl_inconsistent:
            synthesised.append(
                {
                    "label": "Déclaration incohérente",
                    "priority": "medium",
                    "detail": (
                        f"Concordance déclaration/preuves {int(decl_consistency * 100)}% — "
                        "écarts à instruire."
                    ),
                }
            )
        if synthesised:
            overall["attention_items"] = synthesised

    return data


# ---------------------------------------------------------------------------
# Phase 1 tools — Chat / Ask IQ
# ---------------------------------------------------------------------------


async def search_policies(query: str, category: str = "", top_k: int = 5) -> str:
    """Search insurance policy documents using semantic RAG search.

    Use this tool when the user asks about policy coverage, exclusions,
    conditions, deductibles, or any question that requires citing specific
    policy articles.

    Args:
        query: Natural language question about insurance policies.
        category: Optional policy category filter (automotive, life_health,
                  property_casualty, mortgage).
        top_k: Number of policy chunks to retrieve (default 5).

    Returns:
        Formatted policy excerpts with article references and relevance scores.
    """
    from ..config import load_settings
    from ..rag.search import PolicySearchService

    settings = load_settings()
    if not settings.rag.enabled:
        return _fallback_policy_search(settings, query, category)

    # Policy PDFs are indexed per persona table (see scripts/index_pdf_policies.py).
    tables = {
        "automotive": "claim_policy_chunks",
        "life_health": "health_claims_policy_chunks",
    }
    schema = settings.database.schema or "workbenchiq"
    names = [tables[category]] if category in tables else (
        ["policy_chunks"] if category else ["policy_chunks", *tables.values()]
    )

    async def _search(table: str):
        service = PolicySearchService(settings)
        service.table = f"{schema}.{table}"
        if category:
            return await service.filtered_search(query=query, category=category, top_k=top_k)
        return await service.semantic_search(query=query, top_k=top_k)

    # Awaited on the server loop: the asyncpg pool belongs to it, so a private
    # asyncio.run() loop fails with "another operation is in progress".
    try:
        batches = await asyncio.gather(*(_search(t) for t in names), return_exceptions=True)
    except Exception as exc:
        logger.warning("RAG search failed, using fallback: %r", exc)
        return _fallback_policy_search(settings, query, category)
    failures = [b for b in batches if isinstance(b, BaseException)]
    if failures and len(failures) == len(batches):
        logger.warning("RAG search failed, using fallback: %r", failures[0])
        return _fallback_policy_search(settings, query, category)
    for failure in failures:
        logger.warning("RAG search failed on one table: %r", failure)
    results = sorted(
        (r for b in batches if not isinstance(b, BaseException) for r in b),
        key=lambda r: r.similarity, reverse=True,
    )[:top_k]

    if not results:
        return "Aucun article de police trouvé pour cette requête."

    parts = []
    for r in results:
        parts.append(
            f"### {r.policy_name} — {r.chunk_type}\n"
            f"**Catégorie** : {r.category} | **Pertinence** : {r.similarity:.0%}\n"
            f"{r.content}\n"
        )
    return "\n---\n".join(parts)


def _fallback_policy_search(settings, query: str, category: str) -> str:
    """Fallback: return full policy text when RAG is disabled."""
    from ..underwriting_policies import format_policies_for_persona

    persona_map = {
        "automotive": "automotive_claims",
        "life_health": "life_health_claims",
        "property_casualty": "habitation_claims",
        "mortgage": "mortgage_underwriting",
    }
    persona = persona_map.get(category, "underwriting")
    return format_policies_for_persona(
        settings.app.prompts_root, persona, brand=settings.brand_name
    )


def get_application_summary(application_id: str) -> str:
    """Retrieve a comprehensive summary of the insurance application or claim.

    Use this tool when the user asks about a specific application's
    status, extracted data, analysis results, fraud assessment,
    sentiment score, web intelligence findings, or action history.

    Args:
        application_id: The application ID (e.g. 'a1b2c3d4').

    Returns:
        Formatted summary including extracted fields, AI analysis,
        fraud/sentiment data, web intelligence, and action history.
    """
    from ..config import load_settings
    from ..storage import load_application

    settings = load_settings()
    app_md = load_application(settings.app.storage_root, application_id)
    if not app_md:
        return f"Application {application_id} introuvable."
    application_id = app_md.id

    parts = [f"## Application {application_id}"]
    parts.append(f"- **Statut** : {app_md.status}")
    parts.append(f"- **Persona** : {app_md.persona}")
    parts.append(f"- **Fichiers** : {len(app_md.files)}")
    if app_md.external_reference:
        parts.append(f"- **Client** : {app_md.external_reference}")

    if app_md.extracted_fields:
        parts.append("\n### Champs extraits")
        for key, val in list(app_md.extracted_fields.items())[:20]:
            if isinstance(val, dict):
                parts.append(f"- {val.get('field_name', key)}: {val.get('value', '')}")

    if app_md.llm_outputs:
        try:
            section_lines: list[str] = []
            for section, subs in app_md.llm_outputs.items():
                if not subs or not isinstance(subs, dict):
                    continue
                for sub, output in subs.items():
                    if output and isinstance(output, dict) and output.get("parsed"):
                        parsed = output["parsed"]
                        raw_summary = parsed.get("summary") if isinstance(parsed, dict) else None
                        if not raw_summary and isinstance(parsed, dict):
                            raw_summary = parsed.get("synthese")
                        summary = _coerce_text(raw_summary)
                        if summary:
                            section_lines.append(f"- **{section}.{sub}** : {summary[:300]}")
            if section_lines:
                parts.append("\n### Résultats d'analyse IA")
                parts.extend(section_lines)
        except Exception as exc:
            logger.warning("get_application_summary: llm_outputs section failed: %s", exc)

    # ── Fraud analysis ──
    fa = app_md.fraud_analysis
    if fa:
        try:
            oa = fa.get("overall_assessment", {}) or {}
            parts.append("\n### Analyse anti-fraude")
            parts.append(f"- **Risque fraude** : {oa.get('overall_fraud_risk', 'N/A')}")
            parts.append(f"- **Score** : {_pct(oa.get('risk_score', 0))}%")
            if oa.get("siu_referral_recommended"):
                parts.append(f"- **⚠ Renvoi SIU recommandé** : {_coerce_text(oa.get('siu_referral_reason', ''))}")
            if oa.get("summary"):
                parts.append(f"- **Synthèse** : {_coerce_text(oa['summary'])[:300]}")
            for item in (oa.get("attention_items") or [])[:4]:
                if not isinstance(item, dict):
                    continue
                parts.append(
                    f"  - [{item.get('priority', '')}] {item.get('label', '')}: {_coerce_text(item.get('detail', ''))[:150]}"
                )
            for ia in (fa.get("image_analyses") or [])[:3]:
                if not isinstance(ia, dict):
                    continue
                auth = "authentique" if ia.get("is_likely_authentic") else "suspecte"
                parts.append(
                    f"- Image {ia.get('filename', '?')}: {auth} ({_pct(ia.get('authenticity_score', 0))}%)"
                )
            dv = fa.get("declaration_verification", {}) or {}
            if dv.get("consistency_score") is not None:
                parts.append(f"- **Concordance déclaration** : {_pct(dv['consistency_score'])}%")

            # Web intelligence (nested in fraud_analysis)
            wi = fa.get("web_intelligence")
            if wi and isinstance(wi, dict) and not wi.get("error"):
                parts.append("\n### Renseignement web (Bing WebSearch)")
                if wi.get("event_verified") is True:
                    parts.append("- ✅ Événement vérifié par sources web")
                elif wi.get("event_verified") is False:
                    parts.append("- ❌ Événement non confirmé par sources web")
                else:
                    parts.append("- ⚠ Vérification web non concluante")
                if wi.get("confidence") is not None:
                    parts.append(f"- Confiance : {_pct(wi.get('confidence', 0))}%")
                if wi.get("overall_assessment"):
                    parts.append(f"- {_coerce_text(wi['overall_assessment'])[:300]}")
                for finding in (wi.get("findings") or [])[:4]:
                    if not isinstance(finding, dict):
                        continue
                    title = finding.get("title", finding.get("titre", ""))
                    summary = _coerce_text(finding.get("summary", finding.get("resume", "")))
                    parts.append(f"  - {title}: {summary[:150]}")
        except Exception as exc:
            logger.warning("get_application_summary: fraud section failed: %s", exc)

    # ── Sentiment analysis ──
    sa = app_md.sentiment_analysis
    if sa:
        try:
            parts.append("\n### Accompagnement client (Sentiment)")
            parts.append(f"- **Score** : {sa.get('score', '?')}/100 ({sa.get('level', '?')})")
            parts.append(f"- **Ton suggéré** : {sa.get('suggestedTone', '?')}")
            if sa.get("contextSummary"):
                parts.append(f"- {_coerce_text(sa['contextSummary'])[:200]}")
            for f in (sa.get("factors") or [])[:4]:
                parts.append(f"  - {_coerce_text(f)}")
            for s in (sa.get("suggestions") or [])[:3]:
                parts.append(f"  - 💡 {_coerce_text(s)}")
        except Exception as exc:
            logger.warning("get_application_summary: sentiment section failed: %s", exc)

    # ── Action history ──
    ah = app_md.action_history
    if ah:
        try:
            parts.append("\n### Historique des actions")
            for action in ah[-6:]:
                if not isinstance(action, dict):
                    continue
                systems = ", ".join(s for s in (action.get("systems") or []) if s)
                parts.append(
                    f"- [{_coerce_text(action.get('at', '?'))[:16]}] {action.get('label', '?')} ({action.get('performed', '?')}) — {systems}"
                )
        except Exception as exc:
            logger.warning("get_application_summary: action_history section failed: %s", exc)

    return "\n".join(parts)


def get_glossary(term: str = "") -> str:
    """Look up insurance domain terminology in the glossary.

    Use this tool when the user asks about the meaning of a specific
    insurance term, medical code, or abbreviation.

    Args:
        term: Optional specific term to look up. If empty, returns
              the full glossary.

    Returns:
        Definition(s) from the insurance domain glossary.
    """
    from ..config import load_settings
    from ..glossary import format_glossary_for_prompt

    settings = load_settings()
    glossary_text = format_glossary_for_prompt(
        settings.app.prompts_root,
        "underwriting",
        max_terms=100,
        format_type="list",
    )
    if not glossary_text:
        return "Glossaire non disponible."

    if term:
        term_lower = term.lower()
        lines = glossary_text.split("\n")
        matches = [ln for ln in lines if term_lower in ln.lower()]
        if matches:
            return "\n".join(matches)
        return f"Terme '{term}' non trouvé dans le glossaire."

    return glossary_text


# ---------------------------------------------------------------------------
# Phase 2 tools — Analysis
# ---------------------------------------------------------------------------


def analyze_section(
    application_id: str,
    section: str,
    subsection: str,
) -> str:
    """Run a specific prompt-based analysis section on an application.

    Use this tool to re-run or run a specific analysis section. Each
    section/subsection corresponds to a prompt template that will be
    executed against the application's extracted documents.

    Args:
        application_id: The application ID.
        section: Analysis section (e.g. 'medical_summary',
                 'damage_assessment', 'liability_assessment').
        subsection: Analysis subsection (e.g. 'hypertension',
                    'visual_damage_analysis', 'fault_determination').

    Returns:
        JSON analysis result from the LLM.
    """
    from ..config import load_settings
    from ..storage import load_application, save_application_metadata
    from ..processing import _run_single_prompt
    from ..prompts import load_prompts
    from ..underwriting_policies import format_all_policies_for_prompt

    settings = load_settings()
    app_md = load_application(settings.app.storage_root, application_id)
    if not app_md:
        return f"Application {application_id} introuvable."

    persona = app_md.persona or "underwriting"
    prompts = load_prompts(settings.app.prompts_root, persona)

    if section not in prompts or subsection not in prompts.get(section, {}):
        available = []
        for s, subs in prompts.items():
            if isinstance(subs, dict):
                for ss in subs:
                    available.append(f"{s}.{ss}")
        return (
            f"Section '{section}.{subsection}' non trouvée. "
            f"Disponibles : {', '.join(available[:10])}"
        )

    template = prompts[section][subsection]
    policies = format_all_policies_for_prompt(settings.app.prompts_root, persona)
    doc_md = app_md.document_markdown or ""

    result = _run_single_prompt(
        settings,
        section,
        subsection,
        template,
        doc_md,
        underwriting_policies=policies,
    )

    # Store result
    if not app_md.llm_outputs:
        app_md.llm_outputs = {}
    if section not in app_md.llm_outputs:
        app_md.llm_outputs[section] = {}
    app_md.llm_outputs[section][subsection] = result
    save_application_metadata(settings.app.storage_root, app_md)

    parsed = result.get("parsed", {})
    return (
        json.dumps(parsed, ensure_ascii=False, indent=2)
        if parsed
        else result.get("raw", "Pas de résultat")
    )


def list_available_analyses(persona: str = "underwriting") -> str:
    """List all available analysis sections and subsections for a persona.

    Use this tool to discover what analyses can be run for a given
    insurance persona.

    Args:
        persona: The persona ID (underwriting, life_health_claims,
                 automotive_claims, habitation_claims, mortgage).

    Returns:
        Formatted list of section.subsection combinations.
    """
    from ..config import load_settings
    from ..prompts import load_prompts

    settings = load_settings()
    prompts = load_prompts(settings.app.prompts_root, persona)

    lines = [f"## Analyses disponibles — {persona}\n"]
    for section, subs in prompts.items():
        if isinstance(subs, dict):
            for sub in subs:
                lines.append(f"- `{section}.{sub}`")
        else:
            lines.append(f"- `{section}` (prompt unique)")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Phase 3 tools — Content Understanding
# ---------------------------------------------------------------------------


def get_extracted_fields(application_id: str) -> str:
    """Get all extracted fields from an application's documents.

    Use this tool to see the structured data that Content Understanding
    extracted from the uploaded files.

    Args:
        application_id: The application ID.

    Returns:
        Formatted list of extracted fields with values and confidence scores.
    """
    from ..config import load_settings
    from ..storage import load_application

    settings = load_settings()
    app_md = load_application(settings.app.storage_root, application_id)
    if not app_md:
        return f"Application {application_id} introuvable."

    if not app_md.extracted_fields:
        return "Aucun champ extrait. Lancez l'extraction d'abord."

    lines = ["## Champs extraits\n"]
    for key, val in app_md.extracted_fields.items():
        if isinstance(val, dict):
            name = val.get("field_name", key)
            value = val.get("value", "")
            conf = val.get("confidence", 0)
            source = val.get("source_file", "")
            conf_icon = "🟢" if conf >= 0.9 else "🟡" if conf >= 0.7 else "🔴"
            lines.append(f"- {conf_icon} **{name}** : {value} ({conf:.0%}) — {source}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# P1 Chat Tools — Risk, Customer360, Image Descriptions
# ---------------------------------------------------------------------------


def get_risk_analysis(application_id: str) -> str:
    """Get the risk analysis for an application from policy-based assessment.

    Use this tool when the user asks about risk, fraud likelihood,
    coverage gaps, or underwriting recommendations for a specific application.

    Args:
        application_id: The application ID.

    Returns:
        Formatted risk analysis with scores and recommendations.
    """
    from ..config import load_settings
    from ..storage import load_application

    settings = load_settings()
    app_md = load_application(settings.app.storage_root, application_id)
    if not app_md:
        return f"Application {application_id} introuvable."

    ra = app_md.risk_analysis
    if not ra:
        return (
            "Aucune analyse de risque disponible pour cette application. Lancez l'analyse d'abord."
        )

    parts = ["## Analyse de risque\n"]

    # Overall risk level
    parts.append(f"- **Niveau de risque** : {ra.get('risk_level', 'N/A')}")
    parts.append(f"- **Score** : {ra.get('risk_score', 0)}/100")
    try:
        confidence = float(ra.get("confidence", 0) or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    parts.append(f"- **Confiance** : {confidence:.0%}")

    # Key factors
    if ra.get("key_factors"):
        parts.append("\n### Facteurs clés")
        for factor in ra.get("key_factors", [])[:5]:
            parts.append(f"- {factor}")

    # Coverage gaps
    if ra.get("coverage_gaps"):
        parts.append("\n### Lacunes de couverture")
        for gap in ra.get("coverage_gaps", [])[:4]:
            parts.append(f"- ⚠️ {gap}")

    # Recommendations
    if ra.get("recommendations"):
        parts.append("\n### Recommandations")
        for rec in ra.get("recommendations", [])[:4]:
            parts.append(f"- ✅ {rec}")

    # Summary
    if ra.get("summary"):
        parts.append(f"\n**Synthèse** : {_coerce_text(ra['summary'])[:500]}")

    return "\n".join(parts)


def get_customer360_overview(customer_id: str = None, application_id: str = None) -> str:
    """Get a 360-degree view of all customer data and related applications.

    Use this tool when the user asks about the customer history, other claims,
    cross-sell opportunities, or full customer overview.

    Args:
        customer_id: The customer ID (external_reference).
        application_id: Alternatively, specify an application to look up its customer.

    Returns:
        Formatted customer overview including all applications, claims, and patterns.
    """
    from ..config import load_settings
    from ..storage import load_application, list_applications

    settings = load_settings()

    # Resolve customer_id from application if not provided
    if not customer_id and application_id:
        app_md = load_application(settings.app.storage_root, application_id)
        if not app_md:
            return f"Application {application_id} introuvable."
        customer_id = app_md.external_reference

    if not customer_id:
        return "Veuillez spécifier un customer_id ou application_id."

    # Get all applications
    all_apps_list = list_applications(settings.app.storage_root)

    # Filter by customer
    customer_apps = []
    for app_summary in all_apps_list:
        if app_summary.get("external_reference") == customer_id:
            # Load full metadata to get more details
            try:
                app_md = load_application(settings.app.storage_root, app_summary.get("id"))
                if app_md:
                    customer_apps.append(app_md)
            except Exception:
                pass

    if not customer_apps:
        return f"Aucune application trouvée pour le client {customer_id}."

    parts = [f"## Client 360 — {customer_id}\n"]
    parts.append(f"**Total applications** : {len(customer_apps)}")

    # Group by persona/type
    by_persona = {}
    for app in customer_apps:
        persona = app.persona or "autre"
        if persona not in by_persona:
            by_persona[persona] = []
        by_persona[persona].append(app)

    parts.append("\n### Applications par type")
    for persona, apps in by_persona.items():
        parts.append(f"- **{persona}** : {len(apps)} dossier(s)")
        for app in sorted(apps, key=lambda a: a.created_at, reverse=True)[
            -3:
        ]:  # Last 3 for brevity
            status_icon = (
                "✅"
                if app.status == "completed"
                else "⏳"
                if app.status == "processing"
                else "❌"
                if app.status == "error"
                else "📋"
            )
            parts.append(f"  {status_icon} {app.id} ({app.created_at[:10]})")

    # Risk patterns
    high_risk_count = len(
        [
            a
            for a in customer_apps
            if a.risk_analysis and a.risk_analysis.get("risk_level") == "high"
        ]
    )
    if high_risk_count > 0:
        parts.append(f"\n⚠️ **Pattern détecté** : {high_risk_count} application(s) à risque élevé")

    # Claims frequency
    claims_apps = [a for a in customer_apps if a.persona and "claims" in a.persona]
    if claims_apps:
        parts.append(f"\n📊 **Sinistralité** : {len(claims_apps)} sinistre(s)")
        for app in sorted(claims_apps, key=lambda a: a.created_at, reverse=True)[-2:]:
            parts.append(f"  - {app.persona}: {app.created_at[:10]}")

    # Cross-sell opportunities
    personas = set(a.persona for a in customer_apps if a.persona)
    if len(personas) == 1:
        parts.append("\n💡 **Opportunité cross-sell** : Client non assuré pour autres risques")

    return "\n".join(parts)


def get_image_descriptions(application_id: str) -> str:
    """Extract and retrieve descriptions of all images processed in an application.

    Use this tool when the user asks "what does this photo show?" or needs
    to review image descriptions from the Content Understanding or vision-model analysis.

    Args:
        application_id: The application ID.

    Returns:
        Formatted list of image descriptions extracted during processing.
    """
    from ..config import load_settings
    from ..storage import load_application

    settings = load_settings()
    app_md = load_application(settings.app.storage_root, application_id)
    if not app_md:
        return f"Application {application_id} introuvable."

    # Extract image descriptions from markdown_pages
    image_descriptions = []
    if app_md.markdown_pages:
        for page in app_md.markdown_pages:
            if page.get("file", "").lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                markdown = page.get("markdown", "")
                # Extract content after "# Image Analysis:" or "# Analyse photo:"
                if "# Image Analysis:" in markdown or "# Analyse photo:" in markdown:
                    description = markdown.split("#", 1)[-1].strip()
                    image_descriptions.append(
                        {
                            "file": page.get("file"),
                            "page_number": page.get("page_number"),
                            "description": description[:500],  # Truncate to 500 chars
                        }
                    )

    if not image_descriptions:
        return "Aucune description d'image trouvée pour cette application."

    parts = ["## Descriptions d'images\n"]
    for img in image_descriptions:
        parts.append(f"### {img['file']} (Page {img['page_number']})\n")
        parts.append(img["description"])
        parts.append("")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# P2 Chat Tools — Confidence, File List, Context Details
# ---------------------------------------------------------------------------


def get_confidence_scores(application_id: str) -> str:
    """Get confidence scores for all extracted fields.

    Use this tool when the user asks about extraction quality,
    which fields are uncertain, or wants to see confidence metrics.

    Args:
        application_id: The application ID.

    Returns:
        Formatted confidence summary with field-by-field scores.
    """
    from ..config import load_settings
    from ..storage import load_application

    settings = load_settings()
    app_md = load_application(settings.app.storage_root, application_id)
    if not app_md:
        return f"Application {application_id} introuvable."

    if not app_md.confidence_summary:
        return "Aucun score de confiance disponible. Lancez l'extraction d'abord."

    cs = app_md.confidence_summary
    parts = ["## Scores de confiance — Extraction\n"]

    # Overall stats
    parts.append(f"- **Total champs** : {cs.get('total_fields', 0)}")
    parts.append(f"- **Confiance moyenne** : {cs.get('average_confidence', 0):.0%}")
    parts.append("")

    # Confidence distribution
    parts.append("### Distribution par niveau")
    parts.append(f"- 🟢 **Haute confiance** (≥90%) : {cs.get('high_confidence_count', 0)} champ(s)")
    parts.append(
        f"- 🟡 **Confiance moyenne** (70-90%) : {cs.get('medium_confidence_count', 0)} champ(s)"
    )
    parts.append(f"- 🔴 **Basse confiance** (<70%) : {cs.get('low_confidence_count', 0)} champ(s)")

    # High confidence fields (good quality)
    if cs.get("high_confidence_fields"):
        parts.append("\n### Champs de haute confiance")
        for field in cs.get("high_confidence_fields", [])[:10]:
            name = field.get("field_name", "?")
            conf = field.get("confidence", 0)
            parts.append(f"- ✅ {name} ({conf:.0%})")

    # Medium confidence (acceptable but verify)
    if cs.get("medium_confidence_fields"):
        parts.append("\n### Champs de confiance moyenne (à vérifier)")
        for field in cs.get("medium_confidence_fields", [])[:5]:
            name = field.get("field_name", "?")
            conf = field.get("confidence", 0)
            parts.append(f"- ⚠️ {name} ({conf:.0%})")

    # Low confidence (problematic)
    if cs.get("low_confidence_fields"):
        parts.append("\n### Champs de basse confiance (intervention manuelle recommandée)")
        for field in cs.get("low_confidence_fields", [])[:5]:
            name = field.get("field_name", "?")
            conf = field.get("confidence", 0)
            parts.append(f"- 🔴 {name} ({conf:.0%})")

    return "\n".join(parts)


def get_file_list(application_id: str, include_details: bool = True) -> str:
    """Get list of all files in an application with metadata.

    Use this tool when the user asks "what files are in this application?"
    or needs to reference specific documents.

    Args:
        application_id: The application ID.
        include_details: Include file size, type, extraction status.

    Returns:
        Formatted list of files with metadata.
    """
    from ..config import load_settings
    from ..storage import load_application

    settings = load_settings()
    app_md = load_application(settings.app.storage_root, application_id)
    if not app_md:
        return f"Application {application_id} introuvable."

    if not app_md.files:
        return "Aucun fichier dans cette application."

    parts = ["## Fichiers\n"]
    parts.append(f"**Total** : {len(app_md.files)} fichier(s)\n")

    def _read_attr(obj: object, key: str, default: object = None) -> object:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    for idx, stored_file in enumerate(app_md.files, 1):
        filename = _read_attr(stored_file, "filename", "?")
        extracted = bool(_read_attr(stored_file, "extracted", False))
        status_icon = "✅" if extracted else "⏳"

        parts.append(f"{idx}. {status_icon} **{filename}**")

        if include_details:
            original = _read_attr(stored_file, "original_name", "")
            media_type = _read_attr(stored_file, "media_type", "")
            if media_type:
                parts.append(f"   - Type : {media_type}")
            if original and original != filename:
                parts.append(f"   - Nom original : {original}")

    # Extraction status summary
    extracted_count = sum(1 for f in app_md.files if bool(_read_attr(f, "extracted", False)))
    if extracted_count < len(app_md.files):
        parts.append(
            f"\n⚠️ **{len(app_md.files) - extracted_count}** fichier(s) non encore traité(s)"
        )
    else:
        parts.append("\n✅ Tous les fichiers ont été traités")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# P3 Chat Tools — Document Classification, Communications, Sentiment, Multimodal
# ---------------------------------------------------------------------------


def classify_documents(application_id: str) -> str:
    """Classify documents in the application by type (constat, facture, photo, lettre, email).

    Use this tool when the user asks "what types of documents are there?"
    or needs to organize documents by category for processing.

    Args:
        application_id: The application ID.

    Returns:
        Formatted document classifications.
    """
    from ..config import load_settings
    from ..storage import load_application

    settings = load_settings()
    app_md = load_application(settings.app.storage_root, application_id)
    if not app_md:
        return f"Application {application_id} introuvable."

    if not app_md.files:
        return "Aucun fichier à classifier."

    # Simple classification based on filename patterns and extensions
    classifications = {
        "Constats/Déclarations": [],
        "Factures/Devis": [],
        "Photos/Images": [],
        "Lettres/Correspondance": [],
        "Emails": [],
        "Autres": [],
    }

    for stored_file in app_md.files:
        filename = (
            stored_file.filename
            if hasattr(stored_file, "filename")
            else stored_file.get("filename", "")
        )
        filename_lower = filename.lower()

        # Classify by filename patterns
        if any(term in filename_lower for term in ["constat", "déclaration", "sinistre", "claim"]):
            classifications["Constats/Déclarations"].append(filename)
        elif any(term in filename_lower for term in ["facture", "devis", "invoice", "quote"]):
            classifications["Factures/Devis"].append(filename)
        elif any(
            term in filename_lower for term in ["photo", "image", ".jpg", ".jpeg", ".png", ".gif"]
        ):
            classifications["Photos/Images"].append(filename)
        elif any(
            term in filename_lower
            for term in ["lettre", "correspondence", ".docx", ".doc", "letter"]
        ):
            classifications["Lettres/Correspondance"].append(filename)
        elif any(term in filename_lower for term in [".eml", ".msg", "email"]):
            classifications["Emails"].append(filename)
        else:
            classifications["Autres"].append(filename)

    parts = ["## Classification des documents\n"]

    for category, files in classifications.items():
        if files:
            parts.append(f"### {category} ({len(files)})")
            for f in files:
                parts.append(f"- {f}")
            parts.append("")

    return "\n".join(parts) if any(classifications.values()) else "Aucun document à classifier."


def get_communications(application_id: str) -> str:
    """Get communications generated for this application (emails, SMS, letters).

    Use this tool when the user asks "what communications have been sent?"
    or wants to review generated messages.

    Args:
        application_id: The application ID.

    Returns:
        Formatted list of generated communications.
    """
    from ..config import load_settings
    from ..storage import load_application

    settings = load_settings()
    app_md = load_application(settings.app.storage_root, application_id)
    if not app_md:
        return f"Application {application_id} introuvable."

    # Check for communications in llm_outputs
    comms = []
    if app_md.llm_outputs:
        for section, subsections in app_md.llm_outputs.items():
            if (
                "communication" in section.lower()
                or "email" in section.lower()
                or "sms" in section.lower()
            ):
                if isinstance(subsections, dict):
                    for sub, output in subsections.items():
                        if output and isinstance(output, dict):
                            parsed = output.get("parsed", {})
                            if parsed:
                                comms.append(
                                    {
                                        "type": section,
                                        "subtype": sub,
                                        "content": parsed.get("message")
                                        or parsed.get("body")
                                        or str(parsed)[:200],
                                        "recipient": parsed.get("recipient")
                                        or parsed.get("to")
                                        or "N/A",
                                    }
                                )

    if not comms:
        return "Aucune communication générée pour cette application."

    parts = ["## Communications générées\n"]
    for idx, comm in enumerate(comms, 1):
        parts.append(f"{idx}. **{comm['type']} — {comm['subtype']}**")
        parts.append(f"   À : {comm['recipient']}")
        _content = _coerce_text(comm.get("content", ""))
        parts.append(f"   Message : {_content[:300]}")
        if len(_content) > 300:
            parts.append("   ...")
        parts.append("")

    return "\n".join(parts)


def get_document_sentiment(application_id: str) -> str:
    """Get sentiment analysis per document/section in the application.

    Use this tool when the user asks about the tone of generated communications,
    client sentiment, or emotional context of documents.

    Args:
        application_id: The application ID.

    Returns:
        Formatted sentiment analysis per document.
    """
    from ..config import load_settings
    from ..storage import load_application

    settings = load_settings()
    app_md = load_application(settings.app.storage_root, application_id)
    if not app_md:
        return f"Application {application_id} introuvable."

    # Overall sentiment from sentiment_analysis
    parts = ["## Analyse sentiment\n"]

    if app_md.sentiment_analysis:
        sa = app_md.sentiment_analysis
        parts.append("### Sentiment global")
        parts.append(f"- **Score** : {sa.get('score', '?')}/100")
        parts.append(f"- **Niveau** : {sa.get('level', '?')}")
        parts.append(f"- **Ton suggéré** : {sa.get('suggestedTone', '?')}")

        if sa.get("factors"):
            parts.append("\n### Facteurs")
            for factor in sa.get("factors", [])[:5]:
                parts.append(f"- {factor}")

        if sa.get("suggestions"):
            parts.append("\n### Suggestions de ton")
            for sugg in sa.get("suggestions", [])[:4]:
                parts.append(f"- {sugg}")

    # Per-document sentiment from markdown_pages or metadata
    doc_sentiments = []
    if app_md.markdown_pages:
        for page in app_md.markdown_pages:
            # Try to infer sentiment from page content (simple heuristic)
            markdown = _coerce_text(page.get("markdown", ""))[:500]
            score = 50  # Default neutral
            if any(
                word in markdown.lower()
                for word in ["regrettable", "problème", "erreur", "grave", "danger"]
            ):
                score = 30
            elif any(
                word in markdown.lower()
                for word in ["excellent", "approuvé", "satisfait", "positif"]
            ):
                score = 70

            if score != 50:  # Only include if not neutral
                doc_sentiments.append(
                    {
                        "file": page.get("file", "?"),
                        "score": score,
                        "level": "negative"
                        if score < 40
                        else "positive"
                        if score > 60
                        else "neutral",
                    }
                )

    if doc_sentiments:
        parts.append("\n### Sentiment par document")
        for ds in doc_sentiments[:5]:
            icon = (
                "😟" if ds["level"] == "negative" else "😊" if ds["level"] == "positive" else "😐"
            )
            parts.append(f"- {icon} {ds['file']}: {ds['score']}/100 ({ds['level']})")

    return "\n".join(parts) if parts else "Aucune analyse sentiment disponible."


def get_damage_areas_multimodal(application_id: str) -> str:
    """Get multimodal damage data including extracted damage areas and image descriptions.

    Use this tool for automotive/property claims when the user asks about
    "where is the damage?", damage locations, or wants a visual summary.

    Args:
        application_id: The application ID.

    Returns:
        Formatted damage areas with locations and images.
    """
    from ..config import load_settings
    from ..storage import load_application

    settings = load_settings()
    app_md = load_application(settings.app.storage_root, application_id)
    if not app_md:
        return f"Application {application_id} introuvable."

    # Extract damage areas from extracted_fields (automotive-specific)
    damage_areas = []
    if app_md.extracted_fields:
        for key, field in app_md.extracted_fields.items():
            if isinstance(field, dict):
                field_name = field.get("field_name", "")
                if "damage" in field_name.lower() or "area" in field_name.lower():
                    damage_areas.append(
                        {
                            "field": field_name,
                            "value": field.get("value"),
                            "confidence": field.get("confidence"),
                            "source_file": field.get("source_file"),
                        }
                    )

    if not damage_areas and not app_md.markdown_pages:
        return "Aucune donnée multimodal de dommage trouvée."

    parts = ["## Données multimodales — Dommages\n"]

    # Damage areas summary
    if damage_areas:
        parts.append("### Zones de dommage identifiées")
        for da in damage_areas[:10]:
            conf_icon = (
                "🟢" if da["confidence"] >= 0.9 else "🟡" if da["confidence"] >= 0.7 else "🔴"
            )
            parts.append(
                f"- {conf_icon} {da['field']}: {da['value']} ({da['confidence']:.0%}) — {da['source_file']}"
            )

    # Image descriptions for damage photos
    if app_md.markdown_pages:
        damage_images = []
        for page in app_md.markdown_pages:
            if page.get("file", "").lower().endswith((".jpg", ".jpeg", ".png")):
                markdown = page.get("markdown", "")
                if any(
                    word in markdown.lower()
                    for word in ["dommage", "damage", "cassé", "brisé", "endommagé"]
                ):
                    damage_images.append(
                        {
                            "file": page.get("file"),
                            "description": markdown[:300],
                        }
                    )

        if damage_images:
            parts.append(f"\n### Images de dommage ({len(damage_images)})")
            for img in damage_images[:5]:
                parts.append(f"- {img['file']}")
                parts.append(f"  {_coerce_text(img.get('description', ''))[:200]}...")

    return "\n".join(parts)


def get_page_reference(application_id: str, page_number: int) -> str:
    """Get the content of a specific page by page number.

    Use this tool when the user asks "what's on page 5?" or wants to reference
    a specific page of extracted content.

    Args:
        application_id: The application ID.
        page_number: The page number (1-indexed).

    Returns:
        Content of the specified page.
    """
    from ..config import load_settings
    from ..storage import load_application

    settings = load_settings()
    app_md = load_application(settings.app.storage_root, application_id)
    if not app_md:
        return f"Application {application_id} introuvable."

    if not app_md.markdown_pages:
        return "Aucune page trouvée. Lancez l'extraction d'abord."

    # Find page by page_number
    target_page = None
    for page in app_md.markdown_pages:
        if page.get("page_number") == page_number:
            target_page = page
            break

    if not target_page:
        total_pages = len(app_md.markdown_pages)
        return f"Page {page_number} non trouvée. Total pages : {total_pages}"

    markdown = target_page.get("markdown", "")
    file_ref = target_page.get("file", "?")

    # Format with page reference
    parts = [
        f"## Page {page_number} — {file_ref}\n",
        markdown,
    ]

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Phase 5 tools — Fabric Data Agent
# ---------------------------------------------------------------------------


def query_fabric_data(
    question: str,
    persona: str = "",
) -> str:
    """Query business data (claims history, amounts, volumes, statistics) via Fabric Data Agent.

    Use this tool when the user asks quantitative questions about claims data,
    settlement amounts, customer volumes, loss ratios, or any data that requires
    querying the enterprise data warehouse. Do NOT use for policy/coverage
    questions — use search_policies for those.

    Args:
        question: Natural language question about business data
            (e.g. 'Montant total sinistres DDE > 5000€ en 2025').
        persona: Optional persona context for better routing.

    Returns:
        Structured data response from the Fabric Data Agent, or a fallback
        message if the Data Agent is not configured.
    """
    from ..config import load_settings

    project_endpoint = load_settings().foundry.project_endpoint
    fabric_conn_name = os.getenv("FABRIC_CONNECTION_NAME", "")

    if not project_endpoint or not fabric_conn_name:
        logger.info(
            "Fabric Data Agent not configured — missing FOUNDRY_PROJECT_ENDPOINT or FABRIC_CONNECTION_NAME"
        )
        return (
            "Le Data Agent Fabric n'est pas configuré. "
            "Pour répondre aux questions sur les données métier (montants, volumes, statistiques), "
            "les variables FOUNDRY_PROJECT_ENDPOINT et FABRIC_CONNECTION_NAME doivent être définies. "
            "Contactez l'administrateur pour configurer la connexion Fabric dans le projet Foundry."
        )

    fabric_agent_name = "WorkbenchIQ-FabricQuery"
    started = time.perf_counter()
    with start_span(
        "fabric_data_agent.query",
        {
            "gen_ai.operation.name": "fabric_data_agent",
            "gen_ai.system": "foundry_agent_service",
            "gen_ai.agent.name": fabric_agent_name,
            "workbenchiq.persona": persona or None,
            "workbenchiq.fabric.connection": fabric_conn_name,
        },
        tracer_name="workbenchiq.fabric",
        kind="client",
    ) as span:
        try:
            from azure.identity import DefaultAzureCredential
            from azure.ai.projects import AIProjectClient
            from azure.ai.projects.models import (
                PromptAgentDefinition,
                MicrosoftFabricPreviewTool,
                FabricDataAgentToolParameters,
                ToolProjectConnection,
            )

            credential = DefaultAzureCredential()
            project = AIProjectClient(endpoint=project_endpoint, credential=credential)

            # Resolve the connection ID from the connection name
            fabric_connection = project.connections.get(fabric_conn_name)
            logger.debug("Fabric Data Agent: connection %s resolved", fabric_conn_name)

            # Create a temporary agent with the Fabric tool
            model = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME") or os.getenv(
                "AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5.4-mini"
            )
            agent = project.agents.create_version(
                agent_name=fabric_agent_name,
                definition=PromptAgentDefinition(
                    model=model,
                    instructions=(
                        "Tu es un assistant data pour les assurances. "
                        "Utilise le Fabric Data Agent pour répondre aux questions sur les données métier. "
                        "Réponds toujours en français avec des données structurées (tableaux, montants, pourcentages)."
                    ),
                    tools=[
                        MicrosoftFabricPreviewTool(
                            fabric_dataagent_preview=FabricDataAgentToolParameters(
                                project_connections=[
                                    ToolProjectConnection(project_connection_id=fabric_connection.id)
                                ]
                            )
                        )
                    ],
                ),
            )
            logger.debug(
                "Fabric Data Agent: temporary agent %s v%s created (model=%s)", agent.name, agent.version, model
            )
            span.set_attribute("gen_ai.agent.version", str(agent.version))

            try:
                # Send the query and force the Fabric tool to be used
                openai = project.get_openai_client()
                response = openai.responses.create(
                    tool_choice="required",
                    input=question,
                    extra_body={"agent_reference": {"name": agent.name, "type": "agent_reference"}},
                )
                result_text = response.output_text
            finally:
                # Clean up the temporary agent
                try:
                    project.agents.delete_version(agent_name=agent.name, agent_version=agent.version)
                    logger.debug("Fabric Data Agent: temporary agent %s v%s deleted", agent.name, agent.version)
                except Exception:
                    logger.warning(
                        "Fabric Data Agent: could not delete temporary agent %s v%s",
                        agent.name, agent.version, exc_info=True,
                    )

            span.set_attribute("workbenchiq.response_chars", len(result_text or ""))
            logger.info(
                "Fabric Data Agent query completed in %d ms (response_chars=%d)",
                (time.perf_counter() - started) * 1000, len(result_text or ""),
            )
            return result_text or "Aucune donnée retournée par le Data Agent Fabric."

        except ImportError:
            logger.warning("azure-ai-projects SDK not installed — Fabric Data Agent unavailable")
            record_span_error(span, "azure-ai-projects SDK not installed", error_type="ImportError")
            return (
                "Le SDK azure-ai-projects n'est pas installé. "
                "Installez-le avec: pip install azure-ai-projects"
            )
        except Exception as exc:
            logger.warning("Fabric Data Agent query failed: %s", exc, exc_info=True)
            record_span_error(span, exc)
            return (
                f"Erreur lors de l'interrogation du Data Agent Fabric : {exc}. "
                "Les données métier ne sont pas disponibles pour le moment."
            )


# ---------------------------------------------------------------------------
# Fraud Detection — 2-model pipeline
# Phase 1: vision model → image description + manipulation indicators
# Phase 2: reasoning model → cross-check declarations + overall fraud assessment
# ---------------------------------------------------------------------------


def _get_ef_value(app_md, keys: list[str], default: str = "") -> str:
    """Extract a value from application extracted_fields by trying multiple keys.

    Handles both plain keys and prefixed keys (llm_extracted:, cu_extracted:).
    Mirrors the frontend getFieldValue() logic.
    """
    ef = getattr(app_md, "extracted_fields", None) or {}
    # Build expanded key list: try plain, then prefixed variants
    prefixes = ["", "llm_extracted:", "cu_extracted:"]
    expanded_keys = []
    for key in keys:
        for prefix in prefixes:
            expanded_keys.append(f"{prefix}{key}")
    for key in expanded_keys:
        entry = ef.get(key)
        if entry is None:
            continue
        if isinstance(entry, dict):
            val = entry.get("value")
            if val is not None and str(val).strip():
                return str(val).strip()
        elif isinstance(entry, str) and entry.strip():
            return entry.strip()
    return default


def _parse_json_robust(content: str | None) -> dict:
    """Parse JSON from LLM output, handling missing braces and code blocks.

    Returns a dict on success or {"raw_response": ..., "parse_error": True} on failure.
    """
    import re

    if not content or not isinstance(content, str):
        return {"raw_response": str(content), "parse_error": True}

    text = content.strip()
    if not text:
        return {"raw_response": content, "parse_error": True}

    # 1. Direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. Code block extraction
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. Find any top-level JSON object
    match = re.search(r"(\{[\s\S]*\})", text)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            pass

    # 4. Wrap partial JSON (content starts with '"key":' without opening brace)
    if not text.startswith("{"):
        try:
            return json.loads("{" + text + "}")
        except (json.JSONDecodeError, ValueError):
            pass

    return {"raw_response": content, "parse_error": True}


WEBIQ_TOOLS = ("web", "news", "browse")
_WEBIQ_MAX_CHARS = 12000


def create_webiq_tool(settings) -> Any | None:
    """Return a Web IQ MCP tool (not connected), or None when no key / no ``mcp`` package."""
    import importlib.util

    from agent_framework import MCPStreamableHTTPTool

    webiq = settings.webiq
    if not webiq.enabled:
        return None
    if importlib.util.find_spec("mcp") is None:
        logger.warning("Web IQ disabled: the 'mcp' package is not installed")
        return None
    return MCPStreamableHTTPTool(
        name="webiq",
        url=webiq.mcp_url,
        tool_name_prefix="webiq",
        description="Microsoft Web IQ : recherche web, actualités et lecture d'URL publiques.",
        static_headers={"x-apikey": webiq.api_key},
        allowed_tools=WEBIQ_TOOLS,
        approval_mode="never_require",
        load_prompts=False,
        request_timeout=webiq.request_timeout_seconds,
    )


async def webiq_search(query: str, news: bool = False) -> str:
    """Search public sources with Microsoft Web IQ (web pages or recent news).

    Use this tool to verify facts about a claim: Cat-Nat decrees, weather
    events, Argus/market prices, regulatory changes or news. Always cite the
    source URLs returned.

    Args:
        query: Search query, e.g. "arrêté catastrophe naturelle inondation Nîmes juin 2026".
        news: True to search recent news articles instead of web pages.

    Returns:
        Short French passages with their source URLs.
    """
    from ..config import load_settings

    tool = create_webiq_tool(load_settings())
    if tool is None:
        return "Recherche web non disponible (Web IQ non configuré)."
    # Connect per call (~2-6 s) so questions that never search pay nothing.
    wanted = {
        "query": query, "maxResults": 5, "language": "fr", "region": "FR",
        "contentFormat": "passage", "maxLength": 1500,
    }
    try:
        async with tool:
            target = "webiq_news" if news else "webiq_web"
            func = next(f for f in tool.functions if f.name == target)
            accepted = func.parameters().get("properties", {})
            result = await func.invoke(arguments={k: v for k, v in wanted.items() if k in accepted})
    except Exception as exc:
        logger.warning("Web IQ search failed: %r", exc)
        return "Recherche web momentanément indisponible."
    text = "\n\n".join(t for t in (getattr(c, "text", None) for c in result or []) if t)
    try:
        payload = json.loads(text)
        items = payload.get("newsResults" if news else "webResults") or []
        text = "\n\n".join(
            f"### {it.get('title', '')}\nSource : {it.get('url', '')}\n{it.get('content', '')}"
            for it in items
        )
    except (ValueError, AttributeError):
        pass  # keep the raw text when Web IQ changes its response shape
    return text[:_WEBIQ_MAX_CHARS] or "Aucun résultat web."


def resolve_web_tool(settings):
    """Web IQ when configured, otherwise the legacy Bing-backed ``web_search``."""
    return webiq_search if create_webiq_tool(settings) is not None else web_search


def web_search(query: str, claim_type: str = "auto", location: str = "", date: str = "") -> str:
    """Search the web for insurance-relevant information using Bing WebSearch.

    Use this tool when the user asks to verify facts about a claim, check
    weather events, Cat-Nat decrees, market prices (Argus, FFB index),
    regulatory changes, or any question that requires up-to-date public
    information to complement policy data.

    Args:
        query: Natural language search query (e.g. "arrêté Cat-Nat inondation
               Nîmes juin 2024", "cote Argus Peugeot 308 2019").
        claim_type: Type of insurance claim for context (auto, habitation,
                    santé, hypothécaire).
        location: Optional geographic location to focus the search.
        date: Optional date or date range relevant to the query.

    Returns:
        Formatted web search results with findings, sources, and assessment.
    """
    from ..config import load_settings

    settings = load_settings()
    fraud_settings = settings.fraud_detection

    if not fraud_settings.web_intelligence_enabled or not fraud_settings.foundry_project_endpoint:
        return "Recherche web non disponible (Web Intelligence Agent non configuré)."

    result = _run_web_intelligence(
        fraud_settings,
        claim_date=date,
        claim_location=location,
        claim_nature=query,
        claim_type=claim_type,
        declared_amount="",
    )

    if not result or result.get("error"):
        error_msg = result.get("error", "Erreur inconnue") if result else "Pas de résultat"
        return f"Recherche web échouée : {error_msg}"

    parts = []
    # Overall assessment
    assessment = result.get("overall_assessment", "")
    if assessment:
        parts.append(f"### Synthèse\n{assessment}")

    # Event verification
    event_verified = result.get("event_verified")
    if event_verified is not None:
        status = "✅ Confirmé" if event_verified else "❌ Non confirmé"
        parts.append(f"**Événement vérifié** : {status}")

    # Individual findings
    findings = result.get("findings", [])
    if findings:
        parts.append("\n### Résultats de recherche")
        for f in findings:
            if isinstance(f, dict):
                parts.append(
                    f"- **{f.get('type', 'Info')}** : {f.get('detail', f.get('description', str(f)))}"
                )
            else:
                parts.append(f"- {f}")

    # Source URLs
    sources = result.get("source_urls", [])
    if sources:
        parts.append("\n### Sources")
        for url in sources[:10]:
            parts.append(f"- {url}")

    return "\n".join(parts) if parts else "Aucun résultat pertinent trouvé."


def analyze_image_fraud(
    application_id: str,
    filename: str = "",
    declaration_text: str = "",
    reasoning_effort: str = "medium",
) -> str:
    """Analyze claim photos for manipulation, AI generation, and declaration consistency.

    Parallel orchestrator pipeline:
    - Branch A (vision model): describe each image + detect manipulation artefacts
    - Branch B (context):        gather app summary, customer history, policy articles
    -                            and comparable damage statistics via Fabric Data Agent
    - Merge   (reasoning model): cross-reference all branches → fraud risk assessment

    Use this tool when the user asks about image authenticity, photo
    manipulation, or whether a claim declaration matches the evidence.

    Args:
        application_id: The application/claim ID.
        filename: Specific image filename to analyze (if empty, analyzes all images).
        declaration_text: Customer's written claim declaration to cross-check
                         against photos. If empty, uses the extracted document text.
        reasoning_effort: Reasoning effort for the reasoning model (low, medium, high).
                         Higher effort = more thorough but slower analysis.

    Returns:
        JSON fraud analysis with authenticity scores, manipulation indicators,
        declaration cross-check results, and overall fraud risk.
    """
    # Detect whether we're already inside an async event loop (e.g. FastAPI)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # Called from async context (FastAPI) — can't nest event loops.
        # Fall back to synchronous ThreadPoolExecutor-based parallelism.
        raw_result = _fraud_orchestrator_sync(
            application_id, filename, declaration_text, reasoning_effort
        )
    else:
        # Called from sync context (Agent Framework tool) — use asyncio
        new_loop = asyncio.new_event_loop()
        try:
            raw_result = new_loop.run_until_complete(
                _fraud_orchestrator(application_id, filename, declaration_text, reasoning_effort)
            )
        finally:
            new_loop.close()

    # Reconcile the raw model output so verdicts/score/band stay coherent. The
    # orchestrators may also return a plain error string (e.g. "… introuvable.");
    # only structured JSON objects are reconciled, anything else is passed through.
    try:
        parsed = json.loads(raw_result)
    except (json.JSONDecodeError, TypeError):
        return raw_result
    if not isinstance(parsed, dict):
        return raw_result
    return json.dumps(_reconcile_fraud_assessment(parsed), ensure_ascii=False, indent=2)


async def _fraud_orchestrator(
    application_id: str,
    filename: str,
    declaration_text: str,
    reasoning_effort: str,
) -> str:
    """Async fraud orchestrator — runs vision, context, and policies in parallel."""
    from ..config import load_settings
    from ..storage import load_application

    settings = load_settings()
    fraud_settings = settings.fraud_detection

    if not fraud_settings.enabled:
        return "L'analyse anti-fraude est désactivée."

    app_md = load_application(settings.app.storage_root, application_id)
    if not app_md:
        return f"Application {application_id} introuvable."

    prompts = _load_fraud_prompts(settings.app.prompts_root, brand=settings.brand_name)
    if not prompts:
        return "Prompts de détection de fraude non disponibles."

    decl_text = declaration_text or app_md.document_markdown or ""
    if not decl_text:
        decl_text = "Déclaration non disponible."

    # Extract real claim metadata from extracted_fields
    claim_date = _get_ef_value(app_md, ["DateSinistre", "DateDeclaration"], "non spécifiée")
    declared_amount = _get_ef_value(
        app_md, ["MontantEstime", "MontantTotal", "TotalIncurred"], "non spécifié"
    )

    # Collect image files
    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    image_files = []
    for f in app_md.files:
        fname = f.filename
        ext = os.path.splitext(fname)[1].lower()
        if ext in image_extensions:
            if filename and fname != filename:
                continue
            image_files.append(fname)

    if not image_files:
        return "Aucune image trouvée dans ce dossier à analyser."

    # ── Branch A: Vision — analyze all images concurrently ──
    async def _vision_branch() -> list[dict]:
        # Cap concurrent vision calls to avoid 429s on the vision deployment
        # (matches the codebase-wide max_workers=4 convention). Each image is
        # independent, so load + analyze run off the event loop in parallel.
        sem = asyncio.Semaphore(4)

        async def _analyze_one(fname: str) -> dict:
            async with sem:
                file_bytes = await asyncio.to_thread(
                    _load_file_bytes, settings, application_id, fname
                )
                if not file_bytes:
                    return {"filename": fname, "error": "Impossible de charger le fichier"}
                result = await asyncio.to_thread(
                    _analyze_single_image,
                    settings,
                    fraud_settings,
                    prompts,
                    file_bytes,
                    fname,
                    claim_type=app_md.persona or "sinistre",
                    claim_date=claim_date,
                )
                return {"filename": fname, **result}

        # Preserve partial results: a per-image failure is captured, not fatal.
        settled = await asyncio.gather(
            *(_analyze_one(fname) for fname in image_files),
            return_exceptions=True,
        )
        results = []
        for fname, outcome in zip(image_files, settled):
            if isinstance(outcome, Exception):
                logger.warning("Vision analysis failed for %s: %s", fname, outcome)
                results.append({"filename": fname, "error": str(outcome)})
            else:
                results.append(outcome)
        return results

    # ── Branch B: Context gathering (app summary + customer history) ──
    async def _context_branch() -> dict:
        context = {}
        try:
            summary = await asyncio.to_thread(get_application_summary, application_id)
            context["application_summary"] = summary
        except Exception as exc:
            logger.warning("Context: app summary failed: %s", exc)
            context["application_summary"] = ""

        # Customer history via customer360 (if customer_id available)
        try:
            customer_id = _extract_customer_id(app_md)
            if customer_id:
                from ..customer360 import get_customer_360

                c360 = await asyncio.to_thread(
                    get_customer_360, settings.app.storage_root, customer_id
                )
                if c360:
                    context["customer_history"] = _format_customer_history(c360)
                else:
                    context["customer_history"] = ""
            else:
                context["customer_history"] = ""
        except Exception as exc:
            logger.warning("Context: customer360 failed: %s", exc)
            context["customer_history"] = ""

        # Comparable damage statistics — skipped in interactive chat (Fabric SDK too slow)
        context["comparable_stats"] = ""

        return context

    # ── Branch C: Policy search (applicable fraud + coverage articles) ──
    async def _policy_branch() -> str:
        try:
            claim_type = app_md.persona or "sinistre"
            policy_result = await asyncio.to_thread(
                search_policies,
                f"fraude assurance {claim_type} exclusions indicateurs suspicion",
                "fraud_detection",
                5,
            )
            return policy_result
        except Exception as exc:
            logger.warning("Context: policy search failed: %s", exc)
            return ""

    # ── Branch D: Web Intelligence (Web IQ, or Foundry Agent + Bing WebSearch) ──
    async def _web_intelligence_branch() -> dict:
        if not _web_intelligence_available(settings):
            return {}
        try:
            lieu = _get_ef_value(app_md, ["LieuSinistre"], "")
            adresse = _get_ef_value(app_md, ["AdresseAssure", "Adresse", "Ville"], "")
            claim_location = f"{lieu}, {adresse}".strip(", ") if lieu or adresse else ""
            return await asyncio.to_thread(
                _run_claim_web_intelligence,
                settings,
                claim_date=claim_date,
                claim_location=claim_location,
                claim_nature=_get_ef_value(
                    app_md, ["NatureSinistre", "CauseOfLoss", "DescriptionSinistre"], ""
                ),
                claim_type=app_md.persona or "sinistre",
                declared_amount=declared_amount,
            )
        except Exception as exc:
            logger.warning("Web intelligence branch failed: %s", exc)
            return {"error": str(exc)}

    # ── Run all branches in parallel ──
    vision_results, context_data, policy_data, web_intel = await asyncio.gather(
        _vision_branch(),
        _context_branch(),
        _policy_branch(),
        _web_intelligence_branch(),
    )

    # ── Merge: reasoning — cross-reference all data ──
    declaration_result = {}
    if decl_text and decl_text != "Déclaration non disponible.":
        try:
            declaration_result = _cross_check_declaration(
                settings,
                fraud_settings,
                prompts,
                image_analyses=vision_results,
                declaration_text=decl_text,
                claim_type=app_md.persona or "sinistre",
                reasoning_effort=reasoning_effort,
                claim_date=claim_date,
                declared_amount=declared_amount,
            )
        except Exception as exc:
            logger.warning("Declaration cross-check failed: %s", exc)
            declaration_result = {"error": str(exc), "parse_error": True}

    # Overall assessment — enriched with context from all branches
    try:
        overall = _assess_overall_fraud(
            settings,
            fraud_settings,
            prompts,
            vision_results,
            declaration_result,
            context_data=context_data,
            policy_data=policy_data,
            web_intelligence=web_intel,
            reasoning_effort=reasoning_effort,
        )
    except Exception as exc:
        logger.warning("Overall fraud assessment failed: %s", exc)
        overall = {"error": str(exc), "parse_error": True}

    return json.dumps(
        {
            "application_id": application_id,
            "image_analyses": vision_results,
            "declaration_verification": declaration_result,
            "overall_assessment": overall,
            "web_intelligence": web_intel if web_intel else None,
        },
        ensure_ascii=False,
        indent=2,
    )


def _fraud_orchestrator_sync(
    application_id: str,
    filename: str,
    declaration_text: str,
    reasoning_effort: str,
) -> str:
    """Sync fraud orchestrator for FastAPI context — uses ThreadPoolExecutor for parallelism."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from ..config import load_settings
    from ..storage import load_application

    settings = load_settings()
    fraud_settings = settings.fraud_detection

    if not fraud_settings.enabled:
        return "L'analyse anti-fraude est désactivée."

    app_md = load_application(settings.app.storage_root, application_id)
    if not app_md:
        return f"Application {application_id} introuvable."

    prompts = _load_fraud_prompts(settings.app.prompts_root, brand=settings.brand_name)
    if not prompts:
        return "Prompts de détection de fraude non disponibles."

    decl_text = declaration_text or app_md.document_markdown or ""
    if not decl_text:
        decl_text = "Déclaration non disponible."

    # Extract real claim metadata from extracted_fields
    claim_date = _get_ef_value(app_md, ["DateSinistre", "DateDeclaration"], "non spécifiée")
    declared_amount = _get_ef_value(
        app_md, ["MontantEstime", "MontantTotal", "TotalIncurred"], "non spécifié"
    )

    image_extensions = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    image_files = []
    for f in app_md.files:
        fname = f.filename
        ext = os.path.splitext(fname)[1].lower()
        if ext in image_extensions:
            if filename and fname != filename:
                continue
            image_files.append(fname)

    if not image_files:
        return "Aucune image trouvée dans ce dossier à analyser."

    # ── Parallel execution via ThreadPoolExecutor ──
    vision_results = []
    context_data = {}
    policy_data = ""

    with ThreadPoolExecutor(max_workers=8) as executor:
        # Submit vision tasks
        vision_futures = {}
        for fname in image_files:
            file_bytes = _load_file_bytes(settings, application_id, fname)
            if not file_bytes:
                vision_results.append(
                    {"filename": fname, "error": "Impossible de charger le fichier"}
                )
                continue
            future = executor.submit(
                _analyze_single_image,
                settings,
                fraud_settings,
                prompts,
                file_bytes,
                fname,
                claim_type=app_md.persona or "sinistre",
                claim_date=claim_date,
            )
            vision_futures[future] = fname

        # Submit context tasks
        ctx_summary_future = executor.submit(get_application_summary, application_id)

        customer_id = _extract_customer_id(app_md)
        ctx_history_future = None
        if customer_id:
            from ..customer360 import get_customer_360

            ctx_history_future = executor.submit(
                get_customer_360, settings.app.storage_root, customer_id
            )

        claim_type = app_md.persona or "sinistre"
        # Submit context tasks — skip Fabric (too slow for interactive chat, not critical for fraud)
        ctx_fabric_future = None

        # Submit policy search
        policy_future = executor.submit(
            search_policies,
            f"fraude assurance {claim_type} exclusions indicateurs suspicion",
            "fraud_detection",
            5,
        )

        # Submit web intelligence (if enabled)
        web_intel_future = None
        if _web_intelligence_available(settings):
            # Build precise location from multiple fields
            lieu = _get_ef_value(app_md, ["LieuSinistre"], "")
            adresse = _get_ef_value(app_md, ["AdresseAssure", "Adresse", "Ville"], "")
            claim_location = f"{lieu}, {adresse}".strip(", ") if lieu or adresse else ""
            web_intel_future = executor.submit(
                _run_claim_web_intelligence,
                settings,
                claim_date=claim_date,
                claim_location=claim_location,
                claim_nature=_get_ef_value(
                    app_md, ["NatureSinistre", "CauseOfLoss", "DescriptionSinistre"], ""
                ),
                claim_type=app_md.persona or "sinistre",
                declared_amount=declared_amount,
            )

        # Collect vision results
        for future in as_completed(vision_futures):
            fname = vision_futures[future]
            try:
                result = future.result()
                vision_results.append({"filename": fname, **result})
            except Exception as exc:
                logger.warning("Vision analysis failed for %s: %s", fname, exc)
                vision_results.append({"filename": fname, "error": str(exc)})

        # Collect context
        try:
            context_data["application_summary"] = ctx_summary_future.result()
        except Exception as exc:
            logger.warning("Context: app summary failed: %s", exc)
            context_data["application_summary"] = ""

        if ctx_history_future:
            try:
                c360 = ctx_history_future.result()
                context_data["customer_history"] = _format_customer_history(c360) if c360 else ""
            except Exception as exc:
                logger.warning("Context: customer360 failed: %s", exc)
                context_data["customer_history"] = ""
        else:
            context_data["customer_history"] = ""

        try:
            fabric_result = ctx_fabric_future.result() if ctx_fabric_future else ""
            context_data["comparable_stats"] = fabric_result if fabric_result else ""
        except Exception as exc:
            logger.debug("Context: fabric data unavailable: %s", exc)
            context_data["comparable_stats"] = ""

        try:
            policy_data = policy_future.result()
        except Exception as exc:
            logger.warning("Context: policy search failed: %s", exc)
            policy_data = ""

        # Collect web intelligence
        web_intel = {}
        if web_intel_future:
            try:
                web_intel = web_intel_future.result()
            except Exception as exc:
                logger.warning("Web intelligence failed: %s", exc)
                web_intel = {"error": str(exc)}

    # ── Merge: reasoning ──
    declaration_result = {}
    if decl_text and decl_text != "Déclaration non disponible.":
        try:
            declaration_result = _cross_check_declaration(
                settings,
                fraud_settings,
                prompts,
                image_analyses=vision_results,
                declaration_text=decl_text,
                claim_type=app_md.persona or "sinistre",
                reasoning_effort=reasoning_effort,
                claim_date=claim_date,
                declared_amount=declared_amount,
            )
        except Exception as exc:
            logger.warning("Declaration cross-check failed: %s", exc)
            declaration_result = {"error": str(exc), "parse_error": True}

    try:
        overall = _assess_overall_fraud(
            settings,
            fraud_settings,
            prompts,
            vision_results,
            declaration_result,
            context_data=context_data,
            policy_data=policy_data,
            web_intelligence=web_intel,
            reasoning_effort=reasoning_effort,
        )
    except Exception as exc:
        logger.warning("Overall fraud assessment failed: %s", exc)
        overall = {"error": str(exc), "parse_error": True}

    return json.dumps(
        {
            "application_id": application_id,
            "image_analyses": vision_results,
            "declaration_verification": declaration_result,
            "overall_assessment": overall,
            "web_intelligence": web_intel if web_intel else None,
        },
        ensure_ascii=False,
        indent=2,
    )


def _extract_customer_id(app_md) -> str | None:
    """Extract customer ID from application metadata if available."""
    if hasattr(app_md, "customer_id") and app_md.customer_id:
        return app_md.customer_id
    # Try to find it in extracted fields
    if app_md.extracted_fields:
        for key, val in app_md.extracted_fields.items():
            if isinstance(val, dict) and "customer" in key.lower():
                return val.get("value", "")
    return None


def _format_customer_history(c360) -> str:
    """Format Customer360 data as context for fraud reasoning."""
    parts = [f"Client : {c360.customer.name} (ID: {c360.customer.id})"]
    parts.append(f"Risque : {c360.customer.risk_level}")
    parts.append(f"Client depuis : {c360.customer.member_since}")
    if c360.customer.tags:
        parts.append(f"Tags : {', '.join(c360.customer.tags)}")
    if c360.applications:
        claims = [a for a in c360.applications if a.get("persona", "").endswith("claims")]
        parts.append(f"Dossiers total : {len(c360.applications)}, dont sinistres : {len(claims)}")
        recent_claims = claims[:5]
        for claim in recent_claims:
            parts.append(
                f"  - {claim.get('id', '?')} : {claim.get('status', '?')} "
                f"({claim.get('persona', '?')})"
            )
    return "\n".join(parts)


def _load_fraud_prompts(prompts_root: str, brand: str = "") -> dict:
    """Load fraud detection prompts from JSON file, substituting {brand}."""
    if not brand:
        from ..config import load_settings

        brand = load_settings().brand_name
    path = os.path.join(prompts_root, "fraud-detection-prompts.json")
    if not os.path.exists(path):
        logger.warning("Fraud detection prompts not found at %s", path)
        return {}
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().replace("{brand}", brand)
        return json.loads(raw)


def _web_intelligence_available(settings) -> bool:
    fraud_settings = settings.fraud_detection
    return create_webiq_tool(settings) is not None or bool(
        fraud_settings.web_intelligence_enabled and fraud_settings.foundry_project_endpoint
    )


def _run_claim_web_intelligence(settings, **claim) -> dict:
    """Branch D dispatcher: Microsoft Web IQ when configured, else the Foundry Bing agent."""
    if create_webiq_tool(settings) is not None:
        return _run_webiq_intelligence(settings, **claim)
    return _run_web_intelligence(settings.fraud_detection, **claim)


def _run_webiq_intelligence(
    settings,
    claim_date: str,
    claim_location: str,
    claim_nature: str,
    claim_type: str,
    declared_amount: str,
) -> dict:
    """Branch D via Microsoft Web IQ: weather, Cat-Nat decrees and local news at the claim date.

    Runs a few targeted Web IQ searches, then asks the fraud model to turn the
    passages into the same structured result as the Foundry agent path.
    """
    from ..openai_client import chat_completion

    fraud_settings = settings.fraud_detection
    place = claim_location or "France"
    when = claim_date if claim_date and claim_date != "non spécifiée" else ""
    nature = (claim_nature or claim_type or "sinistre")[:120]
    queries = [
        (f"météo {place} {when} tempête pluie vent Météo-France".strip(), False),
        (f"arrêté catastrophe naturelle {place} {when}".strip(), False),
        (f"{nature} {place} {when}".strip(), True),
    ]

    async def _search_all():
        return await asyncio.gather(*(webiq_search(q, news=n) for q, n in queries))

    started = time.perf_counter()
    try:
        passages = asyncio.run(_search_all())
    except Exception as exc:
        logger.warning("Web IQ fraud branch failed: %r", exc)
        return {"error": f"Web IQ indisponible: {exc}"}

    corpus = "\n\n".join(
        f"=== Recherche : {q} ===\n{p}" for (q, _), p in zip(queries, passages)
    )[:12000]
    source_urls = list(dict.fromkeys(re.findall(r"Source : (https?://\S+)", corpus)))[:10]
    messages = [
        {
            "role": "system",
            "content": (
                "Tu es un analyste anti-fraude assurance. À partir UNIQUEMENT des passages web fournis, "
                "vérifie si l'événement déclaré (météo, catastrophe naturelle, fait local) est confirmé "
                "à la date et au lieu du sinistre. N'invente aucune source. Réponds en JSON : "
                '{"event_verified": true|false|null, "confidence": 0.0-1.0, '
                '"findings": [{"title": str, "summary": str, "source_url": str, "supports_claim": true|false|null}], '
                '"overall_assessment": str}. Rédige en français.'
            ),
        },
        {
            "role": "user",
            "content": (
                f"Sinistre : {claim_type} — {nature}\nLieu : {place}\nDate déclarée : {when or 'non précisée'}\n"
                f"Montant déclaré : {declared_amount}\n\nPassages Web IQ :\n{corpus}"
            ),
        },
    ]
    try:
        raw = chat_completion(
            settings.openai,
            messages,
            max_tokens=2000,
            temperature=0.0,
            deployment_override=fraud_settings.deployment_name,
            model_override=fraud_settings.model_name,
            response_format="json_object",
        )
        parsed = _parse_json_robust(raw.get("content", ""))
    except Exception as exc:
        logger.warning("Web IQ fraud synthesis failed: %r", exc)
        return {"error": f"Synthèse Web IQ indisponible: {exc}"}
    if parsed.get("parse_error"):
        parsed = {"overall_assessment": corpus[:1500], "findings": []}
    parsed["source_urls"] = source_urls
    parsed["provider"] = "webiq"
    logger.info(
        "Web IQ fraud branch completed: duration_ms=%d sources=%d",
        (time.perf_counter() - started) * 1000, len(source_urls),
    )
    return parsed


def _run_web_intelligence(
    fraud_settings,
    claim_date: str,
    claim_location: str,
    claim_nature: str,
    claim_type: str,
    declared_amount: str,
) -> dict:
    """Branch D: Query Foundry Agent Service with WebSearchTool for claim verification.

    Creates a query from claim context and sends it to a persistent Foundry agent
    that has Bing WebSearch enabled. Returns structured findings with source URLs.
    """
    try:
        from azure.identity import DefaultAzureCredential
        from azure.ai.projects import AIProjectClient
    except ImportError:
        logger.warning("azure-ai-projects not installed — web intelligence disabled")
        return {}

    agent_name = fraud_settings.web_intelligence_agent_name
    started = time.perf_counter()
    # The claim location (an address) is deliberately not exported as a span attribute.
    with start_span(
        "web_intelligence.query",
        {
            "gen_ai.operation.name": "web_intelligence",
            "gen_ai.system": "foundry_agent_service",
            "gen_ai.agent.name": agent_name,
            "workbenchiq.claim_type": claim_type,
            "workbenchiq.claim_nature": (claim_nature or "unknown")[:100],
            "workbenchiq.agent_name": agent_name,
        },
        tracer_name="workbenchiq.web_intelligence",
        kind="client",
    ) as span:
        logger.debug("Web intelligence: querying Foundry agent %s (claim_type=%s)", agent_name, claim_type)
        try:
            project = AIProjectClient(
                endpoint=fraud_settings.foundry_project_endpoint,
                credential=DefaultAzureCredential(),
            )
            openai_client = project.get_openai_client()

            # Build a focused query from claim context
            query_parts = [f"Vérification sinistre assurance {claim_type}"]
            if claim_nature:
                query_parts.append(f"Nature: {claim_nature}")
            if claim_location:
                query_parts.append(f"Lieu: {claim_location}")
            if claim_date and claim_date != "non spécifiée":
                query_parts.append(f"Date: {claim_date}")
            if declared_amount and declared_amount != "non spécifié":
                query_parts.append(f"Montant déclaré: {declared_amount}")

            query = ". ".join(query_parts) + (
                ". Recherche SPÉCIFIQUEMENT pour cette commune et cette date : "
                "1) Arrêté Cat-Nat publié au JO couvrant cette commune à cette date. "
                "2) Bulletins météo Météo-France pour cette zone et cette période. "
                "3) Articles de presse locale confirmant l'événement. "
                "4) Indices de référence (FFB, Argus) pertinents pour le montant. "
                "Retourne un JSON avec event_verified (true/false), confidence (0.0-1.0), "
                "findings[] (chaque finding avec title, summary, source_url, supports_claim), "
                "source_urls[], et overall_assessment. "
                "Sois PRÉCIS : cite les numéros d'arrêtés, les communes listées, les dates exactes."
            )

            response = openai_client.responses.create(
                input=query,
                extra_body={
                    "agent_reference": {
                        "name": agent_name,
                        "type": "agent_reference",
                    }
                },
            )

            result_text = response.output_text or ""
            # Extract URL citations from response
            citations = []
            for item in response.output or []:
                if getattr(item, "type", None) == "message":
                    for content_block in getattr(item, "content", []):
                        if getattr(content_block, "type", None) == "output_text":
                            for annotation in getattr(content_block, "annotations", []):
                                if getattr(annotation, "type", None) == "url_citation":
                                    url = getattr(annotation, "url", "")
                                    if url:
                                        citations.append(url)

            # Try to parse as JSON, fallback to text summary
            parsed = _parse_json_robust(result_text)
            if parsed.get("parse_error"):
                parsed = {
                    "overall_assessment": result_text[:2000],
                    "findings": [],
                }
            parsed["source_urls"] = citations

            findings = parsed.get("findings")
            findings_count = len(findings) if isinstance(findings, list) else 0
            span.set_attribute("workbenchiq.citations_count", len(citations))
            span.set_attribute("workbenchiq.event_verified", str(parsed.get("event_verified", "unknown")))
            span.set_attribute("workbenchiq.findings_count", findings_count)
            logger.info(
                "Web intelligence completed: agent=%s duration_ms=%d citations=%d findings=%d",
                agent_name, (time.perf_counter() - started) * 1000, len(citations), findings_count,
            )
            return parsed

        except Exception as exc:
            logger.warning("Foundry web intelligence agent call failed: %s", exc)
            record_span_error(span, exc)
            return {"error": str(exc)}


def _load_file_bytes(settings, application_id: str, filename: str) -> bytes | None:
    """Load file bytes from storage (Azure Blob or local)."""
    from ..storage import load_file

    try:
        return load_file(settings.app.storage_root, application_id, filename)
    except Exception as exc:
        logger.warning("Failed to load file %s/%s: %s", application_id, filename, exc)
        return None


def _analyze_single_image(
    settings,
    fraud_settings,
    prompts: dict,
    file_bytes: bytes,
    filename: str,
    claim_type: str,
    claim_date: str,
    reasoning_effort: str = "medium",
) -> dict:
    """Phase 1: Describe image + detect manipulation artefacts using the vision model."""
    import base64
    from ..openai_client import chat_completion

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

    auth_prompts = prompts.get("image_authenticity", {})
    system_prompt = auth_prompts.get(
        "system_prompt", "Analyse cette image pour détecter des fraudes."
    )
    user_template = auth_prompts.get("user_prompt_template", "Analyse cette image: {filename}")

    # Use .replace() instead of .format() — templates contain literal {/} in JSON examples
    user_text = (
        user_template.replace("{filename}", filename)
        .replace("{claim_type}", claim_type)
        .replace("{claim_date}", claim_date)
    )

    messages = [
        {"role": "system", "content": system_prompt},
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
        max_tokens=2000,
        temperature=0.0,
        deployment_override=fraud_settings.vision_deployment_name,
        model_override=fraud_settings.vision_model_name,
        response_format="json_object",
    )

    content = raw.get("content", "")
    if not content:
        return {"error": "Réponse vide du modèle de vision", "parse_error": True}
    return _parse_json_robust(content)


def _cross_check_declaration(
    settings,
    fraud_settings,
    prompts: dict,
    image_analyses: list,
    declaration_text: str,
    claim_type: str,
    reasoning_effort: str = "medium",
    claim_date: str = "non spécifiée",
    declared_amount: str = "non spécifié",
) -> dict:
    """Phase 2: Cross-check declaration against image descriptions using the reasoning model.

    Text-only — no images sent. Uses the image descriptions produced by Phase 1
    (vision model) to reason about inconsistencies with the customer declaration.
    """
    from ..openai_client import chat_completion

    decl_prompts = prompts.get("declaration_cross_check", {})
    system_prompt = decl_prompts.get(
        "system_prompt", "Compare la déclaration avec les descriptions d'images."
    )
    user_template = decl_prompts.get("user_prompt_template", "Vérifie: {declaration_text}")

    # Build image descriptions summary from Phase 1 results
    image_descriptions = []
    for img in image_analyses:
        fname = img.get("filename", "inconnu")
        if img.get("error"):
            image_descriptions.append(f"- {fname} : erreur d'analyse ({img['error']})")
        else:
            score = img.get("authenticity_score", "N/A")
            quality = img.get("image_quality_notes", "")
            indicators = img.get("manipulation_indicators", [])
            indicator_summary = (
                "; ".join(
                    f"{ind.get('type', '?')} ({ind.get('severity', '?')}): {ind.get('description', '')}"
                    for ind in indicators
                )
                if indicators
                else "aucun indicateur de manipulation"
            )
            image_descriptions.append(
                f"- {fname} : authenticité {score}, {quality}. Indicateurs : {indicator_summary}"
            )
    image_desc_text = (
        "\n".join(image_descriptions)
        if image_descriptions
        else "Aucune analyse d'image disponible."
    )

    # Use .replace() instead of .format() — templates contain literal {/} in JSON examples
    user_text = (
        user_template.replace("{declaration_text}", declaration_text[:4000])
        .replace("{claim_type}", claim_type)
        .replace("{claim_date}", claim_date)
        .replace("{declared_amount}", declared_amount)
        .replace("{image_count}", str(len(image_analyses)))
    )
    # Append image descriptions for reasoning context
    user_text += f"\n\n--- DESCRIPTIONS DES IMAGES (analyse vision) ---\n{image_desc_text}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]

    raw = chat_completion(
        settings.openai,
        messages,
        max_tokens=2000,
        temperature=0.0,
        deployment_override=fraud_settings.deployment_name,
        model_override=fraud_settings.model_name,
        reasoning_effort=reasoning_effort,
        response_format="json_object",
    )

    content = raw.get("content", "")
    return _parse_json_robust(content)


def _assess_overall_fraud(
    settings,
    fraud_settings,
    prompts: dict,
    image_results: list,
    declaration_result: dict,
    context_data: dict | None = None,
    policy_data: str = "",
    web_intelligence: dict | None = None,
    reasoning_effort: str = "medium",
) -> dict:
    """Consolidate all parallel branches into overall fraud assessment.

    Receives enriched context from the orchestrator:
    - image_results: Phase 1 vision descriptions
    - declaration_result: Phase 2 declaration cross-check
    - context_data: app summary, customer history, comparable damage stats
    - policy_data: relevant fraud policy articles
    - web_intelligence: web search findings (Cat-Nat, météo, regulatory)
    """
    from ..openai_client import chat_completion

    assess_prompts = prompts.get("overall_assessment", {})
    system_prompt = assess_prompts.get("system_prompt", "Consolide les résultats anti-fraude.")
    user_template = assess_prompts.get("user_prompt_template", "{image_results_json}")

    # Use .replace() instead of .format() — templates contain literal {/} in JSON examples
    user_text = user_template.replace(
        "{image_results_json}", json.dumps(image_results, ensure_ascii=False, indent=2)
    ).replace(
        "{declaration_result_json}", json.dumps(declaration_result, ensure_ascii=False, indent=2)
    )

    # Enrich with context from parallel branches
    enrichment_parts = []
    if context_data:
        if context_data.get("application_summary"):
            enrichment_parts.append(
                f"--- RÉSUMÉ DU DOSSIER ---\n{context_data['application_summary']}"
            )
        if context_data.get("customer_history"):
            enrichment_parts.append(
                f"--- HISTORIQUE CLIENT ---\n{context_data['customer_history']}"
            )
        if context_data.get("comparable_stats"):
            enrichment_parts.append(
                f"--- STATISTIQUES SINISTRES COMPARABLES ---\n{context_data['comparable_stats']}"
            )
    if policy_data:
        enrichment_parts.append(f"--- ARTICLES DE POLICE APPLICABLES ---\n{policy_data}")
    if web_intelligence and not web_intelligence.get("error"):
        enrichment_parts.append(
            f"--- VÉRIFICATION WEB (sources internet) ---\n{json.dumps(web_intelligence, ensure_ascii=False, indent=2)}"
        )
    if enrichment_parts:
        user_text += "\n\n" + "\n\n".join(enrichment_parts)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_text},
    ]

    raw = chat_completion(
        settings.openai,
        messages,
        max_tokens=2000,
        temperature=0.0,
        deployment_override=fraud_settings.deployment_name,
        model_override=fraud_settings.model_name,
        reasoning_effort=reasoning_effort,
        response_format="json_object",
    )

    content = raw.get("content", "")
    return _parse_json_robust(content)
