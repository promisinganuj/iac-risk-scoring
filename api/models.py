"""Pydantic models for API requests and responses."""

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field, model_validator


class AssessmentRequest(BaseModel):
    """Request model for risk assessment endpoint."""

    resource_id: str = Field(
        ...,
        description="Azure resource ID to assess",
        examples=[
            "res-alpha-app",
            "/subscriptions/sub-001/resourceGroups/rg-prod-web-01",
        ],
    )
    environment: Literal["prod", "staging", "dev", "test"] = Field(
        ...,
        description="Environment where the resource exists",
    )


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str = Field(
        ...,
        description="Service status",
        examples=["ok"],
    )
    neo4j: Optional[str] = Field(
        None,
        description="Neo4j connection status",
        examples=["connected", "disconnected"],
    )


class ErrorResponse(BaseModel):
    """Error response model."""

    error: str = Field(
        ...,
        description="Error type",
        examples=["validation_error", "resource_not_found", "internal_error"],
    )
    message: str = Field(
        ...,
        description="Human-readable error message",
    )
    detail: Optional[str] = Field(
        None,
        description="Additional error details",
    )


# ---------------------------------------------------------------------------
# Branch → environment detection
# ---------------------------------------------------------------------------

DEFAULT_BRANCH_ENVIRONMENT_MAP: Dict[str, str] = {
    "main": "prod",
    "master": "prod",
    "release": "prod",
    "staging": "staging",
    "stage": "staging",
    "develop": "dev",
    "dev": "dev",
    "test": "test",
}


def detect_environment(
    target_branch: str,
    custom_map: Optional[Dict[str, str]] = None,
) -> str:
    """Detect environment from a target branch name.

    Resolution order:
    1. Exact match in *custom_map* (if provided, takes precedence).
    2. Exact match in DEFAULT_BRANCH_ENVIRONMENT_MAP.
    3. Prefix match (e.g. ``release/2024-02`` → prod).
    4. Fall back to ``"dev"``.
    """
    branch = target_branch.strip().lower()
    # Strip common ref prefixes
    for prefix in ("refs/heads/", "refs/remotes/origin/"):
        if branch.startswith(prefix):
            branch = branch[len(prefix) :]
            break

    # custom_map overrides defaults
    mapping = {**DEFAULT_BRANCH_ENVIRONMENT_MAP, **(custom_map or {})}

    # Exact match
    if branch in mapping:
        return mapping[branch]

    # Prefix match (e.g. "release/v1.2" → "release" → prod)
    first_segment = branch.split("/")[0]
    if first_segment in mapping:
        return mapping[first_segment]

    return "dev"


# ---------------------------------------------------------------------------
# PR assessment models
# ---------------------------------------------------------------------------


class PRAssessmentRequest(BaseModel):
    """Request model for PR-level risk assessment endpoint."""

    repo_uri: str = Field(
        ...,
        description="Azure DevOps or GitHub repository URI",
        examples=[
            "https://dev.azure.com/org/project/_git/my-repo",
            "https://github.com/org/my-repo",
        ],
    )
    target_branch: str = Field(
        ...,
        description="Branch the PR targets (used for environment detection)",
        examples=["main", "staging", "refs/heads/release/v1.2"],
    )
    source_branch: Optional[str] = Field(
        None,
        description="Source branch of the PR (informational; not used for scoring today)",
        examples=["feature/add-redis-cache"],
    )
    service_name: Optional[str] = Field(
        None,
        description=(
            "Explicit service name. When provided, skips repo → service "
            "resolution and uses this value directly for evidence queries."
        ),
        examples=["Azure Database for PostgreSQL - Flexible Server"],
    )
    environment: Optional[Literal["prod", "staging", "dev", "test"]] = Field(
        None,
        description=(
            "Explicit environment override. When omitted, environment is "
            "detected from target_branch."
        ),
    )
    branch_environment_map: Optional[Dict[str, str]] = Field(
        None,
        description=(
            "Custom branch → environment mapping. Merged on top of defaults "
            '(main→prod, staging→staging, dev→dev). Example: {"release": "prod"}'
        ),
    )
    data_source: Literal["auto", "kusto", "neo4j", "hybrid"] = Field(
        "auto",
        description="Evidence backend to use (default: auto-detect)",
    )

    @model_validator(mode="after")
    def _resolve_environment(self) -> "PRAssessmentRequest":
        """Auto-detect environment from target_branch when not explicit."""
        if self.environment is None:
            object.__setattr__(
                self,
                "environment",
                detect_environment(self.target_branch, self.branch_environment_map),
            )
        return self


class PRAssessmentResponse(BaseModel):
    """Response model for PR-level risk assessment endpoint."""

    repo_uri: str
    target_branch: str
    detected_environment: str
    service_name: Optional[str] = None
    risk_score: int
    risk_level: str
    report: Dict  # full report JSON from the engine
    report_markdown: str
