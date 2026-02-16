"""FastAPI application for risk scoring."""

from __future__ import annotations

import logging
import os
from datetime import date
from typing import List, Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from api.config import settings
from api.models import (
    AssessmentRequest,
    ErrorResponse,
    HealthResponse,
    PRAssessmentRequest,
    PRAssessmentResponse,
)
from risk_scoring.engine import assess_resource_change, assess_with_providers
from risk_scoring.errors import AmbiguousMatchError, NotFoundError, ResolutionError
from risk_scoring.evidence_client import CypherExecutor, EvidenceClient
from risk_scoring.evidence_provider import EvidenceProvider
from risk_scoring.models import ResolvedEntityRef, ResourceSpec
from risk_scoring.neo4j_http import Neo4jHttpConfig, Neo4jHttpError
from risk_scoring.neo4j_http_executor import Neo4jHttpExecutor
from risk_scoring.neo4j_http_repository import Neo4jHttpEntityRepository
from risk_scoring.scoring import ChangeContext

logger = logging.getLogger(__name__)

# Create FastAPI application
app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helpers – data-source detection (mirrors CLI logic)
# ---------------------------------------------------------------------------

def _neo4j_available() -> bool:
    return bool(os.environ.get("NEO4J_PASSWORD"))


def _kusto_available() -> bool:
    return bool(os.environ.get("KUSTO_AUTH_METHOD"))


def _resolve_data_source(requested: str) -> str:
    """Resolve 'auto' to a concrete data source."""
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
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail={
            "error": "no_backend",
            "message": (
                "Cannot auto-detect data source. "
                "Set NEO4J_PASSWORD for Neo4j or KUSTO_AUTH_METHOD for Kusto."
            ),
            "detail": None,
        },
    )


def _build_providers(
    data_source: str,
) -> tuple[List[EvidenceProvider], Optional[Neo4jHttpEntityRepository]]:
    """Construct evidence providers for the resolved data source."""
    providers: List[EvidenceProvider] = []
    repo: Optional[Neo4jHttpEntityRepository] = None

    if data_source in ("neo4j", "hybrid"):
        config = Neo4jHttpConfig.from_env()
        executor: CypherExecutor = Neo4jHttpExecutor(config)
        evidence_client = EvidenceClient(executor)
        repo = Neo4jHttpEntityRepository(config)

        from risk_scoring.neo4j_evidence_provider import Neo4jEvidenceProvider

        providers.append(Neo4jEvidenceProvider(evidence_client))

    if data_source in ("kusto", "hybrid"):
        from risk_scoring.kusto_evidence_provider import KustoEvidenceProvider
        from risk_scoring.kusto_source_config import KustoSourceRegistry

        registry = KustoSourceRegistry.from_yaml()
        providers.append(KustoEvidenceProvider(registry))

    if not providers:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "error": "no_providers",
                "message": f"No evidence providers available for data_source={data_source}",
                "detail": None,
            },
        )

    return providers, repo


# ---------------------------------------------------------------------------
# Health / root
# ---------------------------------------------------------------------------


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check() -> HealthResponse:
    """Health check endpoint.

    Returns service status and Neo4j connection status.
    """
    neo4j_status = "unknown"

    try:
        config = Neo4jHttpConfig.from_env()
        executor = Neo4jHttpExecutor(config)
        result = executor.run_readonly("RETURN 1 as test", {})
        neo4j_status = "connected" if result and len(result) > 0 else "connected (no data)"
    except Neo4jHttpError as e:
        neo4j_status = f"error: {str(e)[:50]}"
    except Exception as e:
        neo4j_status = f"error: {str(e)[:50]}"

    return HealthResponse(status="ok", neo4j=neo4j_status)


@app.get("/", tags=["Root"])
async def root():
    """Root endpoint with API information."""
    return {
        "service": settings.api_title,
        "version": settings.api_version,
        "docs": "/docs",
        "health": "/health",
    }


# ---------------------------------------------------------------------------
# POST /api/v1/assess  (resource-level — existing)
# ---------------------------------------------------------------------------


@app.post("/api/v1/assess", tags=["Assessment"])
async def assess_resource(request: AssessmentRequest):
    """Assess risk for a resource change.

    Request body:
    - resource_id: Azure resource ID to assess
    - environment: Environment (prod, staging, dev, test)
    """
    try:
        config = Neo4jHttpConfig.from_env()
        repo = Neo4jHttpEntityRepository(config)
        executor = Neo4jHttpExecutor(config)
        evidence_client = EvidenceClient(executor)

        resource_spec = ResourceSpec(resource_id=request.resource_id)
        change_context = ChangeContext.create(environment=request.environment)

        result = assess_resource_change(
            repo=repo,
            evidence_client=evidence_client,
            resource=resource_spec,
            change=change_context,
            as_of=date.today(),
            report_id=f"api-{request.resource_id}-{request.environment}",
        )
        return result.report_json

    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "resource_not_found", "message": str(e), "detail": None},
        )
    except AmbiguousMatchError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "ambiguous_resource",
                "message": str(e),
                "detail": f"Found {len(e.candidates)} candidates" if hasattr(e, "candidates") else None,
            },
        )
    except ResolutionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "resolution_error", "message": str(e), "detail": None},
        )
    except Neo4jHttpError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "neo4j_connection_error",
                "message": "Failed to connect to Neo4j database",
                "detail": str(e),
            },
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "validation_error", "message": str(e), "detail": None},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_error", "message": "An unexpected error occurred", "detail": str(e)},
        )


