import sys
import unittest
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
APPROACH2_DIR = THIS_DIR.parent.parent
sys.path.insert(0, str(APPROACH2_DIR))

from risk_scoring.evidence_allowlist import (  # noqa: E402
    ParameterValidationError,
    UnknownQueryError,
    get_query,
    validate_params,
)


class TestEvidenceAllowlist(unittest.TestCase):
    def test_unknown_query_rejected(self) -> None:
        with self.assertRaises(UnknownQueryError):
            get_query("DROP DATABASE")

    def test_limit_is_bounded(self) -> None:
        q = get_query("t3.service_incidents")
        with self.assertRaises(ParameterValidationError):
            validate_params(q, {"serviceId": "A", "limit": 999999})

    def test_limit_defaults(self) -> None:
        q = get_query("t3.service_incidents")
        params = validate_params(q, {"serviceId": "A"})
        self.assertEqual(params["limit"], q.default_limit)

    def test_string_max_len_enforced(self) -> None:
        q = get_query("t1.resolve_azure_resource")
        too_long = "x" * 1000
        with self.assertRaises(ParameterValidationError):
            validate_params(q, {"resourceId": too_long, "limit": 1})

    def test_queries_are_bounded_and_ordered(self) -> None:
        # Guardrail: every query must include LIMIT and ORDER BY to keep results stable.
        for qid in [
            "t1.resolve_azure_resource",
            "t2.resource_context",
            "t3.service_incidents",
            "t4.service_deployments",
        ]:
            q = get_query(qid)
            cypher_upper = q.cypher.upper()
            self.assertIn("LIMIT $LIMIT", cypher_upper)
            self.assertIn("ORDER BY", cypher_upper)


if __name__ == "__main__":
    unittest.main()
