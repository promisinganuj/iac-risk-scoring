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


# A valid Service Tree GUID for testing.
_VALID_SERVICE_ID = "A56C6700-6666-4444-AAAA-000F3B9CC999"


# ============================================================
# get_kql_query
# ============================================================


class TestGetKqlQuery:
    def test_known_query(self) -> None:
        q = get_kql_query("k1.open_icms")
        assert isinstance(q, KqlQuerySpec)
        assert q.query_id == "k1.open_icms"

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
    def test_valid_service_id(self) -> None:
        q = get_kql_query("k1.open_icms")
        result = validate_kql_params(q, {"serviceId": _VALID_SERVICE_ID})
        assert result["serviceId"] == _VALID_SERVICE_ID
        assert result["take"] == q.default_take

    def test_missing_required_service_id(self) -> None:
        q = get_kql_query("k1.open_icms")
        with pytest.raises(ParameterValidationError, match="Missing required"):
            validate_kql_params(q, {})

    def test_empty_service_id(self) -> None:
        q = get_kql_query("k1.open_icms")
        with pytest.raises(ParameterValidationError, match="non-empty"):
            validate_kql_params(q, {"serviceId": ""})

    def test_service_id_too_long(self) -> None:
        q = get_kql_query("k1.open_icms")
        with pytest.raises(ParameterValidationError, match="max_len"):
            validate_kql_params(q, {"serviceId": "a" * 37})

    def test_service_id_must_be_string(self) -> None:
        q = get_kql_query("k1.open_icms")
        with pytest.raises(ParameterValidationError, match="must be a string"):
            validate_kql_params(q, {"serviceId": 12345})


class TestTakeValidation:
    def test_default_take(self) -> None:
        q = get_kql_query("k1.open_icms")
        result = validate_kql_params(q, {"serviceId": _VALID_SERVICE_ID})
        assert result["take"] == 1  # k1 default_take=1

    def test_explicit_take(self) -> None:
        q = get_kql_query("k1.open_icms")
        result = validate_kql_params(q, {"serviceId": _VALID_SERVICE_ID, "take": 1})
        assert result["take"] == 1

    def test_take_exceeds_max(self) -> None:
        q = get_kql_query("k1.open_icms")
        with pytest.raises(ParameterValidationError, match="max_take"):
            validate_kql_params(q, {"serviceId": _VALID_SERVICE_ID, "take": 100})

    def test_take_zero(self) -> None:
        q = get_kql_query("k1.open_icms")
        with pytest.raises(ParameterValidationError, match="must be > 0"):
            validate_kql_params(q, {"serviceId": _VALID_SERVICE_ID, "take": 0})

    def test_take_negative(self) -> None:
        q = get_kql_query("k1.open_icms")
        with pytest.raises(ParameterValidationError, match="must be > 0"):
            validate_kql_params(q, {"serviceId": _VALID_SERVICE_ID, "take": -1})

    def test_take_not_int(self) -> None:
        q = get_kql_query("k1.open_icms")
        with pytest.raises(ParameterValidationError, match="must be an int"):
            validate_kql_params(q, {"serviceId": _VALID_SERVICE_ID, "take": "5"})


# ============================================================
# build_kql
# ============================================================


class TestBuildKql:
    def test_k1_open_icms(self) -> None:
        q = get_kql_query("k1.open_icms")
        params = validate_kql_params(q, {"serviceId": _VALID_SERVICE_ID})
        kql = build_kql(q, params)
        # Should contain the GUID single-quoted
        assert f"toguid('{_VALID_SERVICE_ID}')" in kql
        assert "isempty(ResolveDate)" in kql
        assert "open_icms = count()" in kql
        assert "take 1" in kql

    def test_k4_avg_mttm(self) -> None:
        q = get_kql_query("k4.avg_mttm")
        params = validate_kql_params(q, {"serviceId": _VALID_SERVICE_ID})
        kql = build_kql(q, params)
        assert "avg_mttm_minutes" in kql
        assert "datetime_diff" in kql
        assert "ImpactStartDate" in kql
        assert "MitigateDate" in kql
        assert "ago(180d)" in kql

    def test_k5_outages_180d(self) -> None:
        q = get_kql_query("k5.outages_180d")
        params = validate_kql_params(q, {"serviceId": _VALID_SERVICE_ID})
        kql = build_kql(q, params)
        assert "IsOutage == true" in kql
        assert "ago(180d)" in kql
        assert "historical_outages_180d = count()" in kql

    def test_k6_related_incidents(self) -> None:
        q = get_kql_query("k6.related_incidents")
        params = validate_kql_params(q, {"serviceId": _VALID_SERVICE_ID})
        kql = build_kql(q, params)
        assert "ParentIncidentId" in kql
        assert "dcount" in kql
        assert "ago(90d)" in kql

    def test_unsafe_characters_rejected(self) -> None:
        q = get_kql_query("k1.open_icms")
        # Inject a serviceId with KQL injection attempt
        params = {"serviceId": "abc'); .drop table X; //", "take": 1}
        # First validate (will strip/pass since it looks like a string)
        # but build_kql should reject unsafe chars
        with pytest.raises(ParameterValidationError):
            validated = validate_kql_params(q, params)
            build_kql(q, validated)

    def test_sql_injection_in_guid(self) -> None:
        q = get_kql_query("k1.open_icms")
        # Semicolons are not in SAFE_STRING_RE
        params = {"serviceId": "A56C6700;drop", "take": 1}
        with pytest.raises(ParameterValidationError):
            validated = validate_kql_params(q, params)
            build_kql(q, validated)

    def test_valid_lowercase_guid(self) -> None:
        q = get_kql_query("k1.open_icms")
        lower_guid = "a56c6700-6666-4444-aaaa-000f3b9cc999"
        params = validate_kql_params(q, {"serviceId": lower_guid})
        kql = build_kql(q, params)
        assert f"toguid('{lower_guid}')" in kql


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

    def test_all_queries_reference_icm_table(self) -> None:
        for qid, q in KQL_ALLOWLIST.items():
            assert "IncidentsSnapshotV2" in q.kql, f"{qid} should reference IcM table"

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
