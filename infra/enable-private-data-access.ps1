<#
.SYNOPSIS
    Connects an existing PrevaIQ deployment to private-only Blob Storage and Key Vault.

.DESCRIPTION
    Governance policies such as MCAPS StorageAccount_PublicNetwork_Modify and
    KeyVault_PublicNetwork_Modify force publicNetworkAccess=Disabled. A Container Apps
    environment without VNet integration can then no longer read case data or resolve
    Key Vault references. Public access is never re-enabled by this script.

    Mirroring the private-networking layout of infra/main.bicep and infra/terraform/network.tf,
    the script idempotently:
      1. creates the VNet, an apps subnet delegated to Microsoft.App/environments and a
         private endpoint subnet;
      2. creates the blob and vault private DNS zones and links them to the VNet;
      3. creates private endpoints for the API data Storage account and its Key Vault;
      4. creates a VNet-integrated workload-profiles Container Apps environment;
      5. starts the API PostgreSQL server when governance automation stopped it;
      6. with -MigrateWorkloads, recreates the Container Apps jobs and the API of the API
         environment inside the new environment. An app cannot change environment, so each
         workload is deleted and recreated with the same name, identity, registries, secrets,
         variables, ingress and scale. The frontend keeps its environment and public URL.

    After -MigrateWorkloads, run infra\deploy.ps1 so the frontend is rebuilt against the new
    API FQDN.

.EXAMPLE
    .\infra\enable-private-data-access.ps1                    # network + environment, no downtime
    .\infra\enable-private-data-access.ps1 -MigrateWorkloads  # then move the jobs and the API
