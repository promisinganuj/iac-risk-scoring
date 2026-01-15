# Canonical Change Model v1 (deterministic)

Schema version: `canonical_change.v1`

Purpose:
- Provide a *deterministic* intermediate representation of “what is changing”.
- Serve as the stable input to graph expansion + scoring.
- Avoid inference/guessing: if something can’t be derived deterministically, mark it as unknown.

## Model (v1)

Top-level fields:
- `schema_version` (required): fixed string `canonical_change.v1`
- `change_id` (required): stable identifier (recommended: `sha256:<hex>`)
- `repo` (optional object): `uri`, `revision`
- `environment` (optional string): normalized to `prod|staging|dev|test|<lowercase>`
- `operations` (required list): each operation has:
  - `resource_type` (optional string)
  - `operation` (required string): `create|update|delete|unknown`
  - `resource_id` (optional string)
  - `source` (required string): `diff|user|unknown`
- `unknowns` (required list of strings): explicit unknown/ambiguous fields
- `provenance` (required object): deterministic carry-through of extra metadata

## Determinism rules

1. No timestamps are generated during canonicalization.
2. `operations` are sorted deterministically by `(resource_type, resource_id, operation, source)`.
3. `unknowns` is a sorted unique list.
4. JSON serialization uses `sort_keys=True` so the same input produces byte-for-byte identical JSON.
5. If resource identity can’t be derived deterministically from diff data, do **not** guess:
   - omit/leave `resource_id` as `null`
   - add an entry like `operations[i].resource_id` to `unknowns`

## Input contracts

### Normalized diff → canonical change

The canonicalizer expects an already-normalized diff object (produced by the diff-capture step):

```json
{
  "repo": {"uri": "https://github.com/contoso/payments", "revision": "abc123"},
  "environment": "prod",
  "operations": [
    {"resource_type": "Microsoft.Web/sites", "operation": "update", "resource_id": "res-alpha-app"}
  ]
}
```

If `change_id` is not provided, it is computed deterministically as `sha256` of the normalized diff JSON.

### User input fallback (MVP)

When diff canonicalization is not available/ambiguous, users can provide resource identity:

```json
{
  "schema_version": "canonical_change.v1",
  "change_id": "sha256:...",
  "repo": {"uri": null, "revision": null},
  "environment": "prod",
  "operations": [
    {
      "resource_type": null,
      "operation": "update",
      "resource_id": "res-alpha-app",
      "source": "user"
    }
  ],
  "unknowns": [],
  "provenance": {"input": "user"}
}
```

## Implementation

See `risk_scoring/canonical_change.py` for:
- `canonicalize_from_normalized_diff(...)`
- `canonicalize_from_user_input(...)`
- `to_canonical_json(...)`
