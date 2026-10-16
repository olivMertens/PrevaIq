"""Tests for the read-only Souscr'IA MCP client.

These mock the HTTP/MCP transport (no live Souscr'IA server) and prove:
- ``tools/call`` responses are mapped correctly (structuredContent, content text, SSE)
- ``get_risk_context`` combines alerts + fraud signals
- graceful degradation on connection errors, HTTP 401 and "not configured"
- the stdlib HS256 service-token minting is valid
- the ``external_reference`` → thread-id heuristic and ``fetch_risk_context`` wiring
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json

import pytest
import requests

from app import souscria_mcp_client as smc
from app.souscria_mcp_client import (
    SouscriaMCPClient,
    SouscriaMCPError,
    SouscriaSettings,
    fetch_acquisition_context,
    fetch_risk_context,
    looks_like_thread_ref,
    mint_service_jwt,
)


# ---------------------------------------------------------------------------
# Test transport doubles
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, payload=None, *, status_code=200, headers=None, text=None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {"content-type": "application/json"}
        self._text = text

    def json(self):
        if self._payload is None:
            raise ValueError("response has no JSON body")
        return self._payload

    @property
    def text(self):
        if self._text is not None:
            return self._text
        return json.dumps(self._payload)


class _FakeSession:
    """Records requests and returns whatever ``responder(body)`` produces."""

    def __init__(self, responder):
        self._responder = responder
        self.calls = []

    def post(self, url, headers=None, json=None, timeout=None):  # noqa: A002 - mirror requests API
        self.calls.append({"url": url, "headers": headers, "body": json, "timeout": timeout})
        return self._responder(json)


def _envelope(request_body, data, *, structured=True, include_text=True):
    """Build a JSON-RPC tools/call envelope mirroring the live Souscr'IA server."""
    result = {"isError": False, "content": []}
    if include_text:
        result["content"] = [{"type": "text", "text": json.dumps({"ok": True, "data": data})}]
    if structured:
        result["structuredContent"] = {"ok": True, "data": data}
    return _FakeResponse({"jsonrpc": "2.0", "id": request_body.get("id"), "result": result})


def _client(responder, **settings_overrides):
    settings = SouscriaSettings(
        base_url="https://souscria.example",
        token="test-token",
        **settings_overrides,
    )
    return SouscriaMCPClient(settings, session=_FakeSession(responder))


# ---------------------------------------------------------------------------
# call_tool response mapping
# ---------------------------------------------------------------------------


def test_call_tool_maps_structured_content():
    data = {"alerts": [{"severity": "critical"}], "count": 1}
    client = _client(lambda body: _envelope(body, data))

    result = client.call_tool("crm_alerts", {"thread_id": "t-abc", "limit": 5})

    assert result == data
    # Request was well-formed: JSON-RPC tools/call with bearer + dual Accept.
    sent = client._session.calls[0]
    assert sent["url"] == "https://souscria.example/scout/mcp"
    assert sent["body"]["method"] == "tools/call"
    assert sent["body"]["params"] == {
        "name": "crm_alerts",
        "arguments": {"thread_id": "t-abc", "limit": 5},
    }
    assert sent["headers"]["Authorization"] == "Bearer test-token"
    assert sent["headers"]["Accept"] == "application/json, text/event-stream"


def test_call_tool_falls_back_to_content_text_without_structured():
    data = {"score": 0, "signals": []}
    client = _client(lambda body: _envelope(body, data, structured=False))

    assert client.call_tool("crm_fraud_signals", {"thread_id": "t-abc"}) == data


def test_call_tool_parses_sse_framing():
    data = {"alerts": [], "count": 0}

    def responder(body):
        frame = (
            "event: message\n"
            + "data: "
            + json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": body.get("id"),
                    "result": {"structuredContent": {"ok": True, "data": data}, "isError": False},
                }
            )
            + "\n\n"
        )
        return _FakeResponse(text=frame, headers={"content-type": "text/event-stream"})

    client = _client(responder)
    assert client.call_tool("crm_alerts", {"limit": 1}) == data


def test_call_tool_raises_on_http_401():
    client = _client(lambda body: _FakeResponse({"error": "invalid_token"}, status_code=401))

    with pytest.raises(SouscriaMCPError, match="401"):
        client.call_tool("crm_alerts", {"limit": 1})


