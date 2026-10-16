"""Read-only MCP client for the Souscr'IA front-office (Scout back-office API).

The workbench (back-office) receives finalised dossiers from Souscr'IA (front-office)
via ``POST /api/applications``, which stamps the dossier's ``external_reference``
with the originating Souscr'IA ``thread_id``. This module reads the *live* lead
context for such a dossier — security / compliance alerts and fraud-suspicion
signals — straight from Souscr'IA's MCP server so the back-office can enrich its
instruction with what happened during acquisition.

Transport
---------
MCP Streamable HTTP exposed as **stateless JSON-RPC 2.0** over a single
``POST {SOUSCRIA_MCP_URL}{SOUSCRIA_MCP_PATH}`` (default ``/scout/mcp``). The dev
server replies with ``application/json``; SSE (``text/event-stream``) framing is
also parsed defensively. No session handshake is required.

Auth
----
``Authorization: Bearer <jwt>`` where the JWT is HS256-signed with the shared
``SOUSCRIA_JWT_SECRET`` and carries the read-only ``service`` role. Either provide
a pre-minted token via ``SOUSCRIA_SCOUT_TOKEN`` or let this client mint one from
``SOUSCRIA_JWT_SECRET``. **No secret is ever hard-coded here** — everything comes
from the environment.

Safety
------
The 12 tools exposed by Souscr'IA are all read-only — no mutation is possible from
here. Every high-level helper degrades gracefully: when Souscr'IA is unconfigured
or unreachable, callers get an explicit empty/unavailable result and WorkbenchIQ
keeps working.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import itertools
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_MCP_URL = "http://localhost:8090"
DEFAULT_MCP_PATH = "/scout/mcp"
DEFAULT_TIMEOUT_SECONDS = 10.0
SERVICE_ROLE = "service"
SERVICE_SUBJECT = "SVC-SCOUT-001"
TOKEN_TTL_SECONDS = 3600
THREAD_REF_PREFIX = "t-"

# Severity ranking used to surface the worst alert on a dossier.
_SEVERITY_RANK = {"info": 0, "low": 1, "warning": 2, "medium": 2, "high": 3, "critical": 4}
# Cosmos DB bookkeeping keys we strip from alerts before handing them to the UI.
_NOISE_KEYS = {"partition_key", "ttl"}
# crm_timeline also logs MCP/agent tool calls; we keep only genuine business touchpoints.
_NOISE_INTERACTION_TYPES = {"mcp_search"}
_NOISE_INTERACTION_CHANNELS = {"agent"}
# Advisor fields worth showing on a customer card (the raw blob also carries a large
# supervisor/portfolio payload we don't need here).
_ADVISOR_FIELDS = (
    "id",
    "first_name",
    "last_name",
    "agency",
    "experience_years",
    "specialization",
    "global_quality_score",
)


class SouscriaMCPError(RuntimeError):
    """Raised when an MCP tool call cannot be completed (transport/auth/protocol)."""


@dataclass
class SouscriaSettings:
    """Connection settings for the Souscr'IA MCP server, sourced from the env."""

    base_url: str = DEFAULT_MCP_URL
    mcp_path: str = DEFAULT_MCP_PATH
    token: Optional[str] = None  # pre-minted Bearer (SOUSCRIA_SCOUT_TOKEN)
    jwt_secret: Optional[str] = None  # shared secret to mint a service token
    timeout: float = DEFAULT_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls) -> "SouscriaSettings":
        return cls(
            base_url=(os.getenv("SOUSCRIA_MCP_URL") or DEFAULT_MCP_URL).rstrip("/"),
            mcp_path=os.getenv("SOUSCRIA_MCP_PATH") or DEFAULT_MCP_PATH,
            token=os.getenv("SOUSCRIA_SCOUT_TOKEN") or None,
            jwt_secret=os.getenv("SOUSCRIA_JWT_SECRET") or None,
            timeout=float(os.getenv("SOUSCRIA_MCP_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)),
        )

    @property
    def configured(self) -> bool:
        """True when we have a base URL and a way to authenticate (token or secret)."""
        return bool(self.base_url) and bool(self.token or self.jwt_secret)

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}{self.mcp_path}"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def mint_service_jwt(
    secret: str, *, ttl: int = TOKEN_TTL_SECONDS, now: Optional[int] = None
) -> str:
    """Mint an HS256 service JWT (stdlib only) accepted by the Souscr'IA gateway."""
    issued = int(now if now is not None else time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": SERVICE_SUBJECT, "role": SERVICE_ROLE, "iat": issued, "exp": issued + ttl}
    signing_input = (
        _b64url(json.dumps(header, separators=(",", ":")).encode())
        + "."
        + _b64url(json.dumps(payload, separators=(",", ":")).encode())
    )
    signature = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return signing_input + "." + _b64url(signature)


def looks_like_thread_ref(external_reference: Optional[str]) -> bool:
    """Heuristic: a Souscr'IA ``thread_id`` is prefixed ``t-`` (e.g. ``t-saf-...``)."""
    return bool(external_reference) and external_reference.startswith(THREAD_REF_PREFIX)


def _parse_jsonrpc(resp: requests.Response) -> Dict[str, Any]:
    content_type = (resp.headers.get("content-type") or "").lower()
    if "text/event-stream" in content_type:
        return _parse_sse(resp.text)
    return resp.json()


def _parse_sse(text: str) -> Dict[str, Any]:
    """Extract the last JSON-RPC message from an SSE stream.

    The dev server replies with plain JSON, but a spec-compliant Streamable HTTP
    server may stream the response as ``event: message`` / ``data: {...}`` frames.
    """
    last: Dict[str, Any] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        chunk = line[len("data:") :].strip()
        if not chunk or chunk == "[DONE]":
            continue
        try:
            parsed = json.loads(chunk)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and ("result" in parsed or "error" in parsed):
            last = parsed
    if not last:
        raise SouscriaMCPError("Could not parse SSE response from Souscr'IA MCP.")
    return last


def _tool_text(result: Dict[str, Any]) -> str:
    for item in result.get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            return item.get("text") or ""
    return ""


def _tool_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    """Unwrap the tool's structured payload (the ``{"ok":.., "data":..}`` object)."""
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    text = _tool_text(result)
    if text:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {"ok": True, "data": {"text": text}}
    return {}


def _clean_alert(alert: Dict[str, Any]) -> Dict[str, Any]:
    """Drop Cosmos DB bookkeeping (``_rid``/``_etag``/``ttl``/...) for a tidy UI block."""
    if not isinstance(alert, dict):
        return alert
    return {k: v for k, v in alert.items() if not k.startswith("_") and k not in _NOISE_KEYS}


def _max_severity(alerts: List[Dict[str, Any]]) -> Optional[str]:
    best: Optional[str] = None
    best_rank = -1
    for alert in alerts:
        sev = (alert.get("severity") or "").lower() if isinstance(alert, dict) else ""
        rank = _SEVERITY_RANK.get(sev, -1)
        if rank > best_rank:
            best_rank, best = rank, sev or None
    return best


def _is_business_interaction(interaction: Any) -> bool:
    """True for genuine human/business touchpoints.

    ``crm_timeline`` also records MCP/agent tool-call activity (``type=mcp_search``,
    ``channel=agent``); we filter that noise out so the customer journey stays
    meaningful.
    """
    if not isinstance(interaction, dict):
        return False
    return (
        interaction.get("type") not in _NOISE_INTERACTION_TYPES
        and interaction.get("channel") not in _NOISE_INTERACTION_CHANNELS
    )


def _slim_advisor(advisor: Any) -> Optional[Dict[str, Any]]:
    """Keep only the advisor fields useful on a customer card."""
    if not isinstance(advisor, dict):
        return None
    slim = {k: advisor[k] for k in _ADVISOR_FIELDS if k in advisor}
    return slim or None


class SouscriaMCPClient:
    """Minimal stateless JSON-RPC client for the Souscr'IA MCP server (read-only)."""

    def __init__(
        self,
        settings: Optional[SouscriaSettings] = None,
        *,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.settings = settings or SouscriaSettings.from_env()
        self._session = session or requests.Session()
        self._ids = itertools.count(1)
        self._lock = threading.Lock()
        self._cached_token: Optional[str] = None
        self._cached_token_exp: float = 0.0

    @property
    def configured(self) -> bool:
        return self.settings.configured

    def _bearer(self) -> str:
        if self.settings.token:
            return self.settings.token
        if not self.settings.jwt_secret:
            raise SouscriaMCPError("Souscr'IA MCP is not configured (no token or secret).")
        now = time.time()
        with self._lock:
            if not self._cached_token or now >= self._cached_token_exp:
                self._cached_token = mint_service_jwt(self.settings.jwt_secret, now=int(now))
                # Refresh a minute before expiry to avoid edge-of-window rejections.
                self._cached_token_exp = now + TOKEN_TTL_SECONDS - 60
            return self._cached_token

    def call_tool(self, name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Call an MCP tool and return its unwrapped ``data`` payload.

        Raises ``SouscriaMCPError`` on any transport, auth or protocol failure so
        callers can decide how to degrade. High-level helpers below wrap this.
        """
        if not self.configured:
            raise SouscriaMCPError("Souscr'IA MCP is not configured.")
        body = {
            "jsonrpc": "2.0",
            "id": next(self._ids),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments or {}},
        }
        headers = {
            "Authorization": f"Bearer {self._bearer()}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        try:
            resp = self._session.post(
                self.settings.endpoint, headers=headers, json=body, timeout=self.settings.timeout
            )
        except requests.RequestException as exc:
            raise SouscriaMCPError(f"Souscr'IA MCP request failed: {exc}") from exc

        if resp.status_code == 401:
            raise SouscriaMCPError(
                "Souscr'IA MCP rejected the credentials (401). "
                "A read-only role=service token/secret is required."
            )
        if resp.status_code >= 400:
            raise SouscriaMCPError(
                f"Souscr'IA MCP returned HTTP {resp.status_code}: {resp.text[:200]}"
            )

        try:
            envelope = _parse_jsonrpc(resp)
        except (ValueError, SouscriaMCPError) as exc:
            raise SouscriaMCPError(f"Souscr'IA MCP returned an unreadable response: {exc}") from exc

        if "error" in envelope:
            raise SouscriaMCPError(f"Souscr'IA MCP error: {envelope['error']}")
        result = envelope.get("result") or {}
        if result.get("isError"):
            raise SouscriaMCPError(
                f"Souscr'IA tool '{name}' reported an error: {_tool_text(result)[:200]}"
            )
        payload = _tool_payload(result)
        if payload.get("ok") is False:
            raise SouscriaMCPError(f"Souscr'IA tool '{name}' returned ok=false: {payload}")
        data = payload.get("data")
        return data if isinstance(data, dict) else {"value": data if payload else None}

    # ------------------------------------------------------------------
    # High-level, graceful helpers (never raise — return explicit fallbacks)
    # ------------------------------------------------------------------

    def get_risk_context(self, thread_id: str, *, alert_limit: int = 20) -> Dict[str, Any]:
        """Live security/compliance alerts + fraud-suspicion signals for a thread.

        Combines ``crm_alerts`` and ``crm_fraud_signals``. Read-only and graceful:
        returns ``available: False`` with an ``errors`` list instead of raising.
        """
        alerts: List[Dict[str, Any]] = []
        fraud: Dict[str, Any] = {}
        errors: List[str] = []

        try:
            alerts_data = self.call_tool(
                "crm_alerts", {"thread_id": thread_id, "limit": alert_limit}
            )
            raw_alerts = alerts_data.get("alerts", []) if isinstance(alerts_data, dict) else []
            alerts = [_clean_alert(a) for a in raw_alerts]
        except SouscriaMCPError as exc:
            errors.append(str(exc))

        try:
            fraud = self.call_tool("crm_fraud_signals", {"thread_id": thread_id})
        except SouscriaMCPError as exc:
            errors.append(str(exc))

        return {
            "thread_id": thread_id,
            "available": not errors,
            "alerts": alerts,
            "alert_count": len(alerts),
            "max_severity": _max_severity(alerts),
            "fraud": fraud,
            "fraud_score": fraud.get("score") if isinstance(fraud, dict) else None,
            "fraud_disclaimer": fraud.get("disclaimer") if isinstance(fraud, dict) else None,
            "errors": errors,
            "source": "souscria-mcp",
        }

    def get_acquisition_context(
        self, client_id: str, *, interaction_limit: int = 12
    ) -> Dict[str, Any]:
        """Live front-office acquisition context for a Souscr'IA ``client_id``.

        Combines ``crm_contracts`` (active contracts + the assigned advisor),
        ``crm_timeline`` (business interactions, with agent/MCP tool-call noise
        filtered out) and ``crm_next_best_actions``. Read-only and graceful:
        returns ``available: False`` with an ``errors`` list instead of raising.

        ``crm_search`` is intentionally **not** used: for a ``service`` token the
        Souscr'IA gateway treats it as a self-lookup and returns nothing, so the
        client's presence is derived from contracts/interactions instead.
        """
        contracts: List[Dict[str, Any]] = []
        advisor: Optional[Dict[str, Any]] = None
        interactions: List[Dict[str, Any]] = []
        actions: List[Dict[str, Any]] = []
        errors: List[str] = []

        try:
            data = self.call_tool("crm_contracts", {"client_id": client_id})
            if isinstance(data, dict):
                contracts = [c for c in (data.get("contracts") or []) if isinstance(c, dict)]
                advisor = _slim_advisor(data.get("advisor"))
        except SouscriaMCPError as exc:
            errors.append(str(exc))

        try:
            data = self.call_tool("crm_timeline", {"client_id": client_id})
            raw = data.get("interactions") or [] if isinstance(data, dict) else []
            interactions = [i for i in raw if _is_business_interaction(i)][:interaction_limit]
        except SouscriaMCPError as exc:
            errors.append(str(exc))

        try:
            data = self.call_tool("crm_next_best_actions", {"client_id": client_id})
            actions = (
                [a for a in (data.get("actions") or []) if isinstance(a, dict)]
                if isinstance(data, dict)
                else []
            )
        except SouscriaMCPError as exc:
            errors.append(str(exc))

        return {
            "available": bool(contracts or interactions),
            "client_id": client_id,
            "contracts": contracts,
            "advisor": advisor,
            "interactions": interactions,
            "next_best_actions": actions,
            "errors": errors,
            "source": "souscria-mcp",
        }


# ----------------------------------------------------------------------
# Module-level convenience used by the API layer
# ----------------------------------------------------------------------

_default_client: Optional[SouscriaMCPClient] = None
_default_client_lock = threading.Lock()


def get_default_client() -> SouscriaMCPClient:
    """Process-wide client reading its configuration from the environment."""
    global _default_client
    with _default_client_lock:
        if _default_client is None:
            _default_client = SouscriaMCPClient()
        return _default_client


def fetch_risk_context(external_reference: Optional[str]) -> Optional[Dict[str, Any]]:
    """Best-effort live Souscr'IA risk context for a dossier's ``external_reference``.

    Returns ``None`` when the reference is not a Souscr'IA thread id or the
    connector is not configured (feature off → no behaviour change for callers).
    Otherwise returns a context dict that may carry ``available: False`` when
    Souscr'IA is unreachable. Never raises.
    """
    if not looks_like_thread_ref(external_reference):
        return None
    client = get_default_client()
    if not client.configured:
        return None
    try:
        return client.get_risk_context(external_reference)  # type: ignore[arg-type]
    except Exception as exc:  # pragma: no cover - helper already guards; belt and braces
        logger.warning("Souscr'IA risk context fetch failed for %s: %s", external_reference, exc)
        return {
            "thread_id": external_reference,
            "available": False,
            "alerts": [],
            "alert_count": 0,
            "max_severity": None,
            "fraud": {},
            "errors": [str(exc)],
            "source": "souscria-mcp",
        }


def fetch_acquisition_context(souscria_ref: Optional[str]) -> Optional[Dict[str, Any]]:
    """Best-effort live Souscr'IA acquisition context for a customer's ``souscria_ref``.

    ``souscria_ref`` is the Souscr'IA ``client_id`` (e.g. ``SOC-001``) attached to a
    workbench customer as internal seed data. Returns ``None`` when no ref is set or
    the connector is not configured (feature off → no behaviour change). Never raises.
    """
    if not souscria_ref:
        return None
    client = get_default_client()
    if not client.configured:
        return None
    try:
        return client.get_acquisition_context(souscria_ref)
    except Exception as exc:  # pragma: no cover - helper already guards; belt and braces
        logger.warning("Souscr'IA acquisition context fetch failed for %s: %s", souscria_ref, exc)
        return {
            "available": False,
            "client_id": souscria_ref,
            "contracts": [],
            "advisor": None,
            "interactions": [],
            "next_best_actions": [],
            "errors": [str(exc)],
            "source": "souscria-mcp",
        }
