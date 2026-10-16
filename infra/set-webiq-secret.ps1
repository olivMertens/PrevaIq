<#
.SYNOPSIS
    Stores the Microsoft Web IQ API key in Key Vault and exposes it to the API Container App
    as a Key Vault-referenced secret (webiq-api-key), read through the app's user-assigned identity.

.DESCRIPTION
    The key is read with Read-Host -AsSecureString: never echoed, never written to disk or history.
    Idempotent: creates the RBAC Key Vault and role assignment only when missing.
    Run deploy.ps1 afterwards so new revisions receive WEBIQ_API_KEY=secretref:webiq-api-key.
#>
[CmdletBinding()]
param(
    [string]$SubscriptionId = $env:AZURE_SUBSCRIPTION_ID,
    [string]$TenantId = $env:AZURE_TENANT_ID,
    [string]$ResourceGroup = "rg-prevaiq-demo",
    [string]$ApiAppName = "ca-api-demo",
    [string]$KeyVaultName = "kv-prevaiq-demo",
    [string]$IdentityName = "id-prevaiq-demo",
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

$location = Invoke-Az group show -n $ResourceGroup --query location -o tsv
$exists = az keyvault show -n $KeyVaultName -g $ResourceGroup --query id -o tsv 2>$null
if (-not $exists) {
    Write-Host "Creating Key Vault $KeyVaultName (RBAC, purge protection)..." -ForegroundColor Cyan
    Invoke-Az keyvault create -n $KeyVaultName -g $ResourceGroup -l $location `
        --enable-rbac-authorization true --enable-purge-protection true -o none
}
$vaultId = Invoke-Az keyvault show -n $KeyVaultName -g $ResourceGroup --query id -o tsv
$vaultUri = Invoke-Az keyvault show -n $KeyVaultName -g $ResourceGroup --query properties.vaultUri -o tsv

# The operator needs write access once; the app identity only reads.
$me = Invoke-Az ad signed-in-user show --query id -o tsv
$identity = Invoke-Az identity show -n $IdentityName -g $ResourceGroup -o json | ConvertFrom-Json
foreach ($assignment in @(
        @{ Principal = $me; Type = "User"; Role = "Key Vault Secrets Officer" },
        @{ Principal = $identity.principalId; Type = "ServicePrincipal"; Role = "Key Vault Secrets User" })) {
    # No JMESPath with parentheses here: az.cmd routes arguments through cmd.exe.
    $current = @(Invoke-Az role assignment list --assignee $assignment.Principal --scope $vaultId `
        --role $assignment.Role -o json | ConvertFrom-Json)
    if ($current.Count -eq 0) {
        Invoke-Az role assignment create --assignee-object-id $assignment.Principal `
            --assignee-principal-type $assignment.Type --role $assignment.Role --scope $vaultId -o none
        Write-Host "Granted $($assignment.Role)." -ForegroundColor Green
    }
}

$secure = Read-Host "Web IQ API key (input hidden)" -AsSecureString
$plain = [System.Net.NetworkCredential]::new("", $secure).Password
if ([string]::IsNullOrWhiteSpace($plain)) { throw "Empty key." }
$tempFile = New-TemporaryFile
try {
    # --file keeps the key off the az.cmd command line (visible to other processes).
    [IO.File]::WriteAllText($tempFile.FullName, $plain, [Text.UTF8Encoding]::new($false))
    $set = $false
    for ($attempt = 1; $attempt -le 6 -and -not $set; $attempt++) {
        az keyvault secret set --vault-name $KeyVaultName -n $SecretName --file $tempFile.FullName `
            --encoding utf-8 -o none
        if ($LASTEXITCODE -eq 0) { $set = $true } else {
            Write-Host "Waiting for RBAC propagation (attempt $attempt/6)..." -ForegroundColor Yellow
            Start-Sleep -Seconds 30
        }
    }
    if (-not $set) { throw "Could not write the secret (RBAC propagation can take ~5 min; rerun)." }
} finally {
    Remove-Item $tempFile.FullName -Force -ErrorAction SilentlyContinue
    $plain = $null
}

Invoke-Az containerapp secret set -n $ApiAppName -g $ResourceGroup `
    --secrets "$SecretName=keyvaultref:$($vaultUri)secrets/$SecretName,identityref:$($identity.id)" -o none
Write-Host "ACA secret $SecretName now references Key Vault. Run deploy.ps1 to roll out WEBIQ_API_KEY." -ForegroundColor Green
