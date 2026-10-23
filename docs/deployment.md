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
- `infra/set-entra-auth.ps1` requires `ENTRA_CLIENT_ID` (or `-CreateRegistration`) and `PREVAIQ_ADMIN_EMAILS`. `PREVAIQ_ACCESS_REQUEST_EMAIL` defaults to the first admin email. `PREVAIQ_ALLOWED_EMAILS` pre-approves API access. `PREVAIQ_ENTRA_SECRET_TFVARS` can point to a gitignored tfvars file containing `entra_client_secret`; otherwise the client secret is prompted with hidden input. With `-CreateRegistration`, a six-month credential is generated and stored in Key Vault without printing it. The script rolls out both images through `deploy.ps1`; it no longer updates app revisions independently.

### Microsoft colleague access and administrator email

Use a **dedicated** organizational Entra web registration. Do not convert a registration shared with other applications. Set `ENTRA_TENANT_ID=organizations` and `ENTRA_ALLOWED_TENANT_IDS` to a comma-separated list of explicitly verified tenants: the Microsoft corporate tenant and, when technical demo accounts are required, the existing sandbox tenant. Resolve the corporate tenant from its official OpenID discovery document and the sandbox tenant from the verified Azure directory context, not from an applicant's email suffix. `AZURE_TENANT_ID` remains the Azure subscription/registration-owning tenant; `PREVAIQ_ENTRA_AUTHORITY` is the separate sign-in authority.

The dedicated enterprise app must not require prior sandbox user assignment. Microsoft corporate consent and Conditional Access policies still apply: external applications may require corporate administrator consent. Changing the demo cannot bypass those policies. Personal Microsoft accounts and tenants outside the explicit allowlist are rejected before requests or sessions are created.

After successful eligible authentication, PrevaIQ stores a pending request. Only an administrator explicitly listed in `ACCESS_ADMIN_EMAILS` can approve or refuse it under **Administration > Access requests**. Account-name prefixes do not grant administration. Preapproval still requires an eligible tenant at sign-in.

#### Technical administrator and user accounts

There are two independent gates: **tenant eligibility**, then **application role/access**.
An approved request does not override the tenant restriction. An account whose name contains
`admin` is not automatically an Entra administrator.

1. Verify the sandbox directory and the exact technical account UPNs in Entra.
2. Preserve the corporate tenant in `ENTRA_ALLOWED_TENANT_IDS` and append the verified
   sandbox tenant. Do not replace the allowlist with `common` or an unrestricted value.
3. Preserve the existing administrator addresses in `ACCESS_ADMIN_EMAILS` and append
   only the exact technical administrator UPN. This account can reach Administration
   without waiting for someone else to approve its own request.
4. Preauthorize each technical user in **Administration > Access requests**, or through
   the API-key-protected internal `/authorize` endpoint. Approval grants user access only.
5. Roll out configuration with `infra\deploy.ps1 -FrontendAccessSettings` (or the setup
   helper's `-AllowedTenantIds` and `-AdminEmails`); do not manually update Container Apps.
6. Sign in again using the full UPN, preferably in a private browser window to avoid
   reusing a different Microsoft account. Conditional Access/MFA requirements still apply.

Other accounts in an admitted tenant remain pending until explicitly approved.
Keep environment-specific tenant IDs, technical account inventories and credentials out
of committed configuration. Do not re-enable local password authentication on the hosted demo.

Enable `accessEmailEnabled` (Bicep) / `access_email_enabled` (Terraform), with matching `accessRequestEmail` / `access_request_email` and `accessAdminUrl` / `access_admin_url`. Both IaC tools define the same Europe-resident ACS Email service, Azure-managed sender domain, dedicated Communication Services resource and resource-scoped custom sender role. Authentication uses managed identity; the app neither reads service keys nor accesses the administrator's mailbox. ACS requires the service write permission for Entra-authenticated submission; the custom role excludes key access, deletion and role management. Local-auth disabling is not exposed by the selected ACS resource API.

For the existing Bicep-managed deployment, the standalone module can provision only these new resources without reapplying unrelated resources:

```powershell
$principal = az identity show -g <resource-group> -n <actual-app-identity> --query principalId -o tsv
az deployment group create -g <resource-group> -n prevaiq-access-email `
  --template-file infra\access-email.bicep --parameters identityPrincipalId=$principal
```

Use the deployment's `endpoint` and `senderAddress` outputs for `ACCESS_EMAIL_ENDPOINT` and `ACCESS_EMAIL_SENDER`, plus `ACCESS_REQUEST_EMAIL` and `ACCESS_ADMIN_URL` on the backend. Supply these as the `-EmailSettings` hashtable to `set-entra-auth.ps1` so configuration and images roll out together through `deploy.ps1`. Override `-IdentityName` / `-KeyVaultName` when the deployed environment still uses legacy resource names. Keep the feature enabled with the same values on later full infrastructure applies; do not apply Terraform to Bicep-managed resources.

Repeated pending sign-ins retain the original request and do not send another email. Blob leases serialize mutations across replicas; local development uses a file lock. The dashboard is the source of truth even when email submission fails, and approve/refuse remain available. Historical records load without notification metadata. `submitted` means ACS accepted the message, **not** that it reached the inbox. `sending` can indicate an interrupted process; inspect logs and use the dashboard rather than repeatedly signing in to resend.

Request emails use simple branded HTML with a **Review access requests** button and the administrator's contact address, plus a plain-text fallback. Approving or pre-authorizing an address persists the approval first, then sends an **access approved** email to that applicant with an **Open PrevaIQ** login button. The administrator configured in `ACCESS_REQUEST_EMAIL` is copied and used as the reply-to/contact address. No additional email credentials or environment variables are required. Repeating the same approval or preauthorization does not resend; a later refusal followed by a new approval is a new decision. Approval-notification status and timestamp appear separately from the original administrator request email in the access dashboard. Email failure never revokes an approved account. Email buttons open the application; they do not perform unauthenticated approval actions.

No email can be triggered by a sign-in blocked on Microsoft's page before the application callback. The manual email link remains available for that case. Verify actual mailbox receipt and a real colleague's sign-in after deployment; never report a send API acceptance as confirmed delivery.

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
