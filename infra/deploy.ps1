<#
.SYNOPSIS
    PrevaIQ — Full deployment script (ACR build + ACA update)
    Builds Docker images, pushes to ACR, updates Azure Container Apps.

.DESCRIPTION
    Minimal, fast deployment:
    1. Build backend image in ACR (remote build via az acr build)
    2. Build frontend image in ACR (remote build)
    3. Update both ACA container apps with new image tags
    4. Verify health checks
    5. Print deployment URLs

    Brand:
    - BRAND_NAME is baked into the Docker image via --build-arg (never set as ACA env var)
    - Single brand (PrevaIQ) served on the default host; images are also tagged "latest"

.PARAMETER SkipBackend
    Skip backend image build (use existing latest image)

.PARAMETER SkipFrontend
    Skip frontend image build (use existing latest image)

.PARAMETER Tag
    Override image tag (default: git short SHA)

.PARAMETER BrandName
    Brand identity baked into the Docker images (default: PrevaIQ).

.PARAMETER BuildOnly
    First provisioning: build and push both images (tag + latest) without touching the
    Container Apps, which do not exist yet. Requires -ApiFqdn for the frontend bundle.

.PARAMETER ApiFqdn
    API FQDN baked into the frontend (default: read from the API Container App).

.EXAMPLE
    .\infra\deploy.ps1                                         # Full deploy (PrevaIQ)
    .\infra\deploy.ps1 -SkipFrontend                           # Backend only
    .\infra\deploy.ps1 -SkipBackend                            # Frontend only
    .\infra\deploy.ps1 -Tag "v1.0"                             # Custom tag
#>

param(
    [switch]$SkipBackend,
    [switch]$SkipFrontend,
    [string]$Tag = "",
    [string]$BrandName = "PrevaIQ",
    [string]$ResourceGroup = "rg-prevaiq-demo",
    [string]$AcrName = "acrprevaiqdemo",
    [string]$ApiAppName = "ca-api-demo",
    [string]$FrontendAppName = "ca-frontend-demo",
    [string]$SubscriptionId = $env:AZURE_SUBSCRIPTION_ID,
    [string]$TenantId = $env:AZURE_TENANT_ID,
    [string]$OpenAIAccountName = "",
    [string]$PrimaryDeployment = "gpt-5.4-mini",
    [string]$ChatDeployment = "",
    [string]$NanoDeployment = "gpt-5.4-nano",
    [string]$FraudDeployment = "",
    [ValidateSet("low", "medium", "high")][string]$ReasoningEffort = "low",
    [switch]$PreflightOnly,
    [string]$AgentPool = "",
    [string]$ChangedSince = "",
    [switch]$BuildOnly,
    [string]$ApiFqdn = ""
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$ProgressPreference = "SilentlyContinue"

# ─────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────
$RG            = $ResourceGroup
$ACR           = $AcrName
$API_APP       = $ApiAppName
$FRONTEND_APP  = $FrontendAppName
$API_IMAGE     = "prevaiq-api"
$FE_IMAGE      = "prevaiq-frontend"
$TAGS          = @{ SecurityControl = "ignore"; CostControl = "ignore" }

function Copy-DirectoryToStage {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    robocopy $Source $Destination /E /NFL /NDL /NJH /NJS /NP | Out-Null
    $copyExitCode = $LASTEXITCODE
    if ($copyExitCode -ge 8) {
        throw "robocopy failed from '$Source' to '$Destination' with exit code $copyExitCode"
    }
    $global:LASTEXITCODE = 0
}

if (-not $Tag) {
    $Tag = (git rev-parse --short HEAD 2>$null)
    if (-not $Tag) { $Tag = "latest" }
}

$ACR_SERVER = "$ACR.azurecr.io"

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " PrevaIQ — Azure Deployment" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " Resource Group : $RG"
Write-Host " ACR            : $ACR_SERVER"
Write-Host " Image Tag      : $Tag"
Write-Host " Backend        : $(if ($SkipBackend) { 'SKIP' } else { 'BUILD' })"
Write-Host " Frontend       : $(if ($SkipFrontend) { 'SKIP' } else { 'BUILD' })"
Write-Host " Brand          : $BrandName"
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# ─────────────────────────────────────────────────────────────
# Verify Azure login
# ─────────────────────────────────────────────────────────────
Write-Host ">>> Checking Azure login..." -ForegroundColor Yellow
$currentUpn = az account show --query "user.name" -o tsv 2>$null
if (-not $currentUpn) {
    if (-not $TenantId) { throw "Not authenticated. Log into the intended Azure tenant or supply -TenantId." }
    az login --tenant $TenantId --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw "Azure login failed." }
}
$account = az account show --query "name" -o tsv 2>$null
if ($SubscriptionId) {
    az account set --subscription $SubscriptionId
    if ($LASTEXITCODE -ne 0) { throw "Cannot select subscription $SubscriptionId." }
    $SUBSCRIPTION_ID = $SubscriptionId
    $account = az account show --query "name" -o tsv 2>$null
} else {
    $SUBSCRIPTION_ID = az account show --query "id" -o tsv 2>$null
}
Write-Host "    Subscription: $account" -ForegroundColor Green

