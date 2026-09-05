from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from sandbox.run_reconnect import (CORE, GNB, UE, CONFIG, FAULT_SCRIPT, ReconnectBackend,
                                   noqueue, classify, run_trial, validate_config)
from tests.test_recovery_pilot import good_samples
from tools.audit_reconnect import verify_exposure_timing


class FakeBackend:
    deadline = float("inf")
    restoring = False

    def __init__(self, bad_baseline=False, command_error=False, bad_restore=False, automatic=False):
        self.events = []
        self.bad_baseline, self.command_error = bad_baseline, command_error
        self.bad_restore, self.automatic = bad_restore, automatic
        self.drop = False

    def eth0(self, label):
        self.events.append(label)
        return [{"kind": "noqueue", "root": True}]

    def restart(self, containers):
        self.events.append(tuple(containers))

    def window(self, label):
        self.events.append(label)
        rows = good_samples()
        if (label == "baseline" and self.bad_baseline) or (label == "post" and self.drop and not self.automatic):
            for row in rows:
                row["metrics"].update(packet_loss_pct=100, packets_received=0)
        return rows

    def logs(self, label, since):
        if label == "post":
            return {UE: "Radio link failure detected; Sending Service Request" if self.drop and not self.automatic else "",
                    GNB: "AMF selection failed. Could not find a suitable AMF. Uplink data failure, PDU session not found." if self.drop and not self.automatic else ""}
        return {UE: "Initial Registration is successful; PDU Session establishment is successful"}

    def cmd(self, name, argv):
        self.events.append(name)
        if name == "bounded-link-drop":
            self.drop = True
            if self.command_error:
                raise RuntimeError("fixture timeout")
        return "fixture"

    def clear_owned_fault(self):
        self.events.append("rollback")

    def restore(self):
        self.events.append("restore")
        return [{"clean": not self.bad_restore}]


class ReconnectTests(unittest.TestCase):
    def run_case(self, backend, drop=True):
        trial = {"trial_id": "fixture", "drop_ue_egress": drop}
        approval = {"approval_id": "fixture", "status": "approved", "environment": "sandbox",
                    "trials": [trial], "containers": [CORE, GNB, UE], "rollback_plan": "fixture"}
        with patch("sandbox.run_reconnect.time.sleep"):
            return run_trial(backend, trial, approval)

    def test_invalid_baseline_never_injects_and_still_restores(self):
        backend = FakeBackend(bad_baseline=True)
        row = self.run_case(backend)
        self.assertFalse(row["protocol_execution_valid"])
        self.assertNotIn("bounded-link-drop", backend.events)
        self.assertIn("restore", backend.events)

    def test_command_exception_always_rolls_back_before_restoring(self):
        backend = FakeBackend(command_error=True)
        row = self.run_case(backend)
        self.assertFalse(row["protocol_execution_valid"])
        self.assertLess(backend.events.index("rollback"), backend.events.index("restore"))

    def test_failed_final_restoration_blocks_execution_acceptance(self):
        self.assertFalse(self.run_case(FakeBackend(bad_restore=True))["protocol_execution_valid"])

    def test_reproduced_fault_is_not_mislabelled_automatic_recovery(self):
        row = self.run_case(FakeBackend())
        self.assertTrue(row["protocol_execution_valid"])
        self.assertTrue(row["reconnect_failure_reproduced"])
        self.assertFalse(row["automatic_service_recovered"])

    def test_nonreproduction_is_valid_observation_not_invented_failure(self):
        row = self.run_case(FakeBackend(automatic=True))
        self.assertTrue(row["protocol_execution_valid"])
        self.assertFalse(row["reconnect_failure_reproduced"])

    def test_control_has_no_fault_or_post_restart(self):
        backend = FakeBackend()
        row = self.run_case(backend, drop=False)
        self.assertTrue(row["protocol_execution_valid"])
        self.assertNotIn("bounded-link-drop", backend.events)
        self.assertNotIn("restore", backend.events)

    def test_unapproved_target_never_touches_backend(self):
        backend = FakeBackend()
        with self.assertRaises(PermissionError):
            run_trial(backend, {"trial_id": "fixture"}, {})
        self.assertEqual(backend.events, [])

    def test_unknown_qdisc_is_never_deleted(self):
        class Unknown:
            def eth0(self, label):
                return [{"kind": "netem", "handle": "99:"}]
            def cmd(self, *args):
                raise AssertionError("must not mutate")
        with self.assertRaisesRegex(RuntimeError, "unknown eth0"):
            ReconnectBackend.clear_owned_fault(Unknown())

    def test_protocol_bounds_and_rollback_script_are_fixed(self):
        config = json.loads(CONFIG.read_text())
        validate_config(config)
        with self.assertRaises(PermissionError):
            validate_config({**config, "exposure_seconds": 300})
        self.assertIn("trap cleanup EXIT", FAULT_SCRIPT)
        self.assertIn("sleep 8", FAULT_SCRIPT)
        self.assertIn("handle 7157:", FAULT_SCRIPT)

    def test_reproduction_needs_service_failure_not_only_log_keywords(self):
        observation = classify(good_samples(), "Radio link failure detected; Sending Service Request",
                               "failed. Could not find a suitable AMF. Uplink data failure, PDU session not found.")
        self.assertFalse(all(observation.values()))
        self.assertFalse(noqueue([]))

    def test_auditor_rejects_short_exposure_and_missing_settle(self):
        row = {"exposure_started_at": "2026-09-05T06:00:00+00:00",
               "exposure_completed_at": "2026-09-05T06:00:09+00:00",
               "post": [{"observed_at": "2026-09-05T06:00:14+00:00"}]}
        command = {"started_at": "2026-09-05T06:00:00+00:00",
                   "completed_at": "2026-09-05T06:00:08+00:00"}
        verify_exposure_timing(row, command)
        with self.assertRaisesRegex(ValueError, "exposure command interval"):
            verify_exposure_timing(row, {**command, "completed_at": "2026-09-05T06:00:07+00:00"})
        with self.assertRaisesRegex(ValueError, "settling interval"):
            verify_exposure_timing({**row, "post": [{"observed_at": "2026-09-05T06:00:13+00:00"}]}, command)


if __name__ == "__main__":
    unittest.main()
