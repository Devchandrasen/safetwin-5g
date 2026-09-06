"""Invented whole R5 protocol, not a clock/power/daemon measurement.

The old fixture's metadata and trace generator are reused as in-memory data.
Its R3/R4 runner, transport.run, clocks and actuation methods are NOT invoked.
"""
import base64
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sandbox import run_reconnect_r5 as runner
from sandbox.reconnect_r5_journal import Journal
from sandbox.reconnect_r5_host import AttemptLease, HostGuard, PowerLease
from tests.reconnect_r4_execution_fixture import Transport as InventedState, EPOCH
from tests.test_reconnect_r5_clock import descriptor, set_utc

REVISION, DIGEST = "a"*40, "b"*64
LOCK = runner.ROOT/"config/experiments/reconnect-r5-execution-lock.json"
if LOCK.is_file():
    DIGEST = hashlib.sha256(LOCK.read_bytes()).hexdigest()
CASES = ("complete", "bad-baseline", "incomplete-trace", "busy-host", "existing-receipt",
         "bad-approval", "changed-approval", "future-approval", "prior-attempt", "wrong-receipt",
         "wrong-revision", "failed-switch", "failed-final-switch", "failed-reset", "failed-health",
         "failed-cleanup", "unknown-qdisc", "missing-fresh-pdu", "failed-official-service",
         "power-enable-failed", "power-clear-failed", "power-close-failed", "clock-step",
         "wide-clock", "source-unavailable", "settle-short", "settle-throw", "client-timeout",
         "global-budget", "execution-fsync", "ledger-fsync", "journal-fsync", "official-tag-drift")


class Clock:
    def __init__(self, engine):
        self.engine, self.descriptor, self.sequence = engine, descriptor(), 0
        self.step_at = self.wide_at = None
        self.unavailable = False

    def ticks(self):
        self.engine.sleep(0.000001)
        return 1000000000+round(self.engine.value*self.descriptor["frequency_hz"])

    def capture(self):
        self.sequence += 1
        if self.unavailable:
            raise OSError("invented precise UTC unavailable")
        row = dict(sequence=self.sequence, clock_id=self.descriptor["clock_id"], qpc_before_ticks=self.ticks(),
                   qpc_after_ticks=None, filetime_low=None, filetime_high=None, utc_ns=None, capture_error=None)
        set_utc(row, EPOCH+(row["qpc_before_ticks"]-1000000000)*100+(2000000 if self.sequence == self.step_at else 0))
        if self.sequence == self.wide_at:
            self.engine.sleep(0.0002)
        row["qpc_after_ticks"] = self.ticks()
        return row


