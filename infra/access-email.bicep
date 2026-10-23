targetScope = 'resourceGroup'

param projectName string = 'prevaiq'
param environment string = 'demo'
param identityPrincipalId string
@description('Email data residency geography, not an Azure resource region.')
param dataLocation string = 'Europe'

var prefix = '${projectName}-${environment}'
var tags = {
  SecurityControl: 'ignore'
  CostControl: 'ignore'
  Project: projectName
  Environment: environment
}

resource email 'Microsoft.Communication/emailServices@2023-03-31' = {
  name: 'email-${prefix}'
  location: 'global'
  tags: tags
  properties: {
    dataLocation: dataLocation
  }
}

resource domain 'Microsoft.Communication/emailServices/domains@2023-03-31' = {
  parent: email
  name: 'AzureManagedDomain'
  location: 'global'
  tags: tags
  properties: {
    domainManagement: 'AzureManaged'
    userEngagementTracking: 'Disabled'
  }
}

resource communication 'Microsoft.Communication/communicationServices@2023-03-31' = {
  name: 'acs-${prefix}'
  location: 'global'
  tags: tags
  properties: {
    dataLocation: dataLocation
    linkedDomains: [domain.id]
  }
}

// ACS Entra sending uses the service write action; no keys, deletion or role management.
resource senderRole 'Microsoft.Authorization/roleDefinitions@2022-04-01' = {
  name: guid(resourceGroup().id, prefix, 'access-email-sender')
  properties: {
    roleName: '${prefix}-access-email-sender'
    description: 'Submit access-request emails using Entra authentication on the dedicated ACS resource.'
    type: 'CustomRole'
    assignableScopes: [resourceGroup().id]
    permissions: [
      {
        actions: [
          'Microsoft.Communication/CommunicationServices/read'
          'Microsoft.Communication/CommunicationServices/write'
        ]
        notActions: []
        dataActions: []
        notDataActions: []
      }
    ]
  }
}

resource senderAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(communication.id, identityPrincipalId, senderRole.id)
  scope: communication
  properties: {
    principalId: identityPrincipalId
    principalType: 'ServicePrincipal'
    roleDefinitionId: senderRole.id
  }
}

output endpoint string = 'https://${communication.properties.hostName}'
output senderAddress string = 'DoNotReply@${domain.properties.fromSenderDomain}'
