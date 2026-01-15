"""Pydantic models for API requests and responses."""

from typing import Literal, Optional
from pydantic import BaseModel, Field


class AssessmentRequest(BaseModel):
    """Request model for risk assessment endpoint."""
    
    resource_id: str = Field(
        ...,
        description="Azure resource ID to assess",
        examples=["res-alpha-app", "/subscriptions/sub-001/resourceGroups/rg-prod-web-01"]
    )
    environment: Literal["prod", "staging", "dev", "test"] = Field(
        ...,
        description="Environment where the resource exists"
    )


class HealthResponse(BaseModel):
    """Health check response model."""
    
    status: str = Field(
        ...,
        description="Service status",
        examples=["ok"]
    )
    neo4j: Optional[str] = Field(
        None,
        description="Neo4j connection status",
        examples=["connected", "disconnected"]
    )


class ErrorResponse(BaseModel):
    """Error response model."""
    
    error: str = Field(
        ...,
        description="Error type",
        examples=["validation_error", "resource_not_found", "internal_error"]
    )
    message: str = Field(
        ...,
        description="Human-readable error message"
    )
    detail: Optional[str] = Field(
        None,
        description="Additional error details"
    )
