// =============================================================================
// PrevaIQ — Azure Infrastructure (Bicep)
// Deploys all Azure resources needed for the PrevaIQ application
// =============================================================================

targetScope = 'resourceGroup'

// Parameters
@description('Environment name (demo, dev, staging)')
param environment string = 'demo'

@description('Azure region for deployment')
param location string = resourceGroup().location

@description('Region of Azure AI Search (may differ from location when the region lacks Search capacity)')
param searchLocation string = location

@minLength(2)
@description('Project name used as prefix for resource names')
param projectName string = 'prevaiq'

@description('PostgreSQL database name. Kept as workbenchiq: the application schema and existing data live in it.')
param postgresDatabaseName string = 'workbenchiq'

@description('Brand display name (OpenTelemetry service name). BRAND_NAME itself is baked into the images.')
param brandName string = 'PrevaIQ'

@allowed(['Basic', 'Standard', 'Premium'])
@description('Container Registry SKU. Premium is required for dedicated build agent pools (demo uses Premium).')
param acrSku string = 'Basic'

@secure()
@description('API key for backend authentication (min 32 chars)')
param apiKey string

@description('Fabric API endpoint for Data Agent calls')
param fabricDataAgentEndpoint string = 'https://api.fabric.microsoft.com'

@description('Fabric workspace ID that contains the Data Agent item')
param fabricWorkspaceId string = ''

@description('Fabric Data Agent item ID')
param fabricDataAgentId string = ''

@description('PostgreSQL administrator login')
param pgAdminLogin string = 'prevaiqadmin'

@secure()
@description('PostgreSQL administrator password')
param pgAdminPassword string

@description('Wire the Web IQ key (Key Vault secret webiq-api-key) into the API app. Enable after running infra/set-webiq-secret.ps1.')
param webIqSecretEnabled bool = false

@description('Create the Container Apps. First provisioning: false, build the images (deploy.ps1 -BuildOnly), then true.')
param deployApps bool = true

@description('Object IDs of the people or pipelines running deploy.ps1, set-webiq-secret.ps1 and the maintenance scripts. They get the data-plane roles those need on Foundry, Key Vault and Storage, which Owner/Contributor does not include.')
param adminPrincipalIds array = []

@description('Optional private networking: a VNet for the Container Apps environment, private endpoints for Storage, Key Vault, AI Search and Foundry, and PostgreSQL private access. Mirrors private_networking_enabled in infra/terraform.')
param privateNetworkingEnabled bool = false

@description('Address space of the VNet (must be a /16 for the subnet layout). Used only when privateNetworkingEnabled is true.')
param vnetAddressSpace string = '10.60.0.0/16'

@description('Public IPs or CIDR ranges allowed through the Storage, Key Vault, AI Search and Foundry firewalls when privateNetworkingEnabled is true, so deploy.ps1 and set-webiq-secret.ps1 still work from an operator machine. Empty keeps those services private-only.')
param adminIpRanges array = []

// Naming convention
var prefix = '${projectName}-${environment}'
var uniqueSuffix = uniqueString(resourceGroup().id, projectName)
var dataContainerName = '${projectName}-data'

// Public access stays on unless private networking is enabled without operator IPs.
var publicAccess = !privateNetworkingEnabled || length(adminIpRanges) > 0
var publicNetworkAccess = publicAccess ? 'Enabled' : 'Disabled'
var restrictPublic = privateNetworkingEnabled && publicAccess
var adminIpRules = [for ip in adminIpRanges: { value: ip }]

// Tags applied to all resources
var tags = {
  SecurityControl: 'ignore'
  CostControl: 'ignore'
  Project: projectName
  Environment: environment
}

// =============================================================================
// Log Analytics Workspace (required by Container Apps)
// =============================================================================
resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-${prefix}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// =============================================================================
// Application Insights (APM + OpenTelemetry traces for Foundry agents)
// =============================================================================
resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-${prefix}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
    IngestionMode: 'LogAnalytics'
    RetentionInDays: 30
  }
}

// =============================================================================
// User-Assigned Managed Identity (avoids chicken-and-egg with ACA)
// =============================================================================
resource managedIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-${prefix}'
  location: location
  tags: tags
}

// =============================================================================
// Container Registry
// =============================================================================
resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: 'acr${projectName}${environment}'
  location: location
  tags: tags
  sku: { name: acrSku }
  properties: {
    adminUserEnabled: false
  }
}

