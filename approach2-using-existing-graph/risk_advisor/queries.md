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

