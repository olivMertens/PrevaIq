"""Regression tests locking WorkbenchIQ agent + workflow contracts.

These are pure-construction / pure-function tests — no network, no live LLM.
CI runs ruff + import-check only (not pytest), so these act as local contract
locks. They exist to catch silent regressions in:

* ``_resp_text`` — the AgentResponse text-extraction shim (simplified in PR #20).
* ``_sanitize_refusal`` / ``_contains_refusal`` — the ``> ⚠️`` refusal marker the
  frontend renders as Markdown inside ``steps[].text``.
* ``_build_chat_client`` — chat-client construction on BOTH auth paths. This is the
  test that would have caught the ``model_id=`` → ``model=`` regression the 1.9
  framework bump exposed on the api-key path.
* The workflow result dict shape ``{workflow, status, steps:[{agent, text}], summary}``
  consumed verbatim by the frontend.
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from openai import AsyncOpenAI
from agent_framework import MCPStreamableHTTPTool
from agent_framework.openai import OpenAIChatClient

from app.agents import tools as agent_tools
from app.agents import workflows as wf
from app.agents.agents import (
    _agent_options,
    _build_chat_client,
    _create_agent,
    create_webiq_tool,
)
from app.agents.workflows import _contains_refusal, _resp_text, _sanitize_refusal
from app.config import load_settings
from app.jurisdiction import Jurisdiction
from app.languages import language_instruction, localized_message

_MISSING = object()


@pytest.fixture(autouse=True)
def _clear_webiq_cache():
    agent_tools._webiq_cache.clear()
    yield
    agent_tools._webiq_cache.clear()


class _FakeResp:
    """Stand-in for AgentResponse with a controllable ``.text`` and known ``str()``."""

    def __init__(self, text=_MISSING):
        if text is not _MISSING:
            self.text = text

    def __str__(self) -> str:
        return "STR_FALLBACK"


# ── _resp_text: 5 shapes + None ──────────────────────────────────────────────


def test_resp_text_returns_text_when_present():
    assert _resp_text(_FakeResp("hello")) == "hello"


def test_resp_text_never_leaks_object_repr():
    for resp in (_FakeResp("   "), _FakeResp(), _FakeResp(None), _FakeResp(""), None):
        assert _resp_text(resp) == ""


# ── Refusal handling / UI marker ─────────────────────────────────────────────


def test_sanitize_refusal_truncates_and_flags():
    text = "Voici l'analyse structurée.\n\nI'm sorry, but I cannot assist with that request."
    out = _sanitize_refusal(text, agent_name="ExtractAgent")
    assert "I'm sorry" not in out
    assert "cannot assist" not in out
    assert "⚠️" in out  # frontend renders this Markdown blockquote marker
    assert "requires_human_review: true" in out
    assert out.startswith("Voici l'analyse structurée.")


def test_sanitize_refusal_passthrough_when_clean():
    text = "Analyse complète. Aucun refus détecté."
    assert _sanitize_refusal(text) == text


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "manual review"),
        ("fr", "revue manuelle"),
        ("de", "manuelle Prüfung"),
        ("de-CH", "manuelle Prüfung"),
    ],
)
def test_sanitize_refusal_localizes_review_marker(language, expected):
    text = "Structured analysis.\n\nI'm sorry, but I cannot assist with that request."
    assert expected in _sanitize_refusal(text, language=language)


def test_contains_refusal_detects_en_and_fr():
    assert _contains_refusal("I'm sorry, but I cannot assist")
    assert _contains_refusal("Je suis désolé, mais je ne peux pas vous aider")
    assert not _contains_refusal("Analyse normale, recommandation documentée.")


# ── _build_chat_client: both auth paths (model_id regression guard) ──────────


def _base_openai_env(monkeypatch):
    monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", "https://example.openai.azure.com")
    monkeypatch.setenv("AZURE_OPENAI_API_KEY", "x" * 40)


def test_build_chat_client_api_key_path(monkeypatch):
    """use_azure_ad=false must construct an OpenAIChatClient.

    Before the fix this raised ``TypeError: unexpected keyword argument 'model_id'``.
    """
    _base_openai_env(monkeypatch)
    monkeypatch.setenv("AZURE_OPENAI_USE_AZURE_AD", "false")
    settings = load_settings()
    client = _build_chat_client(settings, "chat")
    assert isinstance(client, OpenAIChatClient)


def test_build_chat_client_azure_ad_path(monkeypatch):
    """use_azure_ad=true must construct an OpenAIChatClient (lazy credential, no network)."""
    _base_openai_env(monkeypatch)
    monkeypatch.setenv("AZURE_OPENAI_USE_AZURE_AD", "true")
    settings = load_settings()
    client = _build_chat_client(settings, "chat")
    assert isinstance(client, OpenAIChatClient)


def test_azure_token_provider_is_awaitable(monkeypatch):
    _base_openai_env(monkeypatch)
    monkeypatch.setenv("AZURE_OPENAI_USE_AZURE_AD", "true")
    monkeypatch.setattr(
        "azure.identity.get_bearer_token_provider", lambda *args: lambda: "test-token"
    )
    client = _build_chat_client(load_settings(), "chat")
    assert asyncio.run(client.client._azure_ad_token_provider()) == "test-token"


def test_chat_defaults_to_primary_without_assuming_deployment_alias(monkeypatch):
    _base_openai_env(monkeypatch)
    monkeypatch.delenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_CHAT_MODEL_NAME", raising=False)
    monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT_NAME", "insurance-mini")
    monkeypatch.setenv("AZURE_OPENAI_MODEL_NAME", "gpt-5.4-mini")
    settings = load_settings()
    assert settings.openai.get_deployment("chat") == ("insurance-mini", "gpt-5.4-mini")
    assert _agent_options(settings) == {"reasoning": {"effort": "low"}}
    assert settings.openai.chat_reasoning_effort == "none"
    assert _agent_options(settings, effort=settings.openai.chat_reasoning_effort) == {
        "reasoning": {"effort": "none"}
    }


def test_invalid_agent_reasoning_effort_is_rejected(monkeypatch):
    _base_openai_env(monkeypatch)
    monkeypatch.setenv("AZURE_OPENAI_MODEL_NAME", "gpt-5.4-mini")
    with pytest.raises(ValueError):
        _agent_options(load_settings(), effort="turbo")


def test_non_reasoning_model_does_not_receive_reasoning_options():
    assert _agent_options(_fake_settings()) == {}


def test_chat_completions_rollback_flag(monkeypatch):
    from agent_framework.openai import OpenAIChatCompletionClient

    _base_openai_env(monkeypatch)
    monkeypatch.setenv("AZURE_OPENAI_USE_AZURE_AD", "false")
    monkeypatch.setenv("AZURE_OPENAI_MODEL_NAME", "gpt-5.4-mini")
    monkeypatch.setenv("AGENTS_OPENAI_API", "chat_completions")
    settings = load_settings()
    assert isinstance(_build_chat_client(settings, "chat"), OpenAIChatCompletionClient)
    assert _agent_options(settings) == {"reasoning_effort": "low"}


def test_reasoning_low_reaches_responses_request(monkeypatch):
    _base_openai_env(monkeypatch)
    monkeypatch.setenv("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME", "insurance-mini")
    monkeypatch.setenv("AZURE_OPENAI_CHAT_MODEL_NAME", "gpt-5.4-mini")
    monkeypatch.setenv("AZURE_OPENAI_REASONING_EFFORT", "low")
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "object": "response",
                "created_at": 1,
                "status": "completed",
                "model": "gpt-5.4-mini",
                "output": [
                    {
                        "id": "msg_test",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {
                                "type": "output_text",
                                "text": "Analyse disponible.",
                                "annotations": [],
                            }
                        ],
                    }
                ],
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
            client = OpenAIChatClient(
                model="insurance-mini",
                async_client=AsyncOpenAI(
                    api_key="test",
                    http_client=transport,
                ),
            )
            agent = _create_agent(
                client,
                name="Test",
                instructions="Respond briefly.",
                default_options=_agent_options(load_settings()),
            )
            result = await agent.run("Bonjour")
            assert result.text == "Analyse disponible."

    asyncio.run(run())
    assert requests[0]["model"] == "insurance-mini"
    assert requests[0]["reasoning"] == {"effort": "low"}


def test_webiq_tool_is_absent_without_key(monkeypatch):
    _base_openai_env(monkeypatch)
    monkeypatch.delenv("WEBIQ_API_KEY", raising=False)
    assert create_webiq_tool(load_settings()) is None


def test_webiq_tool_scopes_key_and_tools(monkeypatch):
    _base_openai_env(monkeypatch)
    monkeypatch.setenv("WEBIQ_API_KEY", "test-webiq-key")
    tool = create_webiq_tool(load_settings())
    assert isinstance(tool, MCPStreamableHTTPTool)
    assert tool.url == "https://api.microsoft.ai/v3/mcp"
    assert tool._static_headers == {"x-apikey": "test-webiq-key"}
    assert set(tool.allowed_tools) == {"web", "news", "browse"}
    assert not tool.is_connected


def test_webiq_mcp_runtime_dependencies_are_installed():
    # MAF MCP tools open sessions with the MCP v2 client and recover them with tenacity;
    # with an older mcp or without tenacity every Web IQ call fails at connection time.
    import mcp
    import tenacity

    assert hasattr(mcp, "Client")
    assert tenacity.AsyncRetrying


def test_web_tool_resolution_prefers_webiq_when_configured(monkeypatch):
    from app.agents.tools import resolve_web_tool, webiq_search

    _base_openai_env(monkeypatch)
    monkeypatch.delenv("WEBIQ_API_KEY", raising=False)
    assert resolve_web_tool(load_settings()) is webiq_search
    monkeypatch.setenv("WEBIQ_API_KEY", "test-webiq-key")
    assert resolve_web_tool(load_settings()) is webiq_search


class _FakeWebIqFunction:
    name = "webiq_web"

    def __init__(self, response):
        self.response = response
        self.arguments = None

    def parameters(self):
        return {
            "properties": {
                "query": {},
                "maxResults": {},
                "language": {},
                "region": {},
                "contentFormat": {},
                "maxLength": {},
            }
        }

    async def invoke(self, *, arguments):
        self.arguments = arguments
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


class _FakeWebIqTool:
    def __init__(self, function):
        self.functions = [function]

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False


@pytest.mark.parametrize("language", ["de-DE", "de-CH"])
def test_webiq_search_localizes_request_and_preserves_source(monkeypatch, language):
    from app.agents.tools import webiq_search

    function = _FakeWebIqFunction(
        [
            SimpleNamespace(
                text=json.dumps(
                    {
                        "webResults": [
                            {
                                "title": "Décret français",
                                "url": "https://example.test/decret",
                                "content": "Citation source française inchangée.",
                            }
                        ]
                    }
                )
            )
        ]
    )
    monkeypatch.setattr(
        "app.agents.tools.create_webiq_tool", lambda settings: _FakeWebIqTool(function)
    )

    result = asyncio.run(webiq_search("Hochwasser Nîmes", language=language))

    assert function.arguments["language"] == "de"
    assert function.arguments["region"] == "FR"
    assert "Quelle: https://example.test/decret" in result
    assert "Citation source française inchangée." in result


def test_webiq_search_localizes_missing_configuration(monkeypatch):
    from app.agents.tools import webiq_search

    monkeypatch.setattr("app.agents.tools.create_webiq_tool", lambda settings: None)

    result = asyncio.run(webiq_search("test", language="de"))

    assert result == "Web-Intelligenz ist nicht verfügbar, da Web IQ nicht konfiguriert ist."


@pytest.mark.parametrize("failure", [PermissionError("denied"), asyncio.TimeoutError()])
def test_webiq_search_localizes_runtime_failures(monkeypatch, failure):
    from app.agents.tools import webiq_search

    function = _FakeWebIqFunction(failure)
    monkeypatch.setattr(
        "app.agents.tools.create_webiq_tool", lambda settings: _FakeWebIqTool(function)
    )

    result = asyncio.run(webiq_search("test", language="en"))

    assert result == "Web intelligence is temporarily unavailable."


def test_webiq_search_caches_successful_results_only(monkeypatch):
    from app.agents.tools import webiq_search

    payload = {"webResults": [{"title": "Météo", "url": "https://example.test/m", "content": "x"}]}
    calls = []

    class _CountingFunction(_FakeWebIqFunction):
        async def invoke(self, *, arguments):
            calls.append(arguments["query"])
            return await super().invoke(arguments=arguments)

    good = _CountingFunction([SimpleNamespace(text=json.dumps(payload))])
    monkeypatch.setattr("app.agents.tools.create_webiq_tool", lambda s: _FakeWebIqTool(good))
    first = asyncio.run(webiq_search("météo Bordeaux 27 mars 2026", language="fr"))
    second = asyncio.run(webiq_search("  Météo  Bordeaux 27 mars 2026 ", language="fr"))
    assert first == second and "https://example.test/m" in first
    assert len(calls) == 1

    failing = _CountingFunction(PermissionError("throttled"))
    monkeypatch.setattr("app.agents.tools.create_webiq_tool", lambda s: _FakeWebIqTool(failing))
    for _ in range(2):
        asyncio.run(webiq_search("arrêté catastrophe naturelle Albi", language="fr"))
    assert calls[1:] == ["arrêté catastrophe naturelle Albi"] * 2


@pytest.mark.parametrize(
    ("lieu", "adresse", "ville", "expected"),
    [
        ("42 rue des Vignobles, 33000 Bordeaux - cave et sous-sol", "", "", "Bordeaux"),
        ("10 Chemin de Falgarde, 81000 Albi — Cave + RDC", "", "", "Albi"),
        ("Cave de la maison, 42 rue des Vignobles, 33000 Bordeaux", "", "", "Bordeaux"),
        ("", "12 rue Paradis, 13001 Marseille 1er", "", "Marseille"),
        ("", "", "33000 BORDEAUX CEDEX", "BORDEAUX"),
        ("Autoroute A7, sortie 15", "", "Saint-Étienne", "Saint-Étienne"),
        ("Autoroute A7, sortie 15", "", "", ""),
    ],
)
def test_search_place_keeps_only_the_municipality(lieu, adresse, ville, expected):
    assert agent_tools._search_place(lieu, adresse, ville) == expected


@pytest.mark.parametrize(
    ("lieu", "adresse", "ville", "expected"),
    [
        ("Kakaogasse 7, 8400 Winterthur", "", "", "Winterthur"),
        ("", "Kakaogasse 7, CH-8400 Winterthur ZH", "", "Winterthur"),
        ("", "Marktgasse 12, 9000 St. Gallen", "", "St. Gallen"),
        ("Laden und Atelier (8400 Winterthur)", "", "", "Winterthur"),
        ("Unwetter vom 28.08.2026 Winterthur", "", "", ""),
        ("Schaden 1'697'400 CHF", "", "Winterthur", "Winterthur"),
    ],
)
def test_search_place_reads_swiss_postcodes(lieu, adresse, ville, expected):
    assert agent_tools._search_place(lieu, adresse, ville, country="CH") == expected


def test_claim_search_place_detects_a_swiss_claim():
    app_md = SimpleNamespace(
        extracted_fields={
            "llm_extracted:LieuSinistre": {"value": "Laden und Atelier, Kakaogasse 7"},
            "cu_extracted:AdresseAssure": {"value": "Kakaogasse 7, 8400 Winterthur"},
            "MontantEstime": "CHF 1'697'400.00",
        }
    )

    assert agent_tools._claim_search_place(app_md) == "Winterthur"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("28.08.2026", ("28. August 2026", "August 2026")),
        ("2026-03-01", ("1. März 2026", "März 2026")),
        ("unbekannt", ("", "")),
    ],
)
def test_german_date_writes_dates_for_search(value, expected):
    assert agent_tools._german_date(value) == expected


def test_claim_search_place_reads_prefixed_extracted_fields():
    app_md = SimpleNamespace(
        extracted_fields={
            "llm_extracted:LieuSinistre": {"value": "Cave, 42 rue des Vignobles"},
            "cu_extracted:AdresseAssure": {"value": "42 rue des Vignobles, 33000 Bordeaux"},
            "Ville": "Mérignac",
        }
    )

    assert agent_tools._claim_search_place(app_md) == "Bordeaux"
    assert agent_tools._claim_search_place(SimpleNamespace(extracted_fields={})) == ""


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("27/03/2026", ("27 mars 2026", "mars 2026")),
        ("2025-10-28", ("28 octobre 2025", "octobre 2025")),
        ("1/8/2025", ("1 août 2025", "août 2025")),
        ("non spécifiée", ("", "")),
        ("31/13/2026", ("", "")),
    ],
)
def test_french_date_writes_dates_for_search(value, expected):
    assert agent_tools._french_date(value) == expected


def _fraud_settings():
    return SimpleNamespace(
        openai=SimpleNamespace(),
        fraud_detection=SimpleNamespace(deployment_name="fraud", model_name="fraud-model"),
    )


def test_claim_web_intelligence_builds_contextual_french_queries(monkeypatch):
    searches, prompts = [], []

    async def fake_search(query, news=False, language="en", region="FR"):
        searches.append((query, news, language, region))
        return f"### Résultat\nSource: https://example.test/{len(searches)}\nPassage"

    def fake_completion(settings, messages, **kwargs):
        prompts.append(messages)
        return {"content": '{"event_verified": true, "findings": [], "overall_assessment": "ok"}'}

    monkeypatch.setattr(agent_tools, "webiq_search", fake_search)
    monkeypatch.setattr("app.openai_client.chat_completion", fake_completion)

    result = agent_tools._run_webiq_intelligence(
        _fraud_settings(),
        claim_date="27/03/2026",
        claim_location=agent_tools._search_place(
            "42 rue des Vignobles, 33000 Bordeaux - cave et sous-sol",
            "42 rue des Vignobles, 33000 Bordeaux",
        ),
        claim_nature="Dégâts des eaux - infiltration suite à tempête",
        claim_type="habitation_claims",
        declared_amount="4 500 €",
        language="en",
    )

    assert searches == [
        ("météo Bordeaux 27 mars 2026 pluie vent orage", False, "fr", "FR"),
        ("arrêté catastrophe naturelle Bordeaux mars 2026", False, "fr", "FR"),
        ("Dégâts des eaux infiltration suite à tempête Bordeaux 27 mars 2026", True, "fr", "FR"),
    ]
    assert not any("rue" in query or "42" in query for query, *_ in searches)
    assert result["search_queries"] == [query for query, *_ in searches]
    assert result["search_region"] == "FR"
    assert result["source_urls"] == [f"https://example.test/{i}" for i in (1, 2, 3)]
    assert language_instruction("en") in prompts[0][0]["content"]
    assert "Suisse" not in prompts[0][1]["content"]


_SWISS_GERMAN = Jurisdiction(country="CH", language="de", currency="CHF", postal_code="8400")
_SWISS_FRENCH = Jurisdiction(country="CH", language="fr", currency="CHF", postal_code="1003")


@pytest.mark.parametrize(
    ("jurisdiction", "place", "date", "nature", "expected"),
    [
        (
            _SWISS_GERMAN,
            "Winterthur",
            "28.08.2026",
            "Hagel / Sturm (Elementarschaden)",
            [
                ("Unwetter Winterthur 28. August 2026 Hagel Sturm", False, "de", "CH"),
                ("Hagel Sturm Winterthur August 2026 Schäden", False, "de", "CH"),
                ("Hagel Sturm Winterthur 28. August 2026", True, "de", "CH"),
            ],
        ),
        (
            _SWISS_GERMAN,
            "Winterthur",
            "28/08/2026",
            "Grêle / tempête (dommage élémentaire)",
            [
                ("Unwetter Winterthur 28. August 2026 Hagel Sturm", False, "de", "CH"),
                ("Hagel Sturm Winterthur August 2026 Schäden", False, "de", "CH"),
                ("Hagel Sturm Winterthur 28. August 2026", True, "de", "CH"),
            ],
        ),
        (
            _SWISS_FRENCH,
            "Lausanne",
            "2026-06-14",
            "Grêle",
            [
                ("intempéries Lausanne 14 juin 2026 grêle orage", False, "fr", "CH"),
                ("Grêle Lausanne juin 2026 dégâts", False, "fr", "CH"),
                ("Grêle Lausanne 14 juin 2026", True, "fr", "CH"),
            ],
        ),
    ],
)
@pytest.mark.parametrize("output_language", ["en", "de-CH"])
def test_claim_web_intelligence_searches_swiss_sources_without_catnat(
    monkeypatch, jurisdiction, place, date, nature, expected, output_language
):
    searches, prompts = [], []

    async def fake_search(query, news=False, language="en", region="FR"):
        searches.append((query, news, language, region))
        return f"### Treffer\nQuelle: https://example.test/{len(searches)}\nPassage"

    def fake_completion(settings, messages, **kwargs):
        prompts.append(messages)
        return {"content": '{"event_verified": true, "findings": [], "overall_assessment": "ok"}'}

    monkeypatch.setattr(agent_tools, "webiq_search", fake_search)
    monkeypatch.setattr("app.openai_client.chat_completion", fake_completion)

    result = agent_tools._run_webiq_intelligence(
        _fraud_settings(),
        claim_date=date,
        claim_location=place,
        claim_nature=nature,
        claim_type="habitation_claims",
        declared_amount="CHF 1'697'400.00",
        language=output_language,
        jurisdiction=jurisdiction,
    )

    assert searches == expected
    assert not any("catastrophe" in query.lower() for query, *_ in searches)
    assert result["search_region"] == "CH"
    assert result["source_urls"] == [f"https://example.test/{i}" for i in (1, 2, 3)]
    assert "Suisse" in prompts[0][1]["content"]
    assert language_instruction(output_language) in prompts[0][0]["content"]


def test_webiq_search_region_is_sent_and_part_of_the_cache_key(monkeypatch):
    from app.agents.tools import webiq_search

    payload = {"webResults": [{"title": "Hagel", "url": "https://example.test/h", "content": "x"}]}
    calls = []

    class _RecordingFunction(_FakeWebIqFunction):
        async def invoke(self, *, arguments):
            calls.append((arguments["query"], arguments["region"]))
            return await super().invoke(arguments=arguments)

    function = _RecordingFunction([SimpleNamespace(text=json.dumps(payload))])
    monkeypatch.setattr("app.agents.tools.create_webiq_tool", lambda s: _FakeWebIqTool(function))

    query = "Unwetter Winterthur 28. August 2026 Hagel Sturm"
    asyncio.run(webiq_search(query, language="de", region="ch"))
    asyncio.run(webiq_search(query, language="de", region="CH"))
    asyncio.run(webiq_search(query, language="de"))
    asyncio.run(webiq_search(query, language="de", region="XX"))

    assert calls == [(query, "CH"), (query, "FR")]


def test_claim_web_intelligence_skips_search_without_municipality(monkeypatch):
    async def forbidden_search(*args, **kwargs):
        raise AssertionError("no generic web search without a municipality")

    monkeypatch.setattr(agent_tools, "webiq_search", forbidden_search)

    result = agent_tools._run_webiq_intelligence(
        _fraud_settings(),
        claim_date="29/01/2026",
        claim_location="",
        claim_nature="Collision / frottement latéral",
        claim_type="automotive_claims",
        declared_amount="non spécifié",
        language="de",
    )

    assert result["skipped"] == "missing_location"
    assert result["overall_assessment"] == localized_message("webiq_missing_location", "de")
    assert result["source_urls"] == [] and result["event_verified"] is None


# ── Workflow result-dict shape (UI data contract) ────────────────────────────


def _stub_workflow(monkeypatch, run):
    monkeypatch.setattr(wf, "_cached_agent", lambda *a, **k: k["name"])
    monkeypatch.setattr(wf, "_run_agent_with_refusal_retry", run)

    async def _context(app_id, *, customer_history=False):
        return "Assuré : Marie Lefevre"

    monkeypatch.setattr(wf, "_read_context", _context)


def test_express_workflow_result_shape(monkeypatch):
    """create_express_workflow must return {workflow,status,steps[{agent,text}],summary}."""
    prompts = {}

    async def _fake_run(agent, prompt, *, agent_name, language="en", max_retries=1):
        prompts[agent_name] = prompt
        return f"[{agent_name}] canned analysis"

    _stub_workflow(monkeypatch, _fake_run)
    result = asyncio.run(wf.create_express_workflow(object(), "APP-1"))

    assert result["workflow"] == "express"
    assert result["status"] == "completed"
    assert [s["agent"] for s in result["steps"]] == ["ExtractAgent", "PolicyAgent", "DecisionAgent"]
    for step in result["steps"]:
        assert set(step) == {"agent", "text"}
    assert result["summary"] == "[DecisionAgent] canned analysis"
    assert "Marie Lefevre" in prompts["ExtractAgent"]
    assert "[PolicyAgent] canned analysis" in prompts["DecisionAgent"]


def test_complet_runs_four_branches_concurrently_and_degrades(monkeypatch):
    running, peak = 0, 0

    async def _fake_run(agent, prompt, *, agent_name, language="en", max_retries=1):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1
        if agent_name == "FraudAgent":
            raise RuntimeError("vision unavailable")
        return f"[{agent_name}] ok"

    _stub_workflow(monkeypatch, _fake_run)
    result = asyncio.run(wf.create_complet_workflow(object(), "APP-1"))

    assert peak == 4
    steps = {s["agent"]: s["text"] for s in result["steps"]}
    assert "requires_human_review: true" in steps["FraudAgent"]
    assert "vision unavailable" not in steps["FraudAgent"]
    assert result["status"] == "needs_review"
    assert result["summary"] == "[RiskAgent] ok"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('```json\n{"requires_human_review": true, "insured_name": "A"}\n```', True),
        ("- requires_human_review: true", True),
        ("> ⚠️ Step: timed out — `requires_human_review: true`.", True),
        ("**requires_human_review**: TRUE", True),
        ('{"requires_human_review": false}', False),
        ("requires_human_review: true_positive_rate", False),
        ("", False),
    ],
)
def test_human_review_flag_is_detected_in_json_and_text(text, expected):
    assert wf._requires_human_review(text) is expected
    status = wf._result("express", [("DecisionAgent", text)])["status"]
    assert status == ("needs_review" if expected else "completed")


@pytest.mark.parametrize(
    ("language", "expected"),
    [
        ("en", "timed out"),
        ("fr", "délai dépassé"),
        ("de", "Zeitüberschreitung"),
        ("de-CH", "Zeitüberschreitung"),
    ],
)
def test_workflow_step_timeout_is_localized(monkeypatch, language, expected):
    async def slow_run(agent, prompt, *, agent_name, language="en", max_retries=1):
        await asyncio.sleep(1)

    monkeypatch.setattr(wf, "_run_agent_with_refusal_retry", slow_run)
    monkeypatch.setattr(wf, "AGENT_TIMEOUT_SECONDS", 0.01)

    result = asyncio.run(wf._run_step(None, "prompt", agent_name="Slow", language=language))

    assert expected in result
    assert "requires_human_review: true" in result


def test_fraud_workflow_runs_vision_and_web_in_parallel(monkeypatch):
    monkeypatch.delenv("WEBIQ_API_KEY", raising=False)
    running, peak = 0, 0

    async def _fake_run(agent, prompt, *, agent_name, language="en", max_retries=1):
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.01)
        running -= 1
        return f"[{agent_name}] ok"

    _stub_workflow(monkeypatch, _fake_run)
    result = asyncio.run(
        wf.create_fraud_workflow(SimpleNamespace(webiq=SimpleNamespace(enabled=False)), "APP-1")
    )

    assert peak == 2
    assert [s["agent"] for s in result["steps"]] == [
        "FraudDetector",
        "WebIntelligence",
        "CrossChecker",
    ]


# ── Agent cache (perf debt #6) ───────────────────────────────────────────────


def _fake_settings():
    openai = SimpleNamespace(
        endpoint="https://example.openai.azure.com",
        use_azure_ad=False,
        api_version="2025-04-01-preview",
        chat_api_version="2025-04-01-preview",
        api_key="x" * 40,
        get_deployment=lambda tier="chat": ("custom-chat", "custom-chat"),
    )
    return SimpleNamespace(openai=openai)


def test_cached_agent_dedupes_identical_config(monkeypatch):
    """Identical (config, name, instructions, tools) must reuse one Agent instance."""
    built = []

    def _fake_create(client, *, name, instructions, tools=None, default_options=None):
        built.append((name, instructions))
        return object()  # unique sentinel per construction

    monkeypatch.setattr(wf, "_get_chat_client", lambda s, tier="chat": object())
    monkeypatch.setattr(wf, "_create_agent", _fake_create)
    wf._AGENT_CACHE.clear()

    settings = _fake_settings()
    a1 = wf._cached_agent(settings, name="X", instructions="INSTR", tools=[])
    a2 = wf._cached_agent(settings, name="X", instructions="INSTR", tools=[])
    assert a1 is a2
    assert len(built) == 1  # built exactly once

    # Different instructions (e.g. another persona/lang) must NOT collide.
    a3 = wf._cached_agent(settings, name="X", instructions="OTHER", tools=[])
    assert a3 is not a1
    assert len(built) == 2

    wf._AGENT_CACHE.clear()
