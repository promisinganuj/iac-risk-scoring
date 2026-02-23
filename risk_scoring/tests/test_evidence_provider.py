"""Tests for the pluggable evidence provider architecture.

Covers:
- EvidenceProvider protocol conformance
- run_providers() orchestration and merging
- KustoEvidenceProvider with mocked KustoClient
- Neo4jEvidenceProvider with mocked EvidenceClient
- Error isolation between providers
- Provider ordering (Neo4j first sets service_name for Kusto)
"""

from __future__ import annotations

from datetime import date
from typing import Any, Dict, List, Mapping, Optional
from unittest.mock import MagicMock, patch

import pytest

from risk_scoring.evidence_provider import (
    EvidenceExpansionResult,
    EvidenceProvider,
    ProviderResult,
    run_providers,
)
from risk_scoring.graph_expansion import QueryRun
from risk_scoring.kusto_evidence_provider import KustoEvidenceProvider
from risk_scoring.models import ResolvedEntityRef
from risk_scoring.neo4j_evidence_provider import Neo4jEvidenceProvider


# ============================================================
# Fixtures
# ============================================================


def _resolved(resource_id: str = "res-alpha-app") -> ResolvedEntityRef:
    return ResolvedEntityRef(
        label="AzureResource",
        resource_id=resource_id,
        display_name="Alpha App",
        resource_type="Microsoft.Web/sites",
    )


class StubProvider:
    """Simple stub that sets specific evidence keys."""

    def __init__(
        self,
        name: str,
        keys: Dict[str, Any],
        unknown_keys: tuple[str, ...] = (),
    ) -> None:
        self._name = name
        self._keys = keys
        self._unknown_keys = unknown_keys

    @property
    def name(self) -> str:
        return self._name

    def populate(
        self,
        resolved: ResolvedEntityRef,
        evidence: Dict[str, Any],
        *,
        as_of: Optional[date] = None,
    ) -> ProviderResult:
        populated = []
        for k, v in self._keys.items():
            evidence[k] = v
            populated.append(k)
        return ProviderResult(
            provider_name=self._name,
            queries=(),
            populated_keys=tuple(sorted(populated)),
            unknown_keys=self._unknown_keys,
        )


class FailingProvider:
    """Provider that always raises."""

    @property
    def name(self) -> str:
        return "failing"

    def populate(
        self,
        resolved: ResolvedEntityRef,
        evidence: Dict[str, Any],
        *,
        as_of: Optional[date] = None,
    ) -> ProviderResult:
        raise RuntimeError("provider crashed")


# ============================================================
# EvidenceProvider protocol tests
# ============================================================


class TestProtocolConformance:
    def test_stub_is_evidence_provider(self) -> None:
        p = StubProvider("test", {})
        assert isinstance(p, EvidenceProvider)

    def test_kusto_provider_is_evidence_provider(self) -> None:
        mock_client = MagicMock()
        p = KustoEvidenceProvider(mock_client)
        assert isinstance(p, EvidenceProvider)

    def test_neo4j_provider_is_evidence_provider(self) -> None:
        mock_client = MagicMock()
        p = Neo4jEvidenceProvider(mock_client)
        assert isinstance(p, EvidenceProvider)


# ============================================================
# run_providers() tests
# ============================================================


class TestRunProviders:
    def test_empty_providers(self) -> None:
        result = run_providers([], _resolved())
        assert result.evidence == {}
        assert result.unknowns == ()
        assert result.all_queries == ()

    def test_single_provider(self) -> None:
        p = StubProvider("p1", {"recent_active_outages": 5, "avg_mttm_minutes": 30})
        result = run_providers([p], _resolved())
        assert result.evidence["recent_active_outages"] == 5
        assert result.evidence["avg_mttm_minutes"] == 30
        assert len(result.provider_results) == 1

    def test_multiple_providers_merge(self) -> None:
        p1 = StubProvider("neo4j", {"service_id": "svc-123", "service_name": "Alpha"})
        p2 = StubProvider("kusto", {"recent_active_outages": 3, "avg_mttm_minutes": 45})
        result = run_providers([p1, p2], _resolved())
        assert result.evidence["service_id"] == "svc-123"
        assert result.evidence["recent_active_outages"] == 3

    def test_initial_evidence(self) -> None:
        result = run_providers(
            [],
            _resolved(),
            initial_evidence={"resource_id": "res-alpha-app"},
        )
        assert result.evidence["resource_id"] == "res-alpha-app"

    def test_provider_error_isolated(self) -> None:
        p1 = FailingProvider()
        p2 = StubProvider("ok", {"recent_active_outages": 1})
        result = run_providers([p1, p2], _resolved())
        # Failing provider recorded with error; second still runs.
        assert result.provider_results[0].error is not None
        assert "crashed" in result.provider_results[0].error
        assert result.evidence["recent_active_outages"] == 1

    def test_unknowns_resolved_by_later_provider(self) -> None:
        # First provider marks "recent_active_outages" as unknown.
        p1 = StubProvider("neo4j", {}, unknown_keys=("recent_active_outages",))
        # Second provider actually populates it.
        p2 = StubProvider("kusto", {"recent_active_outages": 7})
        result = run_providers([p1, p2], _resolved())
        # Should NOT be in final unknowns since p2 populated it.
        assert "recent_active_outages" not in result.unknowns
        assert result.evidence["recent_active_outages"] == 7

    def test_unknowns_remain_if_not_populated(self) -> None:
        p = StubProvider("neo4j", {}, unknown_keys=("peer_resource_count",))
        result = run_providers([p], _resolved())
        assert "peer_resource_count" in result.unknowns

    def test_as_of_passed_through(self) -> None:
        calls = []

        class RecordingProvider:
            @property
            def name(self) -> str:
                return "rec"

            def populate(
                self, resolved, evidence, *, as_of=None
            ) -> ProviderResult:
                calls.append(as_of)
                return ProviderResult("rec", (), (), ())

        d = date(2026, 1, 15)
        run_providers([RecordingProvider()], _resolved(), as_of=d)
        assert calls == [d]


