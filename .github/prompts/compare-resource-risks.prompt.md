---
mode: agent
description: Compare risk scores across multiple resources or environments
tools: ['risk-scoring/*']
---
# Compare Resource Risks

Compare the operational risk across these resources or environments to help prioritize deployment order.

## Resources to Compare

{{resources_and_environments}}

## Instructions

1. Run `mcp_risk_scoring_assess_resource` for each resource/environment combination listed above
2. Collect all risk scores and factor breakdowns
3. Present a **comparison table** showing:
   - Resource ID, Environment, Risk Score, Risk Level, Top Factor
4. Rank resources from highest to lowest risk
5. Recommend a **deployment order** (lowest risk first)
6. Highlight any shared risk patterns across resources (e.g., all have recent outages)

## Output Format

### Comparison Summary

| Resource | Env | Score | Level | Top Factor |
|----------|-----|-------|-------|------------|
| ... | ... | ... | ... | ... |

### Recommended Deployment Order

1. (lowest risk first)
2. ...

### Shared Risk Patterns

- Any factors contributing across multiple resources
