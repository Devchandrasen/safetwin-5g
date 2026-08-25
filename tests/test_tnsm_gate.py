import unittest

from safetwin5g.tnsm_gate import assess_tnsm_manuscript_gate


def passing_inputs():
    report = {
        "execution_passed": True,
        "gates": {name: {"passed": True} for name in ("G1", "G2", "G3", "G4")},
        "decision": {
            "TNSM_claim_gate": "go",
            "live_actuation": "no-go",
            "submission_authorized": False,
        },
        "claim_boundaries": {
            "evidence_label": "sandbox-measured",
            "radio_evidence_label": "simulated",
            "hardware_evidence_label": None,
            "operator_validation": False,
            "conditional_coverage_claimed": False,
            "live_network_claimed": False,
        },
    }
    verification = {
        "passed": True,
        "TNSM_claim_gate": "go",
        "environment_deviation_D1_disclosed": True,
        "procedural_outcome_seal": True,
        "cryptographic_blinding": False,
        "live_actuation": "no-go",
        "submission_authorized": False,
    }
    return report, verification


class TnsmGateTests(unittest.TestCase):
    def test_all_local_gates_allow_draft_but_not_submission_or_live_action(self):
        report, verification = passing_inputs()
        result = assess_tnsm_manuscript_gate(report, verification)
        self.assertTrue(result["passed"])
        self.assertEqual(result["local_manuscript_draft_gate"], "go")
        self.assertEqual(result["publication_submission"], "pending-external-authorization")
        self.assertEqual(result["live_actuation"], "no-go")

    def test_baseline_win_or_any_primary_failure_blocks_positive_draft(self):
        report, verification = passing_inputs()
        report["gates"]["G3"]["passed"] = False
        report["decision"]["TNSM_claim_gate"] = "no-go"
        verification["TNSM_claim_gate"] = "no-go"
        result = assess_tnsm_manuscript_gate(report, verification)
        self.assertFalse(result["passed"])
        self.assertIn("G3_passed", result["failed_checks"])
        self.assertIsNotNone(result["required_if_no_go"])

    def test_claim_promotion_or_missing_D1_disclosure_fails_closed(self):
        report, verification = passing_inputs()
        report["claim_boundaries"]["hardware_evidence_label"] = "hardware-measured"
        verification["environment_deviation_D1_disclosed"] = False
        result = assess_tnsm_manuscript_gate(report, verification)
        self.assertFalse(result["passed"])
        self.assertIn("no_hardware_claim", result["failed_checks"])
        self.assertIn("D1_environment_deviation_disclosed", result["failed_checks"])


if __name__ == "__main__":
    unittest.main()