// AcrPull role for managed identity
resource acrPullRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(acr.id, managedIdentity.id, 'acrpull')
  scope: acr
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7f951dda-4ed3-4680-a7ca-43fe172d538d') // AcrPull
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// =============================================================================
// Key Vault — application secrets (Web IQ API key), read by the managed identity.
// The secret value is written out-of-band by infra/set-webiq-secret.ps1 (never in IaC).
// =============================================================================
resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: 'kv-${prefix}'
  location: location
  tags: tags
  properties: {
    tenantId: subscription().tenantId
    sku: { family: 'A', name: 'standard' }
    enableRbacAuthorization: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: true
    publicNetworkAccess: publicNetworkAccess
    networkAcls: restrictPublic ? {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
      ipRules: adminIpRules
    } : null
  }
}

resource keyVaultSecretsUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, managedIdentity.id, 'kvsecretsuser')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6') // Key Vault Secrets User
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Only reference the secret once it exists, otherwise the revision cannot resolve it.
var webIqSecrets = webIqSecretEnabled ? [
  {
    name: 'webiq-api-key'
    keyVaultUrl: '${keyVault.properties.vaultUri}secrets/webiq-api-key'
    identity: managedIdentity.id
  }
] : []
var webIqEnv = webIqSecretEnabled ? [
  { name: 'WEBIQ_API_KEY', secretRef: 'webiq-api-key' }
] : []

// =============================================================================
// Storage Account + Blob Container
// =============================================================================
resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: take('st${projectName}${uniqueSuffix}', 24)
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    allowSharedKeyAccess: false
    supportsHttpsTrafficOnly: true
    publicNetworkAccess: publicNetworkAccess
    // Selected networks: the Foundry blob connection reaches the account as a trusted resource instance.
    networkAcls: restrictPublic ? {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
      ipRules: adminIpRules
      resourceAccessRules: [
        { tenantId: subscription().tenantId, resourceId: foundryAccount.id }
      ]
    } : null
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

resource blobContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: dataContainerName
}

resource correctionsContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'corrections'
}

// =============================================================================
// Microsoft Foundry (AIServices) account + project — hosts the OpenAI model
// deployments, Content Understanding and the Foundry Agent Service.
// =============================================================================
resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: 'ai-${projectName}-foundry'
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    // Subdomain == account name: deploy.ps1 derives the account from the endpoint host.
    customSubDomainName: 'ai-${projectName}-foundry'
    allowProjectManagement: true
    publicNetworkAccess: publicNetworkAccess
    disableLocalAuth: true
    networkAcls: restrictPublic ? {
      defaultAction: 'Deny'
      bypass: 'AzureServices'
      ipRules: adminIpRules
    } : null
  }
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: foundryAccount
  name: 'ai-${projectName}-project'
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {}
}

var openAiEndpointUrl = foundryAccount.properties.endpoint

// Foundry project connections
resource foundryBlobConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2026-01-15-preview' = {
  parent: foundryProject
  name: '${projectName}-blob'
  properties: {
    authType: 'AAD'
    category: 'AzureBlob'
    target: storageAccount.properties.primaryEndpoints.blob
    metadata: {
      AccountName: storageAccount.name
      ContainerName: dataContainerName
      ResourceId: storageAccount.id
    }
  }
}

resource foundrySearchConnection 'Microsoft.CognitiveServices/accounts/projects/connections@2026-01-15-preview' = {
  parent: foundryProject
  name: '${projectName}-search'
  properties: {
    authType: 'AAD'
    category: 'CognitiveSearch'
    target: 'https://${searchService.name}.search.windows.net'
    metadata: {
      ResourceId: searchService.id
    }
  }
}

// Storage Blob Data Contributor role for managed identity
resource storageBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, managedIdentity.id, 'blobcontributor')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe') // Storage Blob Data Contributor
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// =============================================================================
// Azure OpenAI model deployments on the Foundry account
// (GA, reasoning low): gpt-5.4-mini for chat/analysis/CU, gpt-5.4-nano for light tasks,
// text-embedding-3-large for Content Understanding, text-embedding-3-small for RAG.
// =============================================================================

