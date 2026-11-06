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

For a new subscription/resource group, the Container Apps cannot be created
until their `latest` images exist in ACR. Use this bootstrap sequence:

```powershell
$subscriptionId = "<subscription-id>"
$tenantId = "<tenant-id>"
$resourceGroup = "rg-prevaiq-demo"
$operatorObjectId = az ad signed-in-user show --query id -o tsv

az login --tenant $tenantId
az account set --subscription $subscriptionId
az group create -n $resourceGroup -l swedencentral
$env:AZURE_SUBSCRIPTION_ID = $subscriptionId
$env:AZURE_TENANT_ID = $tenantId
$env:PREVAIQ_API_KEY = "<32+ characters>"
$env:PREVAIQ_PG_PASSWORD = "<strong PostgreSQL password>"

# 1. Shared resources only: ACR, identity, storage, database, Foundry and ACA environment.
az deployment group create `
  -g $resourceGroup `
  --template-file infra/main.bicep `
  --parameters infra/main.bicepparam `
  deployApps=false `
  adminPrincipalIds="['$operatorObjectId']"

# 2. Build the images before the Container Apps reference them.
$defaultDomain = az containerapp env show `
  -g $resourceGroup `
  -n cae-prevaiq-demo `
  --query properties.defaultDomain -o tsv
$apiFqdn = "ca-api-demo.$defaultDomain"
.\infra\deploy.ps1 `
  -BuildOnly `
  -ApiFqdn $apiFqdn `
  -ResourceGroup $resourceGroup `
  -AcrName acrprevaiqdemo `
  -SubscriptionId $subscriptionId `
  -TenantId $tenantId

# 3. Create the Container Apps after both latest images exist. If Aurora access
#    and current.nc are already ready, add the Aurora parameters shown below to
#    this deployment so Entra is configured only once afterward.
az deployment group create `
  -g $resourceGroup `
  --template-file infra/main.bicep `
  --parameters infra/main.bicepparam `
  deployApps=true `
  adminPrincipalIds="['$operatorObjectId']"

# 4. Configure hosted Entra sign-in. This stores the client secret in Key Vault
#    and performs the first normal image rollout through deploy.ps1.
$adminEmail = "<your-admin-UPN>"
.\infra\set-entra-auth.ps1 `
  -CreateRegistration `
  -SubscriptionId $subscriptionId `
  -TenantId $tenantId `
  -ResourceGroup $resourceGroup `
  -SignInTenant $tenantId `
  -AllowedTenantIds $tenantId `
  -AdminEmails $adminEmail
```

