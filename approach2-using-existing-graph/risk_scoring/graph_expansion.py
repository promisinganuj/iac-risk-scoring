from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from risk_scoring.evidence_client import EvidenceClient
from risk_scoring.models import ResolvedEntityRef


@dataclass(frozen=True)
class QueryRun:
    query_id: str
    params: Dict[str, Any]
    row_count: int
    sample_rows: Tuple[Dict[str, Any], ...]


@dataclass(frozen=True)
class GraphExpansionResult:
    """Deterministic, bounded evidence derived from allowlisted Neo4j queries."""

    evidence: Dict[str, Any]
    queries: Tuple[QueryRun, ...]
    unknowns: Tuple[str, ...]


def _coerce_rows(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    rows: List[Dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            rows.append(dict(item))
    return rows


def _parse_iso_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    v = value.strip()
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        return None


def _stable_sort_rows(rows: List[Dict[str, Any]], *, keys: Sequence[str], reverse: bool = False) -> List[Dict[str, Any]]:
    """Return a stably-sorted copy of rows using selected keys.

    This is a defense-in-depth determinism guard. Allowlisted queries already
    include ORDER BY, but this keeps report output stable even if an executor
    or backend returns rows in a different order.
    """

    def norm(v: Any) -> Any:
        if v is None:
            return ""
        if isinstance(v, (str, int, float, bool)):
            return v
        return str(v)

    return sorted(rows, key=lambda r: tuple(norm(r.get(k)) for k in keys), reverse=reverse)


def expand_evidence_for_resource(
    resolved: ResolvedEntityRef,
    client: EvidenceClient,
    *,
    as_of: Optional[date] = None,
    limits: Optional[Mapping[str, int]] = None,
) -> GraphExpansionResult:
    """Expand graph context for a resolved Azure resource.

    Constraints:
    - Uses only allowlisted/bounded queries via EvidenceClient.
    - Deterministic ordering: preserves query ordering and sorts unknown fields.

    Args:
        as_of: Optional explicit reference date for time-window metrics.
              If omitted, time-window metrics are marked unknown.
        limits: Optional per-query limit overrides by query_id.
    """

    unknowns: List[str] = []
    queries: List[QueryRun] = []
    lims: Dict[str, int] = dict(limits or {})

    def limit_for(query_id: str) -> int:
        return lims.get(query_id, 20)

    # Resource context (service ownership, subscription, RG)
    ctx_params = {"resourceId": resolved.resource_id, "limit": limit_for("t2.resource_context")}
    ctx_rows = _stable_sort_rows(
        _coerce_rows(client.run("t2.resource_context", ctx_params)),
        keys=("resourceId",),
        reverse=False,
    )
    queries.append(
        QueryRun(
            query_id="t2.resource_context",
            params=dict(ctx_params),
            row_count=len(ctx_rows),
            sample_rows=tuple(ctx_rows[:10]),
        )
    )

    if not isinstance(ctx_rows, list) or len(ctx_rows) == 0:
        # This should be rare given we already resolved the entity, but keep it explicit.
        unknowns.extend(
            [
                "service_id",
                "service_name",
                "subscription_id",
                "resource_group_key",
                "resource_group_name",
                "resource_type",
            ]
        )
        return GraphExpansionResult(
            evidence={
                "resource_id": resolved.resource_id,
                "services_impacted": 0,
                "critical_services": None,
                "historical_outages_180d": None,
                "open_icms": None,
                "deployment_count_30d": None,
            },
            queries=tuple(queries),
            unknowns=tuple(sorted(set(unknowns))),
        )

    ctx = ctx_rows[0]
    service_id = ctx.get("serviceId")
    service_name = ctx.get("serviceName")

    evidence: Dict[str, Any] = {
        "resource_id": resolved.resource_id,
        "resource_type": ctx.get("resourceType"),
        "subscription_id": ctx.get("subscriptionId"),
        "resource_group_key": ctx.get("resourceGroupKey"),
        "resource_group_name": ctx.get("resourceGroupName"),
        "service_id": service_id,
        "service_name": service_name,
    }

    services_impacted = 1 if isinstance(service_id, str) and service_id.strip() else 0
    evidence["services_impacted"] = services_impacted

    # We don't currently have a deterministic "critical" field in the sample graph.
    evidence["critical_services"] = None
    unknowns.append("critical_services")

    # Incidents (used as outage history in this sample graph)
    if services_impacted == 0:
        evidence["historical_outages_180d"] = None
        unknowns.append("historical_outages_180d")
        evidence["open_icms"] = None
        unknowns.append("open_icms")
        evidence["recent_incidents"] = []
    else:
        inc_params = {"serviceId": service_id, "limit": limit_for("t3.service_incidents")}
        inc_rows = _stable_sort_rows(
            _coerce_rows(client.run("t3.service_incidents", inc_params)),
            keys=("createdDate", "incidentId"),
            reverse=True,
        )
        queries.append(
            QueryRun(
                query_id="t3.service_incidents",
                params=dict(inc_params),
                row_count=len(inc_rows),
                sample_rows=tuple(inc_rows[:10]),
            )
        )

        evidence["recent_incidents"] = inc_rows

        if as_of is None:
            evidence["historical_outages_180d"] = None
            unknowns.append("historical_outages_180d")
        else:
            cutoff = as_of - timedelta(days=180)
            parsed_dates: List[Optional[date]] = [
                _parse_iso_date(r.get("createdDate")) for r in inc_rows
            ]
            if any(d is None for d in parsed_dates):
                # Explicitly mark unknown rather than guessing.
                evidence["historical_outages_180d"] = None
                unknowns.append("historical_outages_180d")
                unknowns.append("incident.createdDate")
            else:
                evidence["historical_outages_180d"] = sum(
                    1 for d in parsed_dates if d is not None and d >= cutoff
                )

        # The sample graph does not include a reliable open/closed status.
        evidence["open_icms"] = None
        unknowns.append("open_icms")

    # Deployments (no timestamp in sample data; provide sampled list and mark 30d as unknown)
    if services_impacted == 0:
        evidence["deployment_count_30d"] = None
        unknowns.append("deployment_count_30d")
        evidence["recent_deployments"] = []
    else:
        dep_params = {"serviceId": service_id, "limit": limit_for("t4.service_deployments")}
        dep_rows = _stable_sort_rows(
            _coerce_rows(client.run("t4.service_deployments", dep_params)),
            keys=("rolloutId",),
            reverse=True,
        )
        queries.append(
            QueryRun(
                query_id="t4.service_deployments",
                params=dict(dep_params),
                row_count=len(dep_rows),
                sample_rows=tuple(dep_rows[:10]),
            )
        )
        evidence["recent_deployments"] = dep_rows
        evidence["deployment_count_30d"] = None
        unknowns.append("deployment_count_30d")

    return GraphExpansionResult(
        evidence=evidence,
        queries=tuple(queries),
        unknowns=tuple(sorted(set(unknowns))),
    )
