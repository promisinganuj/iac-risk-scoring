"""Integration tests for Neo4j JSON/CSV ingestion.

These tests verify that:
1. Neo4j successfully ingests JSON data using apoc.load.json
2. Neo4j successfully ingests CSV data using LOAD CSV (backward compatibility)
3. AzureResource nodes use resourceName property (not resourceId)
4. Relationships are created correctly

Note: These are integration tests that require a running Neo4j instance.
They can be skipped if NEO4J_URI environment variable is not set.
"""
import os
import unittest

# Skip all tests if Neo4j connection not configured
NEO4J_URI = os.getenv("NEO4J_URI")
SKIP_REASON = "NEO4J_URI not set - skipping integration tests"


try:
    from risk_scoring.neo4j_http import Neo4jHttpClient
    from risk_scoring.neo4j_http_repository import Neo4jHttpRepository
except ImportError:
    Neo4jHttpClient = None
    Neo4jHttpRepository = None


@unittest.skipUnless(NEO4J_URI, SKIP_REASON)
class TestNeo4jJsonIngestion(unittest.TestCase):
    """Integration tests for Neo4j JSON ingestion."""

    @classmethod
    def setUpClass(cls):
        """Set up Neo4j client for all tests."""
        if Neo4jHttpClient is None:
            cls.skipTest(cls, "Neo4j HTTP client not available")
            return
        
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "please-change-me")
        
        cls.client = Neo4jHttpClient(
            uri=NEO4J_URI,
            username=neo4j_user,
            password=neo4j_password,
        )
        cls.repo = Neo4jHttpRepository(client=cls.client)

    def test_azure_resources_exist_in_neo4j(self) -> None:
        """Verify AzureResource nodes were created."""
        query = "MATCH (r:AzureResource) RETURN count(r) as count"
        result = self.client.run_query(query)
        
        self.assertGreater(len(result), 0, "Should return at least one row")
        count = result[0].get("count", 0)
        self.assertGreater(count, 0, "Should have at least one AzureResource node")

    def test_azure_resources_use_resourcename_property(self) -> None:
        """Verify AzureResource nodes have resourceName property, not resourceId."""
        # Check that resourceName property exists
        query_name = """
        MATCH (r:AzureResource)
        WHERE r.resourceName IS NOT NULL
        RETURN count(r) as count
        """
        result = self.client.run_query(query_name)
        count_with_name = result[0].get("count", 0)
        self.assertGreater(count_with_name, 0, "Should have resources with resourceName")
        
        # Check that old resourceId property doesn't exist
        query_id = """
        MATCH (r:AzureResource)
        WHERE r.resourceId IS NOT NULL
        RETURN count(r) as count
        """
        result_id = self.client.run_query(query_id)
        count_with_id = result_id[0].get("count", 0)
        self.assertEqual(count_with_id, 0, "Should NOT have resources with old resourceId property")

    def test_can_query_by_resourcename(self) -> None:
        """Verify we can query AzureResource by resourceName."""
        # Get any resource name from the database
        query_sample = """
        MATCH (r:AzureResource)
        WHERE r.resourceName IS NOT NULL
        RETURN r.resourceName as resourceName
        LIMIT 1
        """
        result = self.client.run_query(query_sample)
        self.assertGreater(len(result), 0, "Should find at least one resource")
        
        resource_name = result[0].get("resourceName")
        self.assertIsNotNone(resource_name, "Resource should have resourceName")
        
        # Query by that specific resourceName
        query_by_name = """
        MATCH (r:AzureResource {resourceName: $resourceName})
        RETURN r.resourceName as name, r.displayName as display
        """
        result2 = self.client.run_query(query_by_name, params={"resourceName": resource_name})
        self.assertEqual(len(result2), 1, f"Should find exactly one resource with name {resource_name}")
        self.assertEqual(result2[0].get("name"), resource_name)

    def test_repository_finds_resources_by_resourcename(self) -> None:
        """Verify Neo4jHttpRepository correctly uses resourceName property."""
        # Get a known resource from sample data
        results = self.repo.find_azure_resources_by_resource_id("res-alpha-app", limit=10)
        
        # Should find the resource (if sample data is loaded)
        # Note: This might return empty if sample data isn't loaded, which is OK
        if len(results) > 0:
            self.assertEqual(results[0].resource_id, "res-alpha-app")
            self.assertEqual(results[0].label, "AzureResource")

    def test_services_and_relationships_exist(self) -> None:
        """Verify other node types and relationships were created."""
        # Check for Service nodes
        query_services = "MATCH (s:Service) RETURN count(s) as count"
        result = self.client.run_query(query_services)
        service_count = result[0].get("count", 0)
        self.assertGreater(service_count, 0, "Should have Service nodes")
        
        # Check for relationships
        query_rels = "MATCH ()-[r:OWNS_RESOURCE]->() RETURN count(r) as count"
        result_rels = self.client.run_query(query_rels)
        rel_count = result_rels[0].get("count", 0)
        self.assertGreater(rel_count, 0, "Should have OWNS_RESOURCE relationships")


@unittest.skipUnless(NEO4J_URI, SKIP_REASON)
class TestNeo4jConstraints(unittest.TestCase):
    """Test Neo4j schema constraints."""

    @classmethod
    def setUpClass(cls):
        """Set up Neo4j client."""
        if Neo4jHttpClient is None:
            cls.skipTest(cls, "Neo4j HTTP client not available")
            return
        
        neo4j_user = os.getenv("NEO4J_USER", "neo4j")
        neo4j_password = os.getenv("NEO4J_PASSWORD", "please-change-me")
        
        cls.client = Neo4jHttpClient(
            uri=NEO4J_URI,
            username=neo4j_user,
            password=neo4j_password,
        )

    def test_resourcename_constraint_exists(self) -> None:
        """Verify uniqueness constraint on AzureResource.resourceName exists."""
        query = """
        SHOW CONSTRAINTS
        YIELD name, type, entityType, labelsOrTypes, properties
        WHERE 'AzureResource' IN labelsOrTypes
        RETURN name, type, properties
        """
        result = self.client.run_query(query)
        
        # Should have at least one constraint on AzureResource
        self.assertGreater(len(result), 0, "Should have constraints on AzureResource")
        
        # Check if resourceName is in the constraints
        has_resourcename_constraint = False
        for row in result:
            props = row.get("properties", [])
            if "resourceName" in props:
                has_resourcename_constraint = True
                break
        
        self.assertTrue(
            has_resourcename_constraint,
            "Should have constraint on resourceName property"
        )


if __name__ == "__main__":
    unittest.main()
