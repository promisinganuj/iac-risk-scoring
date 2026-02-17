"""Command-line interface for risk scoring.

Supports three data-source modes:

- **neo4j** (legacy): entity resolution + evidence from Neo4j graph.
- **kusto**: evidence from Kusto (IcM, SafeFly). Requires ``--service-name``
  or ``--repo-uri`` (resolved to service via k11).
- **hybrid**: Neo4j for entity resolution + graph evidence, Kusto for
  IcM/SafeFly evidence. Both backends must be configured.
- **auto** (default): detect available backends from env vars / config.
"""

import argparse
import logging
import os
import sys
from datetime import date
from typing import List, Optional, Sequence

from risk_scoring.engine import assess_resource_change, assess_with_providers
from risk_scoring.evidence_client import CypherExecutor, EvidenceClient
from risk_scoring.evidence_provider import EvidenceProvider
from risk_scoring.models import ResolvedEntityRef, ResourceSpec
from risk_scoring.neo4j_http import Neo4jHttpConfig, Neo4jHttpError
from risk_scoring.neo4j_http_executor import Neo4jHttpExecutor
from risk_scoring.neo4j_http_repository import Neo4jHttpEntityRepository
from risk_scoring.scoring import ChangeContext

logger = logging.getLogger(__name__)

_DATA_SOURCES = ("auto", "kusto", "neo4j", "hybrid")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def create_parser() -> argparse.ArgumentParser:
    """Create and configure the argument parser for the CLI."""
    parser = argparse.ArgumentParser(
        prog="risk_scoring",
        description="Assess risk for Azure resource changes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Neo4j-only (legacy): resolve resource via graph, score from graph evidence
  python -m risk_scoring --resource-id "rg-prod-web-01" --environment prod

  # Kusto-only: score using IcM/SafeFly data (requires --service-name)
  python -m risk_scoring --service-name "My Service" --environment prod \\
      --data-source kusto

  # Hybrid: Neo4j resolution + graph evidence, then Kusto IcM/SafeFly
  python -m risk_scoring --resource-id "rg-prod-web-01" --environment prod \\
      --data-source hybrid

  # Auto-detect backends (default)
  python -m risk_scoring --resource-id "rg-prod-web-01" --environment prod \\
      --data-source auto

  # Repo URI (resolves to service via Service Tree, requires Kusto)
  python -m risk_scoring --repo-uri "https://dev.azure.com/org/project/_git/repo" \\
      --environment prod

  # Output as JSON to a file
  python -m risk_scoring --resource-id "rg-prod-web-01" --environment prod \\
      --output-format json --output-file report.json
""",
    )

    # --- Identity group (mutually-exclusive) ---
    identity = parser.add_argument_group(
        "resource identity (at least one required)"
    )
    identity.add_argument(
        "--resource-id",
        help='Azure resource ID to assess (e.g., "rg-prod-web-01")',
    )
    identity.add_argument(
        "--service-name",
        help="Service name to query Kusto evidence (matches OwningTenantName in IcM)",
    )
    identity.add_argument(
        "--repo-uri",
        help="Azure DevOps repo URI (resolves to service via Service Tree)",
    )

    # --- Required ---
    parser.add_argument(
        "--environment",
        required=True,
        choices=["prod", "staging", "dev", "test"],
        help="Environment where the resource exists",
    )

    # --- Data-source ---
    parser.add_argument(
        "--data-source",
        default="auto",
        choices=list(_DATA_SOURCES),
        help="Evidence backend: auto (detect), kusto, neo4j, or hybrid (default: auto)",
    )

    # --- Output ---
    parser.add_argument(
        "--output-format",
        default="markdown",
        choices=["json", "markdown", "both"],
        help="Output format (default: markdown)",
    )
    parser.add_argument(
        "--output-file",
        help="Write output to file instead of stdout",
    )

    # --- Misc ---
    parser.add_argument(
        "--use-http",
        action="store_true",
        help="Force HTTP Neo4j executor (requires NEO4J_* env vars)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )

    return parser


# ---------------------------------------------------------------------------
# Backend detection helpers
# ---------------------------------------------------------------------------

def _neo4j_available() -> bool:
    """Return True if Neo4j credentials are configured."""
    return bool(os.environ.get("NEO4J_PASSWORD"))


def _kusto_available() -> bool:
    """Return True if Kusto can be used.

    Requires KUSTO_AUTH_METHOD to be explicitly set — the bundled YAML
    config file alone is not sufficient since the user may not have
    credentials configured.
    """
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
    raise SystemExit(
        "Error: cannot auto-detect data source. "
        "Set NEO4J_PASSWORD for Neo4j or KUSTO_AUTH_METHOD for Kusto."
    )


# ---------------------------------------------------------------------------
# Provider construction
# ---------------------------------------------------------------------------

def _build_providers(
    data_source: str,
    *,
    verbose: bool = False,
) -> tuple[
    List[EvidenceProvider],
    Optional["Neo4jHttpEntityRepository"],  # repo (only when neo4j involved)
]:
    """Construct evidence providers for the resolved data source.

    Returns (providers, repo).  ``repo`` is non-None only when Neo4j is
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
        if verbose:
            logger.info("Neo4j evidence provider enabled")

    # --- Kusto ---
    if data_source in ("kusto", "hybrid"):
        from risk_scoring.kusto_evidence_provider import KustoEvidenceProvider
        from risk_scoring.kusto_source_config import KustoSourceRegistry

        registry = KustoSourceRegistry.from_yaml()
        providers.append(KustoEvidenceProvider(registry))
        if verbose:
            logger.info(
                "Kusto evidence provider enabled (sources: %s)",
                ", ".join(registry.list_sources()),
            )

    if not providers:
        raise SystemExit(
            f"Error: no evidence providers available for --data-source={data_source}"
        )

    return providers, repo


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def _resolve_repo_to_service(
    repo_uri: str,
    *,
    verbose: bool = False,
) -> Optional[str]:
    """Resolve a repo URI to a service name via Kusto k11 query.

    Returns the service name if found, or None.
    """
    try:
        from risk_scoring.kusto_source_config import KustoSourceRegistry

        registry = KustoSourceRegistry.from_yaml()
        service_name = registry.resolve_service_from_repo(repo_uri)
        return service_name
    except Exception as exc:
        if verbose:
            logger.warning(
                "Repo → service resolution failed: %s", exc, exc_info=True
            )
        return None


def main(argv: Optional[list] = None) -> int:
    """CLI entry point.

    Returns exit code: 0 = success, 1 = runtime error, 2 = config error.
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    # --- Logging ---
    if args.verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

    # --- Validate identity flags ---
    if not args.resource_id and not args.service_name and not args.repo_uri:
        parser.error(
            "at least one of --resource-id, --service-name, or --repo-uri is required"
        )

    try:
        # --- Resolve data source ---
        data_source = _resolve_data_source(args.data_source)
        if args.verbose:
            logger.info("Data source: %s", data_source)

        # --- Repo URI → service name resolution (k11) ---
        if args.repo_uri:
            if data_source not in ("kusto", "hybrid"):
                print(
                    "Error: --repo-uri requires Kusto (--data-source=kusto or "
                    "hybrid) for Service Tree k11 lookup",
                    file=sys.stderr,
                )
                return 1

            resolved_service = _resolve_repo_to_service(args.repo_uri,
                                                        verbose=args.verbose)
            if resolved_service is None:
                print(
                    f"Error: could not resolve --repo-uri {args.repo_uri!r} "
                    "to a service in Service Tree. "
                    "Use --service-name to supply the service name directly.",
                    file=sys.stderr,
                )
                return 1

            # Promote to service_name for the rest of the pipeline
            if args.verbose:
                logger.info(
                    "Resolved repo %s → service %r",
                    args.repo_uri, resolved_service,
                )
            args.service_name = resolved_service

        # --- Validate flag combinations ---
        if data_source == "kusto" and not args.service_name:
            print(
                "Error: --data-source=kusto requires --service-name or --repo-uri "
                "(Kusto queries need a service name to match OwningTenantName)",
                file=sys.stderr,
            )
            return 1

        if data_source in ("neo4j", "hybrid") and not args.resource_id:
            print(
                f"Error: --data-source={data_source} requires --resource-id "
                "for Neo4j entity resolution",
                file=sys.stderr,
            )
            return 1

        # --- Build pipeline ---
        change_context = ChangeContext.create(environment=args.environment)
        report_id_base = args.resource_id or args.service_name or args.repo_uri or "unknown"
        report_id = f"cli-{report_id_base}-{args.environment}"

        if data_source == "neo4j" and not args.service_name:
            # Pure legacy path — existing assess_resource_change()
            result = _run_legacy_neo4j(args, change_context, report_id)
        else:
            # Provider-based path
            result = _run_providers(args, data_source, change_context, report_id)

        _write_output(result, args)
        return 0

    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        return 130

    except Neo4jHttpError as e:
        print(f"Neo4j configuration error: {e}", file=sys.stderr)
        print(
            "\nEnsure these env vars are set:\n"
            "  NEO4J_HTTP_URL (or NEO4J_HOST + NEO4J_HTTP_PORT)\n"
            "  NEO4J_USERNAME (default: neo4j)\n"
            "  NEO4J_PASSWORD (required)\n"
            "  NEO4J_DATABASE (default: neo4j)",
            file=sys.stderr,
        )
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 2

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.verbose:
            import traceback

            traceback.print_exc()
        return 1


# ---------------------------------------------------------------------------
# Pipeline runners
# ---------------------------------------------------------------------------

def _run_legacy_neo4j(args, change_context, report_id):
    """Legacy Neo4j-only assessment (no Kusto)."""
    config = Neo4jHttpConfig.from_env()
    executor = Neo4jHttpExecutor(config)
    repo = Neo4jHttpEntityRepository(config)
    evidence_client = EvidenceClient(executor)
    resource_spec = ResourceSpec(resource_id=args.resource_id)

    return assess_resource_change(
        repo=repo,
        evidence_client=evidence_client,
        resource=resource_spec,
        change=change_context,
        as_of=date.today(),
        report_id=report_id,
    )


def _run_providers(args, data_source, change_context, report_id):
    """Provider-based assessment (kusto, hybrid, or neo4j+service_name)."""
    providers, repo = _build_providers(data_source, verbose=args.verbose)

    # Determine resolution strategy
    resource: Optional[ResourceSpec] = None
    resolved: Optional[ResolvedEntityRef] = None

    if args.resource_id and repo is not None:
        # Neo4j resolution path
        resource = ResourceSpec(resource_id=args.resource_id)
    else:
        # Kusto-only or service-name supplied: build a synthetic resolved ref
        # so providers can use service_name in evidence dict.
        resource_id = args.resource_id or args.service_name or "unknown"
        display = args.service_name
        label = "Service"
        if args.repo_uri and not args.resource_id:
            label = "Repository"
        resolved = ResolvedEntityRef(
            label=label,
            resource_id=resource_id,
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
# Output
# ---------------------------------------------------------------------------

def _write_output(result, args) -> None:
    """Write the assessment result to the specified output."""
    fmt = args.output_format

    if fmt == "json":
        content = result.report_json_string()
    elif fmt == "markdown":
        content = result.report_markdown
    else:  # both
        content = (
            f"# JSON Report\n\n```json\n{result.report_json_string()}\n```\n\n"
            f"# Markdown Report\n\n{result.report_markdown}"
        )

    if args.output_file:
        with open(args.output_file, "w") as f:
            f.write(content)
        print(f"Report written to {args.output_file}", file=sys.stderr)
    else:
        print(content)


if __name__ == "__main__":
    sys.exit(main())
