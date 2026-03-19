// ---------------------------------------------------------------------------
// vision.bicep — Azure AI Vision (Computer Vision S1)
//
// Used for:
//   • Image analysis (caption, tags, objects)
//   • Multimodal embeddings: vectorizeImage + vectorizeText (1024-d)
//
// Auth: Entra ID (Cognitive Services User role)
// ---------------------------------------------------------------------------

@description('Name of the Computer Vision account (must be globally unique).')
param name string

@description('Azure region.')
param location string

@description('Resource tags.')
param tags object = {}

@description('Principal ID of the managed identity to grant Cognitive Services User.')
param principalId string

resource visionAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: name
  location: location
  tags: tags
  kind: 'ComputerVision'
  sku: {
    name: 'S1'
  }
  properties: {
    customSubDomainName: name
    publicNetworkAccess: 'Enabled'
  }
}

// Cognitive Services User — inference access (analyze, vectorize)
var csUserRoleId = 'a97b65f3-24c7-4388-baec-2e87135dc908'

resource csUserAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(visionAccount.id, principalId, csUserRoleId)
  scope: visionAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', csUserRoleId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Outputs ────────────────────────────────────────────────────────────────
@description('Vision account endpoint')
output endpoint string = visionAccount.properties.endpoint

@description('Vision account name')
output accountName string = visionAccount.name
