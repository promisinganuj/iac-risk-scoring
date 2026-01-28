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

---

# Hierarchical JSON Structures

The JSON format supports rich nested hierarchies that enable deep graph traversals and better operational context modeling. This section documents the hierarchical patterns used across all sample data files.

## Overview

Hierarchical structures allow modeling complex relationships like:
- Deployment stages with health checks and rollout waves
- Incident timelines with events and mitigation steps
- Service artifacts with build configurations and dependencies
- Template parameters with validation rules and outputs

All nested structures are properly imported into Neo4j as separate nodes with relationships, enabling multi-hop graph queries.

---

## File-by-File Hierarchy Documentation

### 1. Azure Service Tree (`azure_service_tree.json`)

**Hierarchical Properties**:

#### `sourceCodeLocations` (Array of Objects)
Nested structure for source code repository locations:

```json
{
  "serviceId": "svc-alpha",
  "name": "Alpha Payments Service",
  "sourceCodeLocations": [
    {
      "uri": "https://github.com/org/alpha-service",
      "type": "git",
      "primary": true,
      "branch": "main"
    },
    {
      "uri": "https://github.com/org/alpha-infra",
      "type": "git",
      "primary": false,
      "branch": "main"
    }
  ]
}
```

**Properties**:
- `uri`: Repository URL
- `type`: Version control system (e.g., "git")
- `primary`: Whether this is the primary repository
- `branch`: Default branch name

#### `subscriptions` (Array of Objects)
Nested structure for Azure subscription associations:

```json
{
  "subscriptions": [
    {
      "subscriptionId": "subs-prod-001",
      "purpose": "production workloads",
      "accessLevel": "owner"
    },
    {
      "subscriptionId": "subs-prod-002",
      "purpose": "disaster recovery",
      "accessLevel": "contributor"
    }
  ]
}
```

**Properties**:
- `subscriptionId`: Azure subscription ID
- `purpose`: Business purpose of subscription
- `accessLevel`: Permission level (owner, contributor, reader)

#### `icmTeams` (Array of Objects)
Nested structure for incident management team associations:

```json
{
  "icmTeams": [
    {
      "teamName": "Payments-Oncall",
      "role": "primary",
      "escalationLevel": 1
    },
    {
      "teamName": "Infrastructure-Oncall",
      "role": "secondary",
      "escalationLevel": 2
    }
  ]
}
```

**Properties**:
- `teamName`: ICM team identifier
- `role`: Team role (primary, secondary, backup)
- `escalationLevel`: Escalation priority (1 = first responder)

**Graph Relationships Created**:
- `Service -[:SUPPORTED_BY_TEAM]-> Team`

---

### 2. Repositories (`repo.json`)

**Hierarchical Properties**:

#### `serviceArtifacts` (Array of Objects with Nested Properties)
Nested structure for build artifacts and service deployables:

```json
{
  "repoName": "alpha-infra",
  "serviceArtifacts": [
    {
      "name": "alpha-api-service",
      "type": "docker-image",
      "buildConfig": {
        "dockerfile": "services/api/Dockerfile",
        "context": "services/api"
      },
      "dependencies": ["shared-logging-lib", "auth-middleware"]
    },
    {
      "name": "alpha-worker",
      "type": "docker-image",
      "buildConfig": {
        "dockerfile": "services/worker/Dockerfile",
        "context": "services/worker"
      },
      "dependencies": ["shared-queue-lib"]
    }
  ]
}
```

**Properties**:
- `name`: Artifact identifier
- `type`: Artifact type (docker-image, binary, library)
- `buildConfig`: Build configuration object
  - `dockerfile`: Path to Dockerfile
  - `context`: Build context directory
- `dependencies`: Array of dependency artifact names

**Graph Relationships Created**:
- `Repo -[:PRODUCES_ARTIFACT]-> Artifact`
- `Artifact -[:DEPENDS_ON]-> Artifact` (dependency chains)

#### `applicationCode` (Object)
Nested structure for application programming language metadata:

```json
{
  "applicationCode": {
    "language": "python",
    "framework": "fastapi",
    "version": "3.11",
    "runtime": "uvicorn"
  }
}
```

