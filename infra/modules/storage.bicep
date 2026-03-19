// ---------------------------------------------------------------------------
// storage.bicep — Azure Blob Storage for image originals & thumbnails
//
// Creates a GPv2 Storage Account with:
//   • Shared key access enabled (connection string auth)
//   • Two private blob containers: originals, thumbnails
//   • No public blob access
// ---------------------------------------------------------------------------

@description('Name of the storage account (must be globally unique, 3-24 chars, lowercase + numbers only).')
param name string

@description('Azure region.')
param location string = resourceGroup().location

@description('Resource tags.')
param tags object = {}

@description('Name of the container for original images.')
param originalsContainer string = 'originals'

@description('Name of the container for thumbnails.')
param thumbnailsContainer string = 'thumbnails'

@description('Principal ID of the managed identity to grant Storage Blob Data Contributor.')
param principalId string

// ── Storage Account ────────────────────────────────────────────────────────

resource storageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: name
  location: location
  tags: tags
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    accessTier: 'Hot'
    publicNetworkAccess: 'Enabled'
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false // Entra ID (Managed Identity) auth only
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

// ── Storage Blob Data Contributor for Managed Identity ─────────────────────
var storageBlobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

resource storageBlobRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storageAccount.id, principalId, storageBlobDataContributorRoleId)
  scope: storageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', storageBlobDataContributorRoleId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

// ── Blob Service + Containers ──────────────────────────────────────────────

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storageAccount
  name: 'default'
}

resource originalsContainerRes 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: originalsContainer
  properties: {
    publicAccess: 'None'
  }
}

resource thumbnailsContainerRes 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: thumbnailsContainer
  properties: {
    publicAccess: 'None'
  }
}

// ── Outputs ────────────────────────────────────────────────────────────────

@description('Storage account name')
output accountName string = storageAccount.name
