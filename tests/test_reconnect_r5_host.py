"""Synthetic clock/transport/power APIs. No actual child, socket or power call."""
import base64
import copy
import ctypes
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from sandbox import reconnect_r5_host as candidate
from sandbox.reconnect_r5_journal import Journal
from tests.test_reconnect_r5_process import Clock
from tools.audit_reconnect_r5_host import audit

REVISION = "a" * 64  # explicit fixture digest, not a committed execution lock
CASES = ("complete", "busy", "empty-query", "stderr", "nonzero", "idle-timeout", "idle-throw", "lease-exists",
         "power-create-fail", "power-set-fail", "power-set-throw", "power-clear-fail", "power-close-fail",
         "power-clear-interrupt", "QPC-before", "QPC-after-enable", "clock-step-after-enable", "wide-after-enable",
         "domain-after-enable", "source-thrown-after-enable", "admission-expired", "power-return-late", "reserve-before", "capacity-before-close",
         "journal-failed-after-enable", "lease-header-failed", "lease-footer-failed")


class FakeTransport:
    def __init__(self, journal, case):
        self.journal, self.clock, self.case = journal, journal.clock, case

    def run(self, argv, *, sequence, timeout_ms, max_output_bytes):
        if self.case == "idle-throw":
            raise OSError("fixture transport never dispatched")
        j, c = self.journal, self.clock
        n, ev = len(j.prefix.points), len(j.events)
        checked, go_before, go_after = c.ticks(), c.ticks(), c.ticks()
        observed, cleaned = c.ticks(), c.ticks()
        timeout = self.case == "idle-timeout"
        stdout = "17\n" if self.case == "busy" else "" if self.case == "empty-query" else "SAFETWIN_R5_IDLE_V1\r\n"
        stderr = "fixture query failure\n" if self.case == "stderr" else ""
        j.checkpoint("process:1:end")
        deadline = j.prefix.points[n - 1]["qpc_before_ticks"] + timeout_ms * c.descriptor["frequency_hz"] // 1000
        row = dict(contract_id="safetwin5g-reconnect-r5-process-v1", sequence=sequence, argv=argv, cleanup=False,
                   timeout_ms=timeout_ms, max_output_bytes=max_output_bytes, cleanup_grace_ms=2000,
                   clock_id=c.descriptor["clock_id"], journal_event_before=ev, journal_event_after=len(j.events),
                   start_point=n, end_point=n + 1, admitted_clock_before=True, counter_error=None,
                   checked_ticks=checked, go_before_ticks=go_before, go_after_ticks=go_after,
                   completion_observed_ticks=observed, cleanup_completed_ticks=cleaned, deadline_ticks=deadline,
                   timer_due_100ns=(deadline-checked)*10000000//c.descriptor["frequency_hz"], timer_armed=True,
                   timer_signaled=timeout, cleanup_timer_armed=True, cleanup_timer_signaled=False, emergency_timer_only=False,
                   launcher_go_sent=True, job_assigned_before_go=True, job_closed=True, owned_launcher_pid=12345,
                   process_reaped=True, reader_threads_joined=True, timed_out=timeout, truncated=False,
                   process_errors=[], cleanup_errors=[], returncode=3 if self.case in ("busy", "nonzero") else 0,
                   timing_valid=True, client_capture_complete=not timeout, complete=not timeout,
                   stdout_utf8=True, stderr_utf8=True, stdout=stdout, stderr=stderr,
                   retained_output_bytes=len(stdout.encode())+len(stderr.encode()))
        for k in ("stdout", "stderr"):
            raw = row[k].encode()
            row[k+"_base64"], row[k+"_sha256"] = base64.b64encode(raw).decode(), hashlib.sha256(raw).hexdigest()
        return row


