---
description: Synthesize evidence from Service Tree, IcM, EV2, and ADO into a deterministic risk score and report
name: Risk Synthesizer
tools: []
---
# Risk Synthesizer Skill

## Purpose

Take the evidence gathered by the Service Tree, IcM, EV2, and ADO skills
and produce a **deterministic risk score** (0–100) with factor breakdown,
severity level, and actionable recommendations.

This skill performs **no MCP tool calls** — it is pure reasoning over the
evidence collected by the other skills.

## Inputs

| Input | Required | Description |
|-------|----------|-------------|
| `service_name` | Yes | The service being assessed |
| `environment` | Yes | Target environment (prod/staging/dev/test) |
| `operations` | No | List of planned operations (e.g., ["delete", "update"]) |
| `service_tree_evidence` | Yes* | Output from the Service Tree Evidence skill |
| `icm_evidence` | Yes* | Output from the IcM Evidence skill |
| `ev2_evidence` | Yes* | Output from the EV2 Evidence skill |
| `ado_evidence` | No | Output from the ADO Evidence skill (enrichment only) |

*If a skill was skipped (e.g., no EV2 service ID), pass `null`.

## Subscription Source Priority

For Factor 3 (Blast Radius — Subscriptions), resolve `subscription_count`
in this order:

1. **Service Tree** `subscription_count` (production subscriptions) — preferred
2. **EV2** `subscription_count` (registered subscriptions) — fallback
3. If both are `null` → Factor 3 = unknown (0 pts)

Note which source was used in the evidence column of the factor table.

## Scoring Rubric

### Risk Levels

| Level | Score Range | Meaning |
|-------|-------------|---------|
| **LOW** | 0–33 | Safe to proceed with standard review |
| **MEDIUM** | 34–66 | Proceed with caution; review flagged factors |
| **HIGH** | 67–100 | Significant risk; consider additional safeguards |

### Core Factors (100 points max)

Apply each factor independently. Sum all points, cap at 100.

#### Factor 1: Deployment-Caused Outages (max 15 pts)

| Evidence Key | Source |
|---|---|
| `safefly_caused_outages_180d` | EV2 evidence (cross-referenced with IcM) |

| Threshold | Points |
|-----------|--------|
| ≥ 3 deployment-caused outages | 15 |
| 2 | 10 |
| 1 | 5 |
| 0 | 0 |
| `null` (unknown) | 0, mark as unknown |

#### Factor 2: Similar Past Incidents (max 12 pts)

| Evidence Key | Source |
|---|---|
| `related_incidents` | IcM evidence |

| Threshold | Points |
|-----------|--------|
| ≥ 5 similar incidents | 12 |
| 3–4 | 8 |
| 1–2 | 4 |
| 0 | 0 |
| `null` | 0, mark as unknown |

#### Factor 3: Blast Radius — Subscriptions (max 12 pts)

| Evidence Key | Source |
|---|---|
| `subscription_count` | **Service Tree evidence** (preferred) or EV2 evidence (fallback) |

| Threshold | Points |
|-----------|--------|
| ≥ 10 subscriptions | 12 |
| ≥ 5 | 8 |
| ≥ 2 | 5 |
| 1 | 2 |
| 0 | 0 |
| `null` | 0, mark as unknown |

#### Factor 4: Recent Outages — 180 days (max 10 pts)

| Evidence Key | Source |
|---|---|
| `historical_outages_180d` | IcM evidence |

| Threshold | Points |
|-----------|--------|
| ≥ 3 outages | 10 |
| 2 | 7 |
| 1 | 4 |
| 0 | 0 |
| `null` | 0, mark as unknown |

#### Factor 5: Slow Incident Mitigation — MTTM (max 10 pts)

| Evidence Key | Source |
|---|---|
| `avg_mttm_minutes` | IcM evidence |

| Threshold | Points |
|-----------|--------|
| ≥ 60 minutes | 10 |
| ≥ 30 | 7 |
| ≥ 15 | 4 |
| < 15 | 0 |
| `null` | 0, mark as unknown |

