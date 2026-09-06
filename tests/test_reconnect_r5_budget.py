"""Synthetic health clients and waits; no actual process, socket or native API."""
import base64
import copy
import hashlib
from unittest.mock import patch

import pytest
from sandbox import reconnect_r5_budget as candidate
from sandbox.reconnect_r5_journal import Journal
from tests.test_reconnect_r5_process import Clock
from tools.audit_reconnect_r5_budget import audit, audit_inventory

CASES = ("healthy", "healthy-last-poll", "unhealthy-all", "starting-then-healthy", "empty", "unknown", "stderr", "nonzero",
         "client-timeout", "client-too-late", "transport-throw", "counter-before", "counter-after-wait", "source-unavailable",
         "clock-step", "domain-change", "wide-terminal", "late-terminal", "normal-capacity", "normal-boundary",
         "cleanup-capacity", "cleanup-boundary", "global-health-reserve", "cleanup-after-global", "wait-short", "wait-throw",
         "settle", "settle-short", "settle-throw", "settle-late", "journal-fsync", "independent-health-targets")
ACCEPTED = {"healthy", "healthy-last-poll", "starting-then-healthy", "normal-boundary", "cleanup-boundary", "cleanup-after-global", "settle"}


class Transport:
    def __init__(self, j, case):
        self.journal, self.clock, self.case, self.next_sequence = j, j.clock, case, 1
        self.calls = []

    def run(self, argv, *, sequence, timeout_ms, max_output_bytes, cleanup=False):
        assert sequence == self.next_sequence
        if self.case == "transport-throw":
            raise OSError("fixture client was not dispatched")
        j, c = self.journal, self.clock
        n, ev, poll = len(j.prefix.points), len(j.events), self.next_sequence
        admitted = j.admitted()
        checked, before, after = c.ticks(), c.ticks(), c.ticks()
        if self.case == "client-too-late":
            c.value += 36*c.descriptor["frequency_hz"]
        observed, cleaned = c.ticks(), c.ticks()
        if self.case == "source-unavailable":
            c.capture = lambda: (_ for _ in ()).throw(OSError("fixture precise source unavailable"))
        if self.case == "clock-step":
            c.step_at = c.sequence+1
        stdout = "healthy\n"
        if self.case == "healthy-last-poll" and poll < 25 or self.case in ("unhealthy-all", "wait-short", "wait-throw", "counter-after-wait"):
            stdout = "unhealthy\n"
        if self.case in ("normal-boundary", "cleanup-boundary") and poll < 25:
            stdout = "starting\n"
        if self.case == "starting-then-healthy" and poll < 3:
            stdout = "starting\n"
        if self.case == "empty":
            stdout = ""
        if self.case == "unknown":
            stdout = "not-configured\n"
        stderr = "fixture stderr\n" if self.case == "stderr" else ""
        j.checkpoint("process:"+str(sequence)+":end", cleanup=cleanup)
        end = len(j.prefix.points) if len(j.prefix.points) > n else None
        deadline = j.prefix.points[n-1]["qpc_before_ticks"]+timeout_ms*c.descriptor["frequency_hz"]//1000
        timing = bool(end and j.prefix.status()["clock_capture_valid"] and not j.capture_failed and not j.failure and observed < deadline)
        timeout = self.case == "client-timeout"
        code = 3 if self.case == "nonzero" or self.case == "independent-health-targets" and poll == 1 else 0
        row = dict(contract_id="safetwin5g-reconnect-r5-process-v1", sequence=sequence, argv=argv, cleanup=cleanup,
                   timeout_ms=timeout_ms, max_output_bytes=max_output_bytes, cleanup_grace_ms=2000,
                   clock_id=j.prefix.descriptor["clock_id"], journal_event_before=ev, journal_event_after=len(j.events),
                   start_point=n, end_point=end, admitted_clock_before=admitted, counter_error=None,
                   checked_ticks=checked, go_before_ticks=before, go_after_ticks=after, completion_observed_ticks=observed,
                   cleanup_completed_ticks=cleaned, deadline_ticks=deadline, timer_due_100ns=(deadline-checked)*10000000//c.descriptor["frequency_hz"],
                   timer_armed=True, timer_signaled=timeout, cleanup_timer_armed=True, cleanup_timer_signaled=False, emergency_timer_only=False,
                   launcher_go_sent=True, job_assigned_before_go=True, job_closed=True, owned_launcher_pid=12345,
                   process_reaped=True, reader_threads_joined=True, timed_out=timeout, truncated=False,
                   process_errors=[], cleanup_errors=[], returncode=code, timing_valid=timing, client_capture_complete=not timeout,
                   complete=timing and not timeout, stdout_utf8=True, stderr_utf8=True, stdout=stdout, stderr=stderr,
                   retained_output_bytes=len(stdout.encode())+len(stderr.encode()))
        for stream in ("stdout", "stderr"):
            raw = row[stream].encode()
            row[stream+"_base64"], row[stream+"_sha256"] = base64.b64encode(raw).decode(), hashlib.sha256(raw).hexdigest()
        self.next_sequence += 1
        self.calls.append(row)
        if self.case == "late-terminal":
            c.value += 51*c.descriptor["frequency_hz"]
        return row


