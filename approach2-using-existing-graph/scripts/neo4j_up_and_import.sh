#!/usr/bin/env bash
set -euo pipefail

# Starts Neo4j via docker compose and imports data using Cypher scripts.
# Usage:
#   cp .env.template .env
#   set -a && source .env && set +a
#   ./scripts/neo4j_up_and_import.sh [json|csv]
#
# Arguments:
#   format: Data format to import (json or csv). Default: json

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

# Parse arguments
DATA_FORMAT="${1:-json}"
if [[ "$DATA_FORMAT" != "json" && "$DATA_FORMAT" != "csv" ]]; then
  echo "Error: Invalid format '$DATA_FORMAT'. Must be 'json' or 'csv'." >&2
  echo "Usage: $0 [json|csv]" >&2
  exit 1
fi

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  source "$ROOT_DIR/.env"
  set +a
fi

NEO4J_PASSWORD="${NEO4J_PASSWORD:-please-change-me}"
NEO4J_HTTP_PORT="${NEO4J_HTTP_PORT:-7474}"
NEO4J_BOLT_PORT="${NEO4J_BOLT_PORT:-7687}"

export NEO4J_PASSWORD
export NEO4J_HTTP_PORT
export NEO4J_BOLT_PORT

echo "Starting Neo4j container..."
docker compose up -d neo4j

echo "Waiting for Neo4j to accept connections..."
last_error=""
for i in {1..60}; do
  if docker exec neo4j-risk cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1;" >/dev/null 2>&1; then
    break
  fi
  last_error="$(docker exec neo4j-risk cypher-shell -u neo4j -p "$NEO4J_PASSWORD" "RETURN 1;" 2>&1 || true)"
  sleep 2
  if [[ $i -eq 60 ]]; then
    echo "Neo4j did not become ready in time." >&2
    if [[ -n "$last_error" ]]; then
      echo "Last error: $last_error" >&2
    fi
    if echo "$last_error" | grep -qi "unauthorized"; then
      echo "Hint: If Neo4j was started before, the password is stored in the docker volume." >&2
      echo "To reset the sample DB and apply a new NEO4J_PASSWORD: docker compose down -v" >&2
    fi
    exit 1
  fi
done

# Select import script based on format
if [[ "$DATA_FORMAT" == "json" ]]; then
  IMPORT_SCRIPT="/import/neo4j_import_json.cypher"
  echo "Running JSON import script..."
else
  IMPORT_SCRIPT="/import/neo4j_import.cypher"
  echo "Running CSV import script..."
fi

docker exec -i neo4j-risk cypher-shell -u neo4j -p "$NEO4J_PASSWORD" -f "$IMPORT_SCRIPT"

echo "Done. Open Neo4j Browser at http://localhost:$NEO4J_HTTP_PORT"
echo "Browser connection (Bolt): neo4j://localhost:$NEO4J_BOLT_PORT"
