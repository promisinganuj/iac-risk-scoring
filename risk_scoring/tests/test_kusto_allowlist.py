"""Tests for risk_scoring.kusto_allowlist."""

from __future__ import annotations

import pytest

from risk_scoring.evidence_allowlist import ParameterValidationError, UnknownQueryError
from risk_scoring.kusto_allowlist import (
    KQL_ALLOWLIST,
    KqlQuerySpec,
    build_kql,
    get_kql_query,
    validate_kql_params,
)


# A valid service name for testing (matches IcM OwningTenantName).
_VALID_SERVICE_NAME = "Azure App Service (Payments)"
_VALID_SUBSCRIPTION_ID = "00000000-0000-0000-0000-000000000123"
_VALID_RESOURCE_GROUP = "rg-payments-prod"


# ============================================================
# get_kql_query
# ============================================================


class TestGetKqlQuery:
    def test_known_query(self) -> None:
        q = get_kql_query("k1.recent_active_outages")
        assert isinstance(q, KqlQuerySpec)
        assert q.query_id == "k1.recent_active_outages"

    def test_unknown_query_raises(self) -> None:
        with pytest.raises(UnknownQueryError, match="not allowlisted"):
            get_kql_query("k99.does_not_exist")

    def test_all_registered_queries_retrievable(self) -> None:
        for qid in KQL_ALLOWLIST:
            q = get_kql_query(qid)
            assert q.query_id == qid


# ============================================================
# validate_kql_params
# ============================================================


class TestValidateKqlParams:
    def test_valid_service_name(self) -> None:
        q = get_kql_query("k1.recent_active_outages")
        result = validate_kql_params(q, {"serviceName": _VALID_SERVICE_NAME})
        assert result["serviceName"] == _VALID_SERVICE_NAME
        assert result["take"] == q.default_take

    def test_missing_required_service_name(self) -> None:
        q = get_kql_query("k1.recent_active_outages")
        with pytest.raises(ParameterValidationError, match="Missing required"):
            validate_kql_params(q, {})

    def test_empty_service_name(self) -> None:
        q = get_kql_query("k1.recent_active_outages")
        with pytest.raises(ParameterValidationError, match="non-empty"):
            validate_kql_params(q, {"serviceName": ""})

    def test_service_name_too_long(self) -> None:
        q = get_kql_query("k1.recent_active_outages")
        with pytest.raises(ParameterValidationError, match="max_len"):
            validate_kql_params(q, {"serviceName": "a" * 257})

    def test_service_name_must_be_string(self) -> None:
        q = get_kql_query("k1.recent_active_outages")
        with pytest.raises(ParameterValidationError, match="must be a string"):
            validate_kql_params(q, {"serviceName": 12345})

    def test_valid_arg_params(self) -> None:
        q = get_kql_query("k13.arg_peer_resources")
        result = validate_kql_params(
            q,
            {
                "subscriptionId": _VALID_SUBSCRIPTION_ID,
                "resourceGroupName": _VALID_RESOURCE_GROUP,
            },
        )
        assert result["subscriptionId"] == _VALID_SUBSCRIPTION_ID
        assert result["resourceGroupName"] == _VALID_RESOURCE_GROUP
        assert result["take"] == 1


class TestTakeValidation:
    def test_default_take(self) -> None:
        q = get_kql_query("k1.recent_active_outages")
        result = validate_kql_params(q, {"serviceName": _VALID_SERVICE_NAME})
        assert result["take"] == 1  # k1 default_take=1

    def test_explicit_take(self) -> None:
        q = get_kql_query("k1.recent_active_outages")
        result = validate_kql_params(q, {"serviceName": _VALID_SERVICE_NAME, "take": 1})
        assert result["take"] == 1

    def test_take_exceeds_max(self) -> None:
        q = get_kql_query("k1.recent_active_outages")
        with pytest.raises(ParameterValidationError, match="max_take"):
            validate_kql_params(q, {"serviceName": _VALID_SERVICE_NAME, "take": 100})

    def test_take_zero(self) -> None:
        q = get_kql_query("k1.recent_active_outages")
        with pytest.raises(ParameterValidationError, match="must be > 0"):
            validate_kql_params(q, {"serviceName": _VALID_SERVICE_NAME, "take": 0})

    def test_take_negative(self) -> None:
        q = get_kql_query("k1.recent_active_outages")
        with pytest.raises(ParameterValidationError, match="must be > 0"):
            validate_kql_params(q, {"serviceName": _VALID_SERVICE_NAME, "take": -1})

    def test_take_not_int(self) -> None:
        q = get_kql_query("k1.recent_active_outages")
        with pytest.raises(ParameterValidationError, match="must be an int"):
            validate_kql_params(q, {"serviceName": _VALID_SERVICE_NAME, "take": "5"})


