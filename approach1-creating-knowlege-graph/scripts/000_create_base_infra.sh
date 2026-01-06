#!/bin/bash
set -euo pipefail

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

# Load environment variables from .env file
ENV_FILE="${PROJECT_ROOT}/.env"
if [[ -f "$ENV_FILE" ]]; then
  source "$ENV_FILE"
else
  echo "Warning: .env file not found at $ENV_FILE"
fi

# Set default location if not provided
LOCATION="${LOCATION:-eastus}"

echo "Subscription: ${AZURE_SUBSCRIPTION_ID}"
echo "Resource Group: ${RESOURCE_GROUP}"
echo "Location: ${LOCATION}"
echo "Azure CosmosDB Gremlin Host: ${COSMOS_GREMLIN_HOST}"
echo "Azure CosmosDB Gremlin Database: ${COSMOS_GREMLIN_DATABASE}"
echo "Azure CosmosDB Gremlin Graph: ${COSMOS_GREMLIN_GRAPH}"

# Set the subscription
az account set --subscription "${AZURE_SUBSCRIPTION_ID}"

az cosmosdb gremlin database create \
  --account-name "${COSMOS_GREMLIN_HOST}" \
  --name "${COSMOS_GREMLIN_DATABASE}" \
  --resource-group "${RESOURCE_GROUP}"

az cosmosdb gremlin graph create \
  --account-name "${COSMOS_GREMLIN_HOST}" \
  --database-name "${COSMOS_GREMLIN_DATABASE}" \
  --name "${COSMOS_GREMLIN_GRAPH}" \
  --partition-key-path "/resourceId" \
  --resource-group "${RESOURCE_GROUP}"
