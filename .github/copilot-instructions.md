# PrevaIQ (WorkbenchIQ) — Copilot Custom Instructions

## Project Overview
PrevaIQ (technical name *WorkbenchIQ*) is a brand-agnostic, AI-powered insurance document processing workbench, built with FastAPI (Python 3.12) backend and Next.js 14 frontend. The brand is injected at build time (`BRAND_NAME`); the only brand today is **PrevaIQ**. It supports 5 personas: Souscription, Sinistres Santé, Sinistres Auto, Souscription Hypothécaire, and Client 360.

## Tech Stack
- **Backend**: Python 3.12, FastAPI, uv (package manager), Gunicorn + Uvicorn workers
- **Frontend**: Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS, next-intl (French i18n)
- **Database**: PostgreSQL 16 + pgvector (RAG semantic search)
- **AI Services**: Azure OpenAI (GPT-5.4 mini / GPT-5.4 nano), Azure AI Content Understanding, MarkItDown, Microsoft Web IQ (MCP)
- **Storage**: Azure Blob Storage
- **Deployment**: Docker → Azure Container Registry → Azure Container Apps (Sweden Central)
- **IaC**: Bicep (infra/main.bicep) or Terraform (infra/terraform/) — same resources, one tool per environment

## Architecture

### Temporary Files
- `.tmp/` — Directory for all temporary, debug, and agent-generated files (scripts, logs, scratch)
- **ALWAYS** use `.tmp/` for any temporary file creation — never pollute project root
- `.tmp/` is gitignored — safe to write anything there

### Backend (root directory)
- `api_server.py` — FastAPI entry point
- `app/` — Application modules (config, auth, storage, processing, claims, rag, mortgage, multimodal)
- `app/orchestration.py` — Controlled orchestration: `StageBudget` (time/tokens/re-extractions), validation (`assess_extraction`, `assess_analysis`), review status (`needs_review` / `auto_ok` / `reviewed`) persisted in `ApplicationMetadata.orchestration`. Never add open-ended retry loops: every retry must be bounded by a stage budget.
- `app/claims/` — Claims processing engine (engine.py, api.py, policies.py, search.py)
- `app/rag/` — RAG pipeline (indexer.py, chunker.py, embeddings.py, search.py, repository.py)
- `app/storage_providers/` — Azure Blob or local file storage
- `prompts/` — Policy JSON files (automotive, life-health, mortgage, property-casualty)
- `scripts/` — CLI tools (index_pdf_policies.py, setup_postgresql_rag.py, etc.)
- `scripts/eval_pipeline.py` — Evaluation harness (quality, completeness, citations, latency, tokens, cost) over `tests/fixtures/eval/manifest.json`; run it to compare variants before generalizing any model/API/extraction change
- `docs/architecture/` — Architecture diagrams (`.drawio` source of truth + `.svg` + `.png`), maintained with the `.github/skills/architecture-diagram-author` skill; update them when components, endpoints or the orchestration flow change

### Frontend (frontend/)
- `src/app/` — Next.js App Router pages (admin, customers, login)
- `src/components/` — 40+ React components (TopNav, Sidebar, LandingPage, claims/, mortgage/)
- `src/lib/` — Utilities (api.ts, personas.ts, PersonaContext.tsx, auth.ts, types.ts)
- `src/i18n/` — next-intl configuration (default locale: en)
- `messages/` — Translation files (fr.json, en.json)