class FakePower:
    def __init__(self, clock, case):
        self.clock, self.case, self.calls = clock, case, []

    def create(self):
        self.calls.append(("create",))
        return 2**64-1 if self.case == "power-create-fail" else 2468

    def set(self, handle):
        self.calls.append(("set", handle, 1))
        if self.case == "power-set-throw":
            raise OSError("fixture set outcome uncertain")
        if self.case == "power-return-late":
            self.clock.value += 36 * self.clock.descriptor["frequency_hz"]
        if self.case == "QPC-after-enable":
            self.clock.dead_at = self.clock.reads + 1
        if self.case == "clock-step-after-enable":
            self.clock.step_at = self.clock.sequence + 1
        if self.case == "domain-after-enable":
            self.clock.descriptor["clock_id"] = "b" * 32
        if self.case == "source-thrown-after-enable":
            self.clock.capture = lambda: (_ for _ in ()).throw(OSError("fixture unavailable UTC source"))
        return 0 if self.case == "power-set-fail" else 1

    def clear(self, handle):
        self.calls.append(("clear", handle, 1))
        if self.case == "power-clear-interrupt":
            raise KeyboardInterrupt("fixture clear interrupted")
        return 0 if self.case == "power-clear-fail" else 1

    def close(self, handle):
        self.calls.append(("close", handle))
        return 0 if self.case == "power-close-fail" else 1


def capture_case(directory, case):
    directory.mkdir(exist_ok=False)
    c = Clock()
    if case == "wide-after-enable":
        original = c.capture
        def wide():
            row = original()
            if row["sequence"] == 5:
                row["qpc_after_ticks"] += 2000
                c.value += 2000
            return row
        c.capture = wide
    j = Journal(c, directory / "clock.jsonl")
    for n in range(766 if case == "reserve-before" else 2):
        j.checkpoint("bootstrap:" + str(n))
    p = directory / "attempt.receipt.jsonl"
    lease = candidate.AttemptLease(p, owner_pid=c.descriptor["owner_pid"], clock_id=c.descriptor["clock_id"], revision_sha256=REVISION)
    if case == "lease-exists":
        p.write_bytes(b"unowned fixture receipt, never replaced\n")
    api = FakePower(c, case)
    host = candidate.HostGuard(j, FakeTransport(j, case), lease, candidate.PowerLease(lambda: api))
    if case == "QPC-before":
        c.dead_at = c.reads + 1
    if case == "admission-expired":
        c.value += 36*c.descriptor["frequency_hz"]
    if case == "lease-header-failed":
        lease._write = lambda value: (_ for _ in ()).throw(OSError("fixture receipt storage failed"))
    try:
        with patch("subprocess.Popen", side_effect=AssertionError("host fixture subprocess forbidden")), \
             patch("socket.socket", side_effect=AssertionError("host fixture socket forbidden")), \
             patch("ctypes.WinDLL", side_effect=AssertionError("host fixture native power/clock forbidden")):
            host.start()
            if case == "capacity-before-close":
                while len(j.prefix.points) < 1024:
                    j.checkpoint("fixture-capacity", cleanup=True)
            if case == "lease-footer-failed":
                lease._write = lambda value: (_ for _ in ()).throw(OSError("fixture receipt footer failed"))
            if case == "journal-failed-after-enable":
                with patch("os.fsync", side_effect=OSError("fixture journal sync failure")):
                    host.close()
            else:
                host.close()
        result = dict(case=case, evidence_label="fixture", measurement_scope="synthetic-host-transport-power-only",
                      actual_power_requests_executed=0, actual_processes_executed=0, network_commands_executed=0,
                      host=host.snapshot(), snapshot=j.snapshot(), api_calls=api.calls, independent=None, audit_error=None)
    finally:
        j.close()
    # Never export the content of a receipt we did not create.
    raw_receipt = p.read_bytes() if lease.record["created"] else None
    if case == "lease-exists":
        assert p.read_bytes() == b"unowned fixture receipt, never replaced\n"
    try:
        result["independent"] = audit(result["host"], result["snapshot"], (directory/"clock.jsonl").read_bytes(), raw_receipt)
    except ValueError as exc:
        result["audit_error"] = str(exc)
    result["receipt_owned"] = lease.record["created"]
    return result


