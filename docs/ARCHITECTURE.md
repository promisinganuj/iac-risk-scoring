# Architecture

## System Overview

```
                ┌──────────────────────────────────────────────┐
                │            Three interfaces, one engine       │
                │                                              │
                │  CLI (cli.py)     FastAPI (api/)     MCP     │
                │  --service-name   POST /assess-pr    Server  │
                │  --resource-id    POST /assess       (agent) │
                └──────────┬───────────────────────────────────┘
                           │
                           ▼
                ┌──────────────────────────────────────────────┐
                │              engine.py — pipeline             │
                │                                              │
                │  1. Entity Resolution                        │
                │     ResourceSpec → ResolvedEntityRef          │
                │                                              │
                │  2. Evidence Expansion                       │
                │     Providers run sequentially, populating    │
                │     a shared evidence dict                    │
                │                                              │
                │  3. Deterministic Scoring                    │
                │     scoring.py — 14 rules, no DB queries     │
                │                                              │
                │  4. Report Generation                        │
                │     JSON + Markdown, stable ordering          │
                └──────────┬──────────────┬────────────────────┘
                           │              │
                           ▼              ▼
              ┌────────────────┐  ┌──────────────────┐
              │ EntityRepository│  │ EvidenceProviders │
              │ (Neo4j / CSV)  │  │                  │
              └────────────────┘  │ Neo4jEvidence    │
                                  │   graph context  │
                                  │   blast radius   │
                                  │                  │
                                  │ KustoEvidence    │
                                  │   IcM incidents  │
                                  │   SafeFly deploys│
                                  │   Service Tree   │
                                  │   blast radius†  │
                                  └────────┬─────────┘
                                           │
                                  ┌────────┴─────────┐
                                  │ KustoSourceRegistry│
                                  │ (kusto_sources.yaml)│
                                  │                    │
                                  │  icm        cluster│
                                  │  service_tree   〃  │
                                  │  safefly        〃  │
                                  └────────────────────┘
```

## Pipeline Stages

### 1. Entity Resolution

Converts user-provided identity to a `ResolvedEntityRef`.

| Mode | Input | Resolution Method |
|------|-------|-------------------|
| Neo4j | `--resource-id` | Cypher query against Neo4j graph |
| Kusto-only | `--service-name` | Direct pass-through (service name is the identity) |
| PR API | `repo_uri` + `target_branch` | Service name from request or repo-name fallback |

### 2. Evidence Expansion

Providers run **sequentially** — later providers can use context set by
earlier ones. The recommended order:

1. **Neo4jEvidenceProvider** — sets `service_name`, `service_id`,
   `services_impacted`, graph-based evidence.
2. **KustoEvidenceProvider** — uses `service_name` to query IcM/SafeFly.
   Internally runs a 5-phase pipeline:
   - Phase 1: Scalar IcM/SafeFly queries (k1, k4–k6, k8–k9)
   - Phase 2: k7 service tree lookup → ServiceId + metadata
   - Phase 3: k10 subscription mapping using ServiceId from phase 2
   - Phase 4: k12 source repos enrichment using ServiceId from phase 2
   - Phase 5: Blast radius derivation from Service Tree metadata
     (`services_impacted`, `critical_services` from k7 ServiceLevel/
     IsExternalFacing; `peer_resource_count` marked unknown)

   > † In Kusto-only mode, `services_impacted` is always 1 (single
   > service resolution). `critical_services` is derived from k7's
   > `ServiceLevel` and `IsExternalFacing` fields. `peer_resource_count`
   > requires Azure Resource Graph and is left as unknown (0 points).

### 3. Scoring

`score_change()` in `scoring.py` applies 14 deterministic rules to the
evidence dict. No DB calls are made during scoring. See
[SCORING_MODEL.md](SCORING_MODEL.md) for the full factor reference.

### 4. Report Generation

`build_report_json()` produces a stable JSON structure. 
`render_markdown_report()` converts it to human-readable Markdown.
Both use deterministic key ordering.

## Data Flow Modes

### Kusto-only (no Neo4j required)

```
CLI: --service-name "My Service" --data-source kusto --environment prod
 │
 ▼
ResolvedEntityRef(display_name="My Service")
 │
 ▼
KustoEvidenceProvider
 ├─ Phase 1: k1, k4, k5, k6 (IcM) → k8, k9 (SafeFly)
 ├─ Phase 2: k7 (Service Tree) → ServiceId + metadata
 ├─ Phase 3: k10 (subscriptions)
 ├─ Phase 4: k12 (source repos)
 └─ Phase 5: blast radius (services_impacted, critical_services)
 │
 ▼
score_change() → ScoreResult → report
```

### Hybrid (Neo4j + Kusto)

```
CLI: --resource-id "res-alpha-app" --data-source hybrid --environment prod
 │
 ▼
Neo4jHttpEntityRepository.resolve()
 │
 ▼
Neo4jEvidenceProvider   →   KustoEvidenceProvider
 (graph blast radius)        (incident + deploy data)
 │
 ▼
score_change() → ScoreResult → report
```

