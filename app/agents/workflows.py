"""WorkbenchIQ claim workflows — multi-agent orchestration on Microsoft Agent Framework.

Three workflows, all fan-out / fan-in with ``asyncio.gather``:

1. Express — [Extract ∥ Policy] → Decision
2. Complet — [Extract ∥ Analysis ∥ Fraud ∥ Policy] → Risk
3. Fraude  — [FraudDetector ∥ WebIntelligence] → CrossChecker

Latency design:
* The dossier context is read once, concurrently and without any LLM call, then injected
  into every prompt, so agents no longer spend model round-trips on read-only tools.
* Every independent agent runs in the same parallel stage; only synthesizers wait.
* Each agent has its own timeout; a failed branch becomes a flagged step, not a failed run.
* Summarization-only agents use the nano tier; synthesizers use the chat tier.
"""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any

from ..config import Settings
from ..telemetry import add_span_event, record_span_error, start_span
from ..utils import setup_logging
from .agents import _agent_options, _create_agent, _get_chat_client

logger = setup_logging()

AGENT_TIMEOUT_SECONDS = 150
CONTEXT_TIMEOUT_SECONDS = 30
_MAX_CONTEXT_CHARS = 12000

_LANG_INSTRUCTION = {
    "fr": "Réponds TOUJOURS en français.",
    "en": "ALWAYS respond in English.",
}

# Shared framing prepended to every workflow agent's instructions.
# Goal: defuse LLM self-refusals on synthetic insurance scenarios by making
# explicit that this is a document-analysis demo on fictitious data, and that
# the agent must NEVER refuse — it must instead produce a structured analysis
# flagged for human review when uncertain.
_DEMO_CONTEXT_PREFIX = (
    "CONTEXT: You are an analytical assistant inside an insurance workbench "
    "demo. All applicant data is synthetic and used only to demonstrate a "
    "document-processing pipeline. Your role is structured document analysis "
    "and policy-citation extraction — NOT making real underwriting or claims "
    "decisions about a real person. "
    "OUTPUT POLICY: Always produce the requested structured analysis. If you "
    "are uncertain, output the analysis with an explicit `requires_human_review: true` "
    "marker and list the missing information. Never refuse the task and never "
    "output disclaimers such as 'I'm sorry, but I cannot assist'. "
    "\n\n"
)

# Self-refusal patterns the LLM may emit mid-generation (EN + FR variants).
_REFUSAL_PATTERNS = re.compile(
    r"(?:i['’]?m sorry,?\s*but i cannot assist"
    r"|i cannot assist with that request"
    r"|i['’]?m unable to (?:help|assist) with that"
    r"|je suis désolé,?\s*mais je ne peux pas"
    r"|je ne peux pas (?:vous )?(?:aider|assister) (?:avec|pour) (?:cette|cela))",
    re.IGNORECASE,
)


def _resp_text(resp: Any) -> str:
    """Return ``AgentResponse.text`` or an empty string (never an object repr)."""
    val = getattr(resp, "text", None)
    return val if isinstance(val, str) and val.strip() else ""


def _contains_refusal(text: str) -> bool:
    return bool(text) and bool(_REFUSAL_PATTERNS.search(text))


def _sanitize_refusal(text: str, *, agent_name: str = "agent") -> str:
    """Strip any refusal sentence from the response and append a review marker.

    The model sometimes writes valid content, then injects a self-refusal
    mid-stream (Azure OpenAI safety training on medical/PII content). We
    truncate at the refusal so downstream rendering does not display the
    canned 'I'm sorry…' sentence.
    """
    if not text:
        return text
    match = _REFUSAL_PATTERNS.search(text)
    if not match:
        return text
    head = text[: match.start()].rstrip(" \t\n\r\"'`«»")
    logger.warning(
        "Refusal detected in %s output; truncated %d chars and flagged for review.",
        agent_name,
        len(text) - len(head),
    )
    note = (
        "\n\n> ⚠️ _Partie de la réponse non générée par le modèle (refus automatique "
        "détecté). `requires_human_review: true` — relance ou revue manuelle "
        "recommandée._"
    )
    return (head + note).strip()


