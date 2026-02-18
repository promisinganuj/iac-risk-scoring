#!/usr/bin/env python3
"""MCP server for risk scoring engine.

Exposes the risk scoring engine as an MCP tool for AI agents.

Architecture:
    User -> Agent -> mcp_risk_scoring_assess_resource(resource_id, env, ...)
              |
         JSON/Markdown report -> Agent formats -> User

This server provides the **same** risk assessment functionality as the CLI
and FastAPI interfaces, but optimized for agent consumption via MCP protocol.

Supports three data-source modes (matching CLI):
- **neo4j** (legacy): entity resolution + evidence from Neo4j graph.
- **kusto**: evidence from Kusto (IcM, SafeFly).  Requires ``service_name``
  or ``repo_uri`` (resolved to service via k11).
- **hybrid**: Neo4j for entity resolution + graph evidence, Kusto for
  IcM/SafeFly evidence.  Both backends must be configured.
- **auto** (default): detect available backends from env vars / config.

Three interfaces, one engine:
    - CLI: Human terminal interaction
    - FastAPI: HTTP clients, CI/CD, webhooks
    - MCP Server: AI agents (GitHub, VS Code)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from datetime import date
from typing import Any, Dict, List, Optional

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

from risk_scoring.engine import assess_resource_change, assess_with_providers
from risk_scoring.errors import AmbiguousMatchError, NotFoundError
from risk_scoring.evidence_client import CypherExecutor, EvidenceClient
from risk_scoring.evidence_provider import EvidenceProvider
from risk_scoring.models import ResolvedEntityRef, ResourceSpec
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

_DATA_SOURCES = ("auto", "kusto", "neo4j", "hybrid")
_ENVIRONMENTS = ("prod", "staging", "dev", "test")
_OUTPUT_FORMATS = ("json", "markdown", "both")


# ---------------------------------------------------------------------------
# Backend detection helpers (mirrored from cli.py)
# ---------------------------------------------------------------------------

def _neo4j_available() -> bool:
    """Return True if Neo4j credentials are configured."""
    return bool(os.environ.get("NEO4J_PASSWORD"))


def _kusto_available() -> bool:
    """Return True if Kusto can be used."""
    return bool(os.environ.get("KUSTO_AUTH_METHOD"))


def _resolve_data_source(requested: str) -> str:
    """Resolve 'auto' to a concrete data source, or validate the request."""
    if requested != "auto":
        return requested

    neo4j = _neo4j_available()
    kusto = _kusto_available()

    if neo4j and kusto:
        return "hybrid"
    if kusto:
        return "kusto"
    if neo4j:
        return "neo4j"
    raise ValueError(
        "Cannot auto-detect data source. "
        "Set NEO4J_PASSWORD for Neo4j or KUSTO_AUTH_METHOD for Kusto."
    )


# ---------------------------------------------------------------------------
# Provider construction (mirrored from cli.py)
# ---------------------------------------------------------------------------

def _build_providers(
    data_source: str,
) -> tuple[
    List[EvidenceProvider],
    Optional[Neo4jHttpEntityRepository],
]:
    """Construct evidence providers for the resolved data source.

    Returns ``(providers, repo)``.  ``repo`` is non-None only when Neo4j is
    part of the pipeline and entity resolution is needed.
    """
    providers: List[EvidenceProvider] = []
    repo: Optional[Neo4jHttpEntityRepository] = None

    # --- Neo4j ---
    if data_source in ("neo4j", "hybrid"):
        config = Neo4jHttpConfig.from_env()
        executor: CypherExecutor = Neo4jHttpExecutor(config)
        evidence_client = EvidenceClient(executor)
        repo = Neo4jHttpEntityRepository(config)

        from risk_scoring.neo4j_evidence_provider import Neo4jEvidenceProvider

        providers.append(Neo4jEvidenceProvider(evidence_client))
        logger.info("Neo4j evidence provider enabled")

    # --- Kusto ---
    if data_source in ("kusto", "hybrid"):
        from risk_scoring.kusto_evidence_provider import KustoEvidenceProvider
        from risk_scoring.kusto_source_config import KustoSourceRegistry

        registry = KustoSourceRegistry.from_yaml()
        providers.append(KustoEvidenceProvider(registry))
        logger.info(
            "Kusto evidence provider enabled (sources: %s)",
            ", ".join(registry.list_sources()),
        )

    if not providers:
        raise ValueError(
            f"No evidence providers available for data_source={data_source}"
        )

    return providers, repo


# ---------------------------------------------------------------------------
# Repo URI -> service name resolution (mirrored from cli.py)
# ---------------------------------------------------------------------------

def _resolve_repo_to_service(repo_uri: str) -> Optional[str]:
    """Resolve a repo URI to a service name via Kusto k11 query."""
    try:
        from risk_scoring.kusto_source_config import KustoSourceRegistry

        registry = KustoSourceRegistry.from_yaml()
        return registry.resolve_service_from_repo(repo_uri)
    except Exception as exc:
        logger.warning("Repo -> service resolution failed: %s", exc, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Tool listing
# ---------------------------------------------------------------------------

@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available MCP tools."""
    return [
        Tool(
            name="assess_resource",
            description=(
                "Assess operational risk for an Azure resource change. "
                "Returns a deterministic risk score (0-100) with evidence-based "
                "factors, blast radius analysis, and actionable recommendations. "
                "Supports multiple data sources (neo4j, kusto, hybrid, auto) and "
                "multiple identity inputs (resource_id, service_name, repo_uri). "
                "Uses the same engine as CLI and FastAPI interfaces."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "resource_id": {
                        "type": "string",
                        "description": (
                            "Azure resource identifier (e.g., 'res-alpha-app', "
                            "'vm-prod-web-01', or full ARM resource ID). "
                            "Required for neo4j/hybrid data sources. "
                            "At least one of resource_id, service_name, or "
                            "repo_uri must be provided."
                        ),
                    },
                    "service_name": {
                        "type": "string",
                        "description": (
                            "Service name as it appears in IcM / Service Tree "
                            "(OwningTenantName). Required for kusto-only if "
                            "resource_id is not an ARM ID. "
                            "At least one of resource_id, service_name, or "
                            "repo_uri must be provided."
                        ),
                    },
                    "repo_uri": {
                        "type": "string",
                        "description": (
                            "Azure DevOps repo URI. Resolves to a service name "
                            "via Service Tree k11 lookup (requires Kusto). "
                            "At least one of resource_id, service_name, or "
                            "repo_uri must be provided."
                        ),
                    },
                    "environment": {
                        "type": "string",
                        "enum": list(_ENVIRONMENTS),
                        "description": (
                            "Target environment for risk assessment. "
                            "Affects base risk score: prod=highest, test=lowest."
                        ),
                    },
                    "data_source": {
                        "type": "string",
                        "enum": list(_DATA_SOURCES),
                        "default": "auto",
                        "description": (
                            "Evidence backend to use. "
                            "'auto' detects available backends from env vars. "
                            "'kusto' uses IcM/SafeFly data. "
                            "'neo4j' uses the graph database. "
                            "'hybrid' combines both. Default: auto."
                        ),
                    },
                    "output_format": {
                        "type": "string",
                        "enum": list(_OUTPUT_FORMATS),
                        "default": "json",
                        "description": (
                            "Output format: 'json' (structured), 'markdown' "
                            "(human-readable), or 'both'. Default: json."
                        ),
                    },
                },
                "required": ["environment"],
            },
        )
    ]


