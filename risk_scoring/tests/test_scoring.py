import unittest

from risk_scoring.scoring import ChangeContext, score_change


class TestScoringDeterminism(unittest.TestCase):
    def test_change_context_operations_are_canonicalized(self) -> None:
        c1 = ChangeContext.create(environment="prod", operations=["Update", "Delete", "update"])
        c2 = ChangeContext.create(environment="prod", operations=["delete", "update"])
        self.assertEqual(c1.operations, c2.operations)
        self.assertEqual(c1.operations, ("delete", "update"))

    def test_golden_case_68_high(self) -> None:
        change = ChangeContext.create(environment="prod")
        evidence = {
            "services_impacted": 3,
            "critical_services": ["svc-alpha"],
            "historical_outages_180d": 1,
            "open_icms": 1,
            "deployment_count_30d": 10,
        }

        result = score_change(change, evidence)
        self.assertEqual(result.risk_score, 68)
        self.assertEqual(result.risk_level, "HIGH")

        factor_ids = [f.factor_id for f in result.factors]
        self.assertEqual(
            factor_ids,
            [
                "env.production",
                "blast_radius.services",
                "blast_radius.critical_services",
                "history.outages_180d",
                "ops.open_icms",
                "ops.deployments_30d",
                "change.destructive",
                "deployment.stage_failures",
                "incident.mttm",
                "artifact.deep_deps",
                "resource.peer_impact",
                "incident.recurrence",
                "template.complexity",
            ],
        )

        # New factors should be unknown since evidence not provided
        self.assertIn("deployment_stage_failures", result.unknowns)
        self.assertIn("avg_mttm_minutes", result.unknowns)
        self.assertIn("max_dependency_depth", result.unknowns)
        self.assertIn("peer_resource_count", result.unknowns)
        self.assertIn("related_incidents", result.unknowns)

    def test_deterministic_to_dict(self) -> None:
        change = ChangeContext.create(environment="staging", operations=["update"])
        evidence = {
            "services_impacted": 1,
            "critical_services": [],
            "historical_outages_180d": 0,
            "open_icms": 0,
            "deployment_count_30d": 9,
        }

        r1 = score_change(change, evidence).to_dict()
        r2 = score_change(change, evidence).to_dict()
        self.assertEqual(r1, r2)

    def test_missing_evidence_is_explicit_unknown(self) -> None:
        change = ChangeContext.create(environment="prod")
        evidence = {
            "services_impacted": 1,
            "critical_services": [],
            "historical_outages_180d": 0,
            "open_icms": 0,
            # deployment_count_30d omitted
        }

        result = score_change(change, evidence)
        self.assertIn("deployment_count_30d", result.unknowns)

        dep_factor = [f for f in result.factors if f.factor_id == "ops.deployments_30d"][0]
        self.assertEqual(dep_factor.status, "unknown")
        self.assertEqual(dep_factor.points, 0)

    def test_new_hierarchical_factors(self) -> None:
        """Test new factors that use hierarchical graph data."""
        change = ChangeContext.create(environment="prod")
        evidence = {
            "services_impacted": 1,
            "critical_services": [],
            "historical_outages_180d": 0,
            "open_icms": 0,
            "deployment_count_30d": 5,
            # New hierarchical evidence
            "deployment_stage_failures": 2,  # 2 failed stages = 10 pts
            "avg_mttm_minutes": 45,  # 45 min MTTM = 7 pts
            "max_dependency_depth": 3,  # depth 3 = 10 pts
            "peer_resource_count": 6,  # 6 peers = 5 pts
            "related_incidents": 1,  # 1 related = 4 pts
        }

        result = score_change(change, evidence)
        
        # Base score: 20 (prod) + 5 (1 svc) + 0 + 0 + 0 + 0 + 0 = 25
        # New factors: 10 + 7 + 10 + 5 + 4 = 36
        # Total: 61
        self.assertEqual(result.risk_score, 61)
        self.assertEqual(result.risk_level, "MEDIUM")

        # Verify new factors are present
        stage_failure_factor = [f for f in result.factors if f.factor_id == "deployment.stage_failures"][0]
        self.assertEqual(stage_failure_factor.status, "hit")
        self.assertEqual(stage_failure_factor.points, 10)

        mttm_factor = [f for f in result.factors if f.factor_id == "incident.mttm"][0]
        self.assertEqual(mttm_factor.status, "hit")
        self.assertEqual(mttm_factor.points, 7)

        deps_factor = [f for f in result.factors if f.factor_id == "artifact.deep_deps"][0]
        self.assertEqual(deps_factor.status, "hit")
        self.assertEqual(deps_factor.points, 10)

        peer_factor = [f for f in result.factors if f.factor_id == "resource.peer_impact"][0]
        self.assertEqual(peer_factor.status, "hit")
        self.assertEqual(peer_factor.points, 5)

        recurrence_factor = [f for f in result.factors if f.factor_id == "incident.recurrence"][0]
        self.assertEqual(recurrence_factor.status, "hit")
        self.assertEqual(recurrence_factor.points, 4)

    def test_template_complexity_high(self) -> None:
        """Test template complexity factor with high complexity (max 10 pts)."""
        change = ChangeContext.create(environment="prod")
        evidence = {
            "services_impacted": 1,
            "critical_services": [],
            "historical_outages_180d": 0,
            "open_icms": 0,
            "deployment_count_30d": 0,
            "template_required_dependency_count": 5,  # > 3 = 5 pts
            "template_max_dependency_depth": 3,  # > 2 = 5 pts
        }

        result = score_change(change, evidence)
        template_factor = [f for f in result.factors if f.factor_id == "template.complexity"][0]
        self.assertEqual(template_factor.status, "hit")
        self.assertEqual(template_factor.points, 10)
        self.assertEqual(template_factor.max_points, 10)

    def test_template_complexity_partial(self) -> None:
        """Test template complexity factor with partial complexity (5 pts)."""
        change = ChangeContext.create(environment="prod")
        evidence = {
            "services_impacted": 1,
            "critical_services": [],
            "historical_outages_180d": 0,
            "open_icms": 0,
            "deployment_count_30d": 0,
            "template_required_dependency_count": 2,  # <= 3 = 0 pts
            "template_max_dependency_depth": 3,  # > 2 = 5 pts
        }

        result = score_change(change, evidence)
        template_factor = [f for f in result.factors if f.factor_id == "template.complexity"][0]
        self.assertEqual(template_factor.status, "hit")
        self.assertEqual(template_factor.points, 5)

    def test_template_complexity_low(self) -> None:
        """Test template complexity factor with low complexity (0 pts)."""
        change = ChangeContext.create(environment="prod")
        evidence = {
            "services_impacted": 1,
            "critical_services": [],
            "historical_outages_180d": 0,
            "open_icms": 0,
            "deployment_count_30d": 0,
            "template_required_dependency_count": 1,  # <= 3 = 0 pts
            "template_max_dependency_depth": 2,  # <= 2 = 0 pts
        }

        result = score_change(change, evidence)
        template_factor = [f for f in result.factors if f.factor_id == "template.complexity"][0]
        self.assertEqual(template_factor.status, "miss")
        self.assertEqual(template_factor.points, 0)

    def test_template_complexity_missing(self) -> None:
        """Test template complexity factor with missing evidence."""
        change = ChangeContext.create(environment="prod")
        evidence = {
            "services_impacted": 1,
            "critical_services": [],
            "historical_outages_180d": 0,
            "open_icms": 0,
            "deployment_count_30d": 0,
            # template data omitted
        }

        result = score_change(change, evidence)
        self.assertIn("template_required_dependency_count", result.unknowns)
        self.assertIn("template_max_dependency_depth", result.unknowns)

        template_factor = [f for f in result.factors if f.factor_id == "template.complexity"][0]
        self.assertEqual(template_factor.status, "unknown")
        self.assertEqual(template_factor.points, 0)


if __name__ == "__main__":
    unittest.main()
