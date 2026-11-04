<#
.SYNOPSIS
    Stores the Microsoft Web IQ API key in Key Vault and exposes it to the API Container App
    as a Key Vault-referenced secret (webiq-api-key), read through the app's user-assigned identity.

.DESCRIPTION
    The key is read with Read-Host -AsSecureString and never echoed or added to shell history.
    It is written through Azure Resource Manager (Microsoft.KeyVault/vaults/secrets), so it also
    works when governance policies keep the Key Vault private (publicNetworkAccess=Disabled).
    The request body exists only in a unique file under the gitignored .tmp directory and is
    deleted in a finally block.
    The Key Vault and identity are discovered from the API Container App unless specified; an
    RBAC Key Vault is created only when it does not exist. Idempotent.
    When the API already maps WEBIQ_API_KEY to the secret, its active revision is restarted to
    load the key; otherwise run deploy.ps1 so new revisions receive WEBIQ_API_KEY.
#>
[CmdletBinding()]
param(
    [string]$SubscriptionId = $env:AZURE_SUBSCRIPTION_ID,
    [string]$TenantId = $env:AZURE_TENANT_ID,
    [string]$ResourceGroup = "rg-prevaiq-demo",
    [string]$ApiAppName = "ca-api-demo",
    [string]$KeyVaultName = "",
    [string]$IdentityName = "",
    [string]$SecretName = "webiq-api-key"
)
$ErrorActionPreference = "Stop"

function Invoke-Az {
    $output = az @args
    if ($LASTEXITCODE -ne 0) { throw "az $($args[0..1] -join ' ') failed." }
    return $output
}

$account = Invoke-Az account show -o json | ConvertFrom-Json
if (($SubscriptionId -and $account.id -ne $SubscriptionId) -or ($TenantId -and $account.tenantId -ne $TenantId)) {
    throw "Wrong Azure context. Run: az account set --subscription $SubscriptionId"
}

# Reuse the resources the API already uses: deployments created before the prevaiq naming
# keep their original Key Vault and identity names.
$app = Invoke-Az containerapp show -n $ApiAppName -g $ResourceGroup -o json | ConvertFrom-Json
if (-not $KeyVaultName) {
    $vaultUrl = @($app.properties.configuration.secrets | Where-Object { $_.keyVaultUrl } |
        Sort-Object { $_.name -ne $SecretName } | Select-Object -First 1).keyVaultUrl
    $KeyVaultName = if ($vaultUrl) { ([uri]$vaultUrl).Host.Split(".")[0] } else { "kv-prevaiq-demo" }
}
if (-not $IdentityName) {
    $identityId = @($app.identity.userAssignedIdentities.PSObject.Properties.Name) | Select-Object -First 1
    $IdentityName = if ($identityId) { Split-Path $identityId -Leaf } else { "id-prevaiq-demo" }
}
Write-Host "Key Vault: $KeyVaultName - identity: $IdentityName" -ForegroundColor Cyan

$location = Invoke-Az group show -n $ResourceGroup --query location -o tsv
$exists = az keyvault show -n $KeyVaultName -g $ResourceGroup --query id -o tsv 2>$null
if (-not $exists) {
    Write-Host "Creating Key Vault $KeyVaultName (RBAC, purge protection)..." -ForegroundColor Cyan
    Invoke-Az keyvault create -n $KeyVaultName -g $ResourceGroup -l $location `
        --enable-rbac-authorization true --enable-purge-protection true -o none
}
$vaultId = Invoke-Az keyvault show -n $KeyVaultName -g $ResourceGroup --query id -o tsv
$vaultUri = Invoke-Az keyvault show -n $KeyVaultName -g $ResourceGroup --query properties.vaultUri -o tsv

# The app identity only reads; the operator writes through Azure Resource Manager.
$identity = Invoke-Az identity show -n $IdentityName -g $ResourceGroup -o json | ConvertFrom-Json
$current = @(Invoke-Az role assignment list --assignee $identity.principalId --scope $vaultId `
    --role "Key Vault Secrets User" -o json | ConvertFrom-Json)
if ($current.Count -eq 0) {
    Invoke-Az role assignment create --assignee-object-id $identity.principalId `
        --assignee-principal-type ServicePrincipal --role "Key Vault Secrets User" --scope $vaultId -o none
    Write-Host "Granted Key Vault Secrets User to $IdentityName." -ForegroundColor Green
}

$secure = Read-Host "Web IQ API key (input hidden)" -AsSecureString
$plain = [System.Net.NetworkCredential]::new("", $secure).Password.Trim()
if ([string]::IsNullOrWhiteSpace($plain)) { throw "Empty key." }
$repoRoot = Split-Path $PSScriptRoot -Parent
$tempDirectory = Join-Path $repoRoot ".tmp"
New-Item -ItemType Directory -Path $tempDirectory -Force | Out-Null
$tempFile = Join-Path $tempDirectory "webiq-key-$([guid]::NewGuid().ToString('N')).json"
try {
    # --body @file keeps the key off the az.cmd command line (visible to other processes).
    $body = @{ properties = @{ value = $plain } } | ConvertTo-Json -Compress
    [IO.File]::WriteAllText($tempFile, $body, [Text.UTF8Encoding]::new($false))
    Invoke-Az rest --method put --uri "https://management.azure.com$($vaultId)/secrets/$($SecretName)?api-version=2023-07-01" `
        --body "@$tempFile" -o none
} finally {
    Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
    $plain = $null
    $body = $null
}

Invoke-Az containerapp secret set -n $ApiAppName -g $ResourceGroup `
    --secrets "$SecretName=keyvaultref:$($vaultUri)secrets/$SecretName,identityref:$($identity.id)" -o none
$mapped = @($app.properties.template.containers | ForEach-Object { $_.env } |
    Where-Object { $_.name -eq "WEBIQ_API_KEY" -and $_.secretRef -eq $SecretName })
if ($mapped.Count -gt 0) {
    $revision = $app.properties.latestReadyRevisionName
    Invoke-Az containerapp revision restart -n $ApiAppName -g $ResourceGroup --revision $revision -o none
    Write-Host "Web IQ key stored; revision $revision restarted to load it." -ForegroundColor Green
} else {
    Write-Host "ACA secret $SecretName now references Key Vault. Run deploy.ps1 to roll out WEBIQ_API_KEY." -ForegroundColor Green
}
