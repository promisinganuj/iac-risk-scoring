"""Tests for the risk scoring CLI.

Covers argument parsing, data-source resolution, provider construction,
and end-to-end main() with mocked backends.
"""

import os
import unittest
from io import StringIO
from unittest.mock import MagicMock, patch

from risk_scoring.cli import (
    _DATA_SOURCES,
    _build_providers,
    _kusto_available,
    _neo4j_available,
    _resolve_data_source,
    _resolve_repo_to_service,
    create_parser,
    main,
)


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestParser(unittest.TestCase):
    """Verify argparse configuration."""

    def test_help_does_not_crash(self):
        parser = create_parser()
        with self.assertRaises(SystemExit) as ctx:
            parser.parse_args(["--help"])
        self.assertEqual(ctx.exception.code, 0)

    def test_environment_optional(self):
        parser = create_parser()
        args = parser.parse_args(["--resource-id", "x"])
        self.assertIsNone(args.environment)

    def test_resource_id_only(self):
        args = create_parser().parse_args(
            ["--resource-id", "res-1", "--environment", "prod"]
        )
        self.assertEqual(args.resource_id, "res-1")
        self.assertEqual(args.environment, "prod")
        self.assertIsNone(args.service_name)
        self.assertIsNone(args.repo_uri)
        self.assertEqual(args.data_source, "auto")

    def test_service_name_flag(self):
        args = create_parser().parse_args(
            ["--service-name", "My Svc", "--environment", "staging", "--data-source", "kusto"]
        )
        self.assertEqual(args.service_name, "My Svc")
        self.assertEqual(args.data_source, "kusto")
        self.assertIsNone(args.resource_id)

    def test_data_source_choices(self):
        for ds in _DATA_SOURCES:
            args = create_parser().parse_args(
                ["--resource-id", "x", "--environment", "dev", "--data-source", ds]
            )
            self.assertEqual(args.data_source, ds)

    def test_invalid_data_source_rejected(self):
        with self.assertRaises(SystemExit):
            create_parser().parse_args(
                ["--resource-id", "x", "--environment", "prod", "--data-source", "nope"]
            )

    def test_output_defaults(self):
        args = create_parser().parse_args(
            ["--resource-id", "x", "--environment", "test"]
        )
        self.assertEqual(args.output_format, "markdown")
        self.assertIsNone(args.output_file)
        self.assertFalse(args.use_http)
        self.assertFalse(args.verbose)

    def test_repo_uri_flag(self):
        args = create_parser().parse_args(
            ["--repo-uri", "https://example.com/repo", "--environment", "prod"]
        )
        self.assertEqual(args.repo_uri, "https://example.com/repo")


# ---------------------------------------------------------------------------
# Data-source detection
# ---------------------------------------------------------------------------


class TestDataSourceDetection(unittest.TestCase):
    """Test _neo4j_available, _kusto_available, and _resolve_data_source."""

    @patch.dict(os.environ, {"NEO4J_PASSWORD": "secret"}, clear=False)
    def test_neo4j_available_with_password(self):
        self.assertTrue(_neo4j_available())

    @patch.dict(os.environ, {}, clear=True)
    def test_neo4j_not_available_without_password(self):
        self.assertFalse(_neo4j_available())

    @patch.dict(os.environ, {"KUSTO_AUTH_METHOD": "az_cli"}, clear=False)
    def test_kusto_available_with_env(self):
        self.assertTrue(_kusto_available())

    @patch.dict(os.environ, {}, clear=True)
    def test_kusto_not_available_without_env(self):
        """YAML alone is not enough — KUSTO_AUTH_METHOD must be set."""
        self.assertFalse(_kusto_available())

    def test_resolve_explicit_source(self):
        for ds in ("kusto", "neo4j", "hybrid"):
            self.assertEqual(_resolve_data_source(ds), ds)

    @patch("risk_scoring.cli._neo4j_available", return_value=True)
    @patch("risk_scoring.cli._kusto_available", return_value=True)
    def test_auto_detects_hybrid(self, _k, _n):
        self.assertEqual(_resolve_data_source("auto"), "hybrid")

    @patch("risk_scoring.cli._neo4j_available", return_value=False)
    @patch("risk_scoring.cli._kusto_available", return_value=True)
    def test_auto_detects_kusto(self, _k, _n):
        self.assertEqual(_resolve_data_source("auto"), "kusto")

    @patch("risk_scoring.cli._neo4j_available", return_value=True)
    @patch("risk_scoring.cli._kusto_available", return_value=False)
    def test_auto_detects_neo4j(self, _k, _n):
        self.assertEqual(_resolve_data_source("auto"), "neo4j")

    @patch("risk_scoring.cli._neo4j_available", return_value=False)
    @patch("risk_scoring.cli._kusto_available", return_value=False)
    def test_auto_raises_when_nothing_available(self, _k, _n):
        with self.assertRaises(SystemExit):
            _resolve_data_source("auto")