# ---------------------------------------------------------------------------
# Error helper
# ---------------------------------------------------------------------------

def _create_error_response(error_type: str, message: str, detail: str = "") -> Dict[str, Any]:
    """Create structured error response matching FastAPI format."""
    return {
        "error": error_type,
        "message": message,
        "detail": detail,
        "success": False,
    }


# ---------------------------------------------------------------------------
# Core assessment implementation
# ---------------------------------------------------------------------------

def _assess_resource_impl(
    *,
    resource_id: Optional[str] = None,
    service_name: Optional[str] = None,
    repo_uri: Optional[str] = None,
    environment: str,
    data_source: str = "auto",
    output_format: str = "json",
) -> str:
    """Run the full assessment pipeline (mirrors CLI ``main()``).

    Returns the formatted output string (JSON, Markdown, or both).

    Raises:
        ValueError: Invalid inputs or configuration.
        Neo4jHttpError: Database connection failure.
        NotFoundError: Resource not found in graph.
        AmbiguousMatchError: Multiple matching resources.
    """

    # --- Validate environment ---
    if environment not in _ENVIRONMENTS:
        raise ValueError(
            f"Invalid environment '{environment}'. "
            f"Must be one of: {', '.join(_ENVIRONMENTS)}"
        )

    # --- Validate identity ---
    if not resource_id and not service_name and not repo_uri:
        raise ValueError(
            "At least one of resource_id, service_name, or repo_uri is required."
        )

    # --- Resolve data source ---
    data_source = _resolve_data_source(data_source)
    logger.info("Resolved data source: %s", data_source)

    # --- Repo URI -> service name resolution (k11) ---
    if repo_uri:
        if data_source not in ("kusto", "hybrid"):
            raise ValueError(
                "repo_uri requires Kusto (data_source=kusto or hybrid) "
                "for Service Tree k11 lookup."
            )
        resolved_service = _resolve_repo_to_service(repo_uri)
        if resolved_service is None:
            raise ValueError(
                f"Could not resolve repo_uri '{repo_uri}' to a service "
                "in Service Tree. Use service_name to supply it directly."
            )
        logger.info("Resolved repo %s -> service %r", repo_uri, resolved_service)
        service_name = resolved_service

    # --- Validate flag combinations ---
    if data_source == "kusto" and not service_name and not resource_id:
        raise ValueError(
            "data_source=kusto requires service_name, repo_uri, "
            "or resource_id (ARM resource ID enables ARG queries)."
        )
    if data_source in ("neo4j", "hybrid") and not resource_id:
        raise ValueError(
            f"data_source={data_source} requires resource_id "
            "for Neo4j entity resolution."
        )

    # --- Build pipeline ---
    change_context = ChangeContext.create(environment=environment)
    report_id_base = resource_id or service_name or repo_uri or "unknown"
    report_id = f"mcp-{report_id_base}-{environment}"

    if data_source == "neo4j" and not service_name:
        # Pure legacy path -- existing assess_resource_change()
        result = _run_legacy_neo4j(
            resource_id=resource_id,
            change_context=change_context,
            report_id=report_id,
        )
    else:
        # Provider-based path
        result = _run_providers(
            resource_id=resource_id,
            service_name=service_name,
            repo_uri=repo_uri,
            data_source=data_source,
            change_context=change_context,
            report_id=report_id,
        )

    logger.info(
        "Assessment complete: %s/100 (%s)",
        result.score.risk_score,
        result.score.risk_level,
    )

    # --- Format output ---
    return _format_output(result, output_format)