if ($TenantId) {
    $actualTenant = az account show --query tenantId -o tsv
    if ($LASTEXITCODE -ne 0 -or $actualTenant -ne $TenantId) { throw "Azure tenant does not match -TenantId." }
}

$backendModelEnvVarArgs = @()
$frontendAuthEnv = @()
if (-not $SkipFrontend -and -not $BuildOnly) {
    $frontendEnvJson = az containerapp show -n $FRONTEND_APP -g $RG --subscription $SUBSCRIPTION_ID `
        --query "properties.template.containers[0].env[].{name:name,value:value,secretRef:secretRef}" -o json
    if ($LASTEXITCODE -ne 0) { throw "Cannot read frontend authentication configuration." }
    $frontendAuthEnv = @($frontendEnvJson | ConvertFrom-Json)
    foreach ($name in @("ENTRA_TENANT_ID", "ENTRA_CLIENT_ID", "ENTRA_CLIENT_SECRET")) {
        $entry = @($frontendAuthEnv | Where-Object { $_.name -eq $name })
        if ($entry.Count -ne 1 -or (-not $entry[0].value -and -not $entry[0].secretRef)) {
            throw "Hosted sign-in requires $name. Configure Entra ID with infra\set-entra-auth.ps1 before deploying."
        }
    }
}
if ($BuildOnly -and -not $SkipFrontend -and -not $ApiFqdn) {
    throw "-BuildOnly needs -ApiFqdn (ca-api-<env>.<Container Apps environment default domain>)."
}
if (-not $SkipBackend -and -not $BuildOnly) {
    Write-Host ">>> Validating AI deployment routing before any build or app update..." -ForegroundColor Yellow
    $endpoint = az containerapp show -n $API_APP -g $RG --subscription $SUBSCRIPTION_ID `
        --query "properties.template.containers[0].env[?name=='AZURE_OPENAI_ENDPOINT'].value | [0]" -o tsv
    if ($LASTEXITCODE -ne 0 -or -not $endpoint) { throw "Cannot read the API OpenAI endpoint." }
    $endpointAccount = ([uri]$endpoint).DnsSafeHost.Split('.')[0]
    if (-not $OpenAIAccountName) { $OpenAIAccountName = $endpointAccount }
    if ($endpointAccount -ne $OpenAIAccountName) { throw "OpenAI account does not match API endpoint $endpoint." }
    $inventoryJson = az cognitiveservices account deployment list --name $OpenAIAccountName `
        --resource-group $RG --subscription $SUBSCRIPTION_ID -o json
    if ($LASTEXITCODE -ne 0) { throw "Cannot validate AI deployment inventory." }
    $inventory = @($inventoryJson | ConvertFrom-Json)
    if (-not $ChatDeployment) { $ChatDeployment = $PrimaryDeployment }
    if (-not $FraudDeployment) { $FraudDeployment = $PrimaryDeployment }
    $routes = [ordered]@{
        AZURE_OPENAI = $PrimaryDeployment
        AZURE_OPENAI_CHAT = $ChatDeployment
        AZURE_OPENAI_NANO = $NanoDeployment
        FRAUD_VISION = $FraudDeployment
        FRAUD_DETECTION = $FraudDeployment
    }
    foreach ($prefix in $routes.Keys) {
        $deployment = $routes[$prefix]
        $matches = @($inventory | Where-Object { $_.name -eq $deployment })
        if ($matches.Count -ne 1 -or $matches[0].properties.provisioningState -ne "Succeeded") {
            throw "AI route $prefix points to absent or unready deployment '$deployment' in $OpenAIAccountName."
        }
        $model = $matches[0].properties.model.name
        $deploymentSuffix = if ($prefix.StartsWith("AZURE_OPENAI")) { "DEPLOYMENT_NAME" } else { "DEPLOYMENT" }
        $modelSuffix = if ($prefix.StartsWith("AZURE_OPENAI")) { "MODEL_NAME" } else { "MODEL" }
        $backendModelEnvVarArgs += "${prefix}_${deploymentSuffix}=$deployment"
        $backendModelEnvVarArgs += "${prefix}_${modelSuffix}=$model"
        Write-Host "    ${prefix}: $deployment -> $model" -ForegroundColor Green
    }
    $backendModelEnvVarArgs += "AZURE_OPENAI_API_VERSION=2025-04-01-preview"
    $backendModelEnvVarArgs += "AZURE_OPENAI_CHAT_API_VERSION=2025-04-01-preview"
    $backendModelEnvVarArgs += "AZURE_OPENAI_REASONING_EFFORT=$ReasoningEffort"

    # Content Understanding resolves model names/aliases through its resource defaults.
    $cuCompletion = @($inventory | Where-Object { $_.name -eq $PrimaryDeployment })[0]
    $cuEmbedding = @($inventory | Where-Object { $_.properties.model.name -eq "text-embedding-3-large" })[0]
    if (-not $cuEmbedding) { throw "Content Understanding needs a text-embedding-3-large deployment." }
    $cuCompletionModel = $cuCompletion.properties.model.name
    $cuDefaults = @{
        modelDeployments = @{
            $cuCompletionModel                  = $cuCompletion.name
            "text-embedding-3-large"            = $cuEmbedding.name
            "completion"                        = $cuCompletion.name
            "embedding"                         = $cuEmbedding.name
            "prebuilt-analyzer-completion"      = $cuCompletion.name
            "prebuilt-analyzer-completion-mini" = $cuCompletion.name
            "prebuilt-analyzer-embedding"       = $cuEmbedding.name
        }
    }
    $backendModelEnvVarArgs += "AZURE_CONTENT_UNDERSTANDING_COMPLETION_DEPLOYMENT=$cuCompletionModel"
    $backendModelEnvVarArgs += "AZURE_CONTENT_UNDERSTANDING_EMBEDDING_DEPLOYMENT=text-embedding-3-large"
    Write-Host "    CONTENT_UNDERSTANDING: $cuCompletionModel -> $($cuCompletion.name), embeddings -> $($cuEmbedding.name)" -ForegroundColor Green

    # Web IQ MCP: key lives in Key Vault, referenced by the ACA secret webiq-api-key.
    $apiSecretNames = az containerapp show -n $API_APP -g $RG --subscription $SUBSCRIPTION_ID `
        --query "properties.configuration.secrets[].name" -o json | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) { throw "Cannot read API secrets from $API_APP." }
    if ($apiSecretNames -contains "webiq-api-key") {
        $backendModelEnvVarArgs += "WEBIQ_API_KEY=secretref:webiq-api-key"
        Write-Host "    WEBIQ: enabled (Key Vault reference)" -ForegroundColor Green
    } else {
        Write-Host "    WEBIQ: not configured (secret webiq-api-key absent) - chat keeps legacy web_search" -ForegroundColor Yellow
    }
}
if ($PreflightOnly) {
    Write-Host "Preflight passed. No images built or Container Apps changed." -ForegroundColor Green
    return
}

