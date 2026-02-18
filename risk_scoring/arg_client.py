"""Azure Resource Graph client with the same execute() interface as KustoClient.

Uses the ``azure-mgmt-resourcegraph`` SDK to query ARG via the ARM REST API.
This is a drop-in replacement for ``KustoClient`` when the query source is
``"arg"`` — it accepts KQL (which ARG supports natively) and returns
``list[dict]`` rows.

Authentication uses ``DefaultAzureCredential`` (or ``AzureCliCredential`` when
``KUSTO_AUTH_METHOD=az_cli``), consistent with the Kusto client auth model.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ARGQueryError(Exception):
    """Raised when an ARG query fails."""


class ARGClient:
    """Query Azure Resource Graph using the official ARM SDK.

    Provides the same ``execute(kql) -> list[dict]`` contract as
    ``KustoClient`` so the evidence provider can dispatch transparently.

    Parameters
    ----------
    subscription_ids : list[str], optional
        Default subscription scope.  If not provided, the query must include
        its own ``where subscriptionId ==`` filter.  Can be overridden per
        call via ``execute(..., subscription_ids=[...])``.
    """

    def __init__(
        self,
        subscription_ids: Optional[List[str]] = None,
    ) -> None:
        self._subscription_ids = subscription_ids or []
        self._client = None  # lazy init

    def _ensure_client(self):
        """Lazily create the ResourceGraphClient on first use."""
        if self._client is not None:
            return

        try:
            from azure.identity import AzureCliCredential, DefaultAzureCredential
            from azure.mgmt.resourcegraph import ResourceGraphClient
        except ImportError as exc:
            raise ARGQueryError(
                "azure-mgmt-resourcegraph and azure-identity are required "
                "for ARG queries. Install with: "
                "pip install azure-mgmt-resourcegraph azure-identity"
            ) from exc

        auth_method = (
            os.environ.get("KUSTO_AUTH_METHOD") or "default"
        ).strip().lower()

        if auth_method == "az_cli":
            credential = AzureCliCredential()
        else:
            credential = DefaultAzureCredential()

        self._client = ResourceGraphClient(credential)
        logger.info("Created ARG client (auth=%s)", auth_method)

    def execute(
        self,
        kql: str,
        database: Optional[str] = None,
        subscription_ids: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Execute a KQL query against Azure Resource Graph.

        Parameters
        ----------
        kql : str
            The KQL query to run.  ARG supports a subset of KQL.
        database : str, optional
            Ignored — ARG has no database concept.  Accepted for interface
            compatibility with ``KustoClient``.
        subscription_ids : list[str], optional
            Override the default subscription scope for this query.

        Returns
        -------
        list of dict
            Each dict maps column names to Python values.

        Raises
        ------
        ARGQueryError
            On auth failure, network error, or ARG query error.
        """
        self._ensure_client()

        from azure.mgmt.resourcegraph.models import (
            QueryRequest,
            QueryRequestOptions,
            ResultFormat,
        )

        subs = subscription_ids or self._subscription_ids

        try:
            request = QueryRequest(
                query=kql,
                subscriptions=subs if subs else None,
                options=QueryRequestOptions(result_format=ResultFormat.OBJECT_ARRAY),
            )
            response = self._client.resources(request)
        except Exception as exc:
            raise ARGQueryError(
                f"ARG query failed ({type(exc).__name__}): {exc}"
            ) from exc

        # response.data is a list of dicts when result_format is OBJECT_ARRAY
        data = response.data
        if isinstance(data, list):
            return data

        # Fallback: sometimes data is returned as a dict with columns/rows
        if isinstance(data, dict):
            columns = data.get("columns", [])
            rows_raw = data.get("rows", [])
            col_names = [c.get("name", f"col{i}") for i, c in enumerate(columns)]
            return [dict(zip(col_names, row)) for row in rows_raw]

        logger.warning("Unexpected ARG response type: %s", type(data))
        return []

    def close(self) -> None:
        """Close the underlying client (if any)."""
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def __enter__(self) -> "ARGClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()
