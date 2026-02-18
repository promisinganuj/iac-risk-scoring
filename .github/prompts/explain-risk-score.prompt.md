---
mode: agent
description: Deep-dive into why a resource has a specific risk score
tools: ['risk-scoring/*', 'neo4j-database/*']
---
# Explain Risk Score

Provide a detailed explanation of the risk score for a resource, including the evidence behind each factor.

## Resource

- **Resource ID**: {{resource_id}}
- **Environment**: {{environment}}

## Instructions

1. Run `mcp_risk_scoring_assess_resource` to get the full risk report
2. For each factor with status "hit" (contributing points):
   - Explain **what evidence** triggered it
   - Show the **specific threshold** that was crossed
   - Suggest what would **reduce** this factor's score
3. For each factor with status "unknown":
   - Explain what data is missing
   - Estimate the **worst-case impact** if the data were available
4. Calculate the **confidence level** = (known factors / total factors) × 100%
5. Provide a plain-language summary suitable for a non-technical stakeholder

## Output Format

### Score Breakdown: {risk_score}/100 ({risk_level})

**Confidence**: {confidence}% ({known_count}/13 factors had data)

### Contributing Factors (hits)

For each hit factor:
- **Factor**: {title}
- **Points**: {points}/{max_points}
- **Evidence**: {what data triggered this}
- **Threshold**: {threshold that was crossed}
- **To reduce**: {what would lower this score}

### Missing Data (unknowns)

For each unknown:
- **Factor**: {title}
- **Max possible**: {max_points} additional points
- **Data needed**: {what evidence is missing}

### Plain-Language Summary

{2-3 sentence summary for non-technical readers}
