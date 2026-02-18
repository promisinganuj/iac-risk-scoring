"""Tests for blast radius via Kusto joins (no Neo4j).

Validates that the Kusto evidence provider correctly populates
blast radius evidence keys (services_impacted, critical_services,
peer_resource_count) from Service Tree data instead of Neo4j.
"""

from __future__ import annotations

import unittest
from datetime import date

from risk_scoring.kusto_evidence_provider import KustoEvidenceProvider
from risk_scoring.models import ResolvedEntityRef
from risk_scoring.scoring import ChangeContext, score_change


# =====================================================================
# Fake Kusto client (same pattern as test_service_subscriptions.py)
# =====================================================================


class FakeKustoClient:
    """In-memory Kusto client returning canned results per query pattern."""

    def __init__(self, responses: dict[str, list[dict]] | None = None):
        self._responses = responses or {}
        self.calls: list[str] = []

    def execute(self, kql: str) -> list[dict]:
        self.calls.append(kql)
        for pattern, rows in self._responses.items():
            if pattern in kql:
                if isinstance(rows, Exception):
                    raise rows
                return rows
        return []


# =====================================================================
# Helper: standard responses for k1-k9 scalar queries
# =====================================================================

_SCALAR_ZEROS: dict[str, list[dict]] = {
    "OwningTenantName": [{"open_icms": 0}],
    "IsOutage": [{"historical_outages_180d": 0}],
    "ParentIncidentId": [{"related_incidents": 0}],
    "SafeFlyRequestCurrentMV": [{"deployment_count_30d": 0}],
}


# =====================================================================
# services_impacted via Kusto
# =====================================================================


class TestServicesImpacted(unittest.TestCase):
    """services_impacted should be 1 when service_name is known, None otherwise."""

    def _resolved(self, name: str = "Payments") -> ResolvedEntityRef:
        return ResolvedEntityRef(
            label="Service", resource_id=name, display_name=name
        )

    def _make_provider(self, responses: dict) -> KustoEvidenceProvider:
        return KustoEvidenceProvider(FakeKustoClient(responses))

    def test_services_impacted_is_1_with_service_name(self):
        provider = self._make_provider(
            {
                **_SCALAR_ZEROS,
                "GetServicesByName": [
                    {
                        "ServiceId": "abc-123",
                        "ServiceName": "Payments",
                        "ServiceLevel": "3",
                        "IsExternalFacing": False,
                    }
                ],
                "GetSubscriptionsAssociatedWith": [],
                "GetServicesMetadataValues": [],
            }
        )
        evidence: dict = {"service_name": "Payments"}
        result = provider.populate(self._resolved(), evidence)

        self.assertEqual(evidence["services_impacted"], 1)
        self.assertIn("services_impacted", result.populated_keys)

    def test_services_impacted_unknown_without_service_name(self):
        provider = self._make_provider({})
        evidence: dict = {}
        result = provider.populate(self._resolved(), evidence)

        self.assertIsNone(evidence.get("services_impacted"))
        self.assertIn("services_impacted", result.unknown_keys)

    def test_services_impacted_unknown_with_empty_service_name(self):
        provider = self._make_provider({})
        evidence: dict = {"service_name": "   "}
        result = provider.populate(self._resolved(), evidence)

        self.assertIsNone(evidence.get("services_impacted"))
        self.assertIn("services_impacted", result.unknown_keys)


# =====================================================================
# critical_services via k7 ServiceLevel / IsExternalFacing
# =====================================================================


