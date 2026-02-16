"""Tests for service → subscription mapping (k10) and blast_radius.subscriptions scoring."""

from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock

from risk_scoring.evidence_allowlist import ParamSpec
from risk_scoring.kusto_allowlist import (
    KQL_ALLOWLIST,
    KqlQuerySpec,
    build_kql,
    get_kql_query,
    validate_kql_params,
)
from risk_scoring.kusto_evidence_provider import KustoEvidenceProvider
from risk_scoring.models import ResolvedEntityRef
from risk_scoring.scoring import ChangeContext, score_change


# =====================================================================
# k10 KQL allowlist tests
# =====================================================================


class TestK10Allowlist(unittest.TestCase):
    """Tests for the k10.service_subscriptions KQL query spec."""

    def test_k10_registered_in_allowlist(self):
        assert "k10.service_subscriptions" in KQL_ALLOWLIST

    def test_k10_spec_shape(self):
        spec = get_kql_query("k10.service_subscriptions")
        assert spec.query_id == "k10.service_subscriptions"
        assert spec.source == "service_tree"
        assert spec.evidence_key == "service_subscriptions"
        assert spec.max_take == 500
        assert spec.default_take == 200

    def test_k10_requires_service_id(self):
        spec = get_kql_query("k10.service_subscriptions")
        param_names = [p.name for p in spec.params]
        assert "serviceId" in param_names

    def test_k10_builds_valid_kql(self):
        spec = get_kql_query("k10.service_subscriptions")
        validated = validate_kql_params(
            spec, {"serviceId": "092c677a-6386-4fa8-a485-991d3f9aa010"}
        )
        kql = build_kql(spec, validated)
        assert "GetSubscriptionsAssociatedWith" in kql
        assert "092c677a-6386-4fa8-a485-991d3f9aa010" in kql
        assert "SubscriptionId" in kql
        assert "take" in kql

    def test_k10_rejects_unsafe_service_id(self):
        """Service IDs with injection chars should be rejected."""
        from risk_scoring.evidence_allowlist import ParameterValidationError

        spec = get_kql_query("k10.service_subscriptions")
        validated = validate_kql_params(
            spec, {"serviceId": "evil'; drop table --"}
        )
        with self.assertRaises(ParameterValidationError):
            build_kql(spec, validated)


# =====================================================================
# k7 service tree lookup tests (already in allowlist, now wired)
# =====================================================================


class TestK7Wired(unittest.TestCase):
    """Test that k7.service_tree_lookup is in the allowlist."""

    def test_k7_registered(self):
        assert "k7.service_tree_lookup" in KQL_ALLOWLIST

    def test_k7_builds_kql(self):
        spec = get_kql_query("k7.service_tree_lookup")
        validated = validate_kql_params(spec, {"serviceName": "My Service"})
        kql = build_kql(spec, validated)
        assert "GetServicesByName" in kql
        assert "'My Service'" in kql


# =====================================================================
# Evidence provider integration tests (mock Kusto client)
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
                return rows
        return []