def capture_case(path, case):
    path.mkdir(exist_ok=False)
    c, j = Clock(), None
    if case == "wide-terminal":
        capture = c.capture
        def wide():
            r = capture()
            if r["sequence"] == 4:
                r["qpc_after_ticks"] += 2000
                c.value += 2000
            return r
        c.capture = wide
    j = Journal(c, path/"clock.jsonl")
    j.checkpoint("bootstrap:0")
    j.checkpoint("bootstrap:1")
    t = Transport(j, case)
    def wait(ms):
        if case in ("wait-throw", "settle-throw"):
            raise OSError("fixture wait failed")
        if case not in ("wait-short", "settle-short"):
            c.value += (1501*1000 if case == "settle-late" else ms)*c.descriptor["frequency_hz"]//1000
        if case == "counter-after-wait":
            c.dead_at = c.reads+1
    budget = candidate.RunnerBudget(j, t, wait)
    initial = {"normal-capacity": 743, "normal-boundary": 742, "cleanup-capacity": 999, "cleanup-boundary": 998}.get(case, 2)
    for i in range(2, initial):
        j.checkpoint("bootstrap:"+str(i), cleanup=i >= 768)
    if case == "global-health-reserve":
        c.value += 1451*c.descriptor["frequency_hz"]
    if case == "cleanup-after-global":
        c.value += 1501*c.descriptor["frequency_hz"]
        j.checkpoint("bootstrap:after-global", cleanup=True)
    if case == "counter-before":
        c.dead_at = c.reads+1
    if case == "domain-change":
        c.descriptor["clock_id"] = "b"*32
    try:
        with patch("subprocess.Popen", side_effect=AssertionError("budget fixture process forbidden")), \
             patch("socket.socket", side_effect=AssertionError("budget fixture socket forbidden")), \
             patch("ctypes.WinDLL", side_effect=AssertionError("budget fixture native clock/power forbidden")):
            if case.startswith("settle"):
                budget.settle()
            elif case == "journal-fsync":
                with patch("os.fsync", side_effect=OSError("fixture journal sync failed")):
                    budget.health(candidate.TARGETS[0])
            else:
                for target in candidate.TARGETS if case == "independent-health-targets" else candidate.TARGETS[:1]:
                    budget.health(target, cleanup=case.startswith("cleanup-") or case == "independent-health-targets")
        bundle = dict(case=case, evidence_label="fixture", measurement_scope="synthetic-runner-budget-only", actual_processes_executed=0,
                      network_commands_executed=0, actual_power_requests_executed=0, budget=budget.snapshot(), snapshot=j.snapshot(),
                      inventory=candidate.inventory(), independent=None, audit_error=None)
    finally:
        j.close()
    bundle["independent_inventory"] = audit_inventory(bundle["inventory"])
    try:
        bundle["independent"] = audit(bundle["budget"], bundle["snapshot"], (path/"clock.jsonl").read_bytes())
    except ValueError as exc:
        bundle["audit_error"] = str(exc)
    return bundle


def check_case(b):
    name, ops = b["case"], b["budget"]["operations"]
    assert b["evidence_label"] == "fixture" and b["measurement_scope"] == "synthetic-runner-budget-only"
    assert b["actual_processes_executed"] == b["network_commands_executed"] == b["actual_power_requests_executed"] == 0
    assert [o["accepted"] for o in ops] == ([False, True, True] if name == "independent-health-targets" else [name in ACCEPTED])
    if name == "journal-fsync":
        assert "journal storage failed" in b["audit_error"]
    else:
        assert b["audit_error"] is None, b["audit_error"]
        assert [d["accepted"] for d in b["independent"]["decisions"]] == [o["accepted"] for o in ops]
    assert b["budget"]["whole_protocol_verified"] is b["budget"]["network_execution_authorized"] is b["budget"]["rollback_verified"] is False
    if name in ("healthy-last-poll", "unhealthy-all", "normal-boundary", "cleanup-boundary"):
        assert len(ops[0]["commands"]) == 25 and len(ops[0]["waits"]) == 24
        assert ops[0]["end_point"]-ops[0]["start_point"] == 26
        # timeout_ms is relative to the last retained anchor, BEFORE the wait.
        # The frozen process adapter deducts the wait at checked_ticks before
        # arming its independent timer. Test the actual remaining envelope.
        row = ops[0]["commands"][-1]
        f = b["snapshot"]["descriptor"]["frequency_hz"]
        anchor = b["snapshot"]["points"][row["start_point"]-1]
        assert 2000 < row["timeout_ms"] < 4001
        assert row["deadline_ticks"] == anchor["qpc_before_ticks"]+row["timeout_ms"]*f//1000
        assert row["deadline_ticks"] <= ops[0]["deadline_ticks"]
        assert 0 < row["timer_due_100ns"] < 2001*10000
        assert row["timer_due_100ns"] == (row["deadline_ticks"]-row["checked_ticks"])*10000000//f
    if name in ("normal-capacity", "cleanup-capacity", "counter-before", "global-health-reserve"):
        assert not ops[0]["commands"]
    if name == "settle":
        assert len(b["snapshot"]["points"]) == 3


