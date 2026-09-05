"""Invented packet text and raw QPC records; no child, socket or native API."""
import base64
import copy
import hashlib
import json
from unittest.mock import patch

import pytest
from sandbox import reconnect_r5_collection as candidate
from sandbox.reconnect_r5_journal import Journal
from tests.test_reconnect_r5_process import Clock
from tests.reconnect_r4_fixture import script, missing_early, saturated, short_recovery, change_identity, IMAGES
from tools.audit_reconnect_r5_collection import audit, packet_candidate, read_window

CASES = ("complete", "positive-skew", "negative-skew", "first-idle-loss", "source-ineligible", "official-source-3",
         "missing-first-trace", "saturated-log", "empty-prefix", "prefix-lost", "reused-prefix-id", "foreign-packet",
         "wrong-image", "restarted", "official-trace", "source-step", "source-precision", "stderr", "nonzero", "partial-command",
         "invalid-utf8", "clock-step", "source-unavailable", "QPC-before", "deadline-before", "deadline-middle", "deadline-closure",
         "point-reserve", "point-boundary", "cleanup-reserve", "cleanup-capacity", "cleanup-boundary", "closure-wide", "ledger-fsync", "transport-throw", "official-15", "official-14", "changed-context")
VALID = {"complete", "positive-skew", "negative-skew", "first-idle-loss", "official-source-3", "point-boundary", "cleanup-reserve", "cleanup-boundary", "official-15", "official-14", "changed-context"}


