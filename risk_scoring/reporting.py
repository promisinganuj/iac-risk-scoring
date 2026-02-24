from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union

from risk_scoring.evidence_provider import EvidenceExpansionResult
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
    expansion: Union[GraphExpansionResult, EvidenceExpansionResult],
    score: ScoreResult,
    report_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a deterministic JSON report payload.

    Notes on determinism:
    - No timestamps are generated here.
    - Ordering is either stable (lists) or rendered later with sort_keys.
    """

    unknowns = _sorted_unique(list(expansion.unknowns) + list(score.unknowns))

    # EvidenceExpansionResult uses 'all_queries'; GraphExpansionResult uses 'queries'.
    queries = getattr(expansion, "all_queries", None) or getattr(expansion, "queries", ())

    evidence_queries: List[Dict[str, Any]] = []
    for q in queries:
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
    """Render a stable Markdown report from the JSON payload optimized for agents."""

    schema_version = report.get("schema_version")
    score = report.get("score") or {}
    factors = score.get("factors") or []
    risk_score = score.get("risk_score", 0)
    risk_level = score.get("risk_level", "UNKNOWN")

    lines: List[str] = []
    lines.append("# Risk Assessment Report")
    lines.append("")
    
    # Prominent risk summary for agents
    lines.append("## 🎯 Risk Summary")
    lines.append("")
    lines.append(f"**Risk Score**: {risk_score}/100")
    lines.append(f"**Risk Level**: {risk_level}")
    lines.append(f"**Verdict**: {_get_verdict(risk_level, risk_score)}")
    lines.append("")
    lines.append(f"*Schema Version*: {schema_version}")
    lines.append(f"*Risk Model*: {score.get('risk_model_version')}")
    lines.append("")

    # Resource information
    resource = report.get("resource") or {}
    change = report.get("change") or {}
    lines.append("## 📋 Resource Information")
    lines.append("")
    lines.append(f"- **Resource ID**: `{resource.get('resource_id')}`")
    lines.append(f"- **Type**: {resource.get('label')}")
    lines.append(f"- **Environment**: {change.get('environment')}")
    ops = change.get("operations") or []
    lines.append(f"- **Operations**: {', '.join(ops) if ops else 'None'}")
    lines.append("")

    # Risk factors in table format
    lines.append("## ⚠️ Risk Factors")
    lines.append("")
    lines.append("| Factor | Status | Points | Impact | Raw Value |")
    lines.append("|--------|--------|--------|--------|-----------|")
    for f in factors:
        status_emoji = _get_status_emoji(f.get('status'))
        factor_name = f.get('title', 'Unknown')
        status = f.get('status', 'unknown')
        points = f"{f.get('points', 0)}/{f.get('max_points', 0)}"
        impact = _get_impact_level(f.get('points', 0), f.get('max_points', 1))
        raw_value = _format_raw_value(f.get('evidence') or {})
        lines.append(f"| {status_emoji} {factor_name} | {status} | {points} | {impact} | {raw_value} |")
    lines.append("")
    
    # Detailed factor explanations
    lines.append("### Factor Details")
    lines.append("")
    for f in factors:
        status_emoji = _get_status_emoji(f.get('status'))
        lines.append(f"**{status_emoji} {f.get('factor_id')}: {f.get('title')}**")
        lines.append("")
        lines.append(f"- **Status**: {f.get('status')}")
        lines.append(f"- **Points**: {f.get('points')} / {f.get('max_points')}")
        lines.append(f"- **Reason**: {f.get('reason')}")
        lines.append("")
        evidence_val = f.get("evidence") or {}
        if evidence_val:
            lines.append("Evidence:")
            lines.append("```json")
            lines.append(_json_block(evidence_val))
            lines.append("```")
            lines.append("")

    # Recommendations based on risk level and factors
    lines.append("## 💡 Recommendations")
    lines.append("")
    recommendations = _generate_recommendations(risk_level, risk_score, factors, report.get("unknowns") or [])
    for rec in recommendations:
        lines.append(f"- {rec}")
    lines.append("")

    # Supporting evidence summary
    evidence = report.get("evidence") or {}
    lines.append("## 📊 Supporting Evidence")
    lines.append("")
    lines.append("```json")
    lines.append(_json_block(evidence))
    lines.append("```")

    lines.append("")
    lines.append("## 🔍 Evidence Queries")
    lines.append("")
    for q in report.get("evidence_queries") or []:
        lines.append(f"### {q.get('query_id')}")
        lines.append(f"- **Rows returned**: {q.get('row_count')}")
        lines.append("- **Parameters**:")
        lines.append("```json")
        lines.append(_json_block(q.get("params") or {}))
        lines.append("```")
        sample_rows = list(q.get("sample_rows") or [])[:max_sample_rows]
        if sample_rows:
            lines.append(f"- **Sample rows** (first {len(sample_rows)}):")
            lines.append("```json")
            lines.append(_json_block(sample_rows))
            lines.append("```")
        lines.append("")

    unknowns = report.get("unknowns") or []
    lines.append("## ❓ Unknowns")
    lines.append("")
    if unknowns:
        lines.append("The following data points were not available for this assessment:")
        lines.append("")
        for u in unknowns:
            lines.append(f"- {u}")
    else:
        lines.append("*All required data points were available.*")

    lines.append("")
    return "\n".join(lines)


def _get_verdict(risk_level: str, risk_score: int) -> str:
    """Generate a verdict based on risk level."""
    if risk_level == "HIGH":
        return "⛔ High risk - Review carefully before proceeding"
    elif risk_level == "MEDIUM":
        return "⚠️ Moderate risk - Proceed with caution"
    elif risk_level == "LOW":
        return "✅ Low risk - Safe to proceed"
    else:
        return "❓ Unable to assess risk"


def _get_status_emoji(status: str) -> str:
    """Get emoji for factor status."""
    status_map = {
        "hit": "🔴",
        "miss": "🟢",
        "unknown": "❓",
        "na": "⚪"
    }
    return status_map.get(status, "❓")


def _get_impact_level(points: int, max_points: int) -> str:
    """Determine impact level from points."""
    if max_points == 0:
        return "None"
    ratio = points / max_points
    if ratio >= 0.7:
        return "High"
    elif ratio >= 0.4:
        return "Medium"
    elif ratio > 0:
        return "Low"
    else:
        return "None"



def _format_raw_value(evidence: dict) -> str:
    """Format the raw evidence values for display in the Risk Factors table.

    Each factor's evidence dict typically has one key-value pair (the evidence
    key and its raw value).  For operations it may be a list.
    """
    if not evidence:
        return "—"
    parts = []
    for key, val in evidence.items():
        if val is None:
            parts.append(f"{key}: —")
        elif isinstance(val, list):
            parts.append(f"{key}: {', '.join(str(v) for v in val) if val else '[]'}")
        else:
            parts.append(f"{key}: {val}")
    return "; ".join(parts)


def _generate_recommendations(risk_level: str, risk_score: int, factors: List[Dict[str, Any]], unknowns: List[str]) -> List[str]:
    """Generate actionable recommendations based on risk assessment."""
    recommendations = []
    
    # Risk level specific recommendations
    if risk_level == "HIGH":
        recommendations.append("**Immediate attention required**: This change carries high risk")
        recommendations.append("Consider implementing this change during a maintenance window")
        recommendations.append("Ensure rollback procedures are tested and ready")
        recommendations.append("Notify stakeholders and on-call teams before deployment")
    elif risk_level == "MEDIUM":
        recommendations.append("**Review recommended**: This change has moderate risk")
        recommendations.append("Verify recent deployment history before proceeding")
        recommendations.append("Have rollback plan ready")
    else:
        recommendations.append("This change appears safe to proceed")
        recommendations.append("Follow standard deployment procedures")
    
    # Factor-specific recommendations
    for f in factors:
        factor_id = f.get('factor_id', '')
        status = f.get('status')
        points = f.get('points', 0)
        
        if status == 'hit' and points > 0:
            if 'blast_radius' in factor_id:
                recommendations.append("Multiple services affected - Coordinate with service owners")
            elif 'outages' in factor_id:
                recommendations.append("Recent outages detected - Review incident history")
            elif 'icms' in factor_id:
                recommendations.append("Open incidents exist - Check for related issues")
    
    # Unknowns recommendations
    if unknowns:
        recommendations.append(f"⚠️ Missing {len(unknowns)} data point(s) - Risk assessment may be incomplete")
        recommendations.append("Consider gathering missing data before high-risk deployments")
    
    return recommendations
