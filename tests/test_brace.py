import unittest

from safetwin5g.brace import (
    BlockConformalCalibration,
    BraceSafetyContext,
    assess_brace_actions,
)


ACTIONS = ("clear_packet_impairment", "resume_upf", "stop_cpu_stress")


def blocks(count, residual_scale=1.0):
    return {
        f"block-{index:02d}": {
            action: (10.0 + action_index, 10.0 + action_index + residual_scale * index / 10.0)
            for action_index, action in enumerate(ACTIONS)
        }
        for index in range(1, count + 1)
    }


def context(**overrides):
    values = {
        "environment": "sandbox",
        "evidence_label": "sandbox-measured",
        "radio_evidence_label": "simulated",
        "hardware_evidence_label": None,
        "operator_validation": False,
        "is_ood": False,
        "allowlisted_actions": ACTIONS,
        "reversible_actions": ACTIONS,
        "rollback_plan_actions": ACTIONS,
    }
    values.update(overrides)
    return BraceSafetyContext(**values)


class BraceTests(unittest.TestCase):
    def test_block_score_is_max_residual_and_n21_radius_is_finite(self):
        calibration = BlockConformalCalibration.fit(
            blocks(21), action_ids=ACTIONS, coverage=0.90
        )
        self.assertEqual(calibration.calibration_block_n, 21)
        self.assertEqual(calibration.rank, 20)
        self.assertEqual(calibration.status, "finite")
        self.assertAlmostEqual(calibration.radius, 2.0)
        self.assertAlmostEqual(calibration.block_scores[0], 0.1)
        self.assertAlmostEqual(calibration.block_scores[-1], 2.1)

    def test_incomplete_block_is_rejected_instead_of_row_calibrated(self):
        incomplete = blocks(21)
        del incomplete["block-01"]["resume_upf"]
        with self.assertRaisesRegex(ValueError, "incomplete"):
            BlockConformalCalibration.fit(
                incomplete, action_ids=ACTIONS, coverage=0.90
            )

    def test_small_calibration_fails_closed_with_unbounded_radius(self):
        calibration = BlockConformalCalibration.fit(
            blocks(3), action_ids=ACTIONS, coverage=0.90
        )
        self.assertEqual(calibration.status, "unbounded")
        decision = assess_brace_actions(
            {action: 100.0 for action in ACTIONS},
            calibration,
            context(),
            minimum_benefit_margin=5.0,
        )
        self.assertEqual(decision.decision, "abstain")
        self.assertIn("unbounded", decision.reasons[0])

    def test_joint_interval_supports_post_selection_certificate(self):
        calibration = BlockConformalCalibration.fit(
            blocks(21), action_ids=ACTIONS, coverage=0.90
        )
        predictions = {
            "clear_packet_impairment": 15.0,
            "resume_upf": 30.0,
            "stop_cpu_stress": 20.0,
        }
        decision = assess_brace_actions(
            predictions,
            calibration,
            context(),
            minimum_benefit_margin=5.0,
        )
        self.assertEqual(decision.decision, "require-human-approval")
        self.assertEqual(decision.selected_action_id, "resume_upf")
        self.assertAlmostEqual(decision.lower_benefit_bound, 28.0)
        self.assertFalse(decision.apply_allowed)
        self.assertTrue(decision.human_approval_required)

        observed = {
            "clear_packet_impairment": 14.0,
            "resume_upf": 29.0,
            "stop_cpu_stress": 18.5,
        }
        self.assertTrue(
            all(
                decision.intervals[action][0]
                <= observed[action]
                <= decision.intervals[action][1]
                for action in ACTIONS
            )
        )
        self.assertGreater(observed[decision.selected_action_id], 5.0)

    def test_ood_live_and_fixture_contexts_cannot_receive_certificate(self):
        calibration = BlockConformalCalibration.fit(
            blocks(21), action_ids=ACTIONS, coverage=0.90
        )
        predictions = {action: 100.0 for action in ACTIONS}
        ood = assess_brace_actions(
            predictions, calibration, context(is_ood=True), minimum_benefit_margin=5.0
        )
        self.assertEqual(ood.decision, "abstain")
        live = assess_brace_actions(
            predictions,
            calibration,
            context(environment="live"),
            minimum_benefit_margin=5.0,
        )
        self.assertEqual(live.decision, "reject")
        fixture = assess_brace_actions(
            predictions,
            calibration,
            context(evidence_label="fixture"),
            minimum_benefit_margin=5.0,
        )
        self.assertEqual(fixture.decision, "abstain")

    def test_missing_rollback_or_allowlist_excludes_action(self):
        calibration = BlockConformalCalibration.fit(
            blocks(21), action_ids=ACTIONS, coverage=0.90
        )
        decision = assess_brace_actions(
            {action: 100.0 for action in ACTIONS},
            calibration,
            context(rollback_plan_actions=(), allowlisted_actions=()),
            minimum_benefit_margin=5.0,
        )
        self.assertEqual(decision.decision, "abstain")
        self.assertTrue(any("rollback plan missing" in reason for reason in decision.reasons))
        self.assertTrue(any("not allowlisted" in reason for reason in decision.reasons))

    def test_guarantee_contract_states_scope_and_exclusions(self):
        calibration = BlockConformalCalibration.fit(
            blocks(21), action_ids=ACTIONS, coverage=0.90
        )
        contract = calibration.guarantee_contract()
        self.assertEqual(contract["calibration_unit"], "complete-assignment-block")
        self.assertIn("detected OOD", contract["exclusions"])
        self.assertIn("actuation authorization", contract["exclusions"])
        self.assertIn("exchangeable complete blocks", contract["assumptions"])


if __name__ == "__main__":
    unittest.main()
