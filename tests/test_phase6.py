from copy import deepcopy
from pathlib import Path
import unittest

from safetwin5g.experiment import expand_design, load_design
from safetwin5g.phase6 import (
    Phase6UnitRunner,
    negative_control_loss,
    summarize_window,
)
from safetwin5g.safety import Decision, SafetyPolicy
from sandbox.run_phase6 import action_proposal, build_approval


ROOT = Path(__file__).resolve().parents[1]
DESIGN = load_design(ROOT / "config" / "experiments" / "phase6-v1.json")
UNITS = expand_design(DESIGN)


def unit_for(family, arm):
    return deepcopy(
        next(
            unit
            for unit in UNITS
            if unit["fault_family"] == family and unit["action_arm"] == arm
        )
    )


class FakeBackend:
    def __init__(self, samples=3, fail_action=False, fail_cleanup=False):
        self.samples = samples
        self.fail_action = fail_action
        self.fail_cleanup = fail_cleanup
        self.events = []
        self.loss = 0.0
        self.upf = 1.0
        self.workers = 0.0

    def reset(self, unit):
        self.events.append("reset")
        self.loss = 0.0
        self.upf = 1.0
        self.workers = 0.0

    def observe_window(self, stage, unit):
        self.events.append(f"observe:{stage}")
        return [
            {
                "sample_index": index,
                "observed_at": f"2026-08-24T00:00:0{index}+00:00",
                "metrics": {
                    "configured_packet_loss_pct": self.loss,
                    "packet_loss_pct": self.loss,
                    "upf_process_running": self.upf,
                    "stress_workers_count": self.workers,
                },
            }
            for index in range(1, self.samples + 1)
        ]

    def inject_fault(self, unit):
        self.events.append("inject")
        if unit["fault_family"] == "packet_impairment":
            self.loss = float(unit["severity_value"])
        elif unit["fault_family"] == "network_function_interruption":
            self.upf = 0.0
        elif unit["fault_family"] == "cpu_saturation":
            self.workers = float(unit["severity_value"])

    def apply_action(self, unit):
        self.events.append("action")
        if self.fail_action:
            raise RuntimeError("action failed")
        if unit["action_arm"] == "effective":
            if unit["fault_family"] == "packet_impairment":
                self.loss = 0.0
            elif unit["fault_family"] == "network_function_interruption":
                self.upf = 1.0
            elif unit["fault_family"] == "cpu_saturation":
                self.workers = 0.0
        elif unit["action_arm"] == "negative_control":
            self.loss = negative_control_loss(unit)

    def cleanup(self, unit):
        self.events.append("cleanup")
        if self.fail_cleanup:
            raise RuntimeError("cleanup failed")
        self.loss = 0.0
        self.upf = 1.0
        self.workers = 0.0


class Phase6RunnerTests(unittest.TestCase):
    def setUp(self):
        self.approval = build_approval(DESIGN, UNITS)

    def test_effective_no_action_and_negative_control_units_pass(self):
        cases = (
            unit_for("network_function_interruption", "effective"),
            unit_for("cpu_saturation", "no_action"),
            unit_for("no_fault", "negative_control"),
        )
        for unit in cases:
            with self.subTest(unit=unit["unit_id"]):
                trace = Phase6UnitRunner(FakeBackend(), 3).run(unit, self.approval)
                self.assertTrue(trace["passed"], trace)
                self.assertTrue(trace["cleanup_verified"])

    def test_action_failure_still_cleans_up_and_fails_unit(self):
        backend = FakeBackend(fail_action=True)
        trace = Phase6UnitRunner(backend, 3).run(
            unit_for("packet_impairment", "effective"), self.approval
        )
        self.assertFalse(trace["passed"])
        self.assertTrue(trace["cleanup_verified"])
        self.assertEqual(backend.events[-2:], ["cleanup", "observe:recovery"])
        self.assertRegex(trace["errors"][0], "action failed")

    def test_cleanup_failure_is_fail_closed(self):
        trace = Phase6UnitRunner(FakeBackend(fail_cleanup=True), 3).run(
            unit_for("no_fault", "no_action"), self.approval
        )
        self.assertFalse(trace["passed"])
        self.assertFalse(trace["cleanup_verified"])
        self.assertRegex(" ".join(trace["errors"]), "cleanup failed")

    def test_missing_approval_prevents_backend_use(self):
        backend = FakeBackend()
        with self.assertRaisesRegex(PermissionError, "approval"):
            Phase6UnitRunner(backend, 3).run(
                unit_for("packet_impairment", "effective"),
                {"approval_status": "pending"},
            )
        self.assertEqual(backend.events, [])

    def test_windows_report_distribution_and_missingness(self):
        summary = summarize_window(
            [
                {"metrics": {"x": 1.0, "y": None}},
                {"metrics": {"x": 2.0, "y": 4.0}},
                {"metrics": {"x": 9.0, "y": 6.0}},
            ]
        )
        self.assertEqual(summary["metrics"]["x"]["median"], 2.0)
        self.assertEqual(summary["metrics"]["x"]["p75"], 5.5)
        self.assertEqual(summary["metrics"]["y"]["missing"], 1)

    def test_every_mutating_action_is_allowlisted_and_requires_approval(self):
        policy = SafetyPolicy.from_path(ROOT / "config" / "actions.json")
        seen = set()
        for unit in UNITS:
            proposal = action_proposal(unit)
            if proposal is None:
                continue
            seen.add(proposal.kind)
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
        self.assertEqual(
            seen,
            {
                "network_impairment_clear",
                "network_impairment_apply",
                "nf_process_resume",
                "cpu_stress_stop",
            },
        )


if __name__ == "__main__":
    unittest.main()
