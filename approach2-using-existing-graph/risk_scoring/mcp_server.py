#!/usr/bin/env python3
"""MCP server for risk scoring engine.

Exposes the risk scoring engine as an MCP tool for AI agents.

Architecture:
    User → Agent → mcp_risk_scoring_assess_resource(resource_id, env)
              ↓
         JSON report → Agent formats markdown → User

This server provides the same risk assessment functionality as the CLI and
FastAPI interfaces, but optimized for agent consumption via MCP protocol.

Three interfaces, one engine:
    - CLI: Human terminal interaction
    - FastAPI: HTTP clients, CI/CD, webhooks
    - MCP Server: AI agents (GitHub, VS Code)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import date
from typing import Any, Dict, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from risk_scoring.engine import assess_resource_change
from risk_scoring.errors import AmbiguousMatchError, NotFoundError
from risk_scoring.evidence_client import EvidenceClient
from risk_scoring.models import ResourceSpec
from risk_scoring.neo4j_http import Neo4jHttpConfig, Neo4jHttpError
from risk_scoring.neo4j_http_executor import Neo4jHttpExecutor
from risk_scoring.neo4j_http_repository import Neo4jHttpEntityRepository
from risk_scoring.scoring import ChangeContext

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("risk_scoring.mcp_server")

# Create MCP server instance
app = Server("risk-scoring")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="assess_resource",
            description=(
                "Assess operational risk for an Azure resource change. "
                "Returns deterministic risk score (0-100) with evidence-based factors, "
                "blast radius analysis, and actionable recommendations. "
                "Uses the same engine as CLI and FastAPI interfaces."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_id": {
                        "type": "string",
                        "description": (
                            "Azure resource identifier (e.g., 'res-alpha-app', 'vm-prod-web-01'). "
                            "This is the resourceName field from the Neo4j AzureResource nodes."
                        ),
                    },
                    "environment": {
                        "type": "string",
                        "enum": ["prod", "staging", "dev", "test"],
                        "description": (
                            "Target environment for risk assessment. "
                            "Affects base risk score: prod=highest, test=lowest."
                        ),
                    },
                },
                "required": ["resource_id", "environment"],
            },
        )
    ]


def _create_error_response(error_type: str, message: str, detail: str = "") -> Dict[str, Any]:
    """Create structured error response matching FastAPI format."""
    return {
        "error": error_type,
        "message": message,
        "detail": detail,
        "success": False,
    }


def _assess_resource_impl(resource_id: str, environment: str) -> Dict[str, Any]:
    """Implementation of assess_resource tool.
    
    Args:
        resource_id: Azure resource identifier
        environment: Target environment (prod, staging, dev, test)
    
    Returns:
        JSON report dict with risk assessment
        
    Raises:
        ValueError: Invalid inputs
        Neo4jHttpError: Database connection failure
        NotFoundError: Resource not found
        AmbiguousMatchError: Multiple matching resources
    """
    # Validate environment
    valid_envs = {"prod", "staging", "dev", "test"}
    if environment not in valid_envs:
        raise ValueError(
            f"Invalid environment '{environment}'. Must be one of: {', '.join(sorted(valid_envs))}"
        )
    
    # Create Neo4j config from environment variables
    try:
        config = Neo4jHttpConfig.from_env()
    except Exception as e:
        raise Neo4jHttpError(f"Failed to load Neo4j configuration: {e}")
    
    # Initialize executor, repository, and evidence client
    executor = Neo4jHttpExecutor(config)
    repo = Neo4jHttpEntityRepository(config)
    evidence_client = EvidenceClient(executor)
    
    # Create resource spec and change context
    resource = ResourceSpec(resource_id=resource_id)
    change = ChangeContext.create(environment=environment)
    
    # Run risk assessment
    logger.info(f"Assessing resource '{resource_id}' in environment '{environment}'")
    result = assess_resource_change(
        repo=repo,
        evidence_client=evidence_client,
        resource=resource,
        change=change,
        as_of=None,
        report_id=None,
    )
    
    logger.info(
        f"Assessment complete: {result.score.risk_score}/100 ({result.score.risk_level})"
    )
    
    return result.report_json


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool invocation from agents."""
    if name != "assess_resource":
        raise ValueError(f"Unknown tool: {name}")
    
    # Extract arguments
    resource_id = arguments.get("resource_id")
    environment = arguments.get("environment")
    
    if not resource_id:
        error_response = _create_error_response(
            "validation_error",
            "Missing required parameter: resource_id",
            "Please provide a valid Azure resource identifier"
        )
        return [TextContent(type="text", text=str(error_response))]
    
    if not environment:
        error_response = _create_error_response(
            "validation_error",
            "Missing required parameter: environment",
            "Please specify one of: prod, staging, dev, test"
        )
        return [TextContent(type="text", text=str(error_response))]
    
    try:
        # Run assessment
        report = _assess_resource_impl(resource_id, environment)
        
        # Return JSON report as text
        import json
        return [TextContent(
            type="text",
            text=json.dumps(report, indent=2)
        )]
        
    except ValueError as e:
        # Input validation error
        error_response = _create_error_response(
            "validation_error",
            str(e),
            "Please check your input parameters and try again"
        )
        return [TextContent(type="text", text=str(error_response))]
        
    except NotFoundError as e:
        # Resource not found
        error_response = _create_error_response(
            "not_found",
            f"Resource '{resource_id}' not found in Neo4j graph",
            str(e) or "The resource may not exist or hasn't been ingested yet"
        )
        return [TextContent(type="text", text=str(error_response))]
        
    except AmbiguousMatchError as e:
        # Multiple matches
        candidates = "\n".join(
            f"  - {c.get('resource_id', 'unknown')} (service: {c.get('service_id', 'unknown')})"
            for c in (e.candidates or [])[:5]
        )
        error_response = _create_error_response(
            "ambiguous_match",
            f"Multiple resources match '{resource_id}'",
            f"Please specify the full resource ID.\nMatching resources:\n{candidates}"
        )
        return [TextContent(type="text", text=str(error_response))]
        
    except Neo4jHttpError as e:
        # Database connection error
        error_response = _create_error_response(
            "database_error",
            "Failed to connect to Neo4j database",
            f"{str(e)}\n\nTroubleshooting:\n"
            "1. Check if Neo4j container is running: docker ps | grep neo4j\n"
            "2. Start Neo4j: cd approach2-using-existing-graph && docker compose up -d neo4j\n"
            "3. Verify connection at http://localhost:7474"
        )
        return [TextContent(type="text", text=str(error_response))]
        
    except Exception as e:
        # Unexpected error
        logger.exception("Unexpected error during risk assessment")
        error_response = _create_error_response(
            "internal_error",
            "An unexpected error occurred during risk assessment",
            f"{type(e).__name__}: {str(e)}"
        )
        return [TextContent(type="text", text=str(error_response))]


async def main():
    """Run the MCP server."""
    logger.info("Starting Risk Scoring MCP server")
    logger.info("Tool: assess_resource(resource_id, environment)")
    
    # Verify Neo4j configuration
    try:
        config = Neo4jHttpConfig.from_env()
        logger.info(f"Neo4j configured: {config.http_url} (database: {config.database})")
    except Exception as e:
        logger.warning(f"Neo4j configuration incomplete: {e}")
        logger.warning("Ensure NEO4J_* environment variables are set in .env file")
    
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
