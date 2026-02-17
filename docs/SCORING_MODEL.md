# Scoring Model Reference

> **Model version:** `0.1`
> **Score range:** 0–100
> **Levels:** LOW (0–33), MEDIUM (34–66), HIGH (67–100)

## Overview

The scoring engine applies **14 deterministic rules** to pre-gathered
evidence. It performs no database queries — only arithmetic on evidence
values. The same inputs always produce the same score.

Each rule produces a `ScoreFactor` with:

| Field | Description |
|-------|-------------|
| `factor_id` | Stable identifier (e.g. `env.production`) |
| `status` | `hit` (points awarded), `miss` (0 points), `unknown` (evidence missing), `na` (not applicable) |
| `points` | Points awarded (0 to `max_points`) |
| `max_points` | Maximum possible points for this factor |
| `evidence` | The evidence values used for the decision |

The total score is `sum(factor.points)`, capped at 100.

## Factors

### 1. Environment Risk

| Factor | `env.production` |
|--------|-------------------|
| Max points | 20 |
| Evidence | `change.environment` |
| Logic | `prod` → 20 pts; anything else → 0 pts; missing → unknown |

### 2. Blast Radius — Services Impacted

| Factor | `blast_radius.services` |
|--------|--------------------------|
| Max points | 25 |
| Evidence | `services_impacted` (int) |

| Threshold | Points |
|-----------|--------|
| ≥ 5 services | 25 |
| ≥ 3 | 18 |
| 2 | 10 |
| 1 | 5 |
| 0 | 0 |

### 3. Blast Radius — Critical Services

| Factor | `blast_radius.critical_services` |
|--------|-----------------------------------|
| Max points | 15 |
| Evidence | `critical_services` (list of strings) |
| Logic | Any critical service impacted → 15 pts; empty list → 0 pts |

### 3b. Blast Radius — Subscriptions

| Factor | `blast_radius.subscriptions` |
|--------|-------------------------------|
| Max points | 10 |
| Evidence | `subscription_count` (int) |

| Threshold | Points |
|-----------|--------|
| ≥ 10 subscriptions | 10 |
| ≥ 5 | 7 |
| ≥ 2 | 4 |
| 1 | 2 |
| 0 | 0 |

> Subscription count is resolved via Service Tree
> `GetSubscriptionsAssociatedWith()` through the KustoEvidenceProvider
> (phase 2: k7 → ServiceId, phase 3: k10 → subscriptions).

### 4. Recent Outages (180 days)

| Factor | `history.outages_180d` |
|--------|-------------------------|
| Max points | 10 |
| Evidence | `historical_outages_180d` (int) |

| Threshold | Points |
|-----------|--------|
| ≥ 2 outages | 10 |
| 1 | 5 |
| 0 | 0 |

### 5. Open Incidents

| Factor | `ops.open_icms` |
|--------|------------------|
| Max points | 5 |
| Evidence | `open_icms` (int) |
| Logic | Any open IcM → 5 pts; 0 → 0 pts |

### 6. Deployment Frequency (30 days)

| Factor | `ops.deployments_30d` |
|--------|------------------------|
| Max points | 10 |
| Evidence | `deployment_count_30d` (int) |

| Threshold | Points |
|-----------|--------|
| ≥ 20 deployments | 10 |
| ≥ 10 | 5 |
| < 10 | 0 |

### 7. Destructive Operations

| Factor | `change.destructive` |
|--------|------------------------|
| Max points | 10 |
| Evidence | `change.operations` (list of strings) |
| Logic | Any `delete` or `destroy` operation → 10 pts; otherwise → 0 pts |
| Note | Status is `na` (not unknown) if no operations are provided |

### 8. Deployment Stage Failures

| Factor | `deployment.stage_failures` |
|--------|------------------------------|
| Max points | 15 |
| Evidence | `deployment_stage_failures` (int) |

| Threshold | Points |
|-----------|--------|
| ≥ 3 failures | 15 |
| 2 | 10 |
| 1 | 5 |
| 0 | 0 |

### 9. Slow Incident Mitigation (MTTM)

| Factor | `incident.mttm` |
|--------|-------------------|
| Max points | 10 |
| Evidence | `avg_mttm_minutes` (int) |

| Threshold | Points |
|-----------|--------|
| ≥ 60 minutes | 10 |
| ≥ 30 | 7 |
| ≥ 15 | 4 |
| < 15 | 0 |

### 10. Deep Artifact Dependencies

| Factor | `artifact.deep_deps` |
|--------|------------------------|
| Max points | 10 |
| Evidence | `max_dependency_depth` (int) |

| Threshold | Points |
|-----------|--------|
| ≥ 3 levels | 10 |
| 2 | 5 |
| ≤ 1 | 0 |

### 11. Peer Resources in Same ResourceGroup

| Factor | `resource.peer_impact` |
|--------|-------------------------|
| Max points | 8 |
| Evidence | `peer_resource_count` (int) |

