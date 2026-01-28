import sys
import unittest
from pathlib import Path

# Ensure approach2-using-existing-graph is on sys.path so we can import risk_scoring.
THIS_DIR = Path(__file__).resolve().parent
APPROACH2_DIR = THIS_DIR.parent.parent
sys.path.insert(0, str(APPROACH2_DIR))

from risk_scoring.evidence_allowlist import get_query  # noqa: E402
from risk_scoring.evidence_client import CypherExecutor, EvidenceClient  # noqa: E402
from risk_scoring.graph_expansion import (  # noqa: E402
    get_resource_blast_radius,
    get_template_blast_radius,
    get_service_blast_radius,
    BlastRadiusResult,
)


class RecordingExecutor(CypherExecutor):
    """Test executor that records calls and returns canned responses."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

        # Invert allowlisted queries by their Cypher string for assertions.
        self.cypher_to_id = {
            get_query("blast_radius.resource_impact").cypher: "blast_radius.resource_impact",
            get_query("blast_radius.template_impact").cypher: "blast_radius.template_impact",
            get_query("blast_radius.service_impact").cypher: "blast_radius.service_impact",
        }

    def run_readonly(self, cypher: str, params: dict):
        query_id = self.cypher_to_id.get(cypher)
        if query_id is None:
            raise AssertionError(f"Unexpected cypher executed: {cypher[:100]}")
        self.calls.append({"query_id": query_id, "cypher": cypher, "params": dict(params)})
        return self.responses.get(query_id, [])


class TestResourceBlastRadius(unittest.TestCase):
    def test_resource_blast_radius_with_full_context(self) -> None:
        """Test resource blast radius calculation with complete data."""
        responses = {
            "blast_radius.resource_impact": [
                {
                    "resourceName": "res-alpha-app",
                    "resourceType": "Microsoft.Web/sites",
                    "resourceGroupKey": "rg-alpha-core",
                    "resourceGroupName": "Alpha Core Infrastructure",
                    "subscriptionId": "subs-prod-001",
                    "serviceId": "A56C6700-6666-4444-AAAA-000F3B9CC999",
                    "serviceName": "Payments",
                    "peerResourceCount": 2,
                    "peerResources": [
                        {"name": "res-alpha-lb", "type": "Microsoft.Network/loadBalancers"},
                        {"name": "res-alpha-db", "type": "Microsoft.Sql/servers/databases"},
                    ],
                    "incidentCount": 3,
                    "recentIncidents": [
                        {"id": "ICM-2025-1001", "severity": "2", "date": "2025-01-15"},
                        {"id": "ICM-2025-1002", "severity": "3", "date": "2025-01-20"},
                        {"id": "ICM-2024-0789", "severity": "2", "date": "2024-12-10"},
                    ],
                }
            ]
        }

        rec = RecordingExecutor(responses)
        client = EvidenceClient(rec)

        result = get_resource_blast_radius("res-alpha-app", client, limit=1)

        # Validate result structure
        self.assertIsInstance(result, BlastRadiusResult)
        self.assertEqual(result.entity_id, "res-alpha-app")
        self.assertEqual(result.entity_type, "resource")

        # Validate blast radius metrics
        self.assertEqual(result.affected_services, 1)
        self.assertEqual(result.affected_resources, 2)
        self.assertEqual(result.affected_resource_groups, 1)
        self.assertEqual(result.affected_subscriptions, 1)
        self.assertEqual(result.incident_count, 3)
        self.assertEqual(result.deployment_count, 0)

        # Validate details
        self.assertEqual(result.details["resourceType"], "Microsoft.Web/sites")
        self.assertEqual(result.details["resourceGroup"]["key"], "rg-alpha-core")
        self.assertEqual(result.details["service"]["id"], "A56C6700-6666-4444-AAAA-000F3B9CC999")
        self.assertEqual(len(result.details["peerResources"]), 2)
        self.assertEqual(len(result.details["recentIncidents"]), 3)

        # Validate query execution
        self.assertEqual(len(rec.calls), 1)
        self.assertEqual(rec.calls[0]["query_id"], "blast_radius.resource_impact")
        self.assertEqual(rec.calls[0]["params"]["resourceName"], "res-alpha-app")
        self.assertEqual(rec.calls[0]["params"]["limit"], 1)

    def test_resource_blast_radius_missing_resource(self) -> None:
        """Test resource blast radius when resource doesn't exist."""
        responses = {"blast_radius.resource_impact": []}

        rec = RecordingExecutor(responses)
        client = EvidenceClient(rec)

        result = get_resource_blast_radius("res-nonexistent", client)

        # Should return zero blast radius
        self.assertEqual(result.entity_id, "res-nonexistent")
        self.assertEqual(result.entity_type, "resource")
        self.assertEqual(result.affected_services, 0)
        self.assertEqual(result.affected_resources, 0)
        self.assertEqual(result.affected_resource_groups, 0)
        self.assertEqual(result.affected_subscriptions, 0)
        self.assertEqual(result.incident_count, 0)
        self.assertEqual(result.details, {})

    def test_resource_blast_radius_no_service_owner(self) -> None:
        """Test resource blast radius when resource has no service owner."""
        responses = {
            "blast_radius.resource_impact": [
                {
                    "resourceName": "res-orphan",
                    "resourceType": "Microsoft.Storage/storageAccounts",
                    "resourceGroupKey": "rg-orphan",
                    "resourceGroupName": "Orphan RG",
                    "subscriptionId": "subs-dev-001",
                    "serviceId": None,
                    "serviceName": None,
                    "peerResourceCount": 0,
                    "peerResources": [],
                    "incidentCount": 0,
                    "recentIncidents": [],
                }
            ]
        }

        rec = RecordingExecutor(responses)
        client = EvidenceClient(rec)

        result = get_resource_blast_radius("res-orphan", client)

        # Should have zero services impacted
        self.assertEqual(result.affected_services, 0)
        self.assertEqual(result.affected_resource_groups, 1)
        self.assertIsNone(result.details["service"])