If app-registration creation is disabled in the directory, ask an Entra
administrator for a dedicated Web app registration and pass `-ClientId`
instead of `-CreateRegistration`. Do not run a normal `deploy.ps1` before the
Entra helper: hosted deployment intentionally fails when `ENTRA_TENANT_ID`,
`ENTRA_CLIENT_ID`, or `ENTRA_CLIENT_SECRET` is absent.

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
- When `-AcrName` is omitted and the default registry does not exist (for example a deployment created before the `prevaiq` naming), `deploy.ps1` reuses the registry already attached to the API Container App.
- `BRAND_NAME` is baked into images with `--build-arg`; never set it through `az containerapp update --set-env-vars`.
- The hosted demo uses Microsoft Entra ID only. Configure `ENTRA_TENANT_ID`, `ENTRA_CLIENT_ID`, and `ENTRA_CLIENT_SECRET` with `infra/set-entra-auth.ps1` before deployment. `deploy.ps1` checks that they exist before builds, preserves session signing, and removes old local-account variables `AUTH_USER*` / `APPSETTING_AUTH_USER*` without recreating them.
- The username/password form is for development only. Enable it explicitly with `LOCAL_AUTH_ENABLED=true` and `npm run dev`, and configure `AUTH_USER_*` in `frontend/.env.local`. In production, these accounts and their old sessions are rejected even if the flag is enabled; missing Entra configuration never makes the site public.
- Web IQ requires `infra/set-webiq-secret.ps1`, then `webIqSecretEnabled=true` in Bicep or `webiq_secret_enabled = true` in Terraform so later applies keep the Key Vault reference. The script prompts for the key with hidden input, discovers the Key Vault and identity already used by the API, and restarts the API revision when `WEBIQ_API_KEY` is already mapped. Never paste the key into chat, source, or frontend configuration.
- Web IQ runs through Microsoft Agent Framework MCP tools, which need `mcp>=2.2,<3` (MCP v2 client API) and `tenacity`; both are pinned in `pyproject.toml` and checked during the backend image build.
- ACR Premium for the build agent pool (`deploy.ps1 -AgentPool`) requires Bicep parameter `acrSku` or Terraform variable `acr_sku`; the default is `Basic`.
- Terraform's first `apply` starts Container Apps with bootstrap image `mcr.microsoft.com/k8se/quickstart`. `deploy.ps1` later publishes real images; Terraform ignores those image changes and frontend `AUTH_*` variables.
- Terraform state contains secrets such as the API key and PostgreSQL password in clear text. Use a remote backend such as `azurerm` instead of a personal workstation. `*.tfstate` and `*.tfvars` are ignored by git.
- Do not apply both IaC tools to the same resource group because names match and states are independent. To switch tools, use a new resource group or `terraform import`.
- The GitHub Actions workflow `deploy.yml` targets the same resources and requires OIDC secrets `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and `AZURE_SUBSCRIPTION_ID`, plus the repository variable `AZURE_DEPLOY_ENABLED=true`; without it the deploy job is skipped.
- RAG policy PDFs are not included. Put insurer policy PDFs in `assets/pdf/` before running `scripts/index_pdf_policies.py`.
- `assets/video/` contains README demo videos only: they are versioned in Git but excluded from deployment. The root `.dockerignore` excludes this folder, `deploy.ps1` stages only `assets/pdf/` from the assets tree, and the frontend build context is limited to `frontend/`. The in-app demo guide still uses `assets/demo-prevaiq/`; its document selections are unchanged.

## Aurora 1.5 preview deployment and smoke test

Aurora is not one of the Azure OpenAI deployments created by this template.
The `Aurora-v1p5` custom model asset shown in Foundry can be used directly in
the subscription that owns the project. Open the asset, select **Use this
model > Real-time endpoint**, and deploy the published inference environment
on supported GPU compute. Record the managed online endpoint scoring URI; that
URI is `AURORA_FOUNDRY_ENDPOINT`.

The PrevaIQ adapter uses the Aurora task/Blob protocol exposed by the real-time
inference environment. The separate **Batch endpoint** wizard creates an Azure
ML batch-job contract and is not interchangeable with this adapter. A future
batch-job integration would submit and poll Azure ML jobs rather than POST
Aurora task messages to a scoring URI.

Before creating billable compute, confirm the portal shows the expected target:

- tenant and subscription that host PrevaIQ;
- Foundry project / Azure ML workspace containing `Aurora-v1p5`;
- endpoint region and GPU family with sufficient quota;
- the endpoint authentication type shown in the portal;
- minimum instance count appropriate for the demo budget.

If the model asset is only visible through a shared registry reference, the
deployment wizard copies/registers the selected version into the target
workspace as part of endpoint deployment. If the wizard reports unavailable
compute, request quota in the endpoint region before continuing.

Aurora also requires a current NetCDF initial condition; latitude and longitude
alone are not model input. Follow the [official Aurora 1.5
example](https://microsoft.github.io/aurora/example_v1p5.html) to construct a
`Batch`, write it with `Batch.to_netcdf`, and upload it to the PrevaIQ data
container:

```powershell
$storageAccount = az storage account list -g $resourceGroup `
  --query "[?starts_with(name, 'stprevaiq')].name | [0]" -o tsv
az storage blob upload `
  --auth-mode login `
  --account-name $storageAccount `
  --container-name prevaiq-data `
  --name aurora/initial/current.nc `
  --file .tmp/current.nc `
  --overwrite
$initialConditionUrl = "https://$storageAccount.blob.core.windows.net/prevaiq-data/aurora/initial/current.nc"
```

For an Entra-authenticated Azure Machine Learning managed online endpoint, grant
the PrevaIQ managed identity permission to score that specific endpoint. The
`AzureML Data Scientist` role includes the required
`Microsoft.MachineLearningServices/workspaces/onlineEndpoints/score/action`;
scope the assignment to the endpoint rather than the whole subscription:

```powershell
$identityPrincipalId = az identity show -g $resourceGroup -n id-prevaiq-demo `
  --query principalId -o tsv
$auroraEndpointResourceId = az ml online-endpoint show `
  -g "<aurora-endpoint-resource-group>" `
  -w "<aurora-workspace>" `
  -n "<aurora-endpoint-name>" `
  --query id -o tsv
az role assignment create `
  --assignee-object-id $identityPrincipalId `
  --assignee-principal-type ServicePrincipal `
  --role "AzureML Data Scientist" `
  --scope $auroraEndpointResourceId
```

The endpoint shown for this demo uses **Key** authentication. Store its primary
or secondary key without placing it in source, shell history, chat, or the admin
form:

```powershell
.\infra\set-aurora-endpoint-secret.ps1 `
  -SubscriptionId $subscriptionId `
  -TenantId $tenantId `
  -ResourceGroup $resourceGroup
```