class FakeTransport:
    def __init__(self, journal, case):
        self.journal, self.clock, self.case, self.next_sequence = journal, journal.clock, case, 1
        self.local, self.rows, self.windows = 0, None, 0

    def prepare(self, identifier, mode):
        self.local, self.windows = 0, self.windows+1
        source = "10.45.0.3" if self.case in ("source-ineligible", "official-source-3") else "10.45.0.2"
        rows = script(identifier, mode, source=source, first_idle=self.case == "first-idle-loss")
        if self.case == "missing-first-trace":
            missing_early(rows)
        if self.case == "saturated-log":
            saturated(rows)
        if self.case == "empty-prefix":
            rows[5]["stdout"] = ""
        if self.case == "prefix-lost":
            rows[8]["stdout"] = "\n".join(rows[8]["stdout"].splitlines()[1:])+"\n"
        if self.case == "reused-prefix-id":
            rows[5]["stdout"] += rows[8]["stdout"].splitlines()[1]+"\n"
        if self.case == "foreign-packet":
            rows[8]["stdout"] = rows[8]["stdout"].replace("id="+str(identifier)+" ", "id=10099 ")
        if self.case == "wrong-image":
            change_identity(rows, 0, Image=IMAGES["official_image_id"])
        if self.case == "restarted":
            change_identity(rows, 13, RestartCount=1)
        if self.case == "changed-context" and self.windows == 3:
            for index in (0, 13):
                change_identity(rows, index, Id="c"*64)
        if self.case == "official-trace":
            rows[8]["stdout"] += script(identifier)[8]["stdout"].splitlines()[1]+"\n"
        if self.case == "official-14" and self.windows == 3:
            short_recovery(rows)
        self.rows = rows

    def run(self, argv, *, sequence, timeout_ms, max_output_bytes, cleanup=False):
        assert sequence == self.next_sequence and argv == self.rows[self.local]["argv"]
        if self.case == "transport-throw" and self.local == 0:
            raise OSError("fixture transport never dispatched")
        j, c, local = self.journal, self.clock, self.local
        n, ev = len(j.prefix.points), len(j.events)
        admitted = j.admitted()
        checked, before, after = c.ticks(), c.ticks(), c.ticks()
        observed, cleaned = c.ticks(), c.ticks()
        stdout, stderr = self.rows[local]["stdout"], "fixture stderr\n" if self.case == "stderr" and local == 7 else ""
        if local in (3, 4, 10, 11):
            skew = {"positive-skew": 86400*10**9, "negative-skew": -86400*10**9}.get(self.case, -10**9)
            if local in (4, 11):
                skew *= -2
            ns = 1788566400000000000+before*100+skew
            if self.case == "source-step" and local == 10:
                ns += 5*10**9
            seconds, nanos = divmod(ns, 10**9)
            stdout = f"{seconds}.{nanos:09d}\n"
            if self.case == "source-precision" and local == 3:
                stdout = f"{seconds}\n"
        if self.case == "clock-step" and local == 7:
            c.step_at = c.sequence+1
        if self.case == "source-unavailable" and local == 7:
            c.capture = lambda: (_ for _ in ()).throw(OSError("fixture UTC unavailable"))
        j.checkpoint("process:"+str(sequence)+":end", cleanup=cleanup)
        end = len(j.prefix.points) if len(j.prefix.points) > n else None
        timing = bool(end and j.prefix.status()["clock_capture_valid"] and not j.capture_failed)
        timeout = self.case == "partial-command" and local == 7
        invalid = self.case == "invalid-utf8" and local == 7
        errors = ["stdout invalid UTF-8"] if invalid else []
        deadline = j.prefix.points[n-1]["qpc_before_ticks"]+timeout_ms*c.descriptor["frequency_hz"]//1000
        row = dict(contract_id="safetwin5g-reconnect-r5-process-v1", sequence=sequence, argv=argv, cleanup=cleanup,
                   timeout_ms=timeout_ms, max_output_bytes=max_output_bytes, cleanup_grace_ms=2000,
                   clock_id=c.descriptor["clock_id"], journal_event_before=ev, journal_event_after=len(j.events),
                   start_point=n, end_point=end, admitted_clock_before=admitted, counter_error=None,
                   checked_ticks=checked, go_before_ticks=before, go_after_ticks=after, completion_observed_ticks=observed,
                   cleanup_completed_ticks=cleaned, deadline_ticks=deadline, timer_due_100ns=(deadline-checked)*10000000//c.descriptor["frequency_hz"],
                   timer_armed=True, timer_signaled=timeout, cleanup_timer_armed=True, cleanup_timer_signaled=False, emergency_timer_only=False,
                   launcher_go_sent=True, job_assigned_before_go=True, job_closed=True, owned_launcher_pid=12345,
                   process_reaped=True, reader_threads_joined=True, timed_out=timeout, truncated=False,
                   process_errors=errors, cleanup_errors=[], returncode=3 if self.case == "nonzero" and local == 7 else 0,
                   timing_valid=timing, client_capture_complete=not timeout and not invalid, complete=timing and not timeout and not invalid,
                   stdout_utf8=not invalid, stderr_utf8=True, stdout=stdout, stderr=stderr)
        size = 0
        for stream in ("stdout", "stderr"):
            raw = b"\xff" if invalid and stream == "stdout" else row[stream].encode()
            row[stream] = raw.decode("utf-8", "replace")
            row[stream+"_base64"], row[stream+"_sha256"] = base64.b64encode(raw).decode(), hashlib.sha256(raw).hexdigest()
            size += len(raw)
        row["retained_output_bytes"] = size
        self.next_sequence, self.local = sequence+1, local+1
        if self.case == "deadline-middle" and local == 6:
            c.value += 86*c.descriptor["frequency_hz"]
        if self.case == "deadline-closure" and local == 14:
            c.value += 121*c.descriptor["frequency_hz"]
        return row


