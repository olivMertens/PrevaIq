# Configuration

## UI and AI response locales

The login switcher and account menu offer EN, FR, DE and **DE-CH — Deutsch (Schweiz)**.
After a frontend rollout, reload an already-open browser tab to load the new menu.
The `locale` cookie selects the UI locale and generated-content language; no Azure
setting or separate tenant configuration is needed.

`de-CH` is preserved in AI requests and revision-bound translation caches. Prompts
request Swiss Standard German (Schweizer Hochdeutsch), without dialect, and Swiss
orthography (`ss`, not `ß`). DE remains generic German. Original documents, quoted
evidence, names, identifiers, amounts, currencies and legal references are preserved.
The language selection never changes the jurisdiction or converts EUR into CHF.
Source matching and Web IQ search parameters still use the base language, while
AI summaries and translations use the requested output variant.

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `BRAND_NAME` | No | `PrevaIQ` | Brand identity, currently only `PrevaIQ`. Baked into Docker images at build time through `ARG BRAND_NAME`; do not set it as a Container App environment variable. |
| `API_KEY` | No | - | API key for backend authentication with the `X-API-Key` header. Must be 32+ characters. Set it on both backend and frontend. |
| `AZURE_CONTENT_UNDERSTANDING_ENDPOINT` | Yes | - | Azure AI Content Understanding endpoint |
| `AZURE_CONTENT_UNDERSTANDING_API_KEY` | Conditional | - | API key if not using Azure AD |
| `AZURE_CONTENT_UNDERSTANDING_USE_AZURE_AD` | No | `true` | Use Azure AD authentication |
| `AZURE_CONTENT_UNDERSTANDING_API_VERSION` | No | `2025-11-01` | Azure AI Content Understanding GA API version |
| `AZURE_CONTENT_UNDERSTANDING_COMPLETION_DEPLOYMENT` | No | `gpt-5.4-mini` | Completion model alias for Content Understanding GA custom analyzers |
| `AZURE_CONTENT_UNDERSTANDING_EMBEDDING_DEPLOYMENT` | No | `text-embedding-3-large` | Embedding model alias for Content Understanding GA custom analyzers |
| `AZURE_OPENAI_ENDPOINT` | Yes | - | Azure OpenAI endpoint |
| `AZURE_OPENAI_API_KEY` | Yes | - | Azure OpenAI API key |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | Yes | `gpt-5.4-mini` | Primary analysis deployment name |
| `AZURE_OPENAI_API_VERSION` | No | `2025-04-01-preview` | Azure OpenAI API version |
| `AZURE_OPENAI_REASONING_EFFORT` | No | `low` | Reasoning effort for reasoning-capable primary and nano models |
| `AZURE_OPENAI_CHAT_REASONING_EFFORT` | No | `none` | Reasoning effort for interactive chat agents; workflows keep `AZURE_OPENAI_REASONING_EFFORT` |
| `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME` | No | primary deployment | Optional dedicated chat deployment; falls back to `AZURE_OPENAI_DEPLOYMENT_NAME` |
| `AZURE_OPENAI_NANO_DEPLOYMENT_NAME` | No | `gpt-5.4-nano` | Low-cost deployment for background labels, classification, and title cleanup |
| `FRAUD_DETECTION_ENABLED` | No | `true` | Enable the anti-fraud pipeline |
| `FRAUD_VISION_DEPLOYMENT` | No | `gpt-5.4-mini` | Vision model for image-authenticity analysis |
| `FRAUD_DETECTION_DEPLOYMENT` | No | `gpt-5.4-mini` | Reasoning model for declaration-versus-evidence consistency |
| `WEBIQ_API_KEY` | No | - | Microsoft Web IQ API key for the demo MCP integration (`web`, `news`, and `browse`). In Azure, Key Vault secret `webiq-api-key` is referenced by the Container App through `infra/set-webiq-secret.ps1`; never set a literal key in source or frontend configuration. Microsoft Entra ID is the recommended future production authentication path. |
| `WEBIQ_MCP_URL` | No | `https://api.microsoft.ai/v3/mcp` | Dedicated Microsoft Web IQ Streamable HTTP MCP endpoint. |
| `WEBIQ_TIMEOUT_SECONDS` | No | `30` | Timeout for a Web IQ MCP request. |
| `FOUNDRY_PROJECT_ENDPOINT` | Conditional | - | Microsoft Foundry project endpoint, distinct from `AZURE_OPENAI_ENDPOINT`; used by the Fabric Data Agent connection, not for web grounding. |
| `AURORA_ENABLED` | No | `false` | Enable the optional managed Foundry Aurora 1.5 weather-risk panel. |
| `AURORA_FOUNDRY_ENDPOINT` | Conditional | - | Tenant-specific Aurora data endpoint from the Foundry deployment; not an OpenAI chat endpoint. |
| `AURORA_DEPLOYMENT_NAME` | No | `aurora-0.25-v1.5` | Deterministic Aurora 1.5 model name from the official Foundry client. |
| `AURORA_ENSEMBLE_DEPLOYMENT_NAME` | No | `aurora-0.25-v1.5-ensemble` | Stochastic Aurora 1.5 model name. One invocation produces one ensemble member. |
| `AURORA_INITIAL_CONDITION_BLOB_URL` | Conditional | - | HTTPS Blob URL of a current, validated Aurora NetCDF batch produced from an authoritative weather-data feed. |
| `AURORA_CHANNEL_CONTAINER_URL` | Conditional | - | Blob container/folder used for endpoint exchange. With Entra auth, the app creates a short-lived delegated SAS and does not persist it. |
| `AURORA_BLOB_CHANNEL_SAS_URL` | Conditional | - | Local-development alternative to `AURORA_CHANNEL_CONTAINER_URL`; SAS must grant read/write/create. Never commit it. |
| `AURORA_TIMEOUT_SECONDS` | No | `900` | End-to-end deadline for task execution and prediction retrieval. |
| `AURORA_POLL_INTERVAL_SECONDS` | No | `2` | Delay between bounded task and Blob marker checks. |
| `AURORA_DEFAULT_HORIZON_HOURS` | No | `12` | Default interactive forecast horizon; must be a multiple of six between 6 and 240 hours. |
| `AURORA_ENDPOINT_EXPIRES_AT` | No | - | ISO 8601 expiration time for a temporary endpoint allocation. The UI displays a persistent countdown and disables new forecasts after expiry. |
| `AURORA_USE_AZURE_AD` | No | `true` | Use DefaultAzureCredential for the managed Aurora endpoint. Set `false` for a Key-authenticated Azure ML endpoint. |
| `AURORA_TOKEN_SCOPE` | No | `https://ml.azure.com/.default` | Entra token scope for an Azure ML managed online endpoint. Override only if the provisioned endpoint specifies another audience. |
| `AURORA_ENDPOINT_TOKEN` | Conditional | - | Endpoint key sent as a bearer token when Entra auth is disabled. Store in Key Vault; never commit it. |
| `AGENTS_OPENAI_API` | No | `responses` | API used by Microsoft Agent Framework agents: `responses` or `chat_completions` for rollback |
| `EXTRACTION_BUDGET_SECONDS` | No | `900` | Wall-clock budget for extraction; remaining files are skipped and the case is flagged for review. Use `0` for no cap. |
| `ANALYSIS_BUDGET_SECONDS` | No | `900` | Wall-clock budget for analysis; remaining sections are skipped. Use `0` for no cap. |
| `ANALYSIS_TOKEN_BUDGET` | No | `400000` | Token budget for analysis. Use `0` for no cap. |
| `MAX_REEXTRACTIONS` | No | `3` | Maximum targeted re-extractions per case, at most one per file |
| `REEXTRACTION_QUALITY_THRESHOLD` | No | `50` | Extraction quality score from 0 to 100 below which a document is re-extracted and flagged |
| `REVIEW_CONFIDENCE_THRESHOLD` | No | `0.6` | Average field confidence below which the case needs human review |
| `MARKITDOWN_ENABLED` | No | `true` | Enable MarkItDown Markdown conversion |
| `MARKITDOWN_MODE` | No | `local` | MarkItDown mode: `local`, `cu`, or `auto` |
| `MARKITDOWN_USE_CONTENT_UNDERSTANDING` | No | `false` | Use Azure Content Understanding from MarkItDown when enabled |
| `UW_APP_STORAGE_ROOT` | No | `data` | Local storage path for application data |
| `UW_APP_PROMPTS_ROOT` | No | `prompts` | Path to prompts and policies |
| `STORAGE_BACKEND` | No | `azure_blob` | Storage backend: `azure_blob` or `local` |
| `AZURE_STORAGE_AUTH_MODE` | No | `default` | Auth method: `default` for DefaultAzureCredential only, or `key` for account key only; there is no fallback |
| `AZURE_STORAGE_ACCOUNT_NAME` | Conditional | - | Azure storage account name, required for DAC and key auth |
| `AZURE_STORAGE_ACCOUNT_KEY` | Conditional | - | Azure storage account key if not using DAC |
| `AZURE_STORAGE_CONTAINER_NAME` | No | `prevaiq-data` | Azure blob container name |

