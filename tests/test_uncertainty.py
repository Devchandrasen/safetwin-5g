from pathlib import Path
import unittest

from safetwin5g.baselines import load_records
from safetwin5g.uncertainty import (
    ConformalCalibration,
    RangeOODDetector,
    selective_assessment,
)


ROOT = Path(__file__).resolve().parents[1]
RECORDS = load_records(
    ROOT / "data" / "releases" / "safetwin5g-interventions-v0" / "records.jsonl"
)


class UncertaintyTests(unittest.TestCase):
    def test_conformal_fails_closed_when_nominal_rank_exceeds_sample(self):
        calibration = ConformalCalibration.fit([1, 2, 3], [0, 0, 0], 0.90)
        self.assertIsNone(calibration.radius)
        self.assertIsNone(calibration.interval(2.0))

    def test_severity_range_detector_uses_development_only(self):
        development = [
            record
            for record in RECORDS
            if record["split"] in {"train", "calibration"}
        ]
        detector = RangeOODDetector.fit(development)
        self.assertEqual(
            set(detector.fitted_scenario_ids),
            {record["scenario_id"] for record in development},
        )
        test = [record for record in RECORDS if record["split"] == "test"]
        self.assertTrue(all(detector.evaluate(record)["is_ood"] for record in test))

    def test_unbounded_interval_forces_abstention(self):
        calibration = ConformalCalibration.fit([1, 2, 3], [0, 0, 0], 0.90)
        result = selective_assessment(
            2.0,
            calibration,
            {"ood_score": 0.0, "is_ood": False, "reason": "in range"},
        )
        self.assertEqual(result["decision"], "abstain")
        self.assertIn("unbounded", result["reasons"][0])

    def test_finite_in_range_case_can_reach_safety_gate(self):
        calibration = ConformalCalibration.fit([0.1] * 19, [0.0] * 19, 0.90)
        result = selective_assessment(
            1.0,
            calibration,
            {"ood_score": 0.0, "is_ood": False, "reason": "in range"},
        )
        self.assertEqual(result["decision"], "eligible-for-safety-gate")


if __name__ == "__main__":
    unittest.main()
