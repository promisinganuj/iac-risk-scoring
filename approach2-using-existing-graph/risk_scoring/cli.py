"""Command-line interface for risk scoring."""

import argparse
import os
import sys
from datetime import date
from typing import Optional

from risk_scoring.engine import assess_resource_change
from risk_scoring.evidence_client import CypherExecutor, EvidenceClient
from risk_scoring.models import ResourceSpec
from risk_scoring.neo4j_http import Neo4jHttpConfig, Neo4jHttpError
from risk_scoring.neo4j_http_executor import Neo4jHttpExecutor
from risk_scoring.neo4j_http_repository import Neo4jHttpEntityRepository
from risk_scoring.scoring import ChangeContext


def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog='risk_scoring',
        description='Assess risk for Azure resource changes using Neo4j graph data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Score a resource change in production environment
  python -m risk_scoring --resource-id "rg-prod-web-01" --environment prod

  # Output as JSON to a file
  python -m risk_scoring --resource-id "rg-prod-web-01" --environment prod \\
      --output-format json --output-file report.json

  # Force HTTP executor instead of MCP
  python -m risk_scoring --resource-id "rg-prod-web-01" --environment prod --use-http

  # Enable verbose debug logging
  python -m risk_scoring --resource-id "rg-prod-web-01" --environment prod --verbose
"""
    )

    # Required arguments
    parser.add_argument(
        '--resource-id',
        required=True,
        help='Azure resource ID to assess (e.g., "rg-prod-web-01")'
    )
    
    parser.add_argument(
        '--environment',
        required=True,
        choices=['prod', 'staging', 'dev', 'test'],
        help='Environment where the resource exists'
    )

    # Optional arguments
    parser.add_argument(
        '--output-format',
        default='markdown',
        choices=['json', 'markdown', 'both'],
        help='Output format (default: markdown)'
    )
    
    parser.add_argument(
        '--output-file',
        help='Write output to file instead of stdout'
    )
    
    parser.add_argument(
        '--use-http',
        action='store_true',
        help='Force HTTP executor instead of MCP (requires NEO4J_* env vars)'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose debug logging'
    )

    return parser


def main(argv: Optional[list] = None) -> int:
    """
    Main entry point for the CLI.
    
    Args:
        argv: Command-line arguments (defaults to sys.argv[1:])
        
    Returns:
        Exit code (0 = success, 1 = error)
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    # Configure logging based on verbose flag
    if args.verbose:
        import logging
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
    
    try:
        # Initialize Neo4j executor
        executor = _create_executor(use_http=args.use_http, verbose=args.verbose)
        
        # Create repository and evidence client
        if args.use_http or not _is_mcp_available():
            # HTTP path requires config for repository too
            config = Neo4jHttpConfig.from_env()
            repo = Neo4jHttpEntityRepository(config)
        else:
            # MCP path: repository also needs to query Neo4j, use HTTP for now
            # TODO: Consider MCP-based repository if needed
            config = Neo4jHttpConfig.from_env()
            repo = Neo4jHttpEntityRepository(config)
        
        evidence_client = EvidenceClient(executor)
        
        # Build inputs
        resource_spec = ResourceSpec(resource_id=args.resource_id)
        change_context = ChangeContext.create(environment=args.environment)
        
        # Run assessment
        result = assess_resource_change(
            repo=repo,
            evidence_client=evidence_client,
            resource=resource_spec,
            change=change_context,
            as_of=date.today(),
            report_id=f"cli-{args.resource_id}-{args.environment}"
        )
        
        # Output results
        _write_output(result, args)
        
        return 0
        
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        return 130  # Standard Unix exit code for SIGINT
    
    except Neo4jHttpError as e:
        print(f"Neo4j configuration error: {e}", file=sys.stderr)
        print("\nEnsure you have set the following environment variables:", file=sys.stderr)
        print("  NEO4J_HTTP_URL (or NEO4J_HOST and NEO4J_HTTP_PORT)", file=sys.stderr)
        print("  NEO4J_USERNAME (default: neo4j)", file=sys.stderr)
        print("  NEO4J_PASSWORD (required)", file=sys.stderr)
        print("  NEO4J_DATABASE (default: neo4j)", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 2  # Configuration error
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


def _is_mcp_available() -> bool:
    """Check if MCP Neo4j tools are available in this environment."""
    # In a CLI context, MCP tools are typically not available
    # This would only work in an agent/LLM context
    return False


def _create_executor(use_http: bool, verbose: bool) -> CypherExecutor:
    """Create the appropriate CypherExecutor based on availability and flags."""
    if use_http or not _is_mcp_available():
        if verbose:
            print("Using Neo4j HTTP executor", file=sys.stderr)
        config = Neo4jHttpConfig.from_env()
        return Neo4jHttpExecutor(config)
    else:
        # MCP path (not available in standalone CLI)
        if verbose:
            print("Using Neo4j MCP executor", file=sys.stderr)
        from risk_scoring.mcp_executor import McpNeo4jExecutor
        # This will raise an error in CLI context, which is expected
        return McpNeo4jExecutor()


def _write_output(result, args) -> None:
    """Write the assessment result to the specified output."""
    output_format = args.output_format
    output_file = args.output_file
    
    # Determine what to write
    if output_format == 'json':
        content = result.report_json_string()
    elif output_format == 'markdown':
        content = result.report_markdown
    else:  # both
        content = f"# JSON Report\n\n```json\n{result.report_json_string()}\n```\n\n"
        content += f"# Markdown Report\n\n{result.report_markdown}"
    
    # Write to file or stdout
    if output_file:
        with open(output_file, 'w') as f:
            f.write(content)
        print(f"Report written to {output_file}", file=sys.stderr)
    else:
        print(content)


if __name__ == '__main__':
    sys.exit(main())