# ---------------------------------------------------------------------------
# Provider construction
# ---------------------------------------------------------------------------


class TestBuildProviders(unittest.TestCase):
    """Test _build_providers for various data sources."""

    @patch("risk_scoring.kusto_source_config.KustoSourceRegistry.from_yaml")
    def test_kusto_only(self, mock_from_yaml):
        mock_reg = MagicMock()
        mock_reg.list_sources.return_value = ["icm", "safefly"]
        mock_from_yaml.return_value = mock_reg

        providers, repo = _build_providers("kusto")

        self.assertEqual(len(providers), 1)
        self.assertIsNone(repo)
        mock_from_yaml.assert_called_once()

    @patch("risk_scoring.cli.Neo4jHttpConfig")
    @patch("risk_scoring.cli.Neo4jHttpExecutor")
    @patch("risk_scoring.cli.Neo4jHttpEntityRepository")
    @patch("risk_scoring.cli.EvidenceClient")
    def test_neo4j_only(self, MockClient, MockRepo, MockExec, MockConfig):
        providers, repo = _build_providers("neo4j")

        self.assertEqual(len(providers), 1)
        self.assertIsNotNone(repo)

    @patch("risk_scoring.kusto_source_config.KustoSourceRegistry.from_yaml")
    @patch("risk_scoring.cli.Neo4jHttpConfig")
    @patch("risk_scoring.cli.Neo4jHttpExecutor")
    @patch("risk_scoring.cli.Neo4jHttpEntityRepository")
    @patch("risk_scoring.cli.EvidenceClient")
    def test_hybrid(self, MockClient, MockRepo, MockExec, MockConfig, mock_from_yaml):
        mock_reg = MagicMock()
        mock_reg.list_sources.return_value = ["icm"]
        mock_from_yaml.return_value = mock_reg

        providers, repo = _build_providers("hybrid")

        self.assertEqual(len(providers), 2)
        self.assertIsNotNone(repo)


# ---------------------------------------------------------------------------
# main() integration tests
# ---------------------------------------------------------------------------


class TestMainValidation(unittest.TestCase):
    """Test CLI validation logic in main()."""

    def test_no_identity_flag_errors(self):
        """Must provide at least one of --resource-id, --service-name, --repo-uri."""
        with self.assertRaises(SystemExit) as ctx:
            main(["--environment", "prod"])
        self.assertEqual(ctx.exception.code, 2)

    @patch("risk_scoring.cli._resolve_repo_to_service", return_value=None)
    @patch("risk_scoring.cli._resolve_data_source", return_value="kusto")
    def test_repo_uri_unresolvable_errors(self, _rds, _rr):
        """--repo-uri that cannot be resolved to a service should fail."""
        code = main(
            ["--repo-uri", "https://dev.azure.com/a/b/_git/c", "--environment", "prod"]
        )
        self.assertEqual(code, 1)

    @patch("risk_scoring.cli._resolve_data_source", return_value="kusto")
    def test_kusto_without_service_name_or_resource_id_errors(self, _rd):
        """--data-source=kusto without --service-name and --resource-id should fail."""
        # argparse rejects completely missing identity flags with SystemExit(2)
        with self.assertRaises(SystemExit) as ctx:
            main(
                ["--environment", "prod", "--data-source", "kusto"]
            )
        self.assertEqual(ctx.exception.code, 2)

    @patch("risk_scoring.cli._resolve_data_source", return_value="neo4j")
    def test_neo4j_without_resource_id_errors(self, _rd):
        """--data-source=neo4j without --resource-id should fail."""
        code = main(
            ["--service-name", "My Svc", "--environment", "prod", "--data-source", "neo4j"]
        )
        self.assertEqual(code, 1)