#### Factor 6: Deployment Frequency — 30 days (max 10 pts)

| Evidence Key | Source |
|---|---|
| `deployment_count_30d` | EV2 evidence |

| Threshold | Points |
|-----------|--------|
| ≥ 20 deployments | 10 |
| ≥ 10 | 5 |
| < 10 | 0 |
| `null` | 0, mark as unknown |

#### Factor 7: Destructive Operations (max 10 pts)

| Evidence Key | Source |
|---|---|
| `operations` | Caller-supplied |

| Condition | Points |
|-----------|--------|
| Any `delete` or `destroy` in operations list | 10 |
| Otherwise | 0 |
| No operations provided | 0, mark as N/A |

#### Factor 8: High-Severity Incidents — Sev1/2 (max 8 pts)

| Evidence Key | Source |
|---|---|
| `sev12_incident_count` | IcM evidence |

| Threshold | Points |
|-----------|--------|
| ≥ 5 Sev1/2 incidents | 8 |
| 3–4 | 5 |
| 1–2 | 3 |
| 0 | 0 |
| `null` | 0, mark as unknown |

#### Factor 9: Regional Blast Radius (max 8 pts)

| Evidence Key | Source |
|---|---|
| `region_count` | EV2 evidence |

| Threshold | Points |
|-----------|--------|
| ≥ 10 regions | 8 |
| ≥ 5 | 5 |
| ≥ 3 | 3 |
| < 3 | 0 |
| `null` | 0, mark as unknown |

#### Factor 10: Recent Active Outages — 7 days (max 5 pts)

| Evidence Key | Source |
|---|---|
| `recent_active_outages` | IcM evidence |

| Threshold | Points |
|-----------|--------|
| ≥ 1 active outage | 5 |
| 0 | 0 |
| `null` | 0, mark as unknown |

### Enrichment Factors (Advisory — Not Scored)

These appear in the report for awareness but do NOT add to the 100-point
score:

| Factor | Evidence Key | Source | Signal |
|--------|-------------|--------|--------|
| Pipeline health | `pipeline_failure_rate_30d` | ADO | >20% failure rate flagged as concern |
| Security posture | `active_security_alerts` | ADO | Any active alert flagged |
| Customer impact | `customer_impact_summary` | IcM | S500/ACE customers affected |
| Change velocity | `commit_count_30d` | ADO | >100 commits in 30d flagged as high churn |
| HVT classification | `is_hvt` | Service Tree | High Value Target — elevated caution warranted |
| TCB classification | `is_tcb` | Service Tree | Trusted Computing Base — security-sensitive |
| DHE violations | `dhe_violation_count` | Service Tree | Compliance concerns |

## Output Format

Produce the report in this exact markdown structure:

