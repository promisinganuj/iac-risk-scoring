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
    ctx_params = {"resourceName": resolved.resource_id, "limit": limit_for("t2.resource_context")}
    ctx_rows = _stable_sort_rows(
        _coerce_rows(client.run("t2.resource_context", ctx_params)),
        keys=("resourceName",),
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


@dataclass(frozen=True)
class BlastRadiusResult:
    """Blast radius analysis showing how changes propagate through the hierarchy."""

    entity_id: str
    entity_type: str  # 'resource', 'template', or 'service'
    affected_services: int
    affected_resources: int
    affected_resource_groups: int
    affected_subscriptions: int
    incident_count: int
    deployment_count: int
    details: Dict[str, Any]
    queries: Tuple[QueryRun, ...]


def get_resource_blast_radius(
    resource_id: str,
    client: EvidenceClient,
    *,
    limit: int = 1,
) -> BlastRadiusResult:
    """Calculate blast radius for a resource change.

    Traversal path: Resource -> ResourceGroup -> Subscription -> Services -> Incidents

    Args:
        resource_id: The resourceName to analyze
        client: EvidenceClient for executing queries
        limit: Result limit (default 1, since we're analyzing a single resource)

    Returns:
        BlastRadiusResult with impact counts and detailed entity information
    """
    queries: List[QueryRun] = []

    params = {"resourceName": resource_id, "limit": limit}
    rows = _coerce_rows(client.run("blast_radius.resource_impact", params))

    queries.append(
        QueryRun(
            query_id="blast_radius.resource_impact",
            params=dict(params),
            row_count=len(rows),
            sample_rows=tuple(rows),
        )
    )

    if not rows:
        return BlastRadiusResult(
            entity_id=resource_id,
            entity_type="resource",
            affected_services=0,
            affected_resources=0,
            affected_resource_groups=0,
            affected_subscriptions=0,
            incident_count=0,
            deployment_count=0,
            details={},
            queries=tuple(queries),
        )

    row = rows[0]

    return BlastRadiusResult(
        entity_id=resource_id,
        entity_type="resource",
        affected_services=1 if row.get("serviceId") else 0,
        affected_resources=row.get("peerResourceCount", 0),
        affected_resource_groups=1 if row.get("resourceGroupKey") else 0,
        affected_subscriptions=1 if row.get("subscriptionId") else 0,
        incident_count=row.get("incidentCount", 0),
        deployment_count=0,  # Not directly tracked at resource level
        details={
            "resourceType": row.get("resourceType"),
            "resourceGroup": {
                "key": row.get("resourceGroupKey"),
                "name": row.get("resourceGroupName"),
            } if row.get("resourceGroupKey") else None,
            "subscription": row.get("subscriptionId"),
            "service": {
                "id": row.get("serviceId"),
                "name": row.get("serviceName"),
            } if row.get("serviceId") else None,
            "peerResources": row.get("peerResources", []),
            "recentIncidents": row.get("recentIncidents", []),
        },
        queries=tuple(queries),
    )


def get_template_blast_radius(
    template_name: str,
    client: EvidenceClient,
    *,
    limit: int = 1,
) -> BlastRadiusResult:
    """Calculate blast radius for a template change.

    Traversal path: Template -> Deployments -> ResourceGroups -> Resources

    Args:
        template_name: The template name to analyze
        client: EvidenceClient for executing queries
        limit: Result limit (default 1, since we're analyzing a single template)

    Returns:
        BlastRadiusResult with impact counts and detailed entity information
    """
    queries: List[QueryRun] = []

    params = {"templateName": template_name, "limit": limit}
    rows = _coerce_rows(client.run("blast_radius.template_impact", params))

    queries.append(
        QueryRun(
            query_id="blast_radius.template_impact",
            params=dict(params),
            row_count=len(rows),
            sample_rows=tuple(rows),
        )
    )

    if not rows:
        return BlastRadiusResult(
            entity_id=template_name,
            entity_type="template",
            affected_services=0,
            affected_resources=0,
            affected_resource_groups=0,
            affected_subscriptions=0,
            incident_count=0,
            deployment_count=0,
            details={},
            queries=tuple(queries),
        )

    row = rows[0]

    return BlastRadiusResult(
        entity_id=template_name,
        entity_type="template",
        affected_services=0,  # Services are indirectly affected via deployments
        affected_resources=row.get("resourceCount", 0),
        affected_resource_groups=row.get("resourceGroupCount", 0),
        affected_subscriptions=0,  # Not tracked at template level in this query
        incident_count=0,  # Would need to traverse to services for this
        deployment_count=row.get("deploymentCount", 0),
        details={
            "templateVersion": row.get("templateVersion"),
            "deployments": row.get("deployments", []),
            "resourceGroups": row.get("resourceGroups", []),
            "resources": row.get("resources", []),
        },
        queries=tuple(queries),
    )


def get_service_blast_radius(
    service_id: str,
    client: EvidenceClient,
    *,
    limit: int = 1,
) -> BlastRadiusResult:
    """Calculate blast radius for a service change.

    Traversal path: Service -> Resources -> ResourceGroups/Subscriptions -> Incidents

    Args:
        service_id: The serviceId to analyze
        client: EvidenceClient for executing queries
        limit: Result limit (default 1, since we're analyzing a single service)

    Returns:
        BlastRadiusResult with impact counts and detailed entity information
    """
    queries: List[QueryRun] = []

    params = {"serviceId": service_id, "limit": limit}
    rows = _coerce_rows(client.run("blast_radius.service_impact", params))

    queries.append(
        QueryRun(
            query_id="blast_radius.service_impact",
            params=dict(params),
            row_count=len(rows),
            sample_rows=tuple(rows),
        )
    )

    if not rows:
        return BlastRadiusResult(
            entity_id=service_id,
            entity_type="service",
            affected_services=0,
            affected_resources=0,
            affected_resource_groups=0,
            affected_subscriptions=0,
            incident_count=0,
            deployment_count=0,
            details={},
            queries=tuple(queries),
        )

    row = rows[0]

    return BlastRadiusResult(
        entity_id=service_id,
        entity_type="service",
        affected_services=1,  # The service itself
        affected_resources=row.get("resourceCount", 0),
        affected_resource_groups=row.get("resourceGroupCount", 0),
        affected_subscriptions=row.get("subscriptionCount", 0),
        incident_count=row.get("incidentCount", 0),
        deployment_count=row.get("deploymentCount", 0),
        details={
            "serviceName": row.get("serviceName"),
            "resources": row.get("resources", []),
            "resourceGroups": row.get("resourceGroups", []),
            "subscriptions": row.get("subscriptions", []),
            "incidents": row.get("incidents", []),
        },
        queries=tuple(queries),
    )
