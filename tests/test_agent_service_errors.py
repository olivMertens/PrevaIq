from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agents.errors import (
    AgentServiceError, agent_response_text, agent_tools_called, translate_agent_error,
)


def test_tool_badges_require_a_completed_sdk_call():
    from agent_framework import AgentResponse, Content, Message

    response = AgentResponse(messages=[
        Message(role="assistant", contents=[
            Content.from_function_call("call1", "search_policies"),
            Content.from_function_call("call2", "web_search"),
        ]),
        Message(role="tool", contents=[Content.from_function_result("call1", result="policy")]),
        Message(role="assistant", contents=[Content.from_text("No resource was found.")]),
    ])
    assert agent_tools_called(response) == ["search_policies"]
    assert agent_tools_called(SimpleNamespace(text="Web search, source, resource")) == []


class ProviderFailure(Exception):
    status_code = 404
    body = {"error": {"code": "DeploymentNotFound", "message": "private endpoint details"}}


def test_wrapped_deployment_error_is_safe_and_not_retryable():
    error = RuntimeError("service failed", ProviderFailure("private endpoint details"))
    translated = translate_agent_error(error)
    assert translated.code == "AI_DEPLOYMENT_NOT_FOUND"
    assert translated.status_code == 502
    assert translated.retryable is False
    assert "private" not in str(translated.public_detail())
    assert translated.public_detail()["request_id"]


@pytest.mark.parametrize("status, expected", [(401, 502), (403, 502), (429, 503), (500, 503)])
def test_provider_status_is_not_confused_with_domain_status(status, expected):
    error = RuntimeError("private provider failure")
    error.status_code = status
    translated = translate_agent_error(error)
    assert translated.status_code == expected
    assert translated.retryable == (status in (429, 500))


def test_timeout_and_already_translated_error():
    translated = translate_agent_error(TimeoutError("private"))
    assert translated.status_code == 504
    assert translated.retryable
    assert translate_agent_error(translated) is translated


def test_response_uses_text_not_object_representation():
    assert agent_response_text(SimpleNamespace(text="Result")) == "Result"
    assert agent_response_text("Legacy text") == "Legacy text"


@pytest.mark.parametrize("response", [None, SimpleNamespace(text=""), SimpleNamespace(value={})])
def test_invalid_response_never_becomes_python_text(response):
    with pytest.raises(AgentServiceError, match="no usable text"):
        agent_response_text(response)