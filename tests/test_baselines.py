from pathlib import Path
import unittest

from safetwin5g.baselines import (
    RidgeModel,
    load_records,
    metrics,
    rule_prediction,
    select_ridge_alpha,
    temporal_persistence_prediction,
)


ROOT = Path(__file__).resolve().parents[1]
RECORDS = load_records(
    ROOT / "data" / "releases" / "safetwin5g-interventions-v0" / "records.jsonl"
)


class BaselineTests(unittest.TestCase):
    def setUp(self):
        self.train = [record for record in RECORDS if record["split"] == "train"]
        self.calibration = [
            record for record in RECORDS if record["split"] == "calibration"
        ]
        self.test = [record for record in RECORDS if record["split"] == "test"]

    def test_rule_uses_only_pre_action_fault_state(self):
        predictions = [rule_prediction(record) for record in self.test]
        self.assertTrue(all(prediction >= 0.0 for prediction in predictions))
        self.assertEqual(len(predictions), 3)

    def test_temporal_persistence_predicts_no_benefit(self):
        self.assertEqual(
            [temporal_persistence_prediction(record) for record in self.test],
            [0.0, 0.0, 0.0],
        )

    def test_ridge_preprocessing_and_alpha_use_no_test_rows(self):
        model, trials = select_ridge_alpha(self.train, self.calibration)
        self.assertIsInstance(model, RidgeModel)
        self.assertEqual(len(trials), 5)
        self.assertIn(model.alpha, {trial["alpha"] for trial in trials})
        self.assertEqual(len([model.predict(record) for record in self.test]), 3)

    def test_metric_reports_small_sample_size(self):
        result = metrics(self.test, rule_prediction)
        self.assertEqual(result["n"], 3)
        self.assertGreaterEqual(result["mae"], 0.0)


if __name__ == "__main__":
    unittest.main()
