# Risk advisor — natural-language query playbook (Approach 2)

This document is a playbook for asking *natural-language* questions about the **risk of making a change** to a graph entity, using the **Neo4j MCP server**.

Constraints (MVP)
- Read-only: all Cypher must be `MATCH/RETURN` only.
- Template-only queries: do not execute user-provided Cypher.
- Bounded retrieval: use `LIMIT` and a max traversal depth (recommendation: <= 2 hops).
- Input is an entity ID (start with `serviceId`, `resourceId`, and `subscriptionId`).

## Entity IDs (MVP)

- Service: `Service.serviceId`
- Azure Resource: `AzureResource.resourceId`
- Subscription: `Subscription.subscriptionId`

If the ID could be ambiguous, require the caller to supply an explicit type (e.g., `Service` vs `AzureResource`).

## How to use this in VS Code Copilot Chat

Recommended pattern:
1. User provides: entity type + ID + “what change?” (optional).
2. Assistant resolves the entity node by ID.
3. Assistant runs a small, fixed set of evidence queries (below).
4. Assistant answers with:
   - Summary risk (narrative and optionally Low/Med/High)
   - Key risk factors
   - Evidence (facts returned by queries)
   - Unknowns (missing data / gaps)

### Copy/paste prompts (examples)

Service example:

"""
You are a read-only risk advisor. I want a risk assessment for changing this Service.

Entity:
- type: Service
- id (serviceId): <PASTE_SERVICE_ID>

Question:
- What is the blast radius and what does incident history suggest about change risk?

Constraints:
- Read-only queries only
- Use bounded evidence queries (<=2 hops, LIMIT)
- Summarize with evidence + unknowns
"""

AzureResource example:

"""
You are a read-only risk advisor.

Entity:
- type: AzureResource
- id (resourceId): res-delta-k8s

Question:
- If I change this resource, what Services might be impacted and why?

Constraints:
- Read-only queries only
- Use bounded evidence queries (<=2 hops, LIMIT)
- Summarize with evidence + unknowns
"""

Subscription example:

"""
You are a read-only risk advisor.

Entity:
- type: Subscription
- id (subscriptionId): <PASTE_SUBSCRIPTION_ID>

Question:
- If I make a subscription-scoped change, what Services/resources could be affected?

Constraints:
- Read-only queries only
- Use bounded evidence queries (<=2 hops, LIMIT)
- Summarize with evidence + unknowns
"""

## Evidence query templates (conceptual)

These are *templates* — the actual allowlisted Cypher will live elsewhere. Keep these as the canonical “what evidence do we fetch” spec.

### T1 — Resolve entity by ID

Purpose: prove the ID exists and fetch minimal identifying attributes.

Parameters:
- `$entityId`

Output fields:
- `label` (Service/AzureResource)
- `id` (serviceId/resourceId)
- `name`/`resourceName` (if present)

### T2 — Blast radius (neighbors up to 2 hops)

Purpose: identify immediate connected entities that could be impacted.

Parameters:
- `$serviceId` or `$resourceId`

Evidence to extract:
- For Service: owned resources, subscriptions, repos, deployments, teams
- For AzureResource: owning service (if tagged), resource group, subscription

### T2b — Subscription blast radius (what lives in this subscription)

Purpose: determine cross-service impact potential at the subscription scope.

Parameters:
- `$subscriptionId`

Evidence to extract:
- Services using the subscription (`(:Service)-[:USES_SUBSCRIPTION]->(:Subscription)`)
- Azure resources in the subscription (`(:AzureResource)-[:IN_SUBSCRIPTION]->(:Subscription)`)
- Resource groups in the subscription (if modeled) and how many entities attach to them

### T3 — Incident history for related services

Purpose: use incident history as a proxy for operational risk.

Parameters:
- `$serviceId`
- Optional `$since` (if we want time window)

Evidence to extract:
- `severity`
- `changeRelated`
- `createdDate`
- `title`/`rootCause` (if present)

### T4 — Deployments targeting the same blast radius

Purpose: detect frequent or risky deployment activity around the same service/RG.