The script uses hidden input, writes `aurora-endpoint-key` to the existing
PrevaIQ Key Vault through ARM, and creates the Container App Key Vault
reference. Bicep parameter `auroraEndpointKeySecretEnabled` and Terraform
variable `aurora_endpoint_key_secret_enabled` control whether
`AURORA_ENDPOINT_TOKEN` is mapped and `AURORA_USE_AZURE_AD` is set to `false`.
Blob input and task-channel access continue to use managed identity.

Set `auroraEndpointExpiresAt` (Bicep) or `aurora_endpoint_expires_at`
(Terraform) to the temporary allocation's absolute ISO 8601 deadline. The
admin and claim UIs count down to this timestamp, warn below 48 and 12 hours,
and stop new forecast submissions after expiry while retaining existing
evidence. When deploying images without reapplying IaC, pass the same value to
`deploy.ps1 -AuroraEndpointExpiresAt`.

Reapply Bicep to enable the adapter. The Container App identity already has
Storage Blob Data Contributor and generates a short-lived delegated SAS for the
`prevaiq-data/aurora` exchange folder:

```powershell
$auroraEndpoint = "https://<tenant-specific-aurora-scoring-endpoint>"
az deployment group what-if `
  -g $resourceGroup `
  --template-file infra/main.bicep `
  --parameters infra/main.bicepparam `
  deployApps=true `
  auroraEnabled=true `
  auroraFoundryEndpoint=$auroraEndpoint `
  auroraInitialConditionBlobUrl=$initialConditionUrl `
  auroraEndpointKeySecretEnabled=true `
  adminPrincipalIds="['$operatorObjectId']"

az deployment group create `
  -g $resourceGroup `
  --template-file infra/main.bicep `
  --parameters infra/main.bicepparam `
  deployApps=true `
  auroraEnabled=true `
  auroraFoundryEndpoint=$auroraEndpoint `
  auroraInitialConditionBlobUrl=$initialConditionUrl `
  auroraEndpointKeySecretEnabled=true `
  adminPrincipalIds="['$operatorObjectId']"

# A Bicep reapply owns the complete Container App template, so restore hosted
# Entra configuration and roll out through the helper rather than calling
# deploy.ps1 directly. Reusing -CreateRegistration finds the dedicated app and
# appends a fresh six-month credential.
.\infra\set-entra-auth.ps1 `
  -CreateRegistration `
  -SubscriptionId $subscriptionId `
  -TenantId $tenantId `
  -ResourceGroup $resourceGroup `
  -SignInTenant $tenantId `
  -AllowedTenantIds $tenantId `
  -AdminEmails $adminEmail
```

Alternatively, deploy the identity and storage permissions with Aurora disabled, then sign in with
an administrator account and open **Admin > Aurora weather**. Enter the managed endpoint, model
identifiers, private initial-condition Blob URL, task-channel container URL, and a 6-12 hour demo
horizon. Save the configuration, enable Aurora, and run **Test readiness**. The live test verifies
the deployment-provided endpoint authentication, endpoint reachability, the full NetCDF input
contract, and managed-identity delegated Blob-channel access.

This admin record contains no credentials and takes precedence over the resource settings supplied
by Bicep or Terraform. Tokens, keys, SAS URLs, and URL query strings are rejected. Keep infrastructure
defaults in Bicep and Terraform aligned even when an operator uses the admin override.

Run local contract tests, then a real six-hour forecast through the deployed
API. Restore a property-claims demo case in the UI first if the environment has
no suitable dossier:

```powershell
uv run python -m pytest tests/test_aurora.py tests/test_aurora_admin.py -q

$apiUrl = az containerapp show -g $resourceGroup -n ca-api-demo `
  --query "'https://' + properties.configuration.ingress.fqdn" -o tsv
.\scripts\test_aurora_endpoint.ps1 `
  -ApiBaseUrl $apiUrl `
  -Latitude 46.2044 `
  -Longitude 6.1432 `
  -HorizonHours 6
```

The smoke test checks readiness, submits the forecast with `X-API-Key`,
confirms forecast points and weather metrics, and verifies that the same Aurora
task was persisted with the dossier. Use `-Ensemble` only after the
deterministic path succeeds. Aurora remains advisory and requires expert review.

In the customer-facing property-claim workflow, the persisted Aurora result is
converted into bounded decision support: weather severity, a potential hazard
window, an hourly gust/precipitation/temperature evidence timeline, case-triage
actions, and localized customer-call talking points. These
signals can prioritize outreach and evidence collection, but they never approve,
deny, price, or pay a claim.

## Environment-specific script inputs

The deployment scripts read environment-specific values from environment variables, with parameters available for overrides.

