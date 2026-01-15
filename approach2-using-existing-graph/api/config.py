"""Configuration for the FastAPI service."""

import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Neo4j connection settings
    neo4j_http_url: str = os.getenv("NEO4J_HTTP_URL", "http://localhost:7474")
    neo4j_username: str = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "")
    neo4j_database: str = os.getenv("NEO4J_DATABASE", "neo4j")
    neo4j_host: str = os.getenv("NEO4J_HOST", "localhost")
    neo4j_http_port: str = os.getenv("NEO4J_HTTP_PORT", "7474")
    
    # API settings
    api_title: str = "Risk Scoring API"
    api_description: str = "Deterministic risk scoring for IaC changes"
    api_version: str = "0.1.0"
    cors_origins: list[str] = ["*"]  # Allow all origins for local testing
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Global settings instance
settings = Settings()
