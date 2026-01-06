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

Re-running the import is intended to be safe (uses constraints + `MERGE`), but properties may be updated on re-run.

## 3) Open Neo4j Browser

Open:

- Neo4j Browser: `http://localhost:${NEO4J_HTTP_PORT:-7474}`
- Bolt URL: `neo4j://localhost:${NEO4J_BOLT_PORT:-7687}`

Login:

- Username: `neo4j`
- Password: `$NEO4J_PASSWORD`

## 4) Minimal validation queries

Run these from your shell:

```bash
docker exec neo4j-risk cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "MATCH (s:Service) RETURN count(s) AS services;"
docker exec neo4j-risk cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "MATCH (i:Incident) RETURN count(i) AS incidents;"
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
