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

// Secrets — provide at deploy time
param apiKey = readEnvironmentVariable('PREVAIQ_API_KEY', '')
param pgAdminPassword = readEnvironmentVariable('PREVAIQ_PG_PASSWORD', '')