class TestMainEndToEnd(unittest.TestCase):
    """E2E tests with fully mocked backends."""

    @patch("risk_scoring.cli._run_legacy_neo4j")
    @patch("risk_scoring.cli._resolve_data_source", return_value="neo4j")
    def test_neo4j_legacy_path(self, _rds, mock_legacy):
        """--resource-id with neo4j source uses legacy path."""
        mock_result = MagicMock()
        mock_result.report_markdown = "# Report"
        mock_result.report_json_string.return_value = '{"score": 42}'
        mock_legacy.return_value = mock_result

        code = main(
            ["--resource-id", "res-x", "--environment", "prod", "--data-source", "neo4j"]
        )
        self.assertEqual(code, 0)
        mock_legacy.assert_called_once()

    @patch("risk_scoring.cli._run_providers")
    @patch("risk_scoring.cli._resolve_data_source", return_value="kusto")
    def test_kusto_with_service_name(self, _rds, mock_prov):
        """--service-name with kusto source uses provider path."""
        mock_result = MagicMock()
        mock_result.report_markdown = "# Report"
        mock_prov.return_value = mock_result

        code = main(
            [
                "--service-name", "Azure Postgres Flex",
                "--environment", "prod",
                "--data-source", "kusto",
            ]
        )
        self.assertEqual(code, 0)
        mock_prov.assert_called_once()

    @patch("risk_scoring.cli._run_providers")
    @patch("risk_scoring.cli._resolve_data_source", return_value="hybrid")
    def test_hybrid_mode(self, _rds, mock_prov):
        mock_result = MagicMock()
        mock_result.report_markdown = "# Report"
        mock_prov.return_value = mock_result

        code = main(
            [
                "--resource-id", "res-x",
                "--environment", "prod",
                "--data-source", "hybrid",
            ]
        )
        self.assertEqual(code, 0)
        mock_prov.assert_called_once()

    @patch("risk_scoring.cli._run_providers")
    @patch("risk_scoring.cli._resolve_data_source", return_value="neo4j")
    def test_neo4j_with_service_name_uses_providers(self, _rds, mock_prov):
        """When --service-name is supplied, even neo4j uses provider path."""
        mock_result = MagicMock()
        mock_result.report_markdown = "# Report"
        mock_prov.return_value = mock_result

        code = main(
            [
                "--resource-id", "res-x",
                "--service-name", "My Svc",
                "--environment", "prod",
                "--data-source", "neo4j",
            ]
        )
        self.assertEqual(code, 0)
        mock_prov.assert_called_once()

    @patch("risk_scoring.cli._run_providers")
    @patch("risk_scoring.cli._resolve_data_source", return_value="kusto")
    def test_output_json(self, _rds, mock_prov):
        mock_result = MagicMock()
        mock_result.report_json_string.return_value = '{"score": 55}'
        mock_prov.return_value = mock_result

        code = main(
            [
                "--service-name", "Svc",
                "--environment", "dev",
                "--data-source", "kusto",
                "--output-format", "json",
            ]
        )
        self.assertEqual(code, 0)


