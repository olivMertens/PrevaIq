using 'main.bicep'

param environment = 'demo'
param location = 'swedencentral'
// Sweden Central had no AI Search capacity at provisioning time (InsufficientResourcesAvailable)
param searchLocation = 'francecentral'
param projectName = 'prevaiq'
param brandName = 'PrevaIQ'
param pgAdminLogin = 'prevaiqadmin'

// Private networking (optional, default off). Mirrors infra/terraform variables.
param privateNetworkingEnabled = false
param vnetAddressSpace = '10.60.0.0/16'
param adminIpRanges = []

// Aurora endpoint uses Key authentication. After running set-aurora-endpoint-secret.ps1,
// provide the initial-condition Blob URL and enable these parameters for deployment:
// param auroraFoundryEndpoint = 'https://ol-workspace-aurora-fqedr.swedencentral.inference.ml.azure.com/score'
param auroraEndpointExpiresAt = '2026-11-13T05:59:39.304Z'
// param auroraEndpointKeySecretEnabled = true
// param auroraInitialConditionBlobUrl = 'https://<storage>.blob.core.windows.net/<container>/initial.nc'
// param auroraEnabled = true

// Secrets — provide at deploy time
param apiKey = readEnvironmentVariable('PREVAIQ_API_KEY', '')
param pgAdminPassword = readEnvironmentVariable('PREVAIQ_PG_PASSWORD', '')

// Optional email for the Azure Monitor alerts (infra/alerts.bicep); kept out of the repository.
param alertEmail = readEnvironmentVariable('PREVAIQ_ALERT_EMAIL', '')