Parameters:
- `$serviceId` (and/or derived resource groups)

Evidence to extract:
- rollout IDs, timestamps (if present), targeted resource group

## Natural-language questions (examples)

Each example lists:
- **Input** (entity ID)
- **Evidence to fetch** (templates)
- **What a good answer includes**

### Q1) “If I change this service, what’s the blast radius?”

Input:
- `serviceId=<...>`

Evidence:
- T1 (resolve)
- T2 (blast radius)

Good answer includes:
- Which subscriptions and resource groups are touched
- Count + key resource types owned by the service
- Linked repos (potential code ownership surface)
- Explicit unknowns (e.g., no resource-to-resource dependency edges)

### Q2) “If I change this service, what does incident history say about risk?”

Input:
- `serviceId=<...>`

Evidence:
- T1
- T3

Good answer includes:
- Any recent high-severity incidents
- Whether incidents are commonly `changeRelated=Yes`
- Any repeated themes in root cause (if present)

### Q3) “If I change this resource, what services might break?”

Input:
- `resourceId=<...>`

Evidence:
- T1
- T2 (resource → owning service; resource → RG/subscription)
- T3 (incident history for owning service)

Good answer includes:
- Owning service (or that ownership is unknown)
- Whether the owning service has change-related incidents
- Caution if the resource is shared via subscription/RG (even if explicit deps aren’t modeled)

### Q4) “Changing a resource in this subscription — what’s the potential impact?”

Input:
- `serviceId=<...>` (starting point)

Evidence:
- T2 to list subscriptions
- For each subscription, list other services using it (via allowlisted subscription query)

Good answer includes:
- Whether the subscription is multi-tenant across multiple services
- A warning that subscription-wide changes may have cross-service impact

### Q7) “If I change this subscription, what could break?”

Input:
- `subscriptionId=<...>`

Evidence:
- T1
- T2b (subscription blast radius)
- T3 for each affected service (bounded: top N services only)

Good answer includes:
- List of impacted services (top N) and why they’re in-scope
- Summary of incident history for the most affected/critical services
- Clear caveat that resource-to-resource dependencies may not be fully modeled

### Q5) “If I change infra for this service, who should be involved?”

Input:
- `serviceId=<...>`

Evidence:
- T2 (team ownership, repos)

Good answer includes:
- Owning team
- Source repos to review / code owners (if repo graph is accurate)

### Q6) “Are there recent deployments around this service that raise risk?”

Input:
- `serviceId=<...>`

Evidence:
- T4
- T3 (optional)

Good answer includes:
- Whether there are frequent rollouts targeting the same RGs
- Caveats if rollout dates aren’t available

## Known limitations of the current sample graph

- The sample model does not encode full *resource-to-resource* runtime dependencies, so blast radius is primarily ownership/containment (Service ↔ Resource ↔ RG ↔ Subscription) + incident/deployment history.
- Template-to-subscription mapping may be partial (some templates ingest with `UNKNOWN` subscription).

---

# Hierarchical Query Examples

The sample data now includes rich hierarchical structures that enable deep traversals and better operational context. This section provides practical Cypher query examples for working with hierarchies.

## Deployment Stage Hierarchies

### Q8) "Show all stages of a deployment with their health status"

**Input:**
- `deploymentId=deploy-alpha-001`

**Evidence to fetch:**
```cypher
MATCH (d:Deployment {deploymentId: $deploymentId})-[:HAS_STAGE]->(stage:DeploymentStage)
RETURN d.deploymentId, 
       stage.name, 
       stage.order, 
       stage.status, 
       stage.regions, 
       stage.percentage,
       stage.startTime,
       stage.endTime
ORDER BY stage.order
```

**Good answer includes:**
- Ordered list of deployment stages (canary → regional → global)
- Health status of each stage (succeeded, failed, in-progress)
- Traffic percentage rollout progression
- Regional expansion pattern
- Duration of each stage

**Usage in risk assessment:**
- Failed stages indicate high-risk change patterns
- Long-duration stages may indicate complexity
- Multi-region rollouts show blast radius expansion

