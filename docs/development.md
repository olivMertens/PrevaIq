# Local development

## Prerequisites

- **Python 3.12+** for the backend runtime.
- **Node.js 18+** for the frontend runtime.
- **[uv](https://github.com/astral-sh/uv)** or **pip** for Python dependency management.
- **Azure subscription** with these services:
  - Azure AI Content Understanding with the `prebuilt-documentSearch` analyzer.
  - Azure OpenAI Service with `gpt-5.4-mini` for primary, chat, fraud, and Content Understanding workloads, `gpt-5.4-nano`, and `text-embedding-3-large` / `text-embedding-3-small`.

Reasoning models such as `gpt-5.4-mini` and `gpt-5.4-nano` spend hidden reasoning tokens before visible output. The backend (`app/openai_client.py`) enforces `_REASONING_MIN_COMPLETION_TOKENS = 4000` so these models do not exhaust the budget before returning JSON. Do not lower this floor.

## Quick start

### Clone and install dependencies

```bash
# Clone the repository.
git clone https://github.com/olivMertens/PrevaIq.git
cd PrevaIq

# Install Python dependencies with uv, recommended.
uv sync

# Or use pip.
pip install -r requirements.txt

# Install frontend dependencies.
cd frontend
npm install
cd ..
```

### Configure Azure services

Create a `.env` file in the project root:

```env
# Azure AI Content Understanding.
AZURE_CONTENT_UNDERSTANDING_ENDPOINT=https://your-resource.cognitiveservices.azure.com
AZURE_CONTENT_UNDERSTANDING_USE_AZURE_AD=true
AZURE_CONTENT_UNDERSTANDING_API_VERSION=2025-11-01
AZURE_CONTENT_UNDERSTANDING_COMPLETION_DEPLOYMENT=gpt-5.4-mini
AZURE_CONTENT_UNDERSTANDING_EMBEDDING_DEPLOYMENT=text-embedding-3-large
# If not using Azure AD, set the API key:
# AZURE_CONTENT_UNDERSTANDING_API_KEY=your-key-here

# Azure OpenAI.
AZURE_OPENAI_ENDPOINT=https://your-openai.openai.azure.com
AZURE_OPENAI_API_KEY=your-openai-api-key
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-5.4-mini
AZURE_OPENAI_MODEL_NAME=gpt-5.4-mini
AZURE_OPENAI_API_VERSION=2025-04-01-preview
AZURE_OPENAI_REASONING_EFFORT=low
AZURE_OPENAI_NANO_DEPLOYMENT_NAME=gpt-5.4-nano
AZURE_OPENAI_NANO_MODEL_NAME=gpt-5.4-nano

# Optional MarkItDown conversion path for Markdown/RAG ingestion.
MARKITDOWN_ENABLED=true
MARKITDOWN_MODE=local
MARKITDOWN_USE_CONTENT_UNDERSTANDING=false

# Optional configuration.
# UW_APP_STORAGE_ROOT=data
```

| Method | When to use | Configuration |
|--------|-------------|---------------|
| Azure AD, recommended | Production and CI/CD | Set `AZURE_CONTENT_UNDERSTANDING_USE_AZURE_AD=true` and run `az login` |
| API key | Local development | Set `USE_AZURE_AD=false` and provide `AZURE_CONTENT_UNDERSTANDING_API_KEY` |

### Run the application

Run both servers together:

```bash
# Windows
scripts/run_frontend.bat

# Linux/macOS
./scripts/run_frontend.sh
```

Or run servers separately:

```bash
# Terminal 1: start API server.
uv run python -m uvicorn api_server:app --reload --port 8000

# Terminal 2: start frontend.
cd frontend
npm run dev
```

### Access the application

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs, Swagger | http://localhost:8000/docs |

For Azure Container Apps, read the FQDNs for `ca-frontend-demo` and `ca-api-demo` in `rg-prevaiq-demo` after initial provisioning. `infra/deploy.ps1` prints them.

## Usage guide

### Underwriter workflow

1. **Create a new application**: select the underwriting persona, click **New Application**, enter an optional external reference or policy number, upload PDF documents, and create the application.
2. **Document extraction**: Azure AI Content Understanding extracts applicant information, medical history, medications, lab results, and allergies with confidence scores.
3. **AI analysis**: the LLM generates customer profile, medical summary, risk assessment, lab results, requirements, and next steps.
4. **Policy-driven assessment**: hover over risk ratings to see rationale and policy citations, run policy checks, and export policy reports.
5. **Ask IQ chat**: ask questions with full application context. Answers include policy citations, structured risk analysis, and rich response cards.
6. **Review and export**: review extracted fields with source citations, confidence indicators, and exports.

### Admin workflow

1. Edit prompts for the target use case.
2. Manage analyzers for field extraction.
3. Re-run selected analysis sections with updated prompts.

## Project structure

```
.
├── api_server.py                 # FastAPI backend server
├── app/
│   ├── config.py                 # Configuration management
│   ├── customer360.py            # Customer 360 unified data layer, blob-aware
│   ├── personas.py               # Multi-persona definitions and field schemas
│   ├── storage.py                # File and metadata handling with provider abstraction
│   ├── storage_providers/        # Pluggable storage backends
│   │   ├── base.py               # StorageProvider protocol and settings
│   │   ├── local.py              # Local filesystem provider
│   │   └── azure_blob.py         # Azure Blob Storage provider
│   ├── prompts.py                # Prompt templates and catalog
│   ├── openai_client.py          # Azure OpenAI integration
│   ├── content_understanding_client.py  # Azure CU integration
│   ├── processing.py             # Orchestration logic
│   ├── underwriting_policies.py  # Policy loader and injector
│   ├── utils.py                  # Helper utilities
│   ├── claims/                   # Claims processing module
│   │   ├── api.py                # Claims API router
│   │   ├── engine.py             # Claims policy engine
│   │   ├── policies.py           # Claims policy loader
│   │   └── search.py             # Claims policy search, RAG
│   ├── mortgage/                 # Mortgage underwriting module
│   │   ├── processor.py          # Document processing and extraction
│   │   ├── calculator.py         # GDS/TDS/LTV ratio calculations
│   │   ├── policy_engine.py      # OSFI B-20 compliance engine
│   │   ├── risk_analysis.py      # Mortgage risk factor scoring
│   │   ├── stress_test.py        # Stress test at MQR rates
│   │   ├── aggregator.py         # Multi-document data aggregation
│   │   ├── property_deep_dive.py # AI property analysis with Bing Grounding
│   │   └── extractors/           # Field extractors for borrower, income, property, loan, credit
│   ├── database/                 # PostgreSQL connection management
│   └── rag/                      # Optional PostgreSQL RAG module
│       ├── chunker.py            # Policy text chunking
│       ├── embedder.py           # Azure OpenAI embedding client
│       ├── repository.py         # PostgreSQL CRUD operations
│       ├── search.py             # Semantic and hybrid search
│       ├── service.py            # Unified RAG service interface
│       └── indexer.py            # Policy indexing pipeline
├── scripts/                      # Utility scripts
│   ├── seed_customer360.py       # Seed Customer 360 data, local and Azure Blob
│   ├── seed_data/                # Rich seed data modules
│   │   ├── underwriting.py       # Underwriting demo apps with full LLM outputs
│   │   ├── claims.py             # Auto and health claim demos
│   │   └── mortgage.py           # Mortgage apps with extracted fields
│   ├── setup_postgresql_rag.py   # Azure PostgreSQL provisioning
│   └── index_policies.py         # CLI for policy indexing
├── prompts/                      # Git-tracked prompts and policies
├── frontend/                     # Next.js 14 frontend
├── tests/                        # Test suite and fixtures
├── data/                         # Application data storage, gitignored
├── docs/
│   └── images/                   # Documentation screenshots
└── .env.example                  # Environment template
```

## API reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| **Applications** | | |
| `GET` | `/api/personas` | List all available personas |
| `GET` | `/api/personas/{id}` | Get a persona configuration |
| `GET` | `/api/applications` | List applications, filterable by `?persona=` |
| `GET` | `/api/applications/{id}` | Get application details |
| `POST` | `/api/applications` | Create an application with file upload |
| `POST` | `/api/applications/{id}/extract` | Run Content Understanding extraction |
| `POST` | `/api/applications/{id}/analyze` | Run GPT analysis |
| `POST` | `/api/applications/{id}/risk-analysis` | Run policy evaluation |
| **Customer 360** | | |
| `GET` | `/api/customers` | List customer profiles |
| `GET` | `/api/customers/{id}` | Get Customer 360 view with profile, journey, and risk correlations |
| **Mortgage** | | |
| `GET` | `/api/mortgage/applications` | List mortgage applications |
| `GET` | `/api/mortgage/applications/{id}` | Get mortgage application with computed ratios and findings |
| `GET` | `/api/mortgage/applications/{id}/property-deep-dive` | Get property deep-dive analysis |
| `POST` | `/api/mortgage/applications/{id}/property-deep-dive` | Run property deep dive |
| **Claims** | | |
| `POST` | `/api/claims/submit` | Submit a claim with files |
| `GET` | `/api/claims/{id}/assessment` | Get claim assessment |
| `POST` | `/api/claims/policies/search` | Search claims policies |
| **Chat and RAG** | | |
| `POST` | `/api/applications/{id}/chat` | Send a chat message with context |
| `GET` | `/api/applications/{id}/conversations` | List chat sessions |
| `GET` | `/api/conversations` | List all conversations across applications |
| `POST` | `/api/rag/index` | Index policies for RAG |
| `GET` | `/api/rag/stats` | Get RAG index statistics |
| `POST` | `/api/rag/query` | Query policies with semantic search |
| **Admin** | | |
| `GET` | `/api/prompts` | Get prompt catalog |
| `PUT` | `/api/prompts/{section}/{subsection}` | Update a prompt |
| `GET` | `/api/policies` | Get underwriting policies |
| `POST` | `/api/policies` | Create an underwriting policy |
| `GET` | `/api/analyzer/status` | Get custom analyzer status |
| `POST` | `/api/analyzer/create` | Create a custom analyzer |

## Development tasks

### Running tests

```bash
pytest tests/ -v
```

### Pipeline evaluation

```bash
python scripts/eval_pipeline.py --variant baseline
```

See [Evaluation before rollout](architecture.md#evaluation-before-rollout).

### Code formatting

```bash
# Python
black app/ api_server.py
ruff check app/ api_server.py --fix

# Frontend
cd frontend
npm run lint
```

### Building for production

```bash
# Frontend build
cd frontend
npm run build

# Run production server
uvicorn api_server:app --host 0.0.0.0 --port 8000
```

## Troubleshooting

### Common issues

| Issue | Cause | Solution |
|-------|-------|----------|
| Settings incomplete | Missing environment variables | Check `.env` and restart the API server |
| 401/403 errors | Invalid API keys | Verify Azure credentials |
| 404 errors | Wrong endpoint URLs | Remove trailing slashes from endpoints |
| 429 errors | Rate limiting | Wait and retry, or increase quota |
| CORS errors | Frontend cannot reach API | Ensure the API runs on port 8000 |

### Logs

- API logs: terminal running `uvicorn`.
- Frontend logs: browser developer console.
- Azure logs: Azure Portal > Monitor > Logs.