### Infrastructure (infra/)
- `main.bicep` — All Azure resources (ACR, ACA, Storage, PostgreSQL, Key Vault, AI Search, Foundry account + project + model deployments for OpenAI and Content Understanding)
- `main.bicepparam` — Parameter values (`projectName=prevaiq`, `environment=demo`, `location=swedencentral`; secrets from `PREVAIQ_API_KEY` / `PREVAIQ_PG_PASSWORD`)
- `main.bicep` and `terraform/` are a pair and must change together in the same edit: every resource, role assignment, app setting, network rule, output and default must exist in both with the same name (`prevaiq-*` naming) and the same default values. Validate both before finishing (`az bicep build --file infra/main.bicep` and `terraform -chdir=infra/terraform fmt -check` / `validate`). Never apply both tools to the same resource group. Optional private networking exists in both: Bicep `privateNetworkingEnabled` / `vnetAddressSpace` / `adminIpRanges`, Terraform `private_networking_enabled` / `vnet_address_space` / `admin_ip_ranges` (`network.tf`).
- `deploy.ps1` — Image build + Container Apps rollout (mandatory deploy path)
- `deploy.sh` — CLI deployment script (infra + images); `--iac bicep|terraform` picks the infra tool
- `set-webiq-secret.ps1` — Stores the Web IQ key in Key Vault

## Coding Conventions

### Python
- Line length: 100 (ruff + black)
- Target: Python 3.12
- Use `from __future__ import annotations` in all modules
- Logging via `app.utils.setup_logging()`
- Async database operations via `asyncpg`
- Dependency management via `uv` (pyproject.toml + uv.lock)
- **After adding/changing dependencies in `pyproject.toml`, ALWAYS run `uv lock` to update `uv.lock`** — the Dockerfile uses `uv sync --frozen` which fails if the lockfile is stale

### Microsoft Agent Framework
- **NEVER depend on `agent-framework` metapackage** — it overwrites `agent_framework/__init__.py` with an empty file in Docker, breaking all imports
- **ALWAYS use `agent-framework-core>=1.21.0,<2.0` + `agent-framework-openai>=1.15.0,<2.0`** as direct dependencies
- Import: `from agent_framework import Agent` (`ChatAgent` is not exported)
- Workflows run branches with `asyncio.gather` (see `app/agents/workflows.py`); Web IQ via `MCPStreamableHTTPTool`
- In `agent-framework-openai` 1.x, `OpenAIChatClient` = **Responses API**, `OpenAIChatCompletionClient` = Chat Completions. `AGENTS_OPENAI_API` (`responses` default / `chat_completions` rollback) selects the client in `_build_chat_client`. `app/openai_client.chat_completion` stays on Chat Completions for JSON prompts.
- Endpoints are separate: `AZURE_OPENAI_ENDPOINT` (models), `FOUNDRY_PROJECT_ENDPOINT` via `settings.foundry` (Agent Service only), `AZURE_CONTENT_UNDERSTANDING_ENDPOINT` (CU). Keep `application_to_dict` keys stable (contract test in `tests/test_orchestration.py`).
- Constructor: `Agent(client=..., name=..., instructions=..., tools=[...])`
- Client: `from agent_framework.openai import OpenAIChatClient`
- The Dockerfile includes a build-time verification: `RUN .venv/bin/python -c "from agent_framework import Agent; ..."`
- Agent system prompts stay in French (they control LLM response language)
- Prompt framing strings (history context, enriched_message) should be in neutral English

### TypeScript / React
- Next.js App Router with `'use client'` directives
- Tailwind CSS for styling (brand colors from `frontend/src/lib/brand.ts`)
- `clsx` for conditional class names
- `lucide-react` for icons
- English as default locale via `next-intl` (`useTranslations()` hook)
- **All user-facing strings MUST use `useTranslations()` — never hardcode text in JSX**
- Translation keys go in `messages/fr.json` (primary) and `messages/en.json` (mirror)

### Branding
- App name: **PrevaIQ** (Azure resources and images are named `prevaiq`; the technical name WorkbenchIQ remains only in the repository, the Python package and the PostgreSQL schema)
- Brand config: `app/brands.py` (backend) and `frontend/src/lib/brand.ts` (frontend) — PrevaIQ only
- Logo: `frontend/public/prevaiq-logo.svg`
- Primary color: `#17395C`, Secondary: `#2EC4B6`, Accent: `#0F2E4D`
- Default language: English (`<html lang="en">`), French available via the FR/EN switcher
- All persona names in French (Souscription, Sinistres Auto, etc.)

## Docker & Deployment

### Deployment — MANDATORY: Use deploy.ps1
**Always use `.\infra\deploy.ps1` for deployment.** Never run individual `az acr build` or `az containerapp update` commands manually.

