from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ResourceSpec:
    """Canonical user-provided resource identity (Approach 2).

    The Neo4j import uses `AzureResource.resourceId` as the unique key.
    In the sample dataset this looks like `res-alpha-app` (not a full Azure ARM ID).
    """

    resource_id: str
    resource_type: Optional[str] = None
    subscription_id: Optional[str] = None
    resource_group: Optional[str] = None


@dataclass(frozen=True)
class CandidateEntity:
    """A candidate node returned by resolution queries."""

    label: str
    resource_id: str
    display_name: Optional[str] = None
    resource_type: Optional[str] = None
    subscription_id: Optional[str] = None
    resource_group: Optional[str] = None


@dataclass(frozen=True)
class ResolvedEntityRef:
    """Resolved entity reference used by the evidence layer."""

    label: str
    resource_id: str
    display_name: Optional[str] = None
    resource_type: Optional[str] = None
    subscription_id: Optional[str] = None
    resource_group: Optional[str] = None
