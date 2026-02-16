import unittest
from datetime import date

from risk_scoring.evidence_client import CypherExecutor, EvidenceClient
from risk_scoring.graph_expansion import expand_evidence_for_resource
from risk_scoring.models import ResolvedEntityRef
from risk_scoring.reporting import build_report_json, render_markdown_report
from risk_scoring.scoring import ChangeContext, score_change


class FakeExecutor(CypherExecutor):
    def __init__(self, by_query_id):
        self.by_query_id = by_query_id

    def run_readonly(self, cypher: str, params: dict):
        # Infer query_id from the distinguishing MATCH patterns.
        if "MATCH (r:AzureResource" in cypher and "OWNS_RESOURCE" in cypher:
            return self.by_query_id.get("t2.resource_context", [])
        if "MATCH (s:Service" in cypher and "Incident" in cypher:
            return self.by_query_id.get("t3.service_incidents", [])
        if "MATCH (d:Deployment" in cypher:
            return self.by_query_id.get("t4.service_deployments", [])
        raise AssertionError("Unexpected cypher")


class TestReporting(unittest.TestCase):
    def test_markdown_is_deterministic(self) -> None:
        resolved = ResolvedEntityRef(label="AzureResource", resource_id="res-x")

        exec = FakeExecutor(
            {
                "t2.resource_context": [
                    {
                        "resourceName": "res-x",
                        "resourceType": "t",
                        "serviceId": "SVC-1",
                        "serviceName": "Service One",
                        "resourceGroupKey": "subs|rg",
                        "resourceGroupName": "rg",
                        "subscriptionId": "subs",
                    }
                ],
                "t3.service_incidents": [
                    {"incidentId": "ICM-1", "createdDate": "2025-12-01"},
                ],
                "t4.service_deployments": [
                    {"rolloutId": "RL-1", "rolloutInfra": "i", "artifactVersion": "v"},
                ],
            }
        )

        client = EvidenceClient(exec)
        expansion = expand_evidence_for_resource(resolved, client, as_of=date(2026, 1, 1))

        change = ChangeContext.create(environment="prod")
        score = score_change(change, expansion.evidence)

        report = build_report_json(
            resolved=resolved, change=change, expansion=expansion, score=score, report_id=None
        )

        md1 = render_markdown_report(report)
        md2 = render_markdown_report(report)
        self.assertEqual(md1, md2)

    def test_json_contains_evidence_query_ids(self) -> None:
        resolved = ResolvedEntityRef(label="AzureResource", resource_id="res-x")
        exec = FakeExecutor(
            {
                "t2.resource_context": [
                    {
                        "resourceName": "res-x",
                        "resourceType": "t",
                        "serviceId": "SVC-1",
                        "serviceName": "Service One",
                        "resourceGroupKey": None,
                        "resourceGroupName": None,
                        "subscriptionId": None,
                    }
                ],
                "t3.service_incidents": [],
                "t4.service_deployments": [],
            }
        )
        client = EvidenceClient(exec)
        expansion = expand_evidence_for_resource(resolved, client, as_of=None)
        change = ChangeContext.create(environment="prod")
        score = score_change(change, expansion.evidence)

        report = build_report_json(resolved=resolved, change=change, expansion=expansion, score=score)
        qids = [q["query_id"] for q in report["evidence_queries"]]
        self.assertEqual(qids, ["t2.resource_context", "t3.service_incidents", "t4.service_deployments"])


if __name__ == "__main__":
    unittest.main()
