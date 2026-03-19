// ---------------------------------------------------------------------------
// search.bicep — Azure AI Search (Standard S1+ for Semantic Ranker)
// ---------------------------------------------------------------------------

@description('Name of the Azure AI Search service (must be globally unique).')
param name string

@description('Azure region.')
param location string

@description('Resource tags.')
param tags object = {}

@description('Search service SKU. Use "standard" for Semantic Ranker support.')
param sku string = 'standard'

resource searchService 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: name
  location: location
  tags: tags
  sku: {
    name: sku
  }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    publicNetworkAccess: 'enabled'
    semanticSearch: 'free'
  }
}

// ── Outputs ────────────────────────────────────────────────────────────────
@description('Search service endpoint URL')
output endpoint string = 'https://${searchService.name}.search.windows.net'

@description('Primary admin API key')
#disable-next-line outputs-should-not-contain-secrets
output adminKey string = searchService.listAdminKeys().primaryKey
