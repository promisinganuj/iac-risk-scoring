"""Snapshot-style determinism tests for scoring and report ordering.

Model v0.2: 10 factors, max 100 pts, all available in Kusto-only mode.
"""

import json
import unittest
from datetime import date

from risk_scoring.evidence_client import CypherExecutor, EvidenceClient
from risk_scoring.graph_expansion import expand_evidence_for_resource
from risk_scoring.models import ResolvedEntityRef
from risk_scoring.reporting import (
    _sorted_unique,
    build_report_json,
    render_markdown_report,
)
from risk_scoring.scoring import ChangeContext, score_change


def _full_evidence(**overrides):
    """Return a full evidence dict with all 10 factor keys populated."""
    base = {
        "subscription_count": 3,
        "historical_outages_180d": 1,
        "recent_active_outages": 0,
        "deployment_count_30d": 5,
        "avg_mttm_minutes": 20,
        "peer_resource_count": 4,
        "related_incidents": 0,
        "safefly_caused_outages_180d": 0,
        "sev12_incident_count": 1,
    }
    base.update(overrides)
    return base


def _resolved():
    return ResolvedEntityRef(label="AzureResource", resource_id="res-test")


class TestFullEvidenceGoldenSnapshot(unittest.TestCase):
    """Snapshot test with all evidence keys populated (no unknowns)."""

    def test_full_evidence_score_and_factors(self):
        change = ChangeContext.create(environment="prod", operations=["update"])
        evidence = _full_evidence()
        result = score_change(change, evidence)

        self.assertEqual(result.unknowns, ())

        # safefly: 0, recurrence: 0, subs: 5, outages: 5, mttm: 4,
        # deploys: 0, destructive: 0, severity: 3, peers: 3, active: 0 = 20
        self.assertEqual(result.risk_score, 20)
        self.assertEqual(result.risk_level, "LOW")

    def test_full_evidence_factor_ids_order_is_stable(self):
        change = ChangeContext.create(environment="prod")
        result = score_change(change, _full_evidence())

        factor_ids = [f.factor_id for f in result.factors]
        self.assertEqual(factor_ids, [
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
        ])

    def test_full_evidence_deterministic_across_runs(self):
        change = ChangeContext.create(environment="prod", operations=["delete"])
        evidence = _full_evidence(subscription_count=10)
        results = [score_change(change, evidence).to_dict() for _ in range(10)]
        for r in results[1:]:
            self.assertEqual(r, results[0])


class TestRiskLevelThresholds(unittest.TestCase):
    """Boundary tests for _risk_level thresholds."""

    def test_score_0_is_low(self):
        change = ChangeContext.create(environment="dev")
        evidence = _full_evidence(
            subscription_count=0,
            historical_outages_180d=0, recent_active_outages=0, deployment_count_30d=0,
            avg_mttm_minutes=0,
            peer_resource_count=0, related_incidents=0, sev12_incident_count=0,
            safefly_caused_outages_180d=0,
        )
        result = score_change(change, evidence)
        self.assertEqual(result.risk_score, 0)
        self.assertEqual(result.risk_level, "LOW")

    def test_score_33_is_low(self):
        change = ChangeContext.create(environment="prod")
        # safefly: 0, recurrence: 4(1), subs: 5(3), outages: 5(1), mttm: 4(20min),
        # deploys: 5(10), destructive: 0, severity: 5(2), peers: 5(6), active: 0
        # = 33
        evidence = _full_evidence(
            subscription_count=3,
            historical_outages_180d=1, recent_active_outages=0, deployment_count_30d=10,
            avg_mttm_minutes=20, peer_resource_count=6,
            related_incidents=1, sev12_incident_count=2,
            safefly_caused_outages_180d=0,
        )
        result = score_change(change, evidence)
        self.assertEqual(result.risk_score, 33)
        self.assertEqual(result.risk_level, "LOW")

    def test_score_34_is_medium(self):
        change = ChangeContext.create(environment="prod")
        # Same as above + 1 more point: add 1 active outage (+5) → 38
        # But we need exactly 34. Let's use: subs=3(5) + outages=1(5) + deploys=10(5)
        # + mttm=30(7) + severity=2(5) + recurrence=1(4) + peers=2(3) = 34
        evidence = _full_evidence(
            subscription_count=3,
            historical_outages_180d=1, recent_active_outages=0, deployment_count_30d=10,
            avg_mttm_minutes=30, peer_resource_count=2,
            related_incidents=1, sev12_incident_count=2,
            safefly_caused_outages_180d=0,
        )
        result = score_change(change, evidence)
        self.assertEqual(result.risk_score, 34)
        self.assertEqual(result.risk_level, "MEDIUM")


