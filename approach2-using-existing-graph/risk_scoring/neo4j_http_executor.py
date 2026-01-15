from __future__ import annotations

from typing import Any, Dict, List, Mapping

from risk_scoring.evidence_client import CypherExecutor
from risk_scoring.neo4j_http import Neo4jHttpConfig, run_cypher_readonly


class Neo4jHttpExecutor(CypherExecutor):
    """Read-only Cypher executor backed by Neo4j's HTTP transactional endpoint."""

    def __init__(self, config: Neo4jHttpConfig):
        self._config = config

    def run_readonly(self, cypher: str, params: Mapping[str, Any]) -> List[Dict[str, Any]]:
        return run_cypher_readonly(config=self._config, cypher=cypher, params=params)
