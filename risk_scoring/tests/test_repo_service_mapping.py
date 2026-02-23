"""Tests for repo → service mapping (k11, k12, normalize_repo_url).

Covers:
- URL normalization for deterministic comparison
- k11 reverse query spec (repo → ServiceId)
- k12 forward query spec (ServiceId → repos)
- KustoSourceRegistry.resolve_service_from_repo()
- KustoEvidenceProvider Phase 4 (service repos enrichment)
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from risk_scoring.evidence_allowlist import ParameterValidationError
from risk_scoring.kusto_allowlist import (
    KQL_ALLOWLIST,
    build_kql,
    get_kql_query,
    validate_kql_params,
)
from risk_scoring.kusto_source_config import (
    KustoSourceRegistry,
    normalize_repo_url,
)


# ============================================================
# normalize_repo_url
# ============================================================


class TestNormalizeRepoUrl:
    def test_strips_trailing_slash(self) -> None:
        assert normalize_repo_url("https://github.com/Org/Repo/") == (
            "https://github.com/org/repo"
        )

    def test_strips_dot_git(self) -> None:
        assert normalize_repo_url("https://github.com/Azure/my-repo.git") == (
            "https://github.com/azure/my-repo"
        )

    def test_lowercases(self) -> None:
        assert normalize_repo_url("https://dev.azure.com/msazure/One/_git/MyRepo") == (
            "https://dev.azure.com/msazure/one/_git/myrepo"
        )

    def test_strips_whitespace(self) -> None:
        assert normalize_repo_url("  https://github.com/Org/Repo  ") == (
            "https://github.com/org/repo"
        )

    def test_combined_normalization(self) -> None:
        url = "  https://dev.azure.com/msazure/One/_git/AzureCliTools.git/ "
        assert normalize_repo_url(url) == (
            "https://dev.azure.com/msazure/one/_git/azureclitools"
        )

    def test_already_normalized(self) -> None:
        url = "https://github.com/azure/repo"
        assert normalize_repo_url(url) == url

    def test_empty_string(self) -> None:
        assert normalize_repo_url("") == ""

    def test_whitespace_only(self) -> None:
        assert normalize_repo_url("   ") == ""


# ============================================================
# k11.repo_to_service query spec
# ============================================================


class TestK11QuerySpec:
    def test_query_registered(self) -> None:
        q = get_kql_query("k11.repo_to_service")
        assert q.query_id == "k11.repo_to_service"
        assert q.source == "service_tree"
        assert q.evidence_key == "repo_service_mapping"

    def test_valid_repo_url_param(self) -> None:
        q = get_kql_query("k11.repo_to_service")
        result = validate_kql_params(
            q, {"repoUrl": "https://dev.azure.com/msazure/One/_git/MyRepo"}
        )
        assert result["repoUrl"] == "https://dev.azure.com/msazure/One/_git/MyRepo"
        assert result["take"] == q.default_take

    def test_missing_repo_url_raises(self) -> None:
        q = get_kql_query("k11.repo_to_service")
        with pytest.raises(ParameterValidationError, match="Missing required"):
            validate_kql_params(q, {})

    def test_empty_repo_url_raises(self) -> None:
        q = get_kql_query("k11.repo_to_service")
        with pytest.raises(ParameterValidationError, match="non-empty"):
            validate_kql_params(q, {"repoUrl": ""})

    def test_build_kql_substitutes_repo_url(self) -> None:
        q = get_kql_query("k11.repo_to_service")
        params = validate_kql_params(
            q, {"repoUrl": "https://github.com/azure/my-repo"}
        )
        kql = build_kql(q, params)
        assert "'https://github.com/azure/my-repo'" in kql
        assert "ProdCat_SourceCodeLocation" in kql
        assert "ServiceTree_ServiceMetadata_Snapshot" in kql
        assert "take 5" in kql  # default_take

    def test_kql_contains_reverse_lookup_pattern(self) -> None:
        q = get_kql_query("k11.repo_to_service")
        params = validate_kql_params(
            q, {"repoUrl": "https://github.com/org/repo"}
        )
        kql = build_kql(q, params)
        # Must join metadata back to hierarchy
        assert "ServiceTree_ServiceHierarchy_Snapshot" in kql
        assert "MetadataDefinition" in kql
        assert "ParsedValue.RepoUrl" in kql


# ============================================================
# k12.service_repos query spec
# ============================================================


class TestK12QuerySpec:
    def test_query_registered(self) -> None:
        q = get_kql_query("k12.service_repos")
        assert q.query_id == "k12.service_repos"
        assert q.source == "service_tree"
        assert q.evidence_key == "source_repos"

    def test_valid_service_id_param(self) -> None:
        q = get_kql_query("k12.service_repos")
        result = validate_kql_params(
            q, {"serviceId": "00000000-0000-0000-0000-000000000001"}
        )
        assert result["serviceId"] == "00000000-0000-0000-0000-000000000001"

    def test_build_kql_uses_metadata_function(self) -> None:
        q = get_kql_query("k12.service_repos")
        params = validate_kql_params(
            q, {"serviceId": "00000000-0000-0000-0000-000000000001"}
        )
        kql = build_kql(q, params)
        assert "GetServicesMetadataValues" in kql
        assert "ProdCat_SourceCodeLocation" in kql
        assert "RepoUrl" in kql
        assert "SourceCodeType" in kql


# ============================================================
# KustoSourceRegistry.resolve_service_from_repo
# ============================================================


class TestResolveServiceFromRepo:
    def _make_registry(self, mock_execute_return: List[Dict[str, Any]]) -> KustoSourceRegistry:
        """Create a registry with a mocked client."""
        reg = KustoSourceRegistry(
            sources={
                "service_tree": MagicMock(
                    name="service_tree",
                    cluster="https://st.kusto.windows.net",
                    database="Shared",
                ),
            },
        )
        mock_client = MagicMock()
        mock_client.execute.return_value = mock_execute_return
        reg._clients["service_tree"] = mock_client
        return reg

    def test_single_match(self) -> None:
        reg = self._make_registry([
            {"ServiceId": "abc-123", "ServiceName": "My Service"},
        ])
        result = reg.resolve_service_from_repo(
            "https://dev.azure.com/msazure/One/_git/MyRepo"
        )
        assert result == "My Service"

    def test_no_match_returns_none(self) -> None:
        reg = self._make_registry([])
        result = reg.resolve_service_from_repo(
            "https://github.com/org/unknown-repo"
        )
        assert result is None

    def test_multiple_matches_returns_first(self) -> None:
        reg = self._make_registry([
            {"ServiceId": "abc-123", "ServiceName": "Service A"},
            {"ServiceId": "def-456", "ServiceName": "Service B"},
        ])
        result = reg.resolve_service_from_repo(
            "https://github.com/org/shared-repo"
        )
        assert result == "Service A"

    def test_empty_url_returns_none(self) -> None:
        reg = self._make_registry([])
        result = reg.resolve_service_from_repo("")
        assert result is None

    def test_query_error_returns_none(self) -> None:
        reg = KustoSourceRegistry(
            sources={
                "service_tree": MagicMock(
                    name="service_tree",
                    cluster="https://st.kusto.windows.net",
                    database="Shared",
                ),
            },
        )
        mock_client = MagicMock()
        mock_client.execute.side_effect = Exception("connection failed")
        reg._clients["service_tree"] = mock_client
        result = reg.resolve_service_from_repo(
            "https://github.com/org/repo"
        )
        assert result is None

    def test_normalizes_url_before_query(self) -> None:
        reg = self._make_registry([
            {"ServiceId": "abc-123", "ServiceName": "My Service"},
        ])
        mock_client = reg._clients["service_tree"]

        reg.resolve_service_from_repo(
            "https://dev.azure.com/msazure/One/_git/MyRepo.git/"
        )

        # Verify the executed KQL contains normalized (lowercased) URL
        call_args = mock_client.execute.call_args
        kql = call_args[0][0]
        assert "https://dev.azure.com/msazure/one/_git/myrepo" in kql


# ============================================================
# KustoEvidenceProvider Phase 4 tests
# ============================================================


class TestPhase4ServiceRepos:
    """Test the _resolve_service_repos method added in Phase 4."""

    def _mock_client(self, responses: Dict[str, List[Dict[str, Any]]]) -> MagicMock:
        mock = MagicMock()

        def side_effect(kql: str, database: Optional[str] = None):
            for key, rows in responses.items():
                if key in kql:
                    return rows
            return []

        mock.execute.side_effect = side_effect
        return mock

    def _resolved(self) -> "ResolvedEntityRef":
        from risk_scoring.models import ResolvedEntityRef
        return ResolvedEntityRef(
            label="AzureResource",
            resource_id="res-alpha-app",
            display_name="Alpha App",
        )

    def test_repos_populated_when_service_id_available(self) -> None:
        from risk_scoring.kusto_evidence_provider import KustoEvidenceProvider

        client = self._mock_client({
            "recent_active_outages": [{"recent_active_outages": 3}],
            "avg_mttm_minutes": [{"avg_mttm_minutes": 42}],
            "historical_outages_180d": [{"historical_outages_180d": 2}],
            "related_incidents": [{"related_incidents": 1}],
            "deployment_count_30d": [{"deployment_count_30d": 12}],
            "deployment_stage_failures": [{"deployment_stage_failures": 3}],
            "GetServicesByName": [
                {"ServiceId": "00000000-0000-0000-0000-000000000001",
                 "ServiceName": "Test Service"}
            ],
            "GetSubscriptionsAssociatedWith": [
                {"SubscriptionId": "sub-1", "SubscriptionName": "Prod",
                 "Environment": "Production", "Status": 1}
            ],
            "GetServicesMetadataValues": [
                {"ServiceId": "00000000-0000-0000-0000-000000000001",
                 "ServiceName": "Test Service",
                 "RepoUrl": "https://dev.azure.com/msazure/One/_git/MyRepo",
                 "SourceCodeType": "Git"},
                {"ServiceId": "00000000-0000-0000-0000-000000000001",
                 "ServiceName": "Test Service",
                 "RepoUrl": "https://github.com/Azure/other-repo",
                 "SourceCodeType": "Git"},
            ],
        })
        provider = KustoEvidenceProvider(client)
        evidence: Dict[str, Any] = {"service_name": "Test Service"}
        result = provider.populate(self._resolved(), evidence)

        assert evidence["source_repos"] is not None
        assert len(evidence["source_repos"]) == 2
        assert evidence["repo_count"] == 2
        assert evidence["source_repos"][0]["repo_url"] == (
            "https://dev.azure.com/msazure/One/_git/MyRepo"
        )
        assert "source_repos" in result.populated_keys
        assert "repo_count" in result.populated_keys

    def test_repos_unknown_when_no_service_id(self) -> None:
        from risk_scoring.kusto_evidence_provider import KustoEvidenceProvider

        client = self._mock_client({
            "recent_active_outages": [{"recent_active_outages": 3}],
            "avg_mttm_minutes": [{"avg_mttm_minutes": 42}],
            "historical_outages_180d": [{"historical_outages_180d": 2}],
            "related_incidents": [{"related_incidents": 1}],
            "deployment_count_30d": [{"deployment_count_30d": 12}],
            "deployment_stage_failures": [{"deployment_stage_failures": 3}],
            "GetServicesByName": [],  # no service found
        })
        provider = KustoEvidenceProvider(client)
        evidence: Dict[str, Any] = {"service_name": "Unknown Service"}
        result = provider.populate(self._resolved(), evidence)

        assert evidence.get("source_repos") is None
        assert evidence.get("repo_count") is None
        assert "source_repos" in result.unknown_keys
        assert "repo_count" in result.unknown_keys

    def test_repos_empty_list_when_none_registered(self) -> None:
        from risk_scoring.kusto_evidence_provider import KustoEvidenceProvider

        client = self._mock_client({
            "recent_active_outages": [{"recent_active_outages": 3}],
            "avg_mttm_minutes": [{"avg_mttm_minutes": 42}],
            "historical_outages_180d": [{"historical_outages_180d": 2}],
            "related_incidents": [{"related_incidents": 1}],
            "deployment_count_30d": [{"deployment_count_30d": 12}],
            "deployment_stage_failures": [{"deployment_stage_failures": 3}],
            "GetServicesByName": [
                {"ServiceId": "00000000-0000-0000-0000-000000000001",
                 "ServiceName": "Test Service"}
            ],
            "GetSubscriptionsAssociatedWith": [],
            "GetServicesMetadataValues": [],  # no repos registered
        })
        provider = KustoEvidenceProvider(client)
        evidence: Dict[str, Any] = {"service_name": "Test Service"}
        result = provider.populate(self._resolved(), evidence)

        assert evidence["source_repos"] == []
        assert evidence["repo_count"] == 0
        assert "source_repos" in result.populated_keys
        assert "repo_count" in result.populated_keys

    def test_no_service_name_marks_all_unknown_including_repos(self) -> None:
        from risk_scoring.kusto_evidence_provider import KustoEvidenceProvider

        provider = KustoEvidenceProvider(MagicMock())
        evidence: Dict[str, Any] = {}
        result = provider.populate(self._resolved(), evidence)

        assert "source_repos" in result.unknown_keys
        assert "repo_count" in result.unknown_keys
        assert len(result.unknown_keys) == 13  # 7 scalar + service_tree_id + subs(2) + repos(2) + peer_resource_count