def test_call_tool_raises_on_jsonrpc_error():
    def responder(body):
        return _FakeResponse(
            {"jsonrpc": "2.0", "id": body.get("id"), "error": {"code": -32000, "message": "boom"}}
        )

    client = _client(responder)
    with pytest.raises(SouscriaMCPError, match="boom"):
        client.call_tool("crm_alerts", {"limit": 1})


def test_call_tool_raises_when_not_configured():
    client = SouscriaMCPClient(SouscriaSettings(base_url="https://x", token=None, jwt_secret=None))
    assert client.configured is False
    with pytest.raises(SouscriaMCPError, match="not configured"):
        client.call_tool("crm_alerts", {})


# ---------------------------------------------------------------------------
# High-level helpers
# ---------------------------------------------------------------------------


def test_get_risk_context_combines_alerts_and_fraud():
    alert = {
        "severity": "warning",
        "category": "offscope",
        "thread_id": "t-abc",
        "_rid": "noise",
        "ttl": 7776000,
        "partition_key": "t-abc",
    }
    critical = {"severity": "critical", "category": "injection", "thread_id": "t-abc"}
    fraud = {"thread_id": "t-abc", "score": 0, "signals": [], "disclaimer": "Suspicion uniquement."}

    def responder(body):
        name = body["params"]["name"]
        if name == "crm_alerts":
            return _envelope(body, {"alerts": [alert, critical], "count": 2})
        if name == "crm_fraud_signals":
            return _envelope(body, fraud)
        raise AssertionError(f"unexpected tool {name}")

    ctx = _client(responder).get_risk_context("t-abc")

    assert ctx["available"] is True
    assert ctx["alert_count"] == 2
    assert ctx["max_severity"] == "critical"
    assert ctx["fraud_score"] == 0
    assert ctx["fraud_disclaimer"] == "Suspicion uniquement."
    # Cosmos bookkeeping is stripped from alerts handed to the UI.
    cleaned = ctx["alerts"][0]
    assert "_rid" not in cleaned and "ttl" not in cleaned and "partition_key" not in cleaned
    assert cleaned["category"] == "offscope"


def test_get_risk_context_degrades_on_connection_error():
    def responder(body):
        raise requests.ConnectionError("souscria down")

    ctx = _client(responder).get_risk_context("t-abc")

    assert ctx["available"] is False
    assert ctx["alerts"] == []
    assert ctx["errors"]  # both tool calls recorded an error
    assert ctx["source"] == "souscria-mcp"


def test_get_acquisition_context_combines_contracts_timeline_nba():
    """Acquisition context derives presence from contracts/timeline (never crm_search),
    slims the advisor blob and filters out agent/MCP tool-call noise from the timeline."""
    called_tools = []

    def responder(body):
        name = body["params"]["name"]
        called_tools.append(name)
        if name == "crm_contracts":
            return _envelope(
                body,
                {
                    "contracts": [{"id": "AUTO-1", "product": "auto", "annual_premium": 744}],
                    "advisor": {
                        "id": "CONS-001",
                        "first_name": "Catherine",
                        "last_name": "Moreau",
                        "agency": "Lyon Centre",
                        "global_quality_score": 91,
                        "portfolio": {"huge": "blob"},  # must be slimmed away
                        "controls_12m": {"drop": "me"},
                    },
                },
            )
        if name == "crm_timeline":
            return _envelope(
                body,
                {
                    "interactions": [
                        {"type": "souscription", "channel": "agence", "summary": "MRH"},
                        {"type": "mcp_search", "channel": "agent", "summary": "noise"},
                    ]
                },
            )
        if name == "crm_next_best_actions":
            return _envelope(body, {"actions": [{"id": "NBA-1", "label": "Renouveler MRH"}]})
        raise AssertionError(f"unexpected tool {name}")

    acq = _client(responder).get_acquisition_context("SOC-001")

    assert acq["available"] is True
    assert acq["client_id"] == "SOC-001"
    assert acq["contracts"] == [{"id": "AUTO-1", "product": "auto", "annual_premium": 744}]
    # advisor slimmed to the display fields only (no portfolio/controls blob)
    assert acq["advisor"] == {
        "id": "CONS-001",
        "first_name": "Catherine",
        "last_name": "Moreau",
        "agency": "Lyon Centre",
        "global_quality_score": 91,
    }
    # agent/mcp_search noise filtered out — only the genuine business interaction remains
    assert acq["interactions"] == [
        {"type": "souscription", "channel": "agence", "summary": "MRH"}
    ]
    assert acq["next_best_actions"] == [{"id": "NBA-1", "label": "Renouveler MRH"}]
    assert acq["errors"] == []
    # crm_search must never be used for a service token (it self-looks-up to null)
    assert "crm_search" not in called_tools


