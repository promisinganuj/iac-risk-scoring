from __future__ import annotations

from dataclasses import asdict
from typing import Callable, Optional

from risk_scoring.errors import AmbiguousMatchError, NotFoundError
from risk_scoring.models import CandidateEntity, ResolvedEntityRef, ResourceSpec
from risk_scoring.repository import EntityRepository


def resolve_azure_resource(
    repo: EntityRepository,
    spec: ResourceSpec,
    *,
    non_interactive: bool,
    chooser: Optional[Callable[[list[CandidateEntity]], int]] = None,
    limit: int = 25,
) -> ResolvedEntityRef:
    """Resolve a ResourceSpec into a single AzureResource entity.

    Determinism rules:
    - Prefer exact match on `resourceId`.
    - If no exact match, attempt case-insensitive match on `resourceId`.
    - If still not found and attributes are provided, query by attributes.
    - If multiple candidates remain:
      - In non-interactive mode: raise with a stable, sorted candidate list.
      - In interactive mode: use the provided chooser callback to select.

    The caller is responsible for providing a chooser that is consistent with the
    desired UX (VS Code picker, CLI prompt, etc.).
    """

    rid = (spec.resource_id or "").strip()
    if not rid:
        raise NotFoundError("resource_id is required")

    # 1) Exact match
    candidates = repo.find_azure_resources_by_resource_id(rid, limit=limit)

    # 2) Case-insensitive fallback
    if not candidates:
        rid_lower = rid.lower()
        # bounded scan: use attributes query on repository side where possible;
        # for now we call attributes query only if we have something to filter.
        # Repositories that can do case-insensitive lookup should implement it
        # behind find_azure_resources_by_attributes.
        all_like = repo.find_azure_resources_by_attributes(
            resource_type=spec.resource_type,
            subscription_id=spec.subscription_id,
            resource_group=spec.resource_group,
            display_name=None,
            limit=limit,
        )
        candidates = [c for c in all_like if c.resource_id.lower() == rid_lower]

    # 3) Attributes query fallback (only if user provided something beyond rid)
    if not candidates:
        if any([spec.resource_type, spec.subscription_id, spec.resource_group]):
            candidates = repo.find_azure_resources_by_attributes(
                resource_type=spec.resource_type,
                subscription_id=spec.subscription_id,
                resource_group=spec.resource_group,
                display_name=None,
                limit=limit,
            )

    if not candidates:
        raise NotFoundError(f"AzureResource not found for resourceId={rid!r}")

    if len(candidates) == 1:
        return _to_ref(candidates[0])

    # Deterministic ordering for candidate list
    ordered = sorted(
        candidates,
        key=lambda c: (
            (c.resource_id or ""),
            (c.subscription_id or ""),
            (c.resource_group or ""),
            (c.resource_type or ""),
            (c.display_name or ""),
        ),
    )

    if non_interactive:
        raise AmbiguousMatchError(
            f"Ambiguous resourceId={rid!r}; {len(ordered)} candidates",
            candidates=[asdict(c) for c in ordered],
        )

    if chooser is None:
        raise AmbiguousMatchError(
            "Interactive resolution requires a chooser callback",
            candidates=[asdict(c) for c in ordered],
        )

    idx = chooser(ordered)
    if idx < 0 or idx >= len(ordered):
        raise AmbiguousMatchError(
            f"Invalid selection index {idx}",
            candidates=[asdict(c) for c in ordered],
        )

    return _to_ref(ordered[idx])


def _to_ref(candidate: CandidateEntity) -> ResolvedEntityRef:
    return ResolvedEntityRef(
        label=candidate.label,
        resource_id=candidate.resource_id,
        display_name=candidate.display_name,
        resource_type=candidate.resource_type,
        subscription_id=candidate.subscription_id,
        resource_group=candidate.resource_group,
    )
