from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional


class EvidenceError(RuntimeError):
    pass


class UnknownQueryError(EvidenceError):
    pass


class ParameterValidationError(EvidenceError):
    pass


@dataclass(frozen=True)
class ParamSpec:
    name: str
    kind: str  # 'str' | 'int' | 'bool'
    required: bool = True
    max_len: int = 512
    min_value: Optional[int] = None
    max_value: Optional[int] = None


@dataclass(frozen=True)
class QuerySpec:
    query_id: str
    cypher: str
    params: tuple[ParamSpec, ...]
    max_limit: int = 50
    default_limit: int = 25


def _validate_param(spec: ParamSpec, value: Any) -> Any:
    if value is None:
        if spec.required:
            raise ParameterValidationError(f"Missing required param: {spec.name}")
        return None

    if spec.kind == "str":
        if not isinstance(value, str):
            raise ParameterValidationError(f"Param {spec.name} must be a string")
        v = value.strip()
        if spec.required and v == "":
            raise ParameterValidationError(f"Param {spec.name} must be non-empty")
        if len(v) > spec.max_len:
            raise ParameterValidationError(
                f"Param {spec.name} exceeds max_len={spec.max_len}"
            )
        return v

    if spec.kind == "int":
        if not isinstance(value, int):
            raise ParameterValidationError(f"Param {spec.name} must be an int")
        if spec.min_value is not None and value < spec.min_value:
            raise ParameterValidationError(
                f"Param {spec.name} must be >= {spec.min_value}"
            )
        if spec.max_value is not None and value > spec.max_value:
            raise ParameterValidationError(
                f"Param {spec.name} must be <= {spec.max_value}"
            )
        return value

    if spec.kind == "bool":
        if not isinstance(value, bool):
            raise ParameterValidationError(f"Param {spec.name} must be a bool")
        return value

    raise ParameterValidationError(f"Unknown param kind for {spec.name}: {spec.kind}")


def validate_params(query: QuerySpec, params: Mapping[str, Any]) -> Dict[str, Any]:
    validated: Dict[str, Any] = {}
    for spec in query.params:
        validated[spec.name] = _validate_param(spec, params.get(spec.name))

    # Enforce limit bounds
    limit = params.get("limit")
    if limit is None:
        limit = query.default_limit

    if not isinstance(limit, int):
        raise ParameterValidationError("Param limit must be an int")

    if limit <= 0:
        raise ParameterValidationError("Param limit must be > 0")

    if limit > query.max_limit:
        raise ParameterValidationError(
            f"Param limit exceeds max_limit={query.max_limit} for query {query.query_id}"
        )

    validated["limit"] = limit

    return validated


# --- Allowlisted queries ---
# IMPORTANT: All queries must be read-only (MATCH/RETURN) and bounded with LIMIT.