### Q9) "Find deployments that had stage failures"

**Evidence:**
```cypher
MATCH (d:Deployment)-[:HAS_STAGE]->(stage:DeploymentStage {status: 'failed'})
RETURN d.deploymentId, 
       d.serviceId, 
       stage.name, 
       stage.order,
       stage.status,
       d.timestamp
ORDER BY d.timestamp DESC
LIMIT 10
```

**Good answer includes:**
- Which deployments had stage failures
- Which stage failed (canary failures less risky than global)
- Service affected by failed deployment
- Temporal pattern of failures

**Usage in risk assessment:**
- Services with recent stage failures are higher risk for changes
- Canary failures indicate testing caught issues before wide rollout
- Global stage failures indicate severe reliability concerns

## Incident Timeline Hierarchies

### Q10) "Show incident mitigation timeline"

**Input:**
- `incidentId=icm-alpha-001`

**Evidence:**
```cypher
MATCH (i:Incident {incidentId: $incidentId})-[:HAS_MITIGATION_STEP]->(step:MitigationStep)
RETURN i.incidentId, 
       i.severity,
       step.step, 
       step.action, 
       step.timestamp, 
       step.assignee
ORDER BY step.step
```

**Good answer includes:**
- Ordered sequence of mitigation actions
- Time between steps (response speed)
- Engineer assignments (team coordination)
- Actions taken (rollback, config change, restart)

**Usage in risk assessment:**
- Fast mitigation (< 30 min) indicates good incident response
- Multiple assignees indicate complex incidents
- Rollback actions indicate deployment-related failures
- Repeated incidents with similar mitigation patterns indicate systemic issues

### Q11) "Find incidents with complex mitigation (many steps)"

**Evidence:**
```cypher
MATCH (i:Incident)-[:HAS_MITIGATION_STEP]->(step:MitigationStep)
WITH i, count(step) AS stepCount
WHERE stepCount >= 5
RETURN i.incidentId, 
       i.serviceId, 
       i.severity, 
       stepCount,
       i.createdAt
ORDER BY stepCount DESC
LIMIT 10
```

**Good answer includes:**
- Incidents requiring many mitigation steps (complex failures)
- Services with complex incident patterns
- Correlation between severity and mitigation complexity

**Usage in risk assessment:**
- Services with complex incidents are higher risk
- Many mitigation steps indicate unclear failure modes
- Suggests need for better monitoring/automation

## Outage Timeline Hierarchies

### Q12) "Show outage timeline events"

**Input:**
- `outageId=outage-alpha-001`

**Evidence:**
```cypher
MATCH (o:Outage {outageId: $outageId})-[:HAS_TIMELINE_EVENT]->(event:TimelineEvent)
RETURN o.outageId, 
       o.serviceId,
       event.event, 
       event.timestamp, 
       event.source, 
       event.action
ORDER BY event.timestamp
```

**Good answer includes:**
- Detection time (first event timestamp)
- Time to mitigation start
- Time to service restoration
- Event sources (monitoring, human, automation)

**Usage in risk assessment:**
- Long detection times indicate monitoring gaps
- Long mitigation times indicate operational complexity
- Automated actions indicate mature incident response

### Q13) "Find outages with slow detection (> 10 min between start and detection)"

**Evidence:**
```cypher
MATCH (o:Outage)-[:HAS_TIMELINE_EVENT]->(detection:TimelineEvent)
WHERE detection.event CONTAINS 'detected'
WITH o, 
     datetime(o.startTime) AS outageStart,
     datetime(detection.timestamp) AS detectionTime
WITH o, duration.between(outageStart, detectionTime).minutes AS detectionDelayMinutes
WHERE detectionDelayMinutes > 10
RETURN o.outageId, 
       o.serviceId, 
       detectionDelayMinutes,
       o.startTime
ORDER BY detectionDelayMinutes DESC
LIMIT 10
```

**Good answer includes:**
- Services with slow outage detection
- Detection delay patterns (monitoring blind spots)

**Usage in risk assessment:**
- Slow detection increases blast radius
- Indicates monitoring gaps for that service
- Higher risk for unmonitored changes

