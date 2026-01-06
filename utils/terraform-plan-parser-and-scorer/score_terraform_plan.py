"""
score_terraform_plan.py

Script to score a Terraform plan using rule-based logic and print the result.
"""

import json
import sys
from terraform_plan_parser import parse_plan, parse_terraform_graph
from risk_score_rules import aggregate_score


def main():
    if len(sys.argv) not in (2, 3):
        print("Usage: python score_terraform_plan.py <plan.json> [graph.dot]")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        plan = json.load(f)
    dep_map = None
    if len(sys.argv) == 3:
        dep_map = parse_terraform_graph(sys.argv[2])
    changes = parse_plan(plan, dep_map)
    result = aggregate_score(changes)
    print(f"Risk Score: {result['score']}/10\nReasoning: {result['reasoning']}")

if __name__ == "__main__":
    main()
