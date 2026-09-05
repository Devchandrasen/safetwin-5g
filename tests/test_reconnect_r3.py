import copy
import json
from pathlib import Path
import unittest

from tools.reconnect_r3_source import SOURCES, RETAINED, render, source_tree, strip
from tools.reconnect_r3_trace import parse, account_window

ROOT = Path(__file__).resolve().parents[1]


def trace_window(first_idle=False, missing=False):
    rows = []
    for seq in range(1, 6):
        idle = seq == 1 and first_idle
        stages = ["nas_in", "nas_idle"] if idle else ["nas_in", "nas_forward", "ue_rls", "gnb_in", "gnb_missing" if missing else "gnb_resource"]
        for stage in stages:
            rows.append({"stage": stage, "psi": 1, "actor": 0, "cm": int(not idle), "mm": 7, "ps": 1,
                         "pending": 0, "ipid": seq, "id": 10001, "seq": seq, "bytes": 84, "fp": seq + 900})
    return rows


class R3TraceTests(unittest.TestCase):
    def test_generated_overlay_strips_to_exact_original(self):
        tree = source_tree()
        self.assertEqual(set(tree), set(SOURCES) | {"src/utils/safetwin_trace_r3.hpp"})
        for path in SOURCES:
            original = (RETAINED / ("upstream-" + path.replace("/", "-"))).read_text(encoding="utf-8")
            self.assertEqual(strip(tree[path].decode()), original)

    def test_changed_base_and_repeat_instrumentation_rejected(self):
        with self.assertRaisesRegex(ValueError, "non-unique source anchor"):
            render(SOURCES[0], "unrelated source")
        with self.assertRaisesRegex(ValueError, "already instrumented"):
            render(SOURCES[0], source_tree()[SOURCES[0]].decode())

    def test_malformed_marker_rejected(self):
        with self.assertRaisesRegex(ValueError, "malformed instrumentation"):
            strip("// SAFETWIN_R3_BEGIN a\nanything\n// SAFETWIN_R3_END b\n")

    def test_behavioral_edit_not_hidden_by_marker_removal(self):
        source = source_tree()[SOURCES[0]].decode().replace("m->pdu = std::move(data);", "m->pdu = {};" )
        original = (RETAINED / "upstream-src-ue-nas-sm-sap.cpp").read_text(encoding="utf-8")
        self.assertNotEqual(strip(source), original)

    def test_complete_idle_loss_trace_is_not_recovery_success(self):
        result = account_window(trace_window(first_idle=True), 10001, [2, 3, 4, 5])
        self.assertTrue(result["trace_accounting_complete"])
        self.assertEqual(result["packets"][0]["fate"], "nas_idle_nonretention_observed")
        self.assertEqual(result["received"], 4)
        self.assertFalse(result["all_packets_returned"] or result["network_fix_validated"])

    def test_clean_control_does_not_claim_fix(self):
        result = account_window(trace_window(), 10001, [1, 2, 3, 4, 5])
        self.assertTrue(result["all_packets_returned"])
        self.assertFalse(result["network_fix_validated"])

    def test_downstream_missing_resource_and_unknown_loss_remain_distinct(self):
        missing = account_window(trace_window(missing=True), 10001, [])
        unknown = account_window(trace_window(), 10001, [])
        self.assertEqual(missing["packets"][0]["fate"], "gnb_missing_resource_observed")
        self.assertEqual(unknown["packets"][0]["fate"], "after_gnb_resource_unlocalized")

    def test_missing_ingress_or_downstream_trace_is_not_localized(self):
        for stage in ("nas_in", "nas_forward", "ue_rls", "gnb_in", "gnb_resource"):
            rows = [r for r in trace_window() if not (r["seq"] == 1 and r["stage"] == stage)]
            with self.subTest(stage=stage), self.assertRaises(ValueError):
                account_window(rows, 10001, [1, 2, 3, 4, 5])

    def test_duplicate_and_mismatched_fingerprint_rejected(self):
        rows = trace_window(); rows.append(copy.deepcopy(rows[0]))
        with self.assertRaisesRegex(ValueError, "duplicate stage"):
            account_window(rows, 10001, [])
        rows = trace_window(); rows[1]["fp"] += 1
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            account_window(rows, 10001, [])

    def test_idle_reply_or_missing_resource_reply_rejected(self):
        for rows in (trace_window(first_idle=True), trace_window(missing=True)):
            with self.subTest(rows=rows[1]["stage"]), self.assertRaises(ValueError):
                account_window(rows, 10001, [1, 2, 3, 4, 5])

    def test_branch_state_and_order_must_match(self):
        rows = trace_window(); rows[1]["cm"] = 0
        with self.assertRaisesRegex(ValueError, "forward branch state"):
            account_window(rows, 10001, [])
        rows = trace_window(); rows[0], rows[1] = rows[1], rows[0]
        with self.assertRaisesRegex(ValueError, "within-component event order"):
            account_window(rows, 10001, [])

    def test_parser_enforces_wire_schema_component_and_domain(self):
        line = "[timestamp] [nas] [debug] ST3 stage=nas_idle psi=1 actor=0 cm=0 mm=7 ps=1 pending=0 ipid=9 id=10001 seq=1 bytes=84 fp=123"
        self.assertEqual(parse(line, "ue")[0]["id"], 10001)
        for bad in (line.replace("seq=1", "seq=6"), line + " trailing", line.replace("nas_idle", "invented")):
            with self.subTest(line=bad), self.assertRaises(ValueError): parse(bad, "ue")
        with self.assertRaisesRegex(ValueError, "stage/component"):
            parse(line, "gnb")

    def test_other_window_is_not_pooled(self):
        rows = trace_window()
        extra = copy.deepcopy(rows)
        for row in extra: row["id"] = 10002
        self.assertEqual(account_window(rows + extra, 10001, [])["sent"], 5)

    def test_frozen_four_trial_scope(self):
        config = json.loads((ROOT / "config/experiments/reconnect-r3-trace.json").read_text())
        self.assertEqual([r["trial_id"] for r in config["trials"]], ["trace:control-before", "trace:drop-a", "trace:drop-b", "trace:control-after"])
        self.assertEqual((config["drop_seconds"], config["required_recovery_packets"]), (8, 15))
        self.assertFalse(config["new_behavioral_correction"] or config["confirmatory_data"] or config["live_actuation"])


if __name__ == "__main__": unittest.main()