# ---------------------------------------------------------------------------
# POST /api/v1/assess-pr  (PR-level — new)
# ---------------------------------------------------------------------------


@app.post(
    "/api/v1/assess-pr",
    response_model=PRAssessmentResponse,
    tags=["Assessment"],
    summary="Assess risk for a pull request",
    responses={
        400: {"model": ErrorResponse, "description": "Validation / resolution error"},
        404: {"model": ErrorResponse, "description": "Service not found"},
        503: {"model": ErrorResponse, "description": "No backend available"},
    },
)
async def assess_pr(request: PRAssessmentRequest):
    """Assess risk for a pull-request change.

    Accepts a repo URI and target branch, resolves the owning service,
    detects the environment, and returns a full risk report.

    **Environment detection** (when ``environment`` is not provided):
    - ``main`` / ``master`` / ``release/*`` → **prod**
    - ``staging`` / ``stage`` → **staging**
    - ``develop`` / ``dev`` → **dev**
    - ``test`` → **test**
    - Override via ``branch_environment_map``.

    **Service resolution**:
    - If ``service_name`` is provided, it is used directly.
    - Otherwise the repo URI is resolved to a service via Service Tree
      (requires Kusto backend).
    """
    try:
        # 1. Resolve data source
        data_source = _resolve_data_source(request.data_source)

        # 2. Determine service identity
        service_name = request.service_name
        resolved: Optional[ResolvedEntityRef] = None

        if service_name:
            # Caller supplied an explicit service name — skip resolution.
            resolved = ResolvedEntityRef(
                label="Service",
                resource_id=service_name,
                display_name=service_name,
            )
        else:
            # Attempt repo → service resolution via Kusto Service Tree
            resolved = await _resolve_service_from_repo(request.repo_uri, data_source)
            service_name = resolved.display_name

        # 3. Build evidence providers
        providers, repo = _build_providers(data_source)

        # 4. Run engine pipeline
        env = request.environment  # already resolved by model_validator
        assert env is not None  # guaranteed by _resolve_environment validator

        change = ChangeContext.create(environment=env)
        report_id = f"pr-{service_name or request.repo_uri}-{env}"

        engine_result = assess_with_providers(
            repo=repo,
            providers=providers,
            resolved=resolved,
            change=change,
            as_of=date.today(),
            report_id=report_id,
        )

        # 5. Build response
        return PRAssessmentResponse(
            repo_uri=request.repo_uri,
            target_branch=request.target_branch,
            detected_environment=env,
            service_name=service_name,
            risk_score=engine_result.score.risk_score,
            risk_level=engine_result.score.risk_level,
            report=engine_result.report_json,
            report_markdown=engine_result.report_markdown,
        )

    except HTTPException:
        raise  # re-raise our own HTTP errors
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error": "service_not_found", "message": str(e), "detail": None},
        )
    except AmbiguousMatchError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "ambiguous_service",
                "message": str(e),
                "detail": f"Found {len(e.candidates)} candidates" if hasattr(e, "candidates") else None,
            },
        )
    except ResolutionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "resolution_error", "message": str(e), "detail": None},
        )
    except Neo4jHttpError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "neo4j_error",
                "message": "Neo4j operation failed",
                "detail": str(e),
            },
        )
    except Exception as e:
        logger.exception("Unexpected error in assess_pr")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "internal_error", "message": "An unexpected error occurred", "detail": str(e)},
        )


async def _resolve_service_from_repo(
    repo_uri: str,
    data_source: str,
) -> ResolvedEntityRef:
    """Resolve a repo URI to a service via Kusto Service Tree.

    If Kusto is not available, returns a synthetic ref using the repo URI
    as the resource_id (graceful degradation).
    """
    if data_source in ("kusto", "hybrid"):
        try:
            from risk_scoring.kusto_evidence_provider import KustoEvidenceProvider
            from risk_scoring.kusto_source_config import KustoSourceRegistry

            registry = KustoSourceRegistry.from_yaml()

            # Query Service Tree for repo → service mapping
            service_name = registry.resolve_service_from_repo(repo_uri)
            if service_name:
                return ResolvedEntityRef(
                    label="Service",
                    resource_id=service_name,
                    display_name=service_name,
                )
        except AttributeError:
            # resolve_service_from_repo not yet implemented on registry
            logger.warning(
                "KustoSourceRegistry.resolve_service_from_repo not available; "
                "falling back to repo_uri as identity."
            )
        except Exception as e:
            logger.warning("Repo → service resolution failed: %s", e)

    # Fallback: use the repo URI itself as identity
    # Extract a short name from the URI for display
    short_name = repo_uri.rstrip("/").rsplit("/", 1)[-1]
    return ResolvedEntityRef(
        label="Repository",
        resource_id=short_name,
        display_name=short_name,
    )
