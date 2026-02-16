from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Optional

from risk_scoring.models import CandidateEntity
from risk_scoring.repository import EntityRepository


class CsvEntityRepository(EntityRepository):
    """Repository backed by Approach 2 sample data files (JSON or CSV).

    This is useful for unit testing and local, DB-less workflows. The canonical
    online path is Neo4j, but the sample dataset exists as JSON and CSV.
    Defaults to JSON, falls back to CSV if JSON not found.
    """

    def __init__(self, *, sample_data_dir: Path):
        self._resources = _load_resources(sample_data_dir / "azure_resources")

    def find_azure_resources_by_resource_id(
        self, resource_id: str, *, limit: int
    ) -> list[CandidateEntity]:
        results = [r for r in self._resources if r.resource_id == resource_id]
        return results[:limit]

    def find_azure_resources_by_attributes(
        self,
        *,
        resource_type: Optional[str],
        subscription_id: Optional[str],
        resource_group: Optional[str],
        display_name: Optional[str],
        limit: int,
    ) -> list[CandidateEntity]:
        results = list(self._resources)

        if resource_type is not None:
            results = [r for r in results if (r.resource_type or "") == resource_type]
        if subscription_id is not None:
            results = [r for r in results if (r.subscription_id or "") == subscription_id]
        if resource_group is not None:
            results = [r for r in results if (r.resource_group or "") == resource_group]
        if display_name is not None:
            results = [r for r in results if (r.display_name or "") == display_name]

        return results[:limit]


def _load_resources(path_prefix: Path) -> list[CandidateEntity]:
    """Load resources from JSON (preferred) or CSV (fallback).
    
    Args:
        path_prefix: Path without extension (e.g., sample-data/azure_resources)
    
    Returns:
        List of CandidateEntity objects
    """
    json_path = path_prefix.with_suffix(".json")
    csv_path = path_prefix.with_suffix(".csv")
    
    # Try JSON first
    if json_path.exists():
        return _load_json_resources(json_path)
    
    # Fall back to CSV
    if csv_path.exists():
        return _load_csv_resources(csv_path)
    
    raise FileNotFoundError(
        f"sample data not found: tried {json_path} and {csv_path}"
    )


def _load_json_resources(path: Path) -> list[CandidateEntity]:
    """Load resources from JSON file."""
    resources: list[CandidateEntity] = []
    
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array in {path}, got {type(data).__name__}")
    
    for row in data:
        if not isinstance(row, dict):
            continue
        
        rid = (row.get("resourceName") or "").strip()
        if not rid:
            continue
        
        resources.append(
            CandidateEntity(
                label="AzureResource",
                resource_id=rid,
                display_name=(row.get("displayName") or "").strip() or None,
                resource_type=(row.get("resourceType") or "").strip() or None,
                subscription_id=(row.get("subscriptionId") or "").strip() or None,
                resource_group=(row.get("resourceGroup") or "").strip() or None,
            )
        )
    
    return resources


def _load_csv_resources(path: Path) -> list[CandidateEntity]:
    """Load resources from CSV file (fallback for backward compatibility)."""
    resources: list[CandidateEntity] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rid = (row.get("resourceName") or "").strip()
            if not rid:
                continue
            resources.append(
                CandidateEntity(
                    label="AzureResource",
                    resource_id=rid,
                    display_name=(row.get("displayName") or "").strip() or None,
                    resource_type=(row.get("resourceType") or "").strip() or None,
                    subscription_id=(row.get("subscriptionId") or "").strip() or None,
                    resource_group=(row.get("resourceGroup") or "").strip() or None,
                )
            )

    return resources
