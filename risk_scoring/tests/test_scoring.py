import unittest

from risk_scoring.scoring import ChangeContext, score_change


class TestScoringDeterminism(unittest.TestCase):
    def test_change_context_operations_are_canonicalized(self) -> None:
        c1 = ChangeContext.create(environment="prod", operations=["Update", "Delete", "update"])
        c2 = ChangeContext.create(environment="prod", operations=["delete", "update"])
        self.assertEqual(c1.operations, c2.operations)
        self.assertEqual(c1.operations, ("delete", "update"))

    def test_golden_case_medium(self) -> None:
        """Test with partial evidence — v0.2 model (10 factors)."""
        change = ChangeContext.create(environment="prod")
        evidence = {
            "subscription_count": 3,
            "historical_outages_180d": 1,
            "recent_active_outages": 1,
            "deployment_count_30d": 10,
        }

        result = score_change(change, evidence)
        # subscription_count=3 → 5 pts, outages_180d=1 → 5 pts,
        # recent_active_outages=1 → 5 pts, deployments_30d=10 → 5 pts = 20
        self.assertEqual(result.risk_score, 20)
        self.assertEqual(result.risk_level, "LOW")

        factor_ids = [f.factor_id for f in result.factors]
        self.assertEqual(
            factor_ids,
            [
                "deployment.change_caused_outages",
                "incident.recurrence",
                "blast_radius.subscriptions",
                "history.outages_180d",
                "incident.mttm",
                "ops.deployments_30d",
                "change.destructive",
                "incident.severity_mix",
                "resource.peer_impact",
                "ops.recent_active_outages",
            ],
        )

        # New factors should be unknown since evidence not provided
        self.assertIn("safefly_caused_outages_180d", result.unknowns)
        self.assertIn("avg_mttm_minutes", result.unknowns)
        self.assertIn("peer_resource_count", result.unknowns)
        self.assertIn("related_incidents", result.unknowns)
        self.assertIn("sev12_incident_count", result.unknowns)

    def test_deterministic_to_dict(self) -> None:
        change = ChangeContext.create(environment="staging", operations=["update"])
        evidence = {
            "subscription_count": 1,
            "historical_outages_180d": 0,
            "recent_active_outages": 0,
            "deployment_count_30d": 9,
        }

        r1 = score_change(change, evidence).to_dict()
        r2 = score_change(change, evidence).to_dict()
        self.assertEqual(r1, r2)

    def test_missing_evidence_is_explicit_unknown(self) -> None:
        change = ChangeContext.create(environment="prod")
        evidence = {
            "subscription_count": 1,
            "historical_outages_180d": 0,
            "recent_active_outages": 0,
            # deployment_count_30d omitted
        }

        result = score_change(change, evidence)
        self.assertIn("deployment_count_30d", result.unknowns)

        dep_factor = [f for f in result.factors if f.factor_id == "ops.deployments_30d"][0]
        self.assertEqual(dep_factor.status, "unknown")
        self.assertEqual(dep_factor.points, 0)

    def test_new_factors_from_v02(self) -> None:
        """Test new v0.2 factors: severity_mix, rebalanced subscriptions."""
        change = ChangeContext.create(environment="prod")
        evidence = {
            "subscription_count": 5,
            "historical_outages_180d": 0,
            "recent_active_outages": 0,
            "deployment_count_30d": 5,
            # New v0.2 evidence
            "avg_mttm_minutes": 45,  # 45 min MTTM = 7 pts
            "peer_resource_count": 6,  # 6 peers = 5 pts
            "related_incidents": 1,  # 1 related = 4 pts
            "sev12_incident_count": 2,  # 2 sev1/2 = 5 pts
        }

        result = score_change(change, evidence)

        # subs=5→8, mttm=7, peers=5, recurrence=4, severity=5 = 29
        self.assertEqual(result.risk_score, 29)
        self.assertEqual(result.risk_level, "LOW")

        # Verify new factor
        sev_factor = [f for f in result.factors if f.factor_id == "incident.severity_mix"][0]
        self.assertEqual(sev_factor.status, "hit")
        self.assertEqual(sev_factor.points, 5)

        mttm_factor = [f for f in result.factors if f.factor_id == "incident.mttm"][0]
        self.assertEqual(mttm_factor.status, "hit")
        self.assertEqual(mttm_factor.points, 7)

        peer_factor = [f for f in result.factors if f.factor_id == "resource.peer_impact"][0]
        self.assertEqual(peer_factor.status, "hit")
        self.assertEqual(peer_factor.points, 5)

        recurrence_factor = [f for f in result.factors if f.factor_id == "incident.recurrence"][0]
        self.assertEqual(recurrence_factor.status, "hit")
        self.assertEqual(recurrence_factor.points, 4)


if __name__ == "__main__":
    unittest.main()
