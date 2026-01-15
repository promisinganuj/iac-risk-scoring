from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Optional, Tuple

from risk_scoring.entity_resolution import resolve_azure_resource
from risk_scoring.evidence_client import EvidenceClient
from risk_scoring.graph_expansion import GraphExpansionResult, expand_evidence_for_resource
from risk_scoring.models import ResolvedEntityRef, ResourceSpec
from risk_scoring.reporting import build_report_json, render_markdown_report
from risk_scoring.repository import EntityRepository
from risk_scoring.scoring import ChangeContext, ScoreResult, score_change


@dataclass(frozen=True)
class EngineResult:
    resolved: ResolvedEntityRef
    expansion: GraphExpansionResult
    score: ScoreResult
    report_json: Dict[str, Any]
    report_markdown: str

    def report_json_string(self) -> str:
        # Stable, machine-friendly representation.
        return json.dumps(self.report_json, indent=2, sort_keys=True)


def assess_resource_change(
    *,
    repo: EntityRepository,
    evidence_client: EvidenceClient,
    resource: ResourceSpec,
    change: ChangeContext,
    as_of: Optional[date] = None,
    report_id: Optional[str] = None,
) -> EngineResult:
    """Deterministic end-to-end engine (Approach 2 MVP).

    Pipeline:
    1) Resolve ResourceSpec -> ResolvedEntityRef (deterministic; non-interactive)
    2) Expand graph evidence via allowlisted queries only
    3) Score deterministically from evidence (no DB queries here)
    4) Build JSON + Markdown reports (stable ordering)

    Notes:
    - This is an MVP front-door that accepts explicit resource identity.
    - Canonical diff -> canonical change model is handled by a separate feature.
    """

    resolved = resolve_azure_resource(repo, resource, non_interactive=True)
    expansion = expand_evidence_for_resource(resolved, evidence_client, as_of=as_of)

    score = score_change(change, expansion.evidence)

    report_json = build_report_json(
        resolved=resolved,
        change=change,
        expansion=expansion,
        score=score,
        report_id=report_id,
    )
    report_markdown = render_markdown_report(report_json)

    return EngineResult(
        resolved=resolved,
        expansion=expansion,
        score=score,
        report_json=report_json,
        report_markdown=report_markdown,
    )
