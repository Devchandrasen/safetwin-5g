"""R3 transport, fail-closed orchestration and independent replay fixtures.

All mutations below affect temporary JSON or FakeDocker memory, never Docker.
"""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from sandbox import run_reconnect_r3 as runner
from sandbox.reconnect_r3_measurement import ping_argv, ping_result, log_text, trace_result, CORE, GNB, UE
from tests.reconnect_r3_fixture import FakeDocker, make_bundle, PREFLIGHT
from tests.test_reconnect_r3 import trace_window
from tools.audit_reconnect_r3_network import audit, raw_ping, raw_logs, raw_paths
from tools.reconnect_r3_contract import command_contract

ROOT = runner.ROOT
SINCE, UNTIL = "2026-09-05T00:00:00+00:00", "2026-09-05T00:01:00+00:00"


def ping_text(replies=range(1, 6)):
    replies = list(replies)
    return ("PING 10.45.0.1 (10.45.0.1) from 10.45.0.2 uesimtun0: 56(84) bytes of data.\n"
            + "".join(f"64 bytes from 10.45.0.1: icmp_seq={n} ttl=64 time=0.1 ms\n" for n in replies)
            + f"5 packets transmitted, {len(replies)} received, {(5-len(replies))*20}% packet loss, time 800ms\n")


def wire(rows):
    outputs = {"ue": [], "gnb": []}
    for row in rows:
        component = "gnb" if row["stage"].startswith("gnb_") else "ue"
        outputs[component].append(SINCE + " [debug] ST3 " + " ".join(f"{k}={v}" for k, v in row.items()))
    return "\n".join(outputs["ue"]), "\n".join(outputs["gnb"])


class MeasurementContractTests(unittest.TestCase):
    def test_raw_reply_counts_not_process_success(self):
        for replies in ([], [2, 3, 4, 5], [1, 2, 3, 4, 5]):
            with self.subTest(replies=replies):
                a, b = ping_result(ping_text(replies)), raw_ping(ping_text(replies))
                self.assertEqual(a, b); self.assertEqual(a["packets_received"], len(replies))

    def test_corrupt_ping_is_rejected_by_both_implementations(self):
        text = ping_text()
        bad = [text + text, text.replace("5 received", "4 received"), text.replace("0% packet loss", "20% packet loss"),
               text.replace("icmp_seq=1", "icmp_seq=2"), text.replace("icmp_seq=1", "icmp_seq=6"),
               text.replace("64 bytes from", "From"), text.replace("time=0.1 ms", "time=0.1 ms (DUP!)"),
               text.replace("5 packets transmitted", "6 packets transmitted"), text.replace("ttl=64", "ttl=bad")]
        for n, value in enumerate(bad):
            for parser in (ping_result, raw_ping):
                with self.subTest(case=n, parser=parser.__name__), self.assertRaises(ValueError): parser(value)

    def test_identifier_does_not_reuse_or_wrap(self):
        for value in (10000, 10100, -1, True, "10001"):
            with self.subTest(value=value), self.assertRaises(ValueError): ping_argv(value)
        self.assertIn("10099", ping_argv(10099))

    def test_trace_accounting_not_recovery_or_historical_localization(self):
        for idle, missing, replies in ((False, False, [1, 2, 3, 4, 5]), (True, False, [2, 3, 4, 5]),
                                       (False, True, []), (False, False, [])):
            with self.subTest(idle=idle, missing=missing, replies=replies):
                ue, gnb = wire(trace_window(idle, missing))
                a = trace_result(ue, gnb, SINCE, UNTIL, 10001, replies)
                self.assertEqual(a, raw_paths(ue, gnb, SINCE, UNTIL, 10001, replies))
                self.assertFalse(a["network_fix_validated"])
                self.assertEqual(a["all_packets_returned"], len(replies) == 5)

    def test_missing_or_duplicate_trace_never_becomes_loss_proof(self):
        variants = []
        for stage in ("nas_in", "nas_forward", "ue_rls", "gnb_in", "gnb_resource"):
            variants.append([r for r in trace_window() if not (r["seq"] == 1 and r["stage"] == stage)])
        rows = trace_window(); rows.append(copy.deepcopy(rows[0])); variants.append(rows)
        for key, value in (("fp", 999), ("id", 10002), ("bytes", 85), ("psi", 2), ("cm", 0)):
            rows = trace_window(); rows[1][key] = value; variants.append(rows)
        rows = trace_window(); rows[0], rows[1] = rows[1], rows[0]; variants.append(rows)
        for n, rows in enumerate(variants):
            for parser in (trace_result, raw_paths):
                with self.subTest(case=n, parser=parser.__name__), self.assertRaises(ValueError):
                    parser(*wire(rows), SINCE, UNTIL, 10001, [1, 2, 3, 4, 5])

    def test_idle_packet_with_reply_is_contradictory(self):
        for parser in (trace_result, raw_paths):
            with self.subTest(parser=parser.__name__), self.assertRaises(ValueError):
                parser(*wire(trace_window(True)), SINCE, UNTIL, 10001, [1, 2, 3, 4, 5])

    def test_saturated_untimestamped_and_outside_logs_rejected(self):
        bad = ["missing-timestamp", (SINCE + " line\n") * 2000, "2026-09-04T00:00:00+00:00 line",
               UNTIL + " later\n" + SINCE + " earlier"]
        for text in bad:
            for parser in (log_text, raw_logs):
                with self.subTest(parser=parser.__name__, text=text[:50]), self.assertRaises(ValueError): parser(text, SINCE, UNTIL)


class ExecutionSafetyTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="safetwin-r3-unit-"); self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.backend = FakeDocker(self.directory)

    def test_preflight_is_read_only(self):
        self.backend.preflight()
        self.assertFalse(self.backend.authorized or self.backend.candidate_touched)
        with self.assertRaises(PermissionError): self.backend.restart([UE])

    def test_command_timeout_and_os_failure_are_durable(self):
        for failure, code in ((subprocess.TimeoutExpired(["docker"], 35, output=b"partial"), -999), (OSError("fixture unavailable"), -998)):
            with self.subTest(code=code), patch.object(self.backend, "invoke", side_effect=failure), self.assertRaises(RuntimeError):
                self.backend.cmd("docker-version", ["docker", "version"])
            row = json.loads((self.directory / "commands.jsonl").read_text().splitlines()[-1])
            self.assertEqual(row["returncode"], code)

    def test_health_has_total_50_second_bound(self):
        timeouts = []
        def starting(argv, merged, timeout):
            timeouts.append(timeout); self.backend.sleep(min(20, timeout))
            return subprocess.CompletedProcess(argv, 0, b"starting\n", b"")
        with patch.object(self.backend, "invoke", side_effect=starting), self.assertRaises(TimeoutError): self.backend.health(UE)
        self.assertEqual(self.backend.monotonic(), 50)
        self.assertEqual(timeouts, [35, 28, 6])

    def test_approval_scope_cannot_expand(self):
        for key, value in (("status", "pending"), ("live_actuation", True), ("operator_validation", True),
                           ("containers", [CORE, GNB, UE, "other"]), ("image_ids", []), ("rollback_plan", "")):
            approval = copy.deepcopy(self.backend.approval); approval[key] = value
            with self.subTest(key=key), self.assertRaises(PermissionError): runner.validate_approval(approval, self.backend.config, self.backend.images)

    def test_initial_scope_cannot_silently_adopt_extra_mount_or_namespace(self):
        mutations = [lambda b: b.containers[CORE]["Mounts"].append({"Destination": "/extra", "Source": "unapproved"}),
                     lambda b: b.containers[CORE]["HostConfig"].update(Privileged=True),
                     lambda b: b.containers[UE]["HostConfig"].update(CapAdd=["CAP_SYS_ADMIN"]),
                     lambda b: b.containers[UE]["State"].update(Running=False),
                     lambda b: b.containers[UE]["NetworkSettings"]["Networks"]["safetwin5g-isolated"].update(NetworkID="wrong")]
        for n, mutate in enumerate(mutations):
            backend = FakeDocker(self.directory); mutate(backend)
            with self.subTest(case=n), self.assertRaises((PermissionError, ValueError)): backend.preflight()
            self.assertFalse(backend.authorized or backend.candidate_touched)

    def test_unknown_qdisc_is_not_deleted(self):
        with patch.object(self.backend, "eth0", return_value=[{"kind": "netem", "handle": "9999:"}]), patch.object(self.backend, "cmd") as cmd:
            with self.assertRaises(PermissionError): self.backend.clear_owned_fault()
            cmd.assert_not_called()

    def test_owned_qdisc_cleanup_is_exact(self):
        self.backend.authorized = True
        states = [[{"kind": "netem", "handle": "7157:"}], [{"kind": "noqueue", "root": True}]]
        with patch.object(self.backend, "eth0", side_effect=states), patch.object(self.backend, "cmd") as cmd:
            self.backend.clear_owned_fault()
            self.assertEqual(cmd.call_args.args[1], ["docker", "exec", UE, "tc", "qdisc", "del", "dev", "eth0", "root", "handle", "7157:"])

    def test_final_cleanup_failure_does_not_suppress_switch_or_reset(self):
        self.backend.authorized = self.backend.candidate_touched = True
        with patch.object(self.backend, "clear_owned_fault", side_effect=RuntimeError("fixture cleanup failed")), patch.object(self.backend, "switch", side_effect=RuntimeError("fixture switch failed")) as switch, patch.object(self.backend, "restart", side_effect=RuntimeError("fixture reset failed")) as restart:
            result = self.backend.final_rollback()
        switch.assert_called_once_with("official"); restart.assert_called_once_with([CORE, GNB, UE])
        self.assertEqual(len(result["errors"]), 3); self.assertFalse(result["service_restored"])

    def test_expired_admission_still_allows_safety_rollback_commands(self):
        self.backend.deadline = -1
        with self.assertRaises(TimeoutError): self.backend.eth0("preflight-eth0")
        self.backend.restoring = True
        self.assertTrue(self.backend.eth0("rollback-inspect-eth0"))

    def test_empty_lock_is_rejected_before_git_or_execution(self):
        path = self.directory / "lock.json"; runner.save(path, {"lock_id": "reconnect-r3-execution-v1", "source_sha256": {}})
        with patch.object(runner, "LOCK_PATH", path), patch.object(subprocess, "run") as shell, self.assertRaises(PermissionError): runner.verify_execution_lock()
        shell.assert_not_called()

    def test_uncommitted_lock_is_rejected(self):
        with patch.object(subprocess, "run", return_value=subprocess.CompletedProcess([], 1, b"", b"")), self.assertRaisesRegex(PermissionError, "not committed"):
            runner.verify_execution_lock()

    def test_fixed_command_contract_matches_implementation(self):
        self.assertEqual(command_contract(), json.loads((ROOT / "config/experiments/reconnect-r3-command-contract.json").read_bytes()))

    def test_cli_without_execute_cannot_invoke_docker(self):
        with patch("sys.argv", ["run_reconnect_r3.py"]), patch.object(subprocess, "run") as shell, self.assertRaisesRegex(SystemExit, "No mutation by default"):
            runner.main()
        shell.assert_not_called()

    def test_restoration_preserves_failed_ue_step_before_full_reset(self):
        metrics = {"packets_transmitted": 5, "packets_received": 5, "packet_loss_pct": 0,
                   "configured_packet_loss_pct": 0, "upf_process_running": 1, "stress_workers_count": 0, "prometheus_targets_up_count": 3}
        good = [{"errors": [], "metrics": dict(metrics)} for _ in range(3)]
        bad = copy.deepcopy(good); bad[0]["metrics"]["packets_received"] = 0
        logs = {UE: "Initial Registration is successful\nPDU Session establishment is successful"}
        with patch.object(self.backend, "restart") as restart, patch.object(self.backend, "window", side_effect=[bad, good]), patch.object(self.backend, "logs", return_value=logs), patch.object(self.backend, "eth0", return_value=[{"kind": "noqueue", "root": True}]):
            attempts = self.backend.restore()
        self.assertEqual([row["step"] for row in attempts], ["restore-ue", "restore-full"])
        self.assertEqual([row["clean"] for row in attempts], [False, True])
        self.assertEqual([call.args[0] for call in restart.call_args_list], [[UE], [CORE, GNB, UE]])


class IndependentBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="safetwin-r3-replay-")
        cls.complete = Path(cls.temp.name) / "complete"
        with patch.object(subprocess, "run", side_effect=AssertionError("fixture attempted real I/O")):
            cls.result = make_bundle(cls.complete)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def copied(self):
        temp = tempfile.TemporaryDirectory(prefix="safetwin-r3-tamper-"); self.addCleanup(temp.cleanup)
        target = Path(temp.name) / "run"; shutil.copytree(self.complete, target); return target

    def reseal(self, target):
        runner.save(target / "manifest.json", {"captured_file_sha256": {p.name: runner.sha(p.read_bytes()) for p in target.iterdir() if p.is_file() and p.name != "manifest.json"}})

    def change(self, target, name, mutate):
        value = json.loads((target / name).read_bytes()); mutate(value); runner.save(target / name, value); self.reseal(target)

    def commands(self, target, mutate):
        rows = [json.loads(line) for line in (target / "commands.jsonl").read_text().splitlines()]; mutate(rows)
        for row in rows:
            for stream in ("stdout", "stderr"): row[stream + "_sha256"] = runner.sha(row[stream].encode())
        (target / "commands.jsonl").write_bytes("".join(json.dumps(row) + "\n" for row in rows).encode()); self.reseal(target)

    def test_complete_fake_transport_replays_but_is_not_network_evidence(self):
        result = audit(self.complete, allow_fixture=True)
        self.assertEqual((result["commands_replayed"], result["samples_replayed"], result["scope_snapshots"]), (354, 33, 8))
        self.assertEqual([row["received"] for row in result["post_packet_counts"]], [15, 14, 14, 15])
        self.assertTrue(result["protocol_execution_valid"]); self.assertFalse(result["network_fix_validated"])
        self.assertEqual(result["evidence_label"], "fixture")
        with self.assertRaisesRegex(ValueError, "fixture cannot pass"): audit(self.complete)

    def test_incomplete_runs_stop_without_replacement_and_restore_official(self):
        for mode, trials, faults in (("bad-baseline", 1, 0), ("incomplete-trace", 2, 1), ("failed-switch", 0, 0)):
            target = Path(self.temp.name) / mode
            with self.subTest(mode=mode), patch.object(subprocess, "run", side_effect=AssertionError("real I/O")):
                result = make_bundle(target, mode)
            self.assertFalse(result["protocol_execution_valid"])
            self.assertEqual(result["completed_trials"], trials)
            self.assertTrue(result["official_image_restored"] and result["final_service_restored"])
            commands = [json.loads(line) for line in (target / "commands.jsonl").read_text().splitlines()]
            self.assertEqual(sum(row["name"] == "bounded-link-drop" for row in commands), faults)
            self.assertEqual([row["name"] for row in commands if row["name"] in ("switch-derived", "switch-official")], ["switch-derived", "switch-official"])
            with self.assertRaises(ValueError): audit(target, allow_fixture=True)

    def test_unmanifested_file_is_rejected(self):
        target = self.copied(); (target / "extra.txt").write_bytes(b"not retained")
        with self.assertRaisesRegex(ValueError, "artifact inventory"): audit(target, True)

    def test_claim_or_transport_promotion_rejected(self):
        for key in ("network_fix_validated", "TNSM_ready", "live_actuation", "operator_validated", "hardware_measured", "confirmatory_data", "long_campaign_ready"):
            target = self.copied(); self.change(target, "summary.json", lambda row: row.update({key: True}))
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "claim promotion"): audit(target, True)
        target = self.copied(); self.change(target, "design.json", lambda row: row.update(transport="docker-cli"))
        with self.assertRaisesRegex(ValueError, "transport"): audit(target, True)

    def test_empty_source_inventory_rejected(self):
        target = self.copied(); self.change(target, "design.json", lambda row: row.update(source_sha256={}))
        with self.assertRaisesRegex(ValueError, "execution inventory"): audit(target, True)

    def test_extra_privilege_warmup_or_long_timeout_rejected_with_valid_hashes(self):
        for mode in ("privilege", "warmup", "timeout"):
            target = self.copied()
            def mutate(rows):
                row = next(r for r in rows if r["name"] == "service-ping")
                if mode == "privilege": row["argv"].insert(2, "--privileged")
                elif mode == "warmup": row["name"] = "warmup-ping"
                else: row["timeout_seconds"] = 100
            self.commands(target, mutate)
            with self.subTest(mode=mode), self.assertRaises(ValueError): audit(target, True)

    def test_scope_attachment_tampering_rejected_with_valid_hashes(self):
        target = self.copied()
        def mutate(rows):
            row = next(r for r in rows if r["name"] == "preflight-network")
            data = json.loads(row["stdout"]); key = next(iter(data[0]["Containers"]))
            data[0]["Containers"]["different-id"] = data[0]["Containers"].pop(key); row["stdout"] = json.dumps(data)
        self.commands(target, mutate)
        with self.assertRaisesRegex(ValueError, "attachment identity"): audit(target, True)

    def test_retained_instrumentation_image_cannot_be_reported_restored(self):
        target = self.copied()
        def mutate(rows):
            row = next(r for r in rows if r["name"] == "final-official-containers")
            containers = [json.loads(line) for line in row["stdout"].splitlines()]
            next(c for c in containers if c["Name"] == "/" + UE)["Image"] = "sha256:unrestored"
            row["stdout"] = "\n".join(json.dumps(c) for c in containers) + "\n"
        self.commands(target, mutate)
        with self.assertRaisesRegex(ValueError, "selected image"): audit(target, True)

    def test_recovery_flag_cannot_turn_14_into_15(self):
        target = self.copied(); self.change(target, "trial-02.json", lambda row: row.update(recovery_15_of_15=True))
        with self.assertRaisesRegex(ValueError, "recovery versus trace"): audit(target, True)

    def test_fault_duration_cannot_be_retuned(self):
        target = self.copied()
        def mutate(rows): next(r for r in rows if r["name"] == "bounded-link-drop")["argv"][-1] += "\nsleep 1"
        self.commands(target, mutate)
        with self.assertRaisesRegex(ValueError, "fixed command scope"): audit(target, True)

    def test_identifier_reuse_rejected(self):
        target = self.copied()
        rows = [json.loads(line) for line in (target / "samples.jsonl").read_text().splitlines()]; rows[1]["identifier"] = rows[0]["identifier"]
        (target / "samples.jsonl").write_bytes("".join(json.dumps(row) + "\n" for row in rows).encode()); self.reseal(target)
        with self.assertRaisesRegex(ValueError, "identifier reuse"): audit(target, True)

    def test_failed_preflight_sources_remain_recoverable(self):
        archive = ROOT / "evidence/engineering/20260905T122339Z-reconnect-r3-preflight-source-archive"
        for n, name in enumerate(("20260905T122202Z", "20260905T122302Z", "20260905T122339Z"), 1):
            directory = PREFLIGHT.parent / (name + "-reconnect-r3-preflight")
            summary = json.loads((directory / "summary.json").read_bytes())
            self.assertEqual(summary["preflight_passed"], n == 3)
            self.assertFalse(summary["mutation_enabled"] or summary["candidate_image_applied"])
            for source, digest in json.loads((directory / "source-hashes.json").read_bytes()).items():
                self.assertEqual(runner.sha((archive / (f"preflight-{n}-" + source.replace("/", "-"))).read_bytes()), digest)


if __name__ == "__main__": unittest.main()