# ---------------------------------------------------------------------------
# Pipeline runners (mirrored from cli.py)
# ---------------------------------------------------------------------------

def _run_legacy_neo4j(
    *,
    resource_id: str,
    change_context: ChangeContext,
    report_id: str,
):
    """Legacy Neo4j-only assessment (no Kusto)."""
    config = Neo4jHttpConfig.from_env()
    executor = Neo4jHttpExecutor(config)
    repo = Neo4jHttpEntityRepository(config)
    evidence_client = EvidenceClient(executor)
    resource = ResourceSpec(resource_id=resource_id)

    return assess_resource_change(
        repo=repo,
        evidence_client=evidence_client,
        resource=resource,
        change=change_context,
        as_of=date.today(),
        report_id=report_id,
    )


def _run_providers(
    *,
    resource_id: Optional[str],
    service_name: Optional[str],
    repo_uri: Optional[str],
    data_source: str,
    change_context: ChangeContext,
    report_id: str,
):
    """Provider-based assessment (kusto, hybrid, or neo4j+service_name)."""
    providers, repo = _build_providers(data_source)

    resource: Optional[ResourceSpec] = None
    resolved: Optional[ResolvedEntityRef] = None

    if resource_id and repo is not None:
        # Neo4j resolution path
        resource = ResourceSpec(resource_id=resource_id)
    else:
        # Kusto-only or service-name supplied: build a synthetic resolved ref
        rid = resource_id or service_name or "unknown"
        display = service_name or resource_id
        label = "Service"
        if resource_id and not service_name:
            label = "AzureResource"
        elif repo_uri and not resource_id:
            label = "Repository"
        resolved = ResolvedEntityRef(
            label=label,
            resource_id=rid,
            display_name=display,
        )

    return assess_with_providers(
        repo=repo,
        providers=providers,
        resource=resource,
        resolved=resolved,
        change=change_context,
        as_of=date.today(),
        report_id=report_id,
    )


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------

def _format_output(result, output_format: str) -> str:
    """Format the EngineResult according to the requested output format."""
    if output_format == "json":
        return json.dumps(result.report_json, indent=2)
    elif output_format == "markdown":
        return result.report_markdown
    else:  # both
        return (
            f"# JSON Report\n\n```json\n{result.report_json_string()}\n```\n\n"
            f"# Markdown Report\n\n{result.report_markdown}"
        )


# ---------------------------------------------------------------------------
# MCP call_tool handler
# ---------------------------------------------------------------------------