class TestTemplateBlastRadius(unittest.TestCase):
    def test_template_blast_radius_with_full_context(self) -> None:
        """Test template blast radius calculation with complete data."""
        responses = {
            "blast_radius.template_impact": [
                {
                    "templateName": "template-alpha-app",
                    "templateVersion": "2.1.0",
                    "deploymentCount": 3,
                    "deployments": [
                        {"rolloutId": "deploy-alpha-001", "artifactVersion": "v1.2.0"},
                        {"rolloutId": "deploy-alpha-002", "artifactVersion": "v1.2.1"},
                        {"rolloutId": "deploy-alpha-003", "artifactVersion": "v1.3.0"},
                    ],
                    "resourceGroupCount": 2,
                    "resourceGroups": [
                        {"key": "rg-alpha-core", "name": "Alpha Core Infrastructure"},
                        {"key": "rg-alpha-dr", "name": "Alpha DR Environment"},
                    ],
                    "resourceCount": 5,
                    "resources": [
                        {"name": "res-alpha-app", "type": "Microsoft.Web/sites"},
                        {"name": "res-alpha-lb", "type": "Microsoft.Network/loadBalancers"},
                        {"name": "res-alpha-db", "type": "Microsoft.Sql/servers/databases"},
                        {"name": "res-alpha-dr-app", "type": "Microsoft.Web/sites"},
                        {"name": "res-alpha-dr-db", "type": "Microsoft.Sql/servers/databases"},
                    ],
                }
            ]
        }

        rec = RecordingExecutor(responses)
        client = EvidenceClient(rec)

        result = get_template_blast_radius("template-alpha-app", client, limit=1)

        # Validate result structure
        self.assertIsInstance(result, BlastRadiusResult)
        self.assertEqual(result.entity_id, "template-alpha-app")
        self.assertEqual(result.entity_type, "template")

        # Validate blast radius metrics
        self.assertEqual(result.affected_services, 0)  # Indirect via resources
        self.assertEqual(result.affected_resources, 5)
        self.assertEqual(result.affected_resource_groups, 2)
        self.assertEqual(result.affected_subscriptions, 0)  # Not tracked at template level
        self.assertEqual(result.incident_count, 0)  # Would need service traversal
        self.assertEqual(result.deployment_count, 3)

        # Validate details
        self.assertEqual(result.details["templateVersion"], "2.1.0")
        self.assertEqual(len(result.details["deployments"]), 3)
        self.assertEqual(len(result.details["resourceGroups"]), 2)
        self.assertEqual(len(result.details["resources"]), 5)

        # Validate query execution
        self.assertEqual(len(rec.calls), 1)
        self.assertEqual(rec.calls[0]["query_id"], "blast_radius.template_impact")

    def test_template_blast_radius_missing_template(self) -> None:
        """Test template blast radius when template doesn't exist."""
        responses = {"blast_radius.template_impact": []}

        rec = RecordingExecutor(responses)
        client = EvidenceClient(rec)

        result = get_template_blast_radius("template-nonexistent", client)

        # Should return zero blast radius
        self.assertEqual(result.entity_id, "template-nonexistent")
        self.assertEqual(result.entity_type, "template")
        self.assertEqual(result.affected_resources, 0)
        self.assertEqual(result.deployment_count, 0)
        self.assertEqual(result.details, {})

    def test_template_blast_radius_no_deployments(self) -> None:
        """Test template blast radius when template has no deployments yet."""
        responses = {
            "blast_radius.template_impact": [
                {
                    "templateName": "template-new",
                    "templateVersion": "1.0.0",
                    "deploymentCount": 0,
                    "deployments": [],
                    "resourceGroupCount": 0,
                    "resourceGroups": [],
                    "resourceCount": 0,
                    "resources": [],
                }
            ]
        }

        rec = RecordingExecutor(responses)
        client = EvidenceClient(rec)

        result = get_template_blast_radius("template-new", client)

        # Should have zero blast radius but template exists
        self.assertEqual(result.deployment_count, 0)
        self.assertEqual(result.affected_resources, 0)
        self.assertEqual(result.details["templateVersion"], "1.0.0")