```markdown
# Risk Assessment: {service_name}

## Risk Summary

| Metric | Value |
|--------|-------|
| **Score** | {score}/100 |
| **Level** | {LOW/MEDIUM/HIGH} |
| **Environment** | {environment} |
| **Assessment Date** | {current date} |
| **HVT** | {Yes/No/Unknown} |
| **TCB** | {Yes/No/Unknown} |

## Scoring Factors

| # | Factor | Points | Max | Status | Evidence |
|---|--------|--------|-----|--------|----------|
| 1 | Deployment-caused outages (180d) | {pts} | 15 | {hit/miss/unknown} | {value or "N/A"} |
| 2 | Similar past incidents | {pts} | 12 | {hit/miss/unknown} | {value} |
| 3 | Blast radius — subscriptions | {pts} | 12 | {hit/miss/unknown} | {value} (source: {Service Tree/EV2}) |
| 4 | Recent outages (180d) | {pts} | 10 | {hit/miss/unknown} | {value} |
| 5 | Slow mitigation (MTTM) | {pts} | 10 | {hit/miss/unknown} | {value} |
| 6 | Deployment frequency (30d) | {pts} | 10 | {hit/miss/unknown} | {value} |
| 7 | Destructive operations | {pts} | 10 | {hit/miss/n-a} | {value} |
| 8 | High-severity incidents (Sev1/2) | {pts} | 8 | {hit/miss/unknown} | {value} |
| 9 | Regional blast radius | {pts} | 8 | {hit/miss/unknown} | {value} |
| 10 | Recent active outages (7d) | {pts} | 5 | {hit/miss/unknown} | {value} |
| | **Total** | **{score}** | **100** | | |

## Service Identity

| Field | Value |
|-------|-------|
| **Service Name** | {canonical name from Service Tree} |
| **Service ID** | {service ID} |
| **Organization** | {org} |
| **Division** | {division} |
| **Service Group** | {service group} |

{If service was not found in Service Tree, note: "Service not validated against Service Tree."}

## Evidence Summary

### Service Tree
{Service identity confirmed/not found, production subscription count,
HVT/TCB status, DHE violations}

### IcM Incidents
{Summarize incident findings: count, severities, MTTM, trends}

### Deployments (EV2)
{Summarize deployment findings: frequency, failures, regions}

### Repository Health (ADO)
{If available: pipeline status, security alerts, change velocity}
{If not available: "ADO evidence not available (repo not in connected org or not provided)"}

## Unknowns

{List any factors marked as unknown with explanation of why data was missing}

## Enrichment Signals

### Service Classification
- **HVT (High Value Target):** {Yes/No/Unknown} — {explanation}
- **TCB (Trusted Computing Base):** {Yes/No/Unknown} — {explanation}
- **DHE Violations:** {count} — {summary if any}

### Operations Context
{Customer impact, pipeline health, security alerts — advisory context}

## Recommendations

{Based on the risk level and top contributing factors:}

### If HIGH (67-100):
- Consider delaying deployment until {top factor} is addressed
- Ensure rollback plan is documented and tested
- Add additional monitoring for the deployment window
- Review similar past incidents for lessons learned
{If HVT: "⚠️ This is a **High Value Target** service — elevated review is strongly recommended."}

### If MEDIUM (34-66):
- Review the {top factors} before proceeding
- Ensure standard deployment safeguards are in place
- Monitor closely during and after deployment
{If HVT: "Note: This is an HVT service — consider additional safeguards."}

### If LOW (0-33):
- Standard deployment process is appropriate
- No elevated risk signals detected

## AI Incident Context

{If ai_incident_summary is available from IcM skill, include it here
as additional context. This is a narrative summary, not a scoring factor.}
```

## Scoring Procedure

1. **Resolve subscription_count:** Check Service Tree evidence first. If
   `service_tree_evidence.subscription_count` is not null, use it. Otherwise
   fall back to `ev2_evidence.subscription_count`. Note the source used.
2. For each factor (1–10), look up the evidence key in the provided evidence.
3. If the value is `null`, award 0 points and mark status as `unknown`.
4. If the value is present, apply the threshold table and award points.
5. Set status to `hit` if points > 0, `miss` if points = 0 (but evidence
   was present), `unknown` if evidence was null, `n-a` if not applicable.
6. Sum all points. Cap at 100.
7. Determine risk level: LOW (0-33), MEDIUM (34-66), HIGH (67-100).
8. Populate the Service Identity section from Service Tree evidence.
9. Populate HVT/TCB/DHE enrichment signals.
10. Generate the full markdown report.

## Critical Rules

- **Deterministic**: Same evidence → same score. No subjectivity in factor scoring.
- **Transparent**: Every factor shows its evidence value and threshold logic.
- **No guessing**: Missing evidence = 0 points + `unknown` status. Never infer values.
- **Enrichments are separate**: ADO, customer impact, HVT/TCB, and DHE data
  appear in the report but do not affect the numeric score.
- **Source attribution**: Factor 3 must note whether data came from Service Tree
  or EV2 in the evidence column.
