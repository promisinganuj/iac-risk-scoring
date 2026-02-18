"""Edge-case tests for entity resolution: validation, normalization, and ambiguity.

Covers gaps identified in iac-risk-scoring-8o9:
- Empty/whitespace resource_id -> NotFoundError
- Case-insensitive fallback matching
- Attribute-only fallback path
- Candidate ordering stability across all 5 sort keys
- Chooser edge cases (out-of-bounds, negative index, None chooser)
- AmbiguousMatchError.candidates payload assertions
- 3+ candidates ordering
- None-field sorting in candidates
- Limit parameter behaviour
"""

import unittest
from dataclasses import asdict

from risk_scoring.entity_resolution import resolve_azure_resource
from risk_scoring.errors import AmbiguousMatchError, NotFoundError
from risk_scoring.models import CandidateEntity, ResourceSpec
from risk_scoring.repository import InMemoryRepository


def _candidate(
    rid="res-x",
    display_name=None,
    resource_type=None,
    subscription_id=None,
    resource_group=None,
):
    return CandidateEntity(
        label="AzureResource",
        resource_id=rid,
        display_name=display_name,
        resource_type=resource_type,
        subscription_id=subscription_id,
        resource_group=resource_group,
    )


class TestInputValidation(unittest.TestCase):
    """Resource ID input validation edge cases."""

    def test_empty_resource_id_raises(self):
        repo = InMemoryRepository([_candidate()])
        with self.assertRaises(NotFoundError):
            resolve_azure_resource(repo, ResourceSpec(resource_id=""), non_interactive=True)

    def test_whitespace_only_resource_id_raises(self):
        repo = InMemoryRepository([_candidate()])
        with self.assertRaises(NotFoundError):
            resolve_azure_resource(repo, ResourceSpec(resource_id="   "), non_interactive=True)

    def test_none_resource_id_raises(self):
        repo = InMemoryRepository([_candidate()])
        spec = ResourceSpec(resource_id=None)  # type: ignore[arg-type]
        with self.assertRaises(NotFoundError):
            resolve_azure_resource(repo, spec, non_interactive=True)


class TestCaseInsensitiveFallback(unittest.TestCase):
    """Step 2: case-insensitive matching when exact match fails."""

    def test_mixed_case_resource_id_resolves(self):
        repo = InMemoryRepository([_candidate(rid="res-alpha-app")])
        ref = resolve_azure_resource(
            repo, ResourceSpec(resource_id="Res-Alpha-App"), non_interactive=True
        )
        self.assertEqual(ref.resource_id, "res-alpha-app")

    def test_upper_case_resource_id_resolves(self):
        repo = InMemoryRepository([_candidate(rid="res-alpha-app")])
        ref = resolve_azure_resource(
            repo, ResourceSpec(resource_id="RES-ALPHA-APP"), non_interactive=True
        )
        self.assertEqual(ref.resource_id, "res-alpha-app")

    def test_case_insensitive_with_multiple_matches_raises_ambiguous(self):
        repo = InMemoryRepository([
            _candidate(rid="res-x", subscription_id="sub-a"),
            _candidate(rid="res-x", subscription_id="sub-b"),
        ])
        with self.assertRaises(AmbiguousMatchError):
            resolve_azure_resource(
                repo, ResourceSpec(resource_id="RES-X"), non_interactive=True
            )


class TestAttributeFallback(unittest.TestCase):
    """Step 3: attribute-based query when resource_id lookup fails."""

    def test_resolves_by_type_and_subscription(self):
        repo = InMemoryRepository([
            _candidate(rid="res-other", resource_type="Microsoft.Web/sites", subscription_id="sub-001"),
        ])
        ref = resolve_azure_resource(
            repo,
            ResourceSpec(resource_id="does-not-match", resource_type="Microsoft.Web/sites", subscription_id="sub-001"),
            non_interactive=True,
        )
        self.assertEqual(ref.resource_id, "res-other")

    def test_attribute_fallback_not_triggered_without_extra_attrs(self):
        repo = InMemoryRepository([_candidate(rid="res-other")])
        with self.assertRaises(NotFoundError):
            resolve_azure_resource(repo, ResourceSpec(resource_id="does-not-match"), non_interactive=True)


