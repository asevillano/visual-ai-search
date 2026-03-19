# ---------------------------------------------------------------------------
# assign-roles.ps1 — Manually assign RBAC roles after azd provision
#
# Use this script when Conditional Access policies in the tenant block
# role assignments during ARM deployment (GraphBadRequest error).
#
# Usage:
#   .\infra\hooks\assign-roles.ps1 -EnvironmentName <your-azd-env-name>
#
# Prerequisites: Azure CLI logged in (az login)
# ---------------------------------------------------------------------------

param(
    [Parameter(Mandatory = $false)]
    [string]$EnvironmentName
)

$ErrorActionPreference = "Stop"

# If no env name provided, try to get it from azd
if (-not $EnvironmentName) {
    $EnvironmentName = (azd env get-values 2>$null | Select-String "^AZURE_ENV_NAME=" | ForEach-Object { $_ -replace "^AZURE_ENV_NAME=", "" -replace '"', '' })
    if (-not $EnvironmentName) {
        Write-Error "Could not determine environment name. Pass -EnvironmentName or run 'azd env select'."
        exit 1
    }
}

Write-Host "`n=== Assigning RBAC roles for environment: $EnvironmentName ===" -ForegroundColor Cyan

$rg = "rg-$EnvironmentName"

# Get the managed identity principal ID
Write-Host "`nLooking up managed identity..." -ForegroundColor Yellow
$allIdentities = az identity list -g $rg -o json | ConvertFrom-Json
$identities = @($allIdentities | Where-Object { $_.name -like '*id-web-*' })
if ($identities.Count -eq 0) {
    Write-Error "No managed identity found in resource group $rg"
    exit 1
}
$principalId = $identities[0].principalId
$identityName = $identities[0].name
Write-Host "  Identity: $identityName"
Write-Host "  Principal ID: $principalId"

# Get the Azure OpenAI account
Write-Host "`nLooking up Azure OpenAI account..." -ForegroundColor Yellow
$allCogAccounts = az cognitiveservices account list -g $rg -o json | ConvertFrom-Json
$openaiAccount = @($allCogAccounts | Where-Object { $_.kind -eq 'OpenAI' })
if ($openaiAccount.Count -eq 0) {
    Write-Error "No Azure OpenAI account found in resource group $rg"
    exit 1
}
$openaiAccountId = $openaiAccount[0].id
Write-Host "  OpenAI: $($openaiAccount[0].name)"

# Get the Azure AI Vision account
$visionAccount = @($allCogAccounts | Where-Object { $_.kind -eq 'ComputerVision' })
if ($visionAccount.Count -eq 0) {
    Write-Error "No Azure AI Vision account found in resource group $rg"
    exit 1
}
$visionAccountId = $visionAccount[0].id
Write-Host "  Vision: $($visionAccount[0].name)"

# Get the ACR
Write-Host "`nLooking up Container Registry..." -ForegroundColor Yellow
$acrs = az acr list -g $rg -o json | ConvertFrom-Json
if ($acrs.Count -eq 0) {
    Write-Error "No Container Registry found in resource group $rg"
    exit 1
}
$acrId = $acrs[0].id
Write-Host "  ACR: $($acrs[0].name)"

# Role definitions
$roles = @(
    @{ Name = "AcrPull"; Id = "7f951dda-4ed3-4680-a7ca-43fe172d538d"; Scope = $acrId }
    @{ Name = "Cognitive Services OpenAI User"; Id = "5e0bd9bd-7b93-4f28-af87-19fc36ad61bd"; Scope = $openaiAccountId }
    @{ Name = "Cognitive Services User"; Id = "a97b65f3-24c7-4388-baec-2e87135dc908"; Scope = $visionAccountId }
)

Write-Host "`nAssigning roles..." -ForegroundColor Yellow
foreach ($role in $roles) {
    Write-Host "  Assigning '$($role.Name)'..." -NoNewline
    try {
        az role assignment create `
            --assignee-object-id $principalId `
            --assignee-principal-type ServicePrincipal `
            --role $role.Id `
            --scope $role.Scope `
            --only-show-errors 2>&1 | Out-Null
        Write-Host " OK" -ForegroundColor Green
    }
    catch {
        Write-Host " FAILED" -ForegroundColor Red
        Write-Host "    Error: $_" -ForegroundColor Red
    }
}

Write-Host "`n=== Done! All roles assigned. ===" -ForegroundColor Green
Write-Host "You can now run 'azd deploy' to push the container image.`n"
