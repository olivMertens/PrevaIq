targetScope = 'resourceGroup'

// Azure Monitor log alerts on the API telemetry. Mirrors infra/terraform/alerts.tf.
// Module of main.bicep; also deployable alone on an existing environment (docs/deployment.md).

@description('Resource name prefix: <projectName>-<environment>.')
param prefix string

param location string = resourceGroup().location

@description('Log Analytics workspace that receives the Application Insights telemetry.')
param workspaceId string

@description('Optional email notified when an alert fires. Empty: alerts only show in Azure Monitor.')
param alertEmail string = ''

param tags object = {}

// Any match within 15 minutes fires; the alert resolves itself once matches stop.
var rules = [
  {
    name: 'api-5xx'
    description: 'The API answered HTTP 5xx.'
    query: 'AppRequests | where toint(ResultCode) >= 500'
  }
  {
    name: 'analysis-failures'
    description: 'Analysis steps failed: the case shows the AI pipeline problem badge. The message names the application and the steps.'
    query: 'AppTraces | where Message startswith "Analysis steps failed for application"'
  }
]

resource actionGroup 'Microsoft.Insights/actionGroups@2023-01-01' = if (!empty(alertEmail)) {
  name: 'ag-${prefix}'
  location: 'global'
  tags: tags
  properties: {
    groupShortName: take(replace(prefix, '-', ''), 12)
    enabled: true
    emailReceivers: [
      {
        name: 'operator'
        emailAddress: alertEmail
        useCommonAlertSchema: true
      }
    ]
  }
}

resource alerts 'Microsoft.Insights/scheduledQueryRules@2023-12-01' = [
  for rule in rules: {
    name: 'alert-${prefix}-${rule.name}'
    location: location
    tags: tags
    kind: 'LogAlert'
    properties: {
      description: rule.description
      severity: 2
      enabled: true
      scopes: [workspaceId]
      evaluationFrequency: 'PT15M'
      windowSize: 'PT15M'
      autoMitigate: true
      // The App* tables only exist once telemetry has arrived in a new workspace.
      skipQueryValidation: true
      criteria: {
        allOf: [
          {
            query: rule.query
            timeAggregation: 'Count'
            operator: 'GreaterThan'
            threshold: 0
            failingPeriods: {
              numberOfEvaluationPeriods: 1
              minFailingPeriodsToAlert: 1
            }
          }
        ]
      }
      actions: {
        actionGroups: empty(alertEmail) ? [] : [actionGroup.id]
      }
    }
  }
]