class TestCriticalServices(unittest.TestCase):
    """critical_services should be derived from k7 Service Tree metadata."""

    def _resolved(self, name: str = "Payments") -> ResolvedEntityRef:
        return ResolvedEntityRef(
            label="Service", resource_id=name, display_name=name
        )

    def _make_provider(self, responses: dict) -> KustoEvidenceProvider:
        return KustoEvidenceProvider(FakeKustoClient(responses))

    def _base_responses(self, **k7_overrides) -> dict:
        row = {
            "ServiceId": "abc-123",
            "ServiceName": "Payments",
            "ServiceLevel": "3",
            "IsExternalFacing": False,
            **k7_overrides,
        }
        return {
            **_SCALAR_ZEROS,
            "GetServicesByName": [row],
            "GetSubscriptionsAssociatedWith": [],
            "GetServicesMetadataValues": [],
        }

    def test_external_facing_service_is_critical(self):
        provider = self._make_provider(
            self._base_responses(IsExternalFacing=True)
        )
        evidence: dict = {"service_name": "Payments"}
        provider.populate(self._resolved(), evidence)

        self.assertEqual(evidence["critical_services"], ["Payments"])

    def test_high_service_level_1_is_critical(self):
        provider = self._make_provider(
            self._base_responses(ServiceLevel="1")
        )
        evidence: dict = {"service_name": "Payments"}
        provider.populate(self._resolved(), evidence)

        self.assertEqual(evidence["critical_services"], ["Payments"])

    def test_high_service_level_2_is_critical(self):
        provider = self._make_provider(
            self._base_responses(ServiceLevel="2")
        )
        evidence: dict = {"service_name": "Payments"}
        provider.populate(self._resolved(), evidence)

        self.assertEqual(evidence["critical_services"], ["Payments"])

    def test_ring_0_label_is_critical(self):
        provider = self._make_provider(
            self._base_responses(ServiceLevel="Ring 0")
        )
        evidence: dict = {"service_name": "Payments"}
        provider.populate(self._resolved(), evidence)

        self.assertEqual(evidence["critical_services"], ["Payments"])

    def test_ring_1_label_is_critical(self):
        provider = self._make_provider(
            self._base_responses(ServiceLevel="Ring 1")
        )
        evidence: dict = {"service_name": "Payments"}
        provider.populate(self._resolved(), evidence)

        self.assertEqual(evidence["critical_services"], ["Payments"])

    def test_non_critical_service_returns_empty_list(self):
        provider = self._make_provider(
            self._base_responses(ServiceLevel="3", IsExternalFacing=False)
        )
        evidence: dict = {"service_name": "Payments"}
        result = provider.populate(self._resolved(), evidence)

        self.assertEqual(evidence["critical_services"], [])
        self.assertIn("critical_services", result.populated_keys)

    def test_critical_services_unknown_when_k7_fails(self):
        """If k7 returns no rows, critical_services should be unknown."""
        provider = self._make_provider(
            {
                **_SCALAR_ZEROS,
                "GetServicesByName": [],  # No match
            }
        )
        evidence: dict = {"service_name": "Unknown Service"}
        result = provider.populate(
            self._resolved("Unknown Service"), evidence
        )

        self.assertIsNone(evidence.get("critical_services"))
        self.assertIn("critical_services", result.unknown_keys)

    def test_both_external_and_high_level(self):
        """External-facing AND high service level should still produce one entry."""
        provider = self._make_provider(
            self._base_responses(ServiceLevel="1", IsExternalFacing=True)
        )
        evidence: dict = {"service_name": "Payments"}
        provider.populate(self._resolved(), evidence)

        self.assertEqual(evidence["critical_services"], ["Payments"])
        self.assertEqual(len(evidence["critical_services"]), 1)


# =====================================================================
# peer_resource_count (always unknown in Kusto-only mode)
# =====================================================================


class TestPeerResourceCount(unittest.TestCase):
    """peer_resource_count should come from ARG when resource context exists."""

    @staticmethod
    def _resource_ref() -> ResolvedEntityRef:
        rid = (
            "/subscriptions/00000000-0000-0000-0000-000000000123"
            "/resourceGroups/rg-payments/providers/Microsoft.Web/sites/payments-api"
        )
        return ResolvedEntityRef(
            label="AzureResource", resource_id=rid, display_name="payments-api"
        )

    def test_peer_resource_count_from_arg(self):
        provider = KustoEvidenceProvider(
            FakeKustoClient(
                {
                    **_SCALAR_ZEROS,
                    "GetServicesByName": [
                        {
                            "ServiceId": "abc-123",
                            "ServiceName": "Payments",
                            "ServiceLevel": "3",
                            "IsExternalFacing": False,
                        }
                    ],
                    "GetSubscriptionsAssociatedWith": [],
                    "GetServicesMetadataValues": [],
                    "Resources": [{"peer_resource_count": 6}],
                }
            )
        )
        evidence: dict = {"service_name": "Payments"}
        result = provider.populate(self._resource_ref(), evidence)

        # ARG count includes the changed resource itself, provider subtracts 1.
        self.assertEqual(evidence.get("peer_resource_count"), 5)
        self.assertIn("peer_resource_count", result.populated_keys)
        self.assertNotIn("peer_resource_count", result.unknown_keys)

    def test_peer_resource_count_unknown_without_resource_context(self):
        provider = KustoEvidenceProvider(
            FakeKustoClient(
                {
                    **_SCALAR_ZEROS,
                    "GetServicesByName": [
                        {
                            "ServiceId": "abc-123",
                            "ServiceName": "Payments",
                            "ServiceLevel": "3",
                            "IsExternalFacing": False,
                        }
                    ],
                    "GetSubscriptionsAssociatedWith": [],
                    "GetServicesMetadataValues": [],
                }
            )
        )
        evidence: dict = {"service_name": "Payments"}
        resolved = ResolvedEntityRef(
            label="Service", resource_id="Payments", display_name="Payments"
        )
        result = provider.populate(resolved, evidence)

        self.assertIsNone(evidence.get("peer_resource_count"))
        self.assertIn("peer_resource_count", result.unknown_keys)

    def test_peer_resource_count_unknown_on_arg_failure(self):
        provider = KustoEvidenceProvider(
            FakeKustoClient(
                {
                    **_SCALAR_ZEROS,
                    "GetServicesByName": [
                        {
                            "ServiceId": "abc-123",
                            "ServiceName": "Payments",
                            "ServiceLevel": "3",
                            "IsExternalFacing": False,
                        }
                    ],
                    "GetSubscriptionsAssociatedWith": [],
                    "GetServicesMetadataValues": [],
                    "Resources": RuntimeError("arg failed"),
                }
            )
        )
        evidence: dict = {"service_name": "Payments"}
        result = provider.populate(self._resource_ref(), evidence)

        self.assertIsNone(evidence.get("peer_resource_count"))
        self.assertIn("peer_resource_count", result.unknown_keys)


