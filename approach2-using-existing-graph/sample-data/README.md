# Sample Data Documentation

This directory contains mock data representing an IT system infrastructure for risk scoring analysis. The data is available in both **JSON** (preferred) and **CSV** (legacy) formats.

## Data Formats

### JSON Format (Default)

JSON files are the preferred format for Neo4j ingestion and Python repository access:

- **File Extension**: `.json`
- **Structure**: Array of objects
- **Ingestion Method**: `apoc.load.json` (requires APOC plugin)
- **Benefits**: Supports nested structures, extensible, type-safe

### CSV Format (Legacy)

CSV files are maintained for backward compatibility:

- **File Extension**: `.csv`
- **Structure**: Flat table with headers
- **Ingestion Method**: `LOAD CSV` (built-in Neo4j)
- **Benefits**: Simple, widely supported, human-readable

## Files

Each file represents a different entity type in the system:

| File | Entity Type | Description | Records |
|------|-------------|-------------|---------|
| `azure_resources` | AzureResource | Azure cloud resources (VMs, databases, storage) | 12 |
| `azure_service_tree` | Service | Logical services owning resources | 12 |
| `ev2_deployment` | Deployment | EV2 deployment events | 12 |
| `icm` | Incident | ICM incident records | 12 |
| `outage` | Outage | Service outage events | 12 |
| `repo` | Repo | Git repositories | 12 |
| `template` | Template | Infrastructure as Code templates | 12 |

## Schema

### Azure Resources

**Purpose**: Represents Azure cloud resources that can be changed

**Properties**:
- `resourceName` (string, required, unique): Resource identifier (e.g., "res-alpha-app")
- `displayName` (string): Human-readable name
- `resourceType` (string): Azure resource type (e.g., "Microsoft.Web/sites")
- `subscriptionId` (string): Azure subscription ID
- `resourceGroup` (string): Azure resource group name
- `tags` (object): Key-value tags for categorization

**JSON Example**:
```json
[
  {
    "resourceName": "res-alpha-app",
    "displayName": "Alpha Application Server",
    "resourceType": "Microsoft.Web/sites",
    "subscriptionId": "subs-prod-001",
    "resourceGroup": "rg-alpha-prod",
    "tags": {
      "env": "prod",
      "owner": "payments",
      "serviceId": "svc-alpha"
    }
  }
]
```

**CSV Example**:
```csv
resourceName,displayName,resourceType,subscriptionId,resourceGroup,tags.env,tags.owner,tags.serviceId
res-alpha-app,Alpha Application Server,Microsoft.Web/sites,subs-prod-001,rg-alpha-prod,prod,payments,svc-alpha
```

### Services (Azure Service Tree)

**Purpose**: Logical services that own resources

**Properties**:
- `serviceId` (string, required, unique): Service identifier
- `name` (string): Service name
- `tier` (string): Service tier (e.g., "Tier1", "Tier2")
- `subscriptions` (array): List of subscription IDs
- `isCritical` (boolean): Whether service is business-critical

**JSON Example**:
```json
[
  {
    "serviceId": "svc-alpha",
    "name": "Alpha Payments Service",
    "tier": "Tier1",
    "subscriptions": ["subs-prod-001", "subs-prod-002"],
    "isCritical": true
  }
]
```

### Deployments (EV2)

**Purpose**: Deployment events for change tracking

**Properties**:
- `deploymentId` (string, required, unique): Deployment identifier
- `templateName` (string): Infrastructure template used
- `serviceId` (string): Service being deployed
- `timestamp` (string, ISO 8601): Deployment time
- `status` (string): Deployment status (e.g., "succeeded")

**JSON Example**:
```json
[
  {
    "deploymentId": "deploy-alpha-001",
    "templateName": "template-alpha-app",
    "serviceId": "svc-alpha",
    "timestamp": "2025-12-15T10:30:00Z",
    "status": "succeeded"
  }
]
```

### Incidents (ICM)

**Purpose**: Incident records for reliability analysis

**Properties**:
- `incidentId` (string, required, unique): Incident identifier
- `serviceId` (string): Affected service
- `severity` (integer): Incident severity (1-4, lower is more severe)
- `createdAt` (string, ISO 8601): Incident creation time
- `resolvedAt` (string, ISO 8601, optional): Resolution time
- `status` (string): Current status (e.g., "active", "resolved")

**JSON Example**:
```json
[
  {
    "incidentId": "icm-alpha-001",
    "serviceId": "svc-alpha",
    "severity": 2,
    "createdAt": "2025-12-20T14:15:00Z",
    "resolvedAt": "2025-12-20T16:45:00Z",
    "status": "resolved"
  }
]
```

### Outages

**Purpose**: Service outage events for blast radius calculation

**Properties**:
- `outageId` (string, required, unique): Outage identifier
- `serviceId` (string): Service experiencing outage
- `startTime` (string, ISO 8601): Outage start
- `endTime` (string, ISO 8601, optional): Outage end
- `impactedUsers` (integer): Number of affected users