**Properties**:
- `language`: Programming language
- `framework`: Web framework or runtime
- `version`: Language version
- `runtime`: Execution runtime

#### `iacConfiguration` (Object)
Nested structure for Infrastructure as Code tooling:

```json
{
  "iacConfiguration": {
    "tool": "bicep",
    "target": "azure",
    "modules": ["compute", "networking", "storage"]
  }
}
```

**Properties**:
- `tool`: IaC tool (bicep, terraform, arm)
- `target`: Cloud provider
- `modules`: List of infrastructure modules managed

---

### 3. Outages (`outage.json`)

**Hierarchical Properties**:

#### `rootCause` (Nested Object)
Deep nested structure for root cause analysis:

```json
{
  "outageId": "outage-alpha-001",
  "rootCause": {
    "category": "deployment",
    "subcategory": "configuration error",
    "description": "Database connection string misconfigured during deployment",
    "relatedResources": ["res-alpha-db", "res-alpha-app"],
    "triggeringChange": "deploy-alpha-001"
  }
}
```

**Properties**:
- `category`: High-level cause category
- `subcategory`: Specific cause type
- `description`: Detailed explanation
- `relatedResources`: Array of resource IDs involved
- `triggeringChange`: Deployment ID that triggered the outage

#### `subscriptionsImpacted` (Array of Objects with Nested User Impact)
Multi-level nested structure for subscription-level impact:

```json
{
  "subscriptionsImpacted": [
    {
      "subscriptionId": "subs-prod-001",
      "impactLevel": "critical",
      "affectedResources": ["res-alpha-app", "res-alpha-db"],
      "userImpact": {
        "usersAffected": 15000,
        "regionsImpacted": ["westus", "eastus"],
        "businessImpact": "Payment processing unavailable"
      }
    }
  ]
}
```

**Properties**:
- `subscriptionId`: Impacted subscription
- `impactLevel`: Severity (critical, high, medium, low)
- `affectedResources`: Array of resource IDs
- `userImpact`: Nested object
  - `usersAffected`: User count
  - `regionsImpacted`: Azure regions
  - `businessImpact`: Business impact description

**Graph Relationships Created**:
- `Outage -[:IMPACTS_SUBSCRIPTION]-> Subscription`

#### `timeline` (Array of Event Objects)
Ordered timeline of outage events:

```json
{
  "timeline": [
    {
      "event": "outage detected",
      "timestamp": "2025-12-18T08:30:00Z",
      "source": "monitoring-alert",
      "action": "ICM incident created"
    },
    {
      "event": "mitigation started",
      "timestamp": "2025-12-18T08:45:00Z",
      "source": "oncall-engineer",
      "action": "Rollback deployment initiated"
    },
    {
      "event": "service restored",
      "timestamp": "2025-12-18T09:15:00Z",
      "source": "automated-health-check",
      "action": "Traffic restored to healthy instances"
    }
  ]
}
```

**Properties**:
- `event`: Event description
- `timestamp`: When event occurred
- `source`: Event source (system, human, automation)
- `action`: Action taken in response

**Graph Relationships Created**:
- `Outage -[:HAS_TIMELINE_EVENT]-> TimelineEvent`

---

### 4. Incidents (`icm.json`)

**Hierarchical Properties**:

#### `relatedIncidents` (Array of Objects)
Nested structure for incident relationships:

```json
{
  "incidentId": "icm-alpha-001",
  "relatedIncidents": [
    {
      "incidentId": "icm-alpha-002",
      "relationship": "caused-by",
      "description": "Downstream dependency failure"
    },
    {
      "incidentId": "icm-beta-003",
      "relationship": "duplicate-of",
      "description": "Same root cause"
    }
  ]
}
```

**Properties**:
- `incidentId`: Related incident ID
- `relationship`: Relationship type (caused-by, duplicate-of, blocks)
- `description`: Relationship explanation

**Graph Relationships Created**:
- `Incident -[:RELATED_TO_INCIDENT]-> Incident`

#### `affectedResources` (Array of Objects)
Nested structure for resource-level impact:

```json
{
  "affectedResources": [
    {
      "resourceId": "res-alpha-app",
      "impactType": "complete-outage",
      "duration": "45 minutes"
    },
    {
      "resourceId": "res-alpha-db",
      "impactType": "degraded-performance",
      "duration": "90 minutes"
    }
  ]
}
```

