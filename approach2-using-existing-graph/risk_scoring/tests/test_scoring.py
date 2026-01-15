import sys
import unittest
from pathlib import Path

# Ensure approach2-using-existing-graph is on sys.path so we can import risk_scoring.
THIS_DIR = Path(__file__).resolve().parent
APPROACH2_DIR = THIS_DIR.parent.parent
sys.path.insert(0, str(APPROACH2_DIR))

from risk_scoring.scoring import ChangeContext, score_change  # noqa: E402


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
            ],
        )

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


if __name__ == "__main__":
    unittest.main()