# ============================================================
# build_kql
# ============================================================


class TestBuildKql:
    def test_k1_recent_active_outages(self) -> None:
        q = get_kql_query("k1.recent_active_outages")
        params = validate_kql_params(q, {"serviceName": _VALID_SERVICE_NAME})
        kql = build_kql(q, params)
        # Should contain the service name single-quoted
        assert f"OwningTenantName == '{_VALID_SERVICE_NAME}'" in kql
        assert "CreateDate >= ago(7d)" in kql
        assert 'Status == "ACTIVE"' in kql
        assert "IsOutage == true" in kql
        assert "recent_active_outages = count()" in kql
        assert "take 1" in kql

    def test_k4_avg_mttm(self) -> None:
        q = get_kql_query("k4.avg_mttm")
        params = validate_kql_params(q, {"serviceName": _VALID_SERVICE_NAME})
        kql = build_kql(q, params)
        assert "avg_mttm_minutes" in kql
        assert "datetime_diff" in kql
        assert "ImpactStartDate" in kql
        assert "MitigateDate" in kql
        assert "ago(180d)" in kql

    def test_k5_outages_180d(self) -> None:
        q = get_kql_query("k5.outages_180d")
        params = validate_kql_params(q, {"serviceName": _VALID_SERVICE_NAME})
        kql = build_kql(q, params)
        assert "IsOutage == true" in kql
        assert "ago(180d)" in kql
        assert "historical_outages_180d = count()" in kql

    def test_k6_related_incidents(self) -> None:
        q = get_kql_query("k6.related_incidents")
        params = validate_kql_params(q, {"serviceName": _VALID_SERVICE_NAME})
        kql = build_kql(q, params)
        assert "ParentIncidentId" in kql
        assert "dcount" in kql
        assert "ago(90d)" in kql

    def test_k7_service_tree_lookup(self) -> None:
        q = get_kql_query("k7.service_tree_lookup")
        params = validate_kql_params(q, {"serviceName": _VALID_SERVICE_NAME})
        kql = build_kql(q, params)
        assert "GetServicesByName" in kql
        assert f"'{_VALID_SERVICE_NAME}'" in kql
        assert "ServiceId" in kql

    def test_k8_deployment_count_30d(self) -> None:
        q = get_kql_query("k8.deployment_count_30d")
        assert q.source == "safefly"
        params = validate_kql_params(q, {"serviceName": _VALID_SERVICE_NAME})
        kql = build_kql(q, params)
        assert "SafeFlyRequestCurrentMV" in kql
        assert "ServiceName ==" in kql
        assert "ago(30d)" in kql
        assert "deployment_count_30d = count()" in kql

    def test_k9_deployment_failures(self) -> None:
        q = get_kql_query("k9.deployment_failures")
        assert q.source == "safefly"
        params = validate_kql_params(q, {"serviceName": _VALID_SERVICE_NAME})
        kql = build_kql(q, params)
        assert "SafeFlyRequestCurrentMV" in kql
        assert "ago(90d)" in kql
        assert "'Abandoned', 'Rejected'" in kql
        assert "deployment_stage_failures = count()" in kql

    def test_k13_arg_peer_resources(self) -> None:
        q = get_kql_query("k13.arg_peer_resources")
        assert q.source == "arg"
        params = validate_kql_params(
            q,
            {
                "subscriptionId": _VALID_SUBSCRIPTION_ID,
                "resourceGroupName": _VALID_RESOURCE_GROUP,
            },
        )
        kql = build_kql(q, params)
        assert "Resources" in kql
        assert f"subscriptionId =~ '{_VALID_SUBSCRIPTION_ID}'" in kql
        assert f"resourceGroup =~ '{_VALID_RESOURCE_GROUP}'" in kql
        assert "peer_resource_count = count()" in kql

    def test_unsafe_characters_rejected(self) -> None:
        q = get_kql_query("k1.recent_active_outages")
        # Inject a serviceName with KQL injection attempt
        params = {"serviceName": "abc'); .drop table X; //", "take": 1}
        with pytest.raises(ParameterValidationError):
            validated = validate_kql_params(q, params)
            build_kql(q, validated)

    def test_quote_injection_rejected(self) -> None:
        q = get_kql_query("k1.recent_active_outages")
        # Double-quote in name should be rejected
        params = {"serviceName": 'My Service" | drop', "take": 1}
        with pytest.raises(ParameterValidationError):
            validated = validate_kql_params(q, params)
            build_kql(q, validated)

    def test_semicolon_injection_rejected(self) -> None:
        q = get_kql_query("k1.recent_active_outages")
        params = {"serviceName": "Service; .drop table X", "take": 1}
        with pytest.raises(ParameterValidationError):
            validated = validate_kql_params(q, params)
            build_kql(q, validated)

    def test_valid_service_name_with_special_chars(self) -> None:
        """Service names like 'Azure App Service (Payments)' should pass."""
        q = get_kql_query("k1.recent_active_outages")
        params = validate_kql_params(q, {"serviceName": "Azure App Service (Payments)"})
        kql = build_kql(q, params)
        assert "OwningTenantName == 'Azure App Service (Payments)'" in kql

    def test_valid_service_name_with_ampersand(self) -> None:
        q = get_kql_query("k1.recent_active_outages")
        params = validate_kql_params(q, {"serviceName": "R&D Platform"})
        kql = build_kql(q, params)
        assert "'R&D Platform'" in kql


