import sys
import unittest
from datetime import date
from pathlib import Path

# Ensure approach2-using-existing-graph is on sys.path so we can import risk_scoring.
THIS_DIR = Path(__file__).resolve().parent
APPROACH2_DIR = THIS_DIR.parent.parent
sys.path.insert(0, str(APPROACH2_DIR))

from risk_scoring.evidence_allowlist import get_query  # noqa: E402
from risk_scoring.evidence_client import CypherExecutor, EvidenceClient  # noqa: E402
from risk_scoring.graph_expansion import expand_evidence_for_resource  # noqa: E402
from risk_scoring.models import ResolvedEntityRef  # noqa: E402


class RecordingExecutor(CypherExecutor):
    def __init__(self, responses):
        self.responses = responses
        self.calls = []

        # Invert allowlisted queries by their Cypher string for assertions.
        self.cypher_to_id = {
            get_query("t2.resource_context").cypher: "t2.resource_context",
            get_query("t3.service_incidents").cypher: "t3.service_incidents",
            get_query("t4.service_deployments").cypher: "t4.service_deployments",
        }

    def run_readonly(self, cypher: str, params: dict):
        query_id = self.cypher_to_id.get(cypher)
        if query_id is None:
            raise AssertionError("Unexpected cypher executed")
        self.calls.append({"query_id": query_id, "cypher": cypher, "params": dict(params)})
        return self.responses.get(query_id, [])


class TestGraphExpansion(unittest.TestCase):
    def test_expands_counts_outages_with_as_of(self) -> None:
        responses = {
            "t2.resource_context": [
                {
                    "resourceId": "res-x",
                    "resourceType": "Microsoft.Web/sites",
                    "serviceId": "SVC-1",
                    "serviceName": "Service One",
                    "resourceGroupKey": "subs|rg",
                    "resourceGroupName": "rg",
                    "subscriptionId": "subs",
                }
            ],
            "t3.service_incidents": [
                {
                    "incidentId": "ICM-1",
                    "createdDate": "2025-12-01",
                    "severity": "High",
                    "changeRelated": "Yes",
                    "title": "x",
                },
                {
                    "incidentId": "ICM-2",
                    "createdDate": "2025-06-01",
                    "severity": "Low",
                    "changeRelated": "No",
                    "title": "y",
                },
            ],
            "t4.service_deployments": [
                {"rolloutId": "RL-2", "rolloutInfra": "i", "artifactVersion": "v"},
                {"rolloutId": "RL-1", "rolloutInfra": "i", "artifactVersion": "v"},
            ],
        }

        rec = RecordingExecutor(responses)
        client = EvidenceClient(rec)

        resolved = ResolvedEntityRef(label="AzureResource", resource_id="res-x")
        result = expand_evidence_for_resource(resolved, client, as_of=date(2026, 1, 1))

        self.assertEqual(result.evidence["services_impacted"], 1)
        # cutoff is 2025-07-05; only ICM-1 is within window
        self.assertEqual(result.evidence["historical_outages_180d"], 1)
        self.assertIsNone(result.evidence["open_icms"])
        self.assertIsNone(result.evidence["deployment_count_30d"])
        self.assertEqual(len(result.evidence["recent_incidents"]), 2)
        self.assertEqual(len(result.evidence["recent_deployments"]), 2)

        # Ensure we only used allowlisted query IDs.
        called_query_ids = [c["query_id"] for c in rec.calls]
        self.assertEqual(called_query_ids, ["t2.resource_context", "t3.service_incidents", "t4.service_deployments"])

        # Query runs are captured for reporting.
        self.assertEqual([q.query_id for q in result.queries], called_query_ids)

    def test_missing_as_of_marks_outage_metric_unknown(self) -> None:
        responses = {
            "t2.resource_context": [
                {
                    "resourceId": "res-x",
                    "resourceType": "t",
                    "serviceId": "SVC-1",
                    "serviceName": "Service One",
                    "resourceGroupKey": None,
                    "resourceGroupName": None,
                    "subscriptionId": None,
                }
            ],
            "t3.service_incidents": [
                {"incidentId": "ICM-1", "createdDate": "2025-12-01"},
            ],
            "t4.service_deployments": [],
        }

        rec = RecordingExecutor(responses)
        client = EvidenceClient(rec)
        resolved = ResolvedEntityRef(label="AzureResource", resource_id="res-x")
        result = expand_evidence_for_resource(resolved, client, as_of=None)

        self.assertIsNone(result.evidence["historical_outages_180d"])
        self.assertIn("historical_outages_180d", result.unknowns)


if __name__ == "__main__":
    unittest.main()
