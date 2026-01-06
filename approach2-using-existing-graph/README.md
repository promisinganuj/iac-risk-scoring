# Approach 2 (existing graph): Neo4j MCP config

## Environment variables

The Neo4j MCP server is configured in `.vscode/mcp.json` and expects these env vars:

- `NEO4J_URI`
- `NEO4J_USERNAME`
- `NEO4J_PASSWORD`
- `NEO4J_DATABASE`

### Option A: Load from `.env`

From this folder:

```bash
cp .env.template .env
set -a
source .env
set +a
```

Then launch VS Code from the same shell (so it inherits the env):

```bash
code ..
```

### Option B: Export in your shell

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=please-change-me
export NEO4J_DATABASE=neo4j
```
