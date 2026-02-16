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
# edit .env with your Neo4j credentials

# Start Neo4j and import sample data
cd approach2-using-existing-graph
export NEO4J_PASSWORD='password'
./scripts/neo4j_up_and_import.sh
cd ..

# Run risk assessment
python -m risk_scoring --resource-id "res-alpha-app" --environment prod
```

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
    EntityRepository    EvidenceClient
    (Neo4j / CSV)       (Cypher / Kusto)
```

Three interfaces, one engine:
- **CLI**: `python -m risk_scoring --resource-id <id> --environment <env>`
- **FastAPI**: `POST /api/v1/assess` (see `api/`)
- **MCP Server**: AI agent consumption via `risk_scoring.mcp_server`

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