// GPT-5.4 nano — background labels, folder titles, classification, JSON cleanup
resource gpt54NanoDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: foundryAccount
  name: 'gpt-5.4-nano'
  dependsOn: [foundryProject] // account-level operations must not overlap (409 RequestConflict)
  sku: {
    name: 'GlobalStandard'
    capacity: 50
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.4-nano'
      version: '2026-03-17'
    }
  }
}

// GPT-5.4 mini — primary model: chat, agents, workflows, fraud vision/reasoning, CU completion
resource gpt54MiniDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: foundryAccount
  name: 'gpt-5.4-mini'
  dependsOn: [gpt54NanoDeployment] // sequential to avoid 409 RequestConflict
  sku: {
    name: 'GlobalStandard'
    capacity: 100
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5.4-mini'
      version: '2026-03-17'
    }
  }
}

// text-embedding-3-large — Content Understanding analyzer embeddings
resource embeddingLargeDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: foundryAccount
  name: 'text-embedding-3-large'
  dependsOn: [gpt54MiniDeployment]
  sku: {
    name: 'GlobalStandard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-large'
      version: '1'
    }
  }
}

// text-embedding-3-small — RAG (pgvector) embeddings
resource embeddingSmallDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: foundryAccount
  name: 'text-embedding-3-small'
  dependsOn: [embeddingLargeDeployment]
  sku: {
    name: 'GlobalStandard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'text-embedding-3-small'
      version: '1'
    }
  }
}

// Cognitive Services OpenAI User role for managed identity on the Foundry account
resource openAiRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundryAccount.id, managedIdentity.id, 'openaiuser')
  scope: foundryAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd') // Cognitive Services OpenAI User
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// =============================================================================
// Azure AI Search (for corrections semantic retrieval)
// =============================================================================
resource searchService 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: 'srch-${prefix}'
  location: searchLocation
  tags: tags
  sku: { name: 'basic' }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    authOptions: {
      aadOrApiKey: {
        aadAuthFailureMode: 'http401WithBearerChallenge'
      }
    }
    publicNetworkAccess: publicAccess ? 'enabled' : 'disabled'
    networkRuleSet: restrictPublic ? {
      bypass: 'AzureServices'
      ipRules: adminIpRules
    } : null
  }
}

// Search Index Data Contributor role for managed identity
resource searchRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(searchService.id, managedIdentity.id, 'searchcontrib')
  scope: searchService
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8ebe5a00-799e-43f5-93ac-243d3dce84a7') // Search Index Data Contributor
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// Search Service Contributor role for managed identity (manage indexes)
resource searchServiceContribRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(searchService.id, managedIdentity.id, 'searchsvccontrib')
  scope: searchService
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7ca78c08-252a-4471-8644-bb5ff32d4ba0') // Search Service Contributor
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// =============================================================================
// Azure Content Understanding — uses the same AIServices (Foundry) account as OpenAI.
// No separate CU resource needed.
// =============================================================================

// Cognitive Services User role for managed identity (required for CU API calls)
resource cuRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundryAccount.id, managedIdentity.id, 'coguser')
  scope: foundryAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908') // Cognitive Services User
    principalId: managedIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// =============================================================================
// Foundry project identity — backs the Entra-authenticated project connections (Storage, AI Search)
// =============================================================================
resource projectStorageBlobRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, foundryProject.id, 'blobcontributor')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe') // Storage Blob Data Contributor
    principalId: foundryProject.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource projectSearchRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(searchService.id, foundryProject.id, 'searchcontrib')
  scope: searchService
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '8ebe5a00-799e-43f5-93ac-243d3dce84a7') // Search Index Data Contributor
    principalId: foundryProject.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource projectSearchServiceRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(searchService.id, foundryProject.id, 'searchsvccontrib')
  scope: searchService
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '7ca78c08-252a-4471-8644-bb5ff32d4ba0') // Search Service Contributor
    principalId: foundryProject.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// =============================================================================
// Operators — data-plane roles for deploy.ps1, set-webiq-secret.ps1 and the maintenance scripts
// =============================================================================
resource adminFoundryRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for principalId in adminPrincipalIds: {
  name: guid(foundryAccount.id, principalId, 'coguser')
  scope: foundryAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'a97b65f3-24c7-4388-baec-2e87135dc908') // Cognitive Services User
    principalId: principalId
  }
}]

