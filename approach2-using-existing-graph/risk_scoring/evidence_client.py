from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Mapping

from risk_scoring.evidence_allowlist import QuerySpec, get_query, validate_params


class CypherExecutor(ABC):
    """Abstract executor for running read-only Cypher queries.

    Implementations may use:
    - Neo4j Bolt driver
    - Neo4j MCP server
    - cypher-shell (not recommended for library usage)

    This layer intentionally does not know about connection details.
    """

    @abstractmethod
    def run_readonly(self, cypher: str, params: Mapping[str, Any]) -> List[Dict[str, Any]]:
        raise NotImplementedError


class EvidenceClient:
    def __init__(self, executor: CypherExecutor):
        self._executor = executor

    def run(self, query_id: str, params: Mapping[str, Any]) -> List[Dict[str, Any]]:
        query: QuerySpec = get_query(query_id)
        validated = validate_params(query, params)
        return self._executor.run_readonly(query.cypher, validated)
