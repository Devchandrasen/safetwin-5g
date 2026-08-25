import unittest

from safetwin5g.phase7_scalability import benchmark_brace, synthetic_contrast_blocks


class Phase7ScalabilityTests(unittest.TestCase):
    def test_fixture_blocks_are_complete_and_deterministic(self):
        first = synthetic_contrast_blocks(21)
        second = synthetic_contrast_blocks(21)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 21)
        self.assertEqual({len(actions) for actions in first.values()}, {4})

    def test_microbenchmark_preserves_claim_and_safety_boundaries(self):
        report = benchmark_brace(block_sizes=(21, 30, 50), repeats=3, decision_batch_n=20)
        self.assertEqual(report["input_evidence_label"], "fixture")
        self.assertFalse(report["network_performance_claim"])
        self.assertFalse(report["hardware_or_operator_claim"])
        self.assertEqual(report["decision_batch"]["decision"], "require-human-approval")
        self.assertFalse(report["decision_batch"]["apply_allowed"])
        self.assertEqual([row["block_n"] for row in report["calibration"]], [21, 30, 50])


if __name__ == "__main__":
    unittest.main()