def check_case(bundle):
    assert bundle["evidence_label"] == "fixture" and bundle["measurement_scope"] == "synthetic-host-transport-power-only"
    assert bundle["actual_power_requests_executed"] == bundle["actual_processes_executed"] == bundle["network_commands_executed"] == 0
    h, case = bundle["host"], bundle["case"]
    assert h["component_complete"] is (case == "complete")
    assert h["closed"] and all(o["called"] for o in h["operations"] if o["cleanup"])
    assert [o["name"] for o in h["operations"]][-2:] == ["clear", "release"]
    if case in ("journal-failed-after-enable", "lease-header-failed", "lease-footer-failed"):
        assert bundle["audit_error"] and ("storage" in bundle["audit_error"] or "durability" in bundle["audit_error"])
    else:
        assert bundle["audit_error"] is None, bundle["audit_error"]
        assert bundle["independent"]["host_component_complete"] == h["component_complete"]
    if case == "complete":
        assert bundle["independent"]["clock_points"] == 7
    assert h["network_execution_authorized"] is h["whole_protocol_verified"] is h["service_restored"] is False


@pytest.mark.parametrize("case", CASES)
def test_retained_host_cases(tmp_path, case):
    check_case(capture_case(tmp_path / "raw", case))


@pytest.mark.parametrize("pid", [None, True, 0, -1, 2**32, "4"])
def test_strict_pid(pid):
    with pytest.raises(ValueError):
        candidate.idle_query(pid)


def test_query_covers_r5_future_and_opaque_processes():
    import re
    script = candidate.idle_query(123)[-1]
    pattern = script.split("-match '")[-1].split("'")[0]
    for name in ("run_phase7.py", "run_recovery_pilot.py", "run_reconnect.py", "run_reconnect_r5.py", "run_reconnect_r27.py"):
        assert re.search(pattern, name)
    assert "$ErrorActionPreference='Stop'" in script and "CommandLine -eq $null" in script
    from tools.audit_reconnect_r5_host import idle_command
    assert candidate.idle_query(123) == idle_command(123)


def test_receipt_persists_and_blocks_second_attempt(tmp_path):
    p = tmp_path / "receipt"
    a = candidate.AttemptLease(p, owner_pid=1, clock_id="1"*32, revision_sha256=REVISION)
    a.acquire(); a.close()
    prior = p.read_bytes()
    b = candidate.AttemptLease(p, owner_pid=2, clock_id="2"*32, revision_sha256=REVISION)
    with pytest.raises(FileExistsError):
        b.acquire()
    b.close()
    assert p.read_bytes() == prior and a.record["handle_closed"]


def test_power_close_is_independent_idempotent_and_owned():
    api = FakePower(Clock(), "power-clear-interrupt")
    lease = candidate.PowerLease(lambda: api)
    lease.enable()
    with pytest.raises(OSError):
        lease.close()
    previous = copy.deepcopy(api.calls)
    lease.close()
    assert api.calls == previous == [("create",), ("set", 2468, 1), ("clear", 2468, 1), ("close", 2468)]
    with pytest.raises(PermissionError):
        lease.enable()


def test_native_abi_uses_only_owned_system_request():
    class Function:
        def __init__(self, result): self.result, self.calls = result, []
        def __call__(self, *args): self.calls.append(args); return self.result
    class API:
        PowerCreateRequest = Function(9876)
        PowerSetRequest = Function(1)
        PowerClearRequest = Function(1)
        CloseHandle = Function(1)
    api = API()
    k = candidate.KernelPower(api=api)
    assert ctypes.sizeof(k.context) == 32 and k.context.version == 0 and k.context.flags == 1
    assert k.context.reason.simple == candidate.REASON
    assert k.create() == 9876 and k.set(9876) == k.clear(9876) == k.close(9876) == 1
    assert api.PowerSetRequest.calls == [(9876, 1)] and api.PowerClearRequest.calls == [(9876, 1)]
    assert api.CloseHandle.calls == [(9876,)]


