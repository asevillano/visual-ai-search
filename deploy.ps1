# =============================================================================
# Deployment Script — Visual AI Search
# Local Docker Desktop  or  Azure Container Apps
# =============================================================================

# ---------------------------------------------------------------------------
# Variables — UPDATE THESE FOR AZURE DEPLOYMENT
# ---------------------------------------------------------------------------
$RESOURCE_GROUP      = "rg-angel"
$LOCATION            = "swedencentral"
$ENVIRONMENT_NAME    = "visual-ai-search-env"
$CONTAINER_APP_NAME  = "visual-ai-search"
$ACR_NAME            = "aigbbemea"              # Reusing existing ACR from rg-angel
$IMAGE_NAME          = "visual-ai-search"
$IMAGE_TAG           = "v$(Get-Date -Format 'yyyyMMdd-HHmmss')"
$LOCAL_PORT          = 8000
$CONTAINER_PORT      = 8000
$ENV_FILE            = ".env"
$DOCKERFILE          = "Dockerfile"

# Environment variables that contain secrets (will be stored as Container Apps secrets)
$SECRET_VARS = @(
    "AZURE_SEARCH_API_KEY"
)

# =============================================================================
# Ask user for deployment target
# =============================================================================
Write-Host ""
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Visual AI Search — Deployment" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Where do you want to deploy?" -ForegroundColor Yellow
Write-Host "  1. Local Docker Desktop  (for development / testing)"
Write-Host "  2. Azure Container Apps  (for production / demos)"
Write-Host ""
$choice = Read-Host "Enter your choice (1 or 2)"

# =============================================================================
# Helper: check last exit code
# =============================================================================
function Test-StepSuccess {
    param([string]$StepName)
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: $StepName failed (exit code $LASTEXITCODE)" -ForegroundColor Red
        Write-Host "Fix the issue and re-run the script." -ForegroundColor Yellow
        exit 1
    }
    Write-Host "  OK — $StepName" -ForegroundColor Green
}

# =============================================================================
# Helper: parse .env file into a hashtable
# =============================================================================
function Read-EnvFile {
    param([string]$Path)
    $vars = @{}
    Get-Content $Path | ForEach-Object {
        if ($_ -match "^\s*#" -or $_ -match "^\s*$") { return }
        if ($_ -match "^([^=]+)=(.*)$") {
            $key   = $matches[1].Trim()
            $value = $matches[2].Trim() -replace '^["'']|["'']$', ''
            if ($value -and $value -ne "" -and -not $value.StartsWith("<")) {
                $vars[$key] = $value
            }
        }
    }
    return $vars
}

# =============================================================================
# Helper: validate .env has all required vars
# =============================================================================
function Show-EnvValidation {
    Write-Host ""
    Write-Host "--- .env validation ---" -ForegroundColor Cyan
    $finalEnv = Read-EnvFile $ENV_FILE
    $allOk = $true

    $requiredKeys = @(
        "AZURE_SEARCH_ENDPOINT", "AZURE_SEARCH_API_KEY", "AZURE_SEARCH_INDEX_NAME",
        "AZURE_VISION_ENDPOINT",
        "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
        "AZURE_STORAGE_ACCOUNT_NAME"
    )

    foreach ($key in $requiredKeys) {
        $val = $finalEnv[$key]
        if ($val) {
            $masked = $val.Substring(0, [Math]::Min(12, $val.Length)) + "..."
            Write-Host "  $key = $masked" -ForegroundColor Green
        } else {
            Write-Host "  $key = (empty or missing)" -ForegroundColor Red
            $allOk = $false
        }
    }

    # Optional keys
    Write-Host ""
    Write-Host "--- Optional ---" -ForegroundColor Cyan
    foreach ($key in @("AZURE_TENANT_ID", "AZURE_OPENAI_API_VERSION", "AZURE_STORAGE_CONTAINER_ORIGINALS", "AZURE_STORAGE_CONTAINER_THUMBNAILS", "FRONTEND_URL")) {
        $val = $finalEnv[$key]
        if ($val) {
            Write-Host "  $key = $val" -ForegroundColor Green
        } else {
            Write-Host "  $key = (using default)" -ForegroundColor Gray
        }
    }

    if (-not $allOk) {
        Write-Host ""
        Write-Host "  WARNING: Some required variables are missing." -ForegroundColor Yellow
        Write-Host "  Edit $ENV_FILE and fill in the Azure credentials." -ForegroundColor Yellow
        $cont = Read-Host "  Continue anyway? (y/n)"
        if ($cont -ne "y") { exit 1 }
    }
}