class TestMainExceptionHandling(unittest.TestCase):
    """Test that exceptions are caught and produce correct exit codes."""

    @patch("risk_scoring.cli._resolve_data_source", return_value="neo4j")
    @patch(
        "risk_scoring.cli._run_legacy_neo4j",
        side_effect=Exception("boom"),
    )
    def test_generic_exception_returns_1(self, _run, _rds):
        code = main(
            ["--resource-id", "res-x", "--environment", "prod", "--data-source", "neo4j"]
        )
        self.assertEqual(code, 1)

    @patch("risk_scoring.cli._resolve_data_source", return_value="neo4j")
    @patch("risk_scoring.cli._run_legacy_neo4j")
    def test_neo4j_http_error_returns_2(self, mock_run, _rds):
        from risk_scoring.neo4j_http import Neo4jHttpError

        mock_run.side_effect = Neo4jHttpError("no connection")

        code = main(
            ["--resource-id", "res-x", "--environment", "prod", "--data-source", "neo4j"]
        )
        self.assertEqual(code, 2)



# ---------------------------------------------------------------------------
# Repo-URI resolution
# ---------------------------------------------------------------------------


class TestResolveRepoToService(unittest.TestCase):
    """Test _resolve_repo_to_service helper."""

    @patch("risk_scoring.kusto_source_config.KustoSourceRegistry")
    def test_successful_resolution(self, MockRegistry):
        mock_reg = MagicMock()
        mock_reg.resolve_service_from_repo.return_value = "Azure Postgres Flex"
        MockRegistry.from_yaml.return_value = mock_reg

        result = _resolve_repo_to_service("https://dev.azure.com/org/proj/_git/repo")
        self.assertEqual(result, "Azure Postgres Flex")
        mock_reg.resolve_service_from_repo.assert_called_once_with(
            "https://dev.azure.com/org/proj/_git/repo"
        )

    @patch("risk_scoring.kusto_source_config.KustoSourceRegistry")
    def test_resolution_returns_none_when_no_match(self, MockRegistry):
        mock_reg = MagicMock()
        mock_reg.resolve_service_from_repo.return_value = None
        MockRegistry.from_yaml.return_value = mock_reg

        result = _resolve_repo_to_service("https://dev.azure.com/org/proj/_git/unknown")
        self.assertIsNone(result)

    @patch("risk_scoring.kusto_source_config.KustoSourceRegistry")
    def test_resolution_returns_none_on_exception(self, MockRegistry):
        MockRegistry.from_yaml.side_effect = RuntimeError("Kusto unavailable")

        result = _resolve_repo_to_service("https://dev.azure.com/org/proj/_git/repo")
        self.assertIsNone(result)


# ---------------------------------------------------------------------------
# main() repo-URI integration tests
# ---------------------------------------------------------------------------


