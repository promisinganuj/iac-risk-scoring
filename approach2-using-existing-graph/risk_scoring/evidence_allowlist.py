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
}


def get_query(query_id: str) -> QuerySpec:
    query = ALLOWLIST.get(query_id)
    if query is None:
        raise UnknownQueryError(f"Query not allowlisted: {query_id}")
    return query