# =============================================================================
# OPTION 1: Local Docker Desktop
# =============================================================================
if ($choice -eq "1") {
    Write-Host ""
    Write-Host "=== Deploying to Local Docker Desktop ===" -ForegroundColor Green
    Write-Host ""

    # --- Pre-flight checks ---
    if (-not (Test-Path $ENV_FILE)) {
        Write-Host "ERROR: $ENV_FILE not found!" -ForegroundColor Red
        Write-Host "Copy .env.example to .env and fill in your credentials." -ForegroundColor Yellow
        exit 1
    }

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: docker CLI not found. Is Docker Desktop installed and running?" -ForegroundColor Red
        exit 1
    }

    Show-EnvValidation

    # --- Ensure RBAC roles for current user (Entra ID auth) ---
    Write-Host ""
    Write-Host "Checking RBAC roles for local development (Entra ID)..." -ForegroundColor Cyan

    $azAvailable = Get-Command az -ErrorAction SilentlyContinue
    if ($azAvailable) {
        $acct = az account show 2>$null | ConvertFrom-Json
        if ($acct) {
            $currentUserId = az ad signed-in-user show --query id -o tsv 2>$null
            if ($currentUserId) {
                Write-Host "  Signed-in user: $($acct.user.name)" -ForegroundColor Gray
                $envVarsLocal = Read-EnvFile $ENV_FILE

                # Helper to assign role
                function Assign-LocalRole {
                    param([string]$Endpoint, [string]$Pattern, [string]$Label, [string]$Role, [string]$UserId)
                    if (-not $Endpoint) { return }
                    if ($Endpoint -match $Pattern) {
                        $resName = $matches[1]
                        $resId = az resource list --name $resName `
                            --resource-type "Microsoft.CognitiveServices/accounts" `
                            --query "[0].id" -o tsv 2>$null
                        if ($resId) {
                            $existing = az role assignment list `
                                --assignee $UserId --role $Role --scope $resId `
                                --query "[0].id" -o tsv 2>$null
                            if ($existing) {
                                Write-Host "  $Label — '$Role' already assigned" -ForegroundColor Green
                            } else {
                                az role assignment create `
                                    --assignee $UserId --role $Role `
                                    --scope $resId --output none 2>$null
                                Write-Host "  $Label — '$Role' assigned" -ForegroundColor Green
                            }
                        } else {
                            Write-Host "  $Label — resource '$resName' not found (assign manually)" -ForegroundColor Yellow
                        }
                    }
                }

                Assign-LocalRole `
                    -Endpoint $envVarsLocal["AZURE_OPENAI_ENDPOINT"] `
                    -Pattern 'https://([^.]+)\.openai\.azure\.com' `
                    -Label "Azure OpenAI" `
                    -Role "Cognitive Services OpenAI User" `
                    -UserId $currentUserId

                Assign-LocalRole `
                    -Endpoint $envVarsLocal["AZURE_VISION_ENDPOINT"] `
                    -Pattern 'https://([^.]+)\.cognitiveservices\.azure\.com' `
                    -Label "Azure AI Vision" `
                    -Role "Cognitive Services User" `
                    -UserId $currentUserId
            } else {
                Write-Host "  Could not get signed-in user. Run 'az login' to enable RBAC setup." -ForegroundColor Yellow
            }
        } else {
            Write-Host "  Not logged in to Azure CLI. Skipping RBAC (run 'az login' if needed)." -ForegroundColor Yellow
        }
    } else {
        Write-Host "  Azure CLI not found. Skipping RBAC — assign roles manually." -ForegroundColor Yellow
    }

    # --- Stop any previous container ---
    Write-Host ""
    Write-Host "Stopping existing container (if any)..." -ForegroundColor Cyan
    docker stop $IMAGE_NAME 2>$null | Out-Null
    docker rm   $IMAGE_NAME 2>$null | Out-Null

    # --- Build ---
    Write-Host "Building Docker image..." -ForegroundColor Cyan
    docker build --no-cache -t "${IMAGE_NAME}:${IMAGE_TAG}" -f $DOCKERFILE .
    Test-StepSuccess "Docker build"

    # --- Run ---
    Write-Host "Starting container..." -ForegroundColor Cyan
    docker run -d `
        --name $IMAGE_NAME `
        -p "${LOCAL_PORT}:${CONTAINER_PORT}" `
        --env-file $ENV_FILE `
        "${IMAGE_NAME}:${IMAGE_TAG}"
    Test-StepSuccess "Docker run"

    # --- Wait & health check ---
    Write-Host "Waiting for server to start..." -ForegroundColor Cyan
    Start-Sleep -Seconds 8

    $containerStatus = docker ps --filter "name=$IMAGE_NAME" --format "{{.Status}}"
    if ($containerStatus) {
        Write-Host ""
        Write-Host "========================================================" -ForegroundColor Green
        Write-Host "  Container started successfully!" -ForegroundColor Green
        Write-Host "========================================================" -ForegroundColor Green
        Write-Host ""
        Write-Host "Web UI:" -ForegroundColor Yellow
        Write-Host "  http://localhost:$LOCAL_PORT" -ForegroundColor White
        Write-Host ""
        Write-Host "Health Check:" -ForegroundColor Yellow
        Write-Host "  http://localhost:$LOCAL_PORT/api/health" -ForegroundColor White
        Write-Host ""
        Write-Host "API Docs (Swagger):" -ForegroundColor Yellow
        Write-Host "  http://localhost:$LOCAL_PORT/docs" -ForegroundColor White
        Write-Host ""
        Write-Host "--- Useful Commands ---" -ForegroundColor Magenta
        Write-Host "  View logs:    docker logs -f $IMAGE_NAME"
        Write-Host "  Stop:         docker stop $IMAGE_NAME"
        Write-Host "  Restart:      docker restart $IMAGE_NAME"
        Write-Host "  Remove:       docker rm -f $IMAGE_NAME"
        Write-Host "  Shell:        docker exec -it $IMAGE_NAME bash"
        Write-Host ""

        # Quick health ping
        try {
            $resp = Invoke-WebRequest -Uri "http://localhost:$LOCAL_PORT/api/health" `
                        -UseBasicParsing -TimeoutSec 10
            if ($resp.StatusCode -eq 200) {
                Write-Host "Health check: OK" -ForegroundColor Green
            }
        } catch {
            Write-Host "Health check: server still starting — run 'docker logs $IMAGE_NAME'" -ForegroundColor Yellow
        }
    } else {
        Write-Host "Container failed to start. Check: docker logs $IMAGE_NAME" -ForegroundColor Red
        exit 1
    }
}

# =============================================================================
# OPTION 2: Azure Container Apps
# =============================================================================
elseif ($choice -eq "2") {
    Write-Host ""
    Write-Host "=== Deploying to Azure Container Apps ===" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Image tag : $IMAGE_TAG" -ForegroundColor Gray
    Write-Host "  Resource  : $RESOURCE_GROUP / $CONTAINER_APP_NAME" -ForegroundColor Gray
    Write-Host ""

    # --- Pre-flight checks ---
    if (-not (Test-Path $ENV_FILE)) {
        Write-Host "ERROR: $ENV_FILE not found!" -ForegroundColor Red
        Write-Host "Copy .env.example to .env and fill in your credentials." -ForegroundColor Yellow
        exit 1
    }

    if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: Azure CLI (az) not found. Install from https://aka.ms/installazurecliwindows" -ForegroundColor Red
        exit 1
    }

    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Write-Host "ERROR: docker CLI not found. Is Docker Desktop installed and running?" -ForegroundColor Red
        exit 1
    }

    Show-EnvValidation

    # --- Ensure logged in to Azure ---
    $acct = az account show 2>$null | ConvertFrom-Json
    if (-not $acct) {
        Write-Host "Not logged in to Azure CLI. Launching login..." -ForegroundColor Yellow
        az login
        $acct = az account show 2>$null | ConvertFrom-Json
        if (-not $acct) {
            Write-Host "ERROR: Azure login failed." -ForegroundColor Red
            exit 1
        }
    }
    Write-Host "  Subscription: $($acct.name) ($($acct.id))" -ForegroundColor Gray

    # --- Skip-step selector ---
    Write-Host ""
    Write-Host "Skip completed steps?" -ForegroundColor Yellow
    Write-Host "  0. Run all steps (default)"
    Write-Host "  1. Skip to Step 2 (ACR)          — Resource Group already exists"
    Write-Host "  2. Skip to Step 3 (Docker)        — ACR already exists"
    Write-Host "  3. Skip to Step 4 (Environment)   — Image already pushed"
    Write-Host "  4. Skip to Step 5 (Env vars)      — Environment already exists"
    Write-Host "  5. Skip to Step 6 (Container App) — Ready to create / update app"
    Write-Host "  6. Skip to Step 7 (RBAC)          — App deployed, assign roles"
    Write-Host "  7. Skip to Step 8 (Get URL)       — Everything done, get URL"
    Write-Host ""
    $startStep = Read-Host "Start from step [0-7, default 0]"
    if (-not $startStep) { $startStep = "0" }
    $startStep = [int]$startStep

    # --- Read .env ---
    Write-Host "Reading environment variables from $ENV_FILE..." -ForegroundColor Cyan
    $envVars = Read-EnvFile $ENV_FILE
    Write-Host "  Found $($envVars.Count) variables" -ForegroundColor Gray

    # == Step 1: Resource Group ================================================
    if ($startStep -le 0) {
        Write-Host ""
        Write-Host "[Step 1/8] Checking Resource Group..." -ForegroundColor Cyan

        $rgExists = az group exists --name $RESOURCE_GROUP 2>$null
        if ($rgExists -eq "true") {
            Write-Host "  Resource Group already exists" -ForegroundColor Gray
        } else {
            az group create --name $RESOURCE_GROUP --location $LOCATION --output none
            Test-StepSuccess "Resource Group"
        }
    } else {
        Write-Host "[Step 1/8] Skipped (Resource Group)" -ForegroundColor Gray
    }

    # == Step 2: Azure Container Registry ======================================
    if ($startStep -le 1) {
        Write-Host ""
        Write-Host "[Step 2/8] Azure Container Registry..." -ForegroundColor Cyan

        $acrExists = az acr show --name $ACR_NAME --query "name" -o tsv 2>$null
        if ($acrExists) {
            Write-Host "  ACR '$ACR_NAME' already exists — skipping creation" -ForegroundColor Gray
        } else {
            az acr create `
                --resource-group $RESOURCE_GROUP `
                --name $ACR_NAME `
                --sku Basic `
                --admin-enabled true `
                --output none
            Test-StepSuccess "ACR creation"
        }
    } else {
        Write-Host "[Step 2/8] Skipped (ACR)" -ForegroundColor Gray
    }

    # Get ACR credentials
    Write-Host "  Retrieving ACR credentials..." -ForegroundColor Gray
    $ACR_LOGIN_SERVER = az acr show --name $ACR_NAME --query loginServer -o tsv
    $ACR_USERNAME     = az acr credential show --name $ACR_NAME --query username -o tsv
    $ACR_PASSWORD     = az acr credential show --name $ACR_NAME --query "passwords[0].value" -o tsv

    if (-not $ACR_LOGIN_SERVER -or -not $ACR_USERNAME -or -not $ACR_PASSWORD) {
        Write-Host "ERROR: Failed to retrieve ACR credentials" -ForegroundColor Red
        exit 1
    }
    Write-Host "  ACR server: $ACR_LOGIN_SERVER" -ForegroundColor Gray

    # == Step 3: Build & Push Docker Image =====================================
    if ($startStep -le 2) {
        Write-Host ""
        Write-Host "[Step 3/8] Building and pushing Docker image..." -ForegroundColor Cyan

        az acr login --name $ACR_NAME
        Test-StepSuccess "ACR login"

        docker build --no-cache -t "${ACR_LOGIN_SERVER}/${IMAGE_NAME}:${IMAGE_TAG}" -f $DOCKERFILE .
        Test-StepSuccess "Docker build"

        docker push "${ACR_LOGIN_SERVER}/${IMAGE_NAME}:${IMAGE_TAG}"
        Test-StepSuccess "Docker push"
    } else {
        Write-Host "[Step 3/8] Skipped (Docker build/push)" -ForegroundColor Gray
    }

    # == Step 4: Container Apps Environment ====================================
    if ($startStep -le 3) {
        Write-Host ""
        Write-Host "[Step 4/8] Container Apps Environment..." -ForegroundColor Cyan

        $envExists = az containerapp env show `
            --name $ENVIRONMENT_NAME `
            --resource-group $RESOURCE_GROUP `
            --query "name" -o tsv 2>$null
        if ($envExists) {
            Write-Host "  Environment '$ENVIRONMENT_NAME' already exists — skipping" -ForegroundColor Gray
        } else {
            az containerapp env create `
                --name $ENVIRONMENT_NAME `
                --resource-group $RESOURCE_GROUP `
                --location $LOCATION `
                --output none
            Test-StepSuccess "Container Apps Environment"
        }
    } else {
        Write-Host "[Step 4/8] Skipped (Environment)" -ForegroundColor Gray
    }

    # == Step 5: Build YAML configuration ======================================
    Write-Host ""
    Write-Host "[Step 5/8] Preparing environment variables & secrets..." -ForegroundColor Cyan

    function ConvertTo-YamlSafe {
        param([string]$Value)
        if ($Value -match '[":{}[\],&*#?|\-<>=!%@`]' -or $Value -match "'" -or $Value -match '\n') {
            return "'$($Value.Replace("'", "''"))'"
        }
        return "`"$Value`""
    }

    # Secrets section
    $secretsYaml = "    - name: acr-password`n      value: $(ConvertTo-YamlSafe $ACR_PASSWORD)"
    foreach ($key in $envVars.Keys) {
        if ($SECRET_VARS -contains $key) {
            $secretName = $key.ToLower().Replace("_", "-")
            $secretsYaml += "`n    - name: $secretName`n      value: $(ConvertTo-YamlSafe $envVars[$key])"
        }
    }

    # Env section
    $envVarsYaml = ""
    foreach ($key in $envVars.Keys) {
        $secretName = $key.ToLower().Replace("_", "-")
        if ($SECRET_VARS -contains $key) {
            $envVarsYaml += "      - name: $key`n        secretRef: $secretName`n"
        } else {
            $envVarsYaml += "      - name: $key`n        value: $(ConvertTo-YamlSafe $envVars[$key])`n"
        }
    }

    $subscriptionId = az account show --query id -o tsv

    $yamlContent = @"
