from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import api_server
from app.underwriting_policies import collect_policy_citations, get_policy_file_for_persona

PROMPTS = Path(__file__).resolve().parents[1] / "prompts"


@pytest.mark.parametrize(
    "persona",
    ["habitation_claims", "property_casualty_claims", "underwriting", "automotive_claims"],
)
def test_policy_detail_uses_the_same_catalog_as_the_persona_list(monkeypatch, persona):
    monkeypatch.setattr(
        api_server,
        "load_settings",
        lambda: SimpleNamespace(app=SimpleNamespace(prompts_root=str(PROMPTS))),
    )
    path = Path(get_policy_file_for_persona(str(PROMPTS), persona))
    expected = json.loads(path.read_text(encoding="utf-8"))["policies"][0]
    result = asyncio.run(api_server.get_policy_by_id(expected["id"], persona))
    assert result == expected


def test_policy_detail_respects_the_configured_catalog_root(monkeypatch, tmp_path):
    policy = {"id": "PC-LOCAL-001", "name": "Local policy contract", "criteria": []}
    path = Path(get_policy_file_for_persona(str(tmp_path), "habitation_claims"))
    path.write_text(json.dumps({"policies": [policy]}), encoding="utf-8")
    monkeypatch.setattr(
        api_server,
        "load_settings",
        lambda: SimpleNamespace(app=SimpleNamespace(prompts_root=str(tmp_path))),
    )
    assert asyncio.run(api_server.get_policy_by_id(policy["id"], "habitation_claims")) == policy
    with pytest.raises(HTTPException) as error:
        asyncio.run(api_server.get_policy_by_id("PC-MISSING", "habitation_claims"))
    assert error.value.status_code == 404


def test_answer_references_resolve_only_exact_ids_in_the_persona_catalog():
    citations = collect_policy_citations(
        str(PROMPTS),
        "habitation_claims",
        "PC-COV-001. CH-AVB-ELE-001-A. PC-COV-001 again. C1 PC-COV-0010 PC-FAKE-009",
    )
    assert [citation["policy_id"] for citation in citations] == ["PC-COV-001", "CH-AVB-ELE-001"]
    assert citations[1]["criteria_id"] == "CH-AVB-ELE-001-A"
    assert all(citation["chunk_type"] == "catalog_reference" for citation in citations)
    assert collect_policy_citations(str(PROMPTS), "underwriting", "PC-COV-001") == []


@pytest.mark.parametrize("stored_persona", ["habitation_claims", None])
def test_saved_answer_gets_verified_links_without_rewriting_stored_conversation(
    monkeypatch, stored_persona
):
    from copy import deepcopy
    from unittest.mock import MagicMock

    conversation = {
        "id": "saved",
        "persona": stored_persona,
        "messages": [
            {"role": "user", "content": "PC-COV-001?"},
            {"role": "assistant", "content": "**PC-COV-001**: C1, C2, C3."},
        ],
    }
    original = deepcopy(conversation)
    monkeypatch.setattr(
        api_server,
        "load_settings",
        lambda: SimpleNamespace(
            app=SimpleNamespace(storage_root="unused", prompts_root=str(PROMPTS))
        ),
    )
    monkeypatch.setattr(api_server, "load_conversation", lambda *args: conversation)
    monkeypatch.setattr(
        api_server,
        "load_application",
        lambda *args: SimpleNamespace(persona="habitation_claims"),
    )
    saved = MagicMock()
    monkeypatch.setattr(api_server, "save_conversation", saved)
    result = asyncio.run(api_server.get_conversation("case", "saved"))
    assert result["messages"][1]["policy_citations"][0]["policy_id"] == "PC-COV-001"
    assert "policy_citations" not in result["messages"][0]
    assert conversation == original
    saved.assert_not_called()


@pytest.mark.parametrize("stream", [False, True])
def test_live_and_streamed_answers_keep_verified_citations_in_response_and_history(
    monkeypatch, stream
):
    from unittest.mock import AsyncMock, MagicMock

    from app.agents import api_integration

    monkeypatch.setattr(
        api_server,
        "load_settings",
        lambda: SimpleNamespace(
            app=SimpleNamespace(storage_root="unused", prompts_root=str(PROMPTS))
        ),
    )
    monkeypatch.setattr(
        api_server,
        "load_application",
        lambda *args: SimpleNamespace(id="case", persona="habitation_claims"),
    )
    monkeypatch.setattr(
        api_integration,
        "agent_chat",
        AsyncMock(
            return_value={
                "response": "See PC-COV-001 and CH-AVB-ELE-001-A.",
                "agent": {"timings_ms": {}},
            }
        ),
    )
    saved = MagicMock()
    monkeypatch.setattr(api_server, "save_conversation", saved)

    async def exercise():
        response = await api_server.create_or_continue_conversation(
            "case", api_server.ChatRequest(message="Policy?", stream=stream)
        )
        if not stream:
            return response
        chunks = [chunk async for chunk in response.body_iterator]
        events = [json.loads(chunk[6:]) for chunk in chunks if chunk.startswith("data: ")]
        return events[-1]["result"]

    result = asyncio.run(exercise())
    assert len(result["policy_citations"]) == 2
    assert result["policy_citations"] == saved.call_args.args[2]["messages"][-1]["policy_citations"]
