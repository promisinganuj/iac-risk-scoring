from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from risk_scoring.graph_expansion import GraphExpansionResult, QueryRun
from risk_scoring.models import ResolvedEntityRef
from risk_scoring.scoring import ChangeContext, ScoreResult


REPORT_SCHEMA_VERSION = "risk_report.v1"


def _sorted_unique(values: Iterable[str]) -> Tuple[str, ...]:
    return tuple(sorted(set(values)))


def build_report_json(
    *,
    resolved: ResolvedEntityRef,
    change: ChangeContext,
    expansion: GraphExpansionResult,
    score: ScoreResult,
    report_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a deterministic JSON report payload.

    Notes on determinism:
    - No timestamps are generated here.
    - Ordering is either stable (lists) or rendered later with sort_keys.
    """

    unknowns = _sorted_unique(list(expansion.unknowns) + list(score.unknowns))

    evidence_queries: List[Dict[str, Any]] = []
    for q in expansion.queries:
        evidence_queries.append(
            {
                "query_id": q.query_id,
                "params": dict(q.params),
                "row_count": q.row_count,
                "sample_rows": list(q.sample_rows),
            }
        )

    payload: Dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "report_id": report_id,
        "resource": asdict(resolved),
        "change": {"environment": change.environment, "operations": list(change.operations)},
        "score": score.to_dict(),
        "evidence": dict(expansion.evidence),
        "evidence_queries": evidence_queries,
        "unknowns": list(unknowns),
    }

    # Ensure deterministic null handling (avoid missing keys for report_id).
    if report_id is None:
        payload["report_id"] = None

    return payload


def _json_block(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True)


def render_markdown_report(report: Mapping[str, Any], *, max_sample_rows: int = 5) -> str:
    """Render a stable Markdown report from the JSON payload."""

    schema_version = report.get("schema_version")
    score = report.get("score") or {}
    factors = score.get("factors") or []

    lines: List[str] = []
    lines.append("# IaC Risk Report")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- schema_version: {schema_version}")
    lines.append(f"- risk_model_version: {score.get('risk_model_version')}")
    lines.append(f"- risk_score: {score.get('risk_score')}")
    lines.append(f"- risk_level: {score.get('risk_level')}")

    resource = report.get("resource") or {}
    lines.append("")
    lines.append("## Resource")
    lines.append(f"- label: {resource.get('label')}")
    lines.append(f"- resource_id: {resource.get('resource_id')}")

    change = report.get("change") or {}
    lines.append("")
    lines.append("## Change")
    lines.append(f"- environment: {change.get('environment')}")
    ops = change.get("operations") or []
    lines.append(f"- operations: {', '.join(ops) if ops else '(none)'}")

    lines.append("")
    lines.append("## Factors")
    for f in factors:
        lines.append(f"### {f.get('factor_id')}: {f.get('title')}")
        lines.append(f"- status: {f.get('status')}")
        lines.append(f"- points: {f.get('points')} / {f.get('max_points')}")
        lines.append(f"- reason: {f.get('reason')}")
        lines.append("- evidence:")
        lines.append("```json")
        lines.append(_json_block(f.get("evidence") or {}))
        lines.append("```")
        lines.append("")

    evidence = report.get("evidence") or {}
    lines.append("## Evidence")
    lines.append("```json")
    lines.append(_json_block(evidence))
    lines.append("```")

    lines.append("")
    lines.append("## Evidence Queries")
    for q in report.get("evidence_queries") or []:
        lines.append(f"### {q.get('query_id')}")
        lines.append(f"- row_count: {q.get('row_count')}")
        lines.append("- params:")
        lines.append("```json")
        lines.append(_json_block(q.get("params") or {}))
        lines.append("```")
        sample_rows = list(q.get("sample_rows") or [])[:max_sample_rows]
        lines.append(f"- sample_rows (first {len(sample_rows)}):")
        lines.append("```json")
        lines.append(_json_block(sample_rows))
        lines.append("```")
        lines.append("")

    unknowns = report.get("unknowns") or []
    lines.append("## Unknowns")
    if unknowns:
        for u in unknowns:
            lines.append(f"- {u}")
    else:
        lines.append("- (none)")

    lines.append("")
    return "\n".join(lines)
