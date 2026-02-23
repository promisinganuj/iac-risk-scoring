"""Tests for blast radius via Kusto joins (no Neo4j).

Validates that the Kusto evidence provider correctly populates
blast radius evidence keys (peer_resource_count, subscription_count)
from Service Tree / ARG data.

Model v0.2: removed services_impacted and critical_services factors.
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
# Helper: standard responses for scalar queries
# =====================================================================

_SCALAR_ZEROS: dict[str, list[dict]] = {
    "OwningTenantName": [{"recent_active_outages": 0}],
    "IsOutage": [{"historical_outages_180d": 0}],
    "ParentIncidentId": [{"related_incidents": 0}],
    "SafeFlyRequestCurrentMV": [{"deployment_count_30d": 0}],
}


# =====================================================================
# peer_resource_count (from ARG when resource context exists)
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
        subscription_count: int | None = 5,
        peer_resource_count: int | None = None,
    ) -> dict:
        """Build evidence as the Kusto provider would, run scorer, return factors."""
        evidence = {
            "subscription_count": subscription_count,
            "peer_resource_count": peer_resource_count,
            "historical_outages_180d": 0,
            "recent_active_outages": 0,
            "deployment_count_30d": 5,
            "avg_mttm_minutes": 10,
            "related_incidents": 0,
            "safefly_caused_outages_180d": 0,
            "sev12_incident_count": 0,
        }
        change = ChangeContext.create(environment="prod")
        result = score_change(change, evidence)
        factors = {f.factor_id: f for f in result.factors}
        return {
            "score": result.risk_score,
            "factors": factors,
            "unknowns": result.unknowns,
        }

    def test_peer_resource_count_none_is_unknown(self):
        """Kusto-only mode: peer_resource_count is always unknown without ARG."""
        r = self._score_with_kusto_evidence(peer_resource_count=None)
        f = r["factors"]["resource.peer_impact"]
        self.assertEqual(f.status, "unknown")
        self.assertEqual(f.points, 0)

    def test_subscription_count_flows_through(self):
        r = self._score_with_kusto_evidence(subscription_count=5)
        f = r["factors"]["blast_radius.subscriptions"]
        self.assertEqual(f.points, 8)
        self.assertEqual(f.status, "hit")

    def test_subscription_count_10_plus_max(self):
        r = self._score_with_kusto_evidence(subscription_count=10)
        f = r["factors"]["blast_radius.subscriptions"]
        self.assertEqual(f.points, 12)
        self.assertEqual(f.status, "hit")

    def test_subscription_count_2_subs(self):
        r = self._score_with_kusto_evidence(subscription_count=2)
        f = r["factors"]["blast_radius.subscriptions"]
        self.assertEqual(f.points, 5)

    def test_subscription_count_1_sub(self):
        r = self._score_with_kusto_evidence(subscription_count=1)
        f = r["factors"]["blast_radius.subscriptions"]
        self.assertEqual(f.points, 2)

    def test_full_kusto_only_score_is_deterministic(self):
        """Same inputs should always produce the same score."""
        r1 = self._score_with_kusto_evidence(
            subscription_count=3,
            peer_resource_count=None,
        )
        r2 = self._score_with_kusto_evidence(
            subscription_count=3,
            peer_resource_count=None,
        )
        self.assertEqual(r1["score"], r2["score"])

    def test_no_service_all_blast_radius_unknown(self):
        """When subscription_count is None, blast_radius.subscriptions is unknown."""
        r = self._score_with_kusto_evidence(
            subscription_count=None,
            peer_resource_count=None,
        )
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

    def test_subscription_count_contributes_to_score(self):
        """Two prod subscriptions should score blast_radius.subscriptions."""
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

        # 1 prod sub → 2 pts
        self.assertEqual(
            factors["blast_radius.subscriptions"].points, 2
        )
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

    def test_non_critical_service_minimal_score(self):
        """Internal, low-level service with zero evidence should have a low score."""
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

        # No subs, no outages, no incidents → minimal score
        self.assertEqual(
            factors["blast_radius.subscriptions"].points, 0
        )
        self.assertEqual(
            factors["blast_radius.subscriptions"].status, "miss"
        )


if __name__ == "__main__":
    unittest.main()