**Properties**:
- `resourceId`: Affected resource ID
- `impactType`: Impact severity (complete-outage, degraded-performance, intermittent)
- `duration`: Impact duration string

**Graph Relationships Created**:
- `Incident -[:AFFECTS_RESOURCE]-> AzureResource`

#### `mitigationSteps` (Array of Objects)
Ordered steps taken to resolve incident:

```json
{
  "mitigationSteps": [
    {
      "step": 1,
      "action": "Identified faulty deployment",
      "timestamp": "2025-12-20T14:30:00Z",
      "assignee": "engineer-alice"
    },
    {
      "step": 2,
      "action": "Initiated rollback to previous version",
      "timestamp": "2025-12-20T14:45:00Z",
      "assignee": "engineer-bob"
    },
    {
      "step": 3,
      "action": "Verified service health restored",
      "timestamp": "2025-12-20T15:15:00Z",
      "assignee": "engineer-alice"
    }
  ]
}
```

**Properties**:
- `step`: Step number (ordering)
- `action`: Action description
- `timestamp`: When action was taken
- `assignee`: Engineer responsible

**Graph Relationships Created**:
- `Incident -[:HAS_MITIGATION_STEP]-> MitigationStep`

#### `escalationPath` (Nested Object)
Multi-level escalation structure:

```json
{
  "escalationPath": {
    "level1": "Payments-Oncall",
    "level2": "Payments-Manager",
    "level3": "VP-Engineering"
  }
}
```

**Properties**:
- `level1`: First responder team
- `level2`: Manager escalation
- `level3`: Executive escalation

---

### 5. Templates (`template.json`)

**Hierarchical Properties**:

#### `properties` (Structured Object with Categories)
Nested structure for template resource properties:

```json
{
  "templateName": "template-alpha-app",
  "properties": {
    "compute": {
      "sku": "Standard_D4s_v3",
      "instanceCount": 3,
      "autoscaleEnabled": true
    },
    "network": {
      "virtualNetwork": "vnet-prod",
      "subnet": "subnet-app",
      "privateEndpoint": true
    },
    "storage": {
      "accountType": "Premium_LRS",
      "replication": "ZRS",
      "encryption": "AES256"
    }
  }
}
```

**Categories**:
- `compute`: VM/container specifications
- `network`: Networking configuration
- `storage`: Storage account settings

#### `dependencies` (Array of Objects)
Template dependency chain:

```json
{
  "dependencies": [
    {
      "templateName": "template-shared-network",
      "version": "v2.3.0",
      "required": true
    },
    {
      "templateName": "template-monitoring",
      "version": "v1.5.0",
      "required": false
    }
  ]
}
```

**Properties**:
- `templateName`: Dependency template name
- `version`: Required version
- `required`: Whether dependency is mandatory

**Graph Relationships Created**:
- `Template -[:DEPENDS_ON_TEMPLATE]-> Template`

#### `parameters` (Array of Objects)
Template input parameters with validation:

```json
{
  "parameters": [
    {
      "name": "environmentName",
      "type": "string",
      "default": "prod",
      "validation": {
        "allowedValues": ["prod", "staging", "dev"],
        "minLength": 3,
        "maxLength": 20
      }
    },
    {
      "name": "instanceCount",
      "type": "integer",
      "default": 3,
      "validation": {
        "minValue": 1,
        "maxValue": 10
      }
    }
  ]
}
```

**Properties**:
- `name`: Parameter name
- `type`: Data type
- `default`: Default value
- `validation`: Validation rules object

**Graph Relationships Created**:
- `Template -[:HAS_PARAMETER]-> TemplateParameter`

#### `outputs` (Array of Objects)
Template output values:

```json
{
  "outputs": [
    {
      "name": "appServiceUrl",
      "type": "string",
      "description": "Public URL of deployed app service"
    },
    {
      "name": "resourceGroupId",
      "type": "string",
      "description": "Resource group ARM ID"
    }
  ]
}
```

**Properties**:
- `name`: Output name
- `type`: Data type
- `description`: Output description