resource adminKeyVaultRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for principalId in adminPrincipalIds: {
  name: guid(keyVault.id, principalId, 'kvsecretsofficer')
  scope: keyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7') // Key Vault Secrets Officer
    principalId: principalId
  }
}]

resource adminStorageRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = [for principalId in adminPrincipalIds: {
  name: guid(storageAccount.id, principalId, 'blobcontributor')
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe') // Storage Blob Data Contributor
    principalId: principalId
  }
}]

// =============================================================================
// Optional private networking (privateNetworkingEnabled) — mirrors infra/terraform/network.tf.
// The Container Apps environment joins the VNet and reaches Storage, Key Vault, AI Search and
// Foundry through private endpoints; PostgreSQL uses private access. ACR stays public (RBAC-protected,
// ACR Tasks builds need it).
// =============================================================================
var privateDnsZoneNames = [
  'privatelink.blob.core.windows.net'
  'privatelink.vaultcore.azure.net'
  'privatelink.search.windows.net'
  'privatelink.cognitiveservices.azure.com'
  'privatelink.openai.azure.com'
  'privatelink.services.ai.azure.com'
]
var postgresPrivateDnsZoneName = '${prefix}.private.postgres.database.azure.com'

resource vnet 'Microsoft.Network/virtualNetworks@2024-05-01' = if (privateNetworkingEnabled) {
  name: 'vnet-${prefix}'
  location: location
  tags: tags
  properties: {
    addressSpace: { addressPrefixes: [vnetAddressSpace] }
    subnets: [
      {
        // Workload profiles environment: at least a /27, delegated to Microsoft.App/environments
        name: 'snet-apps'
        properties: {
          addressPrefix: cidrSubnet(vnetAddressSpace, 26, 0)
          delegations: [
            {
              name: 'container-apps'
              properties: { serviceName: 'Microsoft.App/environments' }
            }
          ]
        }
      }
      {
        name: 'snet-private-endpoints'
        properties: {
          addressPrefix: cidrSubnet(vnetAddressSpace, 24, 1)
        }
      }
      {
        name: 'snet-postgres'
        properties: {
          addressPrefix: cidrSubnet(vnetAddressSpace, 24, 2)
          delegations: [
            {
              name: 'postgres'
              properties: { serviceName: 'Microsoft.DBforPostgreSQL/flexibleServers' }
            }
          ]
        }
      }
    ]
  }
}

resource privateDnsZones 'Microsoft.Network/privateDnsZones@2020-06-01' = [for zone in (privateNetworkingEnabled ? privateDnsZoneNames : []): {
  name: zone
  location: 'global'
  tags: tags
}]

resource privateDnsZoneLinks 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = [for (zone, i) in (privateNetworkingEnabled ? privateDnsZoneNames : []): {
  parent: privateDnsZones[i]
  name: 'link-${prefix}'
  location: 'global'
  tags: tags
  properties: {
    registrationEnabled: false
    virtualNetwork: { id: vnet!.id }
  }
}]

resource postgresPrivateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = if (privateNetworkingEnabled) {
  name: postgresPrivateDnsZoneName
  location: 'global'
  tags: tags
}

resource postgresPrivateDnsZoneLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = if (privateNetworkingEnabled) {
  name: '${postgresPrivateDnsZoneName}/link-${prefix}'
  location: 'global'
  tags: tags
  properties: {
    registrationEnabled: false
    virtualNetwork: { id: vnet!.id }
  }
}

// Private endpoints: one per Private Link target, each with its DNS zone group.
resource peStorage 'Microsoft.Network/privateEndpoints@2024-05-01' = if (privateNetworkingEnabled) {
  name: 'pe-storage-${prefix}'
  location: location
  tags: tags
  properties: {
    subnet: { id: '${vnet!.id}/subnets/snet-private-endpoints' }
    privateLinkServiceConnections: [
      {
        name: 'psc-storage'
        properties: { privateLinkServiceId: storageAccount.id, groupIds: ['blob'] }
      }
    ]
  }
}

resource peStorageDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = if (privateNetworkingEnabled) {
  name: 'pe-storage-${prefix}/default'
  dependsOn: [privateDnsZoneLinks, peStorage]
  properties: {
    privateDnsZoneConfigs: [
      { name: 'blob', properties: { privateDnsZoneId: resourceId('Microsoft.Network/privateDnsZones', 'privatelink.blob.core.windows.net') } }
    ]
  }
}

