import unittest

from risk_scoring.evidence_client import CypherExecutor, EvidenceClient
from risk_scoring.evidence_allowlist import ParameterValidationError


class FakeExecutor(CypherExecutor):
    def __init__(self):
        self.calls = []

    def run_readonly(self, cypher: str, params):
        self.calls.append((cypher, dict(params)))
        # Return shape: list of dict rows
        return [{"ok": True, "limit": params["limit"]}]


class TestEvidenceClient(unittest.TestCase):
    def test_runs_allowlisted_query(self) -> None:
        ex = FakeExecutor()
        client = EvidenceClient(ex)
        rows = client.run("t3.service_incidents", {"serviceId": "A"})
        self.assertEqual(rows[0]["ok"], True)
        self.assertEqual(rows[0]["limit"], 20)
        self.assertEqual(len(ex.calls), 1)

    def test_rejects_bad_params(self) -> None:
        ex = FakeExecutor()
        client = EvidenceClient(ex)
        with self.assertRaises(ParameterValidationError):
            client.run("t3.service_incidents", {"serviceId": "", "limit": 1})
        self.assertEqual(len(ex.calls), 0)


if __name__ == "__main__":
    unittest.main()