### Azure environment — CHECK `az account show` BEFORE DEPLOYING

There is a **single environment** (DEMO). Tenant and subscription come from `AZURE_TENANT_ID` / `AZURE_SUBSCRIPTION_ID` (or the current `az account`); never commit them.

| Env | Region | RG / Apps / ACR / Images |
|-----|--------|--------------------------|
| **DEMO** | `swedencentral` | `rg-prevaiq-demo` / `ca-api-demo`,`ca-frontend-demo` / `acrprevaiqdemo` (Basic, no agent pool) / `prevaiq-api`,`prevaiq-frontend` |

```powershell
az login --tenant $env:AZURE_TENANT_ID   # first time / token expired
az account set --subscription $env:AZURE_SUBSCRIPTION_ID
```

The GitHub Actions CD pipeline needs the OIDC secrets `AZURE_CLIENT_ID` / `AZURE_TENANT_ID` / `AZURE_SUBSCRIPTION_ID`; until they are set, deploy manually via `deploy.ps1`.

```powershell
.\infra\deploy.ps1                              # Full deploy (backend + frontend), brand=PrevaIQ
.\infra\deploy.ps1 -SkipFrontend                # Backend only
.\infra\deploy.ps1 -SkipBackend                 # Frontend only
.\infra\deploy.ps1 -Tag "v1.0"                  # Custom tag (default: git short SHA)
```

The script handles: Azure login verification, AI deployment preflight, minimal context staging (avoids 113 MiB upload), ACR remote build with `--build-arg BRAND_NAME`, ACA container update, traffic routing to the new revision, health checks, and deployment URL display with FQDN change detection.

**Post-deploy DNS check**: `deploy.ps1` compares current ACA FQDNs against `PREVAIQ_KNOWN_API_FQDN` / `PREVAIQ_KNOWN_FE_FQDN` (environment variables, never committed). When unset, the script prints the values to record; a changed FQDN is flagged in red.

**Always report the deployed URLs to the user** after running `deploy.ps1`.

### Brand in the image

**BRAND_NAME is baked into the Docker images at build time** via `ARG BRAND_NAME` (default `PrevaIQ`). The single brand is served on the default host — no revision labels.

- `config.py` reads `BRAND_NAME` env var (set by Docker `ENV BRAND_NAME=${BRAND_NAME}`)
- The brand controls: email/SMS signatures, agent instructions, policy search context, communication templates, blob prefix `brands/<brand>/...`
- **NEVER set `BRAND_NAME` via `az containerapp update --set-env-vars`** — it would override the baked-in value. `deploy.ps1` removes it if present.

**ACA revision immutability**: ACA revisions are immutable — if the image tag hasn't changed, `az containerapp update` is a no-op and the old code keeps running. The deploy script uses `--revision-suffix d<MMddHHmmss>` to force a new revision on every deploy, even when the image tag is reused. The git short SHA is the default tag. Verify active revisions with `az containerapp revision list`.

### Build Images (reference only — prefer deploy.ps1)
```bash
# Backend (from repo root)
az acr build --registry acrprevaiqdemo --image prevaiq-api:<tag> --build-arg BRAND_NAME=PrevaIQ --file Dockerfile .

# Frontend (from frontend/ context)
az acr build --registry acrprevaiqdemo --image prevaiq-frontend:<tag> --build-arg BRAND_NAME=PrevaIQ --file Dockerfile frontend/
```

### .dockerignore Strategy
- Backend: excludes tests/, docs/, specs/, frontend/, assets/pdf/, .git/, scripts/ (except startup.sh)
- Frontend: excludes node_modules/, .next/, coverage/
- Critical for `az acr build` speed (uploads context to Azure)

### ACA Update
```bash
az containerapp update --name ca-api-demo --resource-group rg-prevaiq-demo --image <acr>/prevaiq-api:<tag>
az containerapp update --name ca-frontend-demo --resource-group rg-prevaiq-demo --image <acr>/prevaiq-frontend:<tag>
```