**Graph Relationships Created**:
- `Template -[:HAS_OUTPUT]-> TemplateOutput`

---

### 6. Deployments (`ev2_deployment.json`)

**Hierarchical Properties**:

#### `stages` (Array of Objects with Nested Health Checks)
Multi-stage deployment progression:

```json
{
  "deploymentId": "deploy-alpha-001",
  "stages": [
    {
      "name": "stage-1-canary",
      "order": 1,
      "regions": ["westus"],
      "percentage": 10,
      "status": "succeeded",
      "startTime": "2025-12-15T10:30:00Z",
      "endTime": "2025-12-15T11:00:00Z",
      "healthChecks": [
        {
          "name": "http-health",
          "status": "passed",
          "timestamp": "2025-12-15T10:45:00Z"
        },
        {
          "name": "dependency-check",
          "status": "passed",
          "timestamp": "2025-12-15T10:50:00Z"
        }
      ]
    },
    {
      "name": "stage-2-regional",
      "order": 2,
      "regions": ["westus", "eastus"],
      "percentage": 50,
      "status": "succeeded",
      "startTime": "2025-12-15T11:30:00Z",
      "endTime": "2025-12-15T12:30:00Z",
      "healthChecks": [
        {
          "name": "load-test",
          "status": "passed",
          "timestamp": "2025-12-15T12:15:00Z"
        }
      ]
    },
    {
      "name": "stage-3-global",
      "order": 3,
      "regions": ["westus", "eastus", "westeurope"],
      "percentage": 100,
      "status": "succeeded",
      "startTime": "2025-12-15T13:00:00Z",
      "endTime": "2025-12-15T14:00:00Z",
      "healthChecks": [
        {
          "name": "smoke-test",
          "status": "passed",
          "timestamp": "2025-12-15T13:45:00Z"
        }
      ]
    }
  ]
}
```

**Stage Properties**:
- `name`: Stage identifier
- `order`: Execution order (1, 2, 3...)
- `regions`: Azure regions deployed to
- `percentage`: Traffic percentage
- `status`: Stage status (succeeded, failed, in-progress)
- `startTime`: Stage start timestamp
- `endTime`: Stage completion timestamp
- `healthChecks`: Array of health check results

**Health Check Properties**:
- `name`: Check name
- `status`: Check result (passed, failed)
- `timestamp`: When check ran

**Graph Relationships Created**:
- `Deployment -[:HAS_STAGE]-> DeploymentStage`

#### `rolloutPlan` (Nested Object with Arrays)
Deployment rollout strategy:

```json
{
  "rolloutPlan": {
    "waves": [
      {
        "wave": 1,
        "regions": ["westus"],
        "percentage": 10,
        "duration": "30 minutes"
      },
      {
        "wave": 2,
        "regions": ["westus", "eastus"],
        "percentage": 50,
        "duration": "60 minutes"
      },
      {
        "wave": 3,
        "regions": ["westus", "eastus", "westeurope"],
        "percentage": 100,
        "duration": "60 minutes"
      }
    ],
    "rollbackStrategy": "automatic-on-failure",
    "approvalRequired": true
  }
}
```

**Properties**:
- `waves`: Array of rollout waves
  - `wave`: Wave number
  - `regions`: Regions in wave
  - `percentage`: Traffic percentage
  - `duration`: Expected duration
- `rollbackStrategy`: Rollback policy
- `approvalRequired`: Whether manual approval needed

#### `status` (Nested Object with Arrays)
Deployment health status:

```json
{
  "status": {
    "overallStatus": "succeeded",
    "healthScore": 98,
    "validationGates": [
      {
        "gate": "security-scan",
        "status": "passed",
        "timestamp": "2025-12-15T10:15:00Z"
      },
      {
        "gate": "compliance-check",
        "status": "passed",
        "timestamp": "2025-12-15T10:20:00Z"
      }
    ],
    "issues": []
  }
}
```

**Properties**:
- `overallStatus`: Deployment result
- `healthScore`: Health percentage (0-100)
- `validationGates`: Pre-deployment checks
  - `gate`: Gate name
  - `status`: Gate result
  - `timestamp`: When checked
- `issues`: Array of issues encountered

---

