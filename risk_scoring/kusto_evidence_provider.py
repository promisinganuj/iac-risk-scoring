"""Kusto-backed evidence provider for IcM/Outage data.

Populates scoring evidence keys by executing allowlisted KQL queries
directly against the IcM Kusto cluster. Assumes the caller is already
authenticated (KustoClient is pre-configured with appropriate credentials).
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, Dict, List, Optional

from risk_scoring.evidence_provider import ProviderResult
from risk_scoring.graph_expansion import QueryRun
from risk_scoring.kusto_allowlist import (
    KQL_ALLOWLIST,
    build_kql,
    get_kql_query,
    validate_kql_params,
)
from risk_scoring.kusto_client import KustoClient, KustoQueryError
from risk_scoring.models import ResolvedEntityRef

logger = logging.getLogger(__name__)


class KustoEvidenceProvider:
    """Evidence provider that queries IcM Kusto for incident/outage data.

    Responsible evidence keys:
    - open_icms
    - avg_mttm_minutes
    - historical_outages_180d
    - related_incidents
    """

    def __init__(self, client: KustoClient) -> None:
        self._client = client

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
    }

    def populate(
        self,
        resolved: ResolvedEntityRef,
        evidence: Dict[str, Any],
        *,
        as_of: Optional[date] = None,
    ) -> ProviderResult:
        """Populate IcM evidence keys by running allowlisted KQL queries.

        Requires ``service_id`` in the evidence dict (set by an earlier
        provider or from entity resolution). If missing, all keys are
        marked unknown.
        """
        queries: List[QueryRun] = []
        populated: List[str] = []
        unknowns: List[str] = []

        # We need a service ID (GUID) to query IcM.
        service_id = evidence.get("service_id")
        if not service_id or not isinstance(service_id, str) or not service_id.strip():
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
                result_value, qr = self._run_query(query_id, service_id)
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
        self, query_id: str, service_id: str
    ) -> tuple[Optional[int], QueryRun]:
        """Run a single KQL query and extract the scalar result."""
        spec = get_kql_query(query_id)
        params = {"serviceId": service_id}
        validated = validate_kql_params(spec, params)
        kql = build_kql(spec, validated)

        rows = self._client.execute(kql)

        qr = QueryRun(
            query_id=query_id,
            params={"serviceId": service_id},
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