class TestServiceBlastRadius(unittest.TestCase):
    def test_service_blast_radius_with_full_context(self) -> None:
        """Test service blast radius calculation with complete data."""
        responses = {
            "blast_radius.service_impact": [
                {
                    "serviceId": "A56C6700-6666-4444-AAAA-000F3B9CC999",
                    "serviceName": "Payments",
                    "resourceCount": 3,
                    "resources": [
                        {"name": "res-alpha-app", "type": "Microsoft.Web/sites"},
                        {"name": "res-alpha-lb", "type": "Microsoft.Network/loadBalancers"},
                        {"name": "res-alpha-db", "type": "Microsoft.Sql/servers/databases"},
                    ],
                    "resourceGroupCount": 2,
                    "resourceGroups": [
                        {"key": "rg-alpha-core", "name": "Alpha Core Infrastructure"},
                        {"key": "rg-alpha-dr", "name": "Alpha DR Environment"},
                    ],
                    "subscriptionCount": 1,
                    "subscriptions": ["subs-prod-001"],
                    "incidentCount": 3,
                    "incidents": [
                        {
                            "id": "ICM-2025-1001",
                            "severity": "2",
                            "date": "2025-01-15",
                            "changeRelated": "Yes",
                        },
                        {
                            "id": "ICM-2025-1002",
                            "severity": "3",
                            "date": "2025-01-20",
                            "changeRelated": "No",
                        },
                        {
                            "id": "ICM-2024-0789",
                            "severity": "2",
                            "date": "2024-12-10",
                            "changeRelated": "Yes",
                        },
                    ],
                    "deploymentCount": 12,
                }
            ]
        }

        rec = RecordingExecutor(responses)
        client = EvidenceClient(rec)

        result = get_service_blast_radius("A56C6700-6666-4444-AAAA-000F3B9CC999", client, limit=1)

        # Validate result structure
        self.assertIsInstance(result, BlastRadiusResult)
        self.assertEqual(result.entity_id, "A56C6700-6666-4444-AAAA-000F3B9CC999")
        self.assertEqual(result.entity_type, "service")

        # Validate blast radius metrics
        self.assertEqual(result.affected_services, 1)
        self.assertEqual(result.affected_resources, 3)
        self.assertEqual(result.affected_resource_groups, 2)
        self.assertEqual(result.affected_subscriptions, 1)
        self.assertEqual(result.incident_count, 3)
        self.assertEqual(result.deployment_count, 12)

        # Validate details
        self.assertEqual(result.details["serviceName"], "Payments")
        self.assertEqual(len(result.details["resources"]), 3)
        self.assertEqual(len(result.details["resourceGroups"]), 2)
        self.assertEqual(len(result.details["subscriptions"]), 1)
        self.assertEqual(len(result.details["incidents"]), 3)

        # Validate incident details
        change_related = [inc for inc in result.details["incidents"] if inc["changeRelated"] == "Yes"]
        self.assertEqual(len(change_related), 2)

        # Validate query execution
        self.assertEqual(len(rec.calls), 1)
        self.assertEqual(rec.calls[0]["query_id"], "blast_radius.service_impact")

    def test_service_blast_radius_missing_service(self) -> None:
        """Test service blast radius when service doesn't exist."""
        responses = {"blast_radius.service_impact": []}

        rec = RecordingExecutor(responses)
        client = EvidenceClient(rec)

        result = get_service_blast_radius("SVC-NONEXISTENT", client)

        # Should return zero blast radius
        self.assertEqual(result.entity_id, "SVC-NONEXISTENT")
        self.assertEqual(result.entity_type, "service")
        self.assertEqual(result.affected_services, 0)
        self.assertEqual(result.affected_resources, 0)
        self.assertEqual(result.incident_count, 0)
        self.assertEqual(result.details, {})

    def test_service_blast_radius_no_resources(self) -> None:
        """Test service blast radius when service has no resources."""
        responses = {
            "blast_radius.service_impact": [
                {
                    "serviceId": "SVC-EMPTY",
                    "serviceName": "Empty Service",
                    "resourceCount": 0,
                    "resources": [],
                    "resourceGroupCount": 0,
                    "resourceGroups": [],
                    "subscriptionCount": 0,
                    "subscriptions": [],
                    "incidentCount": 0,
                    "incidents": [],
                    "deploymentCount": 0,
                }
            ]
        }

        rec = RecordingExecutor(responses)
        client = EvidenceClient(rec)

        result = get_service_blast_radius("SVC-EMPTY", client)

        # Should have service counted but no resources
        self.assertEqual(result.affected_services, 1)
        self.assertEqual(result.affected_resources, 0)
        self.assertEqual(result.details["serviceName"], "Empty Service")

    def test_service_blast_radius_multi_subscription(self) -> None:
        """Test service blast radius for service spanning multiple subscriptions."""
        responses = {
            "blast_radius.service_impact": [
                {
                    "serviceId": "SVC-MULTI",
                    "serviceName": "Multi-Sub Service",
                    "resourceCount": 5,
                    "resources": [],
                    "resourceGroupCount": 3,
                    "resourceGroups": [],
                    "subscriptionCount": 2,
                    "subscriptions": ["subs-prod-001", "subs-prod-002"],
                    "incidentCount": 0,
                    "incidents": [],
                    "deploymentCount": 8,
                }
            ]
        }

        rec = RecordingExecutor(responses)
        client = EvidenceClient(rec)

        result = get_service_blast_radius("SVC-MULTI", client)

        # Should reflect multi-subscription complexity
        self.assertEqual(result.affected_subscriptions, 2)
        self.assertEqual(len(result.details["subscriptions"]), 2)
        self.assertEqual(result.affected_resource_groups, 3)