properties:
  managedEnvironmentId: /subscriptions/$subscriptionId/resourceGroups/$RESOURCE_GROUP/providers/Microsoft.App/managedEnvironments/$ENVIRONMENT_NAME
  configuration:
    activeRevisionsMode: Single
    ingress:
      external: true
      targetPort: $CONTAINER_PORT
      transport: auto
      allowInsecure: false
    registries:
    - server: $ACR_LOGIN_SERVER
      username: $ACR_USERNAME
      passwordSecretRef: acr-password
    secrets:
$secretsYaml
  template:
    containers:
    - image: ${ACR_LOGIN_SERVER}/${IMAGE_NAME}:${IMAGE_TAG}
      name: $CONTAINER_APP_NAME
      resources:
        cpu: 1.0
        memory: 2Gi
      env:
$envVarsYaml
      probes:
      - type: Startup
        httpGet:
          path: /api/health
          port: $CONTAINER_PORT
        initialDelaySeconds: 5
        periodSeconds: 30
        failureThreshold: 10
        timeoutSeconds: 5
      - type: Liveness
        httpGet:
          path: /api/health
          port: $CONTAINER_PORT
        initialDelaySeconds: 60
        periodSeconds: 30
        failureThreshold: 5
        timeoutSeconds: 5
      - type: Readiness
        httpGet:
          path: /api/health
          port: $CONTAINER_PORT
        initialDelaySeconds: 60
        periodSeconds: 10
        failureThreshold: 5
        timeoutSeconds: 5
    scale:
      minReplicas: 1
      maxReplicas: 3
      rules:
      - name: http-scaling
        http:
          metadata:
            concurrentRequests: "20"
