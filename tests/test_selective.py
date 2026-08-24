import unittest

from safetwin5g.selective import safe_rate, selective_endpoints


class SelectiveTests(unittest.TestCase):
    def test_safe_rate_preserves_undefined_denominator(self):
        self.assertIsNone(safe_rate(0, 0))
        self.assertEqual(safe_rate(1, 2), 0.5)

    def test_all_abstain_has_zero_coverage_and_undefined_selective_harm(self):
        records = [
            {"scenario_id": "a", "observed_benefit": 1.0},
            {"scenario_id": "b", "observed_benefit": 2.0},
        ]
        assessments = [
            {
                "scenario_id": "a",
                "decision": "abstain",
                "interval": None,
                "ood_score": 1.0,
            },
            {
                "scenario_id": "b",
                "decision": "abstain",
                "interval": None,
                "ood_score": 1.0,
            },
        ]
        result = selective_endpoints(records, assessments)
        self.assertEqual(result["coverage"], 0.0)
        self.assertEqual(result["abstention_rate"], 1.0)
        self.assertIsNone(result["selective_harmful_rate"])
        self.assertIsNone(result["risk_coverage_auc"])
        self.assertFalse(result["harm_reduction_claim_supported"])

    def test_scenario_mismatch_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "scenario sets differ"):
            selective_endpoints(
                [{"scenario_id": "a", "observed_benefit": 1.0}],
                [{"scenario_id": "b", "decision": "abstain"}],
            )


if __name__ == "__main__":
    unittest.main()
