"""Kusto-backed evidence provider for IcM/Outage data.

Populates scoring evidence keys by executing allowlisted KQL queries
against the appropriate Kusto cluster (determined by each query's ``source``
field and the ``KustoSourceRegistry`` YAML config).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional, Union

from risk_scoring.evidence_provider import ProviderResult
from risk_scoring.graph_expansion import QueryRun
from risk_scoring.kusto_allowlist import (
    KQL_ALLOWLIST,
    build_kql,
    get_kql_query,
    validate_kql_params,
)
from risk_scoring.kusto_client import KustoClient, KustoQueryError
from risk_scoring.kusto_source_config import KustoSourceRegistry
from risk_scoring.models import ResolvedEntityRef

logger = logging.getLogger(__name__)


class KustoEvidenceProvider:
    """Evidence provider that queries Kusto for incident/outage data.

    Accepts either a ``KustoSourceRegistry`` (preferred — multi-cluster) or a
    plain ``KustoClient`` (backward-compatible — single cluster, all queries
    run against that one client).

    Responsible evidence keys:
    - open_icms
    - avg_mttm_minutes
    - historical_outages_180d
    - related_incidents
    """

    def __init__(
        self, client_or_registry: Union[KustoClient, KustoSourceRegistry]
    ) -> None:
        if isinstance(client_or_registry, KustoSourceRegistry):
            self._registry: Optional[KustoSourceRegistry] = client_or_registry
            self._client: Optional[KustoClient] = None
        else:
            self._registry = None
            self._client = client_or_registry

    @property
    def name(self) -> str:
        return "kusto-icm"

    # The KQL query IDs this provider is responsible for,
    # mapped to the evidence key each populates.
    _QUERY_MAP = {
        "k1.open_icms": "open_icms",
        "k4.avg_mttm": "avg_mttm_minutes",
        "k5.outages_180d": "historical_outages_180d",
        "k6.related_incidents": "related_incidents",
        "k8.deployment_count_30d": "deployment_count_30d",
        "k9.deployment_failures": "deployment_stage_failures",
    }

    def populate(
        self,
        resolved: ResolvedEntityRef,
        evidence: Dict[str, Any],
        *,
        as_of: Optional[date] = None,
    ) -> ProviderResult:
        """Populate IcM evidence keys by running allowlisted KQL queries.

        Requires ``service_name`` in the evidence dict (set by an earlier
        provider, e.g. Neo4j graph expansion). If missing, all keys are
        marked unknown.
        """
        queries: List[QueryRun] = []
        populated: List[str] = []
        unknowns: List[str] = []

        # We need a service name to query IcM (matches OwningTenantName).
        service_name = evidence.get("service_name")
        if not service_name or not isinstance(service_name, str) or not service_name.strip():
            # No service context — mark all our keys as unknown.
            for ek in self._QUERY_MAP.values():
                evidence.setdefault(ek, None)
                unknowns.append(ek)
            return ProviderResult(
                provider_name=self.name,
                queries=(),
                populated_keys=(),
                unknown_keys=tuple(sorted(unknowns)),
            )

        # Run each allowlisted KQL query.
        for query_id, evidence_key in self._QUERY_MAP.items():
            try:
                result_value, qr = self._run_query(query_id, service_name)
                queries.append(qr)

                if result_value is not None:
                    evidence[evidence_key] = result_value
                    populated.append(evidence_key)
                else:
                    evidence.setdefault(evidence_key, None)
                    unknowns.append(evidence_key)

            except (KustoQueryError, Exception) as exc:
                logger.warning(
                    "KQL query %s failed: %s", query_id, exc, exc_info=True
                )
                evidence.setdefault(evidence_key, None)
                unknowns.append(evidence_key)

        return ProviderResult(
            provider_name=self.name,
            queries=tuple(queries),
            populated_keys=tuple(sorted(populated)),
            unknown_keys=tuple(sorted(unknowns)),
        )

    def _run_query(
        self, query_id: str, service_name: str
    ) -> tuple[Optional[int], QueryRun]:
        """Run a single KQL query and extract the scalar result."""
        spec = get_kql_query(query_id)
        params = {"serviceName": service_name}
        validated = validate_kql_params(spec, params)
        kql = build_kql(spec, validated)

        # Resolve the correct client for this query's source.
        client = self._client_for(spec.source)
        rows = client.execute(kql)

        qr = QueryRun(
            query_id=query_id,
            params={"serviceName": service_name},
            row_count=len(rows),
            sample_rows=tuple(rows[:5]),
        )

        # All our current queries return a single summarize row with one column.
        if rows and len(rows) > 0:
            row = rows[0]
            # The evidence_key in the KQL query is used as the column name.
            value = row.get(spec.evidence_key)
            if value is not None:
                try:
                    return int(value), qr
                except (ValueError, TypeError):
                    return None, qr
        return None, qr

    def _client_for(self, source: str) -> KustoClient:
        """Return the KustoClient for the given logical source name.

        When constructed with a registry, looks up the source; when
        constructed with a plain client, always returns that client.
        """
        if self._registry is not None:
            return self._registry.get_client(source)
        # Fallback: single-client mode (backward compat / tests).
        assert self._client is not None
        return self._client