"@

    $yamlFile = "containerapp-config.yaml"
    [System.IO.File]::WriteAllText(
        (Join-Path $PWD $yamlFile),
        $yamlContent,
        [System.Text.UTF8Encoding]::new($false)
    )
    Write-Host "  Saved $yamlFile" -ForegroundColor Gray

    # == Step 6: Create / Update Container App =================================
    if ($startStep -le 5) {
        Write-Host ""
        Write-Host "[Step 6/8] Deploying Container App..." -ForegroundColor Cyan

        $appExists = az containerapp show `
            --name $CONTAINER_APP_NAME `
            --resource-group $RESOURCE_GROUP `
            --query "name" -o tsv 2>$null

        if ($appExists) {
            Write-Host "  App exists — updating..." -ForegroundColor Yellow
            az containerapp update `
                --name $CONTAINER_APP_NAME `
                --resource-group $RESOURCE_GROUP `
                --yaml $yamlFile `
                --output none
            Test-StepSuccess "Container App update (YAML)"

            az containerapp update `
                --name $CONTAINER_APP_NAME `
                --resource-group $RESOURCE_GROUP `
                --image "${ACR_LOGIN_SERVER}/${IMAGE_NAME}:${IMAGE_TAG}" `
                --output none
            Test-StepSuccess "Container App image update"
        } else {
            Write-Host "  Creating new Container App (this may take 1-2 min)..." -ForegroundColor Gray
            $createAttempt = 0
            $createSuccess = $false
            while ($createAttempt -lt 2 -and -not $createSuccess) {
                $createAttempt++
                az containerapp create `
                    --name $CONTAINER_APP_NAME `
                    --resource-group $RESOURCE_GROUP `
                    --environment $ENVIRONMENT_NAME `
                    --yaml $yamlFile `
                    --output none 2>&1
                if ($LASTEXITCODE -eq 0) {
                    $createSuccess = $true
                } else {
                    # Check if it was created despite the error (connection timeout)
                    $checkApp = az containerapp show --name $CONTAINER_APP_NAME --resource-group $RESOURCE_GROUP --query "name" -o tsv 2>$null
                    if ($checkApp) {
                        Write-Host "  App was created despite CLI error (connection timeout) — continuing" -ForegroundColor Yellow
                        $createSuccess = $true
                    } elseif ($createAttempt -lt 2) {
                        Write-Host "  Attempt $createAttempt failed — retrying in 10s..." -ForegroundColor Yellow
                        Start-Sleep -Seconds 10
                    }
                }
            }
            if (-not $createSuccess) {
                Write-Host "ERROR: Container App creation failed after $createAttempt attempts" -ForegroundColor Red
                exit 1
            }
            Write-Host "  OK — Container App creation" -ForegroundColor Green
        }

        Remove-Item $yamlFile -ErrorAction SilentlyContinue
    } else {
        Write-Host "[Step 6/8] Skipped (Container App)" -ForegroundColor Gray
    }

    # == Step 7: Managed Identity & RBAC for Azure OpenAI + Vision =============
    if ($startStep -le 6) {
        Write-Host ""
        Write-Host "[Step 7/8] Configuring Managed Identity & RBAC..." -ForegroundColor Cyan

        # Enable system-assigned managed identity
        Write-Host "  Enabling system-assigned managed identity..." -ForegroundColor Gray
        az containerapp identity assign `
            --name $CONTAINER_APP_NAME `
            --resource-group $RESOURCE_GROUP `
            --system-assigned `
            --output none 2>$null
        Write-Host "  OK — Managed identity enabled" -ForegroundColor Green

        # Get the principal ID of the managed identity
        $principalId = az containerapp identity show `
            --name $CONTAINER_APP_NAME `
            --resource-group $RESOURCE_GROUP `
            --query "principalId" -o tsv

        if (-not $principalId) {
            Write-Host "  WARNING: Could not retrieve managed identity principal ID." -ForegroundColor Yellow
            Write-Host "  You may need to assign roles manually." -ForegroundColor Yellow
        } else {
            Write-Host "  Principal ID: $principalId" -ForegroundColor Gray

            # --- Helper function to find Cognitive Services resource & assign role ---
            function Assign-CognitiveServicesRole {
                param(
                    [string]$Endpoint,
                    [string]$Pattern,
                    [string]$ServiceLabel,
                    [string]$RoleName,
                    [string]$PrincipalId
                )
                Write-Host "" -ForegroundColor Gray
                Write-Host "  --- $ServiceLabel ---" -ForegroundColor Cyan
                if ($Endpoint -match $Pattern) {
                    $resourceName = $matches[1]
                    Write-Host "  Resource: $resourceName" -ForegroundColor Gray

                    # Try same resource group first
                    $resourceId = az cognitiveservices account show `
                        --name $resourceName `
                        --resource-group $RESOURCE_GROUP `
                        --query "id" -o tsv 2>$null

                    # Fall back to subscription-wide search
                    if (-not $resourceId) {
                        Write-Host "  Searching across subscription..." -ForegroundColor Gray
                        $resourceId = az resource list `
                            --name $resourceName `
                            --resource-type "Microsoft.CognitiveServices/accounts" `
                            --query "[0].id" -o tsv 2>$null
                    }

                    if ($resourceId) {
                        Write-Host "  Assigning '$RoleName' role..." -ForegroundColor Gray
                        az role assignment create `
                            --assignee-object-id $PrincipalId `
                            --assignee-principal-type ServicePrincipal `
                            --role $RoleName `
                            --scope $resourceId `
                            --output none 2>$null
                        Write-Host "  OK — '$RoleName' assigned to $ServiceLabel" -ForegroundColor Green
                    } else {
                        Write-Host "  WARNING: Resource '$resourceName' not found." -ForegroundColor Yellow
                        Write-Host "  Assign manually: az role assignment create --assignee-object-id $PrincipalId --assignee-principal-type ServicePrincipal --role '$RoleName' --scope <resource-id>" -ForegroundColor Gray
                    }
                } else {
                    Write-Host "  WARNING: Could not parse resource name from endpoint." -ForegroundColor Yellow
                    Write-Host "  Assign '$RoleName' role manually after deployment." -ForegroundColor Yellow
                }
            }

            # 7a. Azure OpenAI — Cognitive Services OpenAI User
            Assign-CognitiveServicesRole `
                -Endpoint $envVars["AZURE_OPENAI_ENDPOINT"] `
                -Pattern 'https://([^.]+)\.openai\.azure\.com' `
                -ServiceLabel "Azure OpenAI" `
                -RoleName "Cognitive Services OpenAI User" `
                -PrincipalId $principalId

            # 7b. Azure AI Vision — Cognitive Services User
            Assign-CognitiveServicesRole `
                -Endpoint $envVars["AZURE_VISION_ENDPOINT"] `
                -Pattern 'https://([^.]+)\.cognitiveservices\.azure\.com' `
                -ServiceLabel "Azure AI Vision" `
                -RoleName "Cognitive Services User" `
                -PrincipalId $principalId
        }
    } else {
        Write-Host "[Step 7/8] Skipped (RBAC)" -ForegroundColor Gray
    }

    # == Step 8: Get Application URL ===========================================
    Write-Host ""
    Write-Host "[Step 8/8] Retrieving application URL..." -ForegroundColor Cyan

    Start-Sleep -Seconds 5

    $APP_FQDN = az containerapp show `
        --name $CONTAINER_APP_NAME `
        --resource-group $RESOURCE_GROUP `
        --query "properties.configuration.ingress.fqdn" -o tsv

    if (-not $APP_FQDN) {
        Write-Host "  WARNING: URL not available yet — app may still be provisioning." -ForegroundColor Yellow
        $APP_FQDN = "<pending>"
    }

    Write-Host ""
    Write-Host "========================================================" -ForegroundColor Green
    Write-Host "  Deployment Complete!" -ForegroundColor Green
    Write-Host "========================================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Web UI:" -ForegroundColor Yellow
    Write-Host "  https://$APP_FQDN" -ForegroundColor White
    Write-Host ""
    Write-Host "Health Check:" -ForegroundColor Yellow
    Write-Host "  https://$APP_FQDN/api/health" -ForegroundColor White
    Write-Host ""
    Write-Host "API Docs (Swagger):" -ForegroundColor Yellow
    Write-Host "  https://$APP_FQDN/docs" -ForegroundColor White
    Write-Host ""
    Write-Host "--- Useful Commands ---" -ForegroundColor Magenta
    Write-Host "  View logs:    az containerapp logs show -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP --follow"
    Write-Host "  Status:       az containerapp show -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP --query properties.runningStatus"
    Write-Host "  Revisions:    az containerapp revision list -n $CONTAINER_APP_NAME -g $RESOURCE_GROUP -o table"
    Write-Host "  Delete all:   az group delete -n $RESOURCE_GROUP --yes --no-wait"
    Write-Host ""
}
else {
    Write-Host "Invalid choice. Run the script again and enter 1 or 2." -ForegroundColor Red
    exit 1
}

