# Risk Scoring Model v0.2

Deterministic, evidence-based scoring for IaC change risk assessment.

## Design Principles

1. **Deterministic** — same inputs always produce the same score.
2. **Evidence-based** — every point is traceable to a specific data source.
3. **Kusto-first** — all 10 factors are available in Kusto-only mode (no Neo4j required).
4. **No cap needed** — factors sum to exactly 100 maximum.

## Risk Levels

| Score Range | Level   |
|-------------|---------|
| 0–33        | LOW     |
| 34–66       | MEDIUM  |
| 67–100      | HIGH    |

## Factors (10 total, max 100 pts)

| # | Factor ID | Title | Max Pts | Evidence Key | Source |
|---|-----------|-------|---------|--------------|--------|
| 1 | `deployment.change_caused_outages` | SafeFly-caused outages (180d) | 15 | `safefly_caused_outages_180d` | SafeFly/IcM (k14) |
| 2 | `incident.recurrence` | Similar past incidents | 12 | `related_incidents` | IcM (k6) |
| 3 | `blast_radius.subscriptions` | Blast radius (subscriptions) | 12 | `subscription_count` | Service Tree (k10) |
| 4 | `history.outages_180d` | Recent outages (180d) | 10 | `historical_outages_180d` | IcM (k5) |
| 5 | `incident.mttm` | Slow incident mitigation | 10 | `avg_mttm_minutes` | IcM (k4) |
| 6 | `ops.deployments_30d` | Deployment frequency (30d) | 10 | `deployment_count_30d` | SafeFly (k8) |
| 7 | `change.destructive` | Destructive operations | 10 | `operations` (from ChangeContext) | Caller input |
| 8 | `incident.severity_mix` | High-severity incidents (Sev1/2, 180d) | 8 | `sev12_incident_count` | IcM (k15) |
| 9 | `resource.peer_impact` | Resources in same ResourceGroup | 8 | `peer_resource_count` | ARG (k13) |
| 10 | `ops.recent_active_outages` | Recent active outages (7d) | 5 | `recent_active_outages` | IcM (k1) |

**Total maximum: 100 pts**

## Scoring Thresholds

### Rule 1: SafeFly-caused outages (15 pts)

| Condition | Points |
|-----------|--------|
| `safefly_caused_outages_180d >= 3` | 15 |
| `>= 2` | 10 |
| `== 1` | 5 |
| `== 0` | 0 |

### Rule 2: Incident recurrence (12 pts)

| Condition | Points |
|-----------|--------|
| `related_incidents >= 3` | 12 |
| `>= 2` | 8 |
| `== 1` | 4 |
| `== 0` | 0 |

### Rule 3: Blast radius — subscriptions (12 pts)

| Condition | Points |
|-----------|--------|
| `subscription_count >= 10` | 12 |
| `>= 5` | 8 |
| `>= 2` | 5 |
| `== 1` | 2 |
| `== 0` | 0 |

### Rule 4: Recent outages (10 pts)

| Condition | Points |
|-----------|--------|
| `historical_outages_180d >= 2` | 10 |
| `== 1` | 5 |
| `== 0` | 0 |

### Rule 5: Slow incident mitigation — MTTM (10 pts)

| Condition | Points |
|-----------|--------|
| `avg_mttm_minutes >= 60` | 10 |
| `>= 30` | 7 |
| `>= 15` | 4 |
| `< 15` | 0 |

### Rule 6: Deployment frequency (10 pts)

| Condition | Points |
|-----------|--------|
| `deployment_count_30d >= 20` | 10 |
| `>= 10` | 5 |
| `< 10` | 0 |

### Rule 7: Destructive operations (10 pts)

| Condition | Points |
|-----------|--------|
| Any operation in `{delete, destroy}` | 10 |
| Otherwise | 0 |
| No operations provided | `na` (0 pts) |

### Rule 8: Incident severity mix (8 pts)

| Condition | Points |
|-----------|--------|
| `sev12_incident_count >= 3` | 8 |
| `>= 2` | 5 |
| `== 1` | 3 |
| `== 0` | 0 |

### Rule 9: Peer resource impact (8 pts)

| Condition | Points |
|-----------|--------|
| `peer_resource_count >= 10` | 8 |
| `>= 5` | 5 |
| `>= 2` | 3 |
| `< 2` | 0 |

### Rule 10: Recent active outages (5 pts)

| Condition | Points |
|-----------|--------|
| `recent_active_outages > 0` | 5 |
| `== 0` | 0 |

## Unknown Handling

When an evidence key is missing (`None`), the factor status is `"unknown"` and contributes 0 points. Unknown evidence keys are collected and reported in `ScoreResult.unknowns`.

## Changes from v0.1

### Removed factors (5)
| Factor | Reason |
|--------|--------|
| `env.production` (0 pts) | Always scored 0 — provided no signal |
| `blast_radius.services` (25 pts) | `services_impacted` was always unknown |
| `blast_radius.critical_services` (5 pts) | Folded into service metadata; not actionable as a separate factor |
| `deployment.stage_failures` (15 pts) | `deployment_stage_failures` was always unknown |
| `artifact.deep_deps` (10 pts) | Required Neo4j; not available in Kusto-only mode |

### Added factor (1)
| Factor | Points | Description |
|--------|--------|-------------|
| `incident.severity_mix` | 8 | Count of Sev1/Sev2 incidents (180d) via k15 KQL query |

### Rebalanced
- `blast_radius.subscriptions`: 10 → 12 pts max, thresholds adjusted
- `resource.peer_impact`: 5 → 8 pts max, thresholds adjusted
- Total max: 145 (v0.1, capped to 100) → 100 (v0.2, no cap needed)
