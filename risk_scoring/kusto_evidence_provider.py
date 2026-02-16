"""Kusto-backed evidence provider for IcM/Outage and Service Tree data.

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
    - deployment_count_30d
    - deployment_stage_failures
    - service_tree_id  (ServiceId from Service Tree)
    - service_subscriptions  (list of subscription dicts)
    - subscription_count
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

    # The KQL query IDs this provider is responsible for (scalar queries),
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
        """Populate evidence keys by running allowlisted KQL queries.

        Pipeline within this provider:
        1. Run scalar IcM/SafeFly queries (require service_name)
        2. Resolve ServiceId via k7 (requires service_name)
        3. Get subscriptions via k10 (requires ServiceId from step 2)
        """
        queries: List[QueryRun] = []
        populated: List[str] = []
        unknowns: List[str] = []

        # We need a service name to query IcM (matches OwningTenantName).
        service_name = evidence.get("service_name")
        if not service_name or not isinstance(service_name, str) or not service_name.strip():
            # No service context — mark all our keys as unknown.
            all_keys = list(self._QUERY_MAP.values()) + [
                "service_tree_id",
                "service_subscriptions",
                "subscription_count",
            ]
            for ek in all_keys:
                evidence.setdefault(ek, None)
                unknowns.append(ek)
            return ProviderResult(
                provider_name=self.name,
                queries=(),
                populated_keys=(),
                unknown_keys=tuple(sorted(unknowns)),
            )

        # --- Phase 1: Scalar IcM / SafeFly queries ---
        for query_id, evidence_key in self._QUERY_MAP.items():
            try:
                result_value, qr = self._run_scalar_query(query_id, service_name)
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

        # --- Phase 2: Service Tree lookup (k7) → ServiceId ---
        service_id = self._resolve_service_id(
            service_name, evidence, queries, populated, unknowns
        )

        # --- Phase 3: Subscription mapping (k10) → subscription list ---
        self._resolve_subscriptions(
            service_id, evidence, queries, populated, unknowns
        )

        return ProviderResult(
            provider_name=self.name,
            queries=tuple(queries),
            populated_keys=tuple(sorted(populated)),
            unknown_keys=tuple(sorted(unknowns)),
        )

    # ------------------------------------------------------------------
    # Phase 2: Service Tree ID resolution
    # ------------------------------------------------------------------

    def _resolve_service_id(
        self,
        service_name: str,
        evidence: Dict[str, Any],
        queries: List[QueryRun],
        populated: List[str],
        unknowns: List[str],
    ) -> Optional[str]:
        """Run k7.service_tree_lookup to get the ServiceId for a service name."""
        try:
            spec = get_kql_query("k7.service_tree_lookup")
            params = {"serviceName": service_name}
            validated = validate_kql_params(spec, params)
            kql = build_kql(spec, validated)
            client = self._client_for(spec.source)
            rows = client.execute(kql)

            qr = QueryRun(
                query_id="k7.service_tree_lookup",
                params={"serviceName": service_name},
                row_count=len(rows),
                sample_rows=tuple(rows[:3]),
            )
            queries.append(qr)

            if rows:
                service_id = rows[0].get("ServiceId")
                if service_id:
                    evidence["service_tree_id"] = service_id
                    populated.append("service_tree_id")
                    return str(service_id)

            evidence.setdefault("service_tree_id", None)
            unknowns.append("service_tree_id")
            return None

        except (KustoQueryError, Exception) as exc:
            logger.warning(
                "k7.service_tree_lookup failed: %s", exc, exc_info=True
            )
            evidence.setdefault("service_tree_id", None)
            unknowns.append("service_tree_id")
            return None

    # ------------------------------------------------------------------
    # Phase 3: Subscription mapping
    # ------------------------------------------------------------------

    def _resolve_subscriptions(
        self,
        service_id: Optional[str],
        evidence: Dict[str, Any],
        queries: List[QueryRun],
        populated: List[str],
        unknowns: List[str],
    ) -> None:
        """Run k10.service_subscriptions to get subscriptions for a service."""
        if not service_id:
            evidence.setdefault("service_subscriptions", None)
            evidence.setdefault("subscription_count", None)
            unknowns.extend(["service_subscriptions", "subscription_count"])
            return

        try:
            spec = get_kql_query("k10.service_subscriptions")
            params = {"serviceId": service_id}
            validated = validate_kql_params(spec, params)
            kql = build_kql(spec, validated)
            client = self._client_for(spec.source)
            rows = client.execute(kql)

            qr = QueryRun(
                query_id="k10.service_subscriptions",
                params={"serviceId": service_id},
                row_count=len(rows),
                sample_rows=tuple(rows[:5]),
            )
            queries.append(qr)

            if rows:
                subscriptions = [
                    {
                        "subscription_id": r.get("SubscriptionId", ""),
                        "subscription_name": r.get("SubscriptionName", ""),
                        "environment": r.get("Environment", ""),
                        "status": r.get("Status"),
                    }
                    for r in rows
                ]
                evidence["service_subscriptions"] = subscriptions
                evidence["subscription_count"] = len(subscriptions)
                populated.extend(["service_subscriptions", "subscription_count"])
            else:
                evidence["service_subscriptions"] = []
                evidence["subscription_count"] = 0
                populated.extend(["service_subscriptions", "subscription_count"])

        except (KustoQueryError, Exception) as exc:
            logger.warning(
                "k10.service_subscriptions failed: %s", exc, exc_info=True
            )
            evidence.setdefault("service_subscriptions", None)
            evidence.setdefault("subscription_count", None)
            unknowns.extend(["service_subscriptions", "subscription_count"])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _run_scalar_query(
        self, query_id: str, service_name: str
    ) -> tuple[Optional[int], QueryRun]:
        """Run a single KQL query and extract the scalar result."""
        spec = get_kql_query(query_id)
        params = {"serviceName": service_name}
        validated = validate_kql_params(spec, params)
        kql = build_kql(spec, validated)

        client = self._client_for(spec.source)
        rows = client.execute(kql)

        qr = QueryRun(
            query_id=query_id,
            params={"serviceName": service_name},
            row_count=len(rows),
            sample_rows=tuple(rows[:5]),
        )

        # All scalar queries return a single summarize row with one column.
        if rows and len(rows) > 0:
            row = rows[0]
            value = row.get(spec.evidence_key)
            if value is not None:
                try:
                    return int(value), qr
                except (ValueError, TypeError):
                    return None, qr
        return None, qr

    def _client_for(self, source: str) -> KustoClient:
        """Return the KustoClient for the given logical source name."""
        if self._registry is not None:
            return self._registry.get_client(source)
        assert self._client is not None
        return self._client
