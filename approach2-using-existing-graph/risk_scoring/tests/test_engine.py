import sys
import unittest
from datetime import date
from pathlib import Path

# Ensure approach2-using-existing-graph is on sys.path so we can import risk_scoring.
THIS_DIR = Path(__file__).resolve().parent
APPROACH2_DIR = THIS_DIR.parent.parent
sys.path.insert(0, str(APPROACH2_DIR))

from risk_scoring.engine import assess_resource_change  # noqa: E402
from risk_scoring.evidence_client import CypherExecutor, EvidenceClient  # noqa: E402
from risk_scoring.models import CandidateEntity, ResourceSpec  # noqa: E402
from risk_scoring.repository import InMemoryRepository  # noqa: E402
from risk_scoring.scoring import ChangeContext  # noqa: E402


class FakeExecutor(CypherExecutor):
    def __init__(self):
        self.calls = []

    def run_readonly(self, cypher: str, params: dict):
        self.calls.append({"cypher": cypher, "params": dict(params)})

        # resource_context
        if "MATCH (r:AzureResource" in cypher and "OWNS_RESOURCE" in cypher:
            return [
                {
                    "resourceName": params["resourceName"],
                    "resourceType": "Microsoft.Web/sites",
                    "serviceId": "SVC-1",
                    "serviceName": "Service One",
                    "resourceGroupKey": "subs|rg",
                    "resourceGroupName": "rg",
                    "subscriptionId": "subs",
                }
            ]

        # incidents
        if "MATCH (s:Service" in cypher and "Incident" in cypher:
            return [
                {
                    "incidentId": "ICM-1",
                    "createdDate": "2025-12-01",
                    "severity": "High",
                    "changeRelated": "Yes",
                    "title": "x",
                }
            ]

        # deployments
        if "MATCH (d:Deployment" in cypher:
            return [
                {"rolloutId": "RL-1", "rolloutInfra": "i", "artifactVersion": "v"}
            ]

        raise AssertionError("Unexpected cypher")


class TestEngine(unittest.TestCase):
    def test_end_to_end_engine_is_deterministic(self) -> None:
        repo = InMemoryRepository(
            [CandidateEntity(label="AzureResource", resource_id="res-x")]
        )
        client = EvidenceClient(FakeExecutor())
        resource = ResourceSpec(resource_id="res-x")
        change = ChangeContext.create(environment="prod")

        r1 = assess_resource_change(
            repo=repo,
            evidence_client=client,
            resource=resource,
            change=change,
            as_of=date(2026, 1, 1),
            report_id=None,
        )
        r2 = assess_resource_change(
            repo=repo,
            evidence_client=client,
            resource=resource,
            change=change,
            as_of=date(2026, 1, 1),
            report_id=None,
        )

        self.assertEqual(r1.report_json, r2.report_json)
        self.assertEqual(r1.report_markdown, r2.report_markdown)

        # Sanity: report includes query appendix and score summary
        self.assertIn("evidence_queries", r1.report_json)
        self.assertEqual(r1.report_json["score"]["risk_level"], r1.score.risk_level)


if __name__ == "__main__":
    unittest.main()
