"""Network-disabled positive and adversarial R4 collection fixtures."""
import copy
import json
import unittest
from unittest.mock import patch

from sandbox.reconnect_r4_collection import FixtureCollector, evaluate, recovery_candidate, IMAGES
from tools.audit_reconnect_r4_collection import audit, audit_recovery_candidate
from tests.reconnect_r4_fixture import FakeTransport, script, rehash, change_identity, missing_early, source_step, saturated, short_recovery


class CollectionTests(unittest.TestCase):
    def setUp(self):
        for name in ("subprocess.Popen", "socket.socket"):
            guard = patch(name, side_effect=AssertionError("network/process I/O forbidden in R4 fixtures"))
            guard.start()
            self.addCleanup(guard.stop)

    def collect(self, mode="trace", **kwargs):
        return FixtureCollector(FakeTransport(mode=mode, **kwargs)).collect(mode)

    def rejected_by_both(self, mutate, mode="trace"):
        bundle = self.collect(mode)
        mutate(bundle["commands"])
        for row in bundle["commands"]:
            rehash(row)
        with self.assertRaises((ValueError, KeyError, TypeError)):
            evaluate(bundle["commands"], bundle["identifier"], mode)
        with self.assertRaises((ValueError, KeyError, TypeError)):
            audit(bundle, allow_fixture=True)

    def test_complete_skewed_source_and_host_clocks_do_not_cut_first_packet(self):
        for skew in (-86400 * 10**9, -300_000_000, 0, 86400 * 10**9):
            with self.subTest(skew=skew):
                bundle = self.collect(skew_ns=skew)
                self.assertFalse(bundle["errors"])
                self.assertTrue(audit(bundle, allow_fixture=True)["collection_audit_passed"])
                self.assertEqual([p["sequence"] for p in bundle["result"]["trace"]["packets"]], [1, 2, 3, 4, 5])
                self.assertFalse(bundle["result"]["network_fix_validated"])
                self.assertFalse(any("--since" in r["argv"] or "--until" in r["argv"] for r in bundle["commands"]))

    def test_complete_idle_loss_is_not_delivery_success(self):
        bundle = self.collect(first_idle=True)
        self.assertTrue(audit(bundle, allow_fixture=True)["collection_audit_passed"])
        self.assertEqual(bundle["result"]["trace"]["packets"][0]["fate"], "nas_idle_nonretention_observed")
        self.assertFalse(bundle["result"]["packet_delivery_complete"])

    def test_fixture_never_accepted_without_opt_in_or_as_measurement(self):
        bundle = self.collect()
        with self.assertRaises(ValueError):
            audit(bundle)
        for key, value in (("evidence_label", "sandbox-measured"), ("network_execution_authorized", True),
                           ("network_fix_validated", True), ("actual_docker_commands_executed", 1)):
            modified = copy.deepcopy(bundle)
            modified[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                audit(modified, allow_fixture=True)

    def test_no_live_adapter_allowed(self):
        transport = FakeTransport()
        transport.io_enabled = True
        with self.assertRaises(ValueError):
            FixtureCollector(transport)

    def test_ineligible_source_stops_before_any_ping_and_consumes_id(self):
        fake = FakeTransport(source="10.45.0.3")
        collector = FixtureCollector(fake)
        first, second = collector.collect(), collector.collect()
        self.assertEqual((first["identifier"], second["identifier"]), (10001, 10002))
        self.assertTrue(first["errors"] and second["errors"])
        self.assertFalse(any("ping" in argv for argv in fake.calls))

    def test_id_exhaustion_does_not_wrap_or_send_command(self):
        fake = FakeTransport()
        collector = FixtureCollector(fake)
        collector.next_identifier = 10100
        with self.assertRaises(ValueError):
            collector.collect()
        self.assertEqual(fake.calls, [])

    def test_changed_ip_header_and_interface_are_independently_rejected(self):
        for index in (2, 7, 12):
            with self.subTest(index=index):
                self.rejected_by_both(lambda rows: rows[index].update(stdout=rows[index]["stdout"].replace("10.45.0.2", "10.45.0.3")))

    def test_missing_first_trace_never_becomes_inferred_loss_or_invented_path(self):
        self.rejected_by_both(missing_early)
        bundle = self.collect(mutate=missing_early)
        self.assertTrue(bundle["errors"])
        self.assertIsNone(bundle["result"])
        self.assertIn("5 received, 0%", bundle["commands"][7]["stdout"])

    def test_source_clock_step_rejected_without_estimated_offset(self):
        self.rejected_by_both(source_step)

    def test_host_clock_steps_within_and_between_commands_rejected(self):
        for field in ("wall_start_ns", "wall_end_ns"):
            with self.subTest(field=field):
                self.rejected_by_both(lambda rows: rows[8].update({field: rows[8][field] + 10**9}))
        def shift(rows):
            for row in rows[8:]:
                row["wall_start_ns"] += 10**9
                row["wall_end_ns"] += 10**9
        self.rejected_by_both(shift)

    def test_component_log_clock_reversal_rejected(self):
        self.rejected_by_both(lambda rows: rows[8].update(stdout=rows[8]["stdout"].replace("T00:01:40", "T00:00:40")))

    def test_saturation_before_or_after_and_byte_cap_rejected(self):
        self.rejected_by_both(saturated)
        self.rejected_by_both(lambda rows: rows[5].update(stdout=rows[5]["stdout"] * 2000))
        self.rejected_by_both(lambda rows: rows[8].update(stdout="x" * 1048576))

    def test_prefix_rotation_rewrite_empty_and_partial_line_rejected(self):
        for index, transform in ((8, lambda s: "\n".join(s.splitlines()[1:]) + "\n"),
                                 (8, lambda s: s.replace("component ready", "rewritten")),
                                 (5, lambda s: ""), (8, lambda s: s[:-1])):
            with self.subTest(index=index, transform=str(transform)):
                self.rejected_by_both(lambda rows: rows[index].update(stdout=transform(rows[index]["stdout"])))

    def test_partial_timeout_failed_or_warning_commands_rejected(self):
        for fields in ({"timed_out": True}, {"truncated": True}, {"returncode": 2}, {"stderr": "warning\n"}):
            with self.subTest(fields=fields):
                self.rejected_by_both(lambda rows: rows[8].update(fields))

    def test_changed_identity_restart_image_and_logging_rejected(self):
        for fields in ({"Id": "c" * 64}, {"RestartCount": 1}, {"Running": False},
                       {"Image": IMAGES["official_image_id"]}, {"LogConfig": {"Type": "json-file", "Config": {"max-size": "10m"}}}):
            with self.subTest(fields=fields):
                self.rejected_by_both(lambda rows: change_identity(rows, 13, **fields))

    def test_duplicate_missing_fingerprint_order_and_foreign_id_rejected(self):
        transforms = [lambda s: s + s.splitlines()[-1] + "\n",
                      lambda s: s.replace("fp=901", "fp=0", 1),
                      lambda s: s.replace("stage=nas_in", "stage=nas_idle", 1),
                      lambda s: s.replace("id=10001", "id=10002", 1),
                      lambda s: s.replace("stage=nas_forward", "stage=unknown", 1)]
        for transform in transforms:
            with self.subTest(transform=str(transform)):
                self.rejected_by_both(lambda rows: rows[8].update(stdout=transform(rows[8]["stdout"])))

    def test_id_already_in_precapture_cannot_be_reused(self):
        def mutate(rows):
            rows[5]["stdout"] = rows[8]["stdout"]
        self.rejected_by_both(mutate)
        bundle = self.collect(mutate=mutate)
        self.assertEqual(len(bundle["commands"]), 7)

    def test_exact_commands_prevent_clock_setting_fault_warmup_and_time_filter(self):
        for index, extra in ((3, ["-s", "now"]), (5, ["--since", "2026-09-05T00:00:00Z"]), (7, ["-c", "6"])):
            with self.subTest(index=index):
                self.rejected_by_both(lambda rows: rows[index]["argv"].extend(extra))

    def test_raw_hash_and_report_tampering_rejected(self):
        for mutate in (lambda b: b["commands"][8].update(stdout_sha256="0" * 64),
                       lambda b: b["result"].update(network_fix_validated=True),
                       lambda b: b["result"]["clock_brackets"][0].update(source_delta_ns=0)):
            bundle = self.collect()
            mutate(bundle)
            with self.subTest(mutate=str(mutate)), self.assertRaises(ValueError):
                audit(bundle, allow_fixture=True)

    def test_three_official_service_windows_keep_15_endpoint_without_trace_claim(self):
        collector = FixtureCollector(FakeTransport(mode="official-service", source="10.45.0.3"))
        windows = [collector.collect("official-service") for _ in range(3)]
        for window in windows:
            self.assertTrue(audit(window, allow_fixture=True)["collection_audit_passed"])
            self.assertFalse(window["result"]["trace_eligible"])
        result = recovery_candidate(windows)
        self.assertEqual(audit_recovery_candidate(windows), result)
        self.assertTrue(result["packet_delivery_candidate"])
        self.assertFalse(result["rollback_verified"])

    def test_failed_official_rollback_or_14_of_15_cannot_pass_recovery_candidate(self):
        collector = FixtureCollector(FakeTransport(mode="official-service"))
        windows = [collector.collect("official-service") for _ in range(3)]
        for mutate in (lambda rows: change_identity(rows, 13, Image=IMAGES["derived_image_id"]), short_recovery):
            altered = copy.deepcopy(windows)
            mutate(altered[-1]["commands"])
            for row in altered[-1]["commands"]:
                rehash(row)
            self.assertFalse(recovery_candidate(altered)["packet_delivery_candidate"])
            self.assertFalse(audit_recovery_candidate(altered)["packet_delivery_candidate"])
        self.assertFalse(recovery_candidate(windows[:2])["packet_delivery_candidate"])
        self.assertFalse(recovery_candidate([windows[0]] * 3)["packet_delivery_candidate"])

    def test_malformed_preclock_and_ambiguous_marker_stop_before_ping(self):
        for index, transform in ((3, lambda s: "not a clock\n"),
                                 (5, lambda s: s + s.replace("[fixture] component ready", "ST3 bad ST3 bad"))):
            with self.subTest(index=index):
                bundle = self.collect(mutate=lambda rows: rows[index].update(stdout=transform(rows[index]["stdout"])))
                self.assertEqual(len(bundle["commands"]), 7)
                self.assertTrue(bundle["errors"])

    def test_duplicate_reply_wrong_exit_and_forged_zero_loss_rejected(self):
        for transform in (lambda s: s + s.splitlines()[1] + "\n", lambda s: s.replace("5 received, 0%", "4 received, 0%")):
            self.rejected_by_both(lambda rows: rows[7].update(stdout=transform(rows[7]["stdout"])))
        self.rejected_by_both(lambda rows: rows[7].update(returncode=1))

    def test_nanosecond_local_reversal_is_not_hidden_by_datetime_rounding(self):
        def mutate(rows):
            lines = rows[8]["stdout"].splitlines()
            first_stamp = lines[1].split()[0]
            # First packet's second stage precedes its first by one nanosecond.
            seconds, nanos = first_stamp[:-1].split(".")
            if int(nanos) == 0:
                replacement = first_stamp.replace(":40.", ":39.").replace(".000000000Z", ".999999999Z")
            else:
                replacement = seconds + f".{int(nanos) - 1:09d}Z"
            lines[2] = replacement + " " + lines[2].split(" ", 1)[1]
            rows[8]["stdout"] = "\n".join(lines) + "\n"
        self.rejected_by_both(mutate)

    def test_independent_auditor_does_not_use_runtime_acceptance(self):
        bundle = self.collect()
        with patch("sandbox.reconnect_r4_collection.evaluate", side_effect=AssertionError("must not be called")), \
             patch("sandbox.reconnect_r4_collection.account_window", side_effect=AssertionError("must not be called")):
            self.assertTrue(audit(bundle, allow_fixture=True)["collection_audit_passed"])

    def test_new_session_between_service_windows_is_not_one_recovery_candidate(self):
        collector = FixtureCollector(FakeTransport(mode="official-service"))
        windows = [collector.collect("official-service") for _ in range(3)]
        for index in (0, 13):
            change_identity(windows[-1]["commands"], index, RestartCount=1)
            rehash(windows[-1]["commands"][index])
        self.assertTrue(audit(windows[-1], allow_fixture=True)["collection_audit_passed"])
        self.assertFalse(recovery_candidate(windows)["packet_delivery_candidate"])
        self.assertFalse(audit_recovery_candidate(windows)["packet_delivery_candidate"])


if __name__ == "__main__":
    unittest.main()
