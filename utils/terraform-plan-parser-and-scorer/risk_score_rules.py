"""
risk_score_rules.py

Defines the rule-based logic for risk scoring of Terraform plan changes.
"""

from typing import List, Dict, Any

# Example resource risk weights (can be expanded)
RESOURCE_TYPE_WEIGHTS = {
    # Azure resources from sample_plan.json
    'azurerm_resource_group': 2,
    'azurerm_virtual_network': 5,
    'azurerm_subnet': 4,
    'azurerm_storage_account': 7,
    'azurerm_private_endpoint': 8,
    'azurerm_private_dns_zone': 3,
    'azurerm_private_dns_zone_virtual_network_link': 4,
    'azurerm_private_dns_a_record': 3,
    # Example AWS resources (legacy/demo)
    'aws_db_instance': 8,
    'aws_subnet': 4,
    'aws_security_group': 7,
    'aws_s3_bucket': 5,
    # Add more as needed
}

CHANGE_TYPE_WEIGHTS = {
    'add': 2,
    'create': 2,
    'modify': 5,
    'update': 5,
    'delete': 9,
    'remove': 9
}

def score_resource_change(resource_type: str, change_type: str, dependencies: int = 0) -> int:
    """
    Assigns a risk score to a single resource change based on type, change, and dependencies.
    Lower risk for new (add/create) resources, higher for modify/delete.
    """
    base = RESOURCE_TYPE_WEIGHTS.get(resource_type, 3)
    ct = change_type.lower()
    change = CHANGE_TYPE_WEIGHTS.get(ct, 5)
    dep_factor = min(dependencies, 10)  # Cap dependency effect
    # New resources should not get high risk unless resource type is inherently risky
    if ct in ("add", "create"):
        score = max(1, min(base, 5) + change // 2 + dep_factor // 3)
    elif ct in ("delete", "remove"):
        score = min(10, base + change + dep_factor // 2)
    else:  # modify/update
        score = min(10, base + change + dep_factor // 2)
    return min(score, 10)


def aggregate_score(changes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Aggregates risk scores for all changes and provides formatted reasoning.
    """
    if not changes:
        return {"score": 1, "reasoning": "No changes detected."}
    scores = []
    reasons = []
    for c in changes:
        s = score_resource_change(
            c.get('resource_type', ''),
            c.get('change_type', ''),
            c.get('dependencies', 0)
        )
        scores.append(s)
        reasons.append(f"- {c.get('change_type','').capitalize():<8} {c.get('resource_type',''):<40} (deps: {c.get('dependencies',0)}) → {s}")
    final_score = min(10, max(scores) + len([x for x in scores if x > 5]) // 3)
    reasoning = (
        f"Highest individual risk: {max(scores)}\n"
        f"Resource changes and their risk scores:\n"
        + "\n".join(reasons)
    )
    return {
        "score": final_score,
        "reasoning": reasoning
    }