# =====================================================================
# End-to-end: Kusto blast radius → scoring factor integration
# =====================================================================


class TestKustoBlastRadiusScoring(unittest.TestCase):
    """Test that Kusto-derived blast radius evidence flows through scoring."""

    def _score_with_kusto_evidence(
        self,
        services_impacted: int | None = 1,
        critical_services: list[str] | None = None,
        subscription_count: int | None = 5,
        peer_resource_count: int | None = None,
    ) -> dict:
        """Build evidence as the Kusto provider would, run scorer, return factors."""
        if critical_services is None:
            critical_services = []

        evidence = {
            "services_impacted": services_impacted,
            "critical_services": critical_services,
            "subscription_count": subscription_count,
            "peer_resource_count": peer_resource_count,
            "historical_outages_180d": 0,
            "open_icms": 0,
            "deployment_count_30d": 5,
            "deployment_stage_failures": 0,
            "avg_mttm_minutes": 10,
            "related_incidents": 0,
        }
        change = ChangeContext.create(environment="prod")
        result = score_change(change, evidence)
        factors = {f.factor_id: f for f in result.factors}
        return {
            "score": result.risk_score,
            "factors": factors,
            "unknowns": result.unknowns,
        }

    def test_services_impacted_1_scores_5pts(self):
        r = self._score_with_kusto_evidence(services_impacted=1)
        f = r["factors"]["blast_radius.services"]
        self.assertEqual(f.points, 5)
        self.assertEqual(f.status, "hit")

    def test_services_impacted_none_is_unknown(self):
        r = self._score_with_kusto_evidence(services_impacted=None)
        f = r["factors"]["blast_radius.services"]
        self.assertEqual(f.status, "unknown")
        self.assertEqual(f.points, 0)

    def test_critical_service_hits_15pts(self):
        r = self._score_with_kusto_evidence(
            critical_services=["Payments"]
        )
        f = r["factors"]["blast_radius.critical_services"]
        self.assertEqual(f.points, 15)
        self.assertEqual(f.status, "hit")

    def test_empty_critical_services_is_miss(self):
        r = self._score_with_kusto_evidence(critical_services=[])
        f = r["factors"]["blast_radius.critical_services"]
        self.assertEqual(f.points, 0)
        self.assertEqual(f.status, "miss")

    def test_peer_resource_count_none_is_unknown(self):
        """Kusto-only mode: peer_resource_count is always unknown."""
        r = self._score_with_kusto_evidence(peer_resource_count=None)
        f = r["factors"]["resource.peer_impact"]
        self.assertEqual(f.status, "unknown")
        self.assertEqual(f.points, 0)

    def test_subscription_count_flows_through(self):
        r = self._score_with_kusto_evidence(subscription_count=5)
        f = r["factors"]["blast_radius.subscriptions"]
        self.assertEqual(f.points, 7)
        self.assertEqual(f.status, "hit")

    def test_full_kusto_only_score_is_deterministic(self):
        """Same inputs should always produce the same score."""
        r1 = self._score_with_kusto_evidence(
            services_impacted=1,
            critical_services=["Payments"],
            subscription_count=3,
            peer_resource_count=None,
        )
        r2 = self._score_with_kusto_evidence(
            services_impacted=1,
            critical_services=["Payments"],
            subscription_count=3,
            peer_resource_count=None,
        )
        self.assertEqual(r1["score"], r2["score"])

    def test_no_service_all_blast_radius_unknown(self):
        """When services_impacted is None, blast_radius.services is unknown."""
        r = self._score_with_kusto_evidence(
            services_impacted=None,
            critical_services=None,
            subscription_count=None,
            peer_resource_count=None,
        )
        self.assertIn("services_impacted", r["unknowns"])
        self.assertIn("subscription_count", r["unknowns"])
        self.assertIn("peer_resource_count", r["unknowns"])


