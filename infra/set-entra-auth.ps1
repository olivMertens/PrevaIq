<#
.SYNOPSIS
    Configures an existing or dedicated organizational Entra web registration and
    rolls out PrevaIQ through deploy.ps1.

.DESCRIPTION
    Configuration:
      1. Appends https://<frontend-fqdn>/api/auth/entra/callback to the app's redirect URIs
         (existing URIs are kept). Needs owner rights on the app; otherwise it prints
         the URI to add in the portal.
      2. Stores the client secret in Key Vault (read from an optional gitignored tfvars file
         or typed hidden; never printed, never on the az command line).
      3. Frontend: ENTRA_TENANT_ID / ENTRA_CLIENT_ID / ENTRA_CLIENT_SECRET (Key Vault ref) /
         ENTRA_ALLOWED_TENANT_IDS / ACCESS_ADMIN_EMAILS / ACCESS_REQUEST_EMAIL.
         API: optional preapprovals and ACS Email settings.
      4. Builds and deploys both images through deploy.ps1. A dedicated registration
         gets a separate Key Vault secret and invalidates previous sessions.
    Eligible accounts from explicitly allowed tenants get a pending request unless
    preapproved or explicitly listed as administrators.

    Environment-specific values come from parameters or environment variables:
    AZURE_SUBSCRIPTION_ID, AZURE_TENANT_ID, ENTRA_CLIENT_ID, PREVAIQ_ENTRA_SECRET_TFVARS,
    PREVAIQ_ACCESS_REQUEST_EMAIL, PREVAIQ_ADMIN_EMAILS, PREVAIQ_ALLOWED_EMAILS.
#>
[CmdletBinding()]
param(
    [string]$SubscriptionId = $env:AZURE_SUBSCRIPTION_ID,
    [string]$TenantId = $env:AZURE_TENANT_ID,
    [string]$ResourceGroup = "rg-prevaiq-demo",
    [string]$FrontendAppName = "ca-frontend-demo",
    [string]$ApiAppName = "ca-api-demo",
    [string]$AcrName = "",
    [string]$KeyVaultName = "kv-prevaiq-demo",
    [string]$IdentityName = "id-prevaiq-demo",
    [string]$ClientId = $env:ENTRA_CLIENT_ID,
    [switch]$CreateRegistration,
    [string]$RegistrationName = "PrevaIQ Colleagues Demo",
    [string]$SignInTenant = $env:PREVAIQ_ENTRA_AUTHORITY,
    [string]$AllowedTenantIds = $env:ENTRA_ALLOWED_TENANT_IDS,
    [string]$SecretTfvars = $env:PREVAIQ_ENTRA_SECRET_TFVARS,
    [string]$SecretName = "entra-client-secret",
    [string]$AccessRequestEmail = $env:PREVAIQ_ACCESS_REQUEST_EMAIL,
    [string]$AdminEmails = $env:PREVAIQ_ADMIN_EMAILS,
    [string]$AllowedEmails = $env:PREVAIQ_ALLOWED_EMAILS,
    [hashtable]$EmailSettings = @{},
    [string]$Tag = ""
)
$ErrorActionPreference = "Stop"

function Invoke-Az {
    $output = az @args
    if ($LASTEXITCODE -ne 0) { throw "az $($args[0..1] -join ' ') failed." }
    return $output
}

if (-not $ClientId -and -not $CreateRegistration) {
    throw "Set -ClientId or use -CreateRegistration for a dedicated application."
}
if (-not $AdminEmails) { throw "Set -AdminEmails or PREVAIQ_ADMIN_EMAILS (comma-separated)." }
if (-not $AccessRequestEmail) { $AccessRequestEmail = ($AdminEmails -split ',')[0] }

$account = Invoke-Az account show -o json | ConvertFrom-Json
if (($SubscriptionId -and $account.id -ne $SubscriptionId) -or ($TenantId -and $account.tenantId -ne $TenantId)) {
    throw "Wrong Azure context. Run: az account set --subscription $SubscriptionId"
}
if (-not $TenantId) { $TenantId = $account.tenantId }
if (-not $SignInTenant) { $SignInTenant = if ($CreateRegistration) { "organizations" } else { $TenantId } }
if ($SignInTenant -in @("organizations", "common") -and -not $AllowedTenantIds) {
    throw "Set -AllowedTenantIds to verified tenant IDs before enabling organizational sign-in."
}

$fqdn = Invoke-Az containerapp show -n $FrontendAppName -g $ResourceGroup `
    --query properties.configuration.ingress.fqdn -o tsv
$redirectUri = "https://$fqdn/api/auth/entra/callback"
if (-not $AcrName) {
    $registry = Invoke-Az containerapp show -n $FrontendAppName -g $ResourceGroup `
        --query "properties.configuration.registries[0].server" -o tsv
    if (-not $registry) { throw "Cannot discover the deployed container registry; set -AcrName." }
    $AcrName = ($registry -split '\.')[0]
}