class TestProviderSubscriptions(unittest.TestCase):
    """Test that the provider populates subscription evidence."""

    def _make_provider(self, responses: dict[str, list[dict]]) -> KustoEvidenceProvider:
        client = FakeKustoClient(responses)
        return KustoEvidenceProvider(client)

    def _resolved(self, name: str = "Test Service") -> ResolvedEntityRef:
        return ResolvedEntityRef(
            label="Service", resource_id=name, display_name=name
        )

    def test_populates_subscription_count(self):
        provider = self._make_provider(
            {
                # k1-k9 scalar queries return 0
                "OwningTenantName": [{"open_icms": 0}],
                "IsOutage": [{"historical_outages_180d": 0}],
                "ParentIncidentId": [{"related_incidents": 0}],
                "SafeFlyRequestCurrentMV": [{"deployment_count_30d": 0}],
                # k7 service tree lookup
                "GetServicesByName": [
                    {"ServiceId": "abc-123", "ServiceName": "Test Service"}
                ],
                # k10 subscriptions
                "GetSubscriptionsAssociatedWith": [
                    {
                        "SubscriptionId": "sub-1",
                        "SubscriptionName": "Prod Sub",
                        "Environment": "Production",
                        "Status": 1,
                    },
                    {
                        "SubscriptionId": "sub-2",
                        "SubscriptionName": "Dev Sub",
                        "Environment": "Development",
                        "Status": 1,
                    },
                ],
            }
        )

        evidence: dict = {"service_name": "Test Service"}
        result = provider.populate(self._resolved(), evidence)

        assert evidence["subscription_count"] == 2
        assert len(evidence["service_subscriptions"]) == 2
        assert evidence["service_subscriptions"][0]["subscription_id"] == "sub-1"
        assert "subscription_count" in result.populated_keys

    def test_no_service_id_marks_subscriptions_unknown(self):
        """If k7 returns nothing, subscriptions should be unknown."""
        provider = self._make_provider(
            {
                "OwningTenantName": [{"open_icms": 0}],
                "IsOutage": [{"historical_outages_180d": 0}],
                "ParentIncidentId": [{"related_incidents": 0}],
                "SafeFlyRequestCurrentMV": [{"deployment_count_30d": 0}],
                "GetServicesByName": [],  # no match
            }
        )

        evidence: dict = {"service_name": "Unknown Service"}
        result = provider.populate(self._resolved("Unknown Service"), evidence)

        assert evidence.get("subscription_count") is None
        assert "subscription_count" in result.unknown_keys
        assert "service_subscriptions" in result.unknown_keys

    def test_no_service_name_marks_all_unknown(self):
        """If no service_name in evidence, all keys are unknown."""
        provider = self._make_provider({})
        evidence: dict = {}
        result = provider.populate(self._resolved(), evidence)

        assert "subscription_count" in result.unknown_keys
        assert "service_subscriptions" in result.unknown_keys
        assert "service_tree_id" in result.unknown_keys

    def test_service_tree_id_populated(self):
        """k7 should populate service_tree_id."""
        provider = self._make_provider(
            {
                "OwningTenantName": [{"open_icms": 0}],
                "IsOutage": [{"historical_outages_180d": 0}],
                "ParentIncidentId": [{"related_incidents": 0}],
                "SafeFlyRequestCurrentMV": [{"deployment_count_30d": 0}],
                "GetServicesByName": [
                    {"ServiceId": "abc-123", "ServiceName": "Test Service"}
                ],
                "GetSubscriptionsAssociatedWith": [],
            }
        )

        evidence: dict = {"service_name": "Test Service"}
        result = provider.populate(self._resolved(), evidence)

        assert evidence["service_tree_id"] == "abc-123"
        assert "service_tree_id" in result.populated_keys


# =====================================================================
# Scoring factor: blast_radius.subscriptions
# =====================================================================


class TestSubscriptionCountScoring(unittest.TestCase):
    """Test the blast_radius.subscriptions scoring factor."""

    def _score_with_subscriptions(self, count: int | None) -> dict:
        """Run scorer with subscription_count set and return factor dict."""
        evidence = {
            "services_impacted": 1,
            "critical_services": [],
            "subscription_count": count,
            "historical_outages_180d": 0,
            "open_icms": 0,
            "deployment_count_30d": 5,
            "deployment_stage_failures": 0,
            "avg_mttm_minutes": 30,
            "related_incidents": 0,
            "change_frequency_30d": 5,
            "template_complexity": "low",
        }
        change = ChangeContext.create(environment="prod")
        result = score_change(change, evidence)
        # Find the subscription factor
        for f in result.factors:
            if f.factor_id == "blast_radius.subscriptions":
                return {"points": f.points, "max": f.max_points, "status": f.status}
        return {"points": None, "max": None, "status": "not_found"}

    def test_10_plus_subs_max_points(self):
        r = self._score_with_subscriptions(10)
        assert r["points"] == 10
        assert r["status"] == "hit"

    def test_5_subs(self):
        r = self._score_with_subscriptions(5)
        assert r["points"] == 7

    def test_2_subs(self):
        r = self._score_with_subscriptions(2)
        assert r["points"] == 4

    def test_1_sub(self):
        r = self._score_with_subscriptions(1)
        assert r["points"] == 2

    def test_0_subs(self):
        r = self._score_with_subscriptions(0)
        assert r["points"] == 0
        assert r["status"] == "miss"

    def test_none_is_unknown(self):
        r = self._score_with_subscriptions(None)
        assert r["status"] == "unknown"
        assert r["points"] == 0

    def test_20_subs_caps_at_10(self):
        r = self._score_with_subscriptions(20)
        assert r["points"] == 10


if __name__ == "__main__":
    unittest.main()