class TestBlastRadiusIntegration(unittest.TestCase):
    """Integration tests for blast radius queries working together."""

    def test_blast_radius_query_ids_are_allowlisted(self) -> None:
        """Ensure all blast radius query IDs are in the allowlist."""
        from risk_scoring.evidence_allowlist import get_query

        # All these should succeed without raising UnknownQueryError
        resource_query = get_query("blast_radius.resource_impact")
        template_query = get_query("blast_radius.template_impact")
        service_query = get_query("blast_radius.service_impact")

        # Validate query structure
        self.assertEqual(resource_query.query_id, "blast_radius.resource_impact")
        self.assertEqual(template_query.query_id, "blast_radius.template_impact")
        self.assertEqual(service_query.query_id, "blast_radius.service_impact")

        # Validate limits
        self.assertLessEqual(resource_query.default_limit, resource_query.max_limit)
        self.assertLessEqual(template_query.default_limit, template_query.max_limit)
        self.assertLessEqual(service_query.default_limit, service_query.max_limit)

    def test_blast_radius_queries_have_correct_parameters(self) -> None:
        """Validate query parameter specifications."""
        from risk_scoring.evidence_allowlist import get_query

        resource_query = get_query("blast_radius.resource_impact")
        template_query = get_query("blast_radius.template_impact")
        service_query = get_query("blast_radius.service_impact")

        # Resource query should have resourceName parameter
        param_names = [p.name for p in resource_query.params]
        self.assertIn("resourceName", param_names)

        # Template query should have templateName parameter
        param_names = [p.name for p in template_query.params]
        self.assertIn("templateName", param_names)

        # Service query should have serviceId parameter
        param_names = [p.name for p in service_query.params]
        self.assertIn("serviceId", param_names)

    def test_blast_radius_results_are_deterministic(self) -> None:
        """Ensure blast radius results are stable across multiple calls."""
        responses = {
            "blast_radius.resource_impact": [
                {
                    "resourceName": "res-test",
                    "resourceType": "Microsoft.Web/sites",
                    "resourceGroupKey": "rg-test",
                    "resourceGroupName": "Test RG",
                    "subscriptionId": "subs-test",
                    "serviceId": "SVC-TEST",
                    "serviceName": "Test Service",
                    "peerResourceCount": 2,
                    "peerResources": [
                        {"name": "res-peer-1", "type": "Type1"},
                        {"name": "res-peer-2", "type": "Type2"},
                    ],
                    "incidentCount": 1,
                    "recentIncidents": [{"id": "ICM-1", "severity": "2", "date": "2025-01-01"}],
                }
            ]
        }

        rec1 = RecordingExecutor(responses)
        client1 = EvidenceClient(rec1)
        result1 = get_resource_blast_radius("res-test", client1)

        rec2 = RecordingExecutor(responses)
        client2 = EvidenceClient(rec2)
        result2 = get_resource_blast_radius("res-test", client2)

        # Results should be identical
        self.assertEqual(result1.entity_id, result2.entity_id)
        self.assertEqual(result1.affected_services, result2.affected_services)
        self.assertEqual(result1.affected_resources, result2.affected_resources)
        self.assertEqual(result1.affected_resource_groups, result2.affected_resource_groups)
        self.assertEqual(result1.incident_count, result2.incident_count)


if __name__ == "__main__":
    unittest.main()
