import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tests.reconnect_r4_execution_fixture import make_bundle
from sandbox.run_reconnect_r4 import CORE, GNB, UE, main, validate_approval, approval_expected, sha, allowed_commands
from tools.audit_reconnect_r4_execution import audit


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        for name in ("subprocess.Popen", "socket.socket"):
            guard = patch(name, side_effect=AssertionError("network/process disabled in protocol fixture"))
            guard.start()
            self.addCleanup(guard.stop)

    def bundle(self, case):
        temporary = tempfile.TemporaryDirectory(prefix="safetwin-r4-execution-")
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name) / "bundle"
        result = make_bundle(output, case)
        replay = audit(output, allow_fixture=True, allow_unfrozen_fixture=True)
        self.assertTrue(replay["observation_audit_passed"])
        self.assertEqual(replay["protocol_execution_valid"], result["protocol_execution_valid"])
        return output, result

    def test_complete_protocol_keeps_drop_loss_and_official_rollback_separate(self):
        output, result = self.bundle("complete")
        self.assertTrue(result["protocol_execution_valid"], result)
        self.assertTrue(result["final_service_restored"])
        self.assertFalse(result["network_fix_validated"])
        trials = [json.loads(p.read_bytes()) for p in sorted(output.glob("trial-*.json"))]
        self.assertEqual([sum(s["result"]["ping"]["packets_received"] for s in t["post"]) for t in trials], [15, 14, 14, 15])

    def test_negative_prefixes_stop_and_attempt_official_restoration(self):
        for case in ("bad-baseline", "ineligible-source", "incomplete-trace", "failed-switch", "timeout", "missing-fresh-pdu", "window-budget"):
            with self.subTest(case=case):
                output, result = self.bundle(case)
                self.assertFalse(result["protocol_execution_valid"], result)
                self.assertTrue(result["official_image_restored"] and result["final_service_restored"], result)
                self.assertLess(result["attempted_assignments"], 4)

    def test_final_rollback_failures_are_not_success_and_each_reset_is_attempted(self):
        for case in ("failed-final-switch", "failed-cleanup", "failed-reset", "failed-health", "failed-official-service", "stale-official-trace"):
            with self.subTest(case=case):
                output, result = self.bundle(case)
                self.assertFalse(result["protocol_execution_valid"] or result["final_service_restored"], result)
                rows = [json.loads(line) for line in (output / "commands.jsonl").read_text().splitlines()]
                resets = [r["argv"][2] for r in rows if r["unit_id"] == "final-rollback" and r["argv"][:2] == ["docker", "restart"]]
                self.assertEqual(resets, [CORE, GNB, UE])

    def test_host_admission_stops_without_any_docker_commands(self):
        for case in ("busy-host", "sleep-enable-failed"):
            with self.subTest(case=case):
                output, result = self.bundle(case)
                self.assertFalse(result["candidate_switch_attempted"] or result["protocol_execution_valid"])
                self.assertFalse((output / "commands.jsonl").exists())

    def test_failed_sleep_clear_rejects_protocol_despite_official_service(self):
        output, result = self.bundle("sleep-clear-failed")
        self.assertTrue(result["final_service_restored"])
        self.assertFalse(result["protocol_execution_valid"])

    def test_independent_audit_ignores_runtime_predicates(self):
        output, _ = self.bundle("complete")
        with patch("sandbox.run_reconnect_r4.clean_window", side_effect=AssertionError("runtime predicate reused")), \
             patch("sandbox.run_reconnect_r4.evaluate", side_effect=AssertionError("runtime predicate reused")):
            self.assertTrue(audit(output, allow_fixture=True, allow_unfrozen_fixture=True)["protocol_execution_valid"])

    def test_resealed_tampering_is_not_accepted(self):
        output, _ = self.bundle("complete")
        originals = {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
        edits = [
            ("summary.json", lambda d: d.update(network_fix_validated=True)),
            ("summary.json", lambda d: d.update(operator_validated=True)),
            ("summary.json", lambda d: d.update(valid_completed_assignments=3)),
            ("approval.json", lambda d: d.update(recorded_at="2099-01-01T00:00:00+00:00")),
            ("approval.json", lambda d: d.update(rollback_plan="none")),
            ("approval.json", lambda d: d.update(execution_lock_sha256="0" * 64)),
            ("final-rollback.json", lambda d: d["reset"].update(containers=[UE])),
            ("host-guard.json", lambda d: d["sleep"].update(cleared=False)),
            ("trial-02.json", lambda d: d.update(recovery_15_of_15=True)),
        ]
        for name, edit in edits:
            with self.subTest(file=name, mutation=edits.index((name, edit))):
                data = json.loads(originals[name])
                edit(data)
                (output / name).write_text(json.dumps(data), encoding="utf-8")
                (output / "manifest.json").write_text(json.dumps({"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.name != "manifest.json"}}), encoding="utf-8")
                with self.assertRaises((ValueError, KeyError, TypeError)):
                    audit(output, allow_fixture=True, allow_unfrozen_fixture=True)
                (output / name).write_bytes(originals[name])
        (output / "manifest.json").write_bytes(originals["manifest.json"])
        with self.assertRaises(ValueError):
            audit(output)  # fixture transport cannot be silently relabelled measured
        reservations = (output / "identifiers.jsonl").read_text().splitlines()
        (output / "identifiers.jsonl").write_text("\n".join(reservations[1:]) + "\n", encoding="utf-8")
        (output / "manifest.json").write_text(json.dumps({"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.name != "manifest.json"}}), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "reservation"):
            audit(output, allow_fixture=True, allow_unfrozen_fixture=True)

    def test_default_cli_cannot_start_or_request_sleep_inhibition(self):
        with patch("sys.argv", ["run_reconnect_r4.py"]), patch("sandbox.run_reconnect_r4.verify_lock", side_effect=AssertionError("default CLI went past parser")):
            with self.assertRaises(SystemExit) as caught:
                main()
            self.assertEqual(caught.exception.code, 2)

    def test_exact_approval_and_command_inventory(self):
        approval = {**approval_expected("a" * 64), "recorded_at": "2026-09-05T00:00:00+00:00"}
        validate_approval(approval, "a" * 64)
        for field, value in (("live_actuation", True), ("image_ids", []), ("trials", []), ("approved_by", "agent"), ("execution_lock_sha256", "b" * 64)):
            with self.subTest(field=field), self.assertRaises(PermissionError):
                validate_approval(dict(approval, **{field: value}), "a" * 64)
        commands = allowed_commands()
        self.assertFalse(any("--since" in c or "--until" in c or "--follow" in c for c in commands))
        pings = [c for c in commands if c[:4] == ("docker", "exec", UE, "ping") and "-e" in c]
        self.assertEqual(sorted(int(c[c.index("-e") + 1]) for c in pings), list(range(10001, 10100)))


if __name__ == "__main__":
    unittest.main()
