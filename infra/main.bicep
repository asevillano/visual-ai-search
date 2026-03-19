// ---------------------------------------------------------------------------
// main.bicep — Azure Developer CLI entry point for Visual AI Search
//
// Deploys: RG → Monitoring → ACR + CAE → Identity → AI Services → App
//
// Resources created:
//   • Azure AI Search (Standard S1 — required for Semantic Ranker)
//   • Azure AI Vision (S1 — image analysis + multimodal embeddings 1024-d)
//   • Azure OpenAI (text-embedding-3-large + gpt-4.1)
//   • Azure Blob Storage (connection string auth, shared key enabled)
//   • Azure Container Registry + Container Apps Environment + Container App
//   • Log Analytics + Application Insights
//   • User-Assigned Managed Identity with RBAC
// ---------------------------------------------------------------------------

targetScope = 'subscription'

// ── Parameters ─────────────────────────────────────────────────────────────
@minLength(1)
@maxLength(64)
@description('Name of the azd environment — used to derive all resource names')
param environmentName string

@minLength(1)
@description('Primary Azure region for all resources')
param location string

@description('Container image name for the web service. Set automatically by azd.')
param webImageName string = ''

@description('Azure AI Search SKU. Use "standard" (S1+) to enable Semantic Ranker.')
param searchSku string = 'standard'

@description('Azure AI Search index name.')
param searchIndexName string = 'visual-search-index'

@description('Azure OpenAI embedding deployment name.')
param openaiEmbeddingDeployment string = 'text-embedding-3-large'

@description('Azure OpenAI chat deployment name.')
param openaiChatDeployment string = 'gpt-4.1'

@description('Search strategy shown in frontend: "all", "vision", or "openai".')
param searchStrategy string = 'all'

// ── Derived names ──────────────────────────────────────────────────────────
var resourceSuffix = take(uniqueString(subscription().id, environmentName, location), 6)
var envNameLower = replace(toLower(environmentName), '_', '-')
var resourceGroupName = 'rg-${environmentName}'

var searchServiceName = 'search-${envNameLower}-${resourceSuffix}'
var visionAccountName = 'vision-${envNameLower}-${resourceSuffix}'
var openaiAccountName = 'oai-${envNameLower}-${resourceSuffix}'
var storageAccountName = take('st${replace(envNameLower, '-', '')}${resourceSuffix}', 24)

var tags = {
  'azd-env-name': environmentName
}

// ── Model deployments for Azure OpenAI ─────────────────────────────────────
var modelDeployments = [
  { name: openaiEmbeddingDeployment, model: 'text-embedding-3-large', version: '1', skuName: 'Standard', capacity: 120 }
  { name: openaiChatDeployment, model: 'gpt-4.1', version: '2025-04-14', skuName: 'GlobalStandard', capacity: 100 }
]

// ── Resource Group ─────────────────────────────────────────────────────────
resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: resourceGroupName
  location: location
  tags: tags
}

// ── Monitoring (AVM) ───────────────────────────────────────────────────────
module monitoring 'br/public:avm/ptn/azd/monitoring:0.1.0' = {
  name: 'monitoring'
  scope: rg
  params: {
    logAnalyticsName: 'log-${envNameLower}-${resourceSuffix}'
    applicationInsightsName: 'ai-${envNameLower}-${resourceSuffix}'
    applicationInsightsDashboardName: 'aid-${envNameLower}-${resourceSuffix}'
    location: location
    tags: tags
  }
}

// ── Container Apps Stack — ACR + CAE (AVM) ─────────────────────────────────
module containerApps 'br/public:avm/ptn/azd/container-apps-stack:0.1.0' = {
  name: 'container-apps-stack'
  scope: rg
  params: {
    containerAppsEnvironmentName: 'cae-${envNameLower}-${resourceSuffix}'
    containerRegistryName: 'acr${replace(envNameLower, '-', '')}${resourceSuffix}'
    logAnalyticsWorkspaceResourceId: monitoring.outputs.logAnalyticsWorkspaceResourceId
    location: location
    tags: tags
    acrSku: 'Basic'
    acrAdminUserEnabled: true
    zoneRedundant: false
  }
}

// ── User-Assigned Managed Identity ─────────────────────────────────────────
module webIdentity 'br/public:avm/res/managed-identity/user-assigned-identity:0.4.0' = {
  name: 'web-identity'
  scope: rg
  params: {
    name: 'id-web-${envNameLower}-${resourceSuffix}'
    location: location
    tags: tags
  }
}

// ── ACR Pull role for the managed identity ─────────────────────────────────
module acrAccess './modules/acr-access.bicep' = {
  name: 'acr-access'
  scope: rg
  params: {
    containerRegistryName: containerApps.outputs.registryName
    principalId: webIdentity.outputs.principalId
  }
}

// ── Azure AI Search (Standard S1+ for Semantic Ranker) ─────────────────────
module search './modules/search.bicep' = {
  name: 'search'
  scope: rg
  params: {
    name: searchServiceName
    location: location
    tags: tags
    sku: searchSku
  }
}

// ── Azure AI Vision (Computer Vision S1) ───────────────────────────────────
module vision './modules/vision.bicep' = {
  name: 'vision'
  scope: rg
  params: {
    name: visionAccountName
    location: location
    tags: tags
    principalId: webIdentity.outputs.principalId
  }
}

// ── Azure OpenAI + model deployments ───────────────────────────────────────
module openai './modules/openai.bicep' = {
  name: 'openai'
  scope: rg
  params: {
    name: openaiAccountName
    location: location
    tags: tags
    deployments: modelDeployments
    principalId: webIdentity.outputs.principalId
  }
}