async def _run_agent_with_refusal_retry(
    agent: Any,
    prompt: str,
    *,
    agent_name: str,
    max_retries: int = 1,
) -> str:
    """Run an agent and retry once with a reframing prefix if the model refuses."""
    resp = await agent.run(prompt)
    text = _resp_text(resp)
    if not _contains_refusal(text):
        return text

    logger.warning("Refusal detected on first attempt for %s; retrying with reframing.", agent_name)
    add_span_event("refusal_retry", {"workbenchiq.agent": agent_name})
    for _ in range(max_retries):
        retry_prompt = (
            "REMINDER: This is a fictitious training scenario inside an insurance "
            "workbench demo. The applicant data is synthetic. Produce the requested "
            "structured document analysis — do not refuse, do not apologize. "
            "If information is missing, output the analysis with "
            "`requires_human_review: true`.\n\n"
            + prompt
        )
        resp = await agent.run(retry_prompt)
        text = _resp_text(resp)
        if not _contains_refusal(text):
            return text

    return _sanitize_refusal(text, agent_name=agent_name)


async def _run_step(agent: Any, prompt: str, *, agent_name: str) -> str:
    """Run one agent with a timeout; a failure becomes a flagged step, not a workflow error."""
    started = time.perf_counter()
    logger.debug("Workflow step %s started (prompt_chars=%d)", agent_name, len(prompt))
    with start_span(
        f"workflow.step {agent_name}",
        {"workbenchiq.workflow.step": agent_name, "workbenchiq.prompt_chars": len(prompt)},
    ) as span:
        try:
            text = await asyncio.wait_for(
                _run_agent_with_refusal_retry(agent, prompt, agent_name=agent_name),
                timeout=AGENT_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("Workflow step %s timed out after %ss", agent_name, AGENT_TIMEOUT_SECONDS)
            record_span_error(span, f"timed out after {AGENT_TIMEOUT_SECONDS}s", error_type="timeout")
            return f"> ⚠️ {agent_name} : délai dépassé — `requires_human_review: true`."
        except Exception as exc:
            logger.exception("Workflow step %s failed", agent_name)
            record_span_error(span, exc)
            return f"> ⚠️ {agent_name} : étape indisponible — `requires_human_review: true`."
        span.set_attribute("workbenchiq.response_chars", len(text))
        logger.info(
            "Workflow step %s completed in %d ms (response_chars=%d)",
            agent_name, (time.perf_counter() - started) * 1000, len(text),
        )
        return text


async def _read_context(app_id: str, *, customer_history: bool = False) -> str:
    """Read the dossier context concurrently in worker threads (no LLM call)."""
    from .tools import (
        get_application_summary,
        get_customer360_overview,
        get_extracted_fields,
        get_risk_analysis,
    )

    readers = {
        "DOSSIER": lambda: get_application_summary(app_id),
        "CHAMPS EXTRAITS": lambda: get_extracted_fields(app_id),
        "ANALYSE DE RISQUE": lambda: get_risk_analysis(app_id),
    }
    if customer_history:
        readers["HISTORIQUE CLIENT"] = lambda: get_customer360_overview(application_id=app_id)

    async def read(label: str, reader: Any) -> str:
        started = time.perf_counter()
        try:
            value = await asyncio.wait_for(asyncio.to_thread(reader), CONTEXT_TIMEOUT_SECONDS)
        except Exception:
            logger.warning("Workflow context %s unavailable for %s", label, app_id, exc_info=True)
            return ""
        logger.debug(
            "Workflow context %s read for %s in %d ms (%d chars)",
            label, app_id, (time.perf_counter() - started) * 1000, len(str(value or "")),
        )
        return f"### {label}\n{str(value)[:_MAX_CONTEXT_CHARS]}" if value else ""

    with start_span(
        "workflow.read_context",
        {"workbenchiq.app_id": app_id, "workbenchiq.context.sections": len(readers)},
    ) as span:
        parts = await asyncio.gather(*(read(label, fn) for label, fn in readers.items()))
        context = "\n\n".join(part for part in parts if part)
        span.set_attribute("workbenchiq.context.sections_loaded", sum(1 for part in parts if part))
        span.set_attribute("workbenchiq.context.chars", len(context))
    return context


def _with_context(task: str, context: str) -> str:
    return f"{task}\n\n--- CONTEXTE DU DOSSIER ---\n{context or '(indisponible)'}\n--- FIN ---"


# Agents are stateless config holders: cache them on everything that defines them
# (client config, tier, name, instructions, tools) and reuse them across requests.
_AGENT_CACHE: dict[tuple, Any] = {}


def _agent_config_key(settings: Settings, tier: str = "chat") -> tuple:
    o = settings.openai
    return (
        o.endpoint,
        bool(o.use_azure_ad),
        o.get_deployment(tier),
        o.chat_api_version or o.api_version,
        o.api_key or "",
        getattr(o, "reasoning_effort", "low"),
        getattr(getattr(settings, "foundry", None), "agents_openai_api", "responses"),
    )


def _cached_agent(
    settings: Settings,
    *,
    name: str,
    instructions: str,
    tools: list | None = None,
    tier: str = "chat",
) -> Any:
    """Return a cached Agent for identical (config, tier, name, instructions, tools)."""
    tool_key = tuple(getattr(t, "__name__", repr(t)) for t in (tools or ()))
    key = (_agent_config_key(settings, tier), name, instructions, tool_key)
    agent = _AGENT_CACHE.get(key)
    if agent is None:
        agent = _create_agent(
            _get_chat_client(settings, tier),
            name=name,
            instructions=instructions,
            tools=tools,
            default_options=_agent_options(settings, tier),
        )
        _AGENT_CACHE[key] = agent
        logger.debug("Workflow agent %s created (tier=%s, tools=%s)", name, tier, list(tool_key))
    else:
        logger.debug("Workflow agent %s reused from cache", name)
    return agent


def _role(text: str, lang: str) -> str:
    return f"{_DEMO_CONTEXT_PREFIX}{text} {lang}"


def _result(workflow: str, steps: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "workflow": workflow,
        "status": "completed",
        "steps": [{"agent": agent, "text": text} for agent, text in steps],
        "summary": steps[-1][1] or "No output",
    }


# ── Workflow definitions ─────────────────────────────────────────


async def create_express_workflow(
    settings: Settings,
    app_id: str,
    persona: str = "habitation_claims",
    language: str = "fr",
) -> dict[str, Any]:
    """Express: [Extract ∥ Policy] → Decision, for routine claims."""
    from .tools import search_policies

    lang = _LANG_INSTRUCTION.get(language, _LANG_INSTRUCTION["fr"])
    context = await _read_context(app_id)

    extract_agent = _cached_agent(
        settings,
        name="ExtractAgent",
        tier="nano",
        instructions=_role(
            "ROLE: Document extraction specialist. From the dossier context provided, "
            "produce a structured summary of the key fields: insured name, claim/application "
            "type, amounts, dates, coverage status, missing fields. Describe only what the "
            f"documents contain. Persona: {persona}.",
            lang,
        ),
    )
    policy_agent = _cached_agent(
        settings,
        name="PolicyAgent",
        instructions=_role(
            "ROLE: Policy citation specialist. Use search_policies to find the Conditions "
            "Générales articles, exclusions and franchise amounts documented for this claim "
            "type. Cite articles verbatim. Do not decide — only extract what applies.",
            lang,
        ),
        tools=[search_policies],
    )
    decision_agent = _cached_agent(
        settings,
        name="DecisionAgent",
        instructions=_role(
            "ROLE: Underwriting/claims analysis synthesizer. From the extraction, policy "
            "citations and dossier context, produce a STRUCTURED analysis tagged "
            "`documented_recommendation: approve | approve_with_conditions | defer | decline "
            "| review_needed` strictly based on the policy criteria provided. Always include "
            "documented_recommendation, rationale (citing policy articles), "
            "conditions_or_franchise, next_steps. If information is insufficient, use "
            "review_needed and list the missing items. Never refuse.",
            lang,
        ),
    )

    extract_text, policy_text = await asyncio.gather(
        _run_step(
            extract_agent,
            _with_context(f"Summarize application {app_id}.", context),
            agent_name="ExtractAgent",
        ),
        _run_step(
            policy_agent,
            _with_context(
                f"Cite the Conditions Générales articles, exclusions and franchise that "
                f"apply to application {app_id}.",
                context,
            ),
            agent_name="PolicyAgent",
        ),
    )
    decision_text = await _run_step(
        decision_agent,
        _with_context(
            f"Synthesize the documented analysis for application {app_id}.\n\n"
            f"[ExtractAgent]\n{extract_text}\n\n---\n\n[PolicyAgent]\n{policy_text}",
            context,
        ),
        agent_name="DecisionAgent",
    )
    return _result(
        "express",
        [
            ("ExtractAgent", extract_text),
            ("PolicyAgent", policy_text),
            ("DecisionAgent", decision_text),
        ],
    )


async def create_complet_workflow(
    settings: Settings,
    app_id: str,
    persona: str = "habitation_claims",
    language: str = "fr",
) -> dict[str, Any]:
    """Complet: [Extract ∥ Analysis ∥ Fraud ∥ Policy] → Risk, for complex claims."""
    from .tools import analyze_image_fraud, search_policies

    lang = _LANG_INSTRUCTION.get(language, _LANG_INSTRUCTION["fr"])
    context = await _read_context(app_id, customer_history=True)

    extract_agent = _cached_agent(
        settings,
        name="ExtractAgent",
        tier="nano",
        instructions=_role(
            "ROLE: Document extraction specialist. From the dossier context provided, "
            "produce a structured summary: insured, claim/application type, amounts, dates, "
            f"coverage status, missing fields. Persona: {persona}.",
            lang,
        ),
    )
    analysis_agent = _cached_agent(
        settings,
        name="AnalysisAgent",
        instructions=_role(
            "ROLE: Liability and damage analysis specialist. Describe the documented "
            "liability indicators, damage severity and coverage applicability, using "
            "search_policies for policy citations. Analysis only, not a decision.",
            lang,
        ),
        tools=[search_policies],
    )
    fraud_agent = _cached_agent(
        settings,
        name="FraudAgent",
        instructions=_role(
            "ROLE: Fraud-indicator detection specialist. Use analyze_image_fraud to check "
            "image authenticity and declaration consistency, and use the customer history in "
            "the context to surface patterns. Output documented indicators only.",
            lang,
        ),
        tools=[analyze_image_fraud],
    )
    policy_agent = _cached_agent(
        settings,
        name="PolicyAgent",
        instructions=_role(
            "ROLE: Policy citation specialist. Use search_policies to identify the documented "
            "coverage, exclusions and franchise for this claim type. Cite articles verbatim.",
            lang,
        ),
        tools=[search_policies],
    )
    risk_agent = _cached_agent(
        settings,
        name="RiskAgent",
        instructions=_role(
            "ROLE: Risk analysis synthesizer. Consolidate the extraction, analysis, "
            "fraud-indicator and policy-citation outputs into: documented_risk_score, "
            "documented_recommendation (approve | approve_with_conditions | defer | decline "
            "| review_needed), rationale citing policy articles, next_steps. If fraud "
            "indicators are HIGH, include SIU referral in next_steps. Never refuse.",
            lang,
        ),
    )

    branches = {
        "ExtractAgent": (extract_agent, f"Summarize application {app_id}."),
        "AnalysisAgent": (
            analysis_agent,
            f"Analyze documented liability, damage severity and coverage for application {app_id}.",
        ),
        "FraudAgent": (fraud_agent, f"Surface documented fraud indicators for application {app_id}."),
        "PolicyAgent": (
            policy_agent,
            f"Cite the Conditions Générales articles, exclusions and franchise for application {app_id}.",
        ),
    }
    texts = await asyncio.gather(
        *(
            _run_step(agent, _with_context(task, context), agent_name=name)
            for name, (agent, task) in branches.items()
        )
    )
    steps = list(zip(branches, texts))
    merged = "\n\n---\n\n".join(f"[{name}]\n{text}" for name, text in steps)
    risk_text = await _run_step(
        risk_agent,
        f"Consolidate the outputs for application {app_id} into a structured risk analysis."
        f"\n\n{merged}",
        agent_name="RiskAgent",
    )
    return _result("complet", [*steps, ("RiskAgent", risk_text)])


async def create_fraud_workflow(
    settings: Settings,
    app_id: str,
    persona: str = "habitation_claims",
    language: str = "fr",
) -> dict[str, Any]:
    """Fraude: [FraudDetector ∥ WebIntelligence] → CrossChecker, for SIU investigations."""
    from .tools import analyze_image_fraud, resolve_web_tool, search_policies

    lang = _LANG_INSTRUCTION.get(language, _LANG_INSTRUCTION["fr"])
    context = await _read_context(app_id, customer_history=True)

    fraud_agent = _cached_agent(
        settings,
        name="FraudDetector",
        instructions=_role(
            "ROLE: Fraud-indicator detector using computer vision. Use analyze_image_fraud on "
            "the application images for authenticity markers, manipulation indicators and "
            "AI-generation signs. Output indicators only, never a fraud determination.",
            lang,
        ),
        tools=[analyze_image_fraud],
    )
    webintel_instructions = _role(
        "ROLE: Open-source intelligence analyst. Search public sources (Cat-Nat decrees, "
        "weather, Argus pricing, news) relevant to the declared event and cross-reference "
        "them with the dossier. Always cite source URLs. Research only.",
        lang,
    )
    webintel_agent = _cached_agent(
        settings,
        name="WebIntelligence",
        instructions=webintel_instructions,
        tools=[resolve_web_tool(settings)],
    )
    crosscheck_agent = _cached_agent(
        settings,
        name="CrossChecker",
        instructions=_role(
            "ROLE: Fraud-investigation synthesizer. Cross-reference the image analysis with "
            "the web intelligence and the customer history, use search_policies when a "
            "clause matters, and produce: documented_siu_recommendation (REFER | CLEAR | "
            "review_needed), confidence_score, evidence_summary, rationale. Never refuse.",
            lang,
        ),
        tools=[search_policies],
    )

    fraud_text, webintel_text = await asyncio.gather(
        _run_step(
            fraud_agent,
            _with_context(f"Analyze the images of application {app_id}.", context),
            agent_name="FraudDetector",
        ),
        _run_step(
            webintel_agent,
            _with_context(
                f"Verify the declared event of application {app_id} against public sources.",
                context,
            ),
            agent_name="WebIntelligence",
        ),
    )

    crosscheck_text = await _run_step(
        crosscheck_agent,
        _with_context(
            f"Produce the SIU recommendation for application {app_id}.\n\n"
            f"[FraudDetector]\n{fraud_text}\n\n---\n\n[WebIntelligence]\n{webintel_text}",
            context,
        ),
        agent_name="CrossChecker",
    )
    return _result(
        "fraude",
        [
            ("FraudDetector", fraud_text),
            ("WebIntelligence", webintel_text),
            ("CrossChecker", crosscheck_text),
        ],
    )


# ── Workflow registry ────────────────────────────────────────────

WORKFLOWS = {
    "express": {
        "id": "express",
        "name": "Sinistre Express",
        "icon": "⚡",
        "description": "Traitement parallèle rapide pour sinistres courants < 5 000 €",
        "pattern": "[Extract ∥ Policy] → Decision",
        "agents": ["ExtractAgent", "PolicyAgent", "DecisionAgent"],
        "estimated_duration": "~1 min",
    },
    "complet": {
        "id": "complet",
        "name": "Sinistre Complet",
        "icon": "🔍",
        "description": "Analyse complète : extraction, responsabilité, fraude et polices en parallèle",
        "pattern": "[Extract ∥ Analysis ∥ Fraud ∥ Policy] → Risk",
        "agents": ["ExtractAgent", "AnalysisAgent", "FraudAgent", "PolicyAgent", "RiskAgent"],
        "estimated_duration": "~2 min",
    },
    "fraude": {
        "id": "fraude",
        "name": "Investigation Fraude",
        "icon": "🔎",
        "description": "Investigation fraude : analyse photos et veille web en parallèle",
        "pattern": "[Fraud ∥ WebIntel] → CrossCheck → SIU",
        "agents": ["FraudDetector", "WebIntelligence", "CrossChecker"],
        "estimated_duration": "~2 min",
    },
}