## Artifact Dependency Hierarchies

### Q14) "Show artifact dependency chains"

**Input:**
- `artifactName=alpha-api-service`

**Evidence:**
```cypher
MATCH (r:Repo)-[:PRODUCES_ARTIFACT]->(a:Artifact {name: $artifactName})
OPTIONAL MATCH path = (a)-[:DEPENDS_ON*1..3]->(dep:Artifact)
RETURN r.repoName, 
       a.name, 
       a.type,
       collect(DISTINCT dep.name) AS dependencies,
       length(path) AS depthLevel
ORDER BY depthLevel
```

**Good answer includes:**
- Artifact build configuration (Dockerfile, context)
- Direct dependencies (depth 1)
- Transitive dependencies (depth 2-3)
- Dependency tree structure

**Usage in risk assessment:**
- Artifacts with many dependencies have higher change risk
- Deep dependency chains increase failure surface
- Shared dependencies (used by multiple artifacts) amplify risk

### Q15) "Find artifacts with no dependencies (leaf artifacts)"

**Evidence:**
```cypher
MATCH (r:Repo)-[:PRODUCES_ARTIFACT]->(a:Artifact)
WHERE NOT (a)-[:DEPENDS_ON]->(:Artifact)
RETURN r.repoName, 
       a.name, 
       a.type
```

**Good answer includes:**
- Self-contained artifacts (lower risk)
- Services with minimal external dependencies

**Usage in risk assessment:**
- Leaf artifacts have lower blast radius
- Good candidates for experimental changes
- Minimal coordination required for changes

### Q16) "Find artifacts that are dependencies for many other artifacts (shared libraries)"

**Evidence:**
```cypher
MATCH (shared:Artifact)<-[:DEPENDS_ON]-(dependent:Artifact)
WITH shared, count(DISTINCT dependent) AS dependentCount
WHERE dependentCount >= 2
RETURN shared.name, 
       shared.type,
       dependentCount,
       collect(dependent.name)[..5] AS sampleDependents
ORDER BY dependentCount DESC
```

**Good answer includes:**
- Shared libraries/components
- Number of artifacts depending on each shared component
- Sample dependents (blast radius preview)

**Usage in risk assessment:**
- Changes to shared artifacts have HIGH risk
- Requires coordination across multiple teams
- Breaking changes impact many services
- Suggests need for versioning/compatibility testing

## Template Dependency Hierarchies

### Q17) "Show template dependency tree"

**Input:**
- `templateName=template-alpha-app`

**Evidence:**
```cypher
MATCH (t:Template {templateName: $templateName})
OPTIONAL MATCH path = (t)-[:DEPENDS_ON_TEMPLATE*1..2]->(dep:Template)
RETURN t.templateName, 
       dep.templateName, 
       length(path) AS depthLevel,
       t.path AS mainTemplatePath,
       dep.path AS dependencyPath
ORDER BY depthLevel
```

**Good answer includes:**
- Direct template dependencies (depth 1)
- Transitive template dependencies (depth 2)
- Template file paths for review
- Required vs optional dependencies

**Usage in risk assessment:**
- Template changes may require updating dependent templates
- Deep dependency chains increase coordination needs
- Shared templates (used by many) are high-risk to change

### Q18) "Find templates with parameters and their validation rules"

**Input:**
- `templateName=template-alpha-app`

**Evidence:**
```cypher
MATCH (t:Template {templateName: $templateName})-[:HAS_PARAMETER]->(p:TemplateParameter)
RETURN t.templateName, 
       p.name, 
       p.type, 
       p.default,
       p.validation
ORDER BY p.name
```

**Good answer includes:**
- Parameter names and types
- Default values (what happens if not specified)
- Validation rules (allowed values, ranges)
- Required vs optional parameters

**Usage in risk assessment:**
- Changes to parameter validation can break existing deployments
- Missing required parameters cause deployment failures
- Overly permissive validation increases risk

### Q19) "Find templates with outputs (API contracts)"

**Input:**
- `templateName=template-alpha-app`

