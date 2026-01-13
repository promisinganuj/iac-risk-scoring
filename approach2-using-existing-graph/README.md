# Approach 2 (existing graph)

Run Neo4j in Docker, ingest the sample CSV dataset, and query it via the Neo4j MCP server.

## Prerequisites

- Docker Desktop (or Docker Engine) with `docker compose`
- `uv`/`uvx` installed (for running the Neo4j MCP server)
- VS Code with MCP servers support enabled

## 1) Configure environment

From this folder:

```bash
cd /Users/anuj/002-GitHub/iac-risk-scoring/approach2-using-existing-graph
cp .env.template .env
```

Edit `.env` and set at least:

- `NEO4J_PASSWORD`
- (optional) `NEO4J_HTTP_PORT`, `NEO4J_BOLT_PORT`

Load the env vars into your shell:

```bash
set -a
source .env
set +a
```

## 2) Start Neo4j + ingest sample data

The helper script starts Neo4j and runs the import Cypher against the mounted CSVs:

```bash
./scripts/neo4j_up_and_import.sh
```

**Idempotency**: Re-running the import is safe. The script uses Neo4j constraints with `MERGE` operations, so:
- Nodes with the same unique identifiers won't be duplicated
- Properties may be updated on re-run
- Relationships are recreated safely without duplication

## 3) Open Neo4j Browser

Open:

- Neo4j Browser: `http://localhost:${NEO4J_HTTP_PORT:-7474}`
- Bolt URL: `neo4j://localhost:${NEO4J_BOLT_PORT:-7687}`

Login:

- Username: `neo4j`
- Password: `$NEO4J_PASSWORD`

## 4) Minimal validation queries

Validate the import completed successfully:

```bash
./scripts/validate_import.sh
```

This script checks:
- Node counts for all entity types (Service, Incident, AzureResource, etc.)
- Relationship counts between nodes
- Sample service with its connected entities

**Expected node counts from sample data:**
- Services: 12
- Incidents: 12
- Azure Resources: 12
- Deployments: 12
- Templates: 12
- Subscriptions: 7
- Resource Groups: 24
- Repos: 14
- Teams: 12

**Manual validation queries** (run from your shell):

```bash
# Count services
docker exec neo4j-risk cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "MATCH (s:Service) RETURN count(s) AS services;"

# Count incidents
docker exec neo4j-risk cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "MATCH (i:Incident) RETURN count(i) AS incidents;"

# Count resources
docker exec neo4j-risk cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "MATCH (r:AzureResource) RETURN count(r) AS resources;"
```

## 5) Neo4j MCP server (VS Code)

This repo configures the Neo4j MCP server in `.vscode/mcp.json`.

Important: VS Code must be launched from a shell that has `NEO4J_USERNAME`, `NEO4J_PASSWORD`, and `NEO4J_DATABASE` set (see `.env`).

From the same env-loaded shell:

```bash
code ..
```

Then restart the `neo4j-database` MCP server.

## 6) Risk scoring CLI

The graph-based risk scoring CLI is tracked in the Beads issue `approach2-b03` and is not implemented yet.

Once available, this README will be updated with the exact command to run it.

## 7) Natural-language risk questions (playbook)

For brainstorming and smoke exploration of the Neo4j MCP server (read-only), see:

- `risk_advisor/queries.md`

Key constraints for the MVP:
- Read-only graph access (`MATCH/RETURN` only)
- Template-only queries (do not execute user-provided Cypher)
- Bounded retrieval (use `LIMIT`, keep traversal depth small)
