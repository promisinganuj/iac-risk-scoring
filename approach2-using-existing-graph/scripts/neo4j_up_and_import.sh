#!/usr/bin/env bash
set -euo pipefail

# Starts Neo4j via docker compose and imports CSVs using scripts/neo4j_import.cypher.
# Usage:
#   export NEO4J_PASSWORD='password'
#   ./scripts/neo4j_up_and_import.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

NEO4J_PASSWORD="${NEO4J_PASSWORD:-password}"
NEO4J_HTTP_PORT="${NEO4J_HTTP_PORT:-7474}"
NEO4J_BOLT_PORT="${NEO4J_BOLT_PORT:-7687}"

export NEO4J_PASSWORD
export NEO4J_HTTP_PORT
export NEO4J_BOLT_PORT

echo "Starting Neo4j container..."
docker compose up -d neo4j

echo "Waiting for Neo4j to accept connections..."
for i in {1..60}; do
  if docker exec neo4j-risk cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1;" >/dev/null 2>&1; then
    break
  fi
  sleep 2
  if [[ $i -eq 60 ]]; then
    echo "Neo4j did not become ready in time." >&2
    exit 1
  fi
done

echo "Running import script..."
docker exec -i neo4j-risk cypher-shell -u neo4j -p "$NEO4J_PASSWORD" -f /import/neo4j_import.cypher

echo "Done. Open Neo4j Browser at http://localhost:$NEO4J_HTTP_PORT"
echo "Browser connection (Bolt): neo4j://localhost:$NEO4J_BOLT_PORT"
