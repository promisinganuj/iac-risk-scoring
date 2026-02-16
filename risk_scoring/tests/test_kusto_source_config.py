"""Tests for kusto_source_config.py — YAML-based Kusto source registry."""

from __future__ import annotations

import os
import textwrap
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import pytest

from risk_scoring.kusto_source_config import (
    KustoSourceEntry,
    KustoSourceRegistry,
)


# ============================================================
# Fixtures
# ============================================================


def _write_yaml(tmp_path: Path, content: str) -> Path:
    """Write YAML content to a temp file and return the path."""
    p = tmp_path / "kusto_sources.yaml"
    p.write_text(textwrap.dedent(content))
    return p


_VALID_YAML = """\
kusto_sources:
  icm:
    cluster: https://icmcluster.kusto.windows.net
    database: IcMDataWarehouse
  service_tree:
    cluster: https://servicetreepublic.westus.kusto.windows.net
    database: Shared
"""


# ============================================================
# Parsing tests
# ============================================================


class TestYamlParsing:
    def test_loads_valid_yaml(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _VALID_YAML)
        reg = KustoSourceRegistry.from_yaml(path)
        assert "icm" in reg.sources
        assert "service_tree" in reg.sources
        assert reg.sources["icm"].cluster == "https://icmcluster.kusto.windows.net"
        assert reg.sources["icm"].database == "IcMDataWarehouse"

    def test_strips_trailing_slash(self, tmp_path: Path) -> None:
        yaml_text = """\
        kusto_sources:
          test:
            cluster: https://test.kusto.windows.net/
            database: TestDB
        """
        path = _write_yaml(tmp_path, yaml_text)
        reg = KustoSourceRegistry.from_yaml(path)
        assert reg.sources["test"].cluster == "https://test.kusto.windows.net"

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            KustoSourceRegistry.from_yaml(tmp_path / "nonexistent.yaml")

    def test_missing_kusto_sources_key_raises(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, "other_key: 123\n")
        with pytest.raises(ValueError, match="kusto_sources"):
            KustoSourceRegistry.from_yaml(path)

    def test_missing_cluster_raises(self, tmp_path: Path) -> None:
        yaml_text = """\
        kusto_sources:
          bad:
            database: DB
        """
        path = _write_yaml(tmp_path, yaml_text)
        with pytest.raises(ValueError, match="cluster"):
            KustoSourceRegistry.from_yaml(path)

    def test_missing_database_raises(self, tmp_path: Path) -> None:
        yaml_text = """\
        kusto_sources:
          bad:
            cluster: https://x.kusto.windows.net
        """
        path = _write_yaml(tmp_path, yaml_text)
        with pytest.raises(ValueError, match="database"):
            KustoSourceRegistry.from_yaml(path)

    def test_env_var_override_path(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _VALID_YAML)
        with patch.dict(os.environ, {"KUSTO_SOURCES_PATH": str(path)}):
            reg = KustoSourceRegistry.from_yaml()
        assert "icm" in reg.sources

    def test_list_sources(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _VALID_YAML)
        reg = KustoSourceRegistry.from_yaml(path)
        assert reg.list_sources() == ["icm", "service_tree"]


# ============================================================
# Auth env-var tests
# ============================================================


class TestAuthFromEnv:
    def test_default_auth(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _VALID_YAML)
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("KUSTO_AUTH_METHOD", None)
            reg = KustoSourceRegistry.from_yaml(path)
        assert reg.auth_method == "default"

    def test_az_cli_auth(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _VALID_YAML)
        with patch.dict(os.environ, {"KUSTO_AUTH_METHOD": "az_cli"}):
            reg = KustoSourceRegistry.from_yaml(path)
        assert reg.auth_method == "az_cli"

    def test_invalid_auth_raises(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _VALID_YAML)
        with patch.dict(os.environ, {"KUSTO_AUTH_METHOD": "bad"}):
            with pytest.raises(ValueError, match="KUSTO_AUTH_METHOD"):
                KustoSourceRegistry.from_yaml(path)


# ============================================================
# Config / client generation tests
# ============================================================


class TestGetConfig:
    def test_get_config_returns_kusto_config(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _VALID_YAML)
        with patch.dict(os.environ, {"KUSTO_AUTH_METHOD": "az_cli"}):
            reg = KustoSourceRegistry.from_yaml(path)

        cfg = reg.get_config("icm")
        assert cfg.cluster_url == "https://icmcluster.kusto.windows.net"
        assert cfg.database == "IcMDataWarehouse"
        assert cfg.auth_method == "az_cli"

    def test_unknown_source_raises(self, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _VALID_YAML)
        reg = KustoSourceRegistry.from_yaml(path)
        with pytest.raises(KeyError, match="nonexistent"):
            reg.get_config("nonexistent")


class TestGetClient:
    @patch("risk_scoring.kusto_source_config.KustoClient")
    def test_creates_client_lazily(
        self, MockClient: MagicMock, tmp_path: Path
    ) -> None:
        path = _write_yaml(tmp_path, _VALID_YAML)
        reg = KustoSourceRegistry.from_yaml(path)

        client1 = reg.get_client("icm")
        client2 = reg.get_client("icm")
        # Same instance returned (cached).
        assert client1 is client2
        # Only one KustoClient constructed.
        assert MockClient.call_count == 1

    @patch("risk_scoring.kusto_source_config.KustoClient")
    def test_different_sources_get_different_clients(
        self, MockClient: MagicMock, tmp_path: Path
    ) -> None:
        path = _write_yaml(tmp_path, _VALID_YAML)
        reg = KustoSourceRegistry.from_yaml(path)

        reg.get_client("icm")
        reg.get_client("service_tree")
        assert MockClient.call_count == 2

    @patch("risk_scoring.kusto_source_config.KustoClient")
    def test_close_all(self, MockClient: MagicMock, tmp_path: Path) -> None:
        path = _write_yaml(tmp_path, _VALID_YAML)
        reg = KustoSourceRegistry.from_yaml(path)

        reg.get_client("icm")
        reg.get_client("service_tree")
        reg.close_all()
        assert len(reg._clients) == 0


# ============================================================
# Default YAML loads successfully
# ============================================================


class TestDefaultYaml:
    def test_bundled_yaml_loads(self) -> None:
        """The bundled kusto_sources.yaml should parse without errors."""
        reg = KustoSourceRegistry.from_yaml()
        assert "icm" in reg.sources
        assert "service_tree" in reg.sources