resource peVault 'Microsoft.Network/privateEndpoints@2024-05-01' = if (privateNetworkingEnabled) {
  name: 'pe-vault-${prefix}'
  location: location
  tags: tags
  properties: {
    subnet: { id: '${vnet!.id}/subnets/snet-private-endpoints' }
    privateLinkServiceConnections: [
      {
        name: 'psc-vault'
        properties: { privateLinkServiceId: keyVault.id, groupIds: ['vault'] }
      }
    ]
  }
}

resource peVaultDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = if (privateNetworkingEnabled) {
  name: 'pe-vault-${prefix}/default'
  dependsOn: [privateDnsZoneLinks, peVault]
  properties: {
    privateDnsZoneConfigs: [
      { name: 'vault', properties: { privateDnsZoneId: resourceId('Microsoft.Network/privateDnsZones', 'privatelink.vaultcore.azure.net') } }
    ]
  }
}

resource peSearch 'Microsoft.Network/privateEndpoints@2024-05-01' = if (privateNetworkingEnabled) {
  name: 'pe-search-${prefix}'
  location: location
  tags: tags
  properties: {
    subnet: { id: '${vnet!.id}/subnets/snet-private-endpoints' }
    privateLinkServiceConnections: [
      {
        name: 'psc-search'
        properties: { privateLinkServiceId: searchService.id, groupIds: ['searchService'] }
      }
    ]
  }
}

resource peSearchDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = if (privateNetworkingEnabled) {
  name: 'pe-search-${prefix}/default'
  dependsOn: [privateDnsZoneLinks, peSearch]
  properties: {
    privateDnsZoneConfigs: [
      { name: 'search', properties: { privateDnsZoneId: resourceId('Microsoft.Network/privateDnsZones', 'privatelink.search.windows.net') } }
    ]
  }
}

resource peFoundry 'Microsoft.Network/privateEndpoints@2024-05-01' = if (privateNetworkingEnabled) {
  name: 'pe-foundry-${prefix}'
  location: location
  tags: tags
  properties: {
    subnet: { id: '${vnet!.id}/subnets/snet-private-endpoints' }
    privateLinkServiceConnections: [
      {
        name: 'psc-foundry'
        properties: { privateLinkServiceId: foundryAccount.id, groupIds: ['account'] }
      }
    ]
  }
  // The Foundry account takes one write at a time: attach the endpoint after the model deployments.
  dependsOn: [embeddingSmallDeployment]
}

resource peFoundryDns 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = if (privateNetworkingEnabled) {
  name: 'pe-foundry-${prefix}/default'
  dependsOn: [privateDnsZoneLinks, peFoundry]
  properties: {
    privateDnsZoneConfigs: [
      { name: 'cognitiveservices', properties: { privateDnsZoneId: resourceId('Microsoft.Network/privateDnsZones', 'privatelink.cognitiveservices.azure.com') } }
      { name: 'openai', properties: { privateDnsZoneId: resourceId('Microsoft.Network/privateDnsZones', 'privatelink.openai.azure.com') } }
      { name: 'ai-services', properties: { privateDnsZoneId: resourceId('Microsoft.Network/privateDnsZones', 'privatelink.services.ai.azure.com') } }
    ]
  }
}

// =============================================================================
// PostgreSQL Flexible Server (with pgvector)
// =============================================================================
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: 'pg-${prefix}'
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'Standard_D2ds_v4'
    tier: 'GeneralPurpose'
  }
  properties: {
    version: '16'
    administratorLogin: pgAdminLogin
    administratorLoginPassword: pgAdminPassword
    storage: { storageSizeGB: 32 }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: { mode: 'Disabled' }
    // Private access: delegated subnet and private DNS zone instead of a public endpoint.
    network: privateNetworkingEnabled ? {
      delegatedSubnetResourceId: '${vnet!.id}/subnets/snet-postgres'
      privateDnsZoneArmResourceId: postgresPrivateDnsZone!.id
      publicNetworkAccess: 'Disabled'
    } : {
      publicNetworkAccess: 'Enabled'
    }
  }
  dependsOn: privateNetworkingEnabled ? [postgresPrivateDnsZoneLink] : []
}

