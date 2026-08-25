from copy import deepcopy
from pathlib import Path
import unittest

from safetwin5g.phase7_design import expand_phase7_design, load_phase7_design
from safetwin5g.phase7_runner import (
    Phase7UnitRunner,
    expected_fault_state,
    expected_post_action_state,
)
from safetwin5g.safety import Decision, SafetyPolicy
from sandbox.run_phase7 import action_proposal, select_pilot_blocks, validate_policy


ROOT = Path(__file__).resolve().parents[1]
DESIGN = load_phase7_design(ROOT / "config" / "experiments" / "phase7-brace-v2a.json")
UNITS = expand_phase7_design(DESIGN)


def unit_for(family, action):
    return deepcopy(
        next(
            unit
            for unit in UNITS
            if unit["fault_family"] == family and unit["action_id"] == action
        )
    )


def approval_for(units):
    return {
        "approval_status": "approved",
        "environment": "sandbox",
        "experiment_id": DESIGN["experiment_id"],
        "approval_id": "test-approval",
        "unit_ids": [unit["unit_id"] for unit in units],
    }


class FakeBackend:
    def __init__(self, samples=3, fail_action=False, fail_cleanup=False):
        self.samples = samples
        self.fail_action = fail_action
        self.fail_cleanup = fail_cleanup
        self.events = []
        self.state = {}

    def reset(self, unit):
        self.events.append("reset")
        self.state = {
            "configured_packet_loss_pct": 0.0,
            "upf_process_running": 1.0,
            "stress_workers_count": 0.0,
        }

    def observe_window(self, stage, unit):
        self.events.append(f"observe:{stage}")
        return [
            {
                "sample_index": index,
                "observed_at": f"2026-08-25T00:00:{len(self.events):02d}.{index:02d}+00:00",
                "metrics": dict(self.state),
            }
            for index in range(1, self.samples + 1)
        ]

    def inject_fault(self, unit):
        self.events.append("inject")
        self.state = expected_fault_state(unit)

    def apply_action(self, unit):
        self.events.append("action")
        if self.fail_action:
            raise RuntimeError("action failed")
        self.state = expected_post_action_state(unit)

    def cleanup(self, unit):
        self.events.append("cleanup")
        if self.fail_cleanup:
            raise RuntimeError("cleanup failed")
        self.state = {
            "configured_packet_loss_pct": 0.0,
            "upf_process_running": 1.0,
            "stress_workers_count": 0.0,
        }


class Phase7RunnerTests(unittest.TestCase):
    def test_all_named_actions_have_context_specific_state_checks(self):
        cases = [
            unit_for("packet_impairment", "observe_only"),
            unit_for("packet_impairment", "clear_packet_impairment"),
            unit_for("network_function_interruption", "resume_upf"),
            unit_for("cpu_saturation", "stop_cpu_stress"),
            unit_for("no_fault", "apply_packet_impairment_25"),
            unit_for("network_function_interruption", "clear_packet_impairment"),
        ]
        approval = approval_for(cases)
        for unit in cases:
            with self.subTest(unit=unit["unit_id"]):
                trace = Phase7UnitRunner(FakeBackend(), 3).run(unit, approval)
                self.assertTrue(trace["passed"], trace)
                self.assertTrue(trace["cleanup_verified"])

    def test_action_failure_still_recovers_and_fails(self):
        unit = unit_for("packet_impairment", "clear_packet_impairment")
        backend = FakeBackend(fail_action=True)
        trace = Phase7UnitRunner(backend, 3).run(unit, approval_for([unit]))
        self.assertFalse(trace["passed"])
        self.assertTrue(trace["cleanup_verified"])
        self.assertEqual(backend.events[-2:], ["cleanup", "observe:recovery"])

    def test_dirty_cleanup_aborts_acceptance(self):
        unit = unit_for("no_fault", "apply_packet_impairment_25")
        trace = Phase7UnitRunner(FakeBackend(fail_cleanup=True), 3).run(
            unit, approval_for([unit])
        )
        self.assertFalse(trace["passed"])
        self.assertFalse(trace["cleanup_verified"])

    def test_unit_not_explicitly_approved_is_rejected_before_backend_use(self):
        approved = unit_for("packet_impairment", "observe_only")
        unapproved = unit_for("cpu_saturation", "stop_cpu_stress")
        backend = FakeBackend()
        with self.assertRaisesRegex(PermissionError, "unit-scoped"):
            Phase7UnitRunner(backend, 3).run(unapproved, approval_for([approved]))
        self.assertEqual(backend.events, [])

    def test_missing_samples_fail_trace_even_after_clean_recovery(self):
        unit = unit_for("cpu_saturation", "stop_cpu_stress")
        trace = Phase7UnitRunner(FakeBackend(samples=2), 3).run(
            unit, approval_for([unit])
        )
        self.assertFalse(trace["passed"])
        self.assertTrue(trace["cleanup_verified"])

    def test_one_pilot_block_contains_all_five_named_actions(self):
        pilot = select_pilot_blocks(UNITS, 1)
        self.assertEqual(len(pilot), 5)
        self.assertEqual(len({unit["assignment_block_id"] for unit in pilot}), 1)
        self.assertEqual(
            {unit["action_id"] for unit in pilot},
            {
                "observe_only",
                "clear_packet_impairment",
                "resume_upf",
                "stop_cpu_stress",
                "apply_packet_impairment_25",
            },
        )

    def test_every_mutation_is_allowlisted_reversible_and_requires_approval(self):
        policy = SafetyPolicy.from_path(ROOT / "config" / "actions.json")
        validate_policy(UNITS, policy)
        for unit in UNITS:
            proposal = action_proposal(unit)
            if not unit["mutates"]:
                self.assertIsNone(proposal)
                continue
            self.assertIsNotNone(proposal)
            self.assertTrue(proposal.reversible)
            self.assertTrue(proposal.rollback_plan)
            evaluation = policy.evaluate_action(
                proposal,
                environment="sandbox",
                decision_source="preregistered-experiment",
            )
            self.assertEqual(evaluation.decision, Decision.REQUIRE_APPROVAL)
            self.assertEqual(
                policy.evaluate_action(
                    proposal,
                    environment="live",
                    decision_source="preregistered-experiment",
                ).decision,
                Decision.REJECT,
            )


if __name__ == "__main__":
    unittest.main()
