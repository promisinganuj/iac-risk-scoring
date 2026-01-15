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

The risk scoring CLI tool is now available in the `risk_scoring` package.

### Quick Start

```bash
# Load environment variables
export $(cat .env | xargs)

# Run risk assessment for a resource
python3 -m risk_scoring --resource-id "res-alpha-app" --environment prod
```

### Usage

```bash
python3 -m risk_scoring --resource-id <RESOURCE_ID> --environment <ENV> [OPTIONS]

Required arguments:
  --resource-id          Azure resource ID (e.g., "res-alpha-app")
  --environment          Environment: prod, staging, dev, or test

Optional arguments:
  --output-format        Output format: json, markdown (default), or both
  --output-file          Write output to file instead of stdout
  --use-http             Force HTTP executor (default in CLI context)
  --verbose              Enable debug logging
```

### Examples

**Basic risk assessment (markdown output)**:
```bash
python3 -m risk_scoring --resource-id "res-alpha-app" --environment prod
```

**JSON output to file**:
```bash
python3 -m risk_scoring \
  --resource-id "res-beta-api" \
  --environment staging \
  --output-format json \
  --output-file report.json
```

**Verbose output for debugging**:
```bash
python3 -m risk_scoring \
  --resource-id "res-delta-k8s" \
  --environment prod \
  --verbose
```

### Output Formats

- **markdown** (default): Human-readable report with sections for summary, factors, evidence, and unknowns
- **json**: Machine-readable structured data for integration with other tools
- **both**: Combined JSON + Markdown in a single output

### Architecture

```
┌─────────────┐
│ Sample Data │  CSV files (azure_resources.csv, icm.csv, etc.)
└──────┬──────┘
       │ Import
       ▼
┌─────────────┐
│   Neo4j     │  Graph database (Docker)
│   Graph     │  - Nodes: Resources, Services, Incidents, Deployments
│             │  - Relationships: BELONGS_TO, HAS_INCIDENT, etc.
└──────┬──────┘
       │ Query (HTTP or MCP)
       ▼
┌─────────────┐
│  CLI Tool   │  risk_scoring package
│             │  1. Entity Resolution
│             │  2. Evidence Gathering (allowlisted queries)
│             │  3. Deterministic Scoring
│             │  4. Report Generation
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Risk Report │  JSON and/or Markdown output
└─────────────┘
```

### How It Works

1. **Entity Resolution**: Resolves the resource ID to a node in the Neo4j graph
2. **Evidence Gathering**: Executes allowlisted Cypher queries to gather context:
   - Service relationships
   - Recent incidents
   - Deployment history
   - Resource metadata
3. **Risk Scoring**: Applies deterministic scoring rules based on 7 factors:
   - Production environment (+20 points)
   - Blast radius (services impacted, +0-25 points)
   - Critical services impacted (+0-15 points)
   - Recent outages (+0-10 points)
   - Open incidents (+0-5 points)
   - Deployment frequency (+0-10 points)
   - Destructive operations (+0-10 points)
4. **Report Generation**: Produces structured JSON and/or markdown output

Risk levels: LOW (0-39), MEDIUM (40-69), HIGH (70-100)

## 7) Risk scoring from agents (MCP executor)

For AI agents and LLMs with MCP support, the `McpNeo4jExecutor` provides direct access to Neo4j via the MCP server.

### Agent Usage

```python
from risk_scoring.mcp_executor import McpNeo4jExecutor
from risk_scoring.evidence_client import EvidenceClient
from risk_scoring.engine import assess_resource_change
from risk_scoring.models import ResourceSpec
from risk_scoring.scoring import ChangeContext

# In agent context, mcp_tool_function is available
def mcp_neo4j_query(query, params):
    # Agent invokes MCP tool: mcp_neo4j-databas_read_neo4j_cypher
    return mcp_tool_result

# Create MCP executor (no credentials needed)
executor = McpNeo4jExecutor(mcp_tool_function=mcp_neo4j_query)
evidence_client = EvidenceClient(executor)

# Run risk assessment (repository needs HTTP executor)
result = assess_resource_change(
    repo=repo,  # Use HTTP-based repository
    evidence_client=evidence_client,
    resource=ResourceSpec(resource_id="res-alpha-app"),
    change=ChangeContext.create(environment="prod")
)

print(result.report_markdown)
```

### MCP vs HTTP Executor

| Feature | MCP Executor | HTTP Executor |
|---------|--------------|---------------|
| **Use Case** | AI agent/LLM contexts | Standalone CLI, automation scripts |
| **Credentials** | Not required (MCP handles auth) | Requires NEO4J_* env vars |
| **Availability** | Agent runtime only | Always available |
| **CLI Default** | No (requires MCP infrastructure) | Yes |

The CLI uses HTTP executor by default since MCP tools require agent infrastructure not available in standalone execution.

## 8) Scripts overview

### `scripts/neo4j_up_and_import.sh`

Starts Neo4j Docker container and imports sample data from CSV files.

```bash
./scripts/neo4j_up_and_import.sh
```

What it does:
1. Starts `neo4j-risk` Docker container using `docker-compose.yml`
2. Waits for Neo4j to be ready (HTTP endpoint check)
3. Executes `scripts/neo4j_import.cypher` to:
   - Create constraints (unique identifiers)
   - Load CSV data into nodes (MERGE for idempotency)
   - Create relationships between nodes

**Idempotent**: Safe to re-run. Uses `MERGE` operations to avoid duplicates.

### `scripts/validate_import.sh`

Validates that the Neo4j import completed successfully.

```bash
./scripts/validate_import.sh
```

What it checks:
- Node counts for all entity types (Services, Incidents, Resources, etc.)
- Relationship counts between nodes
- Sample service with connected entities

Expected output: Counts matching the sample dataset (12 services, 12 incidents, etc.)

### `scripts/neo4j_import.cypher`

Cypher script containing all import logic:
- Constraint creation (unique keys)
- CSV file loading (`LOAD CSV`)
- Node creation (`MERGE`)
- Relationship creation between nodes

This is the source of truth for the graph schema and data model.

## 9) Natural-language risk questions (playbook)

For brainstorming and smoke exploration of the Neo4j MCP server (read-only), see:

- `risk_advisor/queries.md`

Key constraints for the MVP:
- Read-only graph access (`MATCH/RETURN` only)
- Template-only queries (do not execute user-provided Cypher)
- Bounded retrieval (use `LIMIT`, keep traversal depth small)
