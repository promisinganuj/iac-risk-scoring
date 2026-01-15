from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable, Optional

from risk_scoring.models import CandidateEntity


class EntityRepository(ABC):
    """Abstract repository for resolving ResourceSpec -> graph entities."""

    @abstractmethod
    def find_azure_resources_by_resource_id(
        self, resource_id: str, *, limit: int
    ) -> list[CandidateEntity]:
        raise NotImplementedError

    @abstractmethod
    def find_azure_resources_by_attributes(
        self,
        *,
        resource_type: Optional[str],
        subscription_id: Optional[str],
        resource_group: Optional[str],
        display_name: Optional[str],
        limit: int,
    ) -> list[CandidateEntity]:
        raise NotImplementedError


class InMemoryRepository(EntityRepository):
    """Simple repository for unit tests."""

    def __init__(self, candidates: Iterable[CandidateEntity]):
        self._candidates = list(candidates)

    def find_azure_resources_by_resource_id(
        self, resource_id: str, *, limit: int
    ) -> list[CandidateEntity]:
        rid = resource_id
        results = [c for c in self._candidates if c.resource_id == rid]
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
        results = list(self._candidates)
        if resource_type is not None:
            results = [c for c in results if (c.resource_type or "") == resource_type]
        if subscription_id is not None:
            results = [c for c in results if (c.subscription_id or "") == subscription_id]
        if resource_group is not None:
            results = [c for c in results if (c.resource_group or "") == resource_group]
        if display_name is not None:
            results = [c for c in results if (c.display_name or "") == display_name]
        return results[:limit]
