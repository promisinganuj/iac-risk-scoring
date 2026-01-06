"""terraform_plan_parser.py

Parses Terraform plan output (JSON) and extracts resource changes for risk scoring.
Also supports parsing a Terraform dependency graph exported as Graphviz DOT.
"""

import json
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set


_DOT_EDGE_RE = re.compile(r'^\s*"(?P<src>[^"]+)"\s*->\s*"(?P<dst>[^"]+)"\s*;')


def parse_terraform_graph(dot_path: str) -> Dict[str, Set[str]]:
    """Parse a Terraform dependency graph exported via `terraform graph`.

    Returns a map of resource address -> set of dependent addresses.
    For a DOT edge `A -> B`, we treat `B` as a dependency of `A`.
    """
    dep_map: Dict[str, Set[str]] = defaultdict(set)
    with open(dot_path, "r", encoding="utf-8") as f:
        for line in f:
            match = _DOT_EDGE_RE.match(line)
            if match:
                dep_map[match.group("src")].add(match.group("dst"))
    return dict(dep_map)

def parse_plan(plan_json: Dict[str, Any], dep_map: Optional[Dict[str, Set[str]]] = None) -> List[Dict[str, Any]]:
    """
    Extracts resource changes from Terraform plan JSON.
    Returns a list of dicts with resource_type, change_type, dependencies.
    If dep_map is provided, uses it to count dependencies for each resource.
    """
    changes = []
    for res in plan_json.get('resource_changes', []):
        resource_type = res.get('type', '')
        change_type = res.get('change', {}).get('actions', [''])[0]  # add/modify/delete
        address = res.get('address', '')
        dependencies = 0
        if dep_map and address in dep_map:
            dependencies = len(dep_map[address])
        elif 'depends_on' in res:
            dependencies = len(res.get('depends_on', []))
        changes.append({
            'resource_type': resource_type,
            'change_type': change_type,
            'dependencies': dependencies,
            'address': address
        })
    return changes

if __name__ == "__main__":
    import sys
    if len(sys.argv) not in (2, 3):
        print("Usage: python terraform_plan_parser.py <plan.json> [graph.dot]")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        plan = json.load(f)
    dep_map = None
    if len(sys.argv) == 3:
        dep_map = parse_terraform_graph(sys.argv[2])
    changes = parse_plan(plan, dep_map)
    print(json.dumps(changes, indent=2))
