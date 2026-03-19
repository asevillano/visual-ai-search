// ---------------------------------------------------------------------------
// openai.bicep — Azure OpenAI account + model deployments
//
// Deploys:
//   • text-embedding-3-large (3072-d text embeddings)
//   • gpt-4.1 (image analysis via GPT Vision)
//
// Auth: Entra ID (Cognitive Services OpenAI User role)
// ---------------------------------------------------------------------------

@description('Name of the Azure OpenAI account (must be globally unique).')
param name string

@description('Azure region.')
param location string

@description('Resource tags.')
param tags object = {}

@description('Model deployments. Each: { name, model, version, skuName?, capacity? }')
param deployments array = []

@description('Principal ID of the managed identity to grant OpenAI User role.')
param principalId string

resource openaiAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: name
  location: location
  tags: tags
  kind: 'OpenAI'
  sku: {
    name: 'S0'
  }
  properties: {
    customSubDomainName: name
    publicNetworkAccess: 'Enabled'
  }
}

// ── Model deployments ──────────────────────────────────────────────────────
@batchSize(1)
resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = [
  for d in deployments: {
    parent: openaiAccount
    name: d.name
    sku: {
      name: d.?skuName ?? 'Standard'
      capacity: d.?capacity ?? 10
    }
    properties: {
      model: {
        format: 'OpenAI'
        name: d.model
        version: d.version
      }
    }
  }
]

// Cognitive Services OpenAI User — chat/completions + embeddings inference
var csOpenAIUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

resource csOpenAIUserAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(openaiAccount.id, principalId, csOpenAIUserRoleId)
  scope: openaiAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', csOpenAIUserRoleId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Outputs ────────────────────────────────────────────────────────────────
@description('Azure OpenAI endpoint')
output endpoint string = openaiAccount.properties.endpoint

@description('Azure OpenAI account name')
output accountName string = openaiAccount.name

@description('Names of deployed models')
output deploymentNames array = [for (d, i) in deployments: modelDeployment[i].name]
