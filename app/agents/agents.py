"""WorkbenchIQ agents — Microsoft Agent Framework agent definitions.

- ChatAgent: interactive Q&A with policy search, dossier context and Web IQ grounding
- AnalysisAgent: prompt-based document analysis with dynamic section selection

Multi-agent claim workflows live in ``workflows.py``. Agents run in-process against
Azure OpenAI (Responses API); they are not hosted in Foundry Agent Service.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any
from urllib.parse import urlparse

from agent_framework import Agent
from agent_framework.observability import OBSERVABILITY_SETTINGS
from agent_framework.openai import OpenAIChatClient, OpenAIChatCompletionClient

from ..config import Settings, load_settings
from ..telemetry import start_span
from ..utils import setup_logging
from .tools import (
    WEBIQ_TOOLS,  # noqa: F401 — re-exported
    create_webiq_tool,  # noqa: F401 — re-exported
    resolve_web_tool,
    search_policies,
    get_application_summary,
    get_glossary,
    query_fabric_data,
    analyze_section,
    list_available_analyses,
    get_extracted_fields,
    get_risk_analysis,
    get_customer360_overview,
    get_image_descriptions,
    get_confidence_scores,
    get_file_list,
    classify_documents,
    get_communications,
    get_document_sentiment,
    get_damage_areas_multimodal,
    get_page_reference,
    analyze_image_fraud,
)

logger = setup_logging()


# ---------------------------------------------------------------------------
# Agent factory — single source of truth for Agent(client=, name=, instructions=, tools=)
# ---------------------------------------------------------------------------


def _agent_options(
    settings: Settings, tier: str = "chat", effort: str | None = None
) -> dict[str, Any]:
    _, model = settings.openai.get_deployment(tier)
    supported = {
        "gpt-5", "gpt-5-mini", "gpt-5-nano",
        "gpt-5.4", "gpt-5.4-mini", "gpt-5.4-nano", "gpt-5.5",
    }
    if model not in supported:
        return {}
    effort = effort or settings.openai.reasoning_effort
    if effort not in {"none", "minimal", "low", "medium", "high"}:
        raise ValueError("Unsupported agent reasoning effort; use none, minimal, low, medium or high")
    if settings.foundry.agents_openai_api == "chat_completions":
        return {"reasoning_effort": effort}
    return {"reasoning": {"effort": effort}}


def _create_agent(
    client, *, name: str, instructions: str, tools: list | None = None,
    default_options: dict[str, Any] | None = None,
) -> Agent:
    """Create an Agent with optional tools."""
    kwargs: dict[str, Any] = {
        "client": client,
        "name": name,
        "instructions": instructions,
        "default_options": default_options,
    }
    if tools:
        kwargs["tools"] = tools
    agent = Agent(**kwargs)
    logger.debug(
        "Agent created: name=%s tools=%s",
        name,
        [getattr(tool, "name", None) or getattr(tool, "__name__", type(tool).__name__) for tool in tools or ()],
    )
    return agent


# ---------------------------------------------------------------------------
# Few-shot enrichment from feedback loop
# ---------------------------------------------------------------------------


async def _build_few_shot_block(
    current_query: str,
    persona: str,
    agent_type: str,
    settings: Settings,
    top_k: int = 3,
) -> str:
    """Build a few-shot instruction block from relevant past corrections.

    Embeds the current query, searches the few_shot_store via pgvector cosine
    similarity, and formats matching corrections as examples for the agent.
    Returns empty string if no relevant corrections found.
    """
    import asyncio

    try:
        from ..feedback import get_relevant_few_shots, has_eligible_few_shots

        with start_span("chat.corrections_eligibility"):
            if not await has_eligible_few_shots(persona, agent_type):
                return ""

        from ..rag.embeddings import EmbeddingService

        svc = EmbeddingService(settings.openai, settings.rag)
        with start_span("chat.corrections_embedding"):
            embedding = await asyncio.to_thread(svc.get_embedding, current_query)
        if not embedding:
            logger.debug("Few-shot enrichment: no embedding for the query - skipping")
            return ""

        with start_span("chat.corrections_lookup"):
            examples = await get_relevant_few_shots(
                query=current_query,
                persona=persona,
                agent_type=agent_type,
                top_k=top_k,
                embedding=embedding,
            )
        if not examples:
            logger.debug(
                "Few-shot enrichment: no relevant correction (persona=%s, agent_type=%s)", persona, agent_type
            )
            return ""
        logger.debug(
            "Few-shot enrichment: %d correction(s) injected (persona=%s, agent_type=%s)",
            len(examples), persona, agent_type,
        )

        lines = []
        for ex in examples:
            lines.append(
                f"Exemple (correction gestionnaire, pertinence {ex['similarity']:.0%}) :\n"
                f"  Question : {ex['query']}\n"
                f"  ❌ Mauvaise réponse : {ex['bad_response']}\n"
                f"  ✅ Bonne réponse : {ex['good_response']}"
            )

        return (
            "\n\n--- Corrections validées par les gestionnaires (à appliquer) ---\n"
            + "\n\n".join(lines)
            + "\n--- Fin des corrections ---"
        )
    except Exception:
        logger.debug("Few-shot enrichment unavailable — skipping", exc_info=True)
        return ""


# ---------------------------------------------------------------------------
# Agent instruction templates
# ---------------------------------------------------------------------------

CHAT_AGENT_INSTRUCTIONS = """Tu es un assistant expert en assurance pour {brand}, intégré dans le poste de travail de gestion.

