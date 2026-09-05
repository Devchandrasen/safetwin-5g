"""Owned local child processes with explicit synthetic/native clock separation."""
import base64
import copy
import ctypes
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

import pytest
from sandbox.reconnect_r5_clock import WindowsClock
from sandbox.reconnect_r5_journal import Journal
from sandbox import reconnect_r5_process as candidate
from tests.test_reconnect_r5_clock import descriptor, set_utc
from tools.audit_reconnect_r5_process import audit

CHILD = str(Path(__file__).with_name("reconnect_r4_process_child.py"))


class Clock:
    """Invented timestamps for deterministic plumbing, never measured latency."""
    def __init__(self):
        self.descriptor = descriptor()
        self.value, self.reads, self.sequence = 1000000000, 0, 0
        self.dead_at, self.step_at = None, None

    def ticks(self):
        self.reads += 1
        if self.dead_at is not None and self.reads >= self.dead_at:
            raise OSError("fixture QPC source unavailable")
        self.value += 10
        return self.value

    def capture(self):
        self.sequence += 1
        row = dict(sequence=self.sequence, clock_id=self.descriptor["clock_id"], qpc_before_ticks=None,
                   qpc_after_ticks=None, filetime_low=None, filetime_high=None, utc_ns=None, capture_error=None)
        try:
            row["qpc_before_ticks"] = self.ticks()
            utc = 1788566400000000000 + (self.value - 1000000000) * 100
            set_utc(row, utc + (2000000 if self.sequence == self.step_at else 0))
            row["qpc_after_ticks"] = self.ticks()
        except OSError as exc:
            row["capture_error"] = str(exc)
        return row


def argv(mode):
    return [sys.executable, "-I", "-S", CHILD, mode]


CASES = ("streams", "flood", "sleep", "descendant", "invalid-utf8", "exit-failure", "job-denied", "timer-denied",
         "QPC-before-normal", "QPC-before-cleanup", "QPC-dead-cleanup-timeout", "QPC-after-GO", "clock-step", "capacity-cleanup", "reserve-cleanup",
         "timer-wait-failed", "timer-wait-after-GO", "job-close-failed", "journal-failed", "expired-shared-envelope", "native-shared-envelopes")


def capture_case(directory, case):
    directory.mkdir(exist_ok=False)
    clock = WindowsClock() if case == "native-shared-envelopes" else Clock()
    journal = Journal(clock, directory / "clock.jsonl")
    rows = []
    try:
        for i in range(1024 if case == "capacity-cleanup" else 768 if case == "reserve-cleanup" else 2):
            journal.checkpoint("bootstrap:" + str(i), cleanup=i >= 768)
        mode = case if case in ("streams", "flood", "sleep", "descendant", "invalid-utf8", "exit-failure") else "streams"
        if case == "QPC-dead-cleanup-timeout":
            mode = "sleep"
        cleanup = case in ("QPC-before-cleanup", "QPC-dead-cleanup-timeout", "capacity-cleanup", "reserve-cleanup")
        command = argv(mode)
        options = {}
        if case == "job-denied":
            def denied(_):
                raise OSError("fixture job assignment denied")
            options["job_factory"] = denied
        elif case == "timer-denied":
            def denied(_):
                raise OSError("fixture relative timer unavailable")
            options["timer_factory"] = denied
        elif case == "job-close-failed":
            class BadClose(candidate.OwnedJob):
                def close(self):
                    super().close()
                    raise OSError("fixture reported close failure after actual owned close")
            options["job_factory"] = BadClose
        elif case in ("timer-wait-failed", "timer-wait-after-GO"):
            class BadWait(candidate.RelativeTimer):
                calls = 0
                def expired(self, wait_ms=0):
                    self.calls += 1
                    if case == "timer-wait-failed" or self.calls >= 3:
                        raise OSError("fixture timer wait API failed")
                    return super().expired(wait_ms)
            options["timer_factory"] = BadWait
        if case in ("QPC-before-normal", "QPC-before-cleanup", "QPC-dead-cleanup-timeout"):
            clock.dead_at = clock.reads + 1
        if case == "QPC-after-GO":
            clock.dead_at = clock.reads + 3
        if case == "clock-step":
            clock.step_at = 3
        adapter = candidate.BoundedProcess(journal, [command], cleanup_allowed=[command], **options)
        def run(cleanup_flag=False):
            row = adapter.run(command, sequence=len(rows) + 1, timeout_ms=500 if mode in ("sleep", "descendant") else 2000,
                              max_output_bytes=32768 if mode == "flood" else 1048576, cleanup=cleanup_flag)
            rows.append(row)
        if case == "journal-failed":
            with patch("os.fsync", side_effect=OSError("fixture storage sync failed")):
                run()
                run(True)
        else:
            run(cleanup)
            if case in ("QPC-after-GO", "clock-step"):
                run(True)
            elif case == "native-shared-envelopes":
                run()
            elif case == "expired-shared-envelope":
                clock.value += 30000000  # invented 3 seconds, all charged to next envelope
                run()
        snapshot = journal.snapshot()
        try:
            replayed = audit(rows, snapshot, (directory / "clock.jsonl").read_bytes(), [command], [command])
            audit_error = None
        except (ValueError, KeyError, TypeError) as exc:
            replayed, audit_error = None, type(exc).__name__ + ": " + str(exc)
        return dict(evidence_label="fixture", clock_scope="native-owned-process-only" if case == "native-shared-envelopes" else "synthetic-clock",
                    case=case, allowed=[command], cleanup_allowed=[command], records=rows, snapshot=snapshot,
                    independent=replayed, audit_error=audit_error, network_commands_executed=0,
                    network_execution_authorized=False, whole_protocol_verified=False, official_rollback_verified=False)
    finally:
        journal.close()


