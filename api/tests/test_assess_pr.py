"""Tests for POST /api/v1/assess-pr endpoint and environment detection."""

from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from api.models import (
    DEFAULT_BRANCH_ENVIRONMENT_MAP,
    PRAssessmentRequest,
    detect_environment,
)


# =====================================================================
# Unit tests: detect_environment
# =====================================================================


class TestDetectEnvironment(unittest.TestCase):
    """Tests for branch → environment detection logic."""

    # -- exact matches ---------------------------------------------------

    def test_main_maps_to_prod(self):
        assert detect_environment("main") == "prod"

    def test_master_maps_to_prod(self):
        assert detect_environment("master") == "prod"

    def test_staging_maps_to_staging(self):
        assert detect_environment("staging") == "staging"

    def test_stage_maps_to_staging(self):
        assert detect_environment("stage") == "staging"

    def test_develop_maps_to_dev(self):
        assert detect_environment("develop") == "dev"

    def test_dev_maps_to_dev(self):
        assert detect_environment("dev") == "dev"

    def test_test_maps_to_test(self):
        assert detect_environment("test") == "test"

    # -- prefix matching -------------------------------------------------

    def test_release_prefix_maps_to_prod(self):
        assert detect_environment("release/v1.2.3") == "prod"

    def test_staging_prefix(self):
        assert detect_environment("staging/hotfix-42") == "staging"

    # -- ref prefix stripping --------------------------------------------

    def test_refs_heads_stripped(self):
        assert detect_environment("refs/heads/main") == "prod"

    def test_refs_remotes_origin_stripped(self):
        assert detect_environment("refs/remotes/origin/staging") == "staging"

    # -- case insensitivity ----------------------------------------------

    def test_case_insensitive(self):
        assert detect_environment("Main") == "prod"
        assert detect_environment("STAGING") == "staging"

    # -- whitespace handling ---------------------------------------------

    def test_whitespace_stripped(self):
        assert detect_environment("  main  ") == "prod"

    # -- unknown branch falls back to dev --------------------------------

    def test_unknown_branch_defaults_to_dev(self):
        assert detect_environment("feature/my-feature") == "dev"
        assert detect_environment("bugfix/hotfix") == "dev"

    # -- custom mapping --------------------------------------------------

    def test_custom_map_overrides_default(self):
        custom = {"main": "staging"}  # override: main → staging
        assert detect_environment("main", custom_map=custom) == "staging"

    def test_custom_map_adds_new_branch(self):
        custom = {"canary": "prod"}
        assert detect_environment("canary", custom_map=custom) == "prod"

    def test_custom_map_prefix_match(self):
        custom = {"hotfix": "prod"}
        assert detect_environment("hotfix/fix-123", custom_map=custom) == "prod"


# =====================================================================
# Unit tests: PRAssessmentRequest model validation
# =====================================================================


class TestPRAssessmentRequestModel(unittest.TestCase):
    """Tests for PRAssessmentRequest Pydantic model validation."""

    def test_environment_auto_detected_from_target_branch(self):
        req = PRAssessmentRequest(
            repo_uri="https://dev.azure.com/org/proj/_git/repo",
            target_branch="main",
        )
        assert req.environment == "prod"

    def test_explicit_environment_not_overridden(self):
        req = PRAssessmentRequest(
            repo_uri="https://dev.azure.com/org/proj/_git/repo",
            target_branch="main",
            environment="staging",  # explicit override
        )
        assert req.environment == "staging"

    def test_data_source_defaults_to_auto(self):
        req = PRAssessmentRequest(
            repo_uri="https://dev.azure.com/org/proj/_git/repo",
            target_branch="main",
        )
        assert req.data_source == "auto"

    def test_custom_branch_map_used(self):
        req = PRAssessmentRequest(
            repo_uri="https://dev.azure.com/org/proj/_git/repo",
            target_branch="canary",
            branch_environment_map={"canary": "prod"},
        )
        assert req.environment == "prod"

    def test_missing_repo_uri_raises(self):
        with pytest.raises(Exception):
            PRAssessmentRequest(target_branch="main")  # type: ignore[call-arg]

    def test_missing_target_branch_raises(self):
        with pytest.raises(Exception):
            PRAssessmentRequest(repo_uri="https://example.com/repo")  # type: ignore[call-arg]


# =====================================================================
# Integration tests: POST /api/v1/assess-pr (httpx + TestClient)
# =====================================================================


# Import TestClient lazily so the module loads even without httpx
try:
    from fastapi.testclient import TestClient

    _HAS_TEST_CLIENT = True
except ImportError:
    _HAS_TEST_CLIENT = False


def _make_engine_result():
    """Build a minimal EngineResult for mocking."""
    from risk_scoring.engine import EngineResult
    from risk_scoring.evidence_provider import EvidenceExpansionResult
    from risk_scoring.models import ResolvedEntityRef
    from risk_scoring.scoring import ScoreResult

    resolved = ResolvedEntityRef(
        label="Service",
        resource_id="test-service",
        display_name="Test Service",
    )
    expansion = EvidenceExpansionResult(
        evidence={"service_name": "Test Service"},
        provider_results=(),
        all_queries=(),
        unknowns=(),
    )
    score = ScoreResult(
        risk_model_version="0.1",
        risk_score=42,
        risk_level="MEDIUM",
        factors=(),
        unknowns=(),
    )
    report_json = {
        "report_id": "test",
        "score": {"total_score": 42, "risk_level": "MEDIUM"},
        "factors": [],
        "evidence_queries": [],
    }
    report_md = "# Risk Report\n\nScore: 42 / 100 — MEDIUM"

    return EngineResult(
        resolved=resolved,
        expansion=expansion,
        score=score,
        report_json=report_json,
        report_markdown=report_md,
    )


