# IaC Risk Scoring

Deterministic risk scoring engine for Azure infrastructure-as-code changes.

Given a resource or service identity, the engine resolves it from a graph database,
expands evidence (incidents, deployments, blast radius), applies deterministic scoring
rules, and produces a structured risk report.

## Quick Start

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt --native-tls

# Copy and configure environment
cp .env.template .env
# edit .env with your Neo4j and/or Kusto credentials

# Start Neo4j and import sample data (optional — not needed for Kusto-only mode)
cd approach2-using-existing-graph
export NEO4J_PASSWORD='password'
./scripts/neo4j_up_and_import.sh
cd ..

# Run risk assessment
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
| `--repo-uri URI` | Azure DevOps repo URI *(placeholder — not yet wired)* |

### Data source

| `--data-source` | Behaviour |
|-----------------|-----------|
| `auto` *(default)* | Detect available backends from env vars / config |
| `kusto` | IcM + SafeFly evidence via Kusto only (requires `--service-name`) |
| `neo4j` | Graph-based evidence only (legacy) |
| `hybrid` | Neo4j for entity resolution + graph evidence, then Kusto for IcM/SafeFly |

### Examples

```bash
# Neo4j-only (legacy)
python -m risk_scoring --resource-id "rg-prod-web-01" --environment prod

# Kusto-only (no Neo4j required)
python -m risk_scoring --service-name "Azure Database for PostgreSQL - Flexible Server" \
    --environment prod --data-source kusto

# Hybrid: Neo4j + Kusto
python -m risk_scoring --resource-id "rg-prod-web-01" --environment prod \
    --data-source hybrid

# JSON output to file
python -m risk_scoring --resource-id "rg-prod-web-01" --environment prod \
    --output-format json --output-file report.json

# Verbose logging
python -m risk_scoring --resource-id "rg-prod-web-01" --environment prod --verbose
```

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
    engine.py (pipeline)
    ┌──────────────────────────────────────────────┐
    │ 1. Entity Resolution  →  2. Evidence Expansion │
    │ 3. Deterministic Scoring  →  4. Report         │
    └──────────────────────────────────────────────┘
         │                    │
         ▼                    ▼
    EntityRepository    EvidenceProviders
    (Neo4j / CSV)       ┌─────────────────────┐
                        │ Neo4jEvidenceProvider│  graph context, blast radius
                        │ KustoEvidenceProvider│  IcM incidents, SafeFly deploys
                        └─────────────────────┘
                                │
                        KustoSourceRegistry
                        (kusto_sources.yaml)
                        ┌─────────────────────┐
                        │ icm         cluster  │
                        │ service_tree cluster  │
                        │ safefly     cluster  │
                        └─────────────────────┘
```

Three interfaces, one engine:
- **CLI**: `python -m risk_scoring --resource-id <id> --environment <env>`
- **FastAPI**: `POST /api/v1/assess` (see `api/`)
- **MCP Server**: AI agent consumption via `risk_scoring.mcp_server`

### Evidence pipeline

Providers run sequentially — later providers can use context set by earlier ones.
The recommended order is Neo4j first (sets `service_name`, `service_id`), then
Kusto (queries IcM/SafeFly using `service_name`).

| Provider | Keys populated | Data source |
|----------|---------------|-------------|
| `Neo4jEvidenceProvider` | service_id, service_name, services_impacted, recent_incidents, recent_deployments | Neo4j graph |
| `KustoEvidenceProvider` | open_icms, avg_mttm_minutes, historical_outages_180d, related_incidents, deployment_count_30d, deployment_stage_failures | Kusto (IcM, SafeFly) |

Kusto queries are defined in `risk_scoring/kusto_allowlist.py`. Each query
specifies a `source` field that maps to a cluster/database pair in
`risk_scoring/config/kusto_sources.yaml`.

## Project Structure

```
risk_scoring/          ← Core scoring engine (Python package)
api/                   ← FastAPI HTTP interface
approach2-using-existing-graph/  ← Neo4j setup, sample data, import scripts
approach1-creating-knowlege-graph/  ← Archived: Azure Cosmos DB experiment
utils/                 ← Archived: Terraform plan parser
```

## Scoring Model

13 deterministic factors covering:
- Environment risk (production penalty)
- Blast radius (services impacted, peer resources)
- Incident history (outages, MTTM, recurrence)
- Deployment signals (frequency, stage failures)
- Change characteristics (destructive operations)
- Dependency depth (artifacts, templates)

Score range: 0–100. Levels: LOW (0–33), MEDIUM (34–66), HIGH (67–100).

## Development

```bash
# Run tests
python -m pytest risk_scoring/tests/

# Start FastAPI server
uvicorn api.main:app --reload

# Start MCP server (for AI agents)
python -m risk_scoring.mcp_server
```

## License

See [LICENSE](./LICENSE).
