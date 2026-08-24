import unittest

from tools.run_dashboard_smoke import all_loopback, evaluate_payloads


class DashboardSmokeTests(unittest.TestCase):
    def test_listener_gate_accepts_loopback_only(self):
        self.assertTrue(all_loopback(["127.0.0.1"]))
        self.assertTrue(all_loopback(["::1"]))
        self.assertFalse(all_loopback([]))
        self.assertFalse(all_loopback(["0.0.0.0"]))
        self.assertFalse(all_loopback(["127.0.0.1", "192.168.1.20"]))

    def test_payload_gate_requires_six_unapplied_abstentions(self):
        status = {
            "overall_decision": {"model_promotion": "no-go"},
            "safety_lock": {"allow_live_actuation": False},
            "proposal_audit": {"proposal_count": 6},
        }
        proposals = {
            "proposal_count": 6,
            "abstain_count": 6,
            "applied_action_count": 0,
            "records": [
                {"decision": "abstain", "execution_status": "not-applied"}
                for _ in range(6)
            ],
        }
        self.assertEqual(evaluate_payloads(status, proposals), [])

    def test_payload_gate_rejects_an_applied_action(self):
        status = {
            "overall_decision": {"model_promotion": "no-go"},
            "safety_lock": {"allow_live_actuation": False},
            "proposal_audit": {"proposal_count": 6},
        }
        proposals = {
            "proposal_count": 6,
            "abstain_count": 5,
            "applied_action_count": 1,
            "records": [
                {"decision": "abstain", "execution_status": "not-applied"}
                for _ in range(5)
            ] + [{"decision": "require-approval", "execution_status": "applied"}],
        }
        errors = evaluate_payloads(status, proposals)
        self.assertGreaterEqual(len(errors), 3)


if __name__ == "__main__":
    unittest.main()
