"""Load Kusto source configuration from YAML.

Reads ``risk_scoring/config/kusto_sources.yaml`` (or a path set via
``KUSTO_SOURCES_PATH`` env-var) and builds ``KustoConfig`` objects for
each logical source.  Auth method is shared across all sources and comes
from the ``KUSTO_AUTH_METHOD`` env-var (default ``"default"``).

Usage::

    registry = KustoSourceRegistry.from_yaml()
    icm_config = registry.get_config("icm")
    st_client  = registry.get_client("service_tree")
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Optional

import yaml

from risk_scoring.kusto_client import KustoClient, KustoConfig

logger = logging.getLogger(__name__)

# Default YAML path — next to this module's package.
_DEFAULT_YAML = Path(__file__).resolve().parent / "config" / "kusto_sources.yaml"


@dataclass
class KustoSourceEntry:
    """A single parsed source entry from the YAML."""

    name: str
    cluster: str
    database: str


@dataclass
class KustoSourceRegistry:
    """Registry of Kusto source configs and lazily-created clients.

    Attributes
    ----------
    sources : dict[str, KustoSourceEntry]
        Parsed source definitions keyed by logical name (e.g., "icm").
    auth_method : str
        Authentication method shared by all sources ("default"|"az_cli"|"mi").
    mi_client_id : str | None
        Optional managed-identity client ID.
    timeout_secs : float
        Per-query timeout.
    """

    sources: Dict[str, KustoSourceEntry]
    auth_method: str = "default"
    mi_client_id: Optional[str] = None
    timeout_secs: float = 30.0

    _clients: Dict[str, KustoClient] = field(
        default_factory=dict, init=False, repr=False
    )

    # ---- factories ----

    @classmethod
    def from_yaml(
        cls,
        path: Optional[str | Path] = None,
    ) -> "KustoSourceRegistry":
        """Load config from YAML, with env-var overrides for auth.

        Parameters
        ----------
        path : str | Path, optional
            Explicit YAML path.  Falls back to ``KUSTO_SOURCES_PATH`` env-var,
            then to the default bundled YAML.
        """
        yaml_path = Path(
            path
            or os.environ.get("KUSTO_SOURCES_PATH", "")
            or _DEFAULT_YAML
        )

        if not yaml_path.exists():
            raise FileNotFoundError(
                f"Kusto sources YAML not found: {yaml_path}"
            )

        with open(yaml_path, "r") as f:
            raw = yaml.safe_load(f)

        if not raw or "kusto_sources" not in raw:
            raise ValueError(
                f"Kusto sources YAML must contain a 'kusto_sources' key: {yaml_path}"
            )

        sources: Dict[str, KustoSourceEntry] = {}
        for name, entry in raw["kusto_sources"].items():
            cluster = (entry.get("cluster") or "").strip()
            database = (entry.get("database") or "").strip()
            if not cluster or not database:
                raise ValueError(
                    f"Kusto source '{name}' must have both 'cluster' and 'database'"
                )
            # Normalise: strip trailing slash from cluster URL
            sources[name] = KustoSourceEntry(
                name=name,
                cluster=cluster.rstrip("/"),
                database=database,
            )

        # Auth from env (shared across all sources)
        auth_method = (
            os.environ.get("KUSTO_AUTH_METHOD") or "default"
        ).strip().lower()
        if auth_method not in ("default", "az_cli", "mi"):
            raise ValueError(
                f"Invalid KUSTO_AUTH_METHOD: {auth_method!r}. "
                "Must be 'default', 'az_cli', or 'mi'."
            )

        mi_client_id = (
            os.environ.get("KUSTO_MI_CLIENT_ID") or ""
        ).strip() or None

        timeout_raw = (os.environ.get("KUSTO_TIMEOUT_SECS") or "").strip()
        timeout_secs = 30.0
        if timeout_raw:
            try:
                timeout_secs = float(timeout_raw)
                if timeout_secs <= 0:
                    raise ValueError("must be positive")
            except ValueError as e:
                raise ValueError(
                    f"Invalid KUSTO_TIMEOUT_SECS: {timeout_raw!r}"
                ) from e

        return cls(
            sources=sources,
            auth_method=auth_method,
            mi_client_id=mi_client_id,
            timeout_secs=timeout_secs,
        )

    # ---- accessors ----

    def get_config(self, source_name: str) -> KustoConfig:
        """Build a ``KustoConfig`` for the named source."""
        entry = self.sources.get(source_name)
        if entry is None:
            available = ", ".join(sorted(self.sources.keys()))
            raise KeyError(
                f"Unknown Kusto source: {source_name!r}. "
                f"Available: {available}"
            )
        return KustoConfig(
            cluster_url=entry.cluster,
            database=entry.database,
            auth_method=self.auth_method,
            mi_client_id=self.mi_client_id,
            timeout_secs=self.timeout_secs,
        )

    def get_client(self, source_name: str) -> KustoClient:
        """Return a (lazily created) ``KustoClient`` for the named source.

        Clients are cached so repeated calls for the same source reuse the
        same SDK connection.
        """
        if source_name not in self._clients:
            cfg = self.get_config(source_name)
            self._clients[source_name] = KustoClient(cfg)
            logger.info(
                "Created KustoClient for source %r → %s/%s",
                source_name, cfg.cluster_url, cfg.database,
            )
        return self._clients[source_name]

    def list_sources(self) -> list[str]:
        """Return sorted list of available source names."""
        return sorted(self.sources.keys())

    def close_all(self) -> None:
        """Close all cached KustoClient instances."""
        for name, client in self._clients.items():
            try:
                client.close()
            except Exception:
                logger.warning("Error closing KustoClient for %r", name)
        self._clients.clear()

    def __enter__(self) -> "KustoSourceRegistry":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close_all()
