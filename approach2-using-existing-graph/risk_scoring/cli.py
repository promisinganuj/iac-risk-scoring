"""Command-line interface for risk scoring."""

import argparse
import sys
from typing import Optional


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
        # TODO: Wire Neo4j config and call engine (task iac-risk-scoring-ldt)
        # This will be implemented in the next task
        print(f"CLI parsed arguments successfully:", file=sys.stderr)
        print(f"  Resource ID: {args.resource_id}", file=sys.stderr)
        print(f"  Environment: {args.environment}", file=sys.stderr)
        print(f"  Output format: {args.output_format}", file=sys.stderr)
        print(f"  Output file: {args.output_file or 'stdout'}", file=sys.stderr)
        print(f"  Use HTTP: {args.use_http}", file=sys.stderr)
        print(f"  Verbose: {args.verbose}", file=sys.stderr)
        
        # Placeholder: Next task will wire up the actual engine call
        print("\nNote: Engine integration pending (task iac-risk-scoring-ldt)", file=sys.stderr)
        return 0
        
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        return 130  # Standard Unix exit code for SIGINT
        
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
