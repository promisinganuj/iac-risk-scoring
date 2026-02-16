"""Neo4j-backed evidence provider.

Wraps the existing ``expand_evidence_for_resource()`` logic from
graph_expansion.py as an EvidenceProvider implementation. This keeps
the current Neo4j/Cypher-based evidence collection working unchanged
while allowing it to participate in the pluggable provider pipeline.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from risk_scoring.evidence_client import EvidenceClient
from risk_scoring.evidence_provider import ProviderResult
from risk_scoring.graph_expansion import (
    GraphExpansionResult,
    QueryRun,
    expand_evidence_for_resource,
)
from risk_scoring.models import ResolvedEntityRef

logger = logging.getLogger(__name__)


class Neo4jEvidenceProvider:
    """Evidence provider backed by Neo4j graph queries.

    Delegates to the existing ``expand_evidence_for_resource()`` function,
    then copies the resulting evidence keys into the shared evidence dict.

    Responsible evidence keys (from Neo4j graph):
    - resource_id, resource_type, subscription_id
    - resource_group_key, resource_group_name
    - service_id, service_name
    - services_impacted
    - historical_outages_180d (from graph incidents, if as_of provided)
    - recent_incidents, recent_deployments
    - deployment_count_30d (always unknown in current graph)
    - critical_services (always unknown in current graph)
    - open_icms (always unknown in current graph)
    """

    def __init__(self, client: EvidenceClient) -> None:
        self._client = client

    @property
    def name(self) -> str:
        return "neo4j"

    def populate(
        self,
        resolved: ResolvedEntityRef,
        evidence: Dict[str, Any],
        *,
        as_of: Optional[date] = None,
    ) -> ProviderResult:
        """Run Neo4j graph expansion and merge results into evidence."""
        try:
            expansion = expand_evidence_for_resource(
                resolved, self._client, as_of=as_of
            )
        except Exception as exc:
            logger.warning("Neo4j expansion failed: %s", exc, exc_info=True)
            return ProviderResult(
                provider_name=self.name,
                queries=(),
                populated_keys=(),
                unknown_keys=(),
                error=f"{type(exc).__name__}: {exc}",
            )

        populated: List[str] = []
        unknowns_from_expansion = set(expansion.unknowns)

        # Copy evidence keys from expansion, but don't overwrite keys
        # already populated by an earlier provider with real values.
        for key, value in expansion.evidence.items():
            if key in unknowns_from_expansion:
                # Only set if not already populated by another provider.
                evidence.setdefault(key, value)
            else:
                # Neo4j produced a real value — set it unless already present.
                if key not in evidence or evidence[key] is None:
                    evidence[key] = value
                    populated.append(key)

        return ProviderResult(
            provider_name=self.name,
            queries=expansion.queries,
            populated_keys=tuple(sorted(populated)),
            unknown_keys=tuple(sorted(unknowns_from_expansion)),
        )
