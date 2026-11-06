<div align="center">

# PrevaIQ

### Agentic workbench for insurance claims and underwriting

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Next.js](https://img.shields.io/badge/Next.js-frontend-black.svg)](frontend/README.md)
[![Content Understanding GA](https://img.shields.io/badge/Content%20Understanding-2025--11--01%20GA-0078D4.svg)](docs/features.md#content-understanding--markitdown-ingestion)
[![Agent Framework](https://img.shields.io/badge/Microsoft-Agent%20Framework%201.21-6366f1.svg)](docs/features.md#agent-framework-microsoft-agent-framework-121)
[![i18n](https://img.shields.io/badge/i18n-en%20%C2%B7%20fr-blue.svg)](docs/features.md#internationalisation)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

[English](#overview) · [Français](#en-français)

</div>

## Overview

**PrevaIQ** helps an insurance case handler process a file end to end: document extraction (Azure AI Content Understanding, MarkItDown), analysis by Microsoft Agent Framework agents on Azure OpenAI (GPT-5.4 mini / nano), fraud detection, a recommended next action, and a traceable human decision.

Five workbenches: **Home claims**, **Auto claims**, **Health claims**, **Life & health underwriting** and **Mortgage underwriting**, plus a **Customer 360** view.

> [!NOTE]
> PrevaIQ is a demonstration project, not a Microsoft product. The insurer, customers, policies and claims are fictitious, and the bundled demo dataset is in French (the UI is available in English and French). Review security, compliance and model behaviour before any production use.

## Demo video

https://github.com/user-attachments/assets/4726f612-a105-43ea-95dd-c199a02d75fa

**[Download the video (MP4, 1080p, ~10 MB)](https://github.com/olivMertens/PrevaIq/raw/refs/heads/main/assets/video/PrevaIQ_demo_EN_1080p.mp4)**

Play the demo directly in the embedded GitHub video player above. The demo is in English.
The video is kept in the repository for documentation only and is excluded from deployment images.

## Screenshots

| Dashboard | Claim and next best action |
|---|---|
| ![Home claims dashboard](docs/images/dashboard.png) | ![Claim with AI summary and recommended actions](docs/images/claim.png) |
| **Multi-branch fraud analysis** | **Ask IQ — agent with tools** |
| ![Fraud analysis with risk score and attention items](docs/images/fraud.png) | ![Agent answer grounded on policy wording](docs/images/chat.png) |
| **Customer 360** | **Admin — agent prompts** |
| ![Customer 360 list with risk levels](docs/images/customers.png) | ![Admin panel for agent prompts](docs/images/admin.png) |

## What it does

- **Reliable extraction**: Content Understanding GA for PDFs and images (confidence per field), MarkItDown for office formats, targeted and bounded re-extraction.
- **Bounded agents**: Express, Complete and Fraud Investigation workflows run branches in parallel within time and token budgets — no open-ended agent loop.
- **Fraud detection**: image authenticity, declaration-versus-evidence consistency, policy RAG (pgvector) and optional web checks, merged into a risk score and an SIU recommendation.
- **Assisted decision**: next best action (straight-through, human review, escalation, SIU) with a confidence level and a draft customer message.
- **Human-in-the-loop learning**: handler corrections are embedded and reused as few-shot examples on similar cases.

## Architecture

![PrevaIQ Azure overview](docs/architecture/prevaiq-architecture.png)

```mermaid
flowchart LR
    U["📤 Case documents"] --> R{Routing}
    R -->|"PDF / images"| CU["Content Understanding GA<br/>fields + confidence"]
    R -->|".docx .xlsx .eml .msg"| MD["MarkItDown<br/>structured Markdown"]
    CU --> N["📋 Normalised fields<br/>+ provenance"]
    MD --> N
    N --> A["🤖 Agent Framework agents<br/>GPT-5.4 mini / nano"]
    A <--> RAG[("pgvector<br/>policies + corrections")]
    A --> H["👤 Human decision<br/>+ audit trail"]
    H -.->|correction| RAG
```

More in [docs/architecture.md](docs/architecture.md).

## Quick start

```bash
git clone https://github.com/olivMertens/PrevaIq.git && cd PrevaIq
cp .env.example .env              # set Content Understanding and Azure OpenAI values
uv sync                           # Python dependencies
(cd frontend && npm install)

uv run python -m uvicorn api_server:app --reload --port 8000   # API → http://localhost:8000/docs
(cd frontend && npm run dev)                                    # UI  → http://localhost:3000
```

Deploy to Azure with Bicep or Terraform, then `infra/deploy.ps1`: see [docs/deployment.md](docs/deployment.md).

### Aurora 1.5 weather-risk demo

Aurora 1.5 is a [Microsoft environmental forecasting model](https://www.microsoft.com/en-us/research/blog/aurora-1-5-extending-open-foundation-models-for-weather-and-earth-system-applications/), not a chat model. It
extends Aurora with 22 additional weather variables, hourly lead-time support
and an ensemble mode for probabilistic forecasts. In PrevaIQ it is an optional,
advisory panel shown beneath a resolved claim location. GPT remains responsible
for narrative case analysis; Aurora output is stored with provenance and always
requires human review.

Aurora 1.5 is currently an open model with a Microsoft-published Foundry
batch-client contract. Preview endpoint access is tenant-specific: it is not an
Azure OpenAI deployment and it does not appear in the PrevaIQ Sweden Central
resource's deployable model list. Obtain access and a scoring endpoint from the
Foundry/Aurora preview owner before enabling it, then set:

```dotenv
AURORA_ENABLED=true
AURORA_FOUNDRY_ENDPOINT=https://<tenant-specific-aurora-scoring-endpoint>
AURORA_DEPLOYMENT_NAME=aurora-0.25-v1.5
AURORA_ENSEMBLE_DEPLOYMENT_NAME=aurora-0.25-v1.5-ensemble
AURORA_INITIAL_CONDITION_BLOB_URL=https://<account>.blob.core.windows.net/<container>/initial/current.nc
AURORA_CHANNEL_CONTAINER_URL=https://<account>.blob.core.windows.net/<container>/aurora
AURORA_USE_AZURE_AD=false
# AURORA_ENDPOINT_TOKEN is injected from Key Vault secret aurora-endpoint-key
```

The adapter implements the [official Aurora Foundry client
protocol](https://github.com/microsoft/aurora/blob/main/docs/foundry/notes.md):
it sends task messages to the scoring endpoint and exchanges NetCDF files over
a read/write Blob channel. A coordinate alone is not a valid input. In Azure,
the app identity creates a short-lived delegated SAS for the configured channel;
an explicit `AURORA_BLOB_CHANNEL_SAS_URL` is supported only as a local fallback.
The initial-condition producer remains a separate meteorological ingestion
responsibility and must provide the required two time steps, variables, and
credible source provenance.
The UI action is available on the property-claims location card. It restores
the latest persisted forecast, classifies the weather signal with transparent
thresholds, plots the hourly gust, precipitation, and temperature evidence,
highlights the potential hazard window, and proposes localized case actions
and customer-call talking points. If Aurora is disabled, the panel
is hidden; if it is enabled but incomplete, the panel reports the missing
administrator configuration without exposing credentials.

Tenant administrators can prepare the integration from **Admin > Aurora
weather**. The tab stores only non-secret Azure resource identifiers, tests
the deployment-provided endpoint authentication plus managed-identity
input/channel access, and shows the exact evidence contract agents receive.
Persisted admin configuration overrides the environment resource values while
retaining secret authentication settings; tokens, keys, and SAS query strings
are rejected.

For the `Aurora-v1p5` custom model asset in Foundry, choose **Use this model >
Real-time endpoint**. The current adapter targets that inference environment's
task/Blob scoring protocol; the portal's separate Azure ML batch-endpoint
contract requires a different job-submission adapter.

Aurora remains a research model and must be benchmarked against an accepted
meteorological baseline for the geography and variables used. Do not use the
demo output for autonomous claim denial, payment, underwriting rejection or
operational alerts.

The repository-local
[Aurora skill](.github/skills/msresearch-aurora/SKILL.md) contains the managed
endpoint workflow, input contract, evaluation gate, troubleshooting path, and
upstream Microsoft Research Vibe Kit attribution without vendoring its large
research and sample-data assets.

## Documentation

| Document | Content |
|---|---|
| [Features](docs/features.md) | Use cases per workbench, agents, fraud detection, HITL demo scenario |
| [Architecture](docs/architecture.md) | Diagrams, data flow, bounded orchestration, API choices, evaluation |
| [Deployment](docs/deployment.md) | Bicep / Terraform, Container Apps, identities and roles, private networking, authentication |
| [Configuration](docs/configuration.md) | Environment variables, storage, PostgreSQL RAG, adding a persona, demo data |
| [Development](docs/development.md) | Detailed setup, user guide, project structure, API reference, tests, troubleshooting |
| [Souscr'IA connector](docs/souscria-mcp-connector.md) | Read-only front-office context over MCP |
| [Frontend](frontend/README.md) | Next.js application |

## En français

**PrevaIQ** aide le gestionnaire d'assurance à traiter un dossier de bout en bout : extraction des pièces, analyse par des agents, détection de fraude, action recommandée et décision humaine tracée. L'application couvre les sinistres habitation, auto et santé, la souscription vie-santé et hypothécaire, ainsi qu'une vue Client 360.

C'est un projet de démonstration : l'assureur, les clients et les dossiers sont fictifs. L'interface existe en français et en anglais, et le jeu de données de démo est en français. La documentation détaillée est en anglais, dans le dossier [docs](docs/).

**[Voir la vidéo de démonstration (en anglais)](#demo-video)** · **[Télécharger la vidéo (MP4, 1080p, ~10 Mo)](https://github.com/olivMertens/PrevaIq/raw/refs/heads/main/assets/video/PrevaIQ_demo_EN_1080p.mp4)**

Le lecteur intégré de la section [Demo video](#demo-video) permet de lire la vidéo directement dans ce README. La vidéo est conservée dans le dépôt uniquement pour la documentation et n'est pas incluse dans les images déployées.

## License

[MIT](LICENSE)
