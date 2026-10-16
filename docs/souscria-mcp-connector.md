# Souscr'IA MCP connector

PrevaIQ, the back-office documentary workbench, and **Souscr'IA**, the separate front-office acquisition app, cover two halves of the same insurance lifecycle.

- **Souscr'IA**: a prospect chats with a conversational agent; a live lead case is built with simulated CRM, OCR, and DDA scoring. Each conversation has a `thread_id`.
- **PrevaIQ**: receives a finalized case and processes it with Content Understanding, analysis, and decision support.

Two bridges connect them:

| # | Direction | Owner | What it does |
|---|-----------|-------|--------------|
| 2 | Souscr'IA -> PrevaIQ | Souscr'IA | `POST /api/applications` multipart upload with `external_reference = <thread_id>` pushes a finalized case into PrevaIQ. |
| 1 | PrevaIQ -> Souscr'IA | This connector | Reads live lead context from the Souscr'IA MCP server, keyed by the same `external_reference`: security and compliance alerts, fraud-suspicion signals, and client card. |

Because bridge 2 stamps every PrevaIQ `application` with the Souscr'IA `thread_id`, PrevaIQ already has the correlation key needed to pull live context.

## Transport and auth

- **Endpoint**: `POST {SOUSCRIA_MCP_URL}{SOUSCRIA_MCP_PATH}`, default path `/scout/mcp`.
- **Protocol**: MCP Streamable HTTP exposed as stateless JSON-RPC 2.0. Each tool call uses one POST, with no `initialize` handshake and no session id. Responses return as `application/json`; SSE `text/event-stream` framing is also parsed defensively.
- **Auth**: `Authorization: Bearer <token>`. The JWT is HS256-signed with the shared `SOUSCRIA_JWT_SECRET` and must carry the read-only `service` role with claims `{"sub": "SVC-SCOUT-001", "role": "service", "exp": <future>}`. `client` and `visitor` roles receive `401`.
- **Read-only**: only the 12 read tools are reachable; no mutation tool exists. Fraud signals are suspicion only and require human validation.

## Configuration

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SOUSCRIA_MCP_URL` | No | `http://localhost:8090` | Base URL of the Souscr'IA MCP server, without trailing `/scout/mcp`. |
| `SOUSCRIA_MCP_PATH` | No | `/scout/mcp` | Streamable HTTP transport path. |
| `SOUSCRIA_SCOUT_TOKEN` | Conditional | - | Pre-minted bearer token with the `service` role. Preferred in production. |
| `SOUSCRIA_JWT_SECRET` | Conditional | - | Shared HS256 secret to mint a `service` token locally for development. |
| `SOUSCRIA_MCP_TIMEOUT_SECONDS` | No | `10` | Per-request timeout. |

The connector is off unless a base URL and a credential (`SOUSCRIA_SCOUT_TOKEN` or `SOUSCRIA_JWT_SECRET`) are present. When off, PrevaIQ behaves as before and no `souscria_context` block is attached. Do not commit secrets; the development secret is only for local smoke tests.

## Integration point

`GET /api/applications/{app_id}` enriches the response with `souscria_context` only when `external_reference` looks like a Souscr'IA thread id with prefix `t-` and the connector is configured. The call runs off the event loop with `asyncio.to_thread`, uses a short timeout, and is guarded so Souscr'IA downtime never breaks the case view.

```jsonc
// GET /api/applications/<id>, excerpt.
{
  "id": "...",
  "external_reference": "t-saf-injection-50d50c",
  "souscria_context": {
    "thread_id": "t-saf-injection-50d50c",
    "available": true,
    "alert_count": 1,
    "max_severity": "critical",
    "alerts": [{ "severity": "critical", "category": "injection", "excerpt": "..." }],
    "fraud": { "score": 0, "signals": [], "disclaimer": "Suspicion only..." },
    "source": "souscria-mcp"
  }
}
```

Programmatic use:

```python
from app.souscria_mcp_client import SouscriaMCPClient

client = SouscriaMCPClient()                 # reads config from the environment
risk = client.get_risk_context("t-abc123")   # crm_alerts + crm_fraud_signals
card = client.get_client_card(nom="Mertens") # crm_search + crm_contracts + crm_timeline
```

## Smoke test

```powershell
$env:SOUSCRIA_MCP_URL = "https://<souscria-mcp-host>"
$env:SOUSCRIA_JWT_SECRET = "souscria-demo-dev-secret-rotate-me-in-prod"   # development placeholder only

python -c "from app.souscria_mcp_client import SouscriaMCPClient; import json; print(json.dumps(SouscriaMCPClient().get_risk_context('t-saf-injection-50d50c'), indent=2, ensure_ascii=False))"
```

End to end: open a case whose `external_reference` is a Souscr'IA `t-...` thread id and confirm that `souscria_context` appears in the `GET /api/applications/{id}` payload.


