from pathlib import Path
import json
import unittest

from safetwin5g.dataset_v2a import ACTION_IDS, build_records, quality_report


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "evidence" / "scenarios" / "20260825T044909Z-phase7-pilot-v2a"


class DatasetV2aTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = build_records(PILOT, require_complete=False)
        cls.report = quality_report(cls.records, require_complete=False)

    def test_full_release_rejects_pilot(self):
        with self.assertRaisesRegex(ValueError, "675-unit"):
            build_records(PILOT)

    def test_pilot_yields_one_complete_named_action_block(self):
        self.assertEqual(len(self.records), 5)
        self.assertEqual({record["action_id"] for record in self.records}, set(ACTION_IDS))
        self.assertEqual(len({record["assignment_block_id"] for record in self.records}), 1)
        self.assertTrue(self.report["passed"], self.report["structural_checks"])
        self.assertFalse(self.report["release_eligible"])

    def test_contrasts_use_observe_only_and_frozen_harm_definition(self):
        control = next(row for row in self.records if row["action_id"] == "observe_only")
        self.assertEqual(control["observed_action_benefit"], 0.0)
        distractor = next(
            row for row in self.records if row["action_id"] == "apply_packet_impairment_25"
        )
        self.assertLess(distractor["observed_action_benefit"], 0.0)
        self.assertTrue(distractor["false_remediation"])
        self.assertTrue(distractor["harmful_action"])
        self.assertTrue(distractor["violates_benefit_margin"])

    def test_public_records_exclude_approval_text_and_claims_stay_bounded(self):
        serialized = json.dumps(self.records, sort_keys=True)
        self.assertNotIn("authorization_basis", serialized)
        self.assertNotIn("approved_by", serialized)
        self.assertEqual({row["evidence_label"] for row in self.records}, {"sandbox-measured"})
        self.assertEqual({row["radio_evidence_label"] for row in self.records}, {"simulated"})
        self.assertTrue(all(row["hardware_evidence_label"] is None for row in self.records))
        self.assertTrue(all(row["operator_validation"] is False for row in self.records))

    def test_all_mutations_retain_approval_rollback_and_clean_recovery(self):
        mutations = [row for row in self.records if row["action_applied"]]
        self.assertEqual(len(mutations), 4)
        self.assertTrue(all(row["approval_id"] for row in mutations))
        self.assertTrue(all(row["safety_decision"] == "require-human-approval" for row in mutations))
        self.assertTrue(all(row["reversible"] and row["rollback_plan_recorded"] for row in mutations))
        self.assertTrue(all(row["cleanup_verified"] for row in mutations))


if __name__ == "__main__":
    unittest.main()