### Aurora admin override

Administrators can configure Aurora from the **Admin > Aurora weather** tab after deployment.
The form persists only non-secret endpoint, model, Blob resource, and default-horizon values under
the current brand. In Azure the record is stored in the application Blob container; local
development uses `UW_APP_STORAGE_ROOT`. A persisted admin record takes precedence over the
`AURORA_*` resource settings above.

Runtime authentication is deployment-owned: managed identity for Blob access and either managed
identity or the Key Vault-backed `aurora-endpoint-key` secret for the endpoint. The admin API rejects
account keys, tokens, URL query strings, and SAS URLs, and never returns the runtime endpoint key.
Use `infra/set-aurora-endpoint-secret.ps1` for a Key-authenticated endpoint. The readiness test can
run while Aurora is disabled. It checks endpoint authentication, reachability, the two-step NetCDF
input contract, and delegated SAS creation **from the PrevaIQ backend**. It does not submit a
forecast or prove that the Aurora worker can read or write the task channel. Only a completed
task with returned NetCDF artifacts establishes end-to-end inference.

The case panel remains visible while calculation is disabled, including when a stored forecast
exists; both calculation and refresh are disabled. Administrators may persist the non-secret
`disabled_reason=blob_access_denied` only after observing a Blob access refusal. It displays the
403 as an observed refusal, not as proof of a particular firewall rule or an Aurora-side failure.
An unspecified suspension does not claim a Blob error. Enabling Aurora clears the suspension reason.
Admin readiness failures expose the originating backend operation, UTC check time, and available
HTTP status, Storage error code and request ID, without exception text, URLs, SAS or credentials.
Correlate these with Storage logs to distinguish backend and worker access failures before changing
network rules. The endpoint invocation protocol and authentication are unchanged.

