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

from app.agents import workflows as wf
from app.agents.agents import (
    _agent_options,
    _build_chat_client,
    _create_agent,
    create_webiq_tool,
)
from app.agents.workflows import _contains_refusal, _resp_text, _sanitize_refusal
from app.config import load_settings

_MISSING = object()


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
    monkeypatch.setattr("azure.identity.get_bearer_token_provider", lambda *args: lambda: "test-token")
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
        return httpx.Response(200, json={
            "id": "resp_test", "object": "response", "created_at": 1,
            "status": "completed", "model": "gpt-5.4-mini",
            "output": [{"id": "msg_test", "type": "message", "role": "assistant",
                        "status": "completed", "content": [{"type": "output_text",
                        "text": "Analyse disponible.", "annotations": []}]}],
        })

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as transport:
            client = OpenAIChatClient(model="insurance-mini", async_client=AsyncOpenAI(
                api_key="test", http_client=transport,
            ))
            agent = _create_agent(client, name="Test", instructions="Respond briefly.",
                                  default_options=_agent_options(load_settings()))
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


def test_web_tool_resolution_prefers_webiq_when_configured(monkeypatch):
    from app.agents.tools import resolve_web_tool, web_search, webiq_search

    _base_openai_env(monkeypatch)
    monkeypatch.delenv("WEBIQ_API_KEY", raising=False)
    assert resolve_web_tool(load_settings()) is web_search
    monkeypatch.setenv("WEBIQ_API_KEY", "test-webiq-key")
    assert resolve_web_tool(load_settings()) is webiq_search


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

    async def _fake_run(agent, prompt, *, agent_name, max_retries=1):
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

    async def _fake_run(agent, prompt, *, agent_name, max_retries=1):
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
    assert result["summary"] == "[RiskAgent] ok"


def test_fraud_workflow_runs_vision_and_web_in_parallel(monkeypatch):
    monkeypatch.delenv("WEBIQ_API_KEY", raising=False)
    running, peak = 0, 0

    async def _fake_run(agent, prompt, *, agent_name, max_retries=1):
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
    assert [s["agent"] for s in result["steps"]] == ["FraudDetector", "WebIntelligence", "CrossChecker"]


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
