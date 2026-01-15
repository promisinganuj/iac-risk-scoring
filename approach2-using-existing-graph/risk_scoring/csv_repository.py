from __future__ import annotations

import csv
from pathlib import Path
from typing import Optional

from risk_scoring.models import CandidateEntity
from risk_scoring.repository import EntityRepository


class CsvEntityRepository(EntityRepository):
    """Repository backed by Approach 2 sample CSVs.

    This is useful for unit testing and local, DB-less workflows. The canonical
    online path is Neo4j, but the sample dataset already exists as CSV.
    """

    def __init__(self, *, sample_data_dir: Path):
        self._resources = _load_resources(sample_data_dir / "azure_resources.csv")

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


def _load_resources(path: Path) -> list[CandidateEntity]:
    if not path.exists():
        raise FileNotFoundError(f"sample data not found: {path}")

    resources: list[CandidateEntity] = []
    with path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rid = (row.get("resourceId") or "").strip()
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
