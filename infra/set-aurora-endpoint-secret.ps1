<#
.SYNOPSIS
    Stores the Azure ML Aurora endpoint key in Key Vault and creates the API
    Container App secret reference expected by the PrevaIQ deployment.

.DESCRIPTION
    The key is entered as a SecureString and never appears in shell history or
    command-line arguments. It is written through Azure Resource Manager using
    a unique file under the gitignored .tmp directory, then the temporary file
    is removed. Run infra/deploy.ps1 afterwards so the next API revision maps
    AURORA_ENDPOINT_TOKEN to this secret and selects Key authentication.
#>
[CmdletBinding()]
param(
    [string]$SubscriptionId = $env:AZURE_SUBSCRIPTION_ID,
    [string]$TenantId = $env:AZURE_TENANT_ID,
    [string]$ResourceGroup = "rg-prevaiq-demo",
    [string]$ApiAppName = "ca-api-demo",
    [string]$KeyVaultName = "",
    [string]$IdentityName = "",
    [string]$SecretName = "aurora-endpoint-key"
)
$ErrorActionPreference = "Stop"

function Invoke-Az {
    $output = az @args
    if ($LASTEXITCODE -ne 0) { throw "az $($args[0..1] -join ' ') failed." }
    return $output
}

$account = Invoke-Az account show -o json | ConvertFrom-Json
if (($SubscriptionId -and $account.id -ne $SubscriptionId) -or ($TenantId -and $account.tenantId -ne $TenantId)) {
    throw "Wrong Azure context. Select the subscription that owns $ApiAppName before storing the key."
}

$app = Invoke-Az containerapp show -n $ApiAppName -g $ResourceGroup -o json | ConvertFrom-Json
if (-not $KeyVaultName) {
    $vaultUrl = @($app.properties.configuration.secrets | Where-Object { $_.keyVaultUrl } |
        Select-Object -First 1).keyVaultUrl
    $KeyVaultName = if ($vaultUrl) { ([uri]$vaultUrl).Host.Split(".")[0] } else { "kv-prevaiq-demo" }
}
if (-not $IdentityName) {
    $identityId = @($app.identity.userAssignedIdentities.PSObject.Properties.Name) | Select-Object -First 1
    $IdentityName = if ($identityId) { Split-Path $identityId -Leaf } else { "id-prevaiq-demo" }
}

$vault = Invoke-Az keyvault show -n $KeyVaultName -g $ResourceGroup -o json | ConvertFrom-Json
$identity = Invoke-Az identity show -n $IdentityName -g $ResourceGroup -o json | ConvertFrom-Json
$assignment = @(Invoke-Az role assignment list --assignee $identity.principalId --scope $vault.id `
    --role "Key Vault Secrets User" -o json | ConvertFrom-Json)
if ($assignment.Count -eq 0) {
    Invoke-Az role assignment create --assignee-object-id $identity.principalId `
        --assignee-principal-type ServicePrincipal --role "Key Vault Secrets User" `
        --scope $vault.id -o none
}

$secure = Read-Host "Aurora endpoint key (input hidden)" -AsSecureString
$plain = [System.Net.NetworkCredential]::new("", $secure).Password.Trim()
if ([string]::IsNullOrWhiteSpace($plain)) { throw "Empty Aurora endpoint key." }

$repoRoot = Split-Path $PSScriptRoot -Parent
$tempDirectory = Join-Path $repoRoot ".tmp"
New-Item -ItemType Directory -Path $tempDirectory -Force | Out-Null
$tempFile = Join-Path $tempDirectory "aurora-key-$([guid]::NewGuid().ToString('N')).json"
try {
    $body = @{ properties = @{ value = $plain } } | ConvertTo-Json -Compress
    [IO.File]::WriteAllText($tempFile, $body, [Text.UTF8Encoding]::new($false))
    Invoke-Az rest --method put `
        --uri "https://management.azure.com$($vault.id)/secrets/$($SecretName)?api-version=2023-07-01" `
        --body "@$tempFile" -o none
} finally {
    Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
    $plain = $null
    $body = $null
}

Invoke-Az containerapp secret set -n $ApiAppName -g $ResourceGroup `
    --secrets "$SecretName=keyvaultref:$($vault.properties.vaultUri)secrets/$SecretName,identityref:$($identity.id)" `
    -o none

Write-Host "Aurora endpoint key stored in Key Vault and referenced by $ApiAppName." -ForegroundColor Green
Write-Host "Run .\infra\deploy.ps1 to roll out AURORA_ENDPOINT_TOKEN without exposing the key." -ForegroundColor Cyan