# ============================================================
# KustoEvidenceProvider tests
# ============================================================


class TestKustoEvidenceProvider:
    def _mock_client(self, responses: Dict[str, List[Dict[str, Any]]]) -> MagicMock:
        """Create a mock KustoClient that returns pre-set responses by query substring."""
        mock = MagicMock()

        def side_effect(kql: str, database: Optional[str] = None):
            for key, rows in responses.items():
                if key in kql:
                    return rows
            return []

        mock.execute.side_effect = side_effect
        return mock

    def test_all_keys_populated(self) -> None:
        client = self._mock_client({
            "recent_active_outages": [{"recent_active_outages": 3}],
            "avg_mttm_minutes": [{"avg_mttm_minutes": 42}],
            "historical_outages_180d": [{"historical_outages_180d": 2}],
            "related_incidents": [{"related_incidents": 1}],
            "deployment_count_30d": [{"deployment_count_30d": 12}],
            "sev12_incident_count": [{"sev12_incident_count": 2}],
            "GetServicesByName": [{"ServiceId": "abc-123", "ServiceName": "Azure App Service (Payments)"}],
            "GetSubscriptionsAssociatedWith": [{"SubscriptionId": "sub-1", "SubscriptionName": "Prod", "Environment": "Production", "Status": 1}],
            "GetServicesMetadataValues": [{"ServiceId": "abc-123", "ServiceName": "Azure App Service (Payments)", "RepoUrl": "https://github.com/org/repo", "SourceCodeType": "Git"}],
            "safefly_caused_outages_180d": [{"safefly_caused_outages_180d": 1}],
        })
        provider = KustoEvidenceProvider(client)
        evidence: Dict[str, Any] = {"service_name": "Azure App Service (Payments)"}
        result = provider.populate(_resolved(), evidence)

        assert evidence["recent_active_outages"] == 3
        assert evidence["avg_mttm_minutes"] == 42
        assert evidence["historical_outages_180d"] == 2
        assert evidence["related_incidents"] == 1
        assert evidence["deployment_count_30d"] == 12
        assert evidence["sev12_incident_count"] == 2
        assert evidence["service_tree_id"] == "abc-123"
        assert evidence["subscription_count"] == 1
        assert evidence["safefly_caused_outages_180d"] == 1
        assert result.unknown_keys == ("peer_resource_count",)
        assert len(result.populated_keys) == 12

    def test_no_service_name_marks_all_unknown(self) -> None:
        client = MagicMock()
        provider = KustoEvidenceProvider(client)
        evidence: Dict[str, Any] = {}
        result = provider.populate(_resolved(), evidence)

        assert len(result.unknown_keys) == 13
        assert result.populated_keys == ()
        # Client should NOT have been called.
        client.execute.assert_not_called()

    def test_query_failure_marks_key_unknown(self) -> None:
        from risk_scoring.kusto_client import KustoQueryError

        client = MagicMock()
        call_count = 0

        def side_effect(kql, database=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise KustoQueryError("timeout")
            if "GetServicesByName" in kql:
                return [{"ServiceId": "00000000-0000-0000-0000-000000000001", "ServiceName": "Test"}]
            return [{"avg_mttm_minutes": 30}] if "avg_mttm" in kql else []

        client.execute.side_effect = side_effect
        provider = KustoEvidenceProvider(client)
        evidence: Dict[str, Any] = {"service_name": "Azure App Service (Payments)"}
        result = provider.populate(_resolved(), evidence)

        # First query failed, but others should still run.
        assert client.execute.call_count == 10
        assert any(k in result.unknown_keys for k in ["recent_active_outages"])

    def test_empty_result_marks_unknown(self) -> None:
        client = MagicMock()
        client.execute.return_value = []
        provider = KustoEvidenceProvider(client)
        evidence: Dict[str, Any] = {"service_name": "Azure App Service (Payments)"}
        result = provider.populate(_resolved(), evidence)

        # 7 scalar + service_tree_id + subscriptions + repos + peer unknown
        assert len(result.unknown_keys) == 13
        assert len(result.populated_keys) == 0

    def test_provider_name(self) -> None:
        provider = KustoEvidenceProvider(MagicMock())
        assert provider.name == "kusto-icm"

    def test_queries_recorded(self) -> None:
        client = MagicMock()
        client.execute.return_value = [{"recent_active_outages": 5, "ServiceId": "00000000-0000-0000-0000-000000000001"}]
        provider = KustoEvidenceProvider(client)
        evidence: Dict[str, Any] = {"service_name": "Azure App Service (Payments)"}
        result = provider.populate(_resolved(), evidence)

        assert len(result.queries) == 10
        query_ids = [q.query_id for q in result.queries]
        assert "k1.recent_active_outages" in query_ids
        assert "k8.deployment_count_30d" in query_ids
        assert "k14.safefly_caused_outages" in query_ids
        assert "k7.service_tree_lookup" in query_ids


# ============================================================
# Neo4jEvidenceProvider tests
# ============================================================


class TestNeo4jEvidenceProvider:
    def test_delegates_to_expand(self) -> None:
        """Ensure the provider calls expand_evidence_for_resource."""
        from risk_scoring.graph_expansion import GraphExpansionResult

        mock_client = MagicMock()
        mock_expansion = GraphExpansionResult(
            evidence={
                "resource_id": "res-alpha-app",
                "service_id": "svc-123",
            },
            queries=(),
            unknowns=("recent_active_outages",),
        )

        with patch(
            "risk_scoring.neo4j_evidence_provider.expand_evidence_for_resource",
            return_value=mock_expansion,
        ):
            provider = Neo4jEvidenceProvider(mock_client)
            evidence: Dict[str, Any] = {}
            result = provider.populate(_resolved(), evidence)

        assert evidence["service_id"] == "svc-123"
        assert "recent_active_outages" in result.unknown_keys

    def test_error_returns_error_result(self) -> None:
        mock_client = MagicMock()
        with patch(
            "risk_scoring.neo4j_evidence_provider.expand_evidence_for_resource",
            side_effect=ConnectionError("neo4j down"),
        ):
            provider = Neo4jEvidenceProvider(mock_client)
            evidence: Dict[str, Any] = {}
            result = provider.populate(_resolved(), evidence)

        assert result.error is not None
        assert "neo4j down" in result.error

    def test_provider_name(self) -> None:
        provider = Neo4jEvidenceProvider(MagicMock())
        assert provider.name == "neo4j"


# ============================================================
# Integration: provider ordering
# ============================================================


class TestProviderOrdering:
    """Test that Neo4j-first, Kusto-second ordering works correctly."""

    def test_neo4j_sets_service_name_for_kusto(self) -> None:
        """When Neo4j runs first and sets service_name, Kusto can use it."""
        neo4j_provider = StubProvider(
            "neo4j",
            {
                "service_id": "A56C6700-6666-4444-AAAA-000F3B9CC999",
                "service_name": "Azure App Service (Payments)",
            },
        )
        kusto_provider = StubProvider(
            "kusto",
            {"recent_active_outages": 5, "avg_mttm_minutes": 30},
        )
        result = run_providers(
            [neo4j_provider, kusto_provider],
            _resolved(),
        )
        assert result.evidence["service_name"] == "Azure App Service (Payments)"
        assert result.evidence["recent_active_outages"] == 5

    def test_kusto_without_neo4j_no_crash(self) -> None:
        """When Kusto runs alone without service_name, it degrades gracefully."""
        client = MagicMock()
        provider = KustoEvidenceProvider(client)
        result = run_providers([provider], _resolved())

        # All keys should be unknown since there's no service_name.
        assert len(result.unknowns) == 13
        client.execute.assert_not_called()


# ============================================================
# KustoEvidenceProvider with registry
# ============================================================


class TestKustoProviderWithRegistry:
    """Test KustoEvidenceProvider when initialised with a KustoSourceRegistry."""

    def test_accepts_registry(self) -> None:
        from risk_scoring.kusto_source_config import KustoSourceRegistry

        mock_registry = MagicMock(spec=KustoSourceRegistry)
        provider = KustoEvidenceProvider(mock_registry)
        assert provider.name == "kusto-icm"

    def test_registry_queries_use_correct_client(self) -> None:
        from risk_scoring.kusto_source_config import KustoSourceRegistry

        mock_registry = MagicMock(spec=KustoSourceRegistry)
        mock_client = MagicMock()
        mock_client.execute.return_value = [{"recent_active_outages": 7, "ServiceId": "00000000-0000-0000-0000-000000000001"}]
        mock_registry.get_client.return_value = mock_client

        provider = KustoEvidenceProvider(mock_registry)
        evidence: Dict[str, Any] = {"service_name": "TestService"}
        provider.populate(_resolved(), evidence)

        # The provider should have called get_client for each query's source.
        assert mock_registry.get_client.call_count == 10
        # Calls should be for "icm", "safefly", and "service_tree" sources.
        source_names = [call[0][0] for call in mock_registry.get_client.call_args_list]
        assert "icm" in source_names
        assert "safefly" in source_names
        assert "service_tree" in source_names