ALLOWLIST: Dict[str, QuerySpec] = {
    "t1.resolve_azure_resource": QuerySpec(
        query_id="t1.resolve_azure_resource",
        cypher=(
            "MATCH (r:AzureResource {resourceName: $resourceName})\n"
            "RETURN r.resourceName AS resourceName, r.displayName AS displayName, r.resourceType AS resourceType, "
            "       r.location AS location\n"
            "ORDER BY r.resourceName\n"
            "LIMIT $limit"
        ),
        params=(ParamSpec("resourceName", "str", required=True, max_len=256),),
        max_limit=5,
        default_limit=1,
    ),
    "t2.resource_context": QuerySpec(
        query_id="t2.resource_context",
        cypher=(
            "MATCH (r:AzureResource {resourceName: $resourceName})\n"
            "OPTIONAL MATCH (r)<-[:OWNS_RESOURCE]-(s:Service)\n"
            "OPTIONAL MATCH (r)-[:IN_RESOURCE_GROUP]->(g:ResourceGroup)\n"
            "OPTIONAL MATCH (r)-[:IN_SUBSCRIPTION]->(sub:Subscription)\n"
            "RETURN r.resourceName AS resourceName, r.resourceType AS resourceType, "
            "       s.serviceId AS serviceId, s.name AS serviceName, "
            "       g.key AS resourceGroupKey, g.name AS resourceGroupName, "
            "       sub.subscriptionId AS subscriptionId\n"
            "ORDER BY r.resourceName\n"
            "LIMIT $limit"
        ),
        params=(ParamSpec("resourceName", "str", required=True, max_len=256),),
        max_limit=25,
        default_limit=5,
    ),
    "t3.service_incidents": QuerySpec(
        query_id="t3.service_incidents",
        cypher=(
            "MATCH (s:Service {serviceId: $serviceId})<-[:AFFECTS_SERVICE]-(i:Incident)\n"
            "RETURN i.incidentId AS incidentId, i.createdDate AS createdDate, i.severity AS severity, "
            "       i.changeRelated AS changeRelated, i.title AS title\n"
            "ORDER BY i.createdDate DESC, i.incidentId DESC\n"
            "LIMIT $limit"
        ),
        params=(ParamSpec("serviceId", "str", required=True, max_len=128),),
        max_limit=50,
        default_limit=20,
    ),
    "t4.service_deployments": QuerySpec(
        query_id="t4.service_deployments",
        cypher=(
            "MATCH (d:Deployment)-[:FOR_SERVICE]->(s:Service {serviceId: $serviceId})\n"
            "OPTIONAL MATCH (d)-[:TARGETS_RESOURCE_GROUP]->(g:ResourceGroup)\n"
            "RETURN d.rolloutId AS rolloutId, d.rolloutInfra AS rolloutInfra, d.artifactVersion AS artifactVersion, "
            "       g.key AS resourceGroupKey, g.name AS resourceGroupName\n"
            "ORDER BY d.rolloutId DESC\n"
            "LIMIT $limit"
        ),
        params=(ParamSpec("serviceId", "str", required=True, max_len=128),),
        max_limit=50,
        default_limit=20,
    ),
    "t5.resource_blast_radius": QuerySpec(
        query_id="t5.resource_blast_radius",
        cypher=(
            "MATCH (r:AzureResource {resourceName: $resourceName})\n"
            "OPTIONAL MATCH (r)-[:IN_RESOURCE_GROUP]->(rg:ResourceGroup)<-[:IN_RESOURCE_GROUP]-(peer:AzureResource)\n"
            "WHERE peer.resourceName <> r.resourceName\n"
            "OPTIONAL MATCH (r)<-[:OWNS_RESOURCE]-(s:Service)<-[:AFFECTS_SERVICE]-(i:Incident)\n"
            "WITH r, collect(DISTINCT peer.resourceName) AS peerResources, count(DISTINCT i) AS incidentCount\n"
            "RETURN r.resourceName AS resourceName, peerResources, incidentCount\n"
            "ORDER BY r.resourceName\n"
            "LIMIT $limit"
        ),
        params=(ParamSpec("resourceName", "str", required=True, max_len=256),),
        max_limit=25,
        default_limit=5,
    ),
    "t6.deployment_stage_failures": QuerySpec(
        query_id="t6.deployment_stage_failures",
        cypher=(
            "MATCH (d:Deployment)-[:FOR_SERVICE]->(s:Service {serviceId: $serviceId})\n"
            "MATCH (d)-[:HAS_STAGE]->(st:DeploymentStage)\n"
            "WHERE st.status = 'failed'\n"
            "RETURN d.rolloutId AS rolloutId, st.name AS stageName, st.status AS status, "
            "       st.order AS stageOrder, st.startTime AS startTime, st.endTime AS endTime\n"
            "ORDER BY d.rolloutId DESC, st.order ASC\n"
            "LIMIT $limit"
        ),
        params=(ParamSpec("serviceId", "str", required=True, max_len=128),),
        max_limit=50,
        default_limit=20,
    ),
    "t7.artifact_dependencies": QuerySpec(
        query_id="t7.artifact_dependencies",
        cypher=(
            "MATCH (s:Service {serviceId: $serviceId})-[:HAS_REPO]->(r:Repo)-[:PRODUCES_ARTIFACT]->(a:Artifact)\n"
            "OPTIONAL MATCH (a)-[:DEPENDS_ON*1..3]->(dep:Artifact)\n"
            "WITH a, collect(DISTINCT dep.name) AS dependencies\n"
            "RETURN a.name AS artifactName, a.type AS artifactType, dependencies\n"
            "ORDER BY a.name\n"
            "LIMIT $limit"
        ),
        params=(ParamSpec("serviceId", "str", required=True, max_len=128),),
        max_limit=50,
        default_limit=20,
    ),
    "t8.incident_mttm": QuerySpec(
        query_id="t8.incident_mttm",
        cypher=(
            "MATCH (i:Incident)-[:AFFECTS_SERVICE]->(s:Service {serviceId: $serviceId})\n"
            "OPTIONAL MATCH (i)-[:HAS_TIMELINE_EVENT]->(detected:TimelineEvent {event: 'detected'})\n"
            "OPTIONAL MATCH (i)-[:HAS_TIMELINE_EVENT]->(mitigated:TimelineEvent {event: 'mitigated'})\n"
            "WITH i, detected.timestamp AS detectedTime, mitigated.timestamp AS mitigatedTime\n"
            "WHERE detectedTime IS NOT NULL AND mitigatedTime IS NOT NULL\n"
            "RETURN i.incidentId AS incidentId, i.createdDate AS createdDate, "
            "       detectedTime, mitigatedTime\n"
            "ORDER BY i.createdDate DESC\n"
            "LIMIT $limit"
        ),
        params=(ParamSpec("serviceId", "str", required=True, max_len=128),),
        max_limit=50,
        default_limit=20,
    ),
    # Blast radius queries
    "blast_radius.resource_impact": QuerySpec(
        query_id="blast_radius.resource_impact",
        cypher=(
            "MATCH (r:AzureResource {resourceName: $resourceName})\n"
            "OPTIONAL MATCH (r)-[:IN_RESOURCE_GROUP]->(rg:ResourceGroup)\n"
            "OPTIONAL MATCH (rg)-[:IN_SUBSCRIPTION]->(sub:Subscription)\n"
            "OPTIONAL MATCH (r)<-[:OWNS_RESOURCE]-(s:Service)\n"
            "OPTIONAL MATCH (r)-[:IN_RESOURCE_GROUP]->(rg)<-[:IN_RESOURCE_GROUP]-(peer:AzureResource)\n"
            "WHERE peer.resourceName <> r.resourceName\n"
            "OPTIONAL MATCH (s)<-[:AFFECTS_SERVICE]-(i:Incident)\n"
            "WITH r, rg, sub, s, collect(DISTINCT peer) AS peers, collect(DISTINCT i) AS incidents\n"
            "RETURN r.resourceName AS resourceName, r.resourceType AS resourceType, "
            "       rg.key AS resourceGroupKey, rg.name AS resourceGroupName, "
            "       sub.subscriptionId AS subscriptionId, "
            "       s.serviceId AS serviceId, s.name AS serviceName, "
            "       size(peers) AS peerResourceCount, "
            "       [p IN peers | {name: p.resourceName, type: p.resourceType}] AS peerResources, "
            "       size(incidents) AS incidentCount, "
            "       [inc IN incidents | {id: inc.incidentId, severity: inc.severity, date: inc.createdDate}] AS recentIncidents\n"
            "LIMIT $limit"
        ),
        params=(ParamSpec("resourceName", "str", required=True, max_len=256),),
        max_limit=10,
        default_limit=1,
    ),
    "blast_radius.template_impact": QuerySpec(
        query_id="blast_radius.template_impact",
        cypher=(
            "MATCH (t:Template {name: $templateName})\n"
            "OPTIONAL MATCH (d:Deployment)-[:USES_TEMPLATE]->(t)\n"
            "OPTIONAL MATCH (d)-[:TARGETS_RESOURCE_GROUP]->(rg:ResourceGroup)\n"
            "OPTIONAL MATCH (rg)<-[:IN_RESOURCE_GROUP]-(r:AzureResource)\n"
            "WITH t, collect(DISTINCT d) AS deployments, collect(DISTINCT rg) AS resourceGroups, collect(DISTINCT r) AS resources\n"
            "RETURN t.name AS templateName, t.version AS templateVersion, "
            "       size(deployments) AS deploymentCount, "
            "       [dep IN deployments | {rolloutId: dep.rolloutId, artifactVersion: dep.artifactVersion}] AS deployments, "
            "       size(resourceGroups) AS resourceGroupCount, "
            "       [g IN resourceGroups | {key: g.key, name: g.name}] AS resourceGroups, "
            "       size(resources) AS resourceCount, "
            "       [res IN resources | {name: res.resourceName, type: res.resourceType}] AS resources\n"
            "LIMIT $limit"
        ),
        params=(ParamSpec("templateName", "str", required=True, max_len=256),),
        max_limit=10,
        default_limit=1,
    ),
    "blast_radius.service_impact": QuerySpec(
        query_id="blast_radius.service_impact",
        cypher=(
            "MATCH (s:Service {serviceId: $serviceId})\n"
            "OPTIONAL MATCH (s)-[:OWNS_RESOURCE]->(r:AzureResource)\n"
            "OPTIONAL MATCH (r)-[:IN_RESOURCE_GROUP]->(rg:ResourceGroup)\n"
            "OPTIONAL MATCH (r)-[:IN_SUBSCRIPTION]->(sub:Subscription)\n"
            "OPTIONAL MATCH (s)<-[:AFFECTS_SERVICE]-(i:Incident)\n"
            "OPTIONAL MATCH (d:Deployment)-[:FOR_SERVICE]->(s)\n"
            "WITH s, collect(DISTINCT r) AS resources, collect(DISTINCT rg) AS resourceGroups, "
            "     collect(DISTINCT sub) AS subscriptions, collect(DISTINCT i) AS incidents, collect(DISTINCT d) AS deployments\n"
            "RETURN s.serviceId AS serviceId, s.name AS serviceName, "
            "       size(resources) AS resourceCount, "
            "       [res IN resources | {name: res.resourceName, type: res.resourceType}] AS resources, "
            "       size(resourceGroups) AS resourceGroupCount, "
            "       [g IN resourceGroups | {key: g.key, name: g.name}] AS resourceGroups, "
            "       size(subscriptions) AS subscriptionCount, "
            "       [sub IN subscriptions | sub.subscriptionId] AS subscriptions, "
            "       size(incidents) AS incidentCount, "
            "       [inc IN incidents | {id: inc.incidentId, severity: inc.severity, date: inc.createdDate, changeRelated: inc.changeRelated}] AS incidents, "
            "       size(deployments) AS deploymentCount\n"
            "LIMIT $limit"
        ),
        params=(ParamSpec("serviceId", "str", required=True, max_len=128),),
        max_limit=10,
        default_limit=1,
    ),
}


def get_query(query_id: str) -> QuerySpec:
    query = ALLOWLIST.get(query_id)
    if query is None:
        raise UnknownQueryError(f"Query not allowlisted: {query_id}")
    return query
