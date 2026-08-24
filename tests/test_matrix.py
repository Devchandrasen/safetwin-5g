import json
from pathlib import Path
import unittest

from safetwin5g.safety import Decision, SafetyPolicy
from sandbox.run_matrix import action_for, expand_matrix, validate_trace


ROOT = Path(__file__).resolve().parents[1]


class MatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads(
            (ROOT / "config" / "scenarios" / "matrix-v0.json").read_text(
                encoding="utf-8"
            )
        )
        cls.specs = expand_matrix(cls.config)
        cls.policy = SafetyPolicy.from_path(ROOT / "config" / "actions.json")

    def test_matrix_has_three_families_two_severities_and_two_seeds(self):
        self.assertEqual(len(self.specs), 12)
        self.assertEqual(len({spec.fault_family for spec in self.specs}), 3)
        for family in self.config["families"]:
            self.assertEqual(len(family["severities"]), 2)
            self.assertEqual(len(family["seeds"]), 2)

    def test_every_matrix_action_is_reversible_sandbox_only_and_requires_approval(self):
        for spec in self.specs:
            action = action_for(spec)
            self.assertTrue(action.reversible)
            result = self.policy.evaluate_action(
                action,
                environment="sandbox",
                decision_source="deterministic-runbook",
            )
            self.assertEqual(result.decision, Decision.REQUIRE_APPROVAL)

    def test_trace_validation_does_not_require_cpu_fault_to_harm_user_plane(self):
        spec = next(spec for spec in self.specs if spec.fault_family == "cpu_saturation")
        workers = float(spec.fault_parameters["workers"])
        trace = {
            "passed": True,
            "cleanup_verified": True,
            "stages": [
                {"stage": "baseline", "metrics": {"packet_loss_pct": 0.0}},
                {"stage": "fault", "metrics": {"packet_loss_pct": 0.0, "stress_workers_count": workers}},
                {"stage": "post-action", "metrics": {"packet_loss_pct": 0.0}},
                {"stage": "rollback", "metrics": {"packet_loss_pct": 0.0, "stress_workers_count": workers}},
                {
                    "stage": "final",
                    "metrics": {
                        "packet_loss_pct": 0.0,
                        "upf_process_running": 1.0,
                        "stress_workers_count": 0.0,
                    },
                },
            ],
        }
        self.assertTrue(all(validate_trace(spec, trace).values()))

    def test_packet_fault_uses_control_state_not_noisy_point_estimate(self):
        spec = next(
            spec
            for spec in self.specs
            if spec.fault_family == "packet_impairment"
            and spec.fault_parameters["loss_pct"] == 25
        )
        trace = {
            "passed": True,
            "cleanup_verified": True,
            "stages": [
                {"stage": "baseline", "metrics": {"packet_loss_pct": 0.0}},
                {
                    "stage": "fault",
                    "metrics": {
                        "packet_loss_pct": 10.0,
                        "configured_packet_loss_pct": 25.0,
                    },
                },
                {"stage": "post-action", "metrics": {"packet_loss_pct": 0.0}},
                {
                    "stage": "rollback",
                    "metrics": {
                        "packet_loss_pct": 10.0,
                        "configured_packet_loss_pct": 25.0,
                    },
                },
                {
                    "stage": "final",
                    "metrics": {
                        "packet_loss_pct": 0.0,
                        "upf_process_running": 1.0,
                        "stress_workers_count": 0.0,
                    },
                },
            ],
        }
        self.assertTrue(all(validate_trace(spec, trace).values()))


if __name__ == "__main__":
    unittest.main()