def capture_case(directory, case):
    directory.mkdir(exist_ok=False)
    c = Clock()
    if case == "closure-wide":
        capture = c.capture
        def wide():
            row = capture()
            if row["sequence"] == 18:
                row["qpc_after_ticks"] += 2000
                c.value += 2000
            return row
        c.capture = wide
    j = Journal(c, directory/"clock.jsonl")
    initial = {"point-reserve": 753, "point-boundary": 752, "cleanup-reserve": 768, "cleanup-capacity": 1010, "cleanup-boundary": 1008}.get(case, 2)
    for i in range(initial):
        j.checkpoint("bootstrap:"+str(i), cleanup=i >= 768)
    ledger = candidate.IdentifierLedger(directory/"identifiers.jsonl", c.descriptor["clock_id"])
    transport = FakeTransport(j, case)
    collector = candidate.Collector(j, transport, ledger)
    if case == "QPC-before":
        c.dead_at = c.reads+1
    if case == "deadline-before":
        c.value += 86*c.descriptor["frequency_hz"]
    if case == "ledger-fsync":
        emit = ledger._emit
        def failed(row):
            with patch("os.fsync", side_effect=OSError("fixture identifier sync failed")):
                emit(row)
        ledger._emit = failed
    count = 3 if case in ("official-15", "official-14", "changed-context") else 1
    mode = "official-service" if case.startswith("official-") or case == "changed-context" else "trace"
    try:
        with patch("subprocess.Popen", side_effect=AssertionError("collector fixture child forbidden")), \
             patch("socket.socket", side_effect=AssertionError("collector fixture socket forbidden")), \
             patch("ctypes.WinDLL", side_effect=AssertionError("collector fixture native clock/power forbidden")):
            for i in range(count):
                transport.prepare(ledger.next_identifier, mode)
                collector.collect("fixture-window-"+str(i+1), mode, cleanup=case in ("cleanup-reserve", "cleanup-capacity", "cleanup-boundary"))
        bundle = dict(case=case, evidence_label="fixture", measurement_scope="synthetic-collection-only", actual_processes_executed=0,
                      actual_power_requests_executed=0, network_commands_executed=0, windows=copy.deepcopy(collector.windows),
                      snapshot=j.snapshot(), ledger=ledger.snapshot(), independent=None, audit_error=None,
                      candidate=candidate.recovery_candidate(collector.windows), independent_candidate=None)
    finally:
        ledger.close()
        j.close()
    try:
        bundle["independent"] = audit(bundle["windows"], bundle["snapshot"], (directory/"clock.jsonl").read_bytes(), bundle["ledger"], (directory/"identifiers.jsonl").read_bytes())
        bundle["independent_candidate"] = packet_candidate(bundle["windows"], bundle["independent"])
    except ValueError as exc:
        bundle["audit_error"] = str(exc)
    return bundle


def check_case(bundle):
    name, windows = bundle["case"], bundle["windows"]
    assert bundle["evidence_label"] == "fixture" and bundle["measurement_scope"] == "synthetic-collection-only"
    assert bundle["actual_processes_executed"] == bundle["actual_power_requests_executed"] == bundle["network_commands_executed"] == 0
    assert all(w["collection_valid"] is (name in VALID) for w in windows)
    assert all(w["network_execution_authorized"] is w["whole_protocol_verified"] is w["rollback_verified"] is w["network_fix_validated"] is False for w in windows)
    assert bundle["candidate"]["packet_delivery_candidate"] is (name == "official-15")
    if name == "ledger-fsync":
        assert "ledger storage failed" in bundle["audit_error"]
        assert not windows[0]["commands"] and bundle["ledger"]["next_identifier"] == 10002
    else:
        assert bundle["audit_error"] is None, bundle["audit_error"]
        assert bundle["independent_candidate"] == bundle["candidate"]
        assert [d["collection_valid"] for d in bundle["independent"]["decisions"]] == [w["collection_valid"] for w in windows]
    if name in ("complete", "positive-skew", "negative-skew", "first-idle-loss", "official-source-3"):
        assert len(bundle["snapshot"]["points"]) == 18
    if name in ("source-ineligible", "wrong-image", "empty-prefix", "reused-prefix-id", "source-precision"):
        assert len(windows[0]["commands"]) == 7  # no packet dispatch
    if name == "first-idle-loss":
        assert windows[0]["result"]["ping"]["reply_sequences"] == [2, 3, 4, 5]
        assert windows[0]["result"]["trace"]["packets"][0]["fate"] == "nas_idle_nonretention_observed"
    if name == "point-boundary":
        assert len(bundle["snapshot"]["points"]) == 768
    if name == "cleanup-boundary":
        assert len(bundle["snapshot"]["points"]) == 1024
    if name in ("closure-wide", "deadline-closure"):
        assert windows[0]["parsed_result"] is not None and windows[0]["result"] is None