PrevaIQ uses managed identity for its own task-channel uploads, markers and prediction
downloads when `AURORA_CHANNEL_CONTAINER_URL` is configured. The short-lived delegated SAS
is passed only to Aurora, not used to authenticate PrevaIQ's own data operations. The
explicit legacy `AURORA_BLOB_CHANNEL_SAS_URL` rollback retains SAS-authenticated I/O.
This distinction matters with Network Security Perimeter: subscription-based inbound
rules accept the managed identity but do not support SAS authentication. Such rules alone
cannot authorize the Aurora worker. A worker still needs an independently approved network
path, such as a private endpoint or a narrowly scoped, verified source-IP rule on a dedicated
weather account. Never infer that a denied public IP belongs to Aurora without correlating
it to a real task; never relax the business-document account to test weather connectivity.

An Aurora workspace in the application tenant can use its existing associated Storage account.
Set `auroraChannelStorageAccountName` / `aurora_channel_storage_account_name` to opt in to an
existing account in the deployment resource group; the default is empty and preserves the
original application channel. Both IaC variants create only a private `aurora-tasks` container
(`auroraChannelContainerName` / `aurora_channel_container_name`), grant the application identity
Blob Data Contributor at container scope and Blob Delegator at account scope, and wire its URL.
They do not create an AML workspace, GPU, account, or change that account's network perimeter.
Adopt/import any manually created container and role assignments before managing them with IaC;
never apply both infrastructure tools to the same environment.

