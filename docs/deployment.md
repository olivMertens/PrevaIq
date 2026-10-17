# Azure deployment

PrevaIQ deploys to a single Azure environment, using the default Container Apps hostnames unless custom DNS is configured. Authenticate and select the target subscription before deploying:

```powershell
az login --tenant <tenant-id>
az account set --subscription <subscription-id>

# Shared by both infrastructure tools: resource group and secrets.
az group create -n rg-prevaiq-demo -l swedencentral
$env:PREVAIQ_API_KEY = "<32+ characters>"; $env:PREVAIQ_PG_PASSWORD = "<password>"
```

The tenant and subscription can also be provided with `AZURE_TENANT_ID` and `AZURE_SUBSCRIPTION_ID`.

## Infrastructure

`infra/main.bicep` and `infra/terraform/` describe the same resources, names, and optional private network. Use exactly one tool per environment.

| | Option A: Bicep | Option B: Terraform |
|---|---|---|
| Code | `infra/main.bicep` and `infra/main.bicepparam` | `infra/terraform/` |
| Prerequisites | Azure CLI | Azure CLI and [Terraform](https://developer.hashicorp.com/terraform/install) >= 1.9 |
| Secrets | `PREVAIQ_API_KEY`, `PREVAIQ_PG_PASSWORD`, read by `main.bicepparam` | Same values through `TF_VAR_api_key`, `TF_VAR_pg_admin_password` |
| Preview | `az deployment group what-if` | `terraform plan` |
| State | Azure ARM deployments | Terraform state file, local by default |
| Private networking | `privateNetworkingEnabled = true` in `main.bicepparam` | `private_networking_enabled = true` |

### Bicep

```powershell
az deployment group what-if -g rg-prevaiq-demo --template-file infra/main.bicep --parameters infra/main.bicepparam   # optional
az deployment group create  -g rg-prevaiq-demo --template-file infra/main.bicep --parameters infra/main.bicepparam
```

### Terraform

```powershell
$env:TF_VAR_api_key = $env:PREVAIQ_API_KEY; $env:TF_VAR_pg_admin_password = $env:PREVAIQ_PG_PASSWORD
terraform -chdir=infra/terraform init
terraform -chdir=infra/terraform plan      # optional
terraform -chdir=infra/terraform apply
```

Defaults in `infra/terraform/variables.tf` target the demo environment. To override them, copy `infra/terraform/terraform.tfvars.example` to `terraform.tfvars`, which is ignored by git. On bash, run `./infra/deploy.sh --infra --iac terraform`, or `--full` to also build images and update apps. Bicep is the default IaC option.

## Images and Container Apps

Image deployment is identical for Bicep and Terraform.

```powershell
.\infra\deploy.ps1                 # backend + frontend, BRAND_NAME=PrevaIQ
.\infra\deploy.ps1 -SkipFrontend   # backend only
.\infra\deploy.ps1 -SkipBackend    # frontend only
```

- Created resources use the same defaults with Bicep and Terraform: `environment=demo`, `projectName` / `project_name = prevaiq`, ACR `acrprevaiqdemo`, Container Apps `ca-api-demo` and `ca-frontend-demo`, images `prevaiq-api` and `prevaiq-frontend`, Foundry `ai-prevaiq-foundry`, project `ai-prevaiq-project`, and deployments `gpt-5.4-mini`, `gpt-5.4-nano`, `text-embedding-3-large`, and `text-embedding-3-small`.
- `BRAND_NAME` is baked into images with `--build-arg`; never set it through `az containerapp update --set-env-vars`.
- The hosted demo uses Microsoft Entra ID only. Configure `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, and `ENTRA_CLIENT_SECRET` with `infra/set-entra-auth.ps1` before deployment. `deploy.ps1` checks that they exist before builds, preserves session signing, and removes old local-account variables `AUTH_USER*` / `APPSETTING_AUTH_USER*` without recreating them.
- The username/password form is for development only. Enable it explicitly with `LOCAL_AUTH_ENABLED=true` and `npm run dev`, and configure `AUTH_USER_*` in `frontend/.env.local`. In production, these accounts and their old sessions are rejected even if the flag is enabled; missing Entra configuration never makes the site public.
- Web IQ requires `infra/set-webiq-secret.ps1`, then `webIqSecretEnabled=true` in Bicep or `webiq_secret_enabled = true` in Terraform so later applies keep the Key Vault reference.
- ACR Premium for the build agent pool (`deploy.ps1 -AgentPool`) requires Bicep parameter `acrSku` or Terraform variable `acr_sku`; the default is `Basic`.
- Terraform's first `apply` starts Container Apps with bootstrap image `mcr.microsoft.com/k8se/quickstart`. `deploy.ps1` later publishes real images; Terraform ignores those image changes and frontend `AUTH_*` variables.
- Terraform state contains secrets such as the API key and PostgreSQL password in clear text. Use a remote backend such as `azurerm` instead of a personal workstation. `*.tfstate` and `*.tfvars` are ignored by git.
- Do not apply both IaC tools to the same resource group because names match and states are independent. To switch tools, use a new resource group or `terraform import`.
- The GitHub Actions workflow `deploy.yml` targets the same resources and requires OIDC secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and `AZURE_SUBSCRIPTION_ID`, plus the repository variable `AZURE_DEPLOY_ENABLED=true`; without it the deploy job is skipped.
- RAG policy PDFs are not included. Put insurer policy PDFs in `assets/pdf/` before running `scripts/index_pdf_policies.py`.
- `assets/video/` contains README demo videos only: they are versioned in Git but excluded from deployment. The root `.dockerignore` excludes this folder, `deploy.ps1` stages only `assets/pdf/` from the assets tree, and the frontend build context is limited to `frontend/`. The in-app demo guide still uses `assets/demo-prevaiq/`; its document selections are unchanged.

## Environment-specific script inputs

The deployment scripts read environment-specific values from environment variables, with parameters available for overrides.

- `infra/deploy.ps1`, `infra/set-webiq-secret.ps1`, and `infra/set-entra-auth.ps1` read `AZURE_SUBSCRIPTION_ID` and `AZURE_TENANT_ID`. These are optional and default to the current `az account` context.
- `infra/deploy.ps1` also reads optional `PREVAIQ_KNOWN_API_FQDN` and `PREVAIQ_KNOWN_FE_FQDN` to detect DNS changes after the first deployment.
- `infra/set-entra-auth.ps1` requires `ENTRA_CLIENT_ID` and `PREVAIQ_ADMIN_EMAILS`. `PREVAIQ_ACCESS_REQUEST_EMAIL` is optional and defaults to the first admin email. `PREVAIQ_ALLOWED_EMAILS` pre-approves API access. `PREVAIQ_ENTRA_SECRET_TFVARS` can point to a gitignored tfvars file containing `entra_client_secret`; otherwise the client secret is prompted with hidden input.

## Identities, roles, and networking

The apps access Azure services through managed identity. Shared Storage keys, Foundry keys, and the ACR admin account are disabled. Exceptions are PostgreSQL, which uses a password stored as an ACA secret, and AI Search, where an API key is still accepted for `scripts/index_corrections_search.py`.

| Identity | Resource | Role | Use |
|---|---|---|---|
| App managed identity (`id-prevaiq-demo`) | ACR | `AcrPull` | Pull images |
| | Key Vault | `Key Vault Secrets User` | Key Vault reference `webiq-api-key` |
| | Storage | `Storage Blob Data Contributor` | Documents and data |
| | Foundry | `Cognitive Services OpenAI User`, `Cognitive Services User` | Models, Content Understanding, Agent Service |
| | AI Search | `Search Index Data Contributor`, `Search Service Contributor` | `corrections` index |
| Foundry project identity | Storage | `Storage Blob Data Contributor` | `prevaiq-blob` connection with Entra auth |
| | AI Search | `Search Index Data Contributor`, `Search Service Contributor` | `prevaiq-search` connection with Entra auth |
| Operators (`adminPrincipalIds` / `admin_principal_ids`) | Foundry, Key Vault, Storage | `Cognitive Services User`, `Key Vault Secrets Officer`, `Storage Blob Data Contributor` | `deploy.ps1`, `set-webiq-secret.ps1`, and maintenance scripts |

- Creating role assignments requires Owner, or Contributor plus User Access Administrator, on the resource group. Owner and Contributor do not include data-plane access. Add the operator object ID from `az ad signed-in-user show --query id -o tsv` to `adminPrincipalIds` in `main.bicepparam` or `admin_principal_ids` in `terraform.tfvars`.
- Default networking uses public endpoints protected by Entra ID and RBAC. PostgreSQL allows Azure services through `AllowAzureServices`, which Container Apps need until they run in a VNet.
- Private networking is enabled the same way in both tools: `privateNetworkingEnabled = true` for Bicep or `private_networking_enabled = true` for Terraform. It creates a VNet, places the Container Apps environment in it, adds private endpoints and private DNS zones for Storage, Key Vault, AI Search, and Foundry, and switches PostgreSQL to private access without `AllowAzureServices`. Public access to these services is closed except for operator public IPs in `adminIpRanges` / `admin_ip_ranges`, which are needed because `deploy.ps1` and `set-webiq-secret.ps1` call the Foundry and Key Vault data planes from an operator workstation. ACR remains public and protected by RBAC for ACR Tasks builds.
- With private networking, PostgreSQL is reachable only from the VNet. RAG scripts such as `scripts/setup_postgresql_rag.py` and `scripts/index_pdf_policies.py` need network access to the VNet through VPN, VM, or container. Foundry project connections to Storage and AI Search use trusted Azure services access, valid with restricted public access when `admin_ip_ranges` is set.

## API authentication

The backend API supports optional API key authentication through the `X-API-Key` header.

### Setup

Set the `API_KEY` environment variable on both backend and frontend:

```bash
# In your .env file (must be at least 32 characters)
API_KEY=your-secret-api-key-at-least-32-characters-long
```

### Behaviour

| `API_KEY` env var | Result |
|-------------------|--------|
| Not set | All endpoints are open in development mode. A warning is logged at startup. |
| Set | Every request must include an `X-API-Key` header with the matching key. Invalid or missing keys receive `401 Unauthorized`. |

### How it works

- The frontend Next.js proxy injects the `X-API-Key` header server-side. The key is never exposed to the browser.
- Direct API consumers such as scripts and Postman must include the header manually:

```bash
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/applications
```

### Production deployment

When deploying to Azure Container Apps, `infra/main.bicep` or `infra/terraform/` stores `API_KEY` as the ACA secret `api-key`. Bicep reads parameter `apiKey` from `PREVAIQ_API_KEY`; Terraform uses variable `api_key`. The secret is exposed to both backend and frontend containers.
