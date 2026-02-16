from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple


CANONICAL_CHANGE_SCHEMA_VERSION = "canonical_change.v1"


CanonicalOperationType = str  # create|update|delete|unknown (kept as str for forward compatibility)


@dataclass(frozen=True)
class CanonicalRepo:
    uri: Optional[str] = None
    revision: Optional[str] = None


@dataclass(frozen=True)
class CanonicalOperation:
    resource_type: Optional[str]
    operation: CanonicalOperationType
    resource_id: Optional[str]
    source: str  # 'diff' | 'user' | 'unknown'


@dataclass(frozen=True)
class CanonicalChange:
    """Canonical change model v1.

    Determinism requirements:
    - No timestamps are generated.
    - Operations are sorted deterministically.
    - Unknown fields are explicit, not inferred.

    The intent is that the same normalized diff will produce identical JSON bytes
    when serialized via `to_canonical_json(...)`.
    """

    schema_version: str
    change_id: str
    repo: CanonicalRepo
    environment: Optional[str]
    operations: Tuple[CanonicalOperation, ...]
    unknowns: Tuple[str, ...]
    provenance: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        # Keep a stable top-level key set.
        return {
            "schema_version": self.schema_version,
            "change_id": self.change_id,
            "repo": asdict(self.repo),
            "environment": self.environment,
            "operations": [asdict(op) for op in self.operations],
            "unknowns": list(self.unknowns),
            "provenance": dict(self.provenance),
        }


def _normalize_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        return None
    v = value.strip()
    return v if v else None


def _normalize_env(value: Any) -> Optional[str]:
    v = _normalize_str(value)
    if v is None:
        return None
    vv = v.lower()
    if vv in {"prod", "production"}:
        return "prod"
    if vv in {"stage", "staging"}:
        return "staging"
    if vv in {"dev", "development"}:
        return "dev"
    if vv in {"test", "testing"}:
        return "test"
    return vv


def _normalize_operation(value: Any) -> str:
    v = _normalize_str(value)
    if v is None:
        return "unknown"
    vv = v.lower()
    if vv in {"create", "add"}:
        return "create"
    if vv in {"update", "modify", "change"}:
        return "update"
    if vv in {"delete", "destroy", "remove"}:
        return "delete"
    return "unknown"


def _stable_json_bytes(value: Any) -> bytes:
    # Canonical JSON form used for hashing.
    # - sort_keys => stable key ordering
    # - separators => stable whitespace
    s = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return s.encode("utf-8")


def compute_change_id_from_normalized_diff(normalized_diff: Mapping[str, Any]) -> str:
    """Compute a deterministic change_id from a normalized diff object."""

    digest = hashlib.sha256(_stable_json_bytes(normalized_diff)).hexdigest()
    return f"sha256:{digest}"


def _sort_operations(ops: Sequence[CanonicalOperation]) -> Tuple[CanonicalOperation, ...]:
    return tuple(
        sorted(
            ops,
            key=lambda o: (
                o.resource_type or "",
                o.resource_id or "",
                o.operation or "",
                o.source or "",
            ),
        )
    )