class Transport:
    def __init__(self, output, case):
        self.state = InventedState(output, case)
        self.clock, self.journal, self.next_sequence = Clock(self.state.clock), None, 1
        self.case, self.runner, self.injected, self.generation = case, None, False, 0
        for c in (runner.CORE, runner.GNB, runner.UE):
            self.state.engine.containers[c]["State"]["StartedAt"] = "2026-09-04T23:59:59+00:00"

    def invoke(self, argv):
        state, r = self.state, self.runner
        state.backend = SimpleNamespace(unit_id=r.unit.replace("r5:", "r4:"), current_name=r.label)
        if argv[0] == "powershell.exe":
            state.clock.sleep(0.01)
            return ("9876\n", 3) if self.case == "busy-host" else ("SAFETWIN_R5_IDLE_V1\n", 0)
        if argv[0] == "git":
            state.clock.sleep(0.01)
            return ("c"*40 if self.case == "wrong-revision" else REVISION)+"\n", 0
        if self.case == "official-tag-drift" and r.cleanup and r.label == "switch-official-tag-"+runner.GNB:
            return "sha256:"+"f"*64+"\n", 0
        if argv[:2] == ["docker", "compose"] and "up" in argv:
            role = "derived" if argv in [runner.image_command("derived", c) for c in (runner.GNB, runner.UE)] else "official"
            container = runner.GNB if argv[-1] == "ueransim-gnb" else runner.UE
            self.generation += 1
            row = state.engine.containers[container]
            row["Id"] = hashlib.sha256((role+container+str(self.generation)).encode()).hexdigest()
            row["Image"], row["Config"]["Image"] = runner.IMAGES[role+"_image_id"], runner.IMAGES[role+"_tag"]
            row["Config"]["Labels"]["safetwin5g.derived.revision"] = "reconnect-r3-trace" if role == "derived" else None
            state.clock.sleep(0.01)
            row["State"]["StartedAt"] = state.clock.now()
            state.engine.events[container] = []
            state.engine.event(container, "[fixture] newly created component ready")
            if container == runner.UE:
                state.engine.fake_role = role
            failed = container == runner.GNB and (role == "derived" and self.case == "failed-switch" or role == "official" and self.case == "failed-final-switch")
            return ("invented uncertain image application\n", 1) if failed else ("", 0)
        if self.case == "unknown-qdisc" and r.unit == "final-rollback" and r.label == "rollback-inspect-eth0":
            return '[{"kind":"netem","handle":"9999:","root":true}]', 0
        if self.case == "failed-official-service" and r.unit == "final-rollback" and argv[:4] == ["docker", "exec", runner.UE, "ping"] and not self.injected:
            state.engine.loss_next, self.injected = True, True
        return state.invoke(argv)

    def run(self, argv, *, sequence, timeout_ms, max_output_bytes, cleanup=False):
        assert sequence == self.next_sequence
        j, c, r = self.journal, self.clock, self.runner
        n, ev, admitted = len(j.prefix.points), len(j.events), j.admitted()
        checked, before, after = c.ticks(), c.ticks(), c.ticks()
        output, code = self.invoke(argv)
        inject = (self.case in ("changed-approval", "clock-step", "wide-clock", "source-unavailable", "client-timeout", "global-budget")
                  and not self.injected and r.unit == "r5:control-before" and r.label == "baseline:0" and argv[:4] == ["docker", "exec", runner.UE, "ping"])
        timeout = False
        if inject:
            self.injected = True
            if self.case == "changed-approval":
                r.approval["live_actuation"] = True
            elif self.case == "clock-step":
                c.step_at = c.sequence+1
            elif self.case == "wide-clock":
                c.wide_at = c.sequence+1
            elif self.case == "source-unavailable":
                c.unavailable = True
            elif self.case == "client-timeout":
                timeout, code = True, -999
                output = output[:70]
            elif self.case == "global-budget":
                c.engine.sleep(1501)
        observed, cleaned = c.ticks(), c.ticks()
        cleanup_errors = []
        try:
            j.checkpoint("process:"+str(sequence)+":end", cleanup=cleanup)
        except BaseException as exc:
            cleanup_errors.append("clock journal: "+type(exc).__name__+": "+str(exc))
        end = len(j.prefix.points) if len(j.prefix.points) > n else None
        anchor = j.prefix.points[n-1]
        deadline = anchor["qpc_before_ticks"]+timeout_ms*c.descriptor["frequency_hz"]//1000
        timing = bool(end and j.prefix.status()["clock_capture_valid"] and not j.capture_failed and not j.failure and observed < deadline)
        due = (deadline-checked)*10000000//c.descriptor["frequency_hz"]
        emergency = bool(cleanup and due <= 0)
        row = dict(contract_id="safetwin5g-reconnect-r5-process-v1", sequence=sequence, argv=list(argv), cleanup=cleanup,
                   timeout_ms=timeout_ms, max_output_bytes=max_output_bytes, cleanup_grace_ms=2000,
                   clock_id=j.prefix.descriptor["clock_id"], journal_event_before=ev, journal_event_after=len(j.events),
                   start_point=n, end_point=end, admitted_clock_before=admitted, counter_error=None,
                   checked_ticks=checked, go_before_ticks=before, go_after_ticks=after, completion_observed_ticks=observed,
                   cleanup_completed_ticks=cleaned, deadline_ticks=deadline, timer_due_100ns=due if due > 0 else timeout_ms*10000,
                   timer_armed=True, timer_signaled=timeout, cleanup_timer_armed=True, cleanup_timer_signaled=False, emergency_timer_only=emergency,
                   launcher_go_sent=True, job_assigned_before_go=True, job_closed=True, owned_launcher_pid=12345,
                   process_reaped=True, reader_threads_joined=True, timed_out=timeout, truncated=False,
                   process_errors=[], cleanup_errors=cleanup_errors, returncode=code, timing_valid=timing and not emergency, client_capture_complete=not timeout and not cleanup_errors,
                   complete=timing and not emergency and not timeout and not cleanup_errors, stdout_utf8=True, stderr_utf8=True, stdout=output, stderr="",
                   retained_output_bytes=len(output.encode()))
        for stream in ("stdout", "stderr"):
            raw = row[stream].encode()
            row[stream+"_base64"], row[stream+"_sha256"] = base64.b64encode(raw).decode(), hashlib.sha256(raw).hexdigest()
        self.next_sequence += 1
        return row


