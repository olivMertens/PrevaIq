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