### Health Check
- API: `GET /` returns `{"status":"ok","name":"PrevaIQ","version":"..."}`
- Bypasses API key auth (middleware intercept)

## CI/CD Pipeline

### CI (ci.yml) — Runs on every push/PR
1. **Backend lint**: `ruff check` + `ruff format --check` + import verification
2. **Frontend lint**: TypeScript type check + Next.js lint + build
3. **Docker build check**: Verify both Dockerfiles build (no push)

### CD (deploy.yml) — Runs after CI passes on main
1. Detect changed paths (api vs frontend)
2. Build + push changed images to ACR
3. Update ACA container apps
4. Health check verification

### Required GitHub Secrets
- `AZURE_CLIENT_ID` — OIDC app registration
- `AZURE_TENANT_ID` — Azure AD tenant
- `AZURE_SUBSCRIPTION_ID` — Subscription ID
- `PREVAIQ_API_KEY` — Backend API key

## RAG / Policy Search

### Indexing policy PDFs
No policy PDFs ship with the repo: drop the insurer's conditions générales PDFs into `assets/pdf/` first.
```bash
python scripts/index_pdf_policies.py --force          # Uses Document Intelligence
python scripts/index_pdf_policies.py --local --force   # Uses PyMuPDF fallback
```

### Policy document categories (assets/pdf/)
| Document type | Category | DB Category |
|---------------|----------|-------------|
| Conditions générales habitation | Property | property_casualty |
| Complémentaire santé | Health | life_health |
| Conditions générales auto | Auto | automotive |
| Conditions générales flotte auto | Fleet | automotive |

### Search Methods
- `semantic_search()` — Pure vector similarity
- `filtered_search()` — Vector + metadata filters (category, risk_level)
- `intelligent_search()` — LLM-inferred categories + vector
- `hybrid_search()` — pgvector + trigram text search

## Key Environment Variables
- `BRAND_NAME` — Brand identity (only `PrevaIQ`). **Baked into Docker image at build time** via `ARG BRAND_NAME`. Do NOT set via ACA env vars.
- `AZURE_OPENAI_ENDPOINT` — OpenAI endpoint URL
- `AZURE_OPENAI_DEPLOYMENT_NAME` — e.g., gpt-5.4-mini
- `WEBIQ_API_KEY` — Microsoft Web IQ key; in Azure it is the Key Vault secret `webiq-api-key` referenced by the Container App (`infra/set-webiq-secret.ps1`). Never commit it.
- `AZURE_CONTENT_UNDERSTANDING_ENDPOINT` — Azure AI Content Understanding
- `AZURE_CONTENT_UNDERSTANDING_COMPLETION_DEPLOYMENT` / `AZURE_CONTENT_UNDERSTANDING_EMBEDDING_DEPLOYMENT` — CU GA analyzer model aliases (defaults: `gpt-5.4-mini`, `text-embedding-3-large`)
- `MARKITDOWN_ENABLED` / `MARKITDOWN_MODE` — optional Markdown conversion path for document/RAG ingestion
- `STORAGE_BACKEND` — `azure_blob` or `local`
- `AGENTS_OPENAI_API` — `responses` (default) or `chat_completions` for MAF agents
- `APPLICATIONINSIGHTS_CONNECTION_STRING` — enables OpenTelemetry → Application Insights (set by Bicep). Startup logs the masked connection and emits an `app_insights.connection_check` span; agent spans/logs come from `app/telemetry.py` (`start_span`)
- `LOG_LEVEL` — `INFO` (default) or `DEBUG` for the app logger (`app.utils.setup_logging()`); use it to see agent/telemetry debug logs
- `EXTRACTION_BUDGET_SECONDS` / `ANALYSIS_BUDGET_SECONDS` / `ANALYSIS_TOKEN_BUDGET` / `MAX_REEXTRACTIONS` / `REEXTRACTION_QUALITY_THRESHOLD` / `REVIEW_CONFIDENCE_THRESHOLD` — orchestration budgets and review thresholds
- `DATABASE_BACKEND` — `postgresql` or `json`
- `RAG_ENABLED` — `true` to enable policy search
- `API_KEY` — Backend auth key (min 32 chars)

