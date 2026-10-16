#!/bin/bash
# =============================================================================
# PrevaIQ — Deploy to Azure Container Apps
# =============================================================================
# Prerequisites:
#   - az CLI authenticated in the target tenant:
#       az login --tenant <tenant-id>
#   - PREVAIQ_API_KEY and PREVAIQ_PG_PASSWORD exported (read by main.bicepparam;
#     for --iac terraform they are passed as TF_VAR_api_key / TF_VAR_pg_admin_password)
#   - Docker (optional — az acr build builds remotely)
#   - Terraform >= 1.9 (only for --iac terraform)
#
# Usage:
#   # First-time full deploy (infra + images + apps)
#   ./infra/deploy.sh --full
#
#   # Same, provisioning the infrastructure with Terraform instead of Bicep
#   ./infra/deploy.sh --full --iac terraform
#
#   # Just rebuild and push images
#   ./infra/deploy.sh --images
#
#   # Just update ACA with new image tags
#   ./infra/deploy.sh --update-apps
# =============================================================================

set -euo pipefail

# Configuration
SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-${AZURE_SUBSCRIPTION_ID:-$(az account show --query id -o tsv)}}"
RESOURCE_GROUP="rg-prevaiq-demo"
LOCATION="swedencentral"
PROJECT_NAME="prevaiq"
ENVIRONMENT="demo"
BRAND_NAME="${BRAND_NAME:-PrevaIQ}"
IAC_TOOL="${IAC_TOOL:-bicep}"
ACR_NAME="acr${PROJECT_NAME}${ENVIRONMENT}"
TAG=$(git rev-parse --short HEAD 2>/dev/null || echo "latest")

az account set --subscription "$SUBSCRIPTION_ID"

echo "============================================="
echo "PrevaIQ Azure Deployment"
echo "============================================="
echo "Resource Group : $RESOURCE_GROUP"
echo "Location       : $LOCATION"
echo "ACR            : $ACR_NAME"
echo "Brand          : $BRAND_NAME"
echo "Image Tag      : $TAG"
echo "============================================="

deploy_bicep() {
    echo ">>> Step 2: Deploy Bicep template"
    echo "    You will be prompted for apiKey and pgAdminPassword"

    az deployment group create \
        --resource-group "$RESOURCE_GROUP" \
        --template-file infra/main.bicep \
        --parameters infra/main.bicepparam \
        --query "properties.outputs" \
        --output table
}

deploy_terraform() {
    echo ">>> Step 2: Apply Terraform configuration (infra/terraform)"
    command -v terraform > /dev/null || { echo "terraform not found in PATH"; exit 1; }

    # Same secrets as main.bicepparam, handed over as Terraform variables.
    if [ -n "${PREVAIQ_API_KEY:-}" ]; then export TF_VAR_api_key="$PREVAIQ_API_KEY"; fi
    if [ -n "${PREVAIQ_PG_PASSWORD:-}" ]; then export TF_VAR_pg_admin_password="$PREVAIQ_PG_PASSWORD"; fi

    terraform -chdir=infra/terraform init -input=false
    terraform -chdir=infra/terraform apply \
        -var "resource_group_name=$RESOURCE_GROUP" \
        -var "location=$LOCATION" \
        -var "project_name=$PROJECT_NAME" \
        -var "environment=$ENVIRONMENT" \
        -var "brand_name=$BRAND_NAME"
}

deploy_infra() {
    echo ""
    echo ">>> Step 1: Create Resource Group"
    az group create \
        --name "$RESOURCE_GROUP" \
        --location "$LOCATION" \
        --output none

    case "$IAC_TOOL" in
        bicep) deploy_bicep ;;
        terraform) deploy_terraform ;;
    esac
}

build_images() {
    echo ""
    echo ">>> Building backend image: prevaiq-api:$TAG"
    az acr build \
        --registry "$ACR_NAME" \
        --image "prevaiq-api:$TAG" \
        --image "prevaiq-api:latest" \
        --build-arg "BRAND_NAME=$BRAND_NAME" \
        --file Dockerfile \
        . \
        --no-logs \
        --output none

    echo ">>> Building frontend image: prevaiq-frontend:$TAG"
    az acr build \
        --registry "$ACR_NAME" \
        --image "prevaiq-frontend:$TAG" \
        --image "prevaiq-frontend:latest" \
        --build-arg "BRAND_NAME=$BRAND_NAME" \
        --file frontend/Dockerfile \
        --build-arg "API_URL=https://ca-api-${ENVIRONMENT}.$(az containerapp env show -n cae-${PROJECT_NAME}-${ENVIRONMENT} -g $RESOURCE_GROUP --query 'properties.defaultDomain' -o tsv)" \
        frontend/ \
        --no-logs \
        --output none

    echo ">>> Images pushed: prevaiq-api:$TAG, prevaiq-frontend:$TAG"
}

update_apps() {
    echo ""
    ACR_SERVER=$(az acr show --name "$ACR_NAME" --query loginServer -o tsv)

    echo ">>> Updating API container app with image $ACR_SERVER/prevaiq-api:$TAG"
    az containerapp update \
        --name "ca-api-$ENVIRONMENT" \
        --resource-group "$RESOURCE_GROUP" \
        --image "$ACR_SERVER/prevaiq-api:$TAG" \
        --output none

    echo ">>> Updating Frontend container app with image $ACR_SERVER/prevaiq-frontend:$TAG"
    az containerapp update \
        --name "ca-frontend-$ENVIRONMENT" \
        --resource-group "$RESOURCE_GROUP" \
        --image "$ACR_SERVER/prevaiq-frontend:$TAG" \
        --output none

    echo ""
    echo "============================================="
    echo "Deployment Complete!"
    echo "============================================="
    API_URL=$(az containerapp show -n "ca-api-$ENVIRONMENT" -g "$RESOURCE_GROUP" --query "properties.configuration.ingress.fqdn" -o tsv)
    FRONTEND_URL=$(az containerapp show -n "ca-frontend-$ENVIRONMENT" -g "$RESOURCE_GROUP" --query "properties.configuration.ingress.fqdn" -o tsv)
    echo "API:      https://$API_URL"
    echo "Frontend: https://$FRONTEND_URL"
    echo "============================================="
}

# Parse arguments
ACTION=""
while [ $# -gt 0 ]; do
    case "$1" in
        --iac)
            [ $# -ge 2 ] || { echo "--iac requires a value: bicep or terraform"; exit 1; }
            IAC_TOOL="$2"
            shift 2
            ;;
        *)
            ACTION="$1"
            shift
            ;;
    esac
done

case "$IAC_TOOL" in
    bicep|terraform) ;;
    *)
        echo "Unknown IaC tool '$IAC_TOOL' (expected bicep or terraform)"
        exit 1
        ;;
esac

case "$ACTION" in
    --full)
        deploy_infra
        build_images
        update_apps
        ;;
    --infra)
        deploy_infra
        ;;
    --images)
        build_images
        ;;
    --update-apps)
        update_apps
        ;;
    *)
        echo "Usage: $0 {--full|--infra|--images|--update-apps} [--iac bicep|terraform]"
        echo ""
        echo "  --full        Deploy infrastructure + build images + update apps"
        echo "  --infra       Deploy infrastructure only (Bicep by default)"
        echo "  --images      Build and push Docker images to ACR only"
        echo "  --update-apps Update container apps with latest images only"
        echo "  --iac TOOL    Infrastructure tool for --full/--infra: bicep (default) or terraform"
        exit 1
        ;;
esac
