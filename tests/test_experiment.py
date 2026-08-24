import copy
from pathlib import Path
import unittest

from safetwin5g.experiment import expand_design, load_design, validate_design


ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = ROOT / "config" / "experiments" / "phase6-v1.json"


class ExperimentDesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = load_design(DESIGN_PATH)
        cls.units = expand_design(cls.design)

    def test_frozen_design_has_declared_split_counts(self):
        counts = {
            split: sum(unit["split"] == split for unit in self.units)
            for split in ("train", "calibration", "test", "ood")
        }
        self.assertEqual(
            counts,
            {"train": 42, "calibration": 21, "test": 21, "ood": 48},
        )
        self.assertEqual(len(self.units), 132)
        self.assertEqual(len({unit["unit_id"] for unit in self.units}), 132)

    def test_every_split_and_family_has_all_action_arms(self):
        expected = {"effective", "no_action", "negative_control"}
        for split in ("train", "calibration", "test", "ood"):
            for family in (
                "packet_impairment",
                "network_function_interruption",
                "cpu_saturation",
                "no_fault",
            ):
                arms = {
                    unit["action_arm"]
                    for unit in self.units
                    if unit["split"] == split and unit["fault_family"] == family
                }
                self.assertEqual(arms, expected)

    def test_ood_changes_workload_and_fault_severity(self):
        self.assertNotEqual(
            self.design["splits"]["test"]["workload"],
            self.design["splits"]["ood"]["workload"],
        )
        for fault in self.design["faults"]:
            if fault["family"] != "no_fault":
                self.assertNotIn(
                    fault["ood_severity"], fault["development_severities"]
                )

    def test_randomization_is_deterministic_but_not_lexical(self):
        repeated = expand_design(self.design)
        self.assertEqual(self.units, repeated)
        train_ids = [
            unit["unit_id"] for unit in self.units if unit["split"] == "train"
        ]
        self.assertNotEqual(train_ids, sorted(train_ids))

    def test_validator_rejects_live_or_underpowered_design(self):
        live = copy.deepcopy(self.design)
        live["environment"] = "live"
        with self.assertRaisesRegex(ValueError, "sandbox"):
            validate_design(live)

        underpowered = copy.deepcopy(self.design)
        underpowered["splits"]["calibration"]["seeds"] = []
        with self.assertRaisesRegex(ValueError, "split counts"):
            validate_design(underpowered)

    def test_claim_and_safety_boundaries_are_explicit(self):
        claims = self.design["claim_boundaries"]
        self.assertEqual(claims["evidence_label_after_measurement"], "sandbox-measured")
        self.assertEqual(claims["radio_evidence_label"], "simulated")
        self.assertIsNone(claims["hardware_evidence_label"])
        self.assertFalse(claims["operator_validation"])
        self.assertFalse(self.design["safety"]["allow_live_actuation"])
        self.assertTrue(self.design["safety"]["require_explicit_sandbox_approval"])


if __name__ == "__main__":
    unittest.main()