def canonicalize_from_normalized_diff(normalized_diff: Mapping[str, Any]) -> CanonicalChange:
    """Canonicalize a normalized diff into CanonicalChange v1.

    Expected (minimal) input shape:
    {
      "repo": {"uri": "...", "revision": "..."},
      "environment": "prod"|"staging"|...,  # optional
      "operations": [
        {"resource_type": "...", "operation": "update", "resource_id": "..."}
      ],
      # anything else can be carried in provenance
    }

    If operations cannot be derived deterministically, they must be omitted and
    `unknowns` should include "operations".
    """

    unknowns = []

    repo_obj = normalized_diff.get("repo")
    repo_uri = None
    repo_rev = None
    if isinstance(repo_obj, Mapping):
        repo_uri = _normalize_str(repo_obj.get("uri"))
        repo_rev = _normalize_str(repo_obj.get("revision"))

    env = _normalize_env(normalized_diff.get("environment"))
    if env is None:
        unknowns.append("environment")

    raw_ops = normalized_diff.get("operations")
    ops: list[CanonicalOperation] = []
    if raw_ops is None:
        unknowns.append("operations")
    elif not isinstance(raw_ops, list):
        unknowns.append("operations")
    else:
        for idx, rop in enumerate(raw_ops):
            if not isinstance(rop, Mapping):
                unknowns.append(f"operations[{idx}]")
                continue

            resource_id = _normalize_str(rop.get("resource_id") or rop.get("resourceId"))
            resource_type = _normalize_str(rop.get("resource_type") or rop.get("resourceType"))
            op_kind = _normalize_operation(rop.get("operation"))

            if resource_id is None:
                unknowns.append(f"operations[{idx}].resource_id")

            ops.append(
                CanonicalOperation(
                    resource_type=resource_type,
                    operation=op_kind,
                    resource_id=resource_id,
                    source="diff",
                )
            )

    # Deterministic id: prefer explicit change_id if present, else hash of whole input.
    change_id = _normalize_str(normalized_diff.get("change_id") or normalized_diff.get("changeId"))
    if change_id is None:
        change_id = compute_change_id_from_normalized_diff(normalized_diff)

    # Provenance: carry only non-schema keys to avoid duplicating and to keep deterministic.
    provenance = {}
    for k, v in normalized_diff.items():
        if k in {"schema_version", "change_id", "changeId", "repo", "environment", "operations"}:
            continue
        provenance[k] = v

    return CanonicalChange(
        schema_version=CANONICAL_CHANGE_SCHEMA_VERSION,
        change_id=change_id,
        repo=CanonicalRepo(uri=repo_uri, revision=repo_rev),
        environment=env,
        operations=_sort_operations(ops),
        unknowns=tuple(sorted(set(unknowns))),
        provenance=provenance,
    )


def canonicalize_from_user_input(
    *,
    resource_id: str,
    resource_type: Optional[str] = None,
    operation: str = "update",
    environment: Optional[str] = None,
    repo_uri: Optional[str] = None,
    repo_revision: Optional[str] = None,
    change_id: Optional[str] = None,
) -> CanonicalChange:
    """Canonicalize explicit user-provided resource identity into CanonicalChange v1."""

    unknowns = []
    rid = _normalize_str(resource_id)
    if rid is None:
        unknowns.append("operations[0].resource_id")

    env = _normalize_env(environment)
    if env is None:
        unknowns.append("environment")

    op = CanonicalOperation(
        resource_type=_normalize_str(resource_type),
        operation=_normalize_operation(operation),
        resource_id=rid,
        source="user",
    )

    normalized = {
        "repo": {"uri": _normalize_str(repo_uri), "revision": _normalize_str(repo_revision)},
        "environment": env,
        "operations": [
            {
                "resource_type": op.resource_type,
                "operation": op.operation,
                "resource_id": op.resource_id,
                "source": op.source,
            }
        ],
    }

    if change_id is None:
        change_id = compute_change_id_from_normalized_diff(normalized)

    return CanonicalChange(
        schema_version=CANONICAL_CHANGE_SCHEMA_VERSION,
        change_id=change_id,
        repo=CanonicalRepo(uri=_normalize_str(repo_uri), revision=_normalize_str(repo_revision)),
        environment=env,
        operations=_sort_operations([op]),
        unknowns=tuple(sorted(set(unknowns))),
        provenance={"input": "user"},
    )


def to_canonical_json(change: CanonicalChange, *, indent: Optional[int] = 2) -> str:
    """Serialize CanonicalChange into a deterministic JSON string.

    Using sort_keys ensures byte-for-byte stable ordering.
    """

    return json.dumps(
        change.to_dict(),
        sort_keys=True,
        indent=indent,
        ensure_ascii=False,
    )
