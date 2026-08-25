from copy import deepcopy
from pathlib import Path
import unittest

from safetwin5g.phase7_design import (
    REQUIRED_ACTION_IDS,
    expand_phase7_design,
    load_phase7_design,
    validate_phase7_design,
)


ROOT = Path(__file__).resolve().parents[1]
DESIGN_PATH = ROOT / "config" / "experiments" / "phase7-brace-v2.json"


class Phase7DesignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.design = load_phase7_design(DESIGN_PATH)
        cls.units = expand_phase7_design(cls.design)

    def test_frozen_design_has_100_complete_blocks_and_500_units(self):
        self.assertEqual(len(self.units), 500)
        blocks = {}
        for unit in self.units:
            blocks.setdefault(unit["assignment_block_id"], set()).add(
                unit["action_id"]
            )
        self.assertEqual(len(blocks), 100)
        self.assertTrue(all(actions == REQUIRED_ACTION_IDS for actions in blocks.values()))

    def test_action_names_do_not_encode_correctness(self):
        forbidden = ("effective", "negative_control", "oracle", "correct_action")
        for action in self.design["action_portfolio"]:
            text = "|".join(str(value).lower() for value in action.values())
            self.assertFalse(any(token in text for token in forbidden), action)

    def test_independent_block_counts_meet_calibration_and_test_gates(self):
        blocks = {
            split: {
                unit["assignment_block_id"]
                for unit in self.units
                if unit["split"] == split
            }
            for split in ("train", "calibration", "test", "ood")
        }
        self.assertEqual({key: len(value) for key, value in blocks.items()}, {
            "train": 28,
            "calibration": 21,
            "test": 35,
            "ood": 16,
        })

    def test_randomization_is_deterministic_and_not_lexical(self):
        repeated = expand_phase7_design(self.design)
        self.assertEqual(self.units, repeated)
        train_ids = [unit["unit_id"] for unit in self.units if unit["split"] == "train"]
        self.assertNotEqual(train_ids, sorted(train_ids))

    def test_safety_and_claim_boundaries_are_fail_closed(self):
        self.assertFalse(self.design["safety"]["allow_live_actuation"])
        self.assertTrue(self.design["safety"]["model_actions_are_proposals_only"])
        self.assertEqual(
            self.design["claim_boundaries"]["evidence_label_after_measurement"],
            "sandbox-measured",
        )
        self.assertEqual(self.design["claim_boundaries"]["radio_evidence_label"], "simulated")
        self.assertIsNone(self.design["claim_boundaries"]["hardware_evidence_label"])
        self.assertFalse(self.design["claim_boundaries"]["operator_validation"])

    def test_validator_rejects_label_leakage_live_use_and_small_calibration(self):
        leaking = deepcopy(self.design)
        leaking["action_portfolio"][1]["description"] = "effective action"
        with self.assertRaisesRegex(ValueError, "leaks correctness"):
            validate_phase7_design(leaking)

        live = deepcopy(self.design)
        live["safety"]["allow_live_actuation"] = True
        with self.assertRaisesRegex(ValueError, "live actuation"):
            validate_phase7_design(live)

        small = deepcopy(self.design)
        small["splits"]["calibration"]["seeds"] = [1201]
        small["expected_counts"]["blocks"]["calibration"] = 7
        small["expected_counts"]["units"]["calibration"] = 35
        small["expected_counts"]["total_blocks"] = 86
        small["expected_counts"]["total_units"] = 430
        with self.assertRaisesRegex(ValueError, "19 independent calibration"):
            validate_phase7_design(small)


if __name__ == "__main__":
    unittest.main()