`infra/set-aurora-endpoint-secret.ps1` still prompts for hidden key input by default. Automation
with authorized Azure ML access may instead pass `-EndpointKey` as an in-memory `SecureString`;
never put the plain key in a command argument, environment file, chat or source control.
| `AZURE_STORAGE_ALLOW_CREATE_CONTAINER` | No | `false` | Auto-create the container at startup; set `true` for development only |
| `DATABASE_BACKEND` | No | `json` | Database backend: `json` or `postgresql` |
| `POSTGRESQL_HOST` | Conditional | - | PostgreSQL host when using the PostgreSQL backend |
| `POSTGRESQL_PORT` | No | `5432` | PostgreSQL port |
| `POSTGRESQL_DATABASE` | Conditional | - | PostgreSQL database name |
| `POSTGRESQL_USER` | Conditional | - | PostgreSQL username |
| `POSTGRESQL_PASSWORD` | Conditional | - | PostgreSQL password |
| `POSTGRESQL_SSL_MODE` | No | - | SSL mode, such as `require` or `verify-full` |
| `POSTGRESQL_SCHEMA` | No | `public` | PostgreSQL schema for RAG tables |
| `RAG_ENABLED` | No | `false` | Enable RAG-powered policy search |
| `RAG_TOP_K` | No | `5` | Number of policy chunks to retrieve |
| `RAG_SIMILARITY_THRESHOLD` | No | `0.5` | Minimum similarity score for results |
| `EMBEDDING_MODEL` | No | `text-embedding-3-small` | Azure OpenAI embedding model name |
| `EMBEDDING_DEPLOYMENT` | No | Same as model | Azure OpenAI embedding deployment name |
| `EMBEDDING_DIMENSIONS` | No | `1536` | Embedding vector dimensions |
| `SOUSCRIA_MCP_URL` | No | `http://localhost:8090` | Base URL of the Souscr'IA front-office MCP server. It is off unless configured with credentials. See [Souscr'IA MCP connector](souscria-mcp-connector.md). |
| `SOUSCRIA_MCP_PATH` | No | `/scout/mcp` | Souscr'IA MCP Streamable HTTP transport path |
| `SOUSCRIA_SCOUT_TOKEN` | Conditional | - | Pre-minted read-only bearer token with the `service` role for Souscr'IA. Preferred in production. |
| `SOUSCRIA_JWT_SECRET` | Conditional | - | Shared HS256 secret to mint a `service` token locally for development. Never commit it. |
| `SOUSCRIA_MCP_TIMEOUT_SECONDS` | No | `10` | Per-request timeout for Souscr'IA MCP calls |

## Storage configuration

PrevaIQ supports Azure Blob Storage and local filesystem storage.

### Azure Blob Storage

For production deployments, use Azure Blob Storage. Set `AZURE_STORAGE_AUTH_MODE` explicitly; there is no automatic fallback.

```env
STORAGE_BACKEND=azure_blob

# Auth mode: "default" uses DefaultAzureCredential only.
# Set to "key" to use account name + key instead.
AZURE_STORAGE_AUTH_MODE=default

# Account name, required for DAC and key auth.
AZURE_STORAGE_ACCOUNT_NAME=mystorageaccount

# Option A: Managed identity / DefaultAzureCredential (recommended).
# No secret is needed when the identity has the
# "Storage Blob Data Contributor" role on the container.

# Option B: Account key.
# AZURE_STORAGE_ACCOUNT_KEY=your-storage-account-key

# Container name, optional. Defaults to prevaiq-data.
AZURE_STORAGE_CONTAINER_NAME=prevaiq-data

# Container auto-creation, default false for least privilege.
# Set true only for development or migration.
AZURE_STORAGE_ALLOW_CREATE_CONTAINER=false
```

Required RBAC roles for managed identity with DefaultAzureCredential:

| Role | Scope | Purpose |
|------|-------|---------|
| Storage Blob Data Contributor | Container | Read and write blobs |
| Storage Blob Data Reader | Container | Read-only access |

Assign roles with Azure CLI:

```bash
az role assignment create \
  --assignee <principal-id> \
  --role "Storage Blob Data Contributor" \
  --scope /subscriptions/<sub>/resourceGroups/<rg>/providers/Microsoft.Storage/storageAccounts/<account>/blobServices/default/containers/<container>
```

See [quickstart.md](../specs/003-azure-blob-storage-integration/quickstart.md) for detailed setup instructions.

### Local storage

For local development, use filesystem storage:

```env
STORAGE_BACKEND=local
UW_APP_STORAGE_ROOT=data
```

## PostgreSQL RAG configuration

Enable RAG with Azure PostgreSQL Flexible Server and pgvector for semantic policy retrieval.

