"""Tests for risk_scoring.kusto_client."""

from __future__ import annotations

import os
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from risk_scoring.kusto_client import (
    KustoClient,
    KustoConfig,
    KustoQueryError,
    _assert_readonly,
)


# ============================================================
# KustoConfig tests
# ============================================================


class TestKustoConfigFromEnv:
    """Test KustoConfig.from_env() with various env var combinations."""

    def _set_env(self, monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
        defaults = {
            "KUSTO_CLUSTER_URL": "https://mycluster.westus2.kusto.windows.net",
            "KUSTO_DATABASE": "mydb",
        }
        defaults.update(overrides)
        for key, val in defaults.items():
            if val is None:
                monkeypatch.delenv(key, raising=False)
            else:
                monkeypatch.setenv(key, val)

    def test_minimal_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._set_env(monkeypatch)
        config = KustoConfig.from_env()
        assert config.cluster_url == "https://mycluster.westus2.kusto.windows.net"
        assert config.database == "mydb"
        assert config.auth_method == "default"
        assert config.mi_client_id is None
        assert config.timeout_secs == 30.0

    def test_trailing_slash_stripped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._set_env(
            monkeypatch,
            KUSTO_CLUSTER_URL="https://mycluster.westus2.kusto.windows.net/",
        )
        config = KustoConfig.from_env()
        assert not config.cluster_url.endswith("/")

    def test_mi_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._set_env(
            monkeypatch,
            KUSTO_AUTH_METHOD="mi",
            KUSTO_MI_CLIENT_ID="11111111-2222-3333-4444-555555555555",
        )
        config = KustoConfig.from_env()
        assert config.auth_method == "mi"
        assert config.mi_client_id == "11111111-2222-3333-4444-555555555555"

    def test_timeout_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._set_env(monkeypatch, KUSTO_TIMEOUT_SECS="60")
        config = KustoConfig.from_env()
        assert config.timeout_secs == 60.0

    def test_missing_cluster_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._set_env(monkeypatch, KUSTO_CLUSTER_URL="")
        with pytest.raises(KustoQueryError, match="Missing KUSTO_CLUSTER_URL"):
            KustoConfig.from_env()

    def test_missing_database(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._set_env(monkeypatch, KUSTO_DATABASE="")
        with pytest.raises(KustoQueryError, match="Missing KUSTO_DATABASE"):
            KustoConfig.from_env()

    def test_invalid_auth_method(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._set_env(monkeypatch, KUSTO_AUTH_METHOD="oauth")
        with pytest.raises(KustoQueryError, match="Invalid KUSTO_AUTH_METHOD"):
            KustoConfig.from_env()

    def test_invalid_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._set_env(monkeypatch, KUSTO_TIMEOUT_SECS="not-a-number")
        with pytest.raises(KustoQueryError, match="Invalid KUSTO_TIMEOUT_SECS"):
            KustoConfig.from_env()

    def test_negative_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._set_env(monkeypatch, KUSTO_TIMEOUT_SECS="-5")
        with pytest.raises(KustoQueryError, match="Invalid KUSTO_TIMEOUT_SECS"):
            KustoConfig.from_env()


# ============================================================
# Read-only enforcement tests
# ============================================================


class TestAssertReadonly:
    """Ensure write/management commands are blocked."""

    @pytest.mark.parametrize(
        "kql",
        [
            "StormEvents | take 10",
            "StormEvents | where State == 'TEXAS' | count",
            "let x = 5; StormEvents | take x",
            "StormEvents | summarize count() by State | order by count_ desc",
            "StormEvents | project StartTime, EndTime, EventType",
        ],
    )
    def test_readonly_queries_pass(self, kql: str) -> None:
        _assert_readonly(kql)  # Should not raise

    @pytest.mark.parametrize(
        "kql,keyword",
        [
            (".set MyTable <| StormEvents | take 10", ".set"),
            (".set-or-append MyTable <| source", ".set-or-append"),
            (".set-or-replace MyTable <| source", ".set-or-replace"),
            (".append MyTable <| source", ".append"),
            (".drop table MyTable", ".drop"),
            (".create table MyTable (col1:string)", ".create"),
            (".alter table MyTable (col1:string)", ".alter"),
            (".delete table MyTable records", ".delete"),
            (".rename table MyTable to NewName", ".rename"),
            (".ingest into table MyTable", ".ingest"),
            (".create-or-alter function MyFunc", ".create-or-alter"),
            (".create-merge table MyTable", ".create-merge"),
        ],
    )
    def test_write_commands_blocked(self, kql: str, keyword: str) -> None:
        with pytest.raises(KustoQueryError, match="management command"):
            _assert_readonly(kql)


# ============================================================
# KustoClient tests (with mocked SDK)
# ============================================================


def _make_config(**overrides: Any) -> KustoConfig:
    defaults = dict(
        cluster_url="https://test.kusto.windows.net",
        database="testdb",
        auth_method="default",
        mi_client_id=None,
        timeout_secs=30.0,
    )
    defaults.update(overrides)
    return KustoConfig(**defaults)


def _mock_column(name: str) -> MagicMock:
    col = MagicMock()
    col.column_name = name
    return col


def _mock_response(
    columns: List[str], rows: List[Dict[str, Any]]
) -> MagicMock:
    """Build a mock KustoResponseDataSet."""
    mock_cols = [_mock_column(c) for c in columns]

    # Each row in the response behaves like a dict-like object
    mock_rows = []
    for row_dict in rows:
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, key, d=row_dict: d[key]
        mock_rows.append(mock_row)

    table = MagicMock()
    table.columns = mock_cols
    table.__iter__ = lambda self: iter(mock_rows)

    response = MagicMock()
    response.primary_results = [table]
    return response


class TestKustoClientExecute:
    """Test KustoClient.execute() with mocked SDK client."""

    @patch("risk_scoring.kusto_client._build_connection_string")
    @patch("risk_scoring.kusto_client._SdkKustoClient")
    def test_simple_query(
        self, mock_sdk_cls: MagicMock, mock_build_kcsb: MagicMock
    ) -> None:
        config = _make_config()
        mock_sdk = MagicMock()
        mock_sdk_cls.return_value = mock_sdk
        mock_sdk.execute.return_value = _mock_response(
            columns=["State", "Count"],
            rows=[
                {"State": "TEXAS", "Count": 42},
                {"State": "FLORIDA", "Count": 17},
            ],
        )

        client = KustoClient(config)
        result = client.execute("StormEvents | summarize count() by State | take 2")

        assert len(result) == 2
        assert result[0] == {"State": "TEXAS", "Count": 42}
        assert result[1] == {"State": "FLORIDA", "Count": 17}
        mock_sdk.execute.assert_called_once_with(
            "testdb", "StormEvents | summarize count() by State | take 2"
        )

    @patch("risk_scoring.kusto_client._build_connection_string")
    @patch("risk_scoring.kusto_client._SdkKustoClient")
    def test_database_override(
        self, mock_sdk_cls: MagicMock, mock_build_kcsb: MagicMock
    ) -> None:
        config = _make_config()
        mock_sdk = MagicMock()
        mock_sdk_cls.return_value = mock_sdk
        mock_sdk.execute.return_value = _mock_response(columns=["x"], rows=[{"x": 1}])

        client = KustoClient(config)
        client.execute("T | take 1", database="otherdb")
        mock_sdk.execute.assert_called_once_with("otherdb", "T | take 1")

    @patch("risk_scoring.kusto_client._build_connection_string")
    @patch("risk_scoring.kusto_client._SdkKustoClient")
    def test_write_command_rejected(
        self, mock_sdk_cls: MagicMock, mock_build_kcsb: MagicMock
    ) -> None:
        config = _make_config()
        mock_sdk_cls.return_value = MagicMock()
        client = KustoClient(config)
        with pytest.raises(KustoQueryError, match="management command"):
            client.execute(".drop table MyTable")

    @patch("risk_scoring.kusto_client._build_connection_string")
    @patch("risk_scoring.kusto_client._SdkKustoClient")
    def test_empty_response(
        self, mock_sdk_cls: MagicMock, mock_build_kcsb: MagicMock
    ) -> None:
        config = _make_config()
        mock_sdk = MagicMock()
        mock_sdk_cls.return_value = mock_sdk
        resp = MagicMock()
        resp.primary_results = []
        mock_sdk.execute.return_value = resp

        client = KustoClient(config)
        result = client.execute("T | where 1==0")
        assert result == []

    @patch("risk_scoring.kusto_client._build_connection_string")
    @patch("risk_scoring.kusto_client._SdkKustoClient")
    def test_sdk_service_error(
        self, mock_sdk_cls: MagicMock, mock_build_kcsb: MagicMock
    ) -> None:
        from azure.kusto.data.exceptions import KustoServiceError

        config = _make_config()
        mock_sdk = MagicMock()
        mock_sdk_cls.return_value = mock_sdk
        mock_sdk.execute.side_effect = KustoServiceError(
            [{"error": {"message": "Bad query"}}]
        )

        client = KustoClient(config)
        with pytest.raises(KustoQueryError, match="KQL query failed"):
            client.execute("bad query syntax")

    @patch("risk_scoring.kusto_client._build_connection_string")
    @patch("risk_scoring.kusto_client._SdkKustoClient")
    def test_generic_exception(
        self, mock_sdk_cls: MagicMock, mock_build_kcsb: MagicMock
    ) -> None:
        config = _make_config()
        mock_sdk = MagicMock()
        mock_sdk_cls.return_value = mock_sdk
        mock_sdk.execute.side_effect = ConnectionError("network down")

        client = KustoClient(config)
        with pytest.raises(KustoQueryError, match="Kusto request failed"):
            client.execute("T | take 1")

    @patch("risk_scoring.kusto_client._build_connection_string")
    @patch("risk_scoring.kusto_client._SdkKustoClient")
    def test_context_manager(
        self, mock_sdk_cls: MagicMock, mock_build_kcsb: MagicMock
    ) -> None:
        config = _make_config()
        mock_sdk = MagicMock()
        mock_sdk_cls.return_value = mock_sdk
        mock_sdk.execute.return_value = _mock_response(
            columns=["n"], rows=[{"n": 1}]
        )

        with KustoClient(config) as client:
            result = client.execute("T | take 1")
            assert result == [{"n": 1}]

        mock_sdk.close.assert_called_once()

    @patch("risk_scoring.kusto_client._build_connection_string")
    @patch("risk_scoring.kusto_client._SdkKustoClient")
    def test_no_database_error(
        self, mock_sdk_cls: MagicMock, mock_build_kcsb: MagicMock
    ) -> None:
        config = _make_config(database="")
        mock_sdk_cls.return_value = MagicMock()
        client = KustoClient(config)
        with pytest.raises(KustoQueryError, match="No database specified"):
            client.execute("T | take 1")


# ============================================================
# Response parsing edge cases
# ============================================================


class TestResponseToDicts:
    """Test the _response_to_dicts static method."""

    def test_multiple_columns(self) -> None:
        resp = _mock_response(
            columns=["a", "b", "c"],
            rows=[
                {"a": 1, "b": "hello", "c": True},
                {"a": 2, "b": "world", "c": False},
            ],
        )
        result = KustoClient._response_to_dicts(resp)
        assert len(result) == 2
        assert result[0] == {"a": 1, "b": "hello", "c": True}
        assert result[1] == {"a": 2, "b": "world", "c": False}

    def test_none_values(self) -> None:
        resp = _mock_response(
            columns=["x", "y"],
            rows=[{"x": None, "y": 42}],
        )
        result = KustoClient._response_to_dicts(resp)
        assert result == [{"x": None, "y": 42}]

    def test_empty_table(self) -> None:
        resp = _mock_response(columns=["x"], rows=[])
        result = KustoClient._response_to_dicts(resp)
        assert result == []