@pytest.mark.parametrize("case", CASES)
def test_retained_collection_cases(tmp_path, case):
    check_case(capture_case(tmp_path/"raw", case))


def test_identifier_capacity_and_exclusive_file(tmp_path):
    path = tmp_path/"ids.jsonl"
    ledger = candidate.IdentifierLedger(path, "a"*32)
    try:
        for n in range(99):
            assert ledger.reserve("fixture", "trace", False, clock_event=3, point=2, ticks=n, command_before=0)["identifier"] == 10001+n
        before = path.read_bytes()
        with pytest.raises(ValueError, match="exhausted"):
            ledger.reserve("no-wrap", "trace", False, clock_event=3, point=2, ticks=100, command_before=0)
        assert path.read_bytes() == before and ledger.next_identifier == 10100
    finally:
        ledger.close()
    with pytest.raises(FileExistsError):
        candidate.IdentifierLedger(path, "a"*32)
    assert path.read_bytes() == before


@pytest.mark.parametrize("field,value", [("collection_valid", False), ("identifier", 10002), ("reservation_persisted", False), ("deadline_ticks", 1),
                                      ("network_execution_authorized", True), ("end_point", 2), ("start_event", 1), ("final_check_ticks", 1), ("whole_protocol_verified", 1)])
def test_window_tampering(tmp_path, field, value):
    b = capture_case(tmp_path/"raw", "complete")
    b["windows"][0][field] = value
    with pytest.raises(ValueError):
        audit(b["windows"], b["snapshot"], (tmp_path/"raw/clock.jsonl").read_bytes(), b["ledger"], (tmp_path/"raw/identifiers.jsonl").read_bytes())


@pytest.mark.parametrize("target", ["raw-stream", "reservation", "deadline-admission", "clock-journal", "global-sequence", "parsed-result", "closure", "phase"])
def test_nested_tampering(tmp_path, target):
    b = capture_case(tmp_path/"raw", "complete")
    clock, ledger = (tmp_path/"raw/clock.jsonl").read_bytes(), (tmp_path/"raw/identifiers.jsonl").read_bytes()
    w = b["windows"][0]
    if target == "raw-stream":
        w["commands"][7]["stdout"] = "5/5 forged"
    elif target == "reservation":
        b["ledger"]["events"][1]["command_before"] = 1
        ledger = b"".join((json.dumps(e)+"\n").encode() for e in b["ledger"]["events"])
    elif target == "deadline-admission":
        w["checks"][0]["points_needed"] = 1
    elif target == "clock-journal":
        clock = clock[:-1]
    elif target == "global-sequence":
        w["commands"][4]["sequence"] = 1
    elif target == "parsed-result":
        w["parsed_result"]["ping"]["packets_received"] = 4
    elif target == "closure":
        w["closure_event_before"] -= 1
    elif target == "phase":
        w["failures"] = [dict(phase="closure", error="invented failure")]
    with pytest.raises(ValueError):
        audit(b["windows"], b["snapshot"], clock, b["ledger"], ledger)