def check_case(bundle):
    name, rows = bundle["case"], bundle["records"]
    if name == "journal-failed":
        assert bundle["independent"] is None and "storage failed" in bundle["audit_error"]
        assert all(r["launcher_go_sent"] and not r["complete"] for r in rows)
        return
    assert bundle["audit_error"] is None, bundle["audit_error"]
    assert bundle["independent"]["observation_audit_passed"]
    if name in ("streams", "exit-failure", "reserve-cleanup", "expired-shared-envelope"):
        assert rows[0]["complete"], rows[0]
    elif name == "native-shared-envelopes":
        # Native scheduling/clock rejection is retained, not retried or selected
        # away. This check validates accounting, not a positive native endpoint.
        assert rows[1]["start_point"] == rows[0]["end_point"]
        assert len(bundle["snapshot"]["points"]) <= 4
    else:
        assert not rows[0]["complete"], rows[0]
    if name in ("sleep", "descendant", "QPC-dead-cleanup-timeout"):
        assert rows[0]["timed_out"] and rows[0]["process_reaped"] and rows[0]["reader_threads_joined"]
        assert "partial-before-timeout" in rows[0]["stdout"]
    if name == "flood":
        assert rows[0]["truncated"] and rows[0]["retained_output_bytes"] == 32768
    if name == "invalid-utf8":
        assert base64.b64decode(rows[0]["stdout_base64"]) == b"valid\xffpartial"
    if name == "exit-failure":
        assert rows[0]["returncode"] == 7
    if name in ("job-denied", "timer-denied", "QPC-before-normal", "timer-wait-failed"):
        assert not rows[0]["launcher_go_sent"]
    if name == "QPC-before-cleanup":
        assert rows[0]["launcher_go_sent"] and rows[0]["emergency_timer_only"] and rows[0]["stdout"] == "stdout\n"
    if name == "QPC-dead-cleanup-timeout":
        assert rows[0]["launcher_go_sent"] and rows[0]["emergency_timer_only"] and rows[0]["timer_signaled"]
    if name in ("QPC-after-GO", "clock-step"):
        assert rows[1]["launcher_go_sent"] and not rows[1]["complete"] and rows[1]["stdout"] == "stdout\n"
    if name == "capacity-cleanup":
        assert rows[0]["launcher_go_sent"] and rows[0]["end_point"] is None
    if name == "timer-wait-after-GO":
        assert rows[0]["launcher_go_sent"] and not rows[0]["complete"]
    if name == "expired-shared-envelope":
        assert rows[0]["end_point"] == rows[1]["start_point"]
        assert rows[1]["timed_out"] and not rows[1]["launcher_go_sent"] and not rows[1]["complete"]
    if name == "descendant":
        pid = int(rows[0]["stdout"].splitlines()[0])
        api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.OpenProcess.argtypes = [ctypes.wintypes.DWORD, ctypes.wintypes.BOOL, ctypes.wintypes.DWORD]
        api.OpenProcess.restype = ctypes.wintypes.HANDLE
        api.GetExitCodeProcess.argtypes = [ctypes.wintypes.HANDLE, ctypes.POINTER(ctypes.wintypes.DWORD)]
        api.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
        handle = api.OpenProcess(0x1000, False, pid)
        if handle:
            try:
                status = ctypes.wintypes.DWORD()
                assert api.GetExitCodeProcess(handle, ctypes.byref(status)) and status.value != 259
            finally:
                api.CloseHandle(handle)


