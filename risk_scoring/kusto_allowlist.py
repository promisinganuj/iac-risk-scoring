"""KQL query allowlist for evidence collection from Azure Data Explorer.

Mirrors the safety pattern of evidence_allowlist.py (Cypher):
- KqlQuerySpec: frozen dataclass with query_id, kql template, params, take limit
- Parameter validation (type, length, bounds)
- All queries are read-only and bounded with `take`

KQL queries use string interpolation placeholders ({param_name}) rather than
parameterised bindings because the Kusto SDK's `execute()` does not support
parameterised queries in the same way as Neo4j.  The `build_kql()` helper
performs safe substitution after validation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional

# Reuse the same param/validation infrastructure from the Cypher allowlist.
from risk_scoring.evidence_allowlist import (
    ParamSpec,
    ParameterValidationError,
    UnknownQueryError,
    _validate_param,
)


# ---------------------------------------------------------------------------
# KQL-specific dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class KqlQuerySpec:
    """A single allowlisted KQL query template.

    Attributes
    ----------
    query_id : str
        Unique identifier, e.g. "k1.open_icms".
    kql : str
        KQL template with ``{param}`` placeholders.
    params : tuple[ParamSpec, ...]
        Declared parameters (validated before substitution).
    max_take : int
        Upper bound for the ``take`` clause injected at the end.
    default_take : int
        Default ``take`` value when the caller does not specify one.
    evidence_key : str
        The key in the scoring evidence dict that this query populates.
    description : str
        Human-readable note for audit/debug.
    """

    query_id: str
    kql: str
    params: tuple[ParamSpec, ...]
    source: str = ""  # logical source name from kusto_sources.yaml
    max_take: int = 1000
    default_take: int = 100
    evidence_key: str = ""
    description: str = ""


# ---------------------------------------------------------------------------
# Validation & KQL building
# ---------------------------------------------------------------------------

# Characters we allow inside interpolated string values.
# GUID pattern (hex + hyphens) — used for Service Tree ServiceId, etc.
_SAFE_GUID_RE = re.compile(r"^[A-Fa-f0-9\-]+$")

# Service-name pattern — letters, digits, spaces, hyphens, underscores,
# parentheses, periods, commas, ampersands, forward-slashes.
# Deliberately excludes quotes, backslashes, semicolons, pipes, and braces
# to prevent KQL injection.
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9 \-_().,&/+:@#]+$")


def validate_kql_params(
    query: KqlQuerySpec, params: Mapping[str, Any]
) -> Dict[str, Any]:
    """Validate params against the query spec and return a clean dict.

    Adds a validated ``take`` key respecting max_take / default_take.
    """
    validated: Dict[str, Any] = {}
    for spec in query.params:
        validated[spec.name] = _validate_param(spec, params.get(spec.name))

    # --- take (analogous to Cypher limit) ---
    take = params.get("take")
    if take is None:
        take = query.default_take

    if not isinstance(take, int):
        raise ParameterValidationError("Param take must be an int")
    if take <= 0:
        raise ParameterValidationError("Param take must be > 0")
    if take > query.max_take:
        raise ParameterValidationError(
            f"Param take exceeds max_take={query.max_take} for query {query.query_id}"
        )
    validated["take"] = take

    return validated


def build_kql(query: KqlQuerySpec, validated_params: Dict[str, Any]) -> str:
    """Substitute validated params into the KQL template.

    String values are single-quoted; ints and bools are inserted literally.
    Only values that passed validation are substituted — this is defence-in-depth.

    Raises ``ParameterValidationError`` if a string value contains characters
    outside the safe set (hex + hyphens), preventing KQL injection.
    """
    replacements: Dict[str, str] = {}
    for spec in query.params:
        val = validated_params[spec.name]
        if val is None:
            continue
        if spec.kind == "str":
            sval = str(val)
            # Choose the appropriate safe-character regex based on context.
            safe_re = _SAFE_GUID_RE if spec.max_len <= 36 else _SAFE_NAME_RE
            if not safe_re.match(sval):
                raise ParameterValidationError(
                    f"Param {spec.name} contains unsafe characters for KQL interpolation"
                )
            replacements[spec.name] = f"'{sval}'"
        elif spec.kind == "int":
            replacements[spec.name] = str(int(val))
        elif spec.kind == "bool":
            replacements[spec.name] = "true" if val else "false"

    # take is always an int
    replacements["take"] = str(int(validated_params["take"]))

    # Perform substitution
    kql = query.kql
    for key, replacement in replacements.items():
        kql = kql.replace(f"{{{key}}}", replacement)

    return kql


# ---------------------------------------------------------------------------
# IcM / Service Tree table references
# ---------------------------------------------------------------------------

# Plain table name — queries run against the database defined in
# kusto_sources.yaml, so no cross-cluster() qualifier is needed.
_ICM_TABLE = "IncidentsSnapshotV2"

# SafeFly deployment request table.
_SAFEFLY_TABLE = "SafeFlyRequestCurrentMV"


# ---------------------------------------------------------------------------
# Allowlisted KQL queries — IcM / Outage
# ---------------------------------------------------------------------------

# Common param: serviceName is the OwningTenantName string in IcM,
# which matches ServiceName in Service Tree.
_SERVICE_NAME_PARAM = ParamSpec(
    name="serviceName", kind="str", required=True, max_len=256
)


KQL_ALLOWLIST: Dict[str, KqlQuerySpec] = {

    # k1 — Count of open (unresolved) IcM incidents for a service
    "k1.open_icms": KqlQuerySpec(
        query_id="k1.open_icms",
        kql=(
            f"{_ICM_TABLE}\n"
            "| where OwningTenantName == {serviceName}\n"
            "| where isempty(ResolveDate)\n"
            "| summarize open_icms = count()\n"
            "| take {take}"
        ),
        params=(_SERVICE_NAME_PARAM,),
        source="icm",
        max_take=1,
        default_take=1,
        evidence_key="open_icms",
        description="Count of open (unresolved) IcM incidents for a service.",
    ),

    # k4 — Average MTTM (ImpactStartDate → MitigateDate) in minutes, last 180d
    "k4.avg_mttm": KqlQuerySpec(
        query_id="k4.avg_mttm",
        kql=(
            f"{_ICM_TABLE}\n"
            "| where OwningTenantName == {serviceName}\n"
            "| where isnotempty(ImpactStartDate) and isnotempty(MitigateDate)\n"
            "| where ImpactStartDate > ago(180d)\n"
            "| extend mttm_minutes = datetime_diff('minute', MitigateDate, ImpactStartDate)\n"
            "| where mttm_minutes > 0\n"
            "| summarize avg_mttm_minutes = toint(avg(mttm_minutes))\n"
            "| take {take}"
        ),
        params=(_SERVICE_NAME_PARAM,),
        source="icm",
        max_take=1,
        default_take=1,
        evidence_key="avg_mttm_minutes",
        description="Average MTTM in minutes (ImpactStartDate→MitigateDate) over last 180 days.",
    ),

    # k5 — Count of outages in the last 180 days
    "k5.outages_180d": KqlQuerySpec(
        query_id="k5.outages_180d",
        kql=(
            f"{_ICM_TABLE}\n"
            "| where OwningTenantName == {serviceName}\n"
            "| where IsOutage == true\n"
            "| where CreateDate > ago(180d)\n"
            "| summarize historical_outages_180d = count()\n"
            "| take {take}"
        ),
        params=(_SERVICE_NAME_PARAM,),
        source="icm",
        max_take=1,
        default_take=1,
        evidence_key="historical_outages_180d",
        description="Count of outages (IsOutage==true) in the last 180 days.",
    ),

    # k6 — Count of related incidents via ParentIncidentId linkage
    "k6.related_incidents": KqlQuerySpec(
        query_id="k6.related_incidents",
        kql=(
            f"let service_incidents = {_ICM_TABLE}\n"
            "    | where OwningTenantName == {serviceName}\n"
            "    | where CreateDate > ago(90d)\n"
            "    | where isnotempty(ParentIncidentId) and ParentIncidentId > 0\n"
            "    | summarize related_incidents = dcount(ParentIncidentId);\n"
            "service_incidents\n"
            "| take {take}"
        ),
        params=(_SERVICE_NAME_PARAM,),
        source="icm",
        max_take=1,
        default_take=1,
        evidence_key="related_incidents",
        description="Count of distinct parent-linked incident clusters in the last 90 days.",
    ),

    # k7 — Resolve ServiceName → ServiceId via Service Tree
    "k7.service_tree_lookup": KqlQuerySpec(
        query_id="k7.service_tree_lookup",
        kql=(
            "GetServicesByName(datatable(ServiceName: string)[{serviceName}])\n"
            "| project ServiceId, ServiceName, ShortName, ServiceLevel,\n"
            "          Organization, ServiceLifecycleStage, IsExternalFacing\n"
            "| take {take}"
        ),
        params=(_SERVICE_NAME_PARAM,),
        source="service_tree",
        max_take=10,
        default_take=1,
        evidence_key="service_tree_id",
        description="Resolve a service name to its Service Tree ServiceId and metadata.",
    ),

    # k8 — Count of SafeFly deployment requests in the last 30 days
    "k8.deployment_count_30d": KqlQuerySpec(
        query_id="k8.deployment_count_30d",
        kql=(
            f"{_SAFEFLY_TABLE}\n"
            "| where ServiceName == {serviceName}\n"
            "| where CreatedDate > ago(30d)\n"
            "| summarize deployment_count_30d = count()\n"
            "| take {take}"
        ),
        params=(_SERVICE_NAME_PARAM,),
        source="safefly",
        max_take=1,
        default_take=1,
        evidence_key="deployment_count_30d",
        description="Count of SafeFly deployment requests in the last 30 days.",
    ),

    # k9 — Count of abandoned/rejected deployments (proxy for stage failures)
    "k9.deployment_failures": KqlQuerySpec(
        query_id="k9.deployment_failures",
        kql=(
            f"{_SAFEFLY_TABLE}\n"
            "| where ServiceName == {serviceName}\n"
            "| where CreatedDate > ago(90d)\n"
            "| where Status in ('Abandoned', 'Rejected')\n"
            "| summarize deployment_stage_failures = count()\n"
            "| take {take}"
        ),
        params=(_SERVICE_NAME_PARAM,),
        source="safefly",
        max_take=1,
        default_take=1,
        evidence_key="deployment_stage_failures",
        description="Count of abandoned or rejected SafeFly requests in the last 90 days.",
    ),
}


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def get_kql_query(query_id: str) -> KqlQuerySpec:
    """Retrieve an allowlisted KQL query by ID.

    Raises ``UnknownQueryError`` if the query_id is not in the allowlist.
    """
    query = KQL_ALLOWLIST.get(query_id)
    if query is None:
        raise UnknownQueryError(f"KQL query not allowlisted: {query_id}")
    return query


# ---------------------------------------------------------------------------
# Service Tree → Subscription mapping
# ---------------------------------------------------------------------------

_SERVICE_ID_PARAM = ParamSpec(
    name="serviceId", kind="str", required=True, max_len=36
)

_SUBSCRIPTION_ID_PARAM = ParamSpec(
    name="subscriptionId", kind="str", required=True, max_len=36
)

_RESOURCE_GROUP_NAME_PARAM = ParamSpec(
    name="resourceGroupName", kind="str", required=True, max_len=256
)

KQL_ALLOWLIST["k10.service_subscriptions"] = KqlQuerySpec(
    query_id="k10.service_subscriptions",
    kql=(
        "let Services = datatable(ServiceId:string)[{serviceId}];\n"
        "GetSubscriptionsAssociatedWith(Services)\n"
        "| project SubscriptionId, SubscriptionName, ServiceId,\n"
        "          ServiceName, Environment, Status\n"
        "| take {take}"
    ),
    params=(_SERVICE_ID_PARAM,),
    source="service_tree",
    max_take=500,
    default_take=200,
    evidence_key="service_subscriptions",
    description=(
        "Get all Azure subscriptions associated with a service via "
        "Service Tree GetSubscriptionsAssociatedWith()."
    ),
)


# ---------------------------------------------------------------------------
# Repo → Service mapping (reverse lookup)
# ---------------------------------------------------------------------------

_REPO_URL_PARAM = ParamSpec(
    name="repoUrl", kind="str", required=True, max_len=512
)

KQL_ALLOWLIST["k11.repo_to_service"] = KqlQuerySpec(
    query_id="k11.repo_to_service",
    kql=(
        "let metadataDefId = ServiceTree_MetadataDefinition_Snapshot\n"
        "    | where Id == 'ProdCat_SourceCodeLocation'\n"
        "    | project InternalId;\n"
        "ServiceTree_ServiceMetadata_Snapshot\n"
        "| where MetadataDefinitionInternalId == toscalar(metadataDefId)"
        " and Status < 2\n"
        "| extend ParsedValue = todynamic(Value)\n"
        "| where tostring(ParsedValue.RepoUrl) =~ {repoUrl}\n"
        "| join kind=inner ServiceTree_ServiceHierarchy_Snapshot"
        " on $left.ServiceInternalId == $right.InternalId\n"
        "| project ServiceId = tostring(Id), ServiceName = Name\n"
        "| take {take}"
    ),
    params=(_REPO_URL_PARAM,),
    source="service_tree",
    max_take=10,
    default_take=5,
    evidence_key="repo_service_mapping",
    description=(
        "Reverse lookup: find the Service Tree service that owns a given "
        "source code repository URL via ProdCat_SourceCodeLocation metadata."
    ),
)


# ---------------------------------------------------------------------------
# Service → Repos (forward lookup for evidence enrichment)
# ---------------------------------------------------------------------------

KQL_ALLOWLIST["k12.service_repos"] = KqlQuerySpec(
    query_id="k12.service_repos",
    kql=(
        "let Services = datatable(ServiceId:string)[{serviceId}];\n"
        "GetServicesMetadataValues(Services, 'ProdCat_SourceCodeLocation')\n"
        "| project ServiceId, ServiceName, RepoUrl, SourceCodeType\n"
        "| take {take}"
    ),
    params=(_SERVICE_ID_PARAM,),
    source="service_tree",
    max_take=100,
    default_take=50,
    evidence_key="source_repos",
    description=(
        "Get all source code repository URLs registered in Service Tree "
        "for a service via GetServicesMetadataValues()."
    ),
)


# ---------------------------------------------------------------------------
# Azure Resource Graph (ARG) evidence
# ---------------------------------------------------------------------------

KQL_ALLOWLIST["k13.arg_peer_resources"] = KqlQuerySpec(
    query_id="k13.arg_peer_resources",
    kql=(
        "Resources\n"
        "| where subscriptionId =~ {subscriptionId}\n"
        "| where resourceGroup =~ {resourceGroupName}\n"
        "| summarize peer_resource_count = count()\n"
        "| take {take}"
    ),
    params=(_SUBSCRIPTION_ID_PARAM, _RESOURCE_GROUP_NAME_PARAM),
    source="arg",
    max_take=1,
    default_take=1,
    evidence_key="peer_resource_count",
    description=(
        "Count resources in the same resource group via ARG. "
        "Provider excludes the changed resource when deriving peer count."
    ),
)
