---
mode: agent
description: Assess risk for a specific Azure resource in a given environment
tools: ['risk-scoring/*']
---
# Assess Resource Risk

Assess the operational risk for the following Azure resource change.

## Resource Details

- **Resource ID**: {{resource_id}}
- **Environment**: {{environment}}

## Instructions

1. Call the `mcp_risk_scoring_assess_resource` tool with the resource ID and environment above
2. Parse the JSON response and present a clear risk report
3. Highlight the top contributing risk factors (status = "hit")
4. Call out any unknowns that could affect the score
5. Provide actionable recommendations based on the risk level (LOW/MEDIUM/HIGH)

Format the output as a structured markdown report with:
- Risk Summary (score, level, verdict)
- Risk Factors table
- Key evidence highlights
- Unknowns section
- Recommendations