**Ton rôle** : Répondre aux questions des gestionnaires de sinistres et souscripteurs en t'appuyant sur les polices d'assurance {brand}, les données extraites des dossiers, le glossaire du domaine, et les données métier via Fabric Data Agent.

**Outils disponibles — Contexte dossier** :
1. `get_application_summary` — Contexte complet (données, analyses, fraude, sentiment, actions)
2. `get_risk_analysis` — Analyse de risque et recommandations de souscription
3. `get_customer360_overview` — Historique client (tous les dossiers, patterns)
4. `get_image_descriptions` — Descriptions des images analysées
5. `get_confidence_scores` — Qualité de l'extraction (scores de confiance par champ)
6. `get_file_list` — Liste des fichiers avec métadonnées
7. `classify_documents` — Classification par type (constat, facture, photo, lettre, email)
8. `get_page_reference` — Contenu d'une page spécifique par numéro

**Outils disponibles — Politiques & Glossaire** :
9. `search_policies` — Articles de police par sujet
10. `get_glossary` — Définitions des termes techniques

**Outils disponibles — Données métier** :
11. `query_fabric_data` — Données chiffrées (statistiques, montants, historiques)
12. `web_search` (ou `webiq_search` via Microsoft Web IQ) — Faits publics (Cat-Nat, météo, Argus, actualités) ; toujours citer les URL sources

**Outils disponibles — Communications & Sentiment** :
13. `get_communications` — Emails/SMS générés pour le dossier
14. `get_document_sentiment` — Ton/sentiment par document

**Outils disponibles — Analyse multimodal (Auto/Habitation)** :
15. `get_damage_areas_multimodal` — Zones de dommage avec images
16. `analyze_image_fraud` — Analyse d'authenticité des photos et cohérence avec la déclaration

**Règles de priorité d'outils** :
1. Pour une question sur les garanties, exclusions ou clauses — utiliser `search_policies` et citer les articles exactement. Ne pas rechercher de police pour une simple question factuelle sur le dossier.
2. Le message contient déjà le résumé du dossier. Répondre directement si ce contexte suffit, sans rappeler `get_application_summary`. Utiliser un outil uniquement pour les informations manquantes nécessaires à la question ; conserver tous les outils disponibles pour ces besoins.
3. Pour le risque/fraude/souscription — utiliser `get_risk_analysis`
4. Pour l'historique client — utiliser `get_customer360_overview`
5. Pour les photos — utiliser `get_image_descriptions`
6. Pour la qualité extraction — utiliser `get_confidence_scores`
7. Pour les fichiers — utiliser `get_file_list`
8. Pour le type de document — utiliser `classify_documents`
9. Pour une page spécifique — utiliser `get_page_reference`
10. Pour les communications — utiliser `get_communications`
11. Pour le sentiment — utiliser `get_document_sentiment`
12. Pour dommages auto/habitation — utiliser `get_damage_areas_multimodal`
13. Pour détecter une fraude sur des photos, vérifier l'authenticité d'images, ou croiser des photos avec la déclaration — utiliser `analyze_image_fraud`