#>
param(
    [string]$ResourceGroup = "rg-prevaiq-demo",
    [string]$SubscriptionId = $env:AZURE_SUBSCRIPTION_ID,
    [string]$Prefix = "prevaiq-demo",
    [string]$VnetAddressSpace = "10.60.0.0/16",
    [string]$AppsSubnetPrefix = "10.60.0.0/26",
    [string]$PrivateEndpointSubnetPrefix = "10.60.1.0/24",
    [string]$ApiAppName = "ca-api-demo",
    [switch]$MigrateWorkloads
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest
$ProgressPreference = "SilentlyContinue"

$ArmApiVersion = "2024-03-01"
$VnetName = "vnet-$Prefix"
$AppsSubnetName = "snet-apps"
$EndpointSubnetName = "snet-private-endpoints"
$EnvironmentName = "cae-$Prefix"
$DnsLinkName = "link-$Prefix"
$PrivateDnsZones = [ordered]@{
    blob  = "privatelink.blob.core.windows.net"
    vault = "privatelink.vaultcore.azure.net"
}
$DefinitionDirectory = Join-Path (Split-Path -Parent $PSScriptRoot) ".tmp\private-data-access"
$JsonDateArgs = @{}
if ((Get-Command ConvertFrom-Json).Parameters.ContainsKey("DateKind")) {
    $JsonDateArgs.DateKind = "String"
}

function Write-Step([string]$Message) {
    Write-Host ">>> $Message" -ForegroundColor Yellow
}

function Get-Property($Object, [string]$Name) {
    if ($null -eq $Object) { return $null }
    $property = $Object.PSObject.Properties[$Name]
    if ($property) { return $property.Value }
    return $null
}

# Arguments are never echoed on failure because some carry keys.
function Invoke-AzJson {
    param(
        [Parameter(Mandatory = $true)][string]$Description,
        [Parameter(Mandatory = $true)][string[]]$Arguments
    )
    $output = & az @Arguments --only-show-errors -o json
    if ($LASTEXITCODE -ne 0) { throw "$Description failed." }
    $text = ($output | Out-String).Trim()
    if (-not $text) { return }
    return ConvertFrom-Json -InputObject $text @JsonDateArgs
}

function Test-AzResource {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    & az @Arguments --only-show-errors -o none 2>$null
    $found = $LASTEXITCODE -eq 0
    $global:LASTEXITCODE = 0
    return $found
}

function Get-AppResourceUri([string]$Kind, [string]$Name, [string]$Action = "") {
    $path = "/subscriptions/$script:SubscriptionIdValue/resourceGroups/$ResourceGroup" +
        "/providers/Microsoft.App/$Kind/$Name"
    if ($Action) { $path += "/$Action" }
    return "https://management.azure.com$($path)?api-version=$ArmApiVersion"
}

function Get-AppSetting($Resource, [string]$Name) {
    foreach ($container in @(Get-Property (Get-Property $Resource.properties "template") "containers")) {
        foreach ($entry in @(Get-Property $container "env")) {
            if ((Get-Property $entry "name") -eq $Name) { return Get-Property $entry "value" }
        }
    }
    return $null
}

function Initialize-PrivateEndpoint {
    param([string]$Name, [string]$TargetId, [string]$GroupId)
    Write-Step "Private endpoint $Name"
    if (-not (Test-AzResource @("network", "private-endpoint", "show", "-g", $ResourceGroup, "-n", $Name))) {
        Invoke-AzJson "Create $Name" (@(
            "network", "private-endpoint", "create", "-g", $ResourceGroup, "-n", $Name, "-l", $Location,
            "--vnet-name", $VnetName, "--subnet", $EndpointSubnetName,
            "--private-connection-resource-id", $TargetId, "--group-id", $GroupId,
            "--connection-name", "psc-$GroupId"
        ) + $TagArguments) | Out-Null
    }
    $zoneGroups = @(Invoke-AzJson "Read $Name DNS registration" @(
        "network", "private-endpoint", "dns-zone-group", "list", "-g", $ResourceGroup, "--endpoint-name", $Name
    ))
    if ($zoneGroups.Count -eq 0) {
        Invoke-AzJson "Register $Name in private DNS" @(
            "network", "private-endpoint", "dns-zone-group", "create", "-g", $ResourceGroup,
            "--endpoint-name", $Name, "-n", "default", "--private-dns-zone", $ZoneIds[$GroupId],
            "--zone-name", $GroupId
        ) | Out-Null
    }
    $endpoint = Invoke-AzJson "Read $Name" @("network", "private-endpoint", "show", "-g", $ResourceGroup, "-n", $Name)
    $connections = @(Get-Property $endpoint "privateLinkServiceConnections") +
        @(Get-Property $endpoint "manualPrivateLinkServiceConnections") | Where-Object { $_ }
    $status = @($connections | ForEach-Object {
        Get-Property (Get-Property $_ "privateLinkServiceConnectionState") "status"
    }) | Select-Object -First 1
    if ($status -ne "Approved") {
        throw "$Name connection is '$status'; approve it on the target resource, then rerun."
    }
    Write-Host "    Connection approved" -ForegroundColor Green
}

function Move-Workload {
    param([ValidateSet("containerApps", "jobs")][string]$Kind, [string]$Name)
    $uri = Get-AppResourceUri $Kind $Name
    $resource = Invoke-AzJson "Read $Name" @("rest", "--method", "get", "--uri", $uri)
    if ((Get-Property $resource.properties "environmentId") -ieq $TargetEnvironmentId) {
        Write-Host "    $Name already runs in $EnvironmentName"
        return
    }
    Write-Step "Moving $Name to $EnvironmentName"

    $secretList = Invoke-AzJson "Read $Name secrets" @(
        "rest", "--method", "post", "--uri", (Get-AppResourceUri $Kind $Name "listSecrets")
    )
    $secrets = @(@(Get-Property $secretList "value") | Where-Object { $_ } | ForEach-Object {
        $vaultUrl = Get-Property $_ "keyVaultUrl"
        if ($vaultUrl) {
            [ordered]@{ name = $_.name; keyVaultUrl = $vaultUrl; identity = Get-Property $_ "identity" }
        } else {
            [ordered]@{ name = $_.name; value = $_.value }
        }
    })

    $configuration = $resource.properties.configuration
    $configuration | Add-Member -NotePropertyName secrets -NotePropertyValue $secrets -Force
    $ingress = Get-Property $configuration "ingress"
    if ($ingress) { $ingress.PSObject.Properties.Remove("fqdn") }
    foreach ($registry in @(Get-Property $configuration "registries")) {
        foreach ($field in @("username", "passwordSecretRef")) {
            if ($registry -and -not (Get-Property $registry $field)) { $registry.PSObject.Properties.Remove($field) }
        }
    }
    $template = $resource.properties.template
    $template.PSObject.Properties.Remove("revisionSuffix")
    foreach ($container in @(Get-Property $template "containers") + @(Get-Property $template "initContainers")) {
        $resources = Get-Property $container "resources"
        if ($resources) { $resources.PSObject.Properties.Remove("ephemeralStorage") }
    }

    $body = [ordered]@{
        location   = $resource.location
        properties = [ordered]@{
            environmentId       = $TargetEnvironmentId
            workloadProfileName = Get-Property $resource.properties "workloadProfileName"
            configuration       = $configuration
            template            = $template
        }
    }
    $sourceIdentity = Get-Property $resource "identity"
    $identityType = Get-Property $sourceIdentity "type"
    if ($identityType) {
        $identity = [ordered]@{ type = $identityType }
        $assigned = Get-Property $sourceIdentity "userAssignedIdentities"
        if ($assigned) {
            $map = [ordered]@{}
            foreach ($property in $assigned.PSObject.Properties) { $map[$property.Name] = @{} }
            $identity.userAssignedIdentities = $map
        }
        $body.identity = $identity
    }
    $tags = Get-Property $resource "tags"
    if ($tags) { $body.tags = $tags }

    # The definition holds secret values: it stays in the gitignored .tmp folder and is
    # deleted once the workload is provisioned again (manual recovery: az rest --method put).
    New-Item -ItemType Directory -Force -Path $DefinitionDirectory | Out-Null
    $definitionFile = Join-Path $DefinitionDirectory "$Kind-$Name.json"
    $body | ConvertTo-Json -Depth 64 | Set-Content -Path $definitionFile -Encoding utf8

    if ($Kind -eq "containerApps") {
        Invoke-AzJson "Delete $Name" @("containerapp", "delete", "-g", $ResourceGroup, "-n", $Name, "--yes") | Out-Null
    } else {
        Invoke-AzJson "Delete $Name" @("containerapp", "job", "delete", "-g", $ResourceGroup, "-n", $Name, "--yes") | Out-Null
    }
    Invoke-AzJson "Create $Name (definition kept in $definitionFile)" @(
        "rest", "--method", "put", "--uri", $uri, "--body", "@$definitionFile"
    ) | Out-Null

    $deadline = (Get-Date).AddMinutes(15)
    do {
        Start-Sleep -Seconds 10
        $state = (Invoke-AzJson "Read $Name" @("rest", "--method", "get", "--uri", $uri)).properties.provisioningState
        Write-Host "    $Name provisioning: $state"
    } while ($state -notin @("Succeeded", "Failed", "Canceled") -and (Get-Date) -lt $deadline)
    if ($state -ne "Succeeded") {
        throw "$Name provisioning ended in '$state'; definition kept in $definitionFile."
    }
    Remove-Item -LiteralPath $definitionFile -Force
    Write-Host "    $Name moved" -ForegroundColor Green
}

# -------------------------------------------------------------
# Context and discovery
# -------------------------------------------------------------
Write-Step "Azure context"
if ($SubscriptionId) {
    az account set --subscription $SubscriptionId --only-show-errors
    if ($LASTEXITCODE -ne 0) { throw "Cannot select the requested subscription." }
}
$account = Invoke-AzJson "Read Azure account" @("account", "show")
$script:SubscriptionIdValue = $account.id
Write-Host "    Subscription: $($account.name)"

$group = Invoke-AzJson "Read $ResourceGroup" @("group", "show", "-n", $ResourceGroup)
$TagArguments = @()
$groupTags = Get-Property $group "tags"
if ($groupTags) {
    $TagArguments = @("--tags") + @($groupTags.PSObject.Properties | ForEach-Object { "$($_.Name)=$($_.Value)" })
}

$api = Invoke-AzJson "Read $ApiAppName" @("rest", "--method", "get", "--uri", (Get-AppResourceUri "containerApps" $ApiAppName))
$SourceEnvironmentId = $api.properties.environmentId
$sourceEnvironment = Invoke-AzJson "Read the API environment" @(
    "rest", "--method", "get", "--uri", "https://management.azure.com$($SourceEnvironmentId)?api-version=$ArmApiVersion"
)
$Location = ($sourceEnvironment.location -replace "\s", "").ToLowerInvariant()

$jobs = @(@(Invoke-AzJson "List Container Apps jobs" @("containerapp", "job", "list", "-g", $ResourceGroup)) |
    Where-Object { $_ -and (Get-Property $_.properties "environmentId") -ieq $SourceEnvironmentId })

$storageName = Get-AppSetting $api "AZURE_STORAGE_ACCOUNT_NAME"
if (-not $storageName) { throw "AZURE_STORAGE_ACCOUNT_NAME is not configured on $ApiAppName." }
$storage = Invoke-AzJson "Read $storageName" @("storage", "account", "show", "-g", $ResourceGroup, "-n", $storageName)

$vaultNames = @(@($api) + $jobs | ForEach-Object {
    @(Get-Property (Get-Property $_.properties "configuration") "secrets")
} | ForEach-Object { Get-Property $_ "keyVaultUrl" } | Where-Object { $_ } |
    ForEach-Object { ([uri]$_).Host.Split(".")[0] } | Sort-Object -Unique)
if ($vaultNames.Count -gt 1) { throw "Several Key Vaults are referenced: $($vaultNames -join ', ')." }

Write-Host "    API environment: $(Split-Path -Leaf $SourceEnvironmentId)"
Write-Host "    Storage: $storageName (publicNetworkAccess=$($storage.publicNetworkAccess))"
if ($vaultNames) { Write-Host "    Key Vault: $($vaultNames[0])" }
Write-Host "    Jobs: $(if ($jobs) { ($jobs | ForEach-Object { $_.name }) -join ', ' } else { 'none' })"

# -------------------------------------------------------------
# Network foundation
# -------------------------------------------------------------
Write-Step "Virtual network $VnetName"
if (-not (Test-AzResource @("network", "vnet", "show", "-g", $ResourceGroup, "-n", $VnetName))) {
    Invoke-AzJson "Create $VnetName" (@(
        "network", "vnet", "create", "-g", $ResourceGroup, "-n", $VnetName, "-l", $Location,
        "--address-prefixes", $VnetAddressSpace
    ) + $TagArguments) | Out-Null
}
$vnet = Invoke-AzJson "Read $VnetName" @("network", "vnet", "show", "-g", $ResourceGroup, "-n", $VnetName)
$subnetNames = @(@(Get-Property $vnet "subnets") | Where-Object { $_ } | ForEach-Object { $_.name })
if ($AppsSubnetName -notin $subnetNames) {
    Invoke-AzJson "Create $AppsSubnetName" @(
        "network", "vnet", "subnet", "create", "-g", $ResourceGroup, "--vnet-name", $VnetName,
        "-n", $AppsSubnetName, "--address-prefixes", $AppsSubnetPrefix,
        "--delegations", "Microsoft.App/environments"
    ) | Out-Null
}
if ($EndpointSubnetName -notin $subnetNames) {
    Invoke-AzJson "Create $EndpointSubnetName" @(
        "network", "vnet", "subnet", "create", "-g", $ResourceGroup, "--vnet-name", $VnetName,
        "-n", $EndpointSubnetName, "--address-prefixes", $PrivateEndpointSubnetPrefix
    ) | Out-Null
}
$appsSubnetId = "$($vnet.id)/subnets/$AppsSubnetName"

$ZoneIds = @{}
foreach ($groupId in $PrivateDnsZones.Keys) {
    $zone = $PrivateDnsZones[$groupId]
    Write-Step "Private DNS zone $zone"
    if (-not (Test-AzResource @("network", "private-dns", "zone", "show", "-g", $ResourceGroup, "-n", $zone))) {
        Invoke-AzJson "Create $zone" (@(
            "network", "private-dns", "zone", "create", "-g", $ResourceGroup, "-n", $zone
        ) + $TagArguments) | Out-Null
    }
    $ZoneIds[$groupId] = (Invoke-AzJson "Read $zone" @(
        "network", "private-dns", "zone", "show", "-g", $ResourceGroup, "-n", $zone
    )).id
    if (-not (Test-AzResource @("network", "private-dns", "link", "vnet", "show", "-g", $ResourceGroup, "-z", $zone, "-n", $DnsLinkName))) {
        Invoke-AzJson "Link $zone to $VnetName" @(
            "network", "private-dns", "link", "vnet", "create", "-g", $ResourceGroup, "-z", $zone,
            "-n", $DnsLinkName, "-v", $vnet.id, "-e", "false"
        ) | Out-Null
    }
}

Initialize-PrivateEndpoint -Name "pe-storage-$Prefix" -TargetId $storage.id -GroupId "blob"
if ($vaultNames) {
    $vault = Invoke-AzJson "Read $($vaultNames[0])" @("keyvault", "show", "-g", $ResourceGroup, "-n", $vaultNames[0])
    Initialize-PrivateEndpoint -Name "pe-vault-$Prefix" -TargetId $vault.id -GroupId "vault"
}

# -------------------------------------------------------------
# VNet-integrated Container Apps environment
# -------------------------------------------------------------
Write-Step "Container Apps environment $EnvironmentName"
if (-not (Test-AzResource @("containerapp", "env", "show", "-g", $ResourceGroup, "-n", $EnvironmentName))) {
    $logs = Get-Property (Get-Property $sourceEnvironment.properties "appLogsConfiguration") "logAnalyticsConfiguration"
    $customerId = Get-Property $logs "customerId"
    $workspace = @(Invoke-AzJson "List Log Analytics workspaces" @(
        "monitor", "log-analytics", "workspace", "list", "-g", $ResourceGroup
    )) | Where-Object { $_ -and $_.customerId -eq $customerId } | Select-Object -First 1
    if (-not $workspace) { throw "Cannot find the Log Analytics workspace of the API environment." }
    $workspaceKeys = Invoke-AzJson "Read Log Analytics key" @(
        "monitor", "log-analytics", "workspace", "get-shared-keys", "-g", $ResourceGroup, "-n", $workspace.name
    )
    Invoke-AzJson "Create $EnvironmentName" (@(
        "containerapp", "env", "create", "-g", $ResourceGroup, "-n", $EnvironmentName, "-l", $Location,
        "--infrastructure-subnet-resource-id", $appsSubnetId, "--internal-only", "false",
        "--enable-workload-profiles", "true", "--logs-destination", "log-analytics",
        "--logs-workspace-id", $customerId, "--logs-workspace-key", $workspaceKeys.primarySharedKey
    ) + $TagArguments) | Out-Null
}
$targetEnvironment = Invoke-AzJson "Read $EnvironmentName" @("containerapp", "env", "show", "-g", $ResourceGroup, "-n", $EnvironmentName)
$attachedSubnet = Get-Property (Get-Property $targetEnvironment.properties "vnetConfiguration") "infrastructureSubnetId"
if ($attachedSubnet -ine $appsSubnetId) { throw "$EnvironmentName is not attached to $AppsSubnetName." }
$TargetEnvironmentId = $targetEnvironment.id
Write-Host "    Default domain: $($targetEnvironment.properties.defaultDomain)" -ForegroundColor Green

# -------------------------------------------------------------
# PostgreSQL (public access with the Azure services rule)
# -------------------------------------------------------------
$postgresHost = Get-AppSetting $api "POSTGRESQL_HOST"
if ($postgresHost) {
    $serverName = $postgresHost.Split(".")[0]
    Write-Step "PostgreSQL $serverName"
    $server = Invoke-AzJson "Read $serverName" @("postgres", "flexible-server", "show", "-g", $ResourceGroup, "-n", $serverName)
    if ($server.state -eq "Stopped") {
        Invoke-AzJson "Start $serverName" @("postgres", "flexible-server", "start", "-g", $ResourceGroup, "-n", $serverName) | Out-Null
        $server = Invoke-AzJson "Read $serverName" @("postgres", "flexible-server", "show", "-g", $ResourceGroup, "-n", $serverName)
    }
    Write-Host "    State: $($server.state)" -ForegroundColor Green
}

# -------------------------------------------------------------
# Workload migration (jobs first: they validate secrets and registry access before the API)
# -------------------------------------------------------------
if (-not $MigrateWorkloads) {
    Write-Host ""
    Write-Host "Network foundation ready. Rerun with -MigrateWorkloads to move the jobs and $ApiAppName." -ForegroundColor Cyan
    return
}
foreach ($job in $jobs) { Move-Workload -Kind "jobs" -Name $job.name }
Move-Workload -Kind "containerApps" -Name $ApiAppName

$apiFqdn = az containerapp show -g $ResourceGroup -n $ApiAppName --only-show-errors --query "properties.configuration.ingress.fqdn" -o tsv
Write-Host ""
Write-Host "API now runs in ${EnvironmentName}: https://$apiFqdn" -ForegroundColor Cyan
Write-Host "Next: .\infra\deploy.ps1 (rebuilds the backend and the frontend against the new API URL)." -ForegroundColor Cyan
