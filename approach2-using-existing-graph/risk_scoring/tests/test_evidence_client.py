import sys
import unittest
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
APPROACH2_DIR = THIS_DIR.parent.parent
sys.path.insert(0, str(APPROACH2_DIR))

from risk_scoring.evidence_client import CypherExecutor, EvidenceClient  # noqa: E402
from risk_scoring.evidence_allowlist import ParameterValidationError  # noqa: E402


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