if (-not $SkipBackend -and -not $BuildOnly) {
    $cuToken = az account get-access-token --resource https://cognitiveservices.azure.com `
        --subscription $SUBSCRIPTION_ID --query accessToken -o tsv
    if ($LASTEXITCODE -ne 0) { throw "Cannot get a Content Understanding token." }
    try {
        Invoke-RestMethod -Method Patch `
            -Uri "https://$OpenAIAccountName.cognitiveservices.azure.com/contentunderstanding/defaults?api-version=2025-11-01" `
            -Headers @{ Authorization = "Bearer $cuToken" } -ContentType "application/merge-patch+json" `
            -Body ($cuDefaults | ConvertTo-Json -Depth 4) | Out-Null
        Write-Host "    Content Understanding defaults updated." -ForegroundColor Green
    } finally {
        $cuToken = $null
    }
}

# ─────────────────────────────────────────────────────────────
# Build acceleration
# ─────────────────────────────────────────────────────────────
# Dedicated agent pool → warm Docker layer cache + faster CPU + no agent-wait.
# Requires a Premium ACR. Falls back to ephemeral QuickRun if the pool is absent.
$PoolArgs = @()
if ($AgentPool) {
    $poolFound = az acr agentpool show --registry $ACR --name $AgentPool --subscription $SUBSCRIPTION_ID --query name -o tsv 2>$null
    if ($poolFound) {
        $PoolArgs = @("--agent-pool", $AgentPool)
        Write-Host "    Agent pool: $AgentPool (warm cache)" -ForegroundColor Green
    } else {
        Write-Host "    Agent pool '$AgentPool' not found — using QuickRun" -ForegroundColor Yellow
    }
}

# Auto-skip the side with no changes since a git ref (e.g. -ChangedSince HEAD~1).
if ($ChangedSince) {
    $feChanged = git diff --name-only $ChangedSince HEAD -- frontend/ 2>$null
    $beChanged = git diff --name-only $ChangedSince HEAD -- . ':(exclude)frontend/' 2>$null
    if (-not $feChanged) { $SkipFrontend = $true; Write-Host "    ChangedSince: no frontend changes since $ChangedSince → SkipFrontend" -ForegroundColor Cyan }
    if (-not $beChanged) { $SkipBackend  = $true; Write-Host "    ChangedSince: no backend changes since $ChangedSince → SkipBackend" -ForegroundColor Cyan }
}

# ─────────────────────────────────────────────────────────────
# Ensure RG tags
# ─────────────────────────────────────────────────────────────
Write-Host ">>> Resource group tagging skipped (deployment-critical path)..." -ForegroundColor Yellow

# ─────────────────────────────────────────────────────────────
# Build backend image
# ─────────────────────────────────────────────────────────────
if (-not $SkipBackend) {
    Write-Host ""
    Write-Host ">>> Building backend: ${API_IMAGE}:$Tag" -ForegroundColor Yellow
    
    # Stage minimal context — az acr build ignores .dockerignore on Windows
    # Without this: 113 MiB uploaded. With staging: ~1 MiB.
    $RepoRoot = Resolve-Path "$PSScriptRoot\.."
    $StageDir = Join-Path ([System.IO.Path]::GetTempPath()) "$API_IMAGE-ctx-$Tag"
    if (Test-Path $StageDir) { Remove-Item $StageDir -Recurse -Force }
    New-Item $StageDir -ItemType Directory -Force | Out-Null
    
    Write-Host "    Staging minimal context..."
    # Copy only what the Dockerfile needs
    Copy-Item "$RepoRoot\Dockerfile"       $StageDir
    Copy-Item "$RepoRoot\pyproject.toml"   $StageDir
    Copy-Item "$RepoRoot\uv.lock"          $StageDir
    Copy-Item "$RepoRoot\requirements.txt" $StageDir -ErrorAction SilentlyContinue
    Copy-Item "$RepoRoot\api_server.py"    $StageDir
    Copy-DirectoryToStage "$RepoRoot\app" "$StageDir\app"
    Copy-DirectoryToStage "$RepoRoot\prompts" "$StageDir\prompts"
    # assets/pdf/ (incl. assets/pdf/<brand>/) for policy PDF serving
    if (Test-Path "$RepoRoot\assets\pdf") {
        Copy-DirectoryToStage "$RepoRoot\assets\pdf" "$StageDir\assets\pdf"
    } else {
        New-Item "$StageDir\assets\pdf" -ItemType Directory -Force | Out-Null
    }
    # scripts/startup.sh for entrypoint
    New-Item "$StageDir\scripts" -ItemType Directory -Force | Out-Null
    Copy-Item "$RepoRoot\scripts\startup.sh" "$StageDir\scripts\" -ErrorAction SilentlyContinue
    
    $CtxSizeMB = [math]::Round((Get-ChildItem $StageDir -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 2)
    Write-Host "    Context: $CtxSizeMB MiB" -ForegroundColor Cyan
    
    $imageArgs = @("--image", "${API_IMAGE}:${Tag}", "--image", "${API_IMAGE}:latest")
    
    az acr build `
        --subscription $SUBSCRIPTION_ID `
        --registry $ACR `
        @imageArgs `
        @PoolArgs `
        --build-arg "BRAND_NAME=$BrandName" `
        $StageDir `
        --no-logs
    
    $buildResult = $LASTEXITCODE
    Remove-Item $StageDir -Recurse -Force -ErrorAction SilentlyContinue
    
    if ($buildResult -ne 0) {
        Write-Host "    FAILED — backend image build failed" -ForegroundColor Red
        exit 1
    }
    Write-Host "    Backend image pushed" -ForegroundColor Green
}

# ─────────────────────────────────────────────────────────────
# Build frontend image
# ─────────────────────────────────────────────────────────────
if (-not $SkipFrontend) {
    Write-Host ""
    Write-Host ">>> Building frontend: ${FE_IMAGE}:$Tag" -ForegroundColor Yellow
    
    $API_FQDN = $ApiFqdn
    for ($attempt = 1; $attempt -le 3 -and -not $API_FQDN; $attempt++) {
        $API_FQDN = az containerapp show -n $API_APP -g $RG --subscription $SUBSCRIPTION_ID --query "properties.configuration.ingress.fqdn" -o tsv 2>$null
        if (-not [string]::IsNullOrWhiteSpace($API_FQDN) -and $API_FQDN.Contains(".")) { break }
        Start-Sleep -Seconds 3
    }
    if ([string]::IsNullOrWhiteSpace($API_FQDN) -or -not $API_FQDN.Contains(".")) {
        throw "Could not resolve API FQDN for $API_APP in $RG."
    }
    
    # Stage minimal context — az acr build ignores .dockerignore on Windows
    # Without this: 103 MiB uploaded. With staging: ~1 MiB.
    $FrontendDir = Resolve-Path "$PSScriptRoot\..\frontend"
    $StageDir = Join-Path ([System.IO.Path]::GetTempPath()) "$FE_IMAGE-ctx-$Tag"
    if (Test-Path $StageDir) { Remove-Item $StageDir -Recurse -Force }
    New-Item $StageDir -ItemType Directory -Force | Out-Null
    
    Write-Host "    Staging minimal context..."
    # Copy only what the Dockerfile needs (no node_modules, no .next)
    Copy-Item "$FrontendDir\Dockerfile"         $StageDir
    Copy-Item "$FrontendDir\package.json"        $StageDir
    Copy-Item "$FrontendDir\package-lock.json"   $StageDir -ErrorAction SilentlyContinue
    Copy-Item "$FrontendDir\next.config.js"      $StageDir
    Copy-Item "$FrontendDir\postcss.config.js"   $StageDir
    Copy-Item "$FrontendDir\tailwind.config.js"  $StageDir
    Copy-Item "$FrontendDir\tsconfig.json"       $StageDir
    Copy-Item "$FrontendDir\next-env.d.ts"       $StageDir -ErrorAction SilentlyContinue
    Copy-DirectoryToStage "$FrontendDir\src" "$StageDir\src"
    Copy-DirectoryToStage "$FrontendDir\public" "$StageDir\public"
    Copy-DirectoryToStage "$FrontendDir\messages" "$StageDir\messages"
    
    $CtxSizeMB = [math]::Round((Get-ChildItem $StageDir -Recurse -File | Measure-Object Length -Sum).Sum / 1MB, 2)
    Write-Host "    Context: $CtxSizeMB MiB" -ForegroundColor Cyan
    
    $feImageArgs = @("--image", "${FE_IMAGE}:${Tag}", "--image", "${FE_IMAGE}:latest")
    
    az acr build `
        --subscription $SUBSCRIPTION_ID `
        --registry $ACR `
        @feImageArgs `
        @PoolArgs `
        --build-arg "API_URL=https://$API_FQDN" `
        --build-arg "BRAND_NAME=$BrandName" `
        $StageDir `
        --no-logs
    
    $buildResult = $LASTEXITCODE
    Remove-Item $StageDir -Recurse -Force -ErrorAction SilentlyContinue
    
    if ($buildResult -ne 0) {
        Write-Host "    FAILED — frontend image build failed" -ForegroundColor Red
        exit 1
    }
    Write-Host "    Frontend image pushed" -ForegroundColor Green
}

if ($BuildOnly) {
    Write-Host ""
    Write-Host "Build-only: images ${API_IMAGE}/${FE_IMAGE}:$Tag (+ latest) pushed; Container Apps untouched." -ForegroundColor Green
    return
}

# ─────────────────────────────────────────────────────────────
# Update Container Apps — force new revisions via unique suffix
# ACA revisions are immutable: if the image tag string is unchanged,
# `az containerapp update` is a no-op unless --revision-suffix changes.
# ─────────────────────────────────────────────────────────────
Write-Host ""
Write-Host ">>> Updating Container Apps..." -ForegroundColor Yellow

# Unique suffix with seconds to avoid same-minute collisions on reruns
$RevisionSuffix = "d$(Get-Date -Format 'MMddHHmmss')"

if (-not $SkipBackend) {
    Write-Host "    Updating $API_APP -> ${API_IMAGE}:$Tag (revision: $RevisionSuffix)"
    
    # Guard: BRAND_NAME must NEVER be set as an ACA env var — it's baked into the Docker image.
    # If someone set it manually, remove it so it doesn't override the baked-in value.
    $brandEnvVar = az containerapp show -n $API_APP -g $RG `
        --subscription $SUBSCRIPTION_ID `
        --query "properties.template.containers[0].env[?name=='BRAND_NAME'].value" -o tsv 2>$null
    if ($brandEnvVar) {
        Write-Host "    WARNING: Removing BRAND_NAME env var from ACA (must be baked in image, not set as env var)" -ForegroundColor Red
        az containerapp update --name $API_APP --resource-group $RG --subscription $SUBSCRIPTION_ID --remove-env-vars BRAND_NAME -o none
    }
    
    az containerapp update `
        --name $API_APP `
        --resource-group $RG `
        --subscription $SUBSCRIPTION_ID `
        --image "$ACR_SERVER/${API_IMAGE}:${Tag}" `
        --revision-suffix $RevisionSuffix `
        --set-env-vars @backendModelEnvVarArgs `
        -o none
    if ($LASTEXITCODE -ne 0) { throw "API revision update failed; do not route traffic." }
    Write-Host "    API updated (image + model routing env vars)" -ForegroundColor Green
}

if (-not $SkipFrontend) {
    Write-Host "    Updating $FRONTEND_APP -> ${FE_IMAGE}:$Tag (revision: $RevisionSuffix)"
    
    # API_URL is baked into the frontend image; an ACA env var would silently override it.
    $existingApiUrl = az containerapp show -n $FRONTEND_APP -g $RG `
        --subscription $SUBSCRIPTION_ID `
        --query "properties.template.containers[0].env[?name=='API_URL'].value" -o tsv 2>$null
    if ($existingApiUrl) {
        Write-Host "    Removing API_URL env var from ACA (URL is baked into the image)" -ForegroundColor Yellow
        az containerapp update --name $FRONTEND_APP --resource-group $RG --subscription $SUBSCRIPTION_ID --remove-env-vars API_URL -o none
    }
    
    # Preserve session signing for Entra, including an existing secret reference.
    $existingAuth = @($frontendAuthEnv | Where-Object { $_.name -eq "AUTH_SECRET" })
    if ($existingAuth.Count -eq 1 -and $existingAuth[0].secretRef) {
        $authSecretArg = "AUTH_SECRET=secretref:$($existingAuth[0].secretRef)"
    } elseif ($existingAuth.Count -eq 1 -and $existingAuth[0].value) {
        $authSecretArg = "AUTH_SECRET=$($existingAuth[0].value)"
    } else {
        Write-Host "    Generating new AUTH_SECRET..." -ForegroundColor Cyan
        $bytes = [byte[]]::new(32)
        [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
        $authSecretArg = "AUTH_SECRET=$([Convert]::ToHexString($bytes).ToLowerInvariant())"
    }

    $envVarArgs = @(
        "API_KEY=secretref:api-key",
        $authSecretArg,
        "LOCAL_AUTH_ENABLED=false"
    )
    $legacyAuthNames = @(
        $frontendAuthEnv |
            Where-Object { $_.name -like "AUTH_USER*" -or $_.name -like "APPSETTING_AUTH_USER*" } |
            ForEach-Object { $_.name }
    )
    $removeAuthArgs = @()
    if ($legacyAuthNames.Count -gt 0) {
        $removeAuthArgs = @("--remove-env-vars") + $legacyAuthNames
    }

    # Remove legacy credentials with the image update; never recreate local accounts.
    az containerapp update `
        --name $FRONTEND_APP `
        --resource-group $RG `
        --subscription $SUBSCRIPTION_ID `
        --image "$ACR_SERVER/${FE_IMAGE}:${Tag}" `
        --revision-suffix $RevisionSuffix `
        --set-env-vars @envVarArgs `
        @removeAuthArgs `
        -o none
    if ($LASTEXITCODE -ne 0) { throw "Frontend revision update failed; do not route traffic." }
    Write-Host "    Frontend updated (image + env vars in single revision)" -ForegroundColor Green
}

# ─────────────────────────────────────────────────────────────
# Traffic routing — single brand on the default host.
# Single revision mode (Bicep default) routes 100% to the new revision on its own;
# multiple revision mode needs an explicit 100% weight on the new revision.
# ─────────────────────────────────────────────────────────────
Write-Host ""
Write-Host ">>> Routing traffic to new revisions..." -ForegroundColor Yellow

function Set-RevisionTraffic {
    param([string]$AppName, [string]$NewRevisionName)

    $mode = az containerapp show -n $AppName -g $RG --subscription $SUBSCRIPTION_ID --query "properties.configuration.activeRevisionsMode" -o tsv 2>$null
    if ($mode -eq "Multiple") {
        az containerapp ingress traffic set --name $AppName -g $RG --subscription $SUBSCRIPTION_ID --revision-weight "$NewRevisionName=100" -o none
        if ($LASTEXITCODE -ne 0) { throw "Traffic routing failed for $AppName." }
        Write-Host "    $AppName traffic: $NewRevisionName=100" -ForegroundColor Cyan
    } else {
        Write-Host "    ${AppName}: single revision mode (latest revision serves 100%)" -ForegroundColor Cyan
    }
}

if (-not $SkipBackend) {
    Set-RevisionTraffic -AppName $API_APP -NewRevisionName "$API_APP--$RevisionSuffix"
}

if (-not $SkipFrontend) {
    Set-RevisionTraffic -AppName $FRONTEND_APP -NewRevisionName "$FRONTEND_APP--$RevisionSuffix"
}

Write-Host "    Traffic routing complete" -ForegroundColor Green

# ─────────────────────────────────────────────────────────────
# Health checks
# ─────────────────────────────────────────────────────────────
Write-Host ""
Write-Host ">>> Running health checks..." -ForegroundColor Yellow

# Use the default-host URLs for health checks.
# Initialize defensively — these vars may not be set when -SkipFrontend is used
# (the frontend block normally populates $API_FQDN for the API_URL build-arg).
if (-not (Get-Variable -Name API_FQDN -Scope Script -ValueOnly -ErrorAction SilentlyContinue)) {
    $API_FQDN = $null
}
if (-not (Get-Variable -Name FE_FQDN -Scope Script -ValueOnly -ErrorAction SilentlyContinue)) {
    $FE_FQDN = $null
}
if (-not $API_FQDN) {
    $API_FQDN = az containerapp show -n $API_APP -g $RG --subscription $SUBSCRIPTION_ID --query "properties.configuration.ingress.fqdn" -o tsv 2>$null
}
if (-not $FE_FQDN) {
    $FE_FQDN = az containerapp show -n $FRONTEND_APP -g $RG --subscription $SUBSCRIPTION_ID --query "properties.configuration.ingress.fqdn" -o tsv 2>$null
}

$HealthApiUrl = "https://$API_FQDN"
$HealthFeUrl = "https://$FE_FQDN"

# API health check
$apiOk = $false
for ($i = 1; $i -le 5; $i++) {
    try {
        $resp = Invoke-RestMethod -Uri $HealthApiUrl -Method GET -TimeoutSec 10
        if ($resp.status -eq "ok") {
            Write-Host "    API: OK ($($resp.name) v$($resp.version))" -ForegroundColor Green
            $apiOk = $true
            break
        }
    } catch {
        Write-Host "    API: attempt $i/5 - waiting 10s..." -ForegroundColor Gray
        Start-Sleep -Seconds 10
    }
}
if (-not $apiOk) {
    Write-Host "    API: FAILED after 5 attempts" -ForegroundColor Red
}

# Frontend health check
$feOk = $false
for ($i = 1; $i -le 3; $i++) {
    try {
        $feResp = Invoke-WebRequest -Uri $HealthFeUrl -Method GET -UseBasicParsing -TimeoutSec 15
        if ($feResp.StatusCode -eq 200) {
            Write-Host "    Frontend: OK (HTTP 200)" -ForegroundColor Green
            $feOk = $true
            break
        }
    } catch {
        Write-Host "    Frontend: attempt $i/3 - waiting 15s..." -ForegroundColor Gray
        Start-Sleep -Seconds 15
    }
}
if (-not $feOk) {
    Write-Host "    Frontend: FAILED (may need more cold-start time)" -ForegroundColor Yellow
}

# ─────────────────────────────────────────────────────────────
# Summary — show ALL access URLs + detect FQDN changes
# ─────────────────────────────────────────────────────────────

# Known FQDNs of your environment, used to detect DNS changes between deployments.
# Set PREVAIQ_KNOWN_API_FQDN / PREVAIQ_KNOWN_FE_FQDN after the first deploy.
$KNOWN_API_FQDN = $env:PREVAIQ_KNOWN_API_FQDN
$KNOWN_FE_FQDN  = $env:PREVAIQ_KNOWN_FE_FQDN

# Resolve current FQDNs from Azure
if (-not $API_FQDN) {
    $API_FQDN = az containerapp show -n $API_APP -g $RG --subscription $SUBSCRIPTION_ID --query "properties.configuration.ingress.fqdn" -o tsv 2>$null
}
if (-not $FE_FQDN) {
    $FE_FQDN = az containerapp show -n $FRONTEND_APP -g $RG --subscription $SUBSCRIPTION_ID --query "properties.configuration.ingress.fqdn" -o tsv 2>$null
}

# Build access URLs
$ApiUrl = "https://$API_FQDN"
$FeUrl  = "https://$FE_FQDN"

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " Deployment Complete!" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host " Tag      : $Tag" -ForegroundColor White
Write-Host " Brand    : $BrandName" -ForegroundColor White
Write-Host ""

# ── Detect FQDN changes ──
$fqdnChanged = $false
if (-not $KNOWN_API_FQDN -or -not $KNOWN_FE_FQDN) {
    Write-Host " DNS: known FQDNs not set — set these after the first deploy:" -ForegroundColor Yellow
    Write-Host "   PREVAIQ_KNOWN_API_FQDN = $API_FQDN" -ForegroundColor Yellow
    Write-Host "   PREVAIQ_KNOWN_FE_FQDN  = $FE_FQDN" -ForegroundColor Yellow
} else {
    if ($API_FQDN -ne $KNOWN_API_FQDN) {
        Write-Host " ⚠ API FQDN CHANGED!" -ForegroundColor Red
        Write-Host "   Previous : $KNOWN_API_FQDN" -ForegroundColor Yellow
        Write-Host "   Current  : $API_FQDN" -ForegroundColor Yellow
        Write-Host "   → Update PREVAIQ_KNOWN_API_FQDN" -ForegroundColor Yellow
        $fqdnChanged = $true
    }
    if ($FE_FQDN -ne $KNOWN_FE_FQDN) {
        Write-Host " ⚠ FRONTEND FQDN CHANGED!" -ForegroundColor Red
        Write-Host "   Previous : $KNOWN_FE_FQDN" -ForegroundColor Yellow
        Write-Host "   Current  : $FE_FQDN" -ForegroundColor Yellow
        Write-Host "   → Update PREVAIQ_KNOWN_FE_FQDN" -ForegroundColor Yellow
        $fqdnChanged = $true
    }
    if (-not $fqdnChanged) {
        Write-Host " DNS: No FQDN changes detected (stable)" -ForegroundColor Green
    }
}

Write-Host ""
Write-Host " ── $BrandName ──" -ForegroundColor Green
Write-Host "   Frontend : $FeUrl" -ForegroundColor White
Write-Host "   API      : $ApiUrl" -ForegroundColor White
Write-Host ""
Write-Host " Authentication: Microsoft Entra ID (hosted demo; local password login disabled)" -ForegroundColor Gray

# ─────────────────────────────────────────────────────────────
# Cleanup — deactivate old revisions (keep last 5 + any with traffic/labels)
# ─────────────────────────────────────────────────────────────
Write-Host "=============================================" -ForegroundColor Cyan
