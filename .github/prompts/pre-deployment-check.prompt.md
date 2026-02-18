---
mode: agent
description: Pre-deployment risk check with go/no-go recommendation
tools: ['risk-scoring/*']
---
# Pre-Deployment Risk Check

Perform a pre-deployment risk check and provide a clear go/no-go recommendation.

## Deployment Details

- **Resource ID**: {{resource_id}}
- **Environment**: {{environment}}
- **Change Type**: {{change_type}}
- **Deployment Window**: {{deployment_window}}

## Instructions

1. Run `mcp_risk_scoring_assess_resource` with the resource and environment
2. Evaluate the risk score against these deployment gates:
   - **Score ≤ 33 (LOW)**: ✅ GO — Deploy normally
   - **Score 34–66 (MEDIUM)**: ⚠️ CONDITIONAL GO — Deploy with precautions
   - **Score ≥ 67 (HIGH)**: ⛔ NO-GO — Needs approval and planning
3. Generate a deployment checklist based on the risk level
4. If destructive operations are involved (delete/destroy), flag explicitly regardless of score

## Output Format

## 🚦 Deployment Decision: {GO / CONDITIONAL GO / NO-GO}

**Risk Score**: {score}/100 ({level})

### Pre-Deployment Checklist

- [ ] {Checklist items based on risk level and contributing factors}
- [ ] Rollback plan documented
- [ ] Monitoring dashboards ready
- [ ] On-call team notified (if MEDIUM or HIGH)
- [ ] Change approval obtained (if HIGH)

### Risk Factors Requiring Attention

{List only "hit" factors with actionable context}

### Recommended Deployment Approach

{Specific guidance: canary, blue-green, maintenance window, etc.}