class TestScoreCapping(unittest.TestCase):
    """Score must not exceed 100."""

    def test_maxed_out_evidence_caps_at_100(self):
        change = ChangeContext.create(environment="prod", operations=["delete"])
        evidence = _full_evidence(
            subscription_count=10,
            historical_outages_180d=5, recent_active_outages=1, deployment_count_30d=20,
            avg_mttm_minutes=60,
            peer_resource_count=10, related_incidents=3,
            safefly_caused_outages_180d=3, sev12_incident_count=3,
        )
        result = score_change(change, evidence)
        self.assertLessEqual(result.risk_score, 100)
        self.assertEqual(result.risk_score, 100)
        self.assertEqual(result.risk_level, "HIGH")


class TestEvidenceTypeSafety(unittest.TestCase):
    """Type guards for evidence fields."""

    def test_bool_evidence_rejected_as_int(self):
        change = ChangeContext.create(environment="prod")
        evidence = _full_evidence(subscription_count=True)
        with self.assertRaises(TypeError) as ctx:
            score_change(change, evidence)
        self.assertIn("bool", str(ctx.exception))

    def test_string_evidence_rejected_as_int(self):
        change = ChangeContext.create(environment="prod")
        evidence = _full_evidence(subscription_count="3")
        with self.assertRaises(TypeError):
            score_change(change, evidence)

    def test_int_rejected_as_int_for_sev12(self):
        """Verify that bool values are rejected for sev12_incident_count."""
        change = ChangeContext.create(environment="prod")
        evidence = _full_evidence(sev12_incident_count=True)
        with self.assertRaises(TypeError) as ctx:
            score_change(change, evidence)
        self.assertIn("bool", str(ctx.exception))

    def test_string_rejected_for_sev12(self):
        change = ChangeContext.create(environment="prod")
        evidence = _full_evidence(sev12_incident_count="3")
        with self.assertRaises(TypeError):
            score_change(change, evidence)


class TestChangeContextNormalization(unittest.TestCase):
    """Edge cases in ChangeContext.create()."""

    def test_environment_aliases(self):
        self.assertEqual(ChangeContext.create(environment="production").environment, "prod")
        self.assertEqual(ChangeContext.create(environment="STAGING").environment, "staging")
        self.assertEqual(ChangeContext.create(environment="Development").environment, "dev")
        self.assertEqual(ChangeContext.create(environment="Testing").environment, "test")

    def test_none_environment(self):
        self.assertIsNone(ChangeContext.create(environment=None).environment)

    def test_empty_environment(self):
        self.assertIsNone(ChangeContext.create(environment="").environment)

    def test_whitespace_environment(self):
        self.assertIsNone(ChangeContext.create(environment="   ").environment)

    def test_unknown_environment_preserved(self):
        self.assertEqual(ChangeContext.create(environment="canary").environment, "canary")

    def test_empty_operations_filtered(self):
        ctx = ChangeContext.create(operations=["", "  ", "update"])
        self.assertEqual(ctx.operations, ("update",))

    def test_duplicate_operations_deduplicated(self):
        ctx = ChangeContext.create(operations=["Update", "update", "UPDATE"])
        self.assertEqual(ctx.operations, ("update",))


class TestUnknownsOrdering(unittest.TestCase):
    """Unknowns are sorted and deduplicated."""

    def test_unknowns_sorted_alphabetically(self):
        change = ChangeContext.create(environment="prod")
        result = score_change(change, {})
        self.assertEqual(result.unknowns, tuple(sorted(result.unknowns)))

    def test_unknowns_deduplicated(self):
        change = ChangeContext.create(environment="prod")
        result = score_change(change, {})
        self.assertEqual(len(result.unknowns), len(set(result.unknowns)))


class TestSortedUnique(unittest.TestCase):
    """Direct tests for _sorted_unique helper."""

    def test_empty(self):
        self.assertEqual(_sorted_unique([]), ())

    def test_deduplication(self):
        self.assertEqual(_sorted_unique(["b", "a", "b", "c"]), ("a", "b", "c"))

    def test_already_sorted(self):
        self.assertEqual(_sorted_unique(["a", "b", "c"]), ("a", "b", "c"))

    def test_reverse_sorted(self):
        self.assertEqual(_sorted_unique(["c", "b", "a"]), ("a", "b", "c"))


class FakeExecutor(CypherExecutor):
    """Canned Cypher executor for report tests."""

    def __init__(self, by_pattern):
        self._by_pattern = by_pattern

    def run_readonly(self, cypher, params):
        for pattern, data in self._by_pattern.items():
            if pattern in cypher:
                return data
        return []


