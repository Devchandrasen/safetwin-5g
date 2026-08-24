from pathlib import Path
import unittest

from safetwin5g.baselines import load_records, select_ridge_alpha
from safetwin5g.diagnostics import (
    final_state_placebo,
    future_outcome_leakage_check,
    permutation_control,
    split_conformal_radius,
    split_group_overlaps,
)


ROOT = Path(__file__).resolve().parents[1]
RECORDS = load_records(
    ROOT / "data" / "releases" / "safetwin5g-interventions-v0" / "records.jsonl"
)


class DiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        train = [record for record in RECORDS if record["split"] == "train"]
        calibration = [
            record for record in RECORDS if record["split"] == "calibration"
        ]
        cls.model, _ = select_ridge_alpha(train, calibration)

    def test_groups_do_not_cross_splits(self):
        self.assertEqual(split_group_overlaps(RECORDS), {})

    def test_future_outcome_mutation_does_not_change_prediction(self):
        result = future_outcome_leakage_check(RECORDS, self.model.predict)
        self.assertTrue(result["passed"])
        self.assertEqual(result["max_prediction_change"], 0.0)

    def test_ninety_percent_conformal_is_unbounded_with_three_rows(self):
        result = split_conformal_radius([1.0, 2.0, 3.0], 0.90)
        self.assertIsNone(result["radius"])
        self.assertEqual(result["status"], "unbounded-insufficient-calibration")

    def test_lower_coverage_can_be_finite(self):
        result = split_conformal_radius([1.0, 2.0, 3.0], 0.50)
        self.assertEqual(result["radius"], 2.0)
        self.assertEqual(result["status"], "finite")

    def test_final_state_placebo_is_zero(self):
        self.assertTrue(final_state_placebo(RECORDS)["passed"])

    def test_exact_three_row_permutation_control_runs(self):
        test = [record for record in RECORDS if record["split"] == "test"]
        self.assertEqual(permutation_control(test, self.model.predict)["n_permutations"], 6)


if __name__ == "__main__":
    unittest.main()
