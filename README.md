# IaC Risk Scoring

Deterministic risk scoring engine for Azure infrastructure-as-code changes.

Given a service or resource identity, the engine gathers evidence from
production data sources (IcM incidents, SafeFly deployments, Service Tree
subscriptions, Azure Resource Graph), applies deterministic scoring rules,
and produces a structured risk report with a 0–100 score and factor breakdown.

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
# edit .env with your credentials (Kusto and/or Neo4j)

# Kusto-only assessment (recommended — no Neo4j required)
python -m risk_scoring --service-name "Azure App Service (Payments)" \
    --environment prod --data-source kusto

# Or with Neo4j sample data (legacy)
cd approach2-using-existing-graph
export NEO4J_PASSWORD='password'
./scripts/neo4j_up_and_import.sh
cd ..
python -m risk_scoring --resource-id "res-alpha-app" --environment prod \
    --data-source neo4j
```

## CLI Usage

```
python -m risk_scoring [identity flags] [options]
```

### Identity flags (at least one required)

| Flag | Description |
|------|-------------|
| `--resource-id ID` | Azure resource ID (Neo4j entity resolution, or ARM resource ID for ARG queries) |
| `--service-name NAME` | Service name matching IcM `OwningTenantName` (Kusto-only, no Neo4j needed) |
| `--repo-uri URI` | Azure DevOps repo URI (resolved to service via k11 Service Tree lookup; requires Kusto) |

### Options

| Flag | Description |
|------|-------------|
| `--environment {prod,staging,dev,test}` | Environment (optional, shown in report) |
| `--data-source {auto,kusto,neo4j,hybrid}` | Evidence backend (default: `auto`) |
| `--output-format {json,markdown,both}` | Output format (default: `markdown`) |
| `--output-file PATH` | Write output to file instead of stdout |
| `--use-http` | Force HTTP Neo4j executor |
| `--verbose` | Enable verbose debug logging |

### Data source

| `--data-source` | Behaviour |
|-----------------|-----------|
| `auto` *(default)* | Detect available backends from env vars (`KUSTO_AUTH_METHOD`, `NEO4J_PASSWORD`) |
| `kusto` | IcM + SafeFly + Service Tree + ARG evidence via Kusto only (recommended) |
| `neo4j` | Graph-based evidence only (legacy) |
| `hybrid` | Neo4j for entity resolution + graph evidence, then Kusto for IcM/SafeFly/Service Tree |

### Examples

```bash
# Kusto-only (recommended — no Neo4j required)
python -m risk_scoring --service-name "Azure Database for PostgreSQL - Flexible Server" \
    --environment prod --data-source kusto

# Without --environment (optional; report just omits environment context)
python -m risk_scoring --service-name "My Service" --data-source kusto

# Neo4j-only (legacy)
python -m risk_scoring --resource-id "res-alpha-app" --environment prod \
    --data-source neo4j

# Hybrid: Neo4j + Kusto
python -m risk_scoring --resource-id "res-alpha-app" --environment prod \
    --data-source hybrid

# JSON output to file
python -m risk_scoring --resource-id "res-alpha-app" --environment prod \
    --output-format json --output-file report.json

# Repo URI (resolves to service via Service Tree k11 lookup)
python -m risk_scoring --repo-uri "https://dev.azure.com/org/project/_git/payments" \
    --environment prod --data-source kusto

# Resource-ID only (ARG peer count — no service name needed)
python -m risk_scoring \
    --resource-id "/subscriptions/<sub-id>/resourceGroups/<rg>/providers/Microsoft.Web/sites/<app>" \
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
| `KUSTO_AUTH_METHOD` | `az_cli` (local dev) or `mi` (managed identity) — enables Kusto backend |
| `KUSTO_SOURCES_PATH` | Custom path to `kusto_sources.yaml` (optional) |
| `KUSTO_MI_CLIENT_ID` | Managed identity client ID (production) |
| `NEO4J_PASSWORD` | Neo4j password (enables Neo4j backend; legacy) |
| `NEO4J_HTTP_URL` | Neo4j HTTP endpoint (default: `http://localhost:7474`) |

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
    (Kusto / Neo4j*)    ├── KustoEvidenceProvider (primary)
                        │    ├── IcM (incidents, outages, MTTM, severity)
                        │    ├── SafeFly (deployments, failures, caused-outages)
                        │    ├── Service Tree (ServiceId, subscriptions)
                        │    └── ARG (peer resource count)
                        └── Neo4jEvidenceProvider (legacy, optional)
                             └── Graph relationships, blast radius
```

*Neo4j is still supported but is being gradually superseded by Kusto-based
evidence. All 10 scoring factors are available in Kusto-only mode.*

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full pipeline,
data flow modes, and design decisions.

## Scoring Model

10 deterministic factors (model version `0.2`), max 100 points:

| # | Factor | Max Pts | Evidence Key | Source |
|---|--------|---------|--------------|--------|
| 1 | SafeFly-caused outages (180d) | 15 | `safefly_caused_outages_180d` | SafeFly/IcM |
| 2 | Similar past incidents | 12 | `related_incidents` | IcM |
| 3 | Blast radius (subscriptions) | 12 | `subscription_count` | Service Tree |
| 4 | Recent outages (180d) | 10 | `historical_outages_180d` | IcM |
| 5 | Slow incident mitigation (MTTM) | 10 | `avg_mttm_minutes` | IcM |
| 6 | Deployment frequency (30d) | 10 | `deployment_count_30d` | SafeFly |
| 7 | Destructive operations | 10 | `operations` (ChangeContext) | Caller input |
| 8 | High-severity incidents (Sev1/2) | 8 | `sev12_incident_count` | IcM |
| 9 | Peer resources (same ResourceGroup) | 8 | `peer_resource_count` | ARG |
| 10 | Recent active outages (7d) | 5 | `recent_active_outages` | IcM |

**Total maximum: 100 pts.** Risk levels: **LOW** (0–33), **MEDIUM** (34–66),
**HIGH** (67–100).

See [docs/SCORING_MODEL.md](docs/SCORING_MODEL.md) for all 10 factor
thresholds, evidence keys, and data sources.

## Development

```bash
# Run all tests (~384 tests)
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
| [docs/SCORING_MODEL.md](docs/SCORING_MODEL.md) | All 10 scoring factors with thresholds and evidence keys |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Pipeline, data flow modes, design decisions, project structure |
| [risk_scoring/canonical_change_model_v1.md](risk_scoring/canonical_change_model_v1.md) | Canonical change model schema (v1) |
| [approach2-using-existing-graph/](approach2-using-existing-graph/) | Neo4j setup, sample data, import scripts (legacy) |

## License

See [LICENSE](./LICENSE).