@pytest.mark.parametrize("change", ["promote", "owner", "clock", "deadline", "bool-tick", "point", "skip-clear", "power-return", "receipt", "idle-byte", "erase-timeout", "receipt-return"])
def test_independent_rejects_resealed_tamper(tmp_path, change):
    b = capture_case(tmp_path / "raw", "idle-timeout" if change == "erase-timeout" else "complete")
    h = b["host"]
    receipt = (tmp_path/"raw/attempt.receipt.jsonl").read_bytes()
    if change == "promote": h["service_restored"] = True
    if change == "owner": h["owner_pid"] += 1
    if change == "clock": h["clock_id"] = "c"*32
    if change == "deadline": h["admission_deadline_ticks"] += 1
    if change == "bool-tick": h["operations"][0]["checked_ticks"] = True
    if change == "point": h["operations"][1]["start_point"] -= 1
    if change == "skip-clear": h["operations"][-2]["called"] = False
    if change == "power-return": h["power"]["calls"][1]["result"] = 0
    if change == "receipt": receipt = receipt.replace(b'close-intent', b'false-intent')
    if change == "idle-byte": h["idle_command"]["stdout"] += "x"
    if change == "erase-timeout": h["admitted"] = h["component_complete"] = True
    if change == "receipt-return": h["operations"][0]["returned"] = False
    with pytest.raises((ValueError, TypeError, KeyError)):
        audit(h, b["snapshot"], (tmp_path/"raw/clock.jsonl").read_bytes(), receipt)


def test_audit_does_not_use_candidate_predicates(tmp_path):
    b = capture_case(tmp_path/"raw", "complete")
    with patch.object(candidate.HostGuard, "snapshot", side_effect=AssertionError("candidate disabled")), \
         patch.object(candidate.HostGuard, "_operation", side_effect=AssertionError("candidate disabled")), \
         patch.object(candidate, "idle_query", side_effect=AssertionError("candidate disabled")):
        assert audit(b["host"], b["snapshot"], (tmp_path/"raw/clock.jsonl").read_bytes(),
                     (tmp_path/"raw/attempt.receipt.jsonl").read_bytes())["host_component_complete"]


def test_component_has_no_alternate_clock_or_destructive_path_api():
    import ast
    source = Path(candidate.__file__).read_text()
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [n.name for n in node.names] if isinstance(node, ast.Import) else [node.module]
            assert not any(n in ("time", "subprocess", "socket", "shutil") for n in names)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in ("unlink", "remove", "rename", "replace", "rmdir", "rmtree", "SetThreadExecutionState")


def test_host_rejects_mixed_journal_and_revision(tmp_path):
    clock = Clock()
    j = Journal(clock, tmp_path/"clock.jsonl")
    lease = candidate.AttemptLease(tmp_path/"receipt", owner_pid=clock.descriptor["owner_pid"], clock_id=clock.descriptor["clock_id"], revision_sha256=REVISION)
    transport = FakeTransport(j, "complete")
    try:
        transport.clock = Clock()
        with pytest.raises(ValueError, match="share one journal"):
            candidate.HostGuard(j, transport, lease, candidate.PowerLease())
        transport.clock = clock
        lease.header["revision_sha256"] = "unknown"
        with pytest.raises(ValueError, match="exact execution revision"):
            candidate.HostGuard(j, transport, lease, candidate.PowerLease())
        assert not (tmp_path/"receipt").exists()
    finally:
        j.close()


def test_repeated_host_lifecycle_cannot_repeat_power_or_idle(tmp_path):
    c = Clock(); j = Journal(c, tmp_path/"clock.jsonl")
    try:
        j.checkpoint("bootstrap:0"); j.checkpoint("bootstrap:1")
        lease = candidate.AttemptLease(tmp_path/"receipt", owner_pid=c.descriptor["owner_pid"], clock_id=c.descriptor["clock_id"], revision_sha256=REVISION)
        api = FakePower(c, "complete")
        host = candidate.HostGuard(j, FakeTransport(j, "complete"), lease, candidate.PowerLease(lambda: api))
        assert host.start()
        with pytest.raises(PermissionError): host.start()
        host.close()
        old = copy.deepcopy(api.calls), j.snapshot()
        host.close()
        assert old == (api.calls, j.snapshot())
        with pytest.raises(PermissionError): host.start()
    finally:
        j.close()