def test_failed_attempt_id_not_reused(tmp_path):
    c = Clock()
    j = Journal(c, tmp_path/"clock.jsonl")
    j.checkpoint("bootstrap:0")
    j.checkpoint("bootstrap:1")
    ledger = candidate.IdentifierLedger(tmp_path/"identifiers.jsonl", c.descriptor["clock_id"])
    transport = FakeTransport(j, "source-ineligible")
    collector = candidate.Collector(j, transport, ledger)
    try:
        transport.prepare(10001, "trace")
        first = collector.collect("failed")
        transport.case = "complete"
        transport.prepare(10002, "trace")
        second = collector.collect("next")
        assert not first["collection_valid"] and second["collection_valid"]
        assert [w["identifier"] for w in collector.windows] == [10001, 10002]
        assert second["command_first"] == 8
        assert audit(collector.windows, j.snapshot(), (tmp_path/"clock.jsonl").read_bytes(), ledger.snapshot(), (tmp_path/"identifiers.jsonl").read_bytes())["collections_replayed"] == 2
    finally:
        ledger.close()
        j.close()


def test_import_and_clock_domain_boundary(tmp_path):
    from pathlib import Path
    text = Path(candidate.__file__).read_text()
    assert all(x not in text for x in ("subprocess", "socket", "WindowsClock", "PowerSetRequest", "monotonic_ns", "time.time"))
    c = Clock()
    j = Journal(c, tmp_path/"clock.jsonl")
    ledger = candidate.IdentifierLedger(tmp_path/"identifiers.jsonl", "b"*32)
    try:
        with pytest.raises(ValueError, match="one collection clock"):
            candidate.Collector(j, FakeTransport(j, "complete"), ledger)
    finally:
        ledger.close()
        j.close()


@pytest.mark.parametrize("bound,change,accepted", [("low", 0, True), ("low", -1, False), ("high", 0, True), ("high", 1, False)])
def test_exact_source_interval_edges(tmp_path, bound, change, accepted):
    b = capture_case(tmp_path/"raw", "complete")
    w, f = b["windows"][0], b["snapshot"]["descriptor"]["frequency_hz"]
    rows = w["commands"]
    sec, ns = rows[3]["stdout"].strip().split(".")
    start = int(sec)*10**9+int(ns)
    delta = ((rows[10]["go_before_ticks"]-rows[3]["completion_observed_ticks"])*10**9//f-1000000 if bound == "low"
             else (rows[10]["completion_observed_ticks"]-rows[3]["go_before_ticks"])*10**9//f+1000000)
    seconds, nanos = divmod(start+delta+change, 10**9)
    rows[10]["stdout"] = f"{seconds}.{nanos:09d}\n"
    for fn in (candidate.evaluate, read_window):
        if accepted:
            assert fn(rows, w["identifier"], w["mode"], f)["clock_brackets"][0]["source_delta_ns"] == delta
        else:
            with pytest.raises(ValueError, match="source elapsed interval"):
                fn(rows, w["identifier"], w["mode"], f)


def test_reservation_is_durable_before_first_dispatch(tmp_path):
    c = Clock()
    j = Journal(c, tmp_path/"clock.jsonl")
    j.checkpoint("bootstrap:0")
    j.checkpoint("bootstrap:1")
    path = tmp_path/"identifiers.jsonl"
    ledger = candidate.IdentifierLedger(path, c.descriptor["clock_id"])
    transport = FakeTransport(j, "complete")
    transport.prepare(10001, "trace")
    run = transport.run
    calls = []
    def checked_run(argv, **kwargs):
        raw = path.read_bytes()
        assert raw.endswith(b"\n")
        event = json.loads(raw.splitlines()[-1])
        assert event["identifier"] == 10001 and event["command_before"] == 0
        calls.append(argv)
        return run(argv, **kwargs)
    transport.run = checked_run
    try:
        assert candidate.Collector(j, transport, ledger).collect("durable")["collection_valid"]
        assert len(calls) == 15
    finally:
        ledger.close()
        j.close()


def test_failed_header_remains_owned_and_cannot_be_replaced(tmp_path):
    path = tmp_path/"identifiers.jsonl"
    with patch("os.fsync", side_effect=OSError("fixture header durability unavailable")), pytest.raises(OSError):
        candidate.IdentifierLedger(path, "a"*32)
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        candidate.IdentifierLedger(path, "a"*32)
    assert path.read_bytes() == original