@pytest.mark.parametrize("case", CASES)
def test_retained_budget_cases(tmp_path, case):
    check_case(capture_case(tmp_path/"raw", case))


@pytest.mark.parametrize("key,value", [("cleanup_points_max", 215), ("normal_nominal_points", 740), ("unpruned_normal_upper_points", 768),
                                      ("guarantees_four_complete_trials", True), ("runner_implemented", True), ("total_limit", 1025)])
def test_inventory_tamper(key, value):
    p = candidate.inventory()
    p[key] = value
    with pytest.raises(ValueError, match="inventory"):
        audit_inventory(p)


@pytest.mark.parametrize("target", ["global", "deadline", "reservation", "poll-count", "early-wait", "closure", "status", "sequence", "acceptance", "timer-renewal",
                                    "initial-order", "poll-wait-order", "poll-type"])
def test_raw_budget_tamper(tmp_path, target):
    b = capture_case(tmp_path/"raw", "healthy-last-poll")
    budget, w = b["budget"], b["budget"]["operations"][0]
    if target == "global":
        budget["global_deadline_ticks"] += 1
    elif target == "deadline":
        w["deadline_ticks"] += 1
    elif target == "reservation":
        w["checks"][0]["points_needed"] = 1
    elif target == "poll-count":
        w["commands"].pop()
    elif target == "early-wait":
        w["waits"][0]["after_ticks"] = w["waits"][0]["before_ticks"]
    elif target == "closure":
        w["final_ticks"] = 0
    elif target == "status":
        w["commands"][0]["stdout"] = "healthy\n"
    elif target == "sequence":
        w["commands"][1]["sequence"] = 1
    elif target == "acceptance":
        w["accepted"] = False
    elif target == "timer-renewal":
        # A full relative timeout renewed AFTER the wait must be rejected.
        w["commands"][-1]["timer_due_100ns"] = w["commands"][-1]["timeout_ms"]*10000
    elif target == "initial-order":
        w["checks"][0]["ticks"] = w["checks"][1]["ticks"]+1
    elif target == "poll-wait-order":
        w["checks"][2]["ticks"] = w["waits"][0]["before_ticks"]
    elif target == "poll-type":
        w["checks"][1]["poll"] = True
    with pytest.raises(ValueError):
        audit(budget, b["snapshot"], (tmp_path/"raw/clock.jsonl").read_bytes())


def test_candidate_disabled_independent_audit(tmp_path):
    b = capture_case(tmp_path/"raw", "healthy-last-poll")
    with patch.object(candidate.RunnerBudget, "health", side_effect=AssertionError("candidate forbidden")), \
         patch.object(candidate.RunnerBudget, "admit", side_effect=AssertionError("candidate forbidden")), \
         patch.object(candidate, "inventory", side_effect=AssertionError("candidate forbidden")):
        assert audit(b["budget"], b["snapshot"], (tmp_path/"raw/clock.jsonl").read_bytes()) == b["independent"]
        assert audit_inventory(b["inventory"]) == b["independent_inventory"]


def test_admission_type_and_domain_rejection(tmp_path):
    j = Journal(Clock(), tmp_path/"clock.jsonl")
    j.checkpoint("bootstrap:0")
    j.checkpoint("bootstrap:1")
    t = Transport(j, "healthy")
    b = candidate.RunnerBudget(j, t, lambda ms: None)
    try:
        for points, seconds in ((True, 1), (0, 1), (769, 1), (1, True), (1, 0), (1, 1501)):
            with pytest.raises(ValueError):
                b.admit("fixture", points_needed=points, seconds_needed=seconds)
        t.clock = Clock()
        with pytest.raises(ValueError, match="same-domain"):
            candidate.RunnerBudget(j, t, lambda ms: None)
        with pytest.raises(ValueError, match="outside"):
            b.health("unrelated-container")
    finally:
        j.close()
