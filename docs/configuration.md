# Configuration

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
| `WEBIQ_API_KEY` | No | - | Microsoft Web IQ key for MCP web, news, and browse. In Azure, Key Vault secret `webiq-api-key` is referenced by the Container App through `infra/set-webiq-secret.ps1`. |
| `WEB_INTELLIGENCE_ENABLED` | No | `false` | Enable the optional Bing web-intelligence branch for Cat-Nat, weather, and decrees |
| `FOUNDRY_PROJECT_ENDPOINT` | Conditional | - | Microsoft Foundry project endpoint for Agent Service only, distinct from `AZURE_OPENAI_ENDPOINT`; required for `WEB_INTELLIGENCE_ENABLED=true` and the Fabric Data Agent |
| `AGENTS_OPENAI_API` | No | `responses` | API used by Microsoft Agent Framework agents: `responses` or `chat_completions` for rollback |
| `EXTRACTION_BUDGET_SECONDS` | No | `900` | Wall-clock budget for extraction; remaining files are skipped and the case is flagged for review. Use `0` for no cap. |
| `ANALYSIS_BUDGET_SECONDS` | No | `900` | Wall-clock budget for analysis; remaining sections are skipped. Use `0` for no cap. |
| `ANALYSIS_TOKEN_BUDGET` | No | `400000` | Token budget for analysis. Use `0` for no cap. |
| `MAX_REEXTRACTIONS` | No | `3` | Maximum targeted re-extractions per case, at most one per file |
| `REEXTRACTION_QUALITY_THRESHOLD` | No | `50` | Extraction quality score from 0 to 100 below which a document is re-extracted and flagged |
| `REVIEW_CONFIDENCE_THRESHOLD` | No | `0.6` | Average field confidence below which the case needs human review |
| `WEB_INTELLIGENCE_AGENT_NAME` | No | `PrevaIQ-WebIntelligence` | Foundry agent name with Bing grounding for web verification |
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