- `infra/deploy.ps1`, `infra/set-webiq-secret.ps1`, `infra/set-aurora-endpoint-secret.ps1`, and `infra/set-entra-auth.ps1` read `AZURE_SUBSCRIPTION_ID` and `AZURE_TENANT_ID`. These are optional and default to the current `az account` context.
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
| Operators (`adminPrincipalIds` / `admin_principal_ids`) | Foundry, Key Vault, Storage | `Cognitive Services User`, `Key Vault Secrets Officer`, `Storage Blob Data Contributor` | `deploy.ps1` and maintenance scripts |

- Creating role assignments requires Owner, or Contributor plus User Access Administrator, on the resource group. Owner and Contributor do not include data-plane access. Add the operator object ID from `az ad signed-in-user show --query id -o tsv` to `adminPrincipalIds` in `main.bicepparam` or `admin_principal_ids` in `terraform.tfvars`.
- Web IQ product access is separate from Azure RBAC. A successful Microsoft sign-in followed by "You don't have access to this" usually means the signed-in account is in the wrong tenant or lacks Web IQ profile/tool entitlement. Confirm access to Web IQ Profile Management and that the account's allowed service list includes `web`, `news`, and `browse`; Azure Owner/Contributor and Key Vault roles do not grant that entitlement.
- Default networking uses public endpoints protected by Entra ID and RBAC. PostgreSQL allows Azure services through `AllowAzureServices`, which Container Apps need until they run in a VNet.
- Private networking is enabled the same way in both tools: `privateNetworkingEnabled = true` for Bicep or `private_networking_enabled = true` for Terraform. It creates a VNet, places the Container Apps environment in it, adds private endpoints and private DNS zones for Storage, Key Vault, AI Search, and Foundry, and switches PostgreSQL to private access without `AllowAzureServices`. Public access to these services is closed except for operator public IPs in `adminIpRanges` / `admin_ip_ranges`, which are needed because `deploy.ps1` calls the Foundry data plane from an operator workstation. `set-webiq-secret.ps1` writes the Web IQ key through Azure Resource Manager (`Microsoft.KeyVault/vaults/secrets`), so it works with a private Key Vault and needs Owner, Contributor, or Key Vault Contributor on the vault rather than a data-plane role. ACR remains public and protected by RBAC for ACR Tasks builds.
- With private networking, PostgreSQL is reachable only from the VNet. RAG scripts such as `scripts/setup_postgresql_rag.py` and `scripts/index_pdf_policies.py` need network access to the VNet through VPN, VM, or container. Foundry project connections to Storage and AI Search use trusted Azure services access, valid with restricted public access when `admin_ip_ranges` is set.

### Existing deployment under private-only governance policies

Governance policies such as MCAPS `StorageAccount_PublicNetwork_Modify` and `KeyVault_PublicNetwork_Modify` can force `publicNetworkAccess=Disabled` on an existing public-mode deployment. The API then returns `AuthorizationFailure` when it lists or uploads cases, and Key Vault references can no longer be resolved from a new environment. Do not re-enable public access or create policy exemptions; connect the data plane privately instead:

```powershell
.\infra\enable-private-data-access.ps1                    # VNet, private DNS, private endpoints, VNet environment (no downtime)
.\infra\enable-private-data-access.ps1 -MigrateWorkloads  # recreate the jobs and the API in that environment
.\infra\deploy.ps1                                        # rebuild the backend and the frontend against the new API URL
```

- The script mirrors the private-networking layout above (`vnet-<prefix>`, `snet-apps`, `snet-private-endpoints`, `privatelink.blob.core.windows.net`, `privatelink.vaultcore.azure.net`, `pe-storage-<prefix>`, `pe-vault-<prefix>`, `cae-<prefix>`) and discovers the Storage account, Key Vault, PostgreSQL server, jobs, and Log Analytics workspace from the API configuration. Every step is idempotent.
- A Container Apps environment cannot gain VNet integration and an app cannot change environment, so `-MigrateWorkloads` deletes and recreates the API and the jobs of its environment with the same name, identity, registries, secrets, variables, ingress, and scale. Plan for a short API interruption. The definition, including secret values, is kept under the gitignored `.tmp/private-data-access/` folder until the workload is provisioned again.
- The frontend keeps its environment, public URL, and Entra redirect URIs; only the API URL baked into the frontend changes, which `deploy.ps1` handles. PostgreSQL stays on public access with `AllowAzureServices`; the script starts it if governance automation stopped it, and the API reconnects automatically within 30 seconds once it is available.
- The VNet environment adds private endpoints, private DNS zones, and an environment-managed load balancer with public IPs to the monthly cost.

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