## TSX / React Best Practices

### SOLID Principles
- **Single Responsibility (SRP)**: One component = one concern. A tab panel should be its own component, not 500 lines inside a parent. Extract `<AdminDocumentsTab>`, `<AdminPromptsTab>`, `<AdminAnalyzerTab>`, `<AdminPoliciesTab>` from monolithic pages.
- **Open/Closed (OCP)**: Extend via composition (render props, children, slots), not by adding more `if/else` branches to existing components. New persona → new overview component, not more conditionals in a shared one.
- **Liskov Substitution (LSP)**: Shared prop interfaces (e.g. `ClaimsOverviewProps`) must be interchangeable across `AutomotiveClaimsOverview`, `PropertyCasualtyClaimsOverview`, `LifeHealthClaimsOverview`.
- **Interface Segregation (ISP)**: Don't pass the entire application object when a component only needs `{ id, status }`. Keep prop types narrow.
- **Dependency Inversion (DIP)**: Components depend on abstractions (API hooks, context), not on `fetch()` calls embedded inline. Extract data-fetching into custom hooks (`useApplications`, `usePolicies`).

### YAGNI (You Aren't Gonna Need It)
- Don't add features, config options, or abstractions "for later". Build only what the current task requires.
- No speculative generalization: if only one persona uses a component, don't parameterize it for all five.
- Delete dead code paths — unused props, commented-out JSX, unreachable branches.

### DRY (Don't Repeat Yourself)
- Extract repeated API call patterns into shared hooks (e.g. `useFetch<T>(url)`).
- Shared form field patterns → reusable `<FormField label={t('key')} value={v} onChange={fn} />`.
- Policy editor forms (automotive, health, underwriting) share identical field layouts — use a data-driven renderer instead of duplicating JSX.
- Translation key patterns: use interpolation (`t('status', { name })`) over separate keys per variant.

### Avoid God Components
- **Rule**: No component file should exceed ~400 lines. Files above 600 lines must be refactored.
- **Current offenders**: `admin/page.tsx` (2392 lines), `LandingPage.tsx` (873), `LifeHealthClaimsOverview.tsx` (875), `GlossaryManager.tsx` (773).
- **Refactor pattern**: Extract each logical section (tab, panel, modal, form) into its own file under a co-located folder (e.g. `src/components/admin/DocumentsTab.tsx`).
- **State management**: Lift shared state into a context or custom hook (`useAdminState`), pass only what each child needs.

### Component Design Guidelines
- Prefer composition over inheritance — never use class components.
- Custom hooks for any logic reused across ≥2 components (`useToast`, `useApplications`, `usePolicyEditor`).
- Co-locate related files: `components/admin/DocumentsTab.tsx`, `components/admin/useAdminState.ts`, `components/admin/types.ts`.
- Keep JSX readable: extract complex conditions into named variables or helper functions before the return statement.
- All user-facing strings via `useTranslations()` — no hardcoded French or English in JSX.

## Demo Quality Standards

### Data Coherence
- Demo data must reflect realistic French insurance scenarios for a neutral insurer (PrevaIQ): fictitious but plausible French names, addresses, SIRET numbers and policy numbers — never real insurer names, logos or documents.
- Use the 5 persona workflows with plausible documents: attestation d'assurance habitation, déclaration de sinistre auto with photos, bulletin d'adhésion santé, dossier hypothécaire with property valuation.
- Monetary values in EUR (€), dates in DD/MM/YYYY, phone numbers in +33 format.
- Policy references must match the policy PDFs actually indexed from `assets/pdf/`.

### Demo Flow — Fast & Coherent
- Each persona demo should complete in under 3 minutes: upload → extraction → AI analysis → result display.
- Pre-seed representative documents in Azure Blob so the demo starts with data already available (no waiting for uploads).
- Show the full AI pipeline: Content Understanding/MarkItDown extraction → GPT-5.4 mini analysis → RAG policy search → risk assessment, not just one step.
- Highlight what each AI agent does: Data Agent (extraction), Risk Agent (analysis), Policy Agent (RAG search).