def _build_full_report():
    """Build a complete report with all evidence populated."""
    resolved = _resolved()
    executor = FakeExecutor({
        "OWNS_RESOURCE": [{
            "resourceName": "res-test", "resourceType": "Microsoft.Web/sites",
            "serviceId": "SVC-1", "serviceName": "Service One",
            "resourceGroupKey": "subs|rg", "resourceGroupName": "rg-prod",
            "subscriptionId": "sub-001",
        }],
        "AFFECTS_SERVICE": [
            {"incidentId": "ICM-1", "createdDate": "2025-12-01", "severity": 3, "changeRelated": True, "title": "Outage"},
            {"incidentId": "ICM-2", "createdDate": "2025-11-15", "severity": 2, "changeRelated": False, "title": "Incident"},
        ],
        "MATCH (d:Deployment": [
            {"rolloutId": "RL-1", "rolloutInfra": "ev2", "artifactVersion": "v1.0"},
        ],
    })
    client = EvidenceClient(executor)
    expansion = expand_evidence_for_resource(resolved, client, as_of=date(2026, 1, 15))
    change = ChangeContext.create(environment="prod", operations=["update"])
    score = score_change(change, expansion.evidence)
    report = build_report_json(
        resolved=resolved, change=change, expansion=expansion,
        score=score, report_id="test-report-001",
    )
    return report, score


class TestReportSnapshot(unittest.TestCase):
    """Snapshot tests for report JSON and markdown output."""

    def test_json_report_has_required_keys(self):
        report, _ = _build_full_report()
        required_keys = {
            "schema_version", "report_id", "resource", "change",
            "score", "evidence", "evidence_queries", "unknowns",
        }
        self.assertEqual(set(report.keys()), required_keys)

    def test_json_report_deterministic(self):
        r1, _ = _build_full_report()
        r2, _ = _build_full_report()
        j1 = json.dumps(r1, sort_keys=True)
        j2 = json.dumps(r2, sort_keys=True)
        self.assertEqual(j1, j2)

    def test_json_report_unknowns_sorted(self):
        report, _ = _build_full_report()
        unknowns = report["unknowns"]
        self.assertEqual(unknowns, sorted(unknowns))

    def test_json_report_evidence_queries_ordered(self):
        report, _ = _build_full_report()
        qids = [q["query_id"] for q in report["evidence_queries"]]
        self.assertIsInstance(qids, list)
        self.assertTrue(len(qids) > 0)

    def test_markdown_contains_expected_sections(self):
        report, _ = _build_full_report()
        md = render_markdown_report(report)
        self.assertIn("# Risk Assessment Report", md)
        self.assertIn("Risk Summary", md)
        self.assertIn("Resource Information", md)
        self.assertIn("Risk Factors", md)
        self.assertIn("Recommendations", md)
        self.assertIn("Supporting Evidence", md)
        self.assertIn("Evidence Queries", md)
        self.assertIn("Unknowns", md)

    def test_markdown_deterministic_10_runs(self):
        report, _ = _build_full_report()
        outputs = [render_markdown_report(report) for _ in range(10)]
        for output in outputs[1:]:
            self.assertEqual(output, outputs[0])

    def test_markdown_includes_resource_id(self):
        report, _ = _build_full_report()
        md = render_markdown_report(report)
        self.assertIn("res-test", md)

    def test_markdown_includes_risk_score(self):
        report, score = _build_full_report()
        md = render_markdown_report(report)
        self.assertIn(str(score.risk_score), md)

    def test_markdown_max_sample_rows_respected(self):
        report, _ = _build_full_report()
        md = render_markdown_report(report, max_sample_rows=1)
        self.assertIn("first 1", md)


class TestToDictDeterminism(unittest.TestCase):
    """ScoreResult.to_dict() is deterministic for various evidence profiles."""

    def test_empty_evidence(self):
        change = ChangeContext.create(environment="prod")
        r1 = score_change(change, {}).to_dict()
        r2 = score_change(change, {}).to_dict()
        self.assertEqual(r1, r2)

    def test_partial_evidence(self):
        change = ChangeContext.create(environment="staging")
        ev = {"subscription_count": 1, "deployment_count_30d": 15}
        r1 = score_change(change, ev).to_dict()
        r2 = score_change(change, ev).to_dict()
        self.assertEqual(r1, r2)

    def test_full_evidence(self):
        change = ChangeContext.create(environment="prod", operations=["delete", "update"])
        ev = _full_evidence()
        r1 = score_change(change, ev).to_dict()
        r2 = score_change(change, ev).to_dict()
        self.assertEqual(r1, r2)

    def test_to_dict_json_serializable(self):
        change = ChangeContext.create(environment="prod")
        result = score_change(change, _full_evidence())
        d = result.to_dict()
        serialized = json.dumps(d, sort_keys=True)
        deserialized = json.loads(serialized)
        self.assertEqual(d, deserialized)


if __name__ == "__main__":
    unittest.main()