@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool invocation from agents."""
    if name != "assess_resource":
        raise ValueError(f"Unknown tool: {name}")

    # Extract arguments
    resource_id = arguments.get("resource_id")
    service_name = arguments.get("service_name")
    repo_uri = arguments.get("repo_uri")
    environment = arguments.get("environment")
    data_source = arguments.get("data_source", "auto")
    output_format = arguments.get("output_format", "json")

    # --- Quick validation ---------------------------------------------------
    if not environment:
        return [TextContent(
            type="text",
            text=json.dumps(_create_error_response(
                "validation_error",
                "Missing required parameter: environment",
                "Please specify one of: prod, staging, dev, test",
            )),
        )]

    if not resource_id and not service_name and not repo_uri:
        return [TextContent(
            type="text",
            text=json.dumps(_create_error_response(
                "validation_error",
                "At least one of resource_id, service_name, or repo_uri is required",
                "Provide resource_id for Neo4j lookups, service_name for Kusto, "
                "or repo_uri to auto-resolve via Service Tree.",
            )),
        )]

    # --- Run assessment ------------------------------------------------------
    try:
        output = _assess_resource_impl(
            resource_id=resource_id,
            service_name=service_name,
            repo_uri=repo_uri,
            environment=environment,
            data_source=data_source,
            output_format=output_format,
        )
        return [TextContent(type="text", text=output)]

    except ValueError as e:
        return [TextContent(
            type="text",
            text=json.dumps(_create_error_response(
                "validation_error",
                str(e),
                "Please check your input parameters and try again",
            )),
        )]

    except NotFoundError as e:
        identifier = resource_id or service_name or repo_uri
        return [TextContent(
            type="text",
            text=json.dumps(_create_error_response(
                "not_found",
                f"Resource '{identifier}' not found",
                str(e) or "The resource may not exist or hasn't been ingested yet",
            )),
        )]

    except AmbiguousMatchError as e:
        candidates = "\n".join(
            f"  - {c.get('resource_id', 'unknown')} "
            f"(service: {c.get('service_id', 'unknown')})"
            for c in (e.candidates or [])[:5]
        )
        return [TextContent(
            type="text",
            text=json.dumps(_create_error_response(
                "ambiguous_match",
                f"Multiple resources match '{resource_id}'",
                f"Please specify the full resource ID.\n"
                f"Matching resources:\n{candidates}",
            )),
        )]

    except Neo4jHttpError as e:
        return [TextContent(
            type="text",
            text=json.dumps(_create_error_response(
                "database_error",
                "Failed to connect to Neo4j database",
                f"{e}\n\nTroubleshooting:\n"
                "1. Check if Neo4j container is running: docker ps | grep neo4j\n"
                "2. Start Neo4j: cd approach2-using-existing-graph && "
                "docker compose up -d neo4j\n"
                "3. Verify connection at http://localhost:7474",
            )),
        )]

    except Exception as e:
        logger.exception("Unexpected error during risk assessment")
        return [TextContent(
            type="text",
            text=json.dumps(_create_error_response(
                "internal_error",
                "An unexpected error occurred during risk assessment",
                f"{type(e).__name__}: {e}",
            )),
        )]


# ---------------------------------------------------------------------------
# Server entry point
# ---------------------------------------------------------------------------

async def main():
    """Run the MCP server."""
    logger.info("Starting Risk Scoring MCP server")
    logger.info(
        "Tool: assess_resource(resource_id|service_name|repo_uri, "
        "environment, data_source, output_format)"
    )

    # Log available backends
    backends = []
    if _neo4j_available():
        try:
            config = Neo4jHttpConfig.from_env()
            logger.info(
                "Neo4j configured: %s (database: %s)",
                config.http_url,
                config.database,
            )
            backends.append("neo4j")
        except Exception as e:
            logger.warning("Neo4j config error: %s", e)
    else:
        logger.info("Neo4j: not configured (NEO4J_PASSWORD not set)")

    if _kusto_available():
        logger.info("Kusto: configured (KUSTO_AUTH_METHOD=%s)", os.environ.get("KUSTO_AUTH_METHOD"))
        backends.append("kusto")
    else:
        logger.info("Kusto: not configured (KUSTO_AUTH_METHOD not set)")

    if backends:
        logger.info("Available backends: %s", ", ".join(backends))
    else:
        logger.warning(
            "No backends configured. Set NEO4J_PASSWORD and/or "
            "KUSTO_AUTH_METHOD in your .env file."
        )

    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