### Mandatory Demo UI and Content Consistency Check
- **Before completing any change to UI components, dialogs, tags, elements, names, labels, translations, assets, demo content, or demo folders, check whether the demo dialog and its referenced content are affected.** Do not assume a UI-only change has no demo impact.
- Update affected demo dialog titles, descriptions, tags, displayed names, previews, and file selections to match the modified UI and demo content. Keep French and English translations synchronized.
- When an asset or demo file/folder is added, renamed, moved, or removed, update all affected dialog references, manifests, loaders, seed/generation scripts, and copy/download/upload paths. Verify that each referenced file exists in the intended folder and that obsolete names or paths are no longer offered.
- Verify the affected demo dialog in the running UI: open it, check the displayed content and assets, and exercise the relevant selection, preview, download, or upload action. Run focused checks for changed references and report any UI verification that could not be performed.
- In the completion summary, explicitly state whether demo dialog/content/folder updates were required, what was synchronized, and what was verified. If no update was needed, state why.

### Personas Demo Scenarios
| Persona | Demo Scenario | Key Output |
|---------|--------------|------------|
| Souscription | Health underwriting: APS medical document → risk scoring | Risk rating, medical flags, policy recommendation |
| Sinistres Santé | Health claim: hospital invoice → coverage check | Reimbursement calculation, policy match, exclusions |
| Sinistres Auto | Auto claim: accident report + photos → damage assessment | Damage estimate, liability analysis, fraud indicators |
| Souscription Hypothécaire | Mortgage: property + borrower docs → eligibility | LTV ratio, debt-to-income, property valuation |
| Client 360 | Customer overview: aggregated view across all policies | Cross-sell opportunities, claim history, risk profile |

## Insurance Workflow Improvement

### How PrevaIQ Improves Claims Processing
The document processing workbench accelerates the end-to-end insurance claims workflow:

1. **FNOL (First Notice of Loss)** — High AI potential
   - Content Understanding extracts structured data from déclarations de sinistre (scanned forms, photos), with MarkItDown Markdown conversion when useful
   - GPT-5.4 mini validates data consistency, flags missing fields
   - RAG searches Conditions Générales to verify initial coverage
   - **Impact**: Automated data extraction replaces manual re-keying, reduces errors

2. **Claim Analysis** — High AI potential
   - Multi-modal analysis: text extraction + damage photo assessment (auto claims)
   - Risk Agent scores claim severity and estimates liability
   - Policy Agent cross-references coverage limits, deductibles, exclusions via RAG
   - **Impact**: Faster triage, consistent analysis, auditable AI reasoning with source citations

3. **Fraud Detection** — High AI potential
   - Anomaly detection via claim history patterns (Client 360 persona)
   - Cross-reference declared damages vs. photo evidence (auto multimodal)
   - Flag inconsistencies between declaration and extracted document data
   - **Impact**: Early fraud indicators surfaced during analysis, not after payment

4. **Underwriting Policy Adjustments** — High AI potential
   - RAG-powered policy search across the indexed conditions générales
   - AI-suggested adjustments based on claims frequency and severity
   - Risk scoring models inform premium recalculation
   - **Impact**: Data-driven underwriting decisions, faster policy updates

5. **Financial Administration** — Medium AI potential
   - Structured extraction of monetary amounts, dates, policy numbers
   - Automated accuracy checks against policy terms
   - **Impact**: Reduced back-and-forth with policyholders, higher data accuracy

### Business Outcomes
- **Less back-and-forth**: AI extracts and validates data upfront, reducing information requests
- **Higher NPS/CSAT**: Faster claim resolution with transparent AI reasoning
- **Lower expense ratio**: Automated extraction and analysis reduce manual processing time
- **Higher productivity**: Agents focus on exceptions, not data entry
- **Higher data accuracy**: Document Intelligence + LLM validation catch errors early
- **Less fraud**: Multi-modal cross-referencing and anomaly detection at intake