// Allow-list pgvector + extensions used by scripts/setup_postgresql_rag.py (hybrid trigram search)
resource pgExtensions 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: postgres
  name: 'azure.extensions'
  properties: {
    value: 'vector,uuid-ossp,pg_trgm'
    source: 'user-override'
  }
}

// Set wal_level=logical (required for Fabric Mirroring / CDC)
resource pgWalLevel 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: postgres
  name: 'wal_level'
  dependsOn: [pgExtensions]
  properties: {
    value: 'logical'
    source: 'user-override'
  }
}

// Allow Azure services to connect (public mode only: private mode relies on the delegated subnet)
resource pgFirewallAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = if (!privateNetworkingEnabled) {
  parent: postgres
  name: 'AllowAzureServices'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// Database
resource pgDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: postgresDatabaseName
}

// =============================================================================
// Container Apps Environment
// =============================================================================
resource acaEnv 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-${prefix}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
    // Private mode: the environment joins the delegated apps subnet (workload profiles, as in Terraform).
    vnetConfiguration: privateNetworkingEnabled ? {
      infrastructureSubnetId: '${vnet!.id}/subnets/snet-apps'
      internal: false
    } : null
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}
// =============================================================================
resource apiApp 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: 'ca-api-${environment}'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: acaEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'http'
        allowInsecure: false
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: managedIdentity.id
        }
      ]
      secrets: concat([
        { name: 'api-key', value: apiKey }
        { name: 'pg-password', value: pgAdminPassword }
      ], webIqSecrets)
    }
    template: {
      containers: [
        {
          name: 'api'
          image: '${acr.properties.loginServer}/${projectName}-api:latest'
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: concat([
            { name: 'API_KEY', secretRef: 'api-key' }
            { name: 'AZURE_CLIENT_ID', value: managedIdentity.properties.clientId }
            { name: 'AZURE_CONTENT_UNDERSTANDING_ENDPOINT', value: openAiEndpointUrl }
            { name: 'AZURE_CONTENT_UNDERSTANDING_USE_AZURE_AD', value: 'true' }
            { name: 'AZURE_CONTENT_UNDERSTANDING_COMPLETION_DEPLOYMENT', value: 'gpt-5.4-mini' }
            { name: 'AZURE_CONTENT_UNDERSTANDING_EMBEDDING_DEPLOYMENT', value: 'text-embedding-3-large' }
            { name: 'AZURE_OPENAI_ENDPOINT', value: openAiEndpointUrl }
            { name: 'AZURE_OPENAI_USE_AZURE_AD', value: 'true' }
            { name: 'AZURE_OPENAI_DEPLOYMENT_NAME', value: 'gpt-5.4-mini' }
            { name: 'AZURE_OPENAI_MODEL_NAME', value: 'gpt-5.4-mini' }
            { name: 'AZURE_OPENAI_CHAT_DEPLOYMENT_NAME', value: 'gpt-5.4-mini' }
            { name: 'AZURE_OPENAI_CHAT_MODEL_NAME', value: 'gpt-5.4-mini' }
            { name: 'AZURE_OPENAI_NANO_DEPLOYMENT_NAME', value: 'gpt-5.4-nano' }
            { name: 'AZURE_OPENAI_NANO_MODEL_NAME', value: 'gpt-5.4-nano' }
            { name: 'AZURE_OPENAI_API_VERSION', value: '2025-04-01-preview' }
            { name: 'AZURE_OPENAI_REASONING_EFFORT', value: 'low' }
            // Fraud detection — 2-model pipeline
            { name: 'FRAUD_VISION_DEPLOYMENT', value: 'gpt-5.4-mini' }
            { name: 'FRAUD_VISION_MODEL', value: 'gpt-5.4-mini' }
            { name: 'FRAUD_DETECTION_DEPLOYMENT', value: 'gpt-5.4-mini' }
            { name: 'FRAUD_DETECTION_MODEL', value: 'gpt-5.4-mini' }
            { name: 'STORAGE_BACKEND', value: 'azure_blob' }
            { name: 'AZURE_STORAGE_AUTH_MODE', value: 'default' }
            { name: 'AZURE_STORAGE_ACCOUNT_NAME', value: storageAccount.name }
            { name: 'AZURE_STORAGE_CONTAINER_NAME', value: dataContainerName }
            { name: 'DATABASE_BACKEND', value: 'postgresql' }
            { name: 'POSTGRESQL_HOST', value: postgres.properties.fullyQualifiedDomainName }
            { name: 'POSTGRESQL_PORT', value: '5432' }
            { name: 'POSTGRESQL_DATABASE', value: pgDatabase.name }
            { name: 'POSTGRESQL_USER', value: pgAdminLogin }
            { name: 'POSTGRESQL_PASSWORD', secretRef: 'pg-password' }
            { name: 'POSTGRESQL_SSL_MODE', value: 'require' }
            { name: 'RAG_ENABLED', value: 'true' }
            { name: 'EMBEDDING_DEPLOYMENT', value: 'text-embedding-3-small' }
            // Agent Framework
            { name: 'AGENT_FRAMEWORK_ENABLED', value: 'true' }
            // OpenTelemetry → Application Insights (agent spans for Foundry)
            { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: appInsights.properties.ConnectionString }
            { name: 'OTEL_SERVICE_NAME', value: brandName }
            { name: 'OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT', value: 'true' }
            // Fabric Data Agent (set real IDs after creating Data Agent in Fabric)
            { name: 'FABRIC_DATA_AGENT_ENDPOINT', value: fabricDataAgentEndpoint }
            { name: 'FABRIC_WORKSPACE_ID', value: fabricWorkspaceId }
            { name: 'FABRIC_DATA_AGENT_ID', value: fabricDataAgentId }
            // Azure AI Search (corrections index)
            { name: 'AZURE_SEARCH_ENDPOINT', value: 'https://${searchService.name}.search.windows.net' }
            { name: 'AZURE_SEARCH_INDEX_NAME', value: 'corrections' }
            // Web Intelligence Agent (Foundry Agent Service + Bing WebSearch)
            { name: 'WEB_INTELLIGENCE_ENABLED', value: 'true' }
            { name: 'FOUNDRY_PROJECT_ENDPOINT', value: '${foundryAccount.properties.endpoint}/api/projects/${foundryProject.name}' }
            { name: 'WEB_INTELLIGENCE_AGENT_NAME', value: 'PrevaIQ-WebIntelligence' }
          ], webIqEnv)
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
      }
    }
  }
  dependsOn: [acrPullRole, keyVaultSecretsUserRole, openAiRole, cuRole, embeddingSmallDeployment]
}

