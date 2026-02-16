from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from risk_scoring.evidence_client import CypherExecutor


class McpNeo4jExecutor(CypherExecutor):
    """Read-only Cypher executor backed by MCP Neo4j server.
    
    This executor is designed for agent/LLM contexts where MCP tools are available.
    For CLI usage, Neo4jHttpExecutor is recommended as it doesn't require the MCP runtime.
    
    The MCP server configuration is managed by VS Code (.vscode/mcp.json) and handles
    authentication automatically via the .env file.
    
    Benefits over HTTP executor:
    - No credential management needed in code
    - Simpler configuration (credentials in .env managed by MCP)
    - Consistent with GitHub agent approach
    - Works in agent contexts without environment setup
    
    Limitations:
    - Requires MCP infrastructure (VS Code or MCP-aware runtime)
    - Not suitable for standalone CLI without MCP client library
    """

    def __init__(self, mcp_tool_function: Optional[callable] = None):
        """Initialize MCP executor.
        
        Args:
            mcp_tool_function: Optional callable that invokes the MCP read_neo4j_cypher tool.
                             If None, will attempt to detect MCP tools at runtime.
                             In agent contexts, this should be provided by the agent framework.
        
        Note: MCP connection is established when tools are invoked, not at init time.
        """
        self._mcp_tool_function = mcp_tool_function

    def run_readonly(self, cypher: str, params: Mapping[str, Any]) -> List[Dict[str, Any]]:
        """Execute a read-only Cypher query via MCP Neo4j server.
        
        Args:
            cypher: Read-only Cypher query string
            params: Query parameters
            
        Returns:
            List of result rows as dictionaries
            
        Raises:
            RuntimeError: If MCP tools are not available or query fails
            
        Note:
            This executor is primarily for agent/LLM contexts. For CLI usage,
            use Neo4jHttpExecutor instead with --use-http flag.
        """
        if self._mcp_tool_function is None:
            raise NotImplementedError(
                "MCP executor requires MCP tool infrastructure. "
                "This executor is designed for agent/LLM contexts where MCP tools are available.\n\n"
                "For CLI usage, use Neo4jHttpExecutor instead:\n"
                "  python -m risk_scoring --resource-id <id> --environment prod --use-http\n\n"
                "For agent contexts, provide mcp_tool_function when initializing McpNeo4jExecutor:\n"
                "  executor = McpNeo4jExecutor(mcp_tool_function=mcp_neo4j_databas_read_neo4j_cypher)\n\n"
                "To enable MCP executor:\n"
                "1. Ensure MCP Neo4j server is configured in .vscode/mcp.json\n"
                "2. Pass the MCP tool function when creating the executor\n"
                "3. Or use Neo4jHttpExecutor for standalone CLI usage"
            )
        
        try:
            # Call MCP tool via the provided function
            # The function should handle the MCP protocol and return results
            result = self._mcp_tool_function(query=cypher, params=dict(params))
            
            # MCP Neo4j tool returns results in a structured format
            # The exact format depends on the MCP server implementation
            if not isinstance(result, list):
                # Handle different MCP response formats
                if isinstance(result, dict):
                    # Check for common Neo4j result structures
                    if "rows" in result:
                        return result["rows"]
                    elif "data" in result:
                        return result["data"]
                    elif "records" in result:
                        return result["records"]
                    else:
                        raise RuntimeError(f"Unexpected MCP result structure: {list(result.keys())}")
                else:
                    raise RuntimeError(f"Unexpected MCP result type: {type(result)}")
            
            return result
            
        except Exception as e:
            raise RuntimeError(
                f"MCP Neo4j query failed. Ensure Neo4j is running and MCP server is connected. "
                f"Error: {e}\n\n"
                f"Fallback option: Use Neo4jHttpExecutor with --use-http flag"
            ) from e