### Prerequisites

- Azure PostgreSQL Flexible Server v15 or later.
- Extensions enabled: `vector` for pgvector and `pg_trgm`.
- Azure OpenAI embedding model deployed, such as `text-embedding-3-small`.

### Quick setup

```bash
# Start your Azure PostgreSQL server if it is stopped.
az postgres flexible-server start --resource-group rg-prevaiq-demo --name pg-prevaiq-demo

# Run the setup script to provision Azure PostgreSQL and create schema.
uv run python scripts/setup_postgresql_rag.py

# Index existing policies.
uv run python scripts/index_policies.py
```

### Server management

```bash
# Check server status.
az postgres flexible-server show --resource-group rg-prevaiq-demo --name pg-prevaiq-demo --query "state"

# Stop server to save cost when not in use.
az postgres flexible-server stop --resource-group rg-prevaiq-demo --name pg-prevaiq-demo
```

### Manual configuration

```env
# Enable PostgreSQL backend.
DATABASE_BACKEND=postgresql

# PostgreSQL connection.
POSTGRESQL_HOST=your-server.postgres.database.azure.com
POSTGRESQL_PORT=5432
POSTGRESQL_DATABASE=workbenchiq
POSTGRESQL_USER=your_admin_user
POSTGRESQL_PASSWORD=your_password
POSTGRESQL_SSL_MODE=require

# Enable RAG.
RAG_ENABLED=true
RAG_TOP_K=5
RAG_SIMILARITY_THRESHOLD=0.5

# Embedding model, matching your Azure OpenAI deployment.
EMBEDDING_MODEL=text-embedding-3-small
EMBEDDING_DEPLOYMENT=text-embedding-3-small
EMBEDDING_DIMENSIONS=1536
```

### How RAG works

1. **Indexing**: policies are chunked into 500-token chunks with 50-token overlap and embedded through Azure OpenAI.
2. **Storage**: chunks are stored in PostgreSQL with a pgvector HNSW index for fast similarity search.
3. **Query**: user questions are embedded and matched against policy chunks.
4. **Hybrid search**: vector similarity is combined with keyword matching through `pg_trgm`.
5. **Augmentation**: retrieved policy context is injected into chat prompts for grounded responses.

### Admin panel features

- Index statistics with total chunks and last indexed time.
- Manual reindexing for underwriting policies.
- Automatic reindexing when policies are created, updated, or deleted.

See [spec.md](../specs/006-azure-postgresql-rag-integration/spec.md) for detailed architecture documentation.

## Adding a new persona

1. Define the field schema in `app/personas.py`:

```python
MY_PERSONA_FIELD_SCHEMA = {
    "name": "MyPersonaFields",
    "fields": {
        "FieldName": {
            "type": "string",
            "description": "Description for extraction",
            "method": "extract",
            "estimateSourceAndConfidence": True
        }
    }
}
```

2. Add prompts for analysis sections.
3. Register the persona in the `PERSONA_CONFIGS` dictionary.
4. Create frontend components as needed.

## Seeding Customer 360 data

The seed script creates 3 customer profiles with 9 rich applications across all personas. It supports local filesystem and Azure Blob Storage.

```bash
# Local development, default.
python scripts/seed_customer360.py

# Azure Blob Storage, with env vars or .env.
STORAGE_BACKEND=azure_blob \
AZURE_STORAGE_ACCOUNT_NAME=<storage-account> \
AZURE_STORAGE_ACCOUNT_KEY=<key> \
AZURE_STORAGE_CONTAINER_NAME=prevaiq-data \
python scripts/seed_customer360.py
```

| Customer | Risk tier | Products | Narrative |
|----------|-----------|----------|-----------|
| Sarah Chen | Low | Life insurance approved, mortgage approved, auto claim settled | Loyal multi-product customer since 2019 with consistent low risk |
| Marcus Williams | Medium | Life insurance referred, health claim approved, mortgage conditional | Cardiac health concerns correlate across products |
| Priya Patel | High | Auto claim investigating, life insurance pending, mortgage declined | New customer with fraud flags and financial overextension |

Each application includes workbench-quality data: `llm_outputs` with complete section/subsection structure, `extracted_fields` with confidence scores, and `risk_analysis` results. Seed data is modular; see `scripts/seed_data/` for per-persona modules.