## Querying Hierarchical Data

### Example Cypher Queries

**Find all stages of a deployment:**
```cypher
MATCH (d:Deployment {deploymentId: 'deploy-alpha-001'})-[:HAS_STAGE]->(stage:DeploymentStage)
RETURN d.deploymentId, stage.name, stage.order, stage.status, stage.regions
ORDER BY stage.order
```

**Find incident mitigation timeline:**
```cypher
MATCH (i:Incident {incidentId: 'icm-alpha-001'})-[:HAS_MITIGATION_STEP]->(step:MitigationStep)
RETURN i.incidentId, step.step, step.action, step.timestamp, step.assignee
ORDER BY step.step
```

**Find artifact dependency chains:**
```cypher
MATCH path = (a:Artifact {name: 'alpha-api-service'})-[:DEPENDS_ON*1..3]->(dep:Artifact)
RETURN path
```

**Find outage timeline events:**
```cypher
MATCH (o:Outage {outageId: 'outage-alpha-001'})-[:HAS_TIMELINE_EVENT]->(event:TimelineEvent)
RETURN o.outageId, event.event, event.timestamp, event.source, event.action
ORDER BY event.timestamp
```

**Find template dependency graph:**
```cypher
MATCH path = (t:Template {templateName: 'template-alpha-app'})-[:DEPENDS_ON_TEMPLATE*1..2]->(dep:Template)
RETURN path
```

**Find all templates with their parameters:**
```cypher
MATCH (t:Template)-[:HAS_PARAMETER]->(p:TemplateParameter)
RETURN t.templateName, collect({name: p.name, type: p.type, default: p.default})
```

**Find services with their support teams:**
```cypher
MATCH (s:Service)-[:SUPPORTED_BY_TEAM]->(team:Team)
RETURN s.name, team.teamName, team.role, team.escalationLevel
ORDER BY team.escalationLevel
```

---

## New Node Types Created from Hierarchies

| Node Type | Source Property | Parent Entity | Count (Sample Data) |
|-----------|----------------|---------------|---------------------|
| `Artifact` | `repo.serviceArtifacts` | Repo | ~24 |
| `DeploymentStage` | `deployment.stages` | Deployment | ~26 (3 per deployment) |
| `TimelineEvent` | `outage.timeline` | Outage | ~36 (3 per outage) |
| `MitigationStep` | `incident.mitigationSteps` | Incident | ~28 (variable per incident) |
| `TemplateParameter` | `template.parameters` | Template | ~48 (2-4 per template) |
| `TemplateOutput` | `template.outputs` | Template | ~24 (2 per template) |
| `Team` | `service.icmTeams` | Service | ~12 |

---

## Design Principles

1. **Normalize Repeated Data**: Convert flat arrays to objects with relationships
2. **Preserve Ordering**: Use `order`, `step`, or `timestamp` properties for sequencing
3. **Deep Nesting**: Multi-level nesting (e.g., `userImpact` within `subscriptionsImpacted`) is supported
4. **Optional Properties**: Use `OPTIONAL MATCH` in Cypher for properties that may not exist
5. **Array Unwinding**: Use `UNWIND` in Cypher to process arrays into nodes
6. **Type Safety**: Nested objects maintain type information (strings, integers, booleans)

---

## Benefits of Hierarchical Structures

1. **Rich Context**: Capture deployment health checks, incident timelines, artifact dependencies
2. **Multi-Hop Queries**: Traverse deep relationships (e.g., template → dependencies → parameters)
3. **Temporal Analysis**: Timeline events enable time-based reasoning
4. **Impact Analysis**: Subscription-level impact data enables precise blast radius calculations
5. **Dependency Graphs**: Artifact and template dependencies enable change impact prediction
6. **Escalation Paths**: ICM team hierarchies enable automated escalation logic

---

## Migration from Flat to Hierarchical

**CSV Format (Flat)**:
- Limited to single-level properties
- Arrays stored as comma-separated strings
- No nested relationships

**JSON Format (Hierarchical)**:
- Multi-level nesting supported
- Arrays of objects with relationships
- Rich metadata and context

**Backward Compatibility**: CSV files remain functional for simple use cases, while JSON enables advanced scenarios.
