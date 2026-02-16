from __future__ import annotations

from typing import Optional

from risk_scoring.models import CandidateEntity
from risk_scoring.neo4j_http import Neo4jHttpConfig, run_cypher_readonly
from risk_scoring.repository import EntityRepository


class Neo4jHttpEntityRepository(EntityRepository):
    """Entity repository implemented via Neo4j HTTP Cypher (read-only)."""

    def __init__(self, config: Neo4jHttpConfig):
        self._config = config

    def find_azure_resources_by_resource_id(
        self, resource_id: str, *, limit: int
    ) -> list[CandidateEntity]:
        cypher = (
            "MATCH (r:AzureResource {resourceName: $resourceName})\n"
            "OPTIONAL MATCH (r)-[:IN_RESOURCE_GROUP]->(g:ResourceGroup)\n"
            "OPTIONAL MATCH (r)-[:IN_SUBSCRIPTION]->(sub:Subscription)\n"
            "RETURN r.resourceName AS resourceName, r.displayName AS displayName, r.resourceType AS resourceType, "
            "       sub.subscriptionId AS subscriptionId, g.name AS resourceGroup\n"
            "ORDER BY r.resourceName\n"
            "LIMIT $limit"
        )

        rows = run_cypher_readonly(
            config=self._config,
            cypher=cypher,
            params={"resourceName": resource_id, "limit": int(limit)},
        )

        out: list[CandidateEntity] = []
        for row in rows:
            rid = row.get("resourceName")
            if not isinstance(rid, str) or not rid.strip():
                continue
            out.append(
                CandidateEntity(
                    label="AzureResource",
                    resource_id=rid,
                    display_name=row.get("displayName") if isinstance(row.get("displayName"), str) else None,
                    resource_type=row.get("resourceType") if isinstance(row.get("resourceType"), str) else None,
                    subscription_id=row.get("subscriptionId")
                    if isinstance(row.get("subscriptionId"), str)
                    else None,
                    resource_group=row.get("resourceGroup")
                    if isinstance(row.get("resourceGroup"), str)
                    else None,
                )
            )

        return out[:limit]

    def find_azure_resources_by_attributes(
        self,
        *,
        resource_type: Optional[str],
        subscription_id: Optional[str],
        resource_group: Optional[str],
        display_name: Optional[str],
        limit: int,
    ) -> list[CandidateEntity]:
        # MVP: keep simple, deterministic filtering.
        # NOTE: This is read-only and only used when the caller doesn't provide resource_id.
        where_clauses: list[str] = []
        params: dict[str, object] = {"limit": int(limit)}

        cypher = (
            "MATCH (r:AzureResource)\n"
            "OPTIONAL MATCH (r)-[:IN_RESOURCE_GROUP]->(g:ResourceGroup)\n"
            "OPTIONAL MATCH (r)-[:IN_SUBSCRIPTION]->(sub:Subscription)\n"
        )

        if resource_type is not None:
            where_clauses.append("r.resourceType = $resourceType")
            params["resourceType"] = resource_type
        if display_name is not None:
            where_clauses.append("r.displayName = $displayName")
            params["displayName"] = display_name
        if subscription_id is not None:
            where_clauses.append("sub.subscriptionId = $subscriptionId")
            params["subscriptionId"] = subscription_id
        if resource_group is not None:
            where_clauses.append("g.name = $resourceGroup")
            params["resourceGroup"] = resource_group

        if where_clauses:
            cypher += "WHERE " + " AND ".join(where_clauses) + "\n"

        cypher += (
            "RETURN r.resourceName AS resourceName, r.displayName AS displayName, r.resourceType AS resourceType, "
            "       sub.subscriptionId AS subscriptionId, g.name AS resourceGroup\n"
            "ORDER BY r.resourceName\n"
            "LIMIT $limit"
        )

        rows = run_cypher_readonly(config=self._config, cypher=cypher, params=params)

        out: list[CandidateEntity] = []
        for row in rows:
            rid = row.get("resourceName")
            if not isinstance(rid, str) or not rid.strip():
                continue
            out.append(
                CandidateEntity(
                    label="AzureResource",
                    resource_id=rid,
                    display_name=row.get("displayName") if isinstance(row.get("displayName"), str) else None,
                    resource_type=row.get("resourceType") if isinstance(row.get("resourceType"), str) else None,
                    subscription_id=row.get("subscriptionId")
                    if isinstance(row.get("subscriptionId"), str)
                    else None,
                    resource_group=row.get("resourceGroup")
                    if isinstance(row.get("resourceGroup"), str)
                    else None,
                )
            )

        return out[:limit]
