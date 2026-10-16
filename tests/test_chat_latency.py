from __future__ import annotations

import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import api_server
from app import openai_client


def test_suggestions_provider_does_not_block_other_requests(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    settings = SimpleNamespace(openai=object(), brand_name="PrevaIQ")
    dossier = SimpleNamespace(
        context_labels=[],
        context_tasks=[],
        llm_outputs={},
        persona="underwriting",
        status="completed",
    )
    settings.app = SimpleNamespace(storage_root="unused")
    monkeypatch.setattr(api_server, "load_settings", lambda: settings)
    monkeypatch.setattr(api_server, "load_application", lambda *args: dossier)

    def slow_provider(*args, **kwargs):
        assert kwargs["timeout"] == 15
        assert kwargs["max_retries"] == 1
        entered.set()
        assert release.wait(timeout=2), "The event loop could not release the provider"
        return {"content": '{"suggestions": ["Statut ?", "Statut ?"]}'}

    monkeypatch.setattr(openai_client, "chat_completion", slow_provider)

    async def exercise():
        request = asyncio.create_task(api_server.generate_chat_suggestions("APP-1"))
        try:
            assert await asyncio.to_thread(entered.wait, 1)
            assert not request.done()
        finally:
            release.set()
        result = await request
        assert result == {"suggestions": ["Statut ?"], "source": "llm"}

    asyncio.run(exercise())


def test_corrections_skip_embedding_without_eligible_examples(monkeypatch):
    from app import feedback
    from app.agents.agents import _build_few_shot_block
    from app.rag.embeddings import EmbeddingService

    eligibility = AsyncMock(return_value=False)
    embedding = MagicMock(side_effect=AssertionError("Embedding must not run"))
    monkeypatch.setattr(feedback, "has_eligible_few_shots", eligibility)
    monkeypatch.setattr(EmbeddingService, "get_embedding", embedding)
    settings = SimpleNamespace(openai=object(), rag=object())
    result = asyncio.run(_build_few_shot_block("Statut ?", "automotive_claims", "chat", settings))
    assert result == ""
    eligibility.assert_awaited_once_with("automotive_claims", "chat")
    embedding.assert_not_called()


def test_corrections_keep_enrichment_when_eligible_examples_exist(monkeypatch):
    from app import feedback
    from app.agents.agents import _build_few_shot_block
    from app.rag import embeddings

    monkeypatch.setattr(feedback, "has_eligible_few_shots", AsyncMock(return_value=True))
    lookup = AsyncMock(
        return_value=[
            {
                "query": "Statut ?",
                "similarity": 0.95,
                "bad_response": "Inconnu",
                "good_response": "En cours",
            }
        ]
    )
    monkeypatch.setattr(feedback, "get_relevant_few_shots", lookup)
    monkeypatch.setattr(
        embeddings,
        "EmbeddingService",
        lambda *args: SimpleNamespace(
            get_embedding=lambda query: [0.1, 0.2],
        ),
    )
    settings = SimpleNamespace(openai=object(), rag=object())
    result = asyncio.run(_build_few_shot_block("Statut ?", "automotive_claims", "chat", settings))
    assert "En cours" in result
    assert lookup.await_args.kwargs["embedding"] == [0.1, 0.2]


def test_missing_correction_store_is_not_eligible(monkeypatch):
    from app import feedback

    monkeypatch.setattr(feedback, "get_pool", AsyncMock(side_effect=RuntimeError("No pool")))
    assert asyncio.run(feedback.has_eligible_few_shots("automotive_claims", "chat")) is False


def test_conversation_reports_load_and_save_timings(monkeypatch):
    from app.agents import api_integration

    settings = SimpleNamespace(app=SimpleNamespace(storage_root="unused"))
    monkeypatch.setattr(api_server, "load_settings", lambda: settings)
    monkeypatch.setattr(
        api_server, "load_application", lambda *args: SimpleNamespace(persona="automotive_claims")
    )
    saved = MagicMock()
    monkeypatch.setattr(api_server, "save_conversation", saved)
    run = AsyncMock(return_value={"response": "En cours", "agent": {"timings_ms": {"total_ms": 1}}})
    monkeypatch.setattr(api_integration, "agent_chat", run)
    result = asyncio.run(
        api_server.create_or_continue_conversation(
            "APP-1",
            api_server.ChatRequest(message="Statut ?"),
        )
    )
    timings = result["agent"]["timings_ms"]
    assert timings["conversation_load_ms"] >= 0
    assert timings["conversation_save_ms"] >= 0
    assert timings["request_ms"] >= timings["conversation_load_ms"]
    assert saved.call_args.args[2]["messages"][-1]["content"] == "En cours"
    assert run.await_args.kwargs["agent_type"] == "auto"


def test_warmup_initializes_agent_and_auth_without_model_calls(monkeypatch):
    from app.agents import agents

    client = SimpleNamespace(run=AsyncMock(side_effect=AssertionError("No model warmup")))
    create = AsyncMock(return_value=client)
    provider = AsyncMock(return_value="not-logged")
    monkeypatch.setattr(agents, "create_chat_agent", create)
    monkeypatch.setattr(agents, "_get_chat_client", lambda settings: client)
    monkeypatch.setattr(agents, "_CHAT_TOKEN_PROVIDERS", {id(client): provider})
    settings = object()
    timings = asyncio.run(agents.initialize_chat_runtime(settings))
    create.assert_awaited_once_with(settings, use_corrections=False)
    provider.assert_awaited_once_with()
    client.run.assert_not_called()
    assert timings["total_ms"] >= timings["setup_ms"]
    assert timings["auth_ms"] >= 0


def test_warmup_failure_closes_resources(monkeypatch):
    import pytest

    from app.agents import agents, runtime

    close = AsyncMock()
    monkeypatch.setattr(agents, "initialize_chat_runtime", AsyncMock(side_effect=RuntimeError("auth")))
    monkeypatch.setattr(agents, "close_chat_runtime", close)
    settings = SimpleNamespace(openai=SimpleNamespace(endpoint="https://example.test"))
    with pytest.raises(RuntimeError, match="auth"):
        asyncio.run(runtime.warmup_chat(settings))
    close.assert_awaited_once_with()


def test_chat_readiness_tracks_initialization(monkeypatch):
    monkeypatch.setattr(api_server.app.state, "chat_runtime", None, raising=False)
    assert asyncio.run(api_server.health_check_chat()).status_code == 503
    api_server.app.state.chat_runtime = {"total_ms": 1}
    assert asyncio.run(api_server.health_check_chat()).status_code == 200


def test_runtime_shutdown_closes_cached_clients_and_credentials(monkeypatch):
    from app.agents import agents

    client = SimpleNamespace(client=SimpleNamespace(close=AsyncMock()))
    credential = SimpleNamespace(close=MagicMock())
    monkeypatch.setattr(agents, "_CHAT_CLIENT_CACHE", {("test",): client})
    monkeypatch.setattr(agents, "_CHAT_CREDENTIALS", [credential])
    monkeypatch.setattr(agents, "_CHAT_TOKEN_PROVIDERS", {id(client): object()})
    asyncio.run(agents.close_chat_runtime())
    client.client.close.assert_awaited_once_with()
    credential.close.assert_called_once_with()
    assert not agents._CHAT_CLIENT_CACHE
    assert not agents._CHAT_TOKEN_PROVIDERS
    assert not agents._CHAT_CREDENTIALS


def test_stream_delivers_text_before_saved_final_result(monkeypatch):
    import json

    from app.agents import api_integration

    settings = SimpleNamespace(app=SimpleNamespace(storage_root="unused"))
    monkeypatch.setattr(api_server, "load_settings", lambda: settings)
    monkeypatch.setattr(
        api_server, "load_application", lambda *args: SimpleNamespace(persona="automotive_claims")
    )
    saved = MagicMock()
    monkeypatch.setattr(api_server, "save_conversation", saved)

    async def run(*args, on_delta, **kwargs):
        await on_delta("En ")
        await on_delta("cours")
        return {"response": "En cours", "agent": {"tools_called": [], "timings_ms": {}}}

    monkeypatch.setattr(api_integration, "agent_chat", run)

    async def exercise():
        response = await api_server.create_or_continue_conversation(
            "APP-1", api_server.ChatRequest(message="Statut ?", stream=True)
        )
        events = [chunk async for chunk in response.body_iterator if chunk.startswith("data: ")]
        return [json.loads(chunk[6:]) for chunk in events]

    events = asyncio.run(exercise())
    assert [event["type"] for event in events] == ["delta", "delta", "done"]
    assert events[-1]["result"]["response"] == "En cours"
    assert events[-1]["result"]["agent"]["tools_called"] == []
    assert saved.call_args.args[2]["messages"][-1]["content"] == "En cours"


def test_stream_preserves_structured_errors_and_cancels_on_disconnect(monkeypatch):
    import json

    async def fail(*args):
        raise api_server.HTTPException(503, {"code": "AI_SERVICE_UNAVAILABLE"})

    monkeypatch.setattr(api_server, "_complete_conversation", fail)

    async def exercise_error():
        response = await api_server.create_or_continue_conversation(
            "APP-1", api_server.ChatRequest(message="Statut ?", stream=True)
        )
        return [chunk async for chunk in response.body_iterator if chunk.startswith("data: ")]

    [event] = asyncio.run(exercise_error())
    assert json.loads(event[6:])["detail"]["code"] == "AI_SERVICE_UNAVAILABLE"

    cancelled = []

    async def wait(*args):
        try:
            await args[2]("Premiers mots")
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    monkeypatch.setattr(api_server, "_complete_conversation", wait)

    async def exercise_cancel():
        response = await api_server.create_or_continue_conversation(
            "APP-1", api_server.ChatRequest(message="Statut ?", stream=True)
        )
        await anext(response.body_iterator)
        await anext(response.body_iterator)
        await response.body_iterator.aclose()

    asyncio.run(exercise_cancel())
    assert cancelled == [True]