### PR Assessment API

```
POST /api/v1/assess-pr
 │  { repo_uri, target_branch, service_name?, ... }
 │
 ▼
detect_environment(target_branch) → environment
 │
 ▼
_build_providers(data_source) → [Neo4j?, Kusto?]
 │
 ▼
assess_with_providers() → EngineResult
 │
 ▼
PRAssessmentResponse (JSON)
```

## Key Design Decisions

### KQL Query Allowlist

All Kusto queries are defined as frozen `KqlQuerySpec` dataclasses in
`kusto_allowlist.py`. This ensures:

- **Audit trail** — every query is named, versioned, and has a description.
- **Injection safety** — parameters are validated against type, length, and
  safe-character regexes (`_SAFE_GUID_RE`, `_SAFE_NAME_RE`) before
  interpolation.
- **Bounded results** — every query has `max_take` and `default_take`.
- **Source routing** — each query declares its `source` (icm, safefly,
  service_tree), and `KustoSourceRegistry` routes it to the correct
  cluster/database from `kusto_sources.yaml`.

### Pluggable Evidence Providers

The `EvidenceProvider` protocol allows adding new data sources without
changing the engine:

```python
class EvidenceProvider(Protocol):
    @property
    def name(self) -> str: ...

    def populate(
        self,
        resolved: ResolvedEntityRef,
        evidence: Dict[str, Any],
        *,
        as_of: Optional[date] = None,
    ) -> ProviderResult: ...
```

Each provider returns a `ProviderResult` with the keys it populated, the
queries it ran, and the keys it couldn't resolve (unknowns).

### Deterministic Scoring

The scoring engine is a pure function: `evidence dict → ScoreResult`.

Determinism guarantees:
- No timestamps generated during scoring.
- No randomness or floating-point arithmetic (integer only).
- Operations are sorted canonically.
- JSON serialization uses `sort_keys=True`.
- If evidence is missing, the factor scores 0 (conservative, not a guess).

### Canonical Change Model

The `CanonicalChange` (v1) provides a deterministic intermediate
representation of "what is changing." See
[canonical_change_model_v1.md](../risk_scoring/canonical_change_model_v1.md)
for the full schema. Key rules:

- `change_id` is `sha256:<hex>` of the normalized input.
- Operations are sorted by `(resource_type, resource_id, operation, source)`.
- Unknown/ambiguous fields are explicitly listed in the `unknowns` array.

## Project Structure

```
risk_scoring/              Core scoring engine (Python package)
├── engine.py              Pipeline orchestrator
├── scoring.py             14 deterministic scoring rules
├── models.py              ResourceSpec, ResolvedEntityRef, CandidateEntity
├── canonical_change.py    Canonical change model v1
├── evidence_provider.py   EvidenceProvider protocol + run_providers()
├── kusto_evidence_provider.py   Kusto-backed provider (IcM, SafeFly, Service Tree)
├── neo4j_evidence_provider.py   Neo4j-backed provider (graph blast radius)
├── kusto_allowlist.py     Allowlisted KQL queries (k1–k12)
├── evidence_allowlist.py  Allowlisted Cypher queries
├── kusto_client.py        Azure Data Explorer SDK wrapper
├── kusto_source_config.py KustoSourceRegistry (YAML → cluster routing)
├── config/
│   └── kusto_sources.yaml Cluster/database mappings per source
├── reporting.py           JSON + Markdown report generation
├── cli.py                 CLI entry point
├── mcp_server.py          MCP server for AI agents
└── tests/                 250 tests

api/                       FastAPI HTTP interface
├── main.py                /assess, /assess-pr, /health endpoints
├── models.py              Pydantic request/response models
├── config.py              Settings (env vars)
└── tests/

approach2-using-existing-graph/   Neo4j infrastructure
├── docker-compose.yml     Neo4j container
├── sample-data/           Mock data (JSON + CSV)
├── scripts/               Import Cypher + shell scripts
└── docs/                  CLI test results, hierarchy validation

docs/                      Project documentation
├── VISION.md              North star, strategy, phases
├── SCORING_MODEL.md       All 14 factors with thresholds
└── ARCHITECTURE.md        This file

.github/agents/            AI agent instructions
├── risk-assessment-via-app.agent.md   App-based agent
└── risk-assessment-via-mcp.agent.md   MCP-based agent
```

## Authentication

| Backend | Local Dev | Production |
|---------|-----------|------------|
| Neo4j | `NEO4J_PASSWORD` env var | Same (Neo4j basic auth) |
| Kusto | `KUSTO_AUTH_METHOD=az_cli` | `KUSTO_AUTH_METHOD=mi` + `KUSTO_MI_CLIENT_ID` |

## Dependencies

Core: Python 3.12+, `azure-kusto-data`, `azure-identity`, `fastapi`,
`uvicorn`, `httpx`.

Optional: Neo4j 5 (Docker), `neo4j` Python driver.

See [requirements.txt](../requirements.txt) and [pyproject.toml](../pyproject.toml).