// =============================================================================
// Container App — Frontend
// =============================================================================
resource frontendApp 'Microsoft.App/containerApps@2024-03-01' = if (deployApps) {
  name: 'ca-frontend-${environment}'
  location: location
  tags: tags
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: {
      '${managedIdentity.id}': {}
    }
  }
  properties: {
    managedEnvironmentId: acaEnv.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 3000
        transport: 'http'
        allowInsecure: false
      }
      registries: [
        {
          server: acr.properties.loginServer
          identity: managedIdentity.id
        }
      ]
      secrets: [
        { name: 'api-key', value: apiKey }
      ]
    }
    template: {
      containers: [
        {
          name: 'frontend'
          image: '${acr.properties.loginServer}/${projectName}-frontend:latest'
          resources: {
            cpu: json('0.25')
            memory: '0.5Gi'
          }
          env: [
            { name: 'API_URL', value: 'https://${apiApp!.properties.configuration.ingress.fqdn}' }
            { name: 'API_KEY', secretRef: 'api-key' }
            { name: 'HOSTNAME', value: '0.0.0.0' }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 2
      }
    }
  }
  dependsOn: [acrPullRole]
}

// =============================================================================
// Outputs
// =============================================================================
output acrLoginServer string = acr.properties.loginServer
output containerAppsDefaultDomain string = acaEnv.properties.defaultDomain
output apiAppUrl string = deployApps ? 'https://${apiApp!.properties.configuration.ingress.fqdn}' : ''
output frontendAppUrl string = deployApps ? 'https://${frontendApp!.properties.configuration.ingress.fqdn}' : ''
output openAiEndpoint string = openAiEndpointUrl
output contentUnderstandingEndpoint string = openAiEndpointUrl
output foundryAccountName string = foundryAccount.name
output foundryProjectName string = foundryProject.name
output storageAccountName string = storageAccount.name
output postgresHost string = postgres.properties.fullyQualifiedDomainName
output managedIdentityClientId string = managedIdentity.properties.clientId
output keyVaultName string = keyVault.name
output appInsightsConnectionString string = appInsights.properties.ConnectionString
