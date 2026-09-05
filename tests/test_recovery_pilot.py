from copy import deepcopy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from sandbox.run_recovery_pilot import (
    Backend, CORE, GNB, UE, CONTAINERS, NETWORK, run_trial,
    samples_clean, validate_config, validate_environment,
)
from tools.audit_recovery_pilot import replay_sample

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/experiments/recovery-pilot-r1.json").read_text())
VERSIONS = json.loads((ROOT / "sandbox/versions.lock.json").read_text())["components"]


def good_samples():
    return [{"metrics": {"packets_transmitted": 5, "packets_received": 5,
        "packet_loss_pct": 0.0, "configured_packet_loss_pct": 0.0,
        "upf_process_running": 1, "stress_workers_count": 0,
        "prometheus_targets_up_count": 3}} for _ in range(3)]


def approval(hold):
    return {"approval_id": "fixture-approval", "status": "approved",
            "environment": "sandbox", "trial_ids": ["fixture-trial"],
            "trial_holds": {"fixture-trial": hold}, "containers": [CORE, GNB, UE],
            "rollback_plan": "fixture restoration"}


class FakeBackend:
    config = CONFIG
    deadline = float("inf")
    restoring = False
    recovery = Backend.recovery

    def __init__(self, bad_baseline=False, bad_steps=(), fail_stop=False, fail_watchdog=False):
        self.events = []
        self.bad_baseline, self.bad_steps = bad_baseline, bad_steps
        self.fail_stop, self.fail_watchdog = fail_stop, fail_watchdog

    def neutralize(self):
        self.events.append("neutralize")

    def window(self, label):
        self.events.append(label)
        rows = good_samples()
        if (label == "baseline" and self.bad_baseline) or label in self.bad_steps:
            rows[0]["metrics"]["packets_received"] = 0
            rows[0]["metrics"]["packet_loss_pct"] = 100
        return rows

    def shell(self, name, command):
        self.events.append(name)
        return "19" if name == "locate-upf" else "T"

    def cmd(self, name, argv):
        self.events.append(name)
        if name == "suspend-upf" and self.fail_stop:
            raise RuntimeError("fixture STOP timeout")
        return ""

    def arm_watchdog(self, pid):
        self.events.append("watchdog-arm")
        return {"fixture": True}

    def settle_watchdog(self, watchdog):
        self.events.append("watchdog-settle")
        if self.fail_watchdog:
            raise RuntimeError("fixture watchdog fired")
        return "disarmed"

    def restart(self, containers):
        self.events.append(tuple(containers))