@pytest.mark.skipif(not _HAS_TEST_CLIENT, reason="httpx / TestClient not installed")
class TestAssessPREndpoint(unittest.TestCase):
    """Integration tests for the assess-pr endpoint using FastAPI TestClient."""

    def setUp(self):
        from api.main import app

        self.client = TestClient(app)

    # -- happy path -------------------------------------------------------

    @patch("api.main.assess_with_providers")
    @patch("api.main._build_providers")
    @patch("api.main._resolve_data_source", return_value="kusto")
    def test_assess_pr_with_service_name(
        self, mock_resolve_ds, mock_build, mock_assess
    ):
        """When service_name is provided, skip repo resolution and score."""
        mock_build.return_value = ([], None)
        mock_assess.return_value = _make_engine_result()

        resp = self.client.post(
            "/api/v1/assess-pr",
            json={
                "repo_uri": "https://dev.azure.com/org/proj/_git/repo",
                "target_branch": "main",
                "service_name": "Test Service",
            },
        )

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["detected_environment"] == "prod"
        assert data["service_name"] == "Test Service"
        assert data["risk_score"] == 42
        assert data["risk_level"] == "MEDIUM"
        assert "report" in data
        assert "report_markdown" in data

    @patch("api.main.assess_with_providers")
    @patch("api.main._build_providers")
    @patch("api.main._resolve_data_source", return_value="kusto")
    def test_assess_pr_environment_from_staging_branch(
        self, mock_resolve_ds, mock_build, mock_assess
    ):
        """Environment detected from staging branch."""
        mock_build.return_value = ([], None)
        mock_assess.return_value = _make_engine_result()

        resp = self.client.post(
            "/api/v1/assess-pr",
            json={
                "repo_uri": "https://dev.azure.com/org/proj/_git/repo",
                "target_branch": "staging",
                "service_name": "Test Service",
            },
        )

        assert resp.status_code == 200
        assert resp.json()["detected_environment"] == "staging"

    @patch("api.main.assess_with_providers")
    @patch("api.main._build_providers")
    @patch("api.main._resolve_data_source", return_value="kusto")
    def test_assess_pr_explicit_environment_overrides_branch(
        self, mock_resolve_ds, mock_build, mock_assess
    ):
        """Explicit environment overrides branch detection."""
        mock_build.return_value = ([], None)
        mock_assess.return_value = _make_engine_result()

        resp = self.client.post(
            "/api/v1/assess-pr",
            json={
                "repo_uri": "https://dev.azure.com/org/proj/_git/repo",
                "target_branch": "main",  # would be prod
                "service_name": "Test Service",
                "environment": "test",  # explicit: test
            },
        )

        assert resp.status_code == 200
        assert resp.json()["detected_environment"] == "test"

    # -- repo fallback (no service_name) ---------------------------------

    @patch("api.main.assess_with_providers")
    @patch("api.main._build_providers")
    @patch("api.main._resolve_data_source", return_value="kusto")
    @patch("api.main._resolve_service_from_repo")
    def test_assess_pr_repo_fallback(
        self, mock_resolve_repo, mock_resolve_ds, mock_build, mock_assess
    ):
        """When no service_name, falls back to repo resolution."""
        from risk_scoring.models import ResolvedEntityRef
        mock_resolve_repo.return_value = ResolvedEntityRef(
            label="Repository",
            resource_id="my-repo",
            display_name="my-repo",
        )
        mock_build.return_value = ([], None)
        mock_assess.return_value = _make_engine_result()

        resp = self.client.post(
            "/api/v1/assess-pr",
            json={
                "repo_uri": "https://dev.azure.com/org/proj/_git/my-repo",
                "target_branch": "main",
            },
        )

        assert resp.status_code == 200
        mock_resolve_repo.assert_awaited_once()

    # -- validation errors -----------------------------------------------

    def test_missing_repo_uri_returns_422(self):
        resp = self.client.post(
            "/api/v1/assess-pr",
            json={"target_branch": "main"},
        )
        assert resp.status_code == 422

    def test_missing_target_branch_returns_422(self):
        resp = self.client.post(
            "/api/v1/assess-pr",
            json={"repo_uri": "https://example.com/repo"},
        )
        assert resp.status_code == 422

    def test_invalid_environment_returns_422(self):
        resp = self.client.post(
            "/api/v1/assess-pr",
            json={
                "repo_uri": "https://example.com/repo",
                "target_branch": "main",
                "environment": "banana",
            },
        )
        assert resp.status_code == 422

    # -- error handling --------------------------------------------------

    @patch("api.main._resolve_data_source")
    def test_no_backend_returns_503(self, mock_resolve_ds):
        from fastapi import HTTPException

        mock_resolve_ds.side_effect = HTTPException(
            status_code=503,
            detail={"error": "no_backend", "message": "No backend", "detail": None},
        )

        resp = self.client.post(
            "/api/v1/assess-pr",
            json={
                "repo_uri": "https://example.com/repo",
                "target_branch": "main",
                "service_name": "Svc",
            },
        )
        assert resp.status_code == 503


if __name__ == "__main__":
    unittest.main()