# ---------------------------------------------------------------------------
# Token minting, heuristic and module-level wiring
# ---------------------------------------------------------------------------


def test_mint_service_jwt_is_valid_hs256():
    secret = "unit-test-secret"
    token = mint_service_jwt(secret, ttl=3600, now=1_000_000)
    header_b64, payload_b64, sig_b64 = token.split(".")

    expected_sig = hmac.new(
        secret.encode(), f"{header_b64}.{payload_b64}".encode(), hashlib.sha256
    ).digest()
    assert base64.urlsafe_b64encode(expected_sig).rstrip(b"=").decode() == sig_b64

    padded = payload_b64 + "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(padded))
    assert payload["role"] == "service"
    assert payload["sub"] == "SVC-SCOUT-001"
    assert payload["exp"] == 1_003_600


def test_looks_like_thread_ref():
    assert looks_like_thread_ref("t-saf-injection-50d50c") is True
    assert looks_like_thread_ref("CLI-001") is False
    assert looks_like_thread_ref(None) is False
    assert looks_like_thread_ref("") is False


def test_fetch_risk_context_returns_none_for_non_thread_ref():
    # Non-thread references and missing references short-circuit before any network.
    assert fetch_risk_context("CLI-001") is None
    assert fetch_risk_context(None) is None


def test_fetch_risk_context_returns_none_when_not_configured(monkeypatch):
    unconfigured = SouscriaMCPClient(
        SouscriaSettings(base_url="https://x", token=None, jwt_secret=None)
    )
    monkeypatch.setattr(smc, "get_default_client", lambda: unconfigured)
    assert fetch_risk_context("t-abc") is None


def test_fetch_risk_context_uses_client_when_configured(monkeypatch):
    def responder(body):
        name = body["params"]["name"]
        data = {"alerts": [], "count": 0} if name == "crm_alerts" else {"score": 0, "signals": []}
        return _envelope(body, data)

    configured = _client(responder)
    monkeypatch.setattr(smc, "get_default_client", lambda: configured)

    ctx = fetch_risk_context("t-abc")
    assert ctx is not None
    assert ctx["thread_id"] == "t-abc"
    assert ctx["available"] is True


def test_fetch_acquisition_context_returns_none_without_ref_or_config(monkeypatch):
    # No souscria_ref → short-circuits before any network.
    assert fetch_acquisition_context(None) is None
    assert fetch_acquisition_context("") is None

    unconfigured = SouscriaMCPClient(
        SouscriaSettings(base_url="https://x", token=None, jwt_secret=None)
    )
    monkeypatch.setattr(smc, "get_default_client", lambda: unconfigured)
    assert fetch_acquisition_context("SOC-001") is None


def test_fetch_acquisition_context_uses_client_when_configured(monkeypatch):
    def responder(body):
        name = body["params"]["name"]
        if name == "crm_contracts":
            return _envelope(body, {"contracts": [{"id": "AUTO-1"}], "advisor": None})
        if name == "crm_timeline":
            return _envelope(body, {"interactions": []})
        return _envelope(body, {"actions": []})

    configured = _client(responder)
    monkeypatch.setattr(smc, "get_default_client", lambda: configured)

    acq = fetch_acquisition_context("SOC-001")
    assert acq is not None
    assert acq["available"] is True
    assert acq["client_id"] == "SOC-001"


def test_settings_from_env_configured_flag(monkeypatch):
    monkeypatch.delenv("SOUSCRIA_SCOUT_TOKEN", raising=False)
    monkeypatch.delenv("SOUSCRIA_JWT_SECRET", raising=False)
    monkeypatch.delenv("SOUSCRIA_MCP_URL", raising=False)
    assert SouscriaSettings.from_env().configured is False

    monkeypatch.setenv("SOUSCRIA_JWT_SECRET", "shared")
    settings = SouscriaSettings.from_env()
    assert settings.configured is True
    assert settings.endpoint == "http://localhost:8090/scout/mcp"
