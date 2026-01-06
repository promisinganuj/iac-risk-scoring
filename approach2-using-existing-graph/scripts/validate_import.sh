#!/usr/bin/env bash
set -euo pipefail

# Validates that Neo4j has been properly populated with sample data.
# Usage:
#   set -a && source .env && set +a
#   ./scripts/validate_import.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  source "$ROOT_DIR/.env"
  set +a
fi

NEO4J_PASSWORD="${NEO4J_PASSWORD:-please-change-me}"

echo "=== Neo4j Data Validation ==="
echo

# Check if Neo4j is running
if ! docker exec neo4j-risk echo "alive" >/dev/null 2>&1; then
  echo "❌ Neo4j container 'neo4j-risk' is not running."
  echo "Run: docker compose up -d neo4j"
  exit 1
fi

# Node counts
echo "Node counts:"
docker exec neo4j-risk cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "MATCH (s:Service) RETURN 'Services' AS type, count(s) AS count
   UNION ALL
   MATCH (i:Incident) RETURN 'Incidents' AS type, count(i) AS count
   UNION ALL
   MATCH (r:AzureResource) RETURN 'Resources' AS type, count(r) AS count
   UNION ALL
   MATCH (d:Deployment) RETURN 'Deployments' AS type, count(d) AS count
   UNION ALL
   MATCH (t:Template) RETURN 'Templates' AS type, count(t) AS count
   UNION ALL
   MATCH (sub:Subscription) RETURN 'Subscriptions' AS type, count(sub) AS count
   UNION ALL
   MATCH (rg:ResourceGroup) RETURN 'ResourceGroups' AS type, count(rg) AS count
   UNION ALL
   MATCH (repo:Repo) RETURN 'Repos' AS type, count(repo) AS count
   UNION ALL
   MATCH (team:Team) RETURN 'Teams' AS type, count(team) AS count
   ORDER BY type;"

echo
echo "Relationship counts:"
docker exec neo4j-risk cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "MATCH ()-[r]->() RETURN type(r) AS relationship, count(r) AS count ORDER BY count DESC;"

echo
echo "Sample Service with relationships:"
docker exec neo4j-risk cypher-shell -u neo4j -p "$NEO4J_PASSWORD" \
  "MATCH (s:Service) 
   WITH s LIMIT 1
   OPTIONAL MATCH (s)-[r1:USES_SUBSCRIPTION]->(sub:Subscription)
   OPTIONAL MATCH (s)-[r2:HAS_REPO]->(repo:Repo)
   OPTIONAL MATCH (s)-[r3:OWNS_RESOURCE]->(res:AzureResource)
   OPTIONAL MATCH (i:Incident)-[r4:AFFECTS_SERVICE]->(s)
   RETURN s.serviceId AS serviceId,
          s.name AS name,
          count(DISTINCT sub) AS subscriptions,
          count(DISTINCT repo) AS repos,
          count(DISTINCT res) AS resources,
          count(DISTINCT i) AS incidents;"

echo
echo "✅ Validation complete!"
