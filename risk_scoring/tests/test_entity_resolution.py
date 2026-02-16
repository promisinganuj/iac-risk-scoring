import json
import os
import tempfile
import unittest
from pathlib import Path

from risk_scoring.csv_repository import CsvEntityRepository
from risk_scoring.entity_resolution import resolve_azure_resource
from risk_scoring.errors import AmbiguousMatchError, NotFoundError
from risk_scoring.models import CandidateEntity, ResourceSpec
from risk_scoring.repository import InMemoryRepository

# Sample data lives under approach2-using-existing-graph/
_SAMPLE_DATA_DIR = Path(__file__).resolve().parents[2] / "approach2-using-existing-graph" / "sample-data"


class TestEntityResolutionCsv(unittest.TestCase):
    def test_resolves_by_resource_id_from_sample_data(self) -> None:
        repo = CsvEntityRepository(
            sample_data_dir=_SAMPLE_DATA_DIR
        )
        ref = resolve_azure_resource(
            repo,
            ResourceSpec(resource_id="res-alpha-app"),
            non_interactive=True,
        )
        self.assertEqual(ref.resource_id, "res-alpha-app")
        self.assertEqual(ref.label, "AzureResource")

    def test_loads_from_json_by_default(self) -> None:
        """Verify CsvEntityRepository loads from JSON files by default."""
        repo = CsvEntityRepository(
            sample_data_dir=_SAMPLE_DATA_DIR
        )
        # JSON file should exist and be loaded
        json_path = _SAMPLE_DATA_DIR / "azure_resources.json"
        self.assertTrue(json_path.exists(), "JSON file should exist")
        
        # Verify data was loaded (should have 12 resources from JSON)
        results = repo.find_azure_resources_by_resource_id("res-alpha-app", limit=10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].resource_id, "res-alpha-app")

    def test_falls_back_to_csv_if_json_not_found(self) -> None:
        """Verify CsvEntityRepository falls back to CSV when JSON doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            
            # Create only CSV file, no JSON
            csv_file = tmp_path / "azure_resources.csv"
            csv_file.write_text(
                "resourceName,displayName,resourceType,subscriptionId,resourceGroup\n"
                "res-test-1,Test Resource 1,Microsoft.Web/sites,subs-test-001,rg-test\n"
                "res-test-2,Test Resource 2,Microsoft.Compute/virtualMachines,subs-test-002,rg-test\n"
            )
            
            repo = CsvEntityRepository(sample_data_dir=tmp_path)
            results = repo.find_azure_resources_by_resource_id("res-test-1", limit=10)
            
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].resource_id, "res-test-1")
            self.assertEqual(results[0].display_name, "Test Resource 1")

    def test_raises_if_neither_json_nor_csv_exists(self) -> None:
        """Verify CsvEntityRepository raises error if neither format exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            
            with self.assertRaises(FileNotFoundError) as ctx:
                CsvEntityRepository(sample_data_dir=tmp_path)
            
            self.assertIn("tried", str(ctx.exception))

    def test_json_uses_resourcename_property(self) -> None:
        """Verify JSON loading correctly reads resourceName property."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            
            # Create JSON file with resourceName property
            json_file = tmp_path / "azure_resources.json"
            json_data = [
                {
                    "resourceName": "res-json-test",
                    "displayName": "JSON Test Resource",
                    "resourceType": "Microsoft.Storage/storageAccounts",
                    "subscriptionId": "subs-json-001",
                    "resourceGroup": "rg-json"
                }
            ]
            json_file.write_text(json.dumps(json_data, indent=2))
            
            repo = CsvEntityRepository(sample_data_dir=tmp_path)
            results = repo.find_azure_resources_by_resource_id("res-json-test", limit=10)
            
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].resource_id, "res-json-test")
            self.assertEqual(results[0].display_name, "JSON Test Resource")
            self.assertEqual(results[0].resource_type, "Microsoft.Storage/storageAccounts")


class TestEntityResolutionBehavior(unittest.TestCase):
    def test_not_found(self) -> None:
        repo = InMemoryRepository([])
        with self.assertRaises(NotFoundError):
            resolve_azure_resource(
                repo,
                ResourceSpec(resource_id="does-not-exist"),
                non_interactive=True,
            )

    def test_ambiguous_non_interactive_raises(self) -> None:
        repo = InMemoryRepository(
            [
                CandidateEntity(label="AzureResource", resource_id="res-x"),
                CandidateEntity(label="AzureResource", resource_id="res-x"),
            ]
        )
        with self.assertRaises(AmbiguousMatchError):
            resolve_azure_resource(
                repo,
                ResourceSpec(resource_id="res-x"),
                non_interactive=True,
            )

    def test_ambiguous_interactive_chooser_picks_deterministically(self) -> None:
        repo = InMemoryRepository(
            [
                CandidateEntity(
                    label="AzureResource",
                    resource_id="res-x",
                    subscription_id="subs-b",
                ),
                CandidateEntity(
                    label="AzureResource",
                    resource_id="res-x",
                    subscription_id="subs-a",
                ),
            ]
        )

        def pick_first(cands):
            # chooser sees sorted candidates; pick the first
            return 0

        ref = resolve_azure_resource(
            repo,
            ResourceSpec(resource_id="res-x"),
            non_interactive=False,
            chooser=pick_first,
        )
        # because sorting uses subscription_id, subs-a comes first
        self.assertEqual(ref.subscription_id, "subs-a")


if __name__ == "__main__":
    unittest.main()
