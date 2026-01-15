from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Make sure `approach2-using-existing-graph` is importable when executed as a script.
THIS_FILE = Path(__file__).resolve()
APPROACH2_DIR = THIS_FILE.parents[1]
if str(APPROACH2_DIR) not in sys.path:
    sys.path.insert(0, str(APPROACH2_DIR))

from risk_scoring.engine import assess_resource_change
from risk_scoring.evidence_client import EvidenceClient
from risk_scoring.neo4j_http import Neo4jHttpConfig
from risk_scoring.neo4j_http_executor import Neo4jHttpExecutor
from risk_scoring.neo4j_http_repository import Neo4jHttpEntityRepository
from risk_scoring.models import ResourceSpec
from risk_scoring.scoring import ChangeContext


def _load_json_text(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _first_nonempty_str(values: List[Any]) -> Optional[str]:
    for v in values:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _extract_canonical_fields(doc: Dict[str, Any]) -> tuple[Optional[str], Optional[str], List[str]]:
    change_id = None
    if isinstance(doc.get("change_id"), str):
        change_id = doc.get("change_id")
    elif isinstance(doc.get("changeId"), str):
        change_id = doc.get("changeId")

    env = doc.get("environment")
    environment = env if isinstance(env, str) and env.strip() else None

    ops: List[str] = []
    raw_ops = doc.get("operations")
    if isinstance(raw_ops, list):
        for op in raw_ops:
            if not isinstance(op, dict):
                continue
            kind = op.get("operation")
            if isinstance(kind, str) and kind.strip():
                ops.append(kind)

    return change_id, environment, ops


def _extract_resource(doc: Dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    raw_ops = doc.get("operations")
    if not isinstance(raw_ops, list):
        return None, None

    resource_id_candidates: List[Any] = []
    resource_type_candidates: List[Any] = []

    for op in raw_ops:
        if not isinstance(op, dict):
            continue
        resource_id_candidates.append(op.get("resource_id"))
        resource_id_candidates.append(op.get("resourceId"))
        resource_type_candidates.append(op.get("resource_type"))
        resource_type_candidates.append(op.get("resourceType"))

    return _first_nonempty_str(resource_id_candidates), _first_nonempty_str(resource_type_candidates)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="VS Code entrypoint: canonical change -> deterministic risk report JSON (Approach 2)."
    )
    parser.add_argument(
        "--input",
        default="-",
        help="Canonical change JSON file path, or '-' for stdin",
    )
    parser.add_argument(
        "--resource-id",
        default=None,
        help="Optional override for resource_id (if canonical model is missing it)",
    )
    parser.add_argument(
        "--resource-type",
        default=None,
        help="Optional override for resource_type",
    )
    args = parser.parse_args(argv)

    try:
        text = _load_json_text(args.input)
        doc = json.loads(text)
        if not isinstance(doc, dict):
            raise ValueError("Input JSON must be an object.")

        change_id, environment, ops = _extract_canonical_fields(doc)
        resource_id, resource_type = _extract_resource(doc)

        if isinstance(args.resource_id, str) and args.resource_id.strip():
            resource_id = args.resource_id.strip()
        if isinstance(args.resource_type, str) and args.resource_type.strip():
            resource_type = args.resource_type.strip()

        if resource_id is None:
            raise ValueError(
                "Missing resource_id. Provide it in the canonical model operations, or pass --resource-id."
            )

        change = ChangeContext.create(environment=environment, operations=ops)
        resource = ResourceSpec(resource_id=resource_id, resource_type=resource_type)

        config = Neo4jHttpConfig.from_env()
        repo = Neo4jHttpEntityRepository(config)
        executor = Neo4jHttpExecutor(config)
        evidence_client = EvidenceClient(executor)

        result = assess_resource_change(
            repo=repo,
            evidence_client=evidence_client,
            resource=resource,
            change=change,
            report_id=change_id,
        )

        sys.stdout.write(result.report_json_string())
        sys.stdout.write("\n")
        return 0

    except Exception as e:
        sys.stderr.write(f"ERROR: {e}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
