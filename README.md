# IaC Risk Scoring

Deterministic risk scoring engine for Azure infrastructure-as-code changes.

Given a service or resource identity, the engine gathers evidence from
production data sources (IcM incidents, SafeFly deployments, Service Tree
subscriptions), applies deterministic scoring rules, and produces a
structured risk report with a 0–100 score and factor breakdown.

**Goal:** Reduce outages by surfacing risk signals at PR time — before
changes reach production. See [docs/VISION.md](docs/VISION.md) for the
full strategy and north-star.

## Quick Start

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt --native-tls

# Copy and configure environment
cp .env.template .env
# edit .env with your Neo4j and/or Kusto credentials

# Kusto-only assessment (no Neo4j required)
python -m risk_scoring --service-name "Azure App Service (Payments)" \
    --environment prod --data-source kusto

# Or with Neo4j sample data
cd approach2-using-existing-graph
export NEO4J_PASSWORD='password'
./scripts/neo4j_up_and_import.sh
cd ..
python -m risk_scoring --resource-id "res-alpha-app" --environment prod
```

## CLI Usage

```
python -m risk_scoring [identity flags] --environment <env> [options]
```

### Identity flags (at least one required)

| Flag | Description |
|------|-------------|
| `--resource-id ID` | Azure resource ID (Neo4j entity resolution) |
| `--service-name NAME` | Service name matching IcM `OwningTenantName` (Kusto-only, no Neo4j needed) |
| `--repo-uri URI` | Azure DevOps repo URI (resolved to service via k11 Service Tree lookup; requires Kusto) |

### Data source

| `--data-source` | Behaviour |
|-----------------|-----------|
| `auto` *(default)* | Detect available backends from env vars / config |
| `kusto` | IcM + SafeFly + Service Tree evidence via Kusto only (requires `--service-name` or `--repo-uri`) |
| `neo4j` | Graph-based evidence only |
| `hybrid` | Neo4j for entity resolution + graph evidence, then Kusto for IcM/SafeFly/Service Tree |

### Examples

```bash
# Kusto-only (recommended — no Neo4j required)
python -m risk_scoring --service-name "Azure Database for PostgreSQL - Flexible Server" \
    --environment prod --data-source kusto

# Neo4j-only
python -m risk_scoring --resource-id "res-alpha-app" --environment prod

# Hybrid: Neo4j + Kusto
python -m risk_scoring --resource-id "res-alpha-app" --environment prod \
    --data-source hybrid

# JSON output to file
python -m risk_scoring --resource-id "res-alpha-app" --environment prod \
    --output-format json --output-file report.json

# Repo URI (resolves to service via Service Tree k11 lookup)
python -m risk_scoring --repo-uri "https://dev.azure.com/org/project/_git/payments" \
    --environment prod --data-source kusto

# Repo URI (resolves to service via Service Tree k11 lookup)
python -m risk_scoring --repo-uri "https://dev.azure.com/org/project/_git/payments" \
    --environment prod --data-source kusto

# Verbose logging
python -m risk_scoring --service-name "My Service" --environment prod --verbose
```

## API Usage

Three interfaces share the same engine pipeline:

| Interface | Usage |
|-----------|-------|
| **CLI** | `python -m risk_scoring --service-name <name> --environment <env>` |
| **FastAPI** | `POST /api/v1/assess` (resource-based) or `POST /api/v1/assess-pr` (PR-based) |
| **MCP Server** | `python -m risk_scoring.mcp_server` (AI agent consumption) |

### PR Assessment API

```bash
# Start the API server
source .env && uvicorn api.main:app --reload

# Assess a PR
curl -X POST http://localhost:8000/api/v1/assess-pr \
  -H "Content-Type: application/json" \
  -d '{
    "repo_uri": "https://dev.azure.com/org/project/_git/payments",
    "target_branch": "main",
    "service_name": "Azure App Service (Payments)"
  }'
```

The `target_branch` is automatically mapped to an environment (`main` → `prod`,
`release/*` → `prod`, `staging` → `staging`, etc.). Interactive docs at
`http://localhost:8000/docs`.

### Environment variables

| Variable | Purpose |
|----------|---------|
| `NEO4J_PASSWORD` | Neo4j password (enables Neo4j backend) |
| `NEO4J_HTTP_URL` | Neo4j HTTP endpoint (default: `http://localhost:7474`) |
| `KUSTO_AUTH_METHOD` | `az_cli` (local dev) or `mi` (managed identity) |
| `KUSTO_SOURCES_PATH` | Custom path to `kusto_sources.yaml` (optional) |
| `KUSTO_MI_CLIENT_ID` | Managed identity client ID (production) |

## Architecture

```
CLI / FastAPI / MCP Server
         │
         ▼
    engine.py ── pipeline ──────────────────────────
    │ 1. Resolve  →  2. Evidence  →  3. Score  →  4. Report │
    ─────────────────────────────────────────────────────────
         │                │
         ▼                ▼
    EntityRepository    EvidenceProviders
    (Neo4j / CSV)       ├── Neo4jEvidenceProvider (graph, blast radius)
                        └── KustoEvidenceProvider
                             ├── IcM (incidents, outages, MTTM)
                             ├── SafeFly (deployments, failures)
                             ├── Service Tree (ServiceId, subscriptions)
                             └── Blast radius (services, critical svc)
```

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full pipeline,
data flow modes, and design decisions.

## Scoring Model

14 deterministic factors (model version `0.1`) across six categories:

| Category | Factors | Max Points |
|----------|---------|------------|
| Environment risk | Production penalty | 20 |
| Blast radius | Services, critical services, subscriptions | 50 |
| Incident history | Outages, open IcMs, MTTM, recurrence | 37 |
| Deployment signals | Frequency, stage failures | 25 |
| Change characteristics | Destructive operations | 10 |
| Dependency depth | Artifacts, peers, templates | 28 |

Score range: 0–100 (capped). Levels: **LOW** (0–33), **MEDIUM** (34–66),
**HIGH** (67–100).

See [docs/SCORING_MODEL.md](docs/SCORING_MODEL.md) for all factor
thresholds, evidence keys, and data sources.

## Development

```bash
# Run all tests (~270 tests)
python -m pytest risk_scoring/tests/ api/tests/ -v

# Start FastAPI server
source .env && uvicorn api.main:app --reload

# Start MCP server (for AI agents)
python -m risk_scoring.mcp_server
```

## Documentation

| Document | Description |
|----------|-------------|
| [docs/VISION.md](docs/VISION.md) | North star, strategy, phases, success metrics |
| [docs/SCORING_MODEL.md](docs/SCORING_MODEL.md) | All 14 scoring factors with thresholds and evidence keys |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Pipeline, data flow modes, design decisions, project structure |
| [risk_scoring/canonical_change_model_v1.md](risk_scoring/canonical_change_model_v1.md) | Canonical change model schema (v1) |
| [approach2-using-existing-graph/](approach2-using-existing-graph/) | Neo4j setup, sample data, import scripts |

## License

See [LICENSE](./LICENSE).