@pytest.mark.skipif(os.name != "nt", reason="Windows-owned process fixture")
@pytest.mark.parametrize("case", [name for name in CASES if name != "native-shared-envelopes"])
def test_owned_capture_cases(tmp_path, case):
    with patch("socket.socket", side_effect=AssertionError("socket forbidden")):
        bundle = capture_case(tmp_path / case, case)
        check_case(bundle)


def test_explicit_allowlist_cleanup_scope_sequence_and_types(tmp_path):
    journal = Journal(Clock(), tmp_path / "clock.jsonl")
    try:
        adapter = candidate.BoundedProcess(journal, [argv("streams")])
        with patch("subprocess.Popen", side_effect=AssertionError("unapproved process started")):
            for kwargs in ({"cleanup": True}, {"timeout_ms": True}, {"timeout_ms": 35001}, {"max_output_bytes": 1048577}, {"sequence": 2}):
                with pytest.raises(PermissionError):
                    adapter.run(argv("streams"), **dict(sequence=1, **kwargs) if "sequence" not in kwargs else kwargs)
            with pytest.raises(PermissionError):
                adapter.run(["docker", "ps"], sequence=1)
        with pytest.raises(PermissionError):
            candidate.BoundedProcess(journal, [], cleanup_allowed=[argv("streams")])
    finally:
        journal.close()


@pytest.mark.parametrize("mutation", ["domain", "GO", "bytes", "deadline", "timer", "point", "float", "claim", "scope", "missing-row"])
def test_independent_resealed_process_tampering(tmp_path, mutation):
    b = capture_case(tmp_path / "original", "streams")
    rows = copy.deepcopy(b["records"])
    r = rows[0]
    if mutation == "domain": r["clock_id"] = "f" * 32
    elif mutation == "GO": r["job_assigned_before_go"] = False
    elif mutation == "bytes": r["stdout_base64"] = "Zm9yZ2Vk"
    elif mutation == "deadline": r["deadline_ticks"] += 1
    elif mutation == "timer": r["timer_due_100ns"] -= 1
    elif mutation == "point": r["start_point"] = 1
    elif mutation == "float": r["go_before_ticks"] = float(r["go_before_ticks"])
    elif mutation == "claim": r["complete"] = False
    elif mutation == "scope": r["argv"] = ["docker", "ps"]
    else: rows = []
    with pytest.raises(ValueError):
        audit(rows, b["snapshot"], (tmp_path / "original/clock.jsonl").read_bytes(), b["allowed"], b["cleanup_allowed"])


def test_auditor_does_not_call_process_or_clock_candidate(tmp_path):
    b = capture_case(tmp_path / "original", "streams")
    with patch.object(candidate, "complete", side_effect=AssertionError("candidate forbidden")), \
         patch.object(candidate.BoundedProcess, "run", side_effect=AssertionError("candidate forbidden")), \
         patch("sandbox.reconnect_r5_clock.evaluate", side_effect=AssertionError("candidate forbidden")):
        assert audit(b["records"], b["snapshot"], (tmp_path / "original/clock.jsonl").read_bytes(), b["allowed"], b["cleanup_allowed"])["observation_audit_passed"]


def test_frozen_r4_process_and_python_clock_adapters_are_not_used(tmp_path):
    import ast
    source = Path(candidate.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert not any(isinstance(n, ast.Import) and any(a.name == "time" for a in n.names) for n in ast.walk(tree))
    assert not any(isinstance(n, ast.ImportFrom) and n.module == "time" for n in ast.walk(tree))
    for name in ("time_ns", "monotonic", "monotonic_ns", "perf_counter", "perf_counter_ns", "SetThreadExecutionState"):
        assert not any(isinstance(n, ast.Attribute) and n.attr == name for n in ast.walk(tree))
    with patch("sandbox.reconnect_r4_process.BoundedProcess.run", side_effect=AssertionError("old clock adapter forbidden")):
        b = capture_case(tmp_path / "isolated-helper-reuse", "streams")
        check_case(b)
