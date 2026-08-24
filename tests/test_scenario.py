import unittest

from safetwin5g.scenario import ScenarioRunner, ScenarioSpec


def valid_spec():
    return ScenarioSpec.from_dict(
        {
            "scenario_id": "packet-loss-001",
            "environment": "sandbox",
            "seed": 1,
            "fault_family": "packet_loss",
            "fault_parameters": {"loss_pct": 25},
            "action_kind": "network_impairment_clear",
            "target": "safetwin5g-ue/uesimtun0",
            "rollback_required": True,
        }
    )


class FakeBackend:
    def __init__(self, fail_action=False):
        self.events = []
        self.loss = 0.0
        self.fail_action = fail_action

    def observe(self, stage):
        self.events.append(f"observe:{stage}")
        return {"packet_loss_pct": self.loss}

    def inject_fault(self, spec):
        self.events.append("inject")
        self.loss = float(spec.fault_parameters["loss_pct"])

    def apply_action(self, spec):
        self.events.append("action")
        if self.fail_action:
            raise RuntimeError("action failed")
        self.loss = 0.0

    def rollback_action(self, spec):
        self.events.append("rollback")
        self.loss = float(spec.fault_parameters["loss_pct"])

    def cleanup(self, spec):
        self.events.append("cleanup")
        self.loss = 0.0


APPROVAL = {
    "approval_status": "approved",
    "approval_id": "test-approval-001",
    "environment": "sandbox",
}


class ScenarioTests(unittest.TestCase):
    def test_runner_uses_fixed_order_and_cleanup(self):
        backend = FakeBackend()
        trace = ScenarioRunner(backend).run(valid_spec(), APPROVAL)
        self.assertTrue(trace.passed)
        self.assertTrue(trace.cleanup_verified)
        self.assertEqual(
            backend.events,
            [
                "observe:baseline", "inject", "observe:fault", "action",
                "observe:post-action", "rollback", "observe:rollback",
                "cleanup", "observe:final",
            ],
        )

    def test_runner_cleans_up_after_action_failure(self):
        backend = FakeBackend(fail_action=True)
        with self.assertRaisesRegex(RuntimeError, "action failed"):
            ScenarioRunner(backend).run(valid_spec(), APPROVAL)
        self.assertEqual(backend.events[-2:], ["cleanup", "observe:final"])
        self.assertEqual(backend.loss, 0.0)

    def test_runner_rejects_missing_approval_before_backend_use(self):
        backend = FakeBackend()
        with self.assertRaisesRegex(PermissionError, "approval"):
            ScenarioRunner(backend).run(valid_spec(), {"approval_status": "pending"})
        self.assertEqual(backend.events, [])

    def test_spec_rejects_live_environment(self):
        with self.assertRaisesRegex(ValueError, "sandbox"):
            ScenarioSpec.from_dict(
                {
                    "scenario_id": "unsafe",
                    "environment": "live",
                    "seed": 1,
                    "fault_family": "packet_loss",
                    "action_kind": "network_impairment_clear",
                    "target": "external",
                }
            )


if __name__ == "__main__":
    unittest.main()