def capture_case(path, case="complete"):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=False)
    t = Transport(path, case)
    j = Journal(t.clock, path/"clock.jsonl")
    t.journal = j
    j.checkpoint("bootstrap:0")
    j.checkpoint("bootstrap:1")
    approval = dict(runner.approval_expected(REVISION, DIGEST), recorded_at="2026-09-05T00:00:00+00:00")
    if case == "bad-approval":
        approval["operator_validation"] = True
    if case == "future-approval":
        approval["recorded_at"] = "2027-01-01T00:00:00+00:00"
    prerequisites = dict(committed_sources=True, prior_r5_attempt=case == "prior-attempt", older_guards_absent=True,
                         receipt_path=runner.RECEIPT, ledger_path="identifiers.jsonl", fixture=True)
    receipt_path = path/("wrong-receipt.jsonl" if case == "wrong-receipt" else "attempt-receipt.jsonl")
    if case == "existing-receipt":
        receipt_path.write_bytes(b"unowned sentinel: do not overwrite\n")
    class Power:
        def create(self): return 1234
        def set(self, handle): return 0 if case == "power-enable-failed" else 1
        def clear(self, handle): return 0 if case == "power-clear-failed" else 1
        def close(self, handle): return 0 if case == "power-close-failed" else 1
    def host(transport):
        lease = AttemptLease(receipt_path, owner_pid=t.clock.descriptor["owner_pid"], clock_id=t.clock.descriptor["clock_id"], revision_sha256=DIGEST)
        return HostGuard(j, transport, lease, PowerLease(Power))
    def wait(ms):
        if case == "settle-throw" and ms == 5000:
            raise OSError("invented settling failure")
        if case != "settle-short" or ms != 5000:
            t.state.clock.sleep(ms/1000)
    r = runner.Runner(path, j, t, host, wait, approval, REVISION, DIGEST, prerequisites)
    t.runner = r
    import os
    real_sync = os.fsync
    def sync(fd):
        target = {"execution-fsync": r.log.handle, "ledger-fsync": getattr(r.ledger, "handle", None), "journal-fsync": j.handle}.get(case)
        if target is not None and not target.closed and fd == target.fileno() and r.unit == "r5:control-before":
            raise OSError("invented "+case)
        return real_sync(fd)
    try:
        with patch("subprocess.Popen", side_effect=AssertionError("full fixture forbids process dispatch")), \
             patch("socket.socket", side_effect=AssertionError("full fixture forbids sockets")), \
             patch("ctypes.WinDLL", side_effect=AssertionError("full fixture forbids native clock/power")), \
             patch("os.fsync", side_effect=sync):
            result = r.execute()
    finally:
        j.close()
    owned = bool(result["host"] and result["host"]["lease"]["created"])
    bundle = dict(case=case, result=result, fixture_scope="invented-whole-protocol-no-process-no-network-no-power",
                  owned_receipt=receipt_path.read_text() if owned else None)
    (path/"capture.json").write_text(json.dumps(bundle, indent=2, allow_nan=False)+"\n", encoding="utf-8")
    return bundle