**Evidence:**
```cypher
MATCH (t:Template {templateName: $templateName})-[:HAS_OUTPUT]->(o:TemplateOutput)
RETURN t.templateName, 
       o.name, 
       o.type, 
       o.description
ORDER BY o.name
```

**Good answer includes:**
- Output names (used by dependent templates/code)
- Output types (string, object, array)
- Output descriptions (semantic meaning)

**Usage in risk assessment:**
- Changes to output names/types break downstream consumers
- Templates with many outputs have higher coupling
- Removing outputs is a breaking change

## Service Support Team Hierarchies

### Q20) "Show service support teams with escalation paths"

**Input:**
- `serviceId=svc-alpha`

**Evidence:**
```cypher
MATCH (s:Service {serviceId: $serviceId})-[:SUPPORTED_BY_TEAM]->(team:Team)
RETURN s.name, 
       team.teamName, 
       team.role, 
       team.escalationLevel
ORDER BY team.escalationLevel
```

**Good answer includes:**
- Primary oncall team (escalationLevel = 1)
- Secondary/backup teams
- Team roles (primary, secondary, backup)
- Escalation order

**Usage in risk assessment:**
- Changes require coordination with primary team
- Multiple teams indicate shared ownership complexity
- Escalation paths show incident response maturity

### Q21) "Find services with no oncall teams (orphaned services)"

**Evidence:**
```cypher
MATCH (s:Service)
WHERE NOT (s)-[:SUPPORTED_BY_TEAM]->(:Team)
RETURN s.serviceId, 
       s.name, 
       s.tier,
       s.isCritical
```

**Good answer includes:**
- Unowned services (no team assigned)
- Critical services without support teams (HIGH RISK)

**Usage in risk assessment:**
- Orphaned services are HIGH RISK for changes
- No clear incident response owner
- Likely to have stale configuration/code

## Incident Relationship Hierarchies

### Q22) "Find related incidents (cascading failures)"

**Input:**
- `incidentId=icm-alpha-001`

**Evidence:**
```cypher
MATCH (i:Incident {incidentId: $incidentId})-[:RELATED_TO_INCIDENT]->(related:Incident)
RETURN i.incidentId, 
       i.serviceId AS rootService,
       related.incidentId, 
       related.serviceId AS relatedService,
       related.severity,
       related.createdAt
ORDER BY related.createdAt
```

**Good answer includes:**
- Incident cascade chains (one failure causes another)
- Cross-service failure propagation
- Temporal relationship (which happened first)

**Usage in risk assessment:**
- Services involved in cascading failures are high risk
- Indicates tight runtime coupling between services
- Changes may trigger downstream failures

### Q23) "Find incident clusters (multiple related incidents)"

**Evidence:**
```cypher
MATCH (root:Incident)-[:RELATED_TO_INCIDENT*1..2]->(related:Incident)
WITH root, count(DISTINCT related) AS relatedCount
WHERE relatedCount >= 3
RETURN root.incidentId, 
       root.serviceId, 
       root.severity,
       relatedCount,
       root.createdAt
ORDER BY relatedCount DESC, root.createdAt DESC
LIMIT 10
```

**Good answer includes:**
- Incidents with many related incidents (systemic failures)
- Services involved in incident clusters
- Temporal patterns

**Usage in risk assessment:**
- Incident clusters indicate systemic issues
- HIGH RISK for changes to affected services
- May require architectural changes, not just config updates

## Outage Impact Hierarchies

### Q24) "Find outages with high user impact"

**Evidence:**
```cypher
MATCH (o:Outage)-[:IMPACTS_SUBSCRIPTION]->(s:Subscription)
WITH o, sum(o.impactedUsers) AS totalUsers
WHERE totalUsers > 10000
RETURN o.outageId, 
       o.serviceId, 
       totalUsers,
       o.startTime,
       o.endTime,
       duration.between(datetime(o.startTime), datetime(o.endTime)).minutes AS durationMinutes
ORDER BY totalUsers DESC
LIMIT 10
```