class TestCandidateOrdering(unittest.TestCase):
    """Deterministic ordering across all 5 sort keys."""

    def test_ordering_by_all_five_keys(self):
        c1 = _candidate(rid="res-x", subscription_id="sub-b", resource_group="rg-a")
        c2 = _candidate(rid="res-x", subscription_id="sub-a", resource_group="rg-b")
        c3 = _candidate(rid="res-x", subscription_id="sub-a", resource_group="rg-a")
        repo = InMemoryRepository([c1, c2, c3])

        with self.assertRaises(AmbiguousMatchError) as ctx:
            resolve_azure_resource(repo, ResourceSpec(resource_id="res-x"), non_interactive=True)

        cands = ctx.exception.candidates
        self.assertEqual(len(cands), 3)
        self.assertEqual(cands[0]["subscription_id"], "sub-a")
        self.assertEqual(cands[0]["resource_group"], "rg-a")
        self.assertEqual(cands[1]["subscription_id"], "sub-a")
        self.assertEqual(cands[1]["resource_group"], "rg-b")
        self.assertEqual(cands[2]["subscription_id"], "sub-b")
        self.assertEqual(cands[2]["resource_group"], "rg-a")

    def test_none_fields_sort_before_non_none(self):
        c1 = _candidate(rid="res-x", subscription_id="sub-a")
        c2 = _candidate(rid="res-x", subscription_id=None)
        repo = InMemoryRepository([c1, c2])

        with self.assertRaises(AmbiguousMatchError) as ctx:
            resolve_azure_resource(repo, ResourceSpec(resource_id="res-x"), non_interactive=True)

        cands = ctx.exception.candidates
        self.assertEqual(len(cands), 2)
        self.assertIsNone(cands[0]["subscription_id"])
        self.assertEqual(cands[1]["subscription_id"], "sub-a")

    def test_three_candidates_stable_ordering(self):
        candidates = [
            _candidate(rid="res-x", display_name="Charlie"),
            _candidate(rid="res-x", display_name="Alpha"),
            _candidate(rid="res-x", display_name="Bravo"),
        ]
        repo = InMemoryRepository(candidates)

        with self.assertRaises(AmbiguousMatchError) as ctx:
            resolve_azure_resource(repo, ResourceSpec(resource_id="res-x"), non_interactive=True)

        names = [c["display_name"] for c in ctx.exception.candidates]
        self.assertEqual(names, ["Alpha", "Bravo", "Charlie"])


class TestAmbiguousMatchPayload(unittest.TestCase):
    """Ensure AmbiguousMatchError carries serializable candidates."""

    def test_candidates_are_serializable_dicts(self):
        c = _candidate(rid="res-x", subscription_id="sub-a", display_name="Test")
        repo = InMemoryRepository([c, c])

        with self.assertRaises(AmbiguousMatchError) as ctx:
            resolve_azure_resource(repo, ResourceSpec(resource_id="res-x"), non_interactive=True)

        cands = ctx.exception.candidates
        self.assertIsInstance(cands, list)
        self.assertTrue(len(cands) >= 2)
        for cand in cands:
            self.assertIsInstance(cand, dict)
            self.assertIn("resource_id", cand)
            self.assertIn("label", cand)

    def test_candidates_match_asdict_output(self):
        c = _candidate(rid="res-x", subscription_id="sub-z")
        repo = InMemoryRepository([c, c])

        with self.assertRaises(AmbiguousMatchError) as ctx:
            resolve_azure_resource(repo, ResourceSpec(resource_id="res-x"), non_interactive=True)

        cands = ctx.exception.candidates
        expected_keys = set(asdict(c).keys())
        for cand in cands:
            self.assertEqual(set(cand.keys()), expected_keys)


class TestChooserEdgeCases(unittest.TestCase):
    """Interactive resolution chooser callback edge cases."""

    def _repo_with_ambiguity(self):
        return InMemoryRepository([
            _candidate(rid="res-x", subscription_id="sub-a"),
            _candidate(rid="res-x", subscription_id="sub-b"),
        ])

    def test_chooser_negative_index_raises(self):
        repo = self._repo_with_ambiguity()
        with self.assertRaises(AmbiguousMatchError) as ctx:
            resolve_azure_resource(
                repo, ResourceSpec(resource_id="res-x"),
                non_interactive=False, chooser=lambda _: -1,
            )
        self.assertIn("Invalid selection index", str(ctx.exception))

    def test_chooser_out_of_bounds_index_raises(self):
        repo = self._repo_with_ambiguity()
        with self.assertRaises(AmbiguousMatchError) as ctx:
            resolve_azure_resource(
                repo, ResourceSpec(resource_id="res-x"),
                non_interactive=False, chooser=lambda _: 100,
            )
        self.assertIn("Invalid selection index", str(ctx.exception))

    def test_no_chooser_interactive_raises(self):
        repo = self._repo_with_ambiguity()
        with self.assertRaises(AmbiguousMatchError) as ctx:
            resolve_azure_resource(
                repo, ResourceSpec(resource_id="res-x"),
                non_interactive=False, chooser=None,
            )
        self.assertIn("chooser callback", str(ctx.exception))

    def test_chooser_picks_last_candidate(self):
        repo = self._repo_with_ambiguity()
        ref = resolve_azure_resource(
            repo, ResourceSpec(resource_id="res-x"),
            non_interactive=False, chooser=lambda cands: len(cands) - 1,
        )
        self.assertEqual(ref.subscription_id, "sub-b")


class TestLimitParameter(unittest.TestCase):
    """Verify the limit parameter bounds repository queries."""

    def test_limit_restricts_returned_candidates(self):
        repo = InMemoryRepository([
            _candidate(rid="res-x", subscription_id="sub-a"),
            _candidate(rid="res-x", subscription_id="sub-b"),
            _candidate(rid="res-x", subscription_id="sub-c"),
        ])
        ref = resolve_azure_resource(
            repo, ResourceSpec(resource_id="res-x"), non_interactive=True, limit=1,
        )
        self.assertEqual(ref.resource_id, "res-x")

    def test_default_limit_allows_multiple(self):
        candidates = [_candidate(rid="res-x", subscription_id=f"sub-{i}") for i in range(5)]
        repo = InMemoryRepository(candidates)
        with self.assertRaises(AmbiguousMatchError) as ctx:
            resolve_azure_resource(repo, ResourceSpec(resource_id="res-x"), non_interactive=True)
        self.assertEqual(len(ctx.exception.candidates), 5)


if __name__ == "__main__":
    unittest.main()
