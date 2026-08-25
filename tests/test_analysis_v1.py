from copy import deepcopy
from pathlib import Path
import unittest

from safetwin5g.analysis_v1 import (
    DesignOODDetector,
    analyze,
    describe,
    holm_adjust,
    load_records,
    raw_features,
    select_model,
)
from safetwin5g.uncertainty import ConformalCalibration


ROOT = Path(__file__).resolve().parents[1]
RECORDS_PATH = (
    ROOT / "data" / "releases" / "safetwin5g-interventions-v1" / "records.jsonl"
)


class AnalysisV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = load_records(RECORDS_PATH)
        cls.by_split = {
            split: [record for record in cls.records if record["split"] == split]
            for split in ("train", "calibration", "test", "ood")
        }
        cls.model, cls.trials = select_model(
            cls.by_split["train"], cls.by_split["calibration"]
        )

    def test_model_fit_and_tuning_do_not_use_test_or_ood_units(self):
        self.assertEqual(len(self.model.fitted_unit_ids), 42)
        self.assertEqual(
            set(self.model.fitted_unit_ids),
            {record["unit_id"] for record in self.by_split["train"]},
        )
        self.assertEqual(len(self.trials), 6)

    def test_features_do_not_change_when_post_treatment_values_are_mutated(self):
        record = self.by_split["test"][0]
        original = raw_features(record)
        mutated = deepcopy(record)
        mutated["post_action_user_plane_burden"] = 1_000_000.0
        for sample in mutated["windows"]["post_action"]["samples"]:
            for name in sample["metrics"]:
                sample["metrics"][name] = 1_000_000.0
        self.assertEqual(original, raw_features(mutated))
        self.assertEqual(self.model.predict(record), self.model.predict(mutated))

    def test_ninety_percent_conformal_is_finite_at_n21(self):
        predictions = [self.model.predict(record) for record in self.by_split["calibration"]]
        targets = [record["post_action_user_plane_burden"] for record in self.by_split["calibration"]]
        calibration = ConformalCalibration.fit(predictions, targets, 0.90)
        self.assertEqual(calibration.calibration_n, 21)
        self.assertEqual(calibration.rank, 20)
        self.assertEqual(calibration.status, "finite")
        self.assertIsNotNone(calibration.radius)

    def test_design_ood_detector_separates_locked_test_from_ood(self):
        detector = DesignOODDetector.fit(
            self.by_split["train"] + self.by_split["calibration"]
        )
        self.assertFalse(any(detector.evaluate(record)["is_ood"] for record in self.by_split["test"]))
        self.assertTrue(all(detector.evaluate(record)["is_ood"] for record in self.by_split["ood"]))

    def test_descriptive_statistics_and_holm_are_deterministic(self):
        summary = describe([1.0, 2.0, 9.0])
        self.assertEqual(summary["median"], 2.0)
        self.assertEqual(summary["p75"], 5.5)
        self.assertEqual(holm_adjust({"H1": 0.01, "H2": 0.04}), {"H1": 0.02, "H2": 0.04})

    def test_full_analysis_preserves_gates_and_claim_boundaries(self):
        report, predictions, contrasts = analyze(self.records)
        self.assertEqual(len(predictions), 132)
        self.assertEqual(len(contrasts), 88)
        self.assertEqual(report["uncertainty"]["calibration"]["status"], "finite")
        self.assertEqual(report["ood"]["test_ood_count"], 0)
        self.assertEqual(report["ood"]["ood_split_ood_count"], 48)
        self.assertIn(report["hypotheses"]["H1"]["status"], {"supported", "not-supported"})
        self.assertIn(report["hypotheses"]["H2"]["status"], {"supported", "not-supported"})
        h3 = report["hypotheses"]["H3"]
        if not (
            report["hypotheses"]["H1"]["gate_passed"]
            and report["hypotheses"]["H2"]["gate_passed"]
        ):
            self.assertEqual(h3["status"], "gated-not-run")
            self.assertIsNone(h3["evaluation"])
        self.assertEqual(report["evidence_label"], "sandbox-measured")
        self.assertEqual(report["radio_evidence_label"], "simulated")
        self.assertIsNone(report["hardware_evidence_label"])
        self.assertFalse(report["operator_validation"])
        self.assertEqual(report["promotion"]["live_actuation"], "no-go")


if __name__ == "__main__":
    unittest.main()