**Règles générales** :
- {language_instruction}
- Si incertain, dire explicitement plutôt que d'inventer
- Inclure citations de police + scores de pertinence
- Terminer par recommandation claire
"""

ANALYSIS_AGENT_INSTRUCTIONS = """Tu es un agent d'analyse spécialisé dans le traitement des dossiers d'assurance {brand}.

**Ton rôle** : Analyser les documents d'un dossier en exécutant les sections d'analyse pertinentes selon le type de dossier (souscription, sinistre auto, sinistre santé, habitation, hypothécaire).

**Règles** :
1. Utiliser `list_available_analyses` pour découvrir les sections disponibles pour le persona du dossier.
2. Utiliser `analyze_section` pour exécuter une analyse spécifique sur le dossier.
3. Utiliser `get_extracted_fields` pour vérifier les données extraites avant l'analyse.
4. Utiliser `search_policies` pour enrichir l'analyse avec les articles de police pertinents.
5. Ne pas exécuter toutes les sections aveuglément — choisir celles qui sont pertinentes selon le contenu du dossier.
6. Rapporter les résultats de manière structurée avec les scores de confiance.

**Workflow typique** :
1. Vérifier les champs extraits → identifier le type de dossier
2. Lister les analyses disponibles → sélectionner les pertinentes
3. Exécuter les analyses sélectionnées
4. Consolider et résumer les résultats
"""


# ---------------------------------------------------------------------------
# Chat client factory
# ---------------------------------------------------------------------------


def _get_chat_client(
    settings: Settings, tier: str = "chat"
) -> OpenAIChatClient | OpenAIChatCompletionClient:
    """Return a cached ``OpenAIChatClient`` for ``(settings, tier)``.

    Each workflow invocation creates 3-5 agents that all need a chat client,
    and ``execute_workflow`` is hit repeatedly per dossier. Rebuilding the
    underlying ``AsyncAzureOpenAI`` HTTP client (and its connection pool) on
    every call wastes ~10-30 ms per agent and forces ``DefaultAzureCredential``
    to re-bootstrap. Caching is safe because:

    * ``Settings`` is a process-wide singleton (``load_settings`` is cached).
    * ``DefaultAzureCredential`` transparently refreshes expired tokens, so the
      same credential instance is fine for the lifetime of the process.
    * ``OpenAIChatClient`` / ``AsyncAzureOpenAI`` are designed to be shared.

    The cache key includes ``id(settings)`` so hot-reloading settings in tests
    (which produces a new instance) invalidates entries automatically.
    """
    openai = settings.openai
    cache_key = (
        openai.endpoint, openai.use_azure_ad, openai.api_key,
        openai.get_deployment(tier), openai.chat_api_version or openai.api_version,
        settings.foundry.agents_openai_api,
    )
    cached = _CHAT_CLIENT_CACHE.get(cache_key)
    if cached is not None:
        logger.debug("Agent chat client reused from cache (tier=%s)", tier)
        return cached
    with start_span("chat.client_setup"):
        client = _build_chat_client(settings, tier)
    _CHAT_CLIENT_CACHE[cache_key] = client
    deployment, model = openai.get_deployment(tier)
    logger.info(
        "Agent chat client created: tier=%s deployment=%s model=%s api=%s auth=%s endpoint=%s "
        "maf_instrumentation=%s maf_sensitive_data=%s",
        tier, deployment, model, settings.foundry.agents_openai_api,
        "azure_ad" if openai.use_azure_ad else "api_key", urlparse(openai.endpoint).netloc,
        OBSERVABILITY_SETTINGS.enable_instrumentation, OBSERVABILITY_SETTINGS.enable_sensitive_data,
    )
    return client


_CHAT_CLIENT_CACHE: dict[tuple, OpenAIChatClient | OpenAIChatCompletionClient] = {}
_CHAT_TOKEN_PROVIDERS: dict[int, Any] = {}
_CHAT_CREDENTIALS: list[Any] = []


async def _http_request_started(request: Any) -> None:
    request.extensions["workbenchiq.started"] = time.perf_counter()


async def _http_response_received(response: Any) -> None:
    started = response.request.extensions.get("workbenchiq.started")
    if started is not None:
        logger.info(
            "chat HTTP attempt: headers_ms=%.1f status=%s request_id=%s",
            (time.perf_counter() - started) * 1000,
            response.status_code,
            response.headers.get("x-request-id") or response.headers.get("apim-request-id"),
        )


async def initialize_chat_runtime(settings: Settings) -> dict[str, float]:
    started = time.perf_counter()
    with start_span("chat.initialize_runtime"):
        await create_chat_agent(settings, use_corrections=False)
        setup_ms = round((time.perf_counter() - started) * 1000, 1)
        provider = _CHAT_TOKEN_PROVIDERS.get(id(_get_chat_client(settings)))
        auth_started = time.perf_counter()
        if provider is not None:
            await asyncio.wait_for(provider(), timeout=30)
        return {
            "setup_ms": setup_ms,
            "auth_ms": round((time.perf_counter() - auth_started) * 1000, 1),
            "total_ms": round((time.perf_counter() - started) * 1000, 1),
        }


async def close_chat_runtime() -> None:
    clients = list(_CHAT_CLIENT_CACHE.values())
    _CHAT_CLIENT_CACHE.clear()
    _CHAT_TOKEN_PROVIDERS.clear()
    try:
        await asyncio.gather(*(client.client.close() for client in clients))
    finally:
        credentials = list(_CHAT_CREDENTIALS)
        _CHAT_CREDENTIALS.clear()
        for credential in credentials:
            await asyncio.to_thread(credential.close)


def _build_chat_client(
    settings: Settings, tier: str = "chat"
) -> OpenAIChatClient | OpenAIChatCompletionClient:
    """Create the MAF chat client from workbench settings.

    ``AGENTS_OPENAI_API`` selects the API: ``responses`` (``OpenAIChatClient``, default)
    or ``chat_completions`` (``OpenAIChatCompletionClient``, rollback path).

    Tier controls which deployment to use:
      - "primary" → configured primary model (main analysis)
      - "chat"    → configured chat deployment (interactive Q&A; falls back to primary)
      - "nano"    → configured GPT-5.4 nano deployment (labels, context, titles)

    Always uses the direct Azure OpenAI endpoint (AZURE_OPENAI_ENDPOINT) —
    NOT the Foundry project endpoint, which requires a different token audience
    (https://ai.azure.com) and causes 401 errors with the OpenAI chat API.
    The Foundry project endpoint is only used for Agent Service calls (web intelligence).

    Uses Azure AD authentication via DefaultAzureCredential.
    """
    from azure.identity import (
        DefaultAzureCredential, ManagedIdentityCredential, get_bearer_token_provider,
    )
    from openai import AsyncAzureOpenAI, DefaultAsyncHttpxClient

    endpoint = settings.openai.endpoint
    if not endpoint:
        raise RuntimeError("AZURE_OPENAI_ENDPOINT not configured.")

    deployment, _model = settings.openai.get_deployment(tier)
    api_version = settings.openai.chat_api_version or settings.openai.api_version
    client_cls = (
        OpenAIChatCompletionClient
        if settings.foundry.agents_openai_api == "chat_completions"
        else OpenAIChatClient
    )

    if settings.openai.use_azure_ad:
        if os.getenv("IDENTITY_ENDPOINT") and not os.getenv("AZURE_TOKEN_CREDENTIALS"):
            credential = ManagedIdentityCredential(client_id=os.getenv("AZURE_CLIENT_ID") or None)
        else:
            credential = DefaultAzureCredential()
        _CHAT_CREDENTIALS.append(credential)
        sync_token_provider = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )

        async def token_provider() -> str:
            started = time.perf_counter()
            with start_span("chat.authentication") as span:
                try:
                    return await asyncio.to_thread(sync_token_provider)
                finally:
                    duration = round((time.perf_counter() - started) * 1000, 1)
                    span.set_attribute("workbenchiq.chat.auth_ms", duration)
                    logger.info("chat authentication: duration_ms=%.1f", duration)

        async_client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            azure_deployment=deployment,
            api_version=api_version,
            azure_ad_token_provider=token_provider,
            http_client=DefaultAsyncHttpxClient(
                event_hooks={"request": [_http_request_started], "response": [_http_response_received]}
            ),
            max_retries=1,
            timeout=90.0,
        )
        client = client_cls(model=deployment, async_client=async_client)
        _CHAT_TOKEN_PROVIDERS[id(client)] = token_provider
        return client

    if not settings.openai.api_key:
        raise RuntimeError("AZURE_OPENAI_API_KEY manquant (et use_azure_ad=false).")

    async_client = AsyncAzureOpenAI(
        azure_endpoint=endpoint,
        azure_deployment=deployment,
        api_version=api_version,
        api_key=settings.openai.api_key,
        http_client=DefaultAsyncHttpxClient(
            event_hooks={"request": [_http_request_started], "response": [_http_response_received]}
        ),
        max_retries=1,
        timeout=90.0,
    )
    return client_cls(
        model=deployment,
        async_client=async_client,
    )


async def create_chat_agent(
    settings: Settings | None = None,
    instructions_override: str | None = None,
    persona: str = "underwriting",
    current_query: str | None = None,
    use_corrections: bool = True,
    language: str = "fr",
) -> Agent:
    """Create the ChatAgent (Phase 1) — interactive Q&A with tool use.

    When a current_query is provided and use_corrections is True,
    dynamically injects relevant few-shot corrections from the feedback
    loop into the agent instructions.
    """
    if settings is None:
        settings = load_settings()

    lang_instr = "Répondre en français" if language == "fr" else "ALWAYS respond in English"
    instructions = instructions_override or CHAT_AGENT_INSTRUCTIONS.format(
        brand=settings.brand_name, language_instruction=lang_instr
    )

    # Dynamic few-shot enrichment from feedback loop
    if current_query and use_corrections and not instructions_override:
        few_shot_block = await _build_few_shot_block(
            current_query, persona, agent_type="chat", settings=settings
        )
        if few_shot_block:
            instructions = instructions + few_shot_block

    return _create_agent(
        _get_chat_client(settings),
        name="ChatAgent",
        default_options=_agent_options(settings, effort=settings.openai.chat_reasoning_effort),
        instructions=instructions,
        tools=[
            # Phase 1 — Policy & glossary
            search_policies,
            get_glossary,
            # Phase 1 — Application context (core + P1 enrichments)
            get_application_summary,
            get_risk_analysis,
            get_customer360_overview,
            get_image_descriptions,
            # Phase 2 — Extraction quality & organization
            get_confidence_scores,
            get_file_list,
            # Phase 3 — Document classification & communications
            classify_documents,
            get_communications,
            get_document_sentiment,
            # Phase 3 — Multimodal data
            get_damage_areas_multimodal,
            get_page_reference,
            # Phase 1 — Metadata queries
            query_fabric_data,
            resolve_web_tool(settings),
            analyze_image_fraud,
        ],
    )


async def create_analysis_agent(
    settings: Settings | None = None,
    instructions_override: str | None = None,
) -> Agent:
    """Create the AnalysisAgent (Phase 2) — prompt-based analysis."""
    if settings is None:
        settings = load_settings()

    instructions = instructions_override or ANALYSIS_AGENT_INSTRUCTIONS.format(
        brand=settings.brand_name
    )

    return _create_agent(
        _get_chat_client(settings),
        name="AnalysisAgent",
        default_options=_agent_options(settings),
        instructions=instructions,
        tools=[
            analyze_section,
            list_available_analyses,
            get_extracted_fields,
            search_policies,
            get_application_summary,
        ],
    )