class RecoveryPilotTests(unittest.TestCase):
    def run_case(self, backend, hold=1):
        with patch("sandbox.run_recovery_pilot.time.sleep"):
            return run_trial(backend, {"trial_id": "fixture-trial", "hold_seconds": hold}, approval(hold))

    def test_service_gate_requires_all_packets_samples_and_targets(self):
        self.assertTrue(samples_clean(good_samples()))
        self.assertFalse(samples_clean(good_samples()[:2]))
        for metric, value in (("packets_received", 4), ("packet_loss_pct", float("nan")),
                              ("prometheus_targets_up_count", 2), ("stress_workers_count", 1)):
            with self.subTest(metric=metric):
                rows = good_samples()
                rows[1]["metrics"][metric] = value
                self.assertFalse(samples_clean(rows))

    def test_unapproved_trial_never_touches_backend(self):
        backend = FakeBackend()
        auth = approval(1)
        auth["trial_holds"]["fixture-trial"] = 30
        with self.assertRaises(PermissionError):
            run_trial(backend, {"trial_id": "fixture-trial", "hold_seconds": 1}, auth)
        self.assertEqual(backend.events, [])

    def test_invalid_baseline_blocks_stop_and_still_recovers(self):
        backend = FakeBackend(bad_baseline=True)
        row = self.run_case(backend)
        self.assertFalse(row["passed"])
        self.assertTrue(row["recovery_clean"])
        self.assertNotIn("suspend-upf", backend.events)

    def test_stop_exception_still_attempts_cont_and_watchdog_barrier(self):
        backend = FakeBackend(fail_stop=True)
        row = self.run_case(backend)
        self.assertFalse(row["passed"])
        self.assertLess(backend.events.index("primary-resume-upf"), backend.events.index("watchdog-settle"))

    def test_watchdog_failure_cannot_become_passing_trial(self):
        row = self.run_case(FakeBackend(fail_watchdog=True))
        self.assertFalse(row["passed"])
        self.assertTrue(row["recovery_clean"])

    def test_escalation_preserves_all_failed_probes(self):
        backend = FakeBackend(bad_steps=("primitive_cleanup", "ue_restart"))
        row = self.run_case(backend)
        self.assertTrue(row["passed"])
        self.assertEqual([r["clean"] for r in row["recovery_attempts"]], [False, False, True])
        self.assertIn((UE,), backend.events)
        self.assertIn((CORE, GNB, UE), backend.events)
        self.assertLess(backend.events.index("watchdog-settle"), backend.events.index((UE,)))

    def test_no_fault_control_fails_if_it_requires_restart(self):
        row = self.run_case(FakeBackend(bad_steps=("primitive_cleanup",)), hold=0)
        self.assertFalse(row["passed"])
        self.assertTrue(row["recovery_clean"])

    def test_no_fault_control_never_stops_upf(self):
        backend = FakeBackend()
        self.assertTrue(self.run_case(backend, hold=0)["passed"])
        self.assertNotIn("suspend-upf", backend.events)

    def test_expired_budget_blocks_new_fault_but_not_restoration(self):
        backend = FakeBackend()
        backend.deadline = 0
        row = self.run_case(backend)
        self.assertFalse(row["passed"])
        self.assertTrue(row["recovery_clean"])
        self.assertNotIn("suspend-upf", backend.events)

    def test_live_policy_or_changed_protocol_is_rejected(self):
        policy = {"allow_live_actuation": False, "require_human_approval": True}
        validate_config(CONFIG, policy)
        with self.assertRaises(PermissionError):
            validate_config(CONFIG, {**policy, "allow_live_actuation": True})
        with self.assertRaises(PermissionError):
            validate_config({**CONFIG, "trial_hold_seconds": [45]}, policy)

    def test_environment_gate_rejects_unisolated_or_wrong_project(self):
        network = {"Name": NETWORK, "Internal": True,
                   "Labels": {"com.docker.compose.project": "safetwin5g-sandbox"},
                   "Containers": {str(i): {"Name": n} for i, n in enumerate(CONTAINERS)}}
        containers = []
        for name in CONTAINERS:
            component = "open5gs" if name == CORE else "ueransim" if name in (UE, GNB) else "mongodb" if name.endswith("mongodb") else "prometheus"
            containers.append({"Name": "/" + name,
                "Config": {"Labels": {"com.docker.compose.project": "safetwin5g-sandbox", "safetwin5g.upstream.commit": VERSIONS[component].get("commit")},
                           "Image": "fixture@" + VERSIONS[component].get("digest", "fixture")},
                "NetworkSettings": {"Networks": {NETWORK: {}}},
                "HostConfig": {"PortBindings": {}, "Privileged": False},
                "State": {"Health": {"Status": "healthy"}}})
        validate_environment(network, containers, VERSIONS)
        with self.assertRaises(PermissionError):
            validate_environment({**network, "Internal": False}, containers, VERSIONS)
        bad = deepcopy(containers)
        bad[0]["NetworkSettings"]["Networks"]["other"] = {}
        with self.assertRaises(PermissionError):
            validate_environment(network, bad, VERSIONS)

    def test_independent_replay_does_not_trust_reported_loss(self):
        outputs = ["5 packets transmitted, 5 received, 0% packet loss", "qdisc fq_codel 0: root", "Sl\n", "",
                   json.dumps({"data": {"activeTargets": [{"labels": {"job": j}, "health": "up"} for j in ("open5gs-amf", "open5gs-smf", "open5gs-upf")]}})]
        names = ["service-ping", "qdisc", "upf-state", "stress-workers", "targets"]
        commands = {i: {"name": n, "stdout": out, "returncode": 0} for i, (n, out) in enumerate(zip(names, outputs), 1)}
        sample = {**good_samples()[0], "command_sequences": [1, 2, 3, 4, 5]}
        self.assertTrue(replay_sample(sample, commands))
        commands[1]["stdout"] = "5 packets transmitted, 0 received, 100% packet loss"
        with self.assertRaisesRegex(ValueError, "raw ping differs"):
            replay_sample(sample, commands)


if __name__ == "__main__":
    unittest.main()
