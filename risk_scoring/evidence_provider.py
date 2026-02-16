"""Pluggable evidence provider architecture.

Defines the ``EvidenceProvider`` protocol and a runner that merges results
from multiple providers into a single evidence dict for scoring.

Design principles:
- Each provider populates the evidence keys it knows about.
- Missing keys stay ``None`` (graceful degradation).
- Providers run sequentially; later providers can see earlier evidence.
- Every provider records the queries it ran for audit/debug.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple, runtime_checkable

from risk_scoring.graph_expansion import QueryRun
from risk_scoring.models import ResolvedEntityRef


@runtime_checkable
class EvidenceProvider(Protocol):
    """Protocol for evidence providers.

    Each implementation populates a subset of evidence keys by querying
    a data source (Kusto, Neo4j, etc.).
    """

    @property
    def name(self) -> str:
        """Short identifier for logging/audit, e.g. 'neo4j', 'kusto-icm'."""
        ...

    def populate(
        self,
        resolved: ResolvedEntityRef,
        evidence: Dict[str, Any],
        *,
        as_of: Optional[date] = None,
    ) -> ProviderResult:
        """Populate evidence keys in-place and return a result summary.

        Parameters
        ----------
        resolved
            The resolved entity reference (resource_id, service_id, etc.).
        evidence
            Mutable dict of evidence keys. The provider should set the keys
            it is responsible for. Keys already set by an earlier provider
            should NOT be overwritten unless the provider has higher-fidelity
            data.
        as_of
            Reference date for time-window queries. If ``None``, the provider
            should use ``now()`` or mark time-dependent keys as unknown.

        Returns
        -------
        ProviderResult
            Summary of queries run and any keys left unknown.
        """
        ...


@dataclass(frozen=True)
class ProviderResult:
    """Summary of a single provider's execution."""

    provider_name: str
    queries: Tuple[QueryRun, ...]
    populated_keys: Tuple[str, ...]
    unknown_keys: Tuple[str, ...]
    error: Optional[str] = None


@dataclass(frozen=True)
class EvidenceExpansionResult:
    """Merged result from running all evidence providers."""

    evidence: Dict[str, Any]
    provider_results: Tuple[ProviderResult, ...]
    all_queries: Tuple[QueryRun, ...]
    unknowns: Tuple[str, ...]


def run_providers(
    providers: Sequence[EvidenceProvider],
    resolved: ResolvedEntityRef,
    *,
    as_of: Optional[date] = None,
    initial_evidence: Optional[Dict[str, Any]] = None,
) -> EvidenceExpansionResult:
    """Run all providers sequentially and merge evidence.

    Each provider sees the evidence accumulated so far, allowing later
    providers to use context set by earlier ones (e.g. Kusto provider
    can use ``service_id`` set by the Neo4j provider).

    If a provider raises an exception, it is caught and recorded as an
    error in the ``ProviderResult``. The pipeline continues with the
    remaining providers.
    """
    evidence: Dict[str, Any] = dict(initial_evidence or {})
    all_results: List[ProviderResult] = []
    all_queries: List[QueryRun] = []

    for provider in providers:
        try:
            result = provider.populate(resolved, evidence, as_of=as_of)
        except Exception as exc:
            result = ProviderResult(
                provider_name=provider.name,
                queries=(),
                populated_keys=(),
                unknown_keys=(),
                error=f"{type(exc).__name__}: {exc}",
            )
        all_results.append(result)
        all_queries.extend(result.queries)

    # Collect all unknown keys across providers (deduplicated, sorted).
    all_unknowns: set[str] = set()
    populated: set[str] = set()
    for r in all_results:
        all_unknowns.update(r.unknown_keys)
        populated.update(r.populated_keys)
    # A key is truly unknown only if no provider populated it.
    final_unknowns = sorted(all_unknowns - populated)

    return EvidenceExpansionResult(
        evidence=evidence,
        provider_results=tuple(all_results),
        all_queries=tuple(all_queries),
        unknowns=tuple(final_unknowns),
    )
