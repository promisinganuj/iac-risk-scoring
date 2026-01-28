# Hierarchical Data Model - Design Patterns and Decisions

This document explains the design decisions behind the hierarchical JSON structures in the sample data, the graph relationship patterns they create, and guidelines for extending the model.

## Table of Contents

1. [Design Philosophy](#design-philosophy)
2. [When to Use Hierarchies vs Flat Structures](#when-to-use-hierarchies-vs-flat-structures)
3. [Relationship Naming Conventions](#relationship-naming-conventions)
4. [Pattern Catalog](#pattern-catalog)
5. [Implementation Decisions](#implementation-decisions)
6. [Extension Guidelines](#extension-guidelines)

---

## Design Philosophy

### Core Principles

1. **Semantic Clarity Over Convenience**: Model entities as separate nodes when they have independent existence and properties
2. **Query Traversability**: Hierarchies enable multi-hop queries that flat structures cannot support
3. **Operational Context**: Rich hierarchies capture real-world complexity (timelines, stages, dependencies)
4. **Backward Compatibility**: CSV format remains flat for simplicity; JSON format enables richness

### Goals

- **Better Risk Assessment**: Deep context (incident timelines, deployment stages) improves risk scoring
- **Graph-Native Modeling**: Leverage Neo4j's strength in relationship traversal
- **Extensibility**: Easy to add new properties to nested entities without schema changes
- **Real-World Fidelity**: Mirror how operators think about systems (stages, steps, waves, chains)

---

## When to Use Hierarchies vs Flat Structures

### Use Hierarchies (Separate Nodes) When:

| Criterion | Example | Rationale |
|-----------|---------|-----------|
| **Entity has independent identity** | `DeploymentStage` has `name`, `order`, `status` | Can be queried, filtered, aggregated independently |
| **One-to-many relationships** | Deployment has multiple stages | Natural graph traversal pattern |
| **Temporal ordering matters** | Timeline events, mitigation steps | Ordered relationships enable sequencing queries |
| **Nested properties are complex** | Artifact with `buildConfig` object | Promotes to node when properties are rich |
| **Cross-references exist** | Incident relates to other incidents | Enables relationship creation between nested entities |
| **Aggregation is needed** | Count mitigation steps per incident | Separate nodes enable `count()`, `collect()`, filtering |

### Use Flat Structures (Properties) When:

| Criterion | Example | Rationale |
|-----------|---------|-----------|
| **Simple scalar values** | `severity: 2`, `status: "succeeded"` | No need for separate node |
| **No independent queries** | `tags: {env: "prod"}` | Tags are always queried through parent |
| **No relationships to other entities** | `description: "..."` | Just metadata, not a first-class entity |
| **Immutable metadata** | `createdAt`, `resourceType` | Static properties that never change |

### Decision Tree

```
Does the nested data...
├─ Have multiple properties (> 2)?
│  └─ YES → Consider hierarchy
│  └─ NO → Use flat property
│
├─ Need independent queries?
│  └─ YES → Use hierarchy
│  └─ NO → Use flat property
│
├─ Have relationships to other entities?
│  └─ YES → MUST use hierarchy
│  └─ NO → Continue evaluation
│
└─ Enable temporal or ordered analysis?
   └─ YES → Use hierarchy
   └─ NO → Use flat property
```

---

## Relationship Naming Conventions

### Naming Patterns

| Pattern | Example | When to Use |
|---------|---------|-------------|
| `HAS_*` | `HAS_STAGE`, `HAS_MITIGATION_STEP` | Parent contains child (composition) |
| `OWNS_*` | `OWNS_RESOURCE`, `OWNS_REPO` | Parent owns/manages child (strong ownership) |
| `DEPENDS_ON_*` | `DEPENDS_ON_TEMPLATE`, `DEPENDS_ON` | Explicit dependency relationship |
| `PRODUCES_*` | `PRODUCES_ARTIFACT` | Parent creates/outputs child |
| `IMPACTS_*` | `IMPACTS_SUBSCRIPTION` | Cause-effect relationship |
| `AFFECTS_*` | `AFFECTS_RESOURCE` | Influence or impact relationship |
| `RELATED_TO_*` | `RELATED_TO_INCIDENT` | Peer relationship (not hierarchical) |
| `SUPPORTED_BY_*` | `SUPPORTED_BY_TEAM` | Support or service relationship |

### Relationship Direction

- **Containment**: Parent → Child (`Deployment -[:HAS_STAGE]-> DeploymentStage`)
- **Ownership**: Owner → Owned (`Service -[:OWNS_RESOURCE]-> AzureResource`)
- **Dependency**: Dependent → Dependency (`Artifact -[:DEPENDS_ON]-> Artifact`)
- **Impact**: Source → Target (`Outage -[:IMPACTS_SUBSCRIPTION]-> Subscription`)

### Properties on Relationships

Relationships can carry properties for metadata:

```cypher
// Timeline ordering
(Outage)-[:HAS_TIMELINE_EVENT {order: 1}]->(TimelineEvent)

// Dependency metadata
(Template)-[:DEPENDS_ON_TEMPLATE {required: true, version: "v2.3.0"}]->(Template)

// Impact severity
(Incident)-[:AFFECTS_RESOURCE {impactType: "complete-outage"}]->(Resource)
```

**When to use relationship properties:**
- Ordering information (`order`, `priority`)
- Relationship metadata (`required`, `version`, `role`)
- Strength/severity indicators (`weight`, `impactLevel`)

---

## Pattern Catalog

### Pattern 1: Ordered Sequence (Timeline, Steps, Stages)

**Use Case**: Model ordered events or phases with temporal or logical progression.

**Example**: Incident mitigation steps

```json
{
  "incidentId": "icm-alpha-001",
  "mitigationSteps": [
    {
      "step": 1,
      "action": "Identified faulty deployment",
      "timestamp": "2025-12-20T14:30:00Z",
      "assignee": "engineer-alice"
    },
    {
      "step": 2,
      "action": "Initiated rollback",
      "timestamp": "2025-12-20T14:45:00Z",
      "assignee": "engineer-bob"
    }
  ]
}
```

**Graph Pattern**:
```cypher
(Incident)-[:HAS_MITIGATION_STEP {order: 1}]->(MitigationStep {step: 1})
(Incident)-[:HAS_MITIGATION_STEP {order: 2}]->(MitigationStep {step: 2})
```

**Query Pattern**:
```cypher
MATCH (i:Incident {incidentId: $id})-[:HAS_MITIGATION_STEP]->(step:MitigationStep)
RETURN step.step, step.action, step.timestamp
ORDER BY step.step
```

**Design Decisions**:
- **Why separate nodes?** Enables queries like "find incidents with > 5 mitigation steps" or "find incidents with rollback actions"
- **Why `step` property?** Explicit ordering is more reliable than timestamp ordering (actions may be logged out of order)
- **Why `assignee`?** Enables queries like "find incidents where Alice was involved" or team coordination analysis

**Applies To**: 
- Deployment stages (`deployment.stages`)
- Timeline events (`outage.timeline`)
- Mitigation steps (`incident.mitigationSteps`)

---

### Pattern 2: Dependency Chain (Artifacts, Templates)

**Use Case**: Model dependency graphs where entities depend on other entities of the same type.

**Example**: Artifact dependencies

```json
{
  "repoName": "alpha-infra",
  "serviceArtifacts": [
    {
      "name": "alpha-api-service",
      "type": "docker-image",
      "dependencies": ["shared-logging-lib", "auth-middleware"]
    },
    {
      "name": "shared-logging-lib",
      "type": "library",
      "dependencies": []
    }
  ]
}
```

**Graph Pattern**:
```cypher
(Repo)-[:PRODUCES_ARTIFACT]->(Artifact {name: "alpha-api-service"})
(Repo)-[:PRODUCES_ARTIFACT]->(Artifact {name: "shared-logging-lib"})
(Artifact {name: "alpha-api-service"})-[:DEPENDS_ON]->(Artifact {name: "shared-logging-lib"})
```

**Query Pattern**:
```cypher
// Find transitive dependencies (depth 1-3)
MATCH path = (a:Artifact {name: $name})-[:DEPENDS_ON*1..3]->(dep:Artifact)
RETURN path

// Find shared libraries (high-impact artifacts)
MATCH (shared:Artifact)<-[:DEPENDS_ON]-(dependent:Artifact)
WITH shared, count(DISTINCT dependent) AS dependentCount
WHERE dependentCount >= 2
RETURN shared.name, dependentCount
```

**Design Decisions**:
- **Why `DEPENDS_ON` relationship?** Enables dependency graph analysis and blast radius calculation
- **Why same-type relationships?** Artifacts depend on artifacts, templates depend on templates (homogeneous dependencies)
- **Why depth limit (1-3)?** Prevents runaway queries on deep dependency chains

**Applies To**:
- Artifact dependencies (`artifact.dependencies`)
- Template dependencies (`template.dependencies`)

---

### Pattern 3: Multi-Level Nesting (Nested Objects with Arrays)

**Use Case**: Model complex entities with multiple levels of nesting.

**Example**: Outage with subscriptions impacted, each with user impact

```json
{
  "outageId": "outage-alpha-001",
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

**Graph Pattern**:
```cypher
(Outage)-[:IMPACTS_SUBSCRIPTION {impactLevel: "critical"}]->(Subscription)
// User impact stored as properties on relationship or parent node
```

**Query Pattern**:
```cypher
MATCH (o:Outage)-[r:IMPACTS_SUBSCRIPTION]->(s:Subscription)
RETURN o.outageId, s.subscriptionId, r.impactLevel, o.userImpact
```

**Design Decisions**:
- **Why not promote `userImpact` to separate node?** It's metadata about the relationship, not an independent entity
- **When to stop nesting?** Stop at 2-3 levels; promote to node if queries need to filter/aggregate on nested data
- **Why store on relationship vs node?** `impactLevel` is about the outage→subscription relationship; `userImpact` is about the overall outage

**Applies To**:
- Outage subscription impact (`outage.subscriptionsImpacted.userImpact`)
- Artifact build configuration (`artifact.buildConfig`)
- Template properties (`template.properties.compute/network/storage`)

---

### Pattern 4: Configuration Hierarchies (Grouped Properties)

**Use Case**: Model structured configuration with logical groupings.

**Example**: Template properties grouped by category

```json
{
  "templateName": "template-alpha-app",
  "properties": {
    "compute": {
      "sku": "Standard_D4s_v3",
      "instanceCount": 3
    },
    "network": {
      "virtualNetwork": "vnet-prod",
      "subnet": "subnet-app"
    }
  }
}
```

**Graph Pattern**:
```cypher
// Store as nested properties on Template node
(Template {
  templateName: "template-alpha-app",
  properties_compute_sku: "Standard_D4s_v3",
  properties_compute_instanceCount: 3,
  properties_network_virtualNetwork: "vnet-prod"
})
```

**Query Pattern**:
```cypher
MATCH (t:Template {templateName: $name})
RETURN t.properties_compute_sku, t.properties_network_virtualNetwork
```

**Design Decisions**:
- **Why not separate nodes?** Configuration categories don't have independent identity or relationships
- **Why flatten to properties?** Enables property-based filtering/indexing in Neo4j
- **When to use this pattern?** When nested data is purely descriptive metadata without relationships

**Applies To**:
- Template properties (`template.properties`)
- Application code metadata (`repo.applicationCode`)
- IaC configuration (`repo.iacConfiguration`)

---

### Pattern 5: Support/Service Relationships (Teams, Escalation)

**Use Case**: Model support relationships with roles and priorities.

**Example**: Service support teams with escalation levels

```json
{
  "serviceId": "svc-alpha",
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

**Graph Pattern**:
```cypher
(Service)-[:SUPPORTED_BY_TEAM {role: "primary", escalationLevel: 1}]->(Team {teamName: "Payments-Oncall"})
(Service)-[:SUPPORTED_BY_TEAM {role: "secondary", escalationLevel: 2}]->(Team {teamName: "Infrastructure-Oncall"})
```

**Query Pattern**:
```cypher
// Find primary oncall team
MATCH (s:Service {serviceId: $id})-[r:SUPPORTED_BY_TEAM {escalationLevel: 1}]->(team:Team)
RETURN team.teamName

// Find escalation path
MATCH (s:Service {serviceId: $id})-[r:SUPPORTED_BY_TEAM]->(team:Team)
RETURN team.teamName, r.role, r.escalationLevel
ORDER BY r.escalationLevel
```

**Design Decisions**:
- **Why Team node?** Teams can support multiple services (many-to-many relationship)
- **Why relationship properties?** `role` and `escalationLevel` describe the relationship, not the team itself
- **Why ordered escalation?** Enables automated escalation queries (find next-level team)

**Applies To**:
- Service support teams (`service.icmTeams`)
- Resource ownership (`resource.owners` - potential future extension)

---

### Pattern 6: Peer Relationships (Incident Relations)

**Use Case**: Model relationships between entities of the same type (siblings, not parent-child).

**Example**: Incident relationships (caused-by, duplicate-of)

```json
{
  "incidentId": "icm-alpha-001",
  "relatedIncidents": [
    {
      "incidentId": "icm-alpha-002",
      "relationship": "caused-by",
      "description": "Downstream dependency failure"
    }
  ]
}
```

**Graph Pattern**:
```cypher
(Incident {incidentId: "icm-alpha-001"})-[:RELATED_TO_INCIDENT {type: "caused-by"}]->(Incident {incidentId: "icm-alpha-002"})
```

**Query Pattern**:
```cypher
// Find cascading failures
MATCH path = (root:Incident {incidentId: $id})-[:RELATED_TO_INCIDENT*1..3]->(related:Incident)
RETURN path

// Find duplicate incidents
MATCH (i1:Incident)-[r:RELATED_TO_INCIDENT {type: "duplicate-of"}]->(i2:Incident)
RETURN i1.incidentId, i2.incidentId
```

**Design Decisions**:
- **Why not parent-child?** Incidents don't have containment; they're peers with relationships
- **Why directed relationship?** `caused-by` has direction (A caused B)
- **Why `type` property?** Different relationship types have different semantics (caused-by vs duplicate-of vs blocks)

**Applies To**:
- Incident relationships (`incident.relatedIncidents`)
- Service dependencies (potential future extension)

---

## Implementation Decisions

### Why APOC for JSON Import?

**Decision**: Use `apoc.load.json` instead of manual JSON parsing.

**Rationale**:
- Handles nested structures naturally
- Supports `UNWIND` for array processing
- Built-in NULL handling
- Better performance than manual parsing

**Trade-off**: Requires APOC plugin installation (acceptable for modern Neo4j deployments).

### Why `MERGE` vs `CREATE`?

**Decision**: Use `MERGE` for idempotent imports.

**Rationale**:
- Re-running import is safe (updates existing nodes)
- Enables incremental updates to sample data
- Prevents duplicate nodes on schema changes

**Trade-off**: Slightly slower than `CREATE` (acceptable for sample data scale).

### Property Naming: Nested vs Flat

**Decision**: Store deeply nested objects as flattened properties with `_` separators.

**Example**:
```json
// JSON structure
{
  "properties": {
    "compute": {
      "sku": "Standard_D4s_v3"
    }
  }
}

// Neo4j property
properties_compute_sku: "Standard_D4s_v3"
```

**Rationale**:
- Neo4j doesn't support nested property objects
- Flattening enables property indexing and filtering
- Clear separation with `_` maintains semantic hierarchy

**Trade-off**: Property names can be long (acceptable given clarity).

### Relationship vs Node Properties

**Decision**: Store relationship metadata on relationships when it describes the relationship itself, not the entities.

**Example**:
```cypher
// Good: impactLevel describes the outage→subscription relationship
(Outage)-[:IMPACTS_SUBSCRIPTION {impactLevel: "critical"}]->(Subscription)

// Bad: severity describes the incident itself, not the relationship
(Service)-[:HAS_INCIDENT {severity: 2}]->(Incident)

// Good: severity is property of incident
(Service)-[:HAS_INCIDENT]->(Incident {severity: 2})
```

**Rationale**:
- Relationship properties enable filtering relationships (`WHERE r.impactLevel = "critical"`)
- Node properties enable entity queries (`WHERE i.severity = 2`)
- Clear semantic distinction improves query clarity

---

## Extension Guidelines

### Adding New Hierarchies

**Step 1: Determine Pattern Type**

Use the [Pattern Catalog](#pattern-catalog) to identify which pattern fits your use case:
- Ordered sequence? → Pattern 1
- Dependency chain? → Pattern 2
- Multi-level nesting? → Pattern 3
- Configuration grouping? → Pattern 4
- Support relationships? → Pattern 5
- Peer relationships? → Pattern 6

**Step 2: Design JSON Structure**

```json
{
  "parentId": "...",
  "newHierarchy": [
    {
      "id": "...",           // Required: unique identifier
      "property1": "...",    // Entity properties
      "property2": "...",
      "relationships": []    // Optional: nested relationships
    }
  ]
}
```

**Step 3: Update Neo4j Import Script**

```cypher
// Load parent entity
CALL apoc.load.json("file:///sample-data/entity.json") YIELD value
MERGE (parent:ParentEntity {id: value.parentId})

// Unwind hierarchy array
WITH parent, value
UNWIND value.newHierarchy AS item

// Create child nodes
MERGE (child:ChildEntity {id: item.id})
SET child.property1 = item.property1,
    child.property2 = item.property2

// Create relationships
MERGE (parent)-[:HAS_CHILD {order: item.order}]->(child)
```

**Step 4: Document the Pattern**

Add to `sample-data/README.md`:
- JSON example
- Graph relationships created
- Example Cypher queries
- Use cases for risk assessment

**Step 5: Add Validation**

Update `scripts/validate_import.sh`:
```bash
# Count child nodes
docker exec neo4j-risk cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "MATCH (c:ChildEntity) RETURN count(c) AS children;"
```

### Extending Existing Hierarchies

**Adding Properties to Existing Nodes**:

```json
// Before
{
  "name": "alpha-api",
  "type": "docker-image"
}

// After
{
  "name": "alpha-api",
  "type": "docker-image",
  "newProperty": "value"  // Add new property
}
```

Update Cypher:
```cypher
SET child.newProperty = item.newProperty
```

**Adding Nested Levels**:

```json
// Before
{
  "artifact": {
    "name": "...",
    "type": "..."
  }
}

// After
{
  "artifact": {
    "name": "...",
    "type": "...",
    "metadata": {           // Add nested level
      "author": "...",
      "version": "..."
    }
  }
}
```

Decide: Promote to node or flatten to properties?
- Promote if `metadata` will have relationships to other entities
- Flatten otherwise: `artifact_metadata_author`, `artifact_metadata_version`

---

## Anti-Patterns (What NOT to Do)

### ❌ Over-Nesting

**Bad**:
```json
{
  "deployment": {
    "stages": [
      {
        "regions": [
          {
            "regionName": "westus",
            "healthChecks": [
              {
                "checks": [
                  {
                    "subChecks": [...]  // Too deep!
                  }
                ]
              }
            ]
          }
        ]
      }
    ]
  }
}
```

**Why**: Query complexity explodes, hard to maintain, unclear semantics.

**Fix**: Flatten intermediate levels, limit depth to 2-3.

### ❌ Mixing IDs and Objects

**Bad**:
```json
{
  "dependencies": [
    "shared-lib",           // String ID
    {                       // Object
      "name": "auth-lib",
      "version": "v2.0"
    }
  ]
}
```

**Why**: Inconsistent structure makes import logic complex.

**Fix**: Use consistent format (all strings or all objects):
```json
{
  "dependencies": [
    {"name": "shared-lib", "version": null},
    {"name": "auth-lib", "version": "v2.0"}
  ]
}
```

### ❌ Embedding Large Arrays

**Bad**:
```json
{
  "service": {
    "allHistoricalIncidents": [
      // 10,000 incidents here...
    ]
  }
}
```

**Why**: Makes JSON files huge, slows import, violates separation of concerns.

**Fix**: Keep hierarchies focused on operational context (recent history, active relationships), not historical archives.

### ❌ Redundant Hierarchies

**Bad**:
```json
{
  "service": {
    "resources": [
      {
        "resourceId": "res-123",
        "displayName": "...",
        "resourceType": "...",
        // Duplicates all resource properties here
      }
    ]
  }
}
```

**Why**: Data duplication, inconsistency risk, maintenance burden.

**Fix**: Use references (IDs) and relationships:
```json
{
  "service": {
    "resourceIds": ["res-123", "res-456"]  // Reference existing resources
  }
}
```

```cypher
// Create relationship to existing resource nodes
MERGE (s:Service {serviceId: value.serviceId})
WITH s, value
UNWIND value.resourceIds AS resourceId
MATCH (r:AzureResource {resourceName: resourceId})
MERGE (s)-[:OWNS_RESOURCE]->(r)
```

---

## Performance Considerations

### Indexing Hierarchical Nodes

Create indexes on frequently queried properties:

```cypher
// Index child nodes by parent relationship
CREATE INDEX child_order_idx FOR (c:ChildEntity) ON (c.order);

// Index by timestamp for temporal queries
CREATE INDEX timeline_event_timestamp_idx FOR (t:TimelineEvent) ON (t.timestamp);
```

### Query Optimization

1. **Use depth limits**: `[:DEPENDS_ON*1..3]` instead of `[:DEPENDS_ON*]`
2. **Add `LIMIT` to bounded queries**: `RETURN ... LIMIT 100`
3. **Use `OPTIONAL MATCH` for optional hierarchies**: Prevents query failure if hierarchy missing
4. **Aggregate before collecting**: `count(DISTINCT x)` then `collect(x)[..5]`

### Import Optimization

1. **Batch UNWIND operations**: Process arrays in batches of 1000 with `apoc.periodic.iterate`
2. **Create constraints before import**: Enables faster `MERGE` operations
3. **Use `apoc.load.json` with `path` filter**: Load specific files, not entire directory

---

## Versioning and Migration

### Adding New Hierarchies (Non-Breaking)

1. Add new JSON properties with default values
2. Update import script with `OPTIONAL MATCH` for new hierarchies
3. Re-run import (existing nodes updated, new nodes created)

### Changing Hierarchy Structure (Breaking)

1. Document migration path in `CHANGELOG.md`
2. Provide migration script to transform old → new structure
3. Support both formats during transition period
4. Deprecate old format with removal timeline

**Example**:
```bash
# Migration script
python scripts/migrate_v1_to_v2.py \
  --input sample-data/old_format/ \
  --output sample-data/new_format/
```

---

## Graph Schema Visualization

### Current Hierarchy Relationships

```
Service
  ├─[:SUPPORTED_BY_TEAM]──> Team
  ├─[:OWNS_RESOURCE]──────> AzureResource
  ├─[:HAS_INCIDENT]───────> Incident
  │                           ├─[:HAS_MITIGATION_STEP]──> MitigationStep
  │                           ├─[:RELATED_TO_INCIDENT]──> Incident
  │                           └─[:AFFECTS_RESOURCE]──────> AzureResource
  ├─[:OWNS_REPO]──────────> Repo
  │                           └─[:PRODUCES_ARTIFACT]─────> Artifact
  │                                └─[:DEPENDS_ON]────────> Artifact
  └─[:HAS_OUTAGE]─────────> Outage
                               ├─[:HAS_TIMELINE_EVENT]───> TimelineEvent
                               └─[:IMPACTS_SUBSCRIPTION]─> Subscription

Deployment
  └─[:HAS_STAGE]──────────> DeploymentStage

Template
  ├─[:DEPENDS_ON_TEMPLATE]─> Template
  ├─[:HAS_PARAMETER]───────> TemplateParameter
  └─[:HAS_OUTPUT]──────────> TemplateOutput
```

---

## Conclusion

Hierarchical structures transform flat data into rich, queryable graphs that mirror real-world operational complexity. By following these patterns and guidelines, you can extend the model to capture additional context while maintaining consistency, performance, and clarity.

**Key Takeaways**:
1. Promote nested data to nodes when it has independent identity or relationships
2. Use consistent relationship naming conventions
3. Limit nesting depth to 2-3 levels
4. Document patterns and provide query examples
5. Optimize for common query patterns with indexes and bounded retrievals

For questions or extensions, see `sample-data/README.md` and `risk_advisor/queries.md`.
