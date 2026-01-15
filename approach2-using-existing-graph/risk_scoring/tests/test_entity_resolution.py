import os
import sys
import unittest
from pathlib import Path

# Ensure approach2-using-existing-graph is on sys.path so we can import risk_scoring.
THIS_DIR = Path(__file__).resolve().parent
APPROACH2_DIR = THIS_DIR.parent.parent
sys.path.insert(0, str(APPROACH2_DIR))

from risk_scoring.csv_repository import CsvEntityRepository  # noqa: E402
from risk_scoring.entity_resolution import resolve_azure_resource  # noqa: E402
from risk_scoring.errors import AmbiguousMatchError, NotFoundError  # noqa: E402
from risk_scoring.models import CandidateEntity, ResourceSpec  # noqa: E402
from risk_scoring.repository import InMemoryRepository  # noqa: E402


class TestEntityResolutionCsv(unittest.TestCase):
    def test_resolves_by_resource_id_from_sample_data(self) -> None:
        repo = CsvEntityRepository(
            sample_data_dir=Path(__file__).resolve().parents[2] / "sample-data"
        )
        ref = resolve_azure_resource(
            repo,
            ResourceSpec(resource_id="res-alpha-app"),
            non_interactive=True,
        )
        self.assertEqual(ref.resource_id, "res-alpha-app")
        self.assertEqual(ref.label, "AzureResource")


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
