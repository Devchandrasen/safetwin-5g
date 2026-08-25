import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "evidence" / "benchmarks" / "20260825T030431Z-phase6-analysis-v1"


class Phase6ResultTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((BENCHMARK / "report.json").read_text(encoding="utf-8"))

    def test_locked_test_baseline_result_is_preserved(self):
        evaluation = self.report["baselines"]["evaluation"]["test"]
        self.assertEqual(self.report["baselines"]["test_winner"], "deterministic_rule")
        self.assertAlmostEqual(evaluation["deterministic_rule"]["mae"], 3.8888888888888893)
        self.assertAlmostEqual(evaluation["action_conditional_ridge"]["mae"], 5.261162973449767)
        self.assertAlmostEqual(evaluation["temporal_persistence"]["mae"], 17.460317460317462)

    def test_uncertainty_and_ood_are_finite_and_distinct(self):
        calibration = self.report["uncertainty"]["calibration"]
        self.assertEqual(calibration["status"], "finite")
        self.assertEqual(calibration["calibration_n"], 21)
        self.assertEqual(calibration["rank"], 20)
        self.assertAlmostEqual(calibration["radius"], 19.45912753311722)
        self.assertEqual(self.report["ood"]["test_ood_count"], 0)
        self.assertEqual(self.report["ood"]["ood_split_ood_count"], 48)

    def test_hypothesis_and_promotion_decisions_are_fail_closed(self):
        hypotheses = self.report["hypotheses"]
        self.assertEqual(hypotheses["H1"]["status"], "not-supported")
        self.assertEqual(hypotheses["H2"]["status"], "not-supported")
        self.assertEqual(hypotheses["H3"]["status"], "gated-not-run")
        self.assertAlmostEqual(hypotheses["H2"]["coverage"], 3 / 14)
        self.assertEqual(
            hypotheses["multiplicity"]["adjusted_pvalues"],
            {"H1": 0.0625, "H2": 0.0625},
        )
        self.assertEqual(self.report["promotion"]["model_promotion"], "no-go")
        self.assertEqual(self.report["promotion"]["live_actuation"], "no-go")

    def test_claim_boundaries_remain_separate(self):
        self.assertEqual(self.report["evidence_label"], "sandbox-measured")
        self.assertEqual(self.report["radio_evidence_label"], "simulated")
        self.assertIsNone(self.report["hardware_evidence_label"])
        self.assertFalse(self.report["operator_validation"])


if __name__ == "__main__":
    unittest.main()