if ($CreateRegistration) {
    if ($ClientId) { throw "-CreateRegistration cannot be combined with -ClientId." }
    if ($SecretName -eq "entra-client-secret") { $SecretName = "entra-colleagues-client-secret" }
    $existing = @(Invoke-Az ad app list --display-name $RegistrationName -o json | ConvertFrom-Json)
    if ($existing.Count -gt 1) { throw "Multiple registrations have this name; specify a unique -RegistrationName." }
    if ($existing.Count -eq 1) {
        if ($existing[0].signInAudience -ne "AzureADMultipleOrgs") {
            throw "Existing registration does not support organizations; refusing to change a shared registration."
        }
        $ClientId = $existing[0].appId
    } else {
        $registration = Invoke-Az ad app create --display-name $RegistrationName `
            --sign-in-audience AzureADMultipleOrgs --web-redirect-uris $redirectUri -o json | ConvertFrom-Json
        $ClientId = $registration.appId
    }
    $sp = az ad sp show --id $ClientId -o json 2>$null | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0) {
        $sp = Invoke-Az ad sp create --id $ClientId -o json | ConvertFrom-Json
    }
    if ($sp.appRoleAssignmentRequired) {
        throw "Dedicated enterprise app requires assignment. Disable this on that dedicated app before proceeding."
    }
}

$uris = @(az ad app show --id $ClientId --query web.redirectUris -o json 2>$null | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Cannot read app $ClientId. Add this redirect URI (Web) in the portal: $redirectUri"
} elseif ($uris -notcontains $redirectUri) {
    az ad app update --id $ClientId --web-redirect-uris @($uris + $redirectUri) -o none
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "No write access on app $ClientId. Add this redirect URI (Web) in the portal: $redirectUri"
    } else { Write-Host "Redirect URI added (kept $($uris.Count) existing)." -ForegroundColor Green }
} else { Write-Host "Redirect URI already registered." -ForegroundColor Green }

if ($CreateRegistration) {
    $expiry = (Get-Date).ToUniversalTime().AddMonths(6).ToString("yyyy-MM-ddTHH:mm:ssZ")
    $credential = Invoke-Az ad app credential reset --id $ClientId --append `
        --display-name "PrevaIQ demo frontend" --end-date $expiry -o json | ConvertFrom-Json
    $plain = $credential.password
    $credential = $null
} elseif ($SecretTfvars -and (Test-Path $SecretTfvars)) {
    $match = Select-String -Path $SecretTfvars -Pattern '^\s*entra_client_secret\s*=\s*"([^"]+)"'
    if (-not $match) { throw "entra_client_secret not found in $SecretTfvars" }
    $plain = $match.Matches[0].Groups[1].Value
} else {
    $secure = Read-Host "Client secret of app $ClientId (input hidden)" -AsSecureString
    $plain = [System.Net.NetworkCredential]::new("", $secure).Password
}
if ([string]::IsNullOrWhiteSpace($plain)) { throw "Empty client secret." }
$temporaryDirectory = Join-Path $PSScriptRoot "..\.tmp"
[IO.Directory]::CreateDirectory($temporaryDirectory) | Out-Null
$tempFile = Join-Path $temporaryDirectory "entra-secret-$([guid]::NewGuid()).txt"
try {
    [IO.File]::WriteAllText($tempFile, $plain, [Text.UTF8Encoding]::new($false))
    Invoke-Az keyvault secret set --vault-name $KeyVaultName -n $SecretName `
        --file $tempFile --encoding utf-8 -o none
} finally {
    if (Test-Path $tempFile) { Remove-Item $tempFile -Force }
    $plain = $null
}

$vaultUri = Invoke-Az keyvault show -n $KeyVaultName -g $ResourceGroup --query properties.vaultUri -o tsv
$identityId = Invoke-Az identity show -n $IdentityName -g $ResourceGroup --query id -o tsv
Invoke-Az containerapp secret set -n $FrontendAppName -g $ResourceGroup `
    --secrets "$SecretName=keyvaultref:${vaultUri}secrets/$SecretName,identityref:$identityId" -o none
$frontend = @{
    ENTRA_TENANT_ID = $SignInTenant
    ENTRA_CLIENT_ID = $ClientId
    ENTRA_CLIENT_SECRET = "secretref:$SecretName"
    ENTRA_ALLOWED_TENANT_IDS = $AllowedTenantIds
    ACCESS_REQUEST_EMAIL = $AccessRequestEmail
    ACCESS_ADMIN_EMAILS = $AdminEmails
}
$backend = @{}
if ($PSBoundParameters.ContainsKey("AllowedEmails") -or $env:PREVAIQ_ALLOWED_EMAILS) {
    $backend.ACCESS_ALLOWED_EMAILS = $AllowedEmails
}
foreach ($name in $EmailSettings.Keys) { $backend[$name] = $EmailSettings[$name] }
& (Join-Path $PSScriptRoot "deploy.ps1") -ResourceGroup $ResourceGroup `
    -FrontendAppName $FrontendAppName -ApiAppName $ApiAppName `
    -AcrName $AcrName `
    -SubscriptionId $account.id -TenantId $account.tenantId -Tag $Tag `
    -FrontendAccessSettings $frontend -BackendAccessSettings $backend -RotateAuthSecret:$CreateRegistration
if ($LASTEXITCODE -ne 0) { throw "PrevaIQ deployment failed; Entra configuration was not rolled out." }
Write-Host "Entra ID sign-in enabled on https://$fqdn/login" -ForegroundColor Green
