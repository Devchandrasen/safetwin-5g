from pathlib import Path
import json
import unittest

from safetwin5g.analysis_v1 import load_records
from safetwin5g.phase7_design import load_phase7_design
from safetwin5g.phase7_feasibility import analyze_v1_feasibility


ROOT = Path(__file__).resolve().parents[1]


class Phase7FeasibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        records = load_records(
            ROOT / "data" / "releases" / "safetwin5g-interventions-v1" / "records.jsonl"
        )
        design = load_phase7_design(
            ROOT / "config" / "experiments" / "phase7-brace-v2.json"
        )
        cls.report = analyze_v1_feasibility(records, design)

    def test_v1_cannot_identify_the_five_named_action_portfolio(self):
        limits = self.report["legacy_limitations"]
        self.assertEqual(limits["strict_phase7_named_action_complete_blocks"], 0)
        self.assertEqual(limits["observed_v1_block_n"], 44)
        self.assertEqual(limits["strict_named_action_feasibility"], "not-identified")

    def test_legacy_block_calibration_is_unbounded_at_seven_blocks(self):
        calibration = self.report["legacy_block_calibration"]
        self.assertEqual(calibration["calibration_block_n"], 7)
        self.assertEqual(calibration["rank"], 8)
        self.assertEqual(calibration["status"], "unbounded")
        self.assertIsNone(calibration["radius"])

    def test_test_and_ood_both_fail_closed(self):
        self.assertEqual(self.report["legacy_test"]["independent_block_n"], 7)
        self.assertEqual(self.report["legacy_test"]["certified_block_n"], 0)
        self.assertEqual(self.report["legacy_ood"]["independent_block_n"], 16)
        self.assertEqual(self.report["legacy_ood"]["certified_block_n"], 0)

    def test_model_selection_uses_train_units_only(self):
        fitted = set(self.report["model"]["fitted_unit_ids"])
        self.assertEqual(len(fitted), 42)
        self.assertTrue(all("-train-" in unit_id for unit_id in fitted))
        self.assertTrue(
            all(trial["independent_fold_n"] == 14 for trial in self.report["model"]["trials"])
        )

    def test_prospective_precision_limit_is_explicit(self):
        design = self.report["prospective_v2_design_check"]
        self.assertEqual(design["calibration_blocks"], 21)
        self.assertEqual(design["test_blocks"], 35)
        self.assertEqual(design["faulty_test_blocks"], 30)
        self.assertEqual(design["minimum_certified_mutations_at_frozen_coverage"], 15)
        self.assertGreater(
            design["one_sided_95pct_zero_violation_upper_at_minimum_coverage"], 0.10
        )
        self.assertEqual(design["minimum_zero_violation_n_for_upper_below_0p10"], 29)
        self.assertEqual(
            design["empirical_ten_percent_precision_at_minimum_coverage"],
            "insufficient",
        )

    def test_negative_result_does_not_change_phase6_or_claim_live_use(self):
        self.assertFalse(self.report["confirmatory_claim_allowed"])
        self.assertFalse(self.report["phase6_decision_changed"])
        self.assertEqual(self.report["decision"]["legacy_v1_BRACE_promotion"], "no-go")
        self.assertEqual(self.report["decision"]["live_actuation"], "no-go")
        self.assertIsNone(self.report["hardware_evidence_label"])
        self.assertFalse(self.report["operator_validation"])


if __name__ == "__main__":
    unittest.main()