# ============================================================
# Query spec invariants
# ============================================================


class TestQuerySpecInvariants:
    """Verify structural properties of all registered queries."""

    def test_all_queries_have_take_placeholder(self) -> None:
        for qid, q in KQL_ALLOWLIST.items():
            assert "{take}" in q.kql, f"{qid} is missing {{take}} placeholder"

    def test_all_queries_have_evidence_key(self) -> None:
        for qid, q in KQL_ALLOWLIST.items():
            assert q.evidence_key, f"{qid} is missing evidence_key"

    def test_all_queries_have_source(self) -> None:
        for qid, q in KQL_ALLOWLIST.items():
            assert q.source, f"{qid} is missing source"

    def test_all_icm_queries_reference_icm_table(self) -> None:
        for qid, q in KQL_ALLOWLIST.items():
            if q.source != "icm":  # Only IcM queries should reference the IcM table
                continue
            assert "IncidentsSnapshotV2" in q.kql, f"{qid} should reference IcM table"

    def test_safefly_queries_reference_safefly_table(self) -> None:
        for qid, q in KQL_ALLOWLIST.items():
            if q.source != "safefly":
                continue
            assert "SafeFlyRequestCurrentMV" in q.kql, f"{qid} should reference SafeFly table"

    def test_default_take_within_max(self) -> None:
        for qid, q in KQL_ALLOWLIST.items():
            assert q.default_take <= q.max_take, (
                f"{qid}: default_take={q.default_take} > max_take={q.max_take}"
            )

    def test_evidence_keys_unique(self) -> None:
        keys = [q.evidence_key for q in KQL_ALLOWLIST.values()]
        assert len(keys) == len(set(keys)), f"Duplicate evidence_keys: {keys}"

    def test_query_ids_match_dict_keys(self) -> None:
        for qid, q in KQL_ALLOWLIST.items():
            assert q.query_id == qid, f"Dict key {qid} != query_id {q.query_id}"
