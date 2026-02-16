"""FastAPI application for risk scoring."""

from datetime import date
from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from api.config import settings
from api.models import AssessmentRequest, ErrorResponse, HealthResponse
from risk_scoring.engine import assess_resource_change
from risk_scoring.errors import NotFoundError, AmbiguousMatchError, ResolutionError
from risk_scoring.evidence_client import EvidenceClient
from risk_scoring.models import ResourceSpec
from risk_scoring.neo4j_http import Neo4jHttpConfig, Neo4jHttpError
from risk_scoring.neo4j_http_executor import Neo4jHttpExecutor
from risk_scoring.neo4j_http_repository import Neo4jHttpEntityRepository
from risk_scoring.scoring import ChangeContext

# Create FastAPI application
app = FastAPI(
    title=settings.api_title,
    description=settings.api_description,
    version=settings.api_version,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check() -> HealthResponse:
    """
    Health check endpoint.
    
    Returns service status and Neo4j connection status.
    Tests actual connectivity to Neo4j database.
    """
    neo4j_status = "unknown"
    
    try:
        # Try to create Neo4j config and executor
        config = Neo4jHttpConfig.from_env()
        executor = Neo4jHttpExecutor(config)
        
        # Execute a simple query to verify connectivity
        # Use a lightweight query that doesn't require specific data
        result = executor.run_readonly(
            "RETURN 1 as test",
            {}
        )
        
        # If we got here without exception, connection is working
        if result and len(result) > 0:
            neo4j_status = "connected"
        else:
            neo4j_status = "connected (no data)"
            
    except Neo4jHttpError as e:
        neo4j_status = f"error: {str(e)[:50]}"  # Truncate long error messages
    except Exception as e:
        neo4j_status = f"error: {str(e)[:50]}"
    
    return HealthResponse(
        status="ok",
        neo4j=neo4j_status
    )


@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint with API information.
    """
    return {
        "service": settings.api_title,
        "version": settings.api_version,
        "docs": "/docs",
        "health": "/health"
    }


@app.post("/api/v1/assess", tags=["Assessment"])
async def assess_resource(request: AssessmentRequest):
    """
    Assess risk for a resource change.
    
    Request body:
    - resource_id: Azure resource ID to assess
    - environment: Environment (prod, staging, dev, test)
    
    Returns:
    - Full risk report JSON from the scoring engine
    
    Raises:
    - 400: Validation error or resource not found
    - 500: Internal server error or Neo4j connection error
    """
    try:
        # Initialize Neo4j configuration
        config = Neo4jHttpConfig.from_env()
        
        # Create repository and executor
        repo = Neo4jHttpEntityRepository(config)
        executor = Neo4jHttpExecutor(config)
        evidence_client = EvidenceClient(executor)
        
        # Build inputs
        resource_spec = ResourceSpec(resource_id=request.resource_id)
        change_context = ChangeContext.create(environment=request.environment)
        
        # Run assessment
        result = assess_resource_change(
            repo=repo,
            evidence_client=evidence_client,
            resource=resource_spec,
            change=change_context,
            as_of=date.today(),
            report_id=f"api-{request.resource_id}-{request.environment}"
        )
        
        # Return JSON report
        return result.report_json
        
    except NotFoundError as e:
        # Resource not found in graph
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "error": "resource_not_found",
                "message": str(e),
                "detail": None
            }
        )
    except AmbiguousMatchError as e:
        # Multiple matching resources found
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "ambiguous_resource",
                "message": str(e),
                "detail": f"Found {len(e.candidates)} candidates" if hasattr(e, 'candidates') else None
            }
        )
    except ResolutionError as e:
        # Other resolution errors
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "resolution_error",
                "message": str(e),
                "detail": None
            }
        )
    except Neo4jHttpError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "neo4j_connection_error",
                "message": "Failed to connect to Neo4j database",
                "detail": str(e)
            }
        )
    except ValueError as e:
        # Resource not found or validation errors
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "error": "validation_error",
                "message": str(e),
                "detail": None
            }
        )
    except Exception as e:
        # Catch-all for unexpected errors
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "internal_error",
                "message": "An unexpected error occurred",
                "detail": str(e)
            }
        )