**Good answer includes:**
- Outages affecting many users (high blast radius)
- Outage duration (user impact × time)
- Services with high-impact outages

**Usage in risk assessment:**
- Services with high-impact outages are high risk
- Indicates critical user-facing services
- Changes require extra validation/testing

## Multi-Hop Hierarchical Queries

### Q25) "Full service context with all hierarchies"

**Input:**
- `serviceId=svc-alpha`

**Evidence:**
```cypher
MATCH (s:Service {serviceId: $serviceId})

// Teams
OPTIONAL MATCH (s)-[:SUPPORTED_BY_TEAM]->(team:Team)

// Resources
OPTIONAL MATCH (s)-[:OWNS_RESOURCE]->(r:AzureResource)

// Recent incidents with mitigation steps
OPTIONAL MATCH (s)-[:HAS_INCIDENT]->(i:Incident)-[:HAS_MITIGATION_STEP]->(step:MitigationStep)
WHERE datetime(i.createdAt) > datetime() - duration({days: 180})

// Recent deployments with stages
OPTIONAL MATCH (s)<-[:DEPLOYS_TO]-(d:Deployment)-[:HAS_STAGE]->(stage:DeploymentStage)
WHERE datetime(d.timestamp) > datetime() - duration({days: 90})

// Repos with artifacts
OPTIONAL MATCH (s)-[:OWNS_REPO]->(repo:Repo)-[:PRODUCES_ARTIFACT]->(artifact:Artifact)

RETURN s.serviceId,
       s.name,
       s.tier,
       s.isCritical,
       collect(DISTINCT team.teamName) AS teams,
       count(DISTINCT r) AS resourceCount,
       count(DISTINCT i) AS recentIncidentCount,
       count(DISTINCT d) AS recentDeploymentCount,
       count(DISTINCT artifact) AS artifactCount,
       collect(DISTINCT {
         incidentId: i.incidentId, 
         severity: i.severity, 
         mitigationSteps: count(DISTINCT step)
       })[..5] AS sampleIncidents,
       collect(DISTINCT {
         deploymentId: d.deploymentId, 
         status: d.status, 
         stageCount: count(DISTINCT stage)
       })[..5] AS sampleDeployments
```

**Good answer includes:**
- Complete operational context for service
- Team ownership and escalation paths
- Resource footprint
- Incident history with mitigation complexity
- Deployment frequency and stage patterns
- Build artifact inventory

**Usage in risk assessment:**
- Comprehensive risk profile for service changes
- Identifies multiple risk factors across hierarchies
- Enables multi-dimensional risk scoring
- Shows operational maturity indicators (teams, stages, mitigation speed)

---

## Best Practices for Hierarchical Queries

1. **Use ORDER BY for temporal hierarchies**: Timeline events, mitigation steps, deployment stages
2. **Use LIMIT for bounded retrieval**: Prevent runaway queries on deep hierarchies
3. **Use OPTIONAL MATCH for optional hierarchies**: Not all entities have all hierarchies
4. **Use depth limits on variable-length paths**: `[:DEPENDS_ON*1..3]` instead of `[:DEPENDS_ON*]`
5. **Collect nested data sparingly**: Use `collect()[..5]` to sample nested results
6. **Aggregate counts before collecting**: `count(DISTINCT x)` before `collect(x)` for efficiency

## Hierarchy-Specific Risk Indicators

| Hierarchy | Risk Indicator | Threshold |
|-----------|----------------|-----------|
| Deployment Stages | Failed stages | Any failures in last 90 days |
| Mitigation Steps | Complex incidents | ≥ 5 steps |
| Timeline Events | Slow detection | > 10 min delay |
| Artifact Dependencies | Shared libraries | Used by ≥ 3 artifacts |
| Template Dependencies | Deep chains | Depth ≥ 3 |
| Incident Relations | Cascading failures | ≥ 2 related incidents |
| User Impact | High blast radius | ≥ 10,000 users |
| Team Support | Orphaned services | No teams assigned |

These hierarchical queries enable the risk advisor to provide much richer context than flat data models, leading to better risk assessments and operational insights.

