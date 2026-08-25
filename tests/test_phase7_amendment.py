from copy import deepcopy
from pathlib import Path
import unittest

from safetwin5g.phase7_design import (
    expand_phase7_design,
    load_phase7_design,
    validate_phase7_design,
)


ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = ROOT / "config" / "experiments" / "phase7-brace-v2a.json"


class Phase7AmendmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = load_phase7_design(DESIGN_PATH)
        cls.units = expand_phase7_design(cls.design)

    def test_amended_design_has_135_blocks_and_675_units(self):
        self.assertEqual(len(self.units), 675)
        blocks = {unit["assignment_block_id"] for unit in self.units}
        self.assertEqual(len(blocks), 135)
        self.assertEqual(
            {
                split: len(
                    {
                        unit["assignment_block_id"]
                        for unit in self.units
                        if unit["split"] == split
                    }
                )
                for split in ("train", "calibration", "test", "ood")
            },
            {"train": 28, "calibration": 21, "test": 70, "ood": 16},
        )

    def test_coverage_floor_produces_30_certified_faulty_blocks(self):
        faulty_test_blocks = {
            unit["assignment_block_id"]
            for unit in self.units
            if unit["split"] == "test" and unit["fault_family"] != "no_fault"
        }
        no_fault_test_blocks = {
            unit["assignment_block_id"]
            for unit in self.units
            if unit["split"] == "test" and unit["fault_family"] == "no_fault"
        }
        self.assertEqual(len(faulty_test_blocks), 60)
        self.assertEqual(len(no_fault_test_blocks), 10)
        self.assertEqual(
            int(
                len(faulty_test_blocks)
                * self.design["analysis"]["minimum_faulty_block_mutation_coverage"]
            ),
            30,
        )
        self.assertEqual(self.design["analysis"]["minimum_certified_mutation_count"], 29)

    def test_zero_violation_precision_is_below_ten_percent_at_floor(self):
        upper = 1.0 - 0.05 ** (1.0 / 30.0)
        self.assertLess(upper, 0.10)

    def test_amendment_is_frozen_before_pilot_and_preserves_boundaries(self):
        self.assertTrue(self.design["amendment"]["frozen_before_pilot"])
        self.assertEqual(self.design["amendment"]["amendment_id"], "phase7-precision-a1")
        self.assertFalse(self.design["safety"]["allow_live_actuation"])
        self.assertEqual(self.design["claim_boundaries"]["radio_evidence_label"], "simulated")
        self.assertIsNone(self.design["claim_boundaries"]["hardware_evidence_label"])
        self.assertFalse(self.design["claim_boundaries"]["operator_validation"])

    def test_validator_rejects_amendment_that_cannot_reach_precision_floor(self):
        weakened = deepcopy(self.design)
        weakened["splits"]["test"]["seeds"] = [1301, 1302, 1303, 1304, 1305]
        weakened["expected_counts"]["blocks"]["test"] = 35
        weakened["expected_counts"]["units"]["test"] = 175
        weakened["expected_counts"]["total_blocks"] = 100
        weakened["expected_counts"]["total_units"] = 500
        with self.assertRaisesRegex(ValueError, "cannot reach"):
            validate_phase7_design(weakened)


if __name__ == "__main__":
    unittest.main()
