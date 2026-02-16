"""Thin wrapper around azure-kusto-data SDK for querying Azure Data Explorer.

Follows the same structural pattern as neo4j_http.py:
- KustoConfig: frozen dataclass loaded from env vars
- run_kql_readonly(): executes a KQL query and returns List[Dict[str, Any]]
- Read-only enforcement via keyword scanning

The module intentionally keeps a small public surface and returns plain dicts
so that callers are decoupled from the SDK's response types.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional

from azure.identity import (
    AzureCliCredential,
    DefaultAzureCredential,
    ManagedIdentityCredential,
)
from azure.kusto.data import KustoClient as _SdkKustoClient
from azure.kusto.data import KustoConnectionStringBuilder
from azure.kusto.data.exceptions import KustoServiceError

logger = logging.getLogger(__name__)


class KustoQueryError(RuntimeError):
    """Raised when a KQL query fails or returns an unexpected response."""


# ---- read-only enforcement ----

_WRITE_KEYWORDS = re.compile(
    r"(?:^|[\s;|])"                        # start of string or whitespace/delimiter
    r"(\.set-or-append|\.set-or-replace|\.create-or-alter|\.create-merge"
    r"|\.set|\.append|\.drop|\.create|\.alter|\.delete|\.rename|\.move"
    r"|\.replace|\.ingest)"
    r"(?:\s|$)",                            # followed by whitespace or end
    re.IGNORECASE,
)


def _assert_readonly(kql: str) -> None:
    """Reject KQL that contains management/write commands."""
    if _WRITE_KEYWORDS.search(kql):
        raise KustoQueryError(
            "Refusing to run non-read-only KQL (management command detected)."
        )


# ---- configuration ----


@dataclass(frozen=True)
class KustoConfig:
    """Connection settings for an Azure Data Explorer cluster.

    Environment variables
    ---------------------
    KUSTO_CLUSTER_URL   – required, e.g. https://mycluster.region.kusto.windows.net
    KUSTO_DATABASE      – required, the default database for queries
    KUSTO_AUTH_METHOD   – "default" (DefaultAzureCredential), "az_cli" (AzureCliCredential),
                         or "mi" (ManagedIdentityCredential)
    KUSTO_MI_CLIENT_ID  – client ID when using user-assigned managed identity
    KUSTO_TIMEOUT_SECS  – per-query timeout in seconds (default 30)
    """

    cluster_url: str
    database: str
    auth_method: str = "default"  # "default" | "az_cli" | "mi"
    mi_client_id: Optional[str] = None
    timeout_secs: float = 30.0

    @staticmethod
    def from_env() -> "KustoConfig":
        cluster_url = (os.environ.get("KUSTO_CLUSTER_URL") or "").strip()
        if not cluster_url:
            raise KustoQueryError(
                "Missing KUSTO_CLUSTER_URL. Set it to your ADX cluster URL, "
                "e.g. https://mycluster.region.kusto.windows.net"
            )

        database = (os.environ.get("KUSTO_DATABASE") or "").strip()
        if not database:
            raise KustoQueryError(
                "Missing KUSTO_DATABASE. Set it to the target database name."
            )

        auth_method = (
            os.environ.get("KUSTO_AUTH_METHOD") or "default"
        ).strip().lower()
        if auth_method not in ("default", "az_cli", "mi"):
            raise KustoQueryError(
                f"Invalid KUSTO_AUTH_METHOD: {auth_method!r}. Must be 'default', 'az_cli', or 'mi'."
            )

        mi_client_id = (os.environ.get("KUSTO_MI_CLIENT_ID") or "").strip() or None

        timeout_raw = (os.environ.get("KUSTO_TIMEOUT_SECS") or "").strip()
        timeout_secs = 30.0
        if timeout_raw:
            try:
                timeout_secs = float(timeout_raw)
                if timeout_secs <= 0:
                    raise ValueError("must be positive")
            except ValueError as e:
                raise KustoQueryError(
                    f"Invalid KUSTO_TIMEOUT_SECS: {timeout_raw!r}"
                ) from e

        return KustoConfig(
            cluster_url=cluster_url.rstrip("/"),
            database=database,
            auth_method=auth_method,
            mi_client_id=mi_client_id,
            timeout_secs=timeout_secs,
        )


# ---- client ----


def _build_connection_string(
    config: KustoConfig,
) -> KustoConnectionStringBuilder:
    """Build a KustoConnectionStringBuilder with the appropriate credential."""
    if config.auth_method == "mi":
        if config.mi_client_id:
            return KustoConnectionStringBuilder.with_aad_managed_service_identity_authentication(
                config.cluster_url,
                client_id=config.mi_client_id,
            )
        return KustoConnectionStringBuilder.with_aad_managed_service_identity_authentication(
            config.cluster_url,
        )

    if config.auth_method == "az_cli":
        return KustoConnectionStringBuilder.with_az_cli_authentication(
            config.cluster_url,
        )

    # "default" → use DefaultAzureCredential (works for local dev, MI, SP, etc.)
    kcsb = KustoConnectionStringBuilder.with_azure_token_credential(
        config.cluster_url,
        credential=DefaultAzureCredential(),
    )
    return kcsb


class KustoClient:
    """Thin wrapper for executing read-only KQL against Azure Data Explorer.

    Usage::

        config = KustoConfig.from_env()
        client = KustoClient(config)
        rows = client.execute("StormEvents | take 5")
    """

    def __init__(self, config: KustoConfig) -> None:
        self._config = config
        self._kcsb = _build_connection_string(config)
        self._client = _SdkKustoClient(self._kcsb)

    @property
    def config(self) -> KustoConfig:
        return self._config

    def execute(
        self,
        kql: str,
        database: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a read-only KQL query and return rows as plain dicts.

        Parameters
        ----------
        kql : str
            The KQL query to run. Must be read-only (no management commands).
        database : str, optional
            Override the default database from config.

        Returns
        -------
        list of dict
            Each dict maps column names to Python values.

        Raises
        ------
        KustoQueryError
            On write-command detection, auth error, timeout, or query failure.
        """
        _assert_readonly(kql)

        db = database or self._config.database
        if not db:
            raise KustoQueryError("No database specified and no default configured.")

        try:
            response = self._client.execute(db, kql)
        except KustoServiceError as e:
            raise KustoQueryError(f"KQL query failed: {e}") from e
        except Exception as e:
            # Catch auth/network errors from the SDK
            raise KustoQueryError(
                f"Kusto request failed ({type(e).__name__}): {e}"
            ) from e

        return self._response_to_dicts(response)

    def close(self) -> None:
        """Release underlying SDK resources."""
        try:
            self._client.close()
        except Exception:
            pass

    def __enter__(self) -> "KustoClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---- internal helpers ----

    @staticmethod
    def _response_to_dicts(response: Any) -> List[Dict[str, Any]]:
        """Convert a KustoResponseDataSet into a list of plain dicts."""
        rows: List[Dict[str, Any]] = []
        primary = response.primary_results
        if not primary:
            return rows

        table = primary[0]
        columns = [col.column_name for col in table.columns]

        for row in table:
            d: Dict[str, Any] = {}
            for col_name in columns:
                d[col_name] = row[col_name]
            rows.append(d)

        return rows
