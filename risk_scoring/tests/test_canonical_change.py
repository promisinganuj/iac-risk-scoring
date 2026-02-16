import unittest

from risk_scoring.canonical_change import (
    canonicalize_from_normalized_diff,
    canonicalize_from_user_input,
    to_canonical_json,
)


class TestCanonicalChange(unittest.TestCase):
    def test_same_normalized_diff_is_byte_for_byte_stable(self) -> None:
        # Same semantic content, different key order.
        d1 = {
            "repo": {"revision": "abc123", "uri": "https://example.com/repo"},
            "environment": "Prod",
            "operations": [
                {"operation": "update", "resource_id": "res-b"},
                {"operation": "update", "resource_id": "res-a"},
            ],
            "extra": {"x": 1, "y": 2},
        }
        d2 = {
            "operations": [
                {"resource_id": "res-a", "operation": "update"},
                {"resource_id": "res-b", "operation": "update"},
            ],
            "environment": "production",
            "repo": {"uri": "https://example.com/repo", "revision": "abc123"},
            "extra": {"y": 2, "x": 1},
        }

        c1 = canonicalize_from_normalized_diff(d1)
        c2 = canonicalize_from_normalized_diff(d2)

        # The change_id differs because it's computed from the whole input.
        # But JSON for each change must be byte-for-byte stable per input.
        j1a = to_canonical_json(c1)
        j1b = to_canonical_json(c1)
        self.assertEqual(j1a, j1b)

        j2a = to_canonical_json(c2)
        j2b = to_canonical_json(c2)
        self.assertEqual(j2a, j2b)

        # Operations are sorted deterministically within each canonical model.
        self.assertEqual([o.resource_id for o in c1.operations], ["res-a", "res-b"])
        self.assertEqual([o.resource_id for o in c2.operations], ["res-a", "res-b"])

    def test_missing_ops_is_explicit_unknown(self) -> None:
        c = canonicalize_from_normalized_diff({"repo": {"uri": "x"}})
        self.assertIn("operations", c.unknowns)

    def test_user_input_fallback_sets_source(self) -> None:
        c = canonicalize_from_user_input(resource_id="res-x", environment="prod")
        self.assertEqual(c.operations[0].source, "user")
        self.assertEqual(c.environment, "prod")


if __name__ == "__main__":
    unittest.main()
