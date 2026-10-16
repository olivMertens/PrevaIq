from app.config import OpenAISettings
from app import openai_client


def test_reasoning_model_uses_reasoning_request_shape(monkeypatch):
    captured = {}

    def fake_call_openai_endpoint(url, headers, params, body, endpoint_name="primary", timeout=120):
        captured.update(body)
        return {"content": "ok", "usage": {}}

    monkeypatch.setattr(openai_client, "_call_openai_endpoint", fake_call_openai_endpoint)

    settings = OpenAISettings(
        endpoint="https://example.openai.azure.com",
        api_key="test-key",
        deployment_name="gpt-5.4-mini",
        model_name="gpt-5.4-mini",
        reasoning_effort="low",
    )

    result = openai_client.chat_completion(
        settings,
        [
            {"role": "system", "content": "You are a claims analyst."},
            {"role": "user", "content": "Assess the dossier."},
        ],
        temperature=0.8,
        max_tokens=8000,
    )

    assert result["content"] == "ok"
    assert captured["model"] == "gpt-5.4-mini"
    # Budget above the reasoning floor is preserved verbatim.
    assert captured["max_completion_tokens"] == 8000
    assert captured["reasoning_effort"] == "low"
    assert captured["messages"][0]["role"] == "developer"
    assert "temperature" not in captured
    assert "max_tokens" not in captured


def test_reasoning_model_floors_small_completion_budget(monkeypatch):
    """Reasoning models must get a minimum completion budget so hidden reasoning
    tokens never starve the visible answer (empty response -> JSON parse failure)."""
    captured = {}

    def fake_call_openai_endpoint(url, headers, params, body, endpoint_name="primary", timeout=120):
        captured.update(body)
        return {"content": "ok", "usage": {}}

    monkeypatch.setattr(openai_client, "_call_openai_endpoint", fake_call_openai_endpoint)

    settings = OpenAISettings(
        endpoint="https://example.openai.azure.com",
        api_key="test-key",
        deployment_name="gpt-5.4-mini",
        model_name="gpt-5.4-mini",
        reasoning_effort="low",
    )

    # Default max_tokens (1200) is well below the floor and previously yielded empty output.
    openai_client.chat_completion(
        settings,
        [{"role": "user", "content": "Extract damage areas as JSON."}],
        response_format="json_object",
    )

    assert captured["max_completion_tokens"] == openai_client._REASONING_MIN_COMPLETION_TOKENS
    assert captured["max_completion_tokens"] >= 4000


def test_non_reasoning_model_not_floored(monkeypatch):
    """Chat (non-reasoning) models keep their explicit max_tokens unchanged."""
    captured = {}

    def fake_call_openai_endpoint(url, headers, params, body, endpoint_name="primary", timeout=120):
        captured.update(body)
        return {"content": "ok", "usage": {}}

    monkeypatch.setattr(openai_client, "_call_openai_endpoint", fake_call_openai_endpoint)

    settings = OpenAISettings(
        endpoint="https://example.openai.azure.com",
        api_key="test-key",
        deployment_name="custom-chat",
        model_name="custom-chat",
    )

    openai_client.chat_completion(
        settings,
        [{"role": "user", "content": "Summarize."}],
        max_tokens=512,
    )

    assert captured["max_tokens"] == 512
    assert "max_completion_tokens" not in captured