# =====================================================================
# Provider + Scoring integration (full pipeline)
# =====================================================================


class TestKustoProviderPipeline(unittest.TestCase):
    """Full pipeline: Kusto provider → evidence → scoring."""

    def _resolved(self, name: str = "Payments") -> ResolvedEntityRef:
        return ResolvedEntityRef(
            label="Service", resource_id=name, display_name=name
        )

    def test_critical_external_service_increases_score(self):
        """External-facing service should add critical_services points."""
        provider = KustoEvidenceProvider(
            FakeKustoClient(
                {
                    **_SCALAR_ZEROS,
                    "GetServicesByName": [
                        {
                            "ServiceId": "abc-123",
                            "ServiceName": "Payments",
                            "ServiceLevel": "1",
                            "IsExternalFacing": True,
                        }
                    ],
                    "GetSubscriptionsAssociatedWith": [
                        {
                            "SubscriptionId": "sub-1",
                            "SubscriptionName": "Prod",
                            "Environment": "Production",
                            "Status": 1,
                        },
                        {
                            "SubscriptionId": "sub-2",
                            "SubscriptionName": "Staging",
                            "Environment": "Staging",
                            "Status": 1,
                        },
                    ],
                    "GetServicesMetadataValues": [],
                }
            )
        )

        evidence: dict = {"service_name": "Payments"}
        provider.populate(self._resolved(), evidence)

        # Now score
        change = ChangeContext.create(environment="prod")
        result = score_change(change, evidence)

        factors = {f.factor_id: f for f in result.factors}

        # Blast radius facts from Kusto
        self.assertEqual(
            factors["blast_radius.services"].points, 5
        )  # services_impacted=1
        self.assertEqual(
            factors["blast_radius.critical_services"].points, 15
        )  # critical
        self.assertEqual(
            factors["blast_radius.subscriptions"].points, 4
        )  # 2 subs = 4pts
        self.assertEqual(
            factors["resource.peer_impact"].status, "unknown"
        )  # no ARG

    def test_arg_peer_count_contributes_peer_impact_points(self):
        provider = KustoEvidenceProvider(
            FakeKustoClient(
                {
                    **_SCALAR_ZEROS,
                    "GetServicesByName": [
                        {
                            "ServiceId": "abc-123",
                            "ServiceName": "Payments",
                            "ServiceLevel": "3",
                            "IsExternalFacing": False,
                        }
                    ],
                    "GetSubscriptionsAssociatedWith": [],
                    "GetServicesMetadataValues": [],
                    "Resources": [{"peer_resource_count": 11}],
                }
            )
        )

        resolved = ResolvedEntityRef(
            label="AzureResource",
            resource_id=(
                "/subscriptions/00000000-0000-0000-0000-000000000123"
                "/resourceGroups/rg-payments/providers/Microsoft.Web/sites/payments-api"
            ),
            display_name="payments-api",
        )

        evidence: dict = {"service_name": "Payments"}
        provider.populate(resolved, evidence)

        change = ChangeContext.create(environment="prod")
        result = score_change(change, evidence)
        factors = {f.factor_id: f for f in result.factors}

        self.assertEqual(evidence["peer_resource_count"], 10)
        self.assertEqual(factors["resource.peer_impact"].points, 8)
        self.assertEqual(factors["resource.peer_impact"].status, "hit")

    def test_non_critical_service_no_extra_points(self):
        """Internal, low-level service should NOT add critical points."""
        provider = KustoEvidenceProvider(
            FakeKustoClient(
                {
                    **_SCALAR_ZEROS,
                    "GetServicesByName": [
                        {
                            "ServiceId": "def-456",
                            "ServiceName": "Internal Tools",
                            "ServiceLevel": "4",
                            "IsExternalFacing": False,
                        }
                    ],
                    "GetSubscriptionsAssociatedWith": [],
                    "GetServicesMetadataValues": [],
                }
            )
        )

        evidence: dict = {"service_name": "Internal Tools"}
        provider.populate(self._resolved("Internal Tools"), evidence)

        change = ChangeContext.create(environment="dev")
        result = score_change(change, evidence)

        factors = {f.factor_id: f for f in result.factors}

        # Not prod, not critical
        self.assertEqual(factors["env.production"].points, 0)
        self.assertEqual(
            factors["blast_radius.critical_services"].points, 0
        )
        self.assertEqual(
            factors["blast_radius.critical_services"].status, "miss"
        )


if __name__ == "__main__":
    unittest.main()