**JSON Example**:
```json
[
  {
    "outageId": "outage-alpha-001",
    "serviceId": "svc-alpha",
    "startTime": "2025-12-18T08:30:00Z",
    "endTime": "2025-12-18T09:15:00Z",
    "impactedUsers": 15000
  }
]
```

### Repositories

**Purpose**: Git repositories containing IaC templates

**Properties**:
- `repoName` (string, required, unique): Repository name
- `serviceId` (string): Owning service
- `url` (string): Repository URL
- `defaultBranch` (string): Default branch name

**JSON Example**:
```json
[
  {
    "repoName": "alpha-infra",
    "serviceId": "svc-alpha",
    "url": "https://github.com/org/alpha-infra",
    "defaultBranch": "main"
  }
]
```

### Templates

**Purpose**: Infrastructure as Code templates

**Properties**:
- `templateName` (string, required, unique): Template identifier
- `repoName` (string): Source repository
- `path` (string): Template file path
- `resourceTypes` (array): List of Azure resource types created

**JSON Example**:
```json
[
  {
    "templateName": "template-alpha-app",
    "repoName": "alpha-infra",
    "path": "templates/app-service.bicep",
    "resourceTypes": ["Microsoft.Web/sites", "Microsoft.Storage/storageAccounts"]
  }
]
```

## Property Naming Conventions

### Neo4j Properties (camelCase)

Neo4j uses **camelCase** for property names to match JSON format:
- `resourceName` (not `resource_name`)
- `displayName` (not `display_name`)
- `subscriptionId` (not `subscription_id`)

### Python Attributes (snake_case)

Python code uses **snake_case** following PEP 8:
- `resource_name` (not `resourceName`)
- `display_name` (not `displayName`)
- `subscription_id` (not `subscriptionId`)

This is the standard cross-language mapping convention.

## Migration from resourceId to resourceName

**Important**: The `resourceId` property has been renamed to `resourceName` for semantic clarity:

- **Old Property**: `resourceId` (deprecated)
- **New Property**: `resourceName` (current)
- **Reason**: The property stores a resource identifier/name, not a numeric ID

**Migration Impact**:
- ✅ All Cypher queries updated to use `resourceName`
- ✅ Neo4j constraints updated to use `resourceName`
- ✅ CSV and JSON files updated
- ✅ Python repository code updated
- ✅ All tests updated

## Usage

### Loading Data in Neo4j

**JSON (default)**:
```bash
./scripts/neo4j_up_and_import.sh json
```

**CSV (legacy)**:
```bash
./scripts/neo4j_up_and_import.sh csv
```

### Loading Data in Python

The `CsvEntityRepository` (despite its name) supports both formats:

```python
from pathlib import Path
from risk_scoring.csv_repository import CsvEntityRepository

# Loads JSON by default, falls back to CSV
repo = CsvEntityRepository(
    sample_data_dir=Path("sample-data")
)

# Find resources
results = repo.find_azure_resources_by_resource_id("res-alpha-app", limit=10)
```

### Querying in Neo4j

**Query by resourceName**:
```cypher
MATCH (r:AzureResource {resourceName: $resourceName})
RETURN r
```

**Get service context**:
```cypher
MATCH (r:AzureResource {resourceName: $resourceName})
OPTIONAL MATCH (s:Service)-[:OWNS_RESOURCE]->(r)
RETURN r, s
```

## Validation

Verify data was loaded correctly:

```bash
./scripts/validate_import.sh
```

This checks:
- Node counts match expected values (12 resources, 12 services, etc.)
- Relationships exist between nodes
- Constraints are properly configured

## Adding New Data

### Adding Resources

**JSON format** (`azure_resources.json`):
```json
{
  "resourceName": "res-new-resource",
  "displayName": "New Resource",
  "resourceType": "Microsoft.Compute/virtualMachines",
  "subscriptionId": "subs-dev-001",
  "resourceGroup": "rg-dev",
  "tags": {
    "env": "dev",
    "owner": "team-name"
  }
}
```

**CSV format** (`azure_resources.csv`):
```csv
resourceName,displayName,resourceType,subscriptionId,resourceGroup,tags.env,tags.owner
res-new-resource,New Resource,Microsoft.Compute/virtualMachines,subs-dev-001,rg-dev,dev,team-name
```

### Re-importing

After modifying data files:

```bash
./scripts/neo4j_up_and_import.sh
```

The import is idempotent - existing nodes are updated, new nodes are created.

## Notes

- **Record Count**: Each file contains 12 mock records representing a realistic system topology
- **Relationships**: The Neo4j import scripts create relationships between entities (e.g., Service OWNS_RESOURCE AzureResource)
- **Extensibility**: JSON format supports nested objects and arrays for future enhancements
- **Compatibility**: Both formats will be maintained during the transition period