// ── Blob Storage (connection string auth) ──────────────────────────────────
module storage './modules/storage.bicep' = {
  name: 'storage'
  scope: rg
  params: {
    name: storageAccountName
    location: location
    tags: tags
    principalId: webIdentity.outputs.principalId
  }
}

// ── Container App ──────────────────────────────────────────────────────────
var containerAppName = take('ca-${envNameLower}-${resourceSuffix}', 32)
var containerImage = !empty(webImageName)
  ? webImageName
  : 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'

var containerEnv = [
  { name: 'PYTHONUNBUFFERED', value: '1' }
  { name: 'AZURE_TENANT_ID', value: tenant().tenantId }
  { name: 'AZURE_CLIENT_ID', value: webIdentity.outputs.clientId }
  // Azure AI Search
  { name: 'AZURE_SEARCH_ENDPOINT', value: search.outputs.endpoint }
  { name: 'AZURE_SEARCH_API_KEY', secretRef: 'search-api-key' }
  { name: 'AZURE_SEARCH_INDEX_NAME', value: searchIndexName }
  // Azure AI Vision (Entra ID auth)
  { name: 'AZURE_VISION_ENDPOINT', value: vision.outputs.endpoint }
  // Azure OpenAI (Entra ID auth)
  { name: 'AZURE_OPENAI_ENDPOINT', value: openai.outputs.endpoint }
  { name: 'AZURE_OPENAI_API_VERSION', value: '2024-10-21' }
  { name: 'AZURE_OPENAI_EMBEDDING_DEPLOYMENT', value: openaiEmbeddingDeployment }
  { name: 'AZURE_OPENAI_CHAT_DEPLOYMENT', value: openaiChatDeployment }
  // Azure Blob Storage (Managed Identity auth)
  { name: 'AZURE_STORAGE_ACCOUNT_NAME', value: storage.outputs.accountName }
  { name: 'AZURE_STORAGE_CONTAINER_ORIGINALS', value: 'originals' }
  { name: 'AZURE_STORAGE_CONTAINER_THUMBNAILS', value: 'thumbnails' }
  // App
  { name: 'SEARCH_STRATEGY', value: searchStrategy }
  { name: 'APPLICATIONINSIGHTS_CONNECTION_STRING', value: monitoring.outputs.applicationInsightsConnectionString }
]

module web 'br/public:avm/res/app/container-app:0.10.0' = {
  name: 'web-container-app'
  scope: rg
  dependsOn: [acrAccess]
  params: {
    name: containerAppName
    location: location
    tags: union(tags, { 'azd-service-name': 'web' })
    environmentResourceId: '${rg.id}/providers/Microsoft.App/managedEnvironments/${containerApps.outputs.environmentName}'
    managedIdentities: {
      userAssignedResourceIds: [webIdentity.outputs.resourceId]
    }
    registries: [
      {
        server: containerApps.outputs.registryLoginServer
        identity: webIdentity.outputs.resourceId
      }
    ]

    secrets: {
      secureList: [
        { name: 'search-api-key', value: search.outputs.adminKey }
      ]
    }

    ingressExternal: true
    ingressTargetPort: 8000
    ingressTransport: 'auto'
    ingressAllowInsecure: false

    scaleMinReplicas: 1
    scaleMaxReplicas: 3
    scaleRules: [
      {
        name: 'http-scaling'
        http: {
          metadata: {
            concurrentRequests: '20'
          }
        }
      }
    ]

    containers: [
      {
        image: containerImage
        name: 'main'
        env: containerEnv
        resources: {
          cpu: json('1.0')
          memory: '2.0Gi'
        }
        probes: [
          {
            type: 'Startup'
            httpGet: { path: '/api/health', port: 8000 }
            initialDelaySeconds: 5
            periodSeconds: 30
            failureThreshold: 10        // 10 × 30 s = 300 s max startup — prevents ARM stream timeout
            timeoutSeconds: 5
          }
          {
            type: 'Liveness'
            httpGet: { path: '/api/health', port: 8000 }
            initialDelaySeconds: 60     // only starts after Startup probe succeeds
            periodSeconds: 30
            failureThreshold: 5
            timeoutSeconds: 5
          }
          {
            type: 'Readiness'
            httpGet: { path: '/api/health', port: 8000 }
            initialDelaySeconds: 60     // only starts after Startup probe succeeds
            periodSeconds: 10
            failureThreshold: 5
            timeoutSeconds: 5
          }
        ]
      }
    ]
  }
}

// ── Outputs (consumed by azd) ──────────────────────────────────────────────
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = containerApps.outputs.registryLoginServer
output AZURE_CONTAINER_REGISTRY_NAME string = containerApps.outputs.registryName
output AZURE_CONTAINER_ENVIRONMENT_NAME string = containerApps.outputs.environmentName
output AZURE_RESOURCE_GROUP string = rg.name
output SERVICE_WEB_ENDPOINT_URL string = 'https://${web.outputs.fqdn}'
output SERVICE_WEB_IMAGE_NAME string = containerImage
output SERVICE_WEB_NAME string = web.outputs.name
output AZURE_SEARCH_ENDPOINT string = search.outputs.endpoint
output AZURE_VISION_ENDPOINT string = vision.outputs.endpoint
output AZURE_OPENAI_ENDPOINT string = openai.outputs.endpoint
output AZURE_STORAGE_ACCOUNT_NAME string = storage.outputs.accountName