class TestMainRepoUri(unittest.TestCase):
    """Test --repo-uri flows through main()."""

    @patch("risk_scoring.cli._run_providers")
    @patch("risk_scoring.cli._resolve_repo_to_service", return_value="My Svc")
    @patch("risk_scoring.cli._resolve_data_source", return_value="kusto")
    def test_repo_uri_resolves_and_runs(self, _rds, _rr, mock_prov):
        """--repo-uri that resolves to a service should proceed normally."""
        mock_result = MagicMock()
        mock_result.report_markdown = "# Report"
        mock_prov.return_value = mock_result

        code = main(
            ["--repo-uri", "https://dev.azure.com/org/proj/_git/repo",
             "--environment", "prod"]
        )
        self.assertEqual(code, 0)
        mock_prov.assert_called_once()

        # Verify the resolved service_name was promoted
        call_args = mock_prov.call_args
        args_passed = call_args[0][0]  # first positional arg is args namespace
        self.assertEqual(args_passed.service_name, "My Svc")

    @patch("risk_scoring.cli._resolve_repo_to_service", return_value=None)
    @patch("risk_scoring.cli._resolve_data_source", return_value="kusto")
    def test_repo_uri_no_match_returns_1(self, _rds, _rr):
        """--repo-uri with no service match should return exit code 1."""
        code = main(
            ["--repo-uri", "https://dev.azure.com/org/proj/_git/nope",
             "--environment", "prod"]
        )
        self.assertEqual(code, 1)

    @patch("risk_scoring.cli._resolve_data_source", return_value="neo4j")
    def test_repo_uri_without_kusto_returns_1(self, _rds):
        """--repo-uri with neo4j-only data source should fail."""
        code = main(
            ["--repo-uri", "https://dev.azure.com/org/proj/_git/repo",
             "--environment", "prod", "--data-source", "neo4j"]
        )
        self.assertEqual(code, 1)

    @patch("risk_scoring.cli._run_providers")
    @patch("risk_scoring.cli._resolve_repo_to_service", return_value="Svc X")
    @patch("risk_scoring.cli._resolve_data_source", return_value="hybrid")
    def test_repo_uri_hybrid_mode(self, _rds, _rr, mock_prov):
        """--repo-uri should also work in hybrid mode."""
        mock_result = MagicMock()
        mock_result.report_markdown = "# Report"
        mock_prov.return_value = mock_result

        code = main(
            ["--repo-uri", "https://dev.azure.com/org/proj/_git/repo",
             "--resource-id", "res-x",
             "--environment", "prod", "--data-source", "hybrid"]
        )
        self.assertEqual(code, 0)
        mock_prov.assert_called_once()

    @patch("risk_scoring.cli._run_providers")
    @patch("risk_scoring.cli._resolve_repo_to_service", return_value="Resolved Svc")
    @patch("risk_scoring.cli._resolve_data_source", return_value="kusto")
    def test_repo_uri_sets_label_repository(self, _rds, _rr, mock_prov):
        """When --repo-uri without --resource-id, label should be 'Repository'."""
        mock_result = MagicMock()
        mock_result.report_markdown = "# Report"
        mock_prov.return_value = mock_result

        code = main(
            ["--repo-uri", "https://dev.azure.com/org/proj/_git/repo",
             "--environment", "prod"]
        )
        self.assertEqual(code, 0)

        # _run_providers builds a ResolvedEntityRef — verify it was called
        call_args = mock_prov.call_args
        args_passed = call_args[0][0]
        # service_name should be promoted from repo resolution
        self.assertEqual(args_passed.service_name, "Resolved Svc")
        # repo_uri should still be set
        self.assertEqual(args_passed.repo_uri, "https://dev.azure.com/org/proj/_git/repo")


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


class TestWriteOutput(unittest.TestCase):
    """Test _write_output with different formats."""

    def _make_args(self, fmt="markdown", output_file=None):
        return create_parser().parse_args(
            [
                "--resource-id", "x",
                "--environment", "prod",
                "--output-format", fmt,
                *(["--output-file", output_file] if output_file else []),
            ]
        )

    def test_markdown_output(self):
        from risk_scoring.cli import _write_output

        result = MagicMock()
        result.report_markdown = "# Test Report\nScore: 42"
        args = self._make_args("markdown")

        # Should not raise
        _write_output(result, args)

    def test_json_output(self):
        from risk_scoring.cli import _write_output

        result = MagicMock()
        result.report_json_string.return_value = '{"score": 42}'
        args = self._make_args("json")

        _write_output(result, args)

    def test_both_output(self):
        from risk_scoring.cli import _write_output

        result = MagicMock()
        result.report_markdown = "# md"
        result.report_json_string.return_value = '{"a": 1}'
        args = self._make_args("both")

        _write_output(result, args)

    def test_output_to_file(self, tmp_dir=None):
        import tempfile

        from risk_scoring.cli import _write_output

        result = MagicMock()
        result.report_markdown = "# File Report"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            path = f.name

        try:
            args = self._make_args("markdown", output_file=path)
            _write_output(result, args)

            with open(path) as f:
                content = f.read()
            self.assertEqual(content, "# File Report")
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