| Threshold | Points |
|-----------|--------|
| ≥ 10 peers | 8 |
| ≥ 5 | 5 |
| ≥ 2 | 3 |
| < 2 | 0 |

### 12. Incident Recurrence

| Factor | `incident.recurrence` |
|--------|------------------------|
| Max points | 12 |
| Evidence | `related_incidents` (int) |

| Threshold | Points |
|-----------|--------|
| ≥ 3 related | 12 |
| 2 | 8 |
| 1 | 4 |
| 0 | 0 |

### 13. Template Dependency Complexity

| Factor | `template.complexity` |
|--------|------------------------|
| Max points | 10 |
| Evidence | `template_required_dependency_count` (int), `template_max_dependency_depth` (int) |

| Condition | Points |
|-----------|--------|
| > 3 required dependencies | +5 |
| dependency depth > 2 hops | +5 |

Both evidence keys must be present; if either is missing, the factor is
unknown.

## Summary Table

| # | Factor ID | Title | Max | Evidence Key(s) | Source |
|---|-----------|-------|-----|-----------------|--------|
| 1 | `env.production` | Production environment | 20 | `change.environment` | Change context |
| 2 | `blast_radius.services` | Services impacted | 25 | `services_impacted` | Neo4j / Kusto |
| 3 | `blast_radius.critical_services` | Critical services | 15 | `critical_services` | Neo4j / Kusto (k7) |
| 3b | `blast_radius.subscriptions` | Subscriptions | 10 | `subscription_count` | Kusto (k10) |
| 4 | `history.outages_180d` | Recent outages | 10 | `historical_outages_180d` | Kusto (k5) |
| 5 | `ops.open_icms` | Open incidents | 5 | `open_icms` | Kusto (k1) |
| 6 | `ops.deployments_30d` | Deploy frequency | 10 | `deployment_count_30d` | Kusto (k8) |
| 7 | `change.destructive` | Destructive ops | 10 | `change.operations` | Change context |
| 8 | `deployment.stage_failures` | Stage failures | 15 | `deployment_stage_failures` | Kusto (k9) |
| 9 | `incident.mttm` | Slow mitigation | 10 | `avg_mttm_minutes` | Kusto (k4) |
| 10 | `artifact.deep_deps` | Deep dependencies | 10 | `max_dependency_depth` | Neo4j |
| 11 | `resource.peer_impact` | Peer resources | 8 | `peer_resource_count` | Neo4j (Kusto: unknown) |
| 12 | `incident.recurrence` | Incident recurrence | 12 | `related_incidents` | Kusto (k6) |
| 13 | `template.complexity` | Template complexity | 10 | `template_required_dep…`, `template_max_dep…` | Neo4j |
| | | **Total possible** | **170** | | |

> The maximum possible score exceeds 100; the engine caps at 100.
> In practice, a service hitting every factor at max is extremely rare.

## Evidence Sources

Evidence is gathered by pluggable providers before scoring runs:

| Provider | Keys Populated |
|----------|----------------|
| `Neo4jEvidenceProvider` | `services_impacted`, `critical_services`, `max_dependency_depth`, `peer_resource_count`, `template_required_dependency_count`, `template_max_dependency_depth` |
| `KustoEvidenceProvider` | `open_icms`, `avg_mttm_minutes`, `historical_outages_180d`, `related_incidents`, `deployment_count_30d`, `deployment_stage_failures`, `service_tree_id`, `service_subscriptions`, `subscription_count`, `source_repos`, `repo_count`, `services_impacted`, `critical_services`, `peer_resource_count` |

The KQL queries are defined in `risk_scoring/kusto_allowlist.py`:

| Query ID | Evidence Key | Kusto Source | Description |
|----------|-------------|--------------|-------------|
| `k1.open_icms` | `open_icms` | icm | Open IcM incidents |
| `k4.avg_mttm` | `avg_mttm_minutes` | icm | Avg mitigation time (180d) |
| `k5.outages_180d` | `historical_outages_180d` | icm | Outage count (180d) |
| `k6.related_incidents` | `related_incidents` | icm | Parent-linked clusters (90d) |
| `k7.service_tree_lookup` | `service_tree_id` | service_tree | Service name → ServiceId |
| `k8.deployment_count_30d` | `deployment_count_30d` | safefly | SafeFly deploys (30d) |
| `k9.deployment_failures` | `deployment_stage_failures` | safefly | Abandoned/rejected deploys (90d) |
| `k10.service_subscriptions` | `service_subscriptions` | service_tree | Service → Azure subscriptions |
| `k11.repo_to_service` | `repo_service_mapping` | service_tree | Repo URL → ServiceId (reverse lookup) |
| `k12.service_repos` | `source_repos` | service_tree | Service → registered source code repos |

## Unknowns

When an evidence key is missing (provider error, no data source configured),
the factor is marked `unknown` with 0 points and the evidence key is added
to the `unknowns` list in `ScoreResult`. This ensures:

- Scores are **conservative** (unknown ≠ risky).
- The report clearly shows what data was unavailable.
- Providers can be added incrementally without breaking existing scores.
