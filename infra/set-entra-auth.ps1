<#
.SYNOPSIS
    Enables Microsoft Entra ID sign-in on the PrevaIQ frontend with an existing Entra app
    registration (web platform, client secret).

.DESCRIPTION
    Idempotent:
      1. Appends https://<frontend-fqdn>/api/auth/entra/callback to the app's redirect URIs
         (existing URIs are kept). Needs owner rights on the app; otherwise it prints
         the URI to add in the portal.
      2. Stores the client secret in Key Vault (read from an optional gitignored tfvars file
         or typed hidden; never printed, never on the az command line).
      3. Frontend: ENTRA_TENANT_ID / ENTRA_CLIENT_ID / ENTRA_CLIENT_SECRET (Key Vault ref) /
         ACCESS_ADMIN_EMAILS / ACCESS_REQUEST_EMAIL. API: ACCESS_ALLOWED_EMAILS (pre-approved).
    Other accounts get a pending request approved in Administration > Access requests.

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
    [string]$KeyVaultName = "kv-prevaiq-demo",
    [string]$IdentityName = "id-prevaiq-demo",
    [string]$ClientId = $env:ENTRA_CLIENT_ID,
    [string]$SecretTfvars = $env:PREVAIQ_ENTRA_SECRET_TFVARS,
    [string]$SecretName = "entra-client-secret",
    [string]$AccessRequestEmail = $env:PREVAIQ_ACCESS_REQUEST_EMAIL,
    [string]$AdminEmails = $env:PREVAIQ_ADMIN_EMAILS,
    [string]$AllowedEmails = $env:PREVAIQ_ALLOWED_EMAILS
)
$ErrorActionPreference = "Stop"

function Invoke-Az {
    $output = az @args
    if ($LASTEXITCODE -ne 0) { throw "az $($args[0..1] -join ' ') failed." }
    return $output
}

if (-not $ClientId) { throw "Set -ClientId or ENTRA_CLIENT_ID to the Entra app registration ID." }
if (-not $AdminEmails) { throw "Set -AdminEmails or PREVAIQ_ADMIN_EMAILS (comma-separated)." }
if (-not $AccessRequestEmail) { $AccessRequestEmail = ($AdminEmails -split ',')[0] }

$account = Invoke-Az account show -o json | ConvertFrom-Json
if (($SubscriptionId -and $account.id -ne $SubscriptionId) -or ($TenantId -and $account.tenantId -ne $TenantId)) {
    throw "Wrong Azure context. Run: az account set --subscription $SubscriptionId"
}
if (-not $TenantId) { $TenantId = $account.tenantId }

$fqdn = Invoke-Az containerapp show -n $FrontendAppName -g $ResourceGroup `
    --query properties.configuration.ingress.fqdn -o tsv
$redirectUri = "https://$fqdn/api/auth/entra/callback"

$uris = @(az ad app show --id $ClientId --query web.redirectUris -o json 2>$null | ConvertFrom-Json)
if ($LASTEXITCODE -ne 0) {
    Write-Warning "Cannot read app $ClientId. Add this redirect URI (Web) in the portal: $redirectUri"
} elseif ($uris -notcontains $redirectUri) {
    az ad app update --id $ClientId --web-redirect-uris @($uris + $redirectUri) -o none
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "No write access on app $ClientId. Add this redirect URI (Web) in the portal: $redirectUri"
    } else { Write-Host "Redirect URI added (kept $($uris.Count) existing)." -ForegroundColor Green }
} else { Write-Host "Redirect URI already registered." -ForegroundColor Green }

if ($SecretTfvars -and (Test-Path $SecretTfvars)) {
    $match = Select-String -Path $SecretTfvars -Pattern '^\s*entra_client_secret\s*=\s*"([^"]+)"'
    if (-not $match) { throw "entra_client_secret not found in $SecretTfvars" }
    $plain = $match.Matches[0].Groups[1].Value
} else {
    $secure = Read-Host "Client secret of app $ClientId (input hidden)" -AsSecureString
    $plain = [System.Net.NetworkCredential]::new("", $secure).Password
}
if ([string]::IsNullOrWhiteSpace($plain)) { throw "Empty client secret." }
$tempFile = New-TemporaryFile
try {
    [IO.File]::WriteAllText($tempFile.FullName, $plain, [Text.UTF8Encoding]::new($false))
    Invoke-Az keyvault secret set --vault-name $KeyVaultName -n $SecretName `
        --file $tempFile.FullName --encoding utf-8 -o none
} finally {
    Remove-Item $tempFile.FullName -Force -ErrorAction SilentlyContinue
    $plain = $null
}

$vaultUri = Invoke-Az keyvault show -n $KeyVaultName -g $ResourceGroup --query properties.vaultUri -o tsv
$identityId = Invoke-Az identity show -n $IdentityName -g $ResourceGroup --query id -o tsv
Invoke-Az containerapp secret set -n $FrontendAppName -g $ResourceGroup `
    --secrets "$SecretName=keyvaultref:${vaultUri}secrets/$SecretName,identityref:$identityId" -o none
Invoke-Az containerapp update -n $FrontendAppName -g $ResourceGroup --set-env-vars `
    "ENTRA_TENANT_ID=$TenantId" "ENTRA_CLIENT_ID=$ClientId" `
    "ENTRA_CLIENT_SECRET=secretref:$SecretName" "ACCESS_REQUEST_EMAIL=$AccessRequestEmail" `
    "ACCESS_ADMIN_EMAILS=$AdminEmails" -o none
Invoke-Az containerapp update -n $ApiAppName -g $ResourceGroup --set-env-vars `
    "ACCESS_ALLOWED_EMAILS=$AllowedEmails" -o none
Write-Host "Entra ID sign-in enabled on https://$fqdn/login" -ForegroundColor Green
