"""Retained negative-result audit and clock/filter counterexamples, no Docker."""
import copy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest

from tools.audit_reconnect_r3_observation import RUN, CLOCK, ROOT, audit_run, audit_clock, source_address
from tools.audit_reconnect_r3_network import audit as complete_audit, raw_paths
from tools.capture_reconnect_r3_clock import clock_bounds
from sandbox.reconnect_r3_measurement import ping_result
from tests.test_reconnect_r3 import trace_window


class ObservationTests(unittest.TestCase):
    def copied(self, original):
        temp = tempfile.TemporaryDirectory(prefix="safetwin-r3-observation-"); self.addCleanup(temp.cleanup)
        result = Path(temp.name) / "bundle"; shutil.copytree(original, result); return result

    def reseal(self, directory):
        rows = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in directory.iterdir() if p.is_file() and p.name != "manifest.json"}
        (directory / "manifest.json").write_text(json.dumps({"captured_file_sha256": rows}), encoding="utf-8")

    def change_json(self, directory, name, mutate):
        path = directory / name; data = json.loads(path.read_bytes()); mutate(data)
        path.write_text(json.dumps(data), encoding="utf-8"); self.reseal(directory)

    def change_commands(self, directory, mutate, clock=False):
        path = directory / ("commands.json" if clock else "commands.jsonl")
        rows = json.loads(path.read_bytes()) if clock else [json.loads(line) for line in path.read_text().splitlines()]
        mutate(rows)
        for row in rows:
            for stream in ("stdout", "stderr"): row[stream + "_sha256"] = hashlib.sha256(row[stream].encode()).hexdigest()
        path.write_bytes((json.dumps(rows) if clock else "\n".join(json.dumps(r) for r in rows)).encode()); self.reseal(directory)

    def test_rejected_prefix_is_not_a_completed_diagnostic_or_packet_loss(self):
        result = audit_run()
        self.assertEqual((result["commands_replayed"], result["samples_replayed"], result["scope_snapshots"]), (131, 6, 5))
        self.assertEqual((result["attempted_assignments"], result["valid_completed_assignments"], result["fault_exposures"]), (1, 0, 0))
        self.assertFalse(result["protocol_execution_valid"] or result["network_fix_validated"])
        self.assertEqual([r["received"] for r in result["observations"]], [5]*6)
        self.assertEqual([r.get("unobserved_sequences") for r in result["observations"][:3]], [[1], [1,2,3,4,5], [1,2]])
        self.assertIsNone(result["observations"][1]["observed_paths_have_consistent_fingerprints"])
        self.assertTrue(result["official_images_restored"]); self.assertEqual(result["final_official_packets_returned"], 15)

    def test_original_complete_auditor_still_rejects(self):
        with self.assertRaisesRegex(ValueError, "eight required scope snapshots"): complete_audit(RUN)

    def test_later_clock_measurement_does_not_recover_historical_trace(self):
        result = audit_clock()
        self.assertEqual((result["paired_clock_probes"], result["read_only_commands"]), (10, 15))
        self.assertTrue(result["all_clock_upper_bounds_negative"] and result["official_service_snapshots_unchanged"])
        self.assertLess(result["maximum_offset_upper_seconds"], 0)
        self.assertFalse(result["historical_missing_trace_recovered"] or result["network_fix_validated"])

    def test_claim_promotion_rejected(self):
        for key in ("network_fix_validated", "TNSM_ready", "protocol_execution_valid", "live_actuation", "hardware_measured"):
            directory = self.copied(RUN); self.change_json(directory, "summary.json", lambda r:r.update({key:True}))
            with self.subTest(key=key), self.assertRaises(ValueError): audit_run(directory)

    def test_invented_baseline_completion_rejected(self):
        directory = self.copied(RUN); self.change_json(directory, "trial-01.json", lambda r:r.update(baseline=[]))
        with self.assertRaisesRegex(ValueError, "stopped initial baseline"): audit_run(directory)

    def test_fault_or_warmup_cannot_be_hidden_in_stopped_prefix(self):
        for name in ("bounded-link-drop", "warmup-ping"):
            directory = self.copied(RUN)
            self.change_commands(directory, lambda rows:next(r for r in rows if r["name"] == "service-ping").update(name=name))
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "stopped command inventory"): audit_run(directory)

    def test_packet_count_change_rejected_even_with_updated_hash(self):
        directory = self.copied(RUN)
        def mutate(rows):
            row = next(r for r in rows if r["name"] == "service-ping")
            row["stdout"] = "\n".join(line for line in row["stdout"].splitlines() if "icmp_seq=1" not in line).replace("5 received, 0%", "4 received, 20%")
        self.change_commands(directory, mutate)
        with self.assertRaisesRegex(ValueError, "raw packet delivery"): audit_run(directory)

    def test_neutral_settings_do_not_override_stopped_upf(self):
        directory = self.copied(RUN)
        self.change_commands(directory, lambda rows:next(r for r in rows if r["name"] == "upf-state").update(stdout="T\n"))
        with self.assertRaisesRegex(ValueError, "raw service telemetry"): audit_run(directory)

    def test_source_address_is_not_inferred_from_returned_packet_count(self):
        rows = [json.loads(line) for line in (RUN / "commands.jsonl").read_text().splitlines()]
        raw = next(row["stdout"] for row in rows if row["sequence"] == 51)
        self.assertEqual(ping_result(raw)["packets_received"], 5)
        self.assertEqual(source_address(raw), "10.45.0.3")
        header = (ROOT / "sandbox/patches/ueransim-reconnect-r3-trace/safetwin_trace_r3.hpp").read_text()
        flow = re.search(r"flow\[\] = \{([^}]+)\}", header).group(1)
        self.assertEqual([int(n) for n in flow.split(",")], [10,45,0,2,10,45,0,1])
        self.assertIn("data[12 + i] != flow[i]", header)

    def test_missing_or_duplicate_ping_header_rejected(self):
        line = "PING 10.45.0.1 (10.45.0.1) from 10.45.0.2 uesimtun0: 56(84) bytes of data."
        for value in ("", line+"\n"+line, line.replace("uesimtun0", "eth0")):
            with self.subTest(value=value[:50]), self.assertRaises(ValueError): source_address(value)

    def test_inconsistent_present_packet_fingerprint_rejected(self):
        directory = self.copied(RUN)
        def mutate(rows):
            row = next(r for r in rows if r["sequence"] == 43)
            row["stdout"] = row["stdout"].replace("fp=9172637494916554484", "fp=1", 1)
        self.change_commands(directory, mutate)
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"): audit_run(directory)

    def test_clock_cannot_be_adjusted_by_read_only_probe(self):
        directory = self.copied(CLOCK)
        self.change_commands(directory, lambda rows:rows[2]["argv"].extend(["-s", "now"]), clock=True)
        with self.assertRaisesRegex(ValueError, "date only"): audit_clock(directory)

    def test_clock_brackets_recomputed_independently(self):
        directory = self.copied(CLOCK)
        self.change_json(directory, "summary.json", lambda r:r["clock_brackets"][0].update(container_minus_host_upper_seconds=0))
        with self.assertRaisesRegex(ValueError, "independent clock intervals"): audit_clock(directory)

    def test_clock_probe_cannot_be_claimed_historical_packet_recovery(self):
        directory = self.copied(CLOCK)
        self.change_json(directory, "summary.json", lambda r:r.update(historical_missing_trace_recovered=True))
        with self.assertRaisesRegex(ValueError, "clock claim boundary"): audit_clock(directory)

    def test_clock_brackets_bound_latency_without_midpoint_assumption(self):
        row = {"started_at":"2026-09-05T00:00:00.300000+00:00", "completed_at":"2026-09-05T00:00:00.500000+00:00", "stdout":"2026-09-05T00:00:00.100000Z\n", "monotonic_elapsed_seconds":0.2}
        self.assertEqual(clock_bounds(row), {"container_minus_host_lower_seconds":-0.4, "container_minus_host_upper_seconds":-0.2})
        row["monotonic_elapsed_seconds"] = 1
        with self.assertRaisesRegex(ValueError, "wall-clock step"): clock_bounds(row)

    def test_host_clock_filter_can_clip_trace_despite_all_replies_fixture_only(self):
        base = datetime(2026,9,5,tzinfo=timezone.utc)
        host_since = (base + timedelta(seconds=0.25)).isoformat()
        container_since = base.isoformat(); until = (base + timedelta(seconds=2)).isoformat()
        logs = {"ue":[], "gnb":[]}
        for row in trace_window():
            timestamp = (base + timedelta(seconds=0.1 + 0.2*(row["seq"]-1))).isoformat()
            component = "gnb" if row["stage"].startswith("gnb_") else "ue"
            logs[component].append(timestamp + " ST3 " + " ".join(f"{k}={v}" for k,v in row.items()))
        # Emulate documented timestamp filtering. No captured R3 line is added.
        clipped = ["\n".join(line for line in logs[c] if datetime.fromisoformat(line.split()[0]) >= datetime.fromisoformat(host_since)) for c in ("ue","gnb")]
        with self.assertRaises(ValueError): raw_paths(*clipped, host_since, until, 10001, [1,2,3,4,5])
        whole = raw_paths(*["\n".join(logs[c]) for c in ("ue","gnb")], container_since, until, 10001, [1,2,3,4,5])
        self.assertTrue(whole["trace_accounting_complete"])
        self.assertFalse(whole["network_fix_validated"])


if __name__ == "__main__": unittest.main()
