"""Agent API integration — connect agents to FastAPI endpoints.

Provides helper functions that the api_server uses to route
requests through the Agent Framework for tool-calling chat.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from typing import Any, Dict, List

from ..config import Settings
from ..telemetry import record_span_error, start_span
from ..utils import setup_logging
from .errors import agent_response_text, agent_tools_called, translate_agent_error

logger = setup_logging()


def _tool_span(tool_name: str):
    """Span for a tool the router calls directly (agent runs get ``execute_tool`` spans from the framework)."""
    return start_span(
        f"execute_tool {tool_name}",
        {
            "gen_ai.operation.name": "execute_tool",
            "gen_ai.tool.name": tool_name,
            "gen_ai.tool.type": "function",
        },
    )


def _framework_label() -> str:
    """Single source of truth for the reported Agent Framework version.

    Reads the installed ``agent-framework-core`` version at import time so the
    label can never drift from the actual dependency.
    """
    try:
        from importlib.metadata import version

        return f"Microsoft Agent Framework {version('agent-framework-core')}"
    except Exception:  # pragma: no cover - defensive, metadata always present in prod
        return "Microsoft Agent Framework"


FRAMEWORK_LABEL = _framework_label()


def _format_fraud_response(raw_output: str) -> str:
    """Format fraud tool output into a readable chat response."""
    try:
        payload = json.loads(raw_output)
    except (TypeError, ValueError, json.JSONDecodeError):
        return raw_output

    if not isinstance(payload, dict):
        return raw_output

    parts: list[str] = ["## Analyse fraude photo"]

    image_analyses = payload.get("image_analyses") or []
    if image_analyses:
        parts.append(f"- Photos analysées : {len(image_analyses)}")

    overall = payload.get("overall_assessment") or {}
    if isinstance(overall, dict):
        risk_level = overall.get("fraud_risk_level") or overall.get("risk_level")
        score = overall.get("fraud_score") or overall.get("risk_score")
        summary = overall.get("summary") or overall.get("overall_summary") or overall.get("assessment")
        rationale = overall.get("rationale") or overall.get("reasoning")

        if risk_level:
            parts.append(f"- Niveau de risque : {risk_level}")
        if score is not None:
            parts.append(f"- Score : {score}")
        if summary:
            parts.append("")
            parts.append(f"Synthèse : {summary}")
        if rationale:
            parts.append(f"Justification : {rationale}")

    suspicious_items: list[str] = []
    for item in image_analyses:
        if not isinstance(item, dict):
            continue
        filename = item.get("filename", "photo")
        if item.get("error"):
            suspicious_items.append(f"- {filename} : analyse indisponible ({item['error']})")
            continue

        suspicion = item.get("manipulation_probability") or item.get("fraud_probability")
        indicators = item.get("manipulation_indicators") or item.get("suspicious_indicators") or []
        indicator_lines: list[str] = []
        for indicator in indicators[:3]:
            if isinstance(indicator, dict):
                label = indicator.get("type") or indicator.get("description") or "indicateur"
                severity = indicator.get("severity")
                confidence = indicator.get("confidence")
                description = indicator.get("description")
                details = []
                if severity:
                    details.append(f"gravité {severity}")
                if confidence is not None:
                    details.append(f"confiance {confidence}")
                if description and description != label:
                    details.append(description)
                indicator_lines.append(f"  - {label}: {'; '.join(details)}" if details else f"  - {label}")
            else:
                indicator_lines.append(f"  - {indicator}")
        summary_bits = []
        if suspicion is not None:
            summary_bits.append(f"score suspicion {suspicion}")
        suspicious_items.append(f"- {filename}{' (' + ', '.join(summary_bits) + ')' if summary_bits else ''}")
        suspicious_items.extend(indicator_lines)

    if suspicious_items:
        parts.append("")
        parts.append("Points relevés :")
        parts.extend(suspicious_items[:5])

    declaration = payload.get("declaration_verification") or {}
    if isinstance(declaration, dict):
        decl_summary = declaration.get("summary") or declaration.get("consistency_summary")
        if decl_summary:
            parts.append("")
            parts.append(f"Cohérence déclaration/photos : {decl_summary}")

    if len(parts) == 1:
        return raw_output
    return "\n".join(parts)


async def agent_chat(
    settings: Settings,
    app_id: str,
    message: str,
    history: List[Dict[str, str]] | None = None,
    persona: str = "underwriting",
    agent_type: str = "auto",
    use_corrections: bool | None = True,
    language: str = "fr",
    on_delta: Callable[[str], Awaitable[None]] | None = None,
) -> Dict[str, Any]:
    """Route chat to the appropriate agent based on agent_type pill.

    Routing:
        auto     → ChatAgent (all tools, LLM picks)
        data     → Direct Fabric Data Agent NL→SQL call
        policy   → PolicyAgent (search_policies + glossary only)
        analysis → AnalysisAgent (analyze_section, list_available_analyses)
        dashboard→ DashboardAgent (KPIs, structured data)
        fraud    → Direct analyze_image_fraud call
    """
    started = time.perf_counter()
    from .agents import (
        create_chat_agent, create_analysis_agent, _create_agent, _get_chat_client, _agent_options,
    )
    from .tools import (
        analyze_image_fraud, query_fabric_data, search_policies, resolve_web_tool,
        get_glossary, get_application_summary, get_risk_analysis,
        get_customer360_overview, get_extracted_fields,
    )

    imports_ms = round((time.perf_counter() - started) * 1000, 1)
    logger.debug(
        "agent_chat: app_id=%s persona=%s agent_type=%s history=%d language=%s",
        app_id, persona, agent_type, len(history or []), language,
    )

    # Preload the dossier summary (blocking I/O) concurrently with agent creation,
    # which itself embeds the query for few-shot corrections.
    timings: dict[str, float] = {"imports_ms": imports_ms}

    async def _load_summary() -> str:
        context_started = time.perf_counter()
        with start_span("chat.load_context", {"workbenchiq.app_id": app_id}):
            try:
                return await asyncio.to_thread(get_application_summary, application_id=app_id)
            finally:
                timings["context_ms"] = round((time.perf_counter() - context_started) * 1000, 1)

    summary_task = asyncio.create_task(_load_summary())

    async def _build_enriched_message() -> str:
        dossier_context = ""
        try:
            summary = await summary_task
            if (
                summary
                and not summary.startswith("Error")
                and not summary.startswith("Application not found")
                and "introuvable" not in summary[:80]
            ):
                dossier_context = f"\n\n--- DOSSIER CONTEXT ---\n{summary}\n--- END CONTEXT ---\n"
            logger.debug("agent_chat: dossier context loaded (%d chars)", len(dossier_context))
        except Exception:
            logger.exception("agent_chat: failed to preload dossier summary for %s", app_id)

        dossier_header = f"[Dossier: {app_id}, Persona: {persona}]"
        if not history:
            return f"{dossier_header}{dossier_context}\n\n{message}"
        # Keep the dossier header + context so the agent always has the application_id.
        context_parts = [
            f"[{msg.get('role', 'user')}]: {msg.get('content', '')}" for msg in history[-6:]
        ]
        return (
            f"{dossier_header}{dossier_context}\n\n"
            "Recent conversation history:\n"
            + "\n".join(context_parts)
            + f"\n\nNew user question: {message}"
        )

    # ── Route based on agent_type ──
    fraud_terms = {"fraude", "fraud", "truqu", "authentic", "authenticit", "manipul", "retouch", "faux"}
    image_terms = {"photo", "photos", "image", "images", "png", "jpg", "jpeg", "capture"}
    lowered_message = message.lower()
    looks_like_fraud = (
        agent_type in {"fraud", "fraud_detection"}
        or (any(term in lowered_message for term in fraud_terms)
            and any(term in lowered_message for term in image_terms))
    )

    agent = None
    agent_name = "ChatAgent"
    tools_available: list[str] = []

    if looks_like_fraud:
        agent_name = "FraudDetectionAgent"
        tools_available = ["analyze_image_fraud", "get_application_summary", "search_policies"]

    elif agent_type == "data":
        # Données pill → Direct Fabric Data Agent NL→SQL
        agent_name = "FabricDataAgent"
        tools_available = ["query_fabric_data"]

    elif agent_type == "policy":
        # Polices pill → Focused policy RAG agent
        agent_name = "PolicyAgent"
        tools_available = ["search_policies", "get_glossary", "get_application_summary"]
        agent = _create_agent(
            _get_chat_client(settings),
            name="PolicyAgent",
            default_options=_agent_options(settings, effort=settings.openai.chat_reasoning_effort),
            instructions=(
                f"Tu es un agent spécialisé dans la recherche et l'interprétation des Conditions Générales d'assurance {settings.brand_name}.\n"
                "Tu utilises EXCLUSIVEMENT l'outil search_policies pour trouver les clauses pertinentes.\n"
                "Cite toujours les articles, numéros de page et extraits exacts des CG.\n"
                "Si une question sort du périmètre des polices d'assurance, dis-le clairement.\n"
                f"Contexte : Persona={persona}, Dossier={app_id}."
            ),
            tools=[search_policies, get_glossary, get_application_summary],
        )

    elif agent_type == "analysis":
        # Analyse pill → Specialized AnalysisAgent
        agent_name = "AnalysisAgent"
        tools_available = ["analyze_section", "list_available_analyses", "get_extracted_fields",
                           "search_policies", "get_application_summary"]
        agent = await create_analysis_agent(settings)

    elif agent_type == "dashboard":
        # KPIs pill → Dashboard/KPI agent
        agent_name = "DashboardAgent"
        tools_available = ["get_application_summary", "get_risk_analysis",
                           "get_customer360_overview", "get_extracted_fields"]
        agent = _create_agent(
            _get_chat_client(settings),
            name="DashboardAgent",
            default_options=_agent_options(settings, effort=settings.openai.chat_reasoning_effort),
            instructions=(
                "Tu es un agent spécialisé dans les indicateurs clés (KPIs) et tableaux de bord.\n"
                "Réponds avec des données structurées : montants, délais, taux, volumes, tendances.\n"
                "Utilise les outils pour récupérer les données du dossier et du client.\n"
                "Présente les résultats sous forme de tableau Markdown ou liste structurée.\n"
                "Format recommandé :\n"
                "## KPIs Dossier\n"
                "| Indicateur | Valeur |\n|---|---|\n| ... | ... |\n\n"
                f"Contexte : Persona={persona}, Dossier={app_id}."
            ),
            tools=[get_application_summary, get_risk_analysis,
                   get_customer360_overview, get_extracted_fields],
        )

    else:
        # Auto pill → Full ChatAgent with all tools
        with start_span("chat.create_agent", {"workbenchiq.persona": persona}):
            try:
                agent = await create_chat_agent(
                    settings,
                    persona=persona,
                    current_query=message,
                    use_corrections=use_corrections if use_corrections is not None else True,
                    language=language,
                )
            except BaseException:
                summary_task.cancel()
                await asyncio.gather(summary_task, return_exceptions=True)
                raise
        agent_name = "ChatAgent"
        tools_available = [
            "search_policies", "get_application_summary", "get_glossary",
            "query_fabric_data", "analyze_image_fraud",
            "get_risk_analysis", "get_customer360_overview", "get_image_descriptions",
            "get_confidence_scores", "get_file_list", "classify_documents",
            "get_communications", "get_document_sentiment", "get_damage_areas_multimodal",
            "get_page_reference",
        ]
        tools_available.append(resolve_web_tool(settings).__name__)

    # ── Execute ──
    enriched_message = await _build_enriched_message()
    timings["setup_ms"] = round((time.perf_counter() - started) * 1000, 1)
    logger.debug(
        "agent_chat: agent=%s ready after %d ms (message_chars=%d, enriched_chars=%d, tools_available=%d)",
        agent_name, (time.perf_counter() - started) * 1000, len(message), len(enriched_message),
        len(tools_available),
    )

    tools_called: list[str] = []
    usage: Any = {}
    run_started = time.perf_counter()
    with start_span(
        agent_name,
        {
            "gen_ai.operation.name": "chat",
            "gen_ai.system": "openai",
            "gen_ai.agent.name": agent_name,
            "workbenchiq.persona": persona,
            "workbenchiq.app_id": app_id,
            "workbenchiq.agent_type": agent_type,
        },
    ) as span:
        if looks_like_fraud:
            tools_called = ["analyze_image_fraud"]
            with _tool_span("analyze_image_fraud") as tool_span:
                try:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(
                            analyze_image_fraud,
                            application_id=app_id,
                            declaration_text=message,
                            reasoning_effort="low",
                        ),
                        timeout=120,
                    )
                    response_text = _format_fraud_response(str(result))
                except asyncio.TimeoutError:
                    logger.warning("Fraud photo analysis timed out for application %s", app_id)
                    record_span_error(tool_span, "timed out after 120s", error_type="timeout")
                    response_text = (
                        "## Fraud Analysis Timeout\n"
                        "The photo analysis is taking longer than expected. "
                        "Please try again or launch a full AI analysis."
                    )
        elif agent_type == "data":
            tools_called = ["query_fabric_data"]
            # Direct Fabric NL→SQL call — pass enriched message with dossier context
            with _tool_span("query_fabric_data") as tool_span:
                try:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(query_fabric_data, question=enriched_message, persona=persona),
                        timeout=90,
                    )
                    response_text = str(result)
                except asyncio.TimeoutError:
                    logger.warning("Fabric data query timed out for application %s", app_id)
                    record_span_error(tool_span, "timed out after 90s", error_type="timeout")
                    response_text = (
                        "## Fabric Data Agent Timeout\n"
                        "The Fabric Data Agent query timed out. "
                        "Please try a more specific question."
                    )
        else:
            # Agent loop (policy, analysis, dashboard, auto)
            try:
                if on_delta is None:
                    result = await agent.run(enriched_message)
                else:
                    stream = agent.run(enriched_message, stream=True)
                    async for update in stream:
                        if update.text:
                            timings.setdefault(
                                "first_text_ms", round((time.perf_counter() - started) * 1000, 1)
                            )
                            await on_delta(update.text)
                    result = await stream.get_final_response()
                response_text = agent_response_text(result)
                tools_called = agent_tools_called(result)
                usage = getattr(result, "usage_details", None) or {}
            except Exception as exc:
                error = translate_agent_error(exc)
                logger.exception("Agent invocation failed: code=%s request_id=%s", error.code, error.request_id)
                span.set_attribute("error.type", error.code)
                span.set_attribute("workbenchiq.request_id", error.request_id)
                raise error from exc

        timings["run_ms"] = round((time.perf_counter() - run_started) * 1000, 1)
        timings["total_ms"] = round((time.perf_counter() - started) * 1000, 1)
        for stage, duration in timings.items():
            span.set_attribute(f"workbenchiq.chat.{stage}", duration)
        if tools_called:
            span.set_attribute("workbenchiq.tools_called", tools_called)
        # Logged inside the span so the record carries its trace context in Application Insights.
        logger.info(
            "agent_chat done: agent=%s persona=%s app_id=%s duration_ms=%d tools_called=%s "
            "tokens_in=%s tokens_out=%s response_chars=%d timings_ms=%s",
            agent_name, persona, app_id, (time.perf_counter() - started) * 1000, tools_called,
            usage.get("input_token_count"), usage.get("output_token_count"), len(response_text), timings,
        )

    return {
        "response": response_text,
        "usage": {},
        "agent": {
            "name": agent_name,
            "tools_available": tools_available,
            "tools_called": tools_called,
            "framework": FRAMEWORK_LABEL,
            "timings_ms": timings,
        },
    }


async def agent_workflow(
    settings: Settings,
    app_id: str,
    workflow_id: str,
    persona: str = "habitation_claims",
    language: str = "fr",
) -> Dict[str, Any]:
    """Execute a named workflow on an application.

    Available workflows: express, complet, fraude.
    Returns structured result with step-by-step agent outputs.
    """
    from .workflows import (
        create_express_workflow, create_complet_workflow,
        create_fraud_workflow, WORKFLOWS,
    )

    if workflow_id not in WORKFLOWS:
        logger.warning("Unknown workflow requested: %s", workflow_id)
        return {"error": f"Unknown workflow: {workflow_id}", "available": list(WORKFLOWS.keys())}

    workflow_meta = WORKFLOWS[workflow_id]
    agent_name = f"Workflow:{workflow_meta['name']}"

    started = time.perf_counter()
    with start_span(
        agent_name,
        {
            "gen_ai.operation.name": "workflow",
            "gen_ai.system": "openai",
            "gen_ai.agent.name": agent_name,
            "workbenchiq.persona": persona,
            "workbenchiq.app_id": app_id,
            "workbenchiq.workflow_id": workflow_id,
        },
    ) as span:
        logger.info(
            "Workflow %s started: app_id=%s persona=%s language=%s", workflow_id, app_id, persona, language
        )
        try:
            if workflow_id == "express":
                result = await create_express_workflow(settings, app_id, persona, language=language)
            elif workflow_id == "complet":
                result = await create_complet_workflow(settings, app_id, persona, language=language)
            elif workflow_id == "fraude":
                result = await create_fraud_workflow(settings, app_id, persona, language=language)
            else:
                result = {"error": f"Workflow {workflow_id} not implemented"}
        except Exception as exc:
            error = translate_agent_error(exc)
            logger.exception(
                "Workflow %s failed: code=%s request_id=%s", workflow_id, error.code, error.request_id
            )
            span.set_attribute("error.type", error.code)
            span.set_attribute("workbenchiq.request_id", error.request_id)
            raise error from exc

        logger.info(
            "Workflow %s completed: app_id=%s steps=%d duration_ms=%d",
            workflow_id, app_id, len(result.get("steps", [])), (time.perf_counter() - started) * 1000,
        )

    return result
