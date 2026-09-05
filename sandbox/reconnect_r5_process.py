"""R5 owned-client capture envelopes. No network runner or execution CLI.

Authorization and complete protocol admission belong to a future locked caller.
Only OwnedJob and the clock-free GO launcher are reused from immutable R4.
"""
import base64
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading

from sandbox.reconnect_r4_process import OwnedJob, LAUNCHER

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ID = "safetwin5g-reconnect-r5-process-v1"
NS = 10**9


class RelativeTimer:
    """Unnamed, non-inherited kernel fail-safe, not an alternate timestamp.

    One-shot negative due time, no callback/period/resume/power request. This
    guard cannot establish elapsed QPC evidence when that API has failed.
    """
    def __init__(self, due_100ns):
        if type(due_100ns) is not int or not 1 <= due_100ns <= 350000000:
            raise ValueError("relative timer bound")
        api = self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        api.CreateWaitableTimerW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        api.CreateWaitableTimerW.restype = wintypes.HANDLE
        api.SetWaitableTimer.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_longlong), wintypes.LONG,
                                        ctypes.c_void_p, ctypes.c_void_p, wintypes.BOOL]
        api.SetWaitableTimer.restype = wintypes.BOOL
        api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        api.WaitForSingleObject.restype = wintypes.DWORD
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        api.CloseHandle.restype = wintypes.BOOL
        self.handle = api.CreateWaitableTimerW(None, True, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            due = ctypes.c_longlong(-due_100ns)
            if not api.SetWaitableTimer(self.handle, ctypes.byref(due), 0, None, None, False):
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            self.close()
            raise

    def expired(self, wait_ms=0):
        if type(wait_ms) is not int or not 0 <= wait_ms <= 5:
            raise ValueError("bounded timer wait")
        value = self.api.WaitForSingleObject(self.handle, wait_ms)
        if value == 0:
            return True
        if value != 258:
            raise OSError("WaitForSingleObject failed: " + str(value))
        return False

    def close(self):
        if self.handle:
            if not self.api.CloseHandle(self.handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self.handle = None


def captured(row):
    """Complete raw client capture, independent of return-code acceptance."""
    return bool(row["launcher_go_sent"] and row["job_assigned_before_go"] and row["job_closed"]
                and row["process_reaped"] and row["reader_threads_joined"]
                and not row["timed_out"] and not row["truncated"]
                and not row["process_errors"] and not row["cleanup_errors"])


def complete(row):
    return captured(row) and row["timing_valid"]


class BoundedProcess:
    def __init__(self, journal, allowed=(), *, cleanup_allowed=(), job_factory=OwnedJob, timer_factory=RelativeTimer):
        if os.name != "nt":
            raise OSError("R5 process adapter supports Windows only")
        self.journal, self.clock = journal, journal.clock
        self.allowed = frozenset(tuple(a) for a in allowed)
        self.cleanup_allowed = frozenset(tuple(a) for a in cleanup_allowed)
        if not self.cleanup_allowed <= self.allowed:
            raise PermissionError("cleanup argv must be a subset of the explicit allowlist")
        self.job_factory, self.timer_factory = job_factory, timer_factory
        self.last_tick, self.counter_error, self.next_sequence = None, None, 1

    def _tick(self, row, phase):
        if self.counter_error is None:
            try:
                if json.dumps(self.clock.descriptor, sort_keys=True) != json.dumps(self.journal.prefix.descriptor, sort_keys=True):
                    raise OSError("clock descriptor changed")
                tick = self.clock.ticks()
                if type(tick) is not int or not 0 <= tick < 2**63 or (self.last_tick is not None and tick < self.last_tick):
                    raise OSError("invalid or reversing raw QPC")
                self.last_tick = tick
                return tick
            except BaseException as exc:
                self.counter_error = phase + ": " + type(exc).__name__ + ": " + str(exc)
        row["counter_error"] = self.counter_error
        return None

    def run(self, argv, *, sequence, timeout_ms=35000, max_output_bytes=1048576, cleanup=False):
        if (type(argv) not in (list, tuple) or not argv or not all(type(a) is str and a and "\0" not in a for a in argv)
                or tuple(argv) not in self.allowed or type(cleanup) is not bool
                or (cleanup and tuple(argv) not in self.cleanup_allowed)
                or type(sequence) is not int or sequence != self.next_sequence or sequence > 2048
                or type(timeout_ms) is not int or not 1 <= timeout_ms <= 35000
                or type(max_output_bytes) is not int or not 1 <= max_output_bytes <= 1048576):
            raise PermissionError("R5 argv, sequence, cleanup allowlist or bounds")
        self.next_sequence += 1
        journal = self.journal
        before_count = len(journal.prefix.points)
        anchor = journal.prefix.points[-1] if before_count else None
        row = dict(contract_id=CONTRACT_ID, sequence=sequence, argv=list(argv), cleanup=cleanup,
                   timeout_ms=timeout_ms, max_output_bytes=max_output_bytes, cleanup_grace_ms=2000,
                   clock_id=journal.prefix.descriptor["clock_id"], journal_event_before=len(journal.events),
                   journal_event_after=None, start_point=before_count or None, end_point=None,
                   admitted_clock_before=journal.admitted(), counter_error=self.counter_error,
                   checked_ticks=None, go_before_ticks=None, go_after_ticks=None,
                   completion_observed_ticks=None, cleanup_completed_ticks=None, deadline_ticks=None,
                   timer_due_100ns=None, timer_armed=False, timer_signaled=False,
                   cleanup_timer_armed=False, cleanup_timer_signaled=False,
                   emergency_timer_only=False, launcher_go_sent=False, job_assigned_before_go=False,
                   job_closed=False, owned_launcher_pid=None, process_reaped=False, reader_threads_joined=False,
                   timed_out=False, truncated=False, process_errors=[], cleanup_errors=[],
                   returncode=None, timing_valid=False, client_capture_complete=False, complete=False)
        buffers = [bytearray(), bytearray()]
        mutex, overflow = threading.Lock(), threading.Event()
        eof = [threading.Event(), threading.Event()]
        errors, readers = [], []
        process = job = timer = cleanup_timer = None
        frequency = journal.prefix.descriptor["frequency_hz"]

        def consume(pipe, which):
            try:
                while True:
                    chunk = pipe.read(4096)
                    if not chunk:
                        break
                    with mutex:
                        room = max_output_bytes - sum(map(len, buffers))
                        buffers[which].extend(chunk[:max(0, room)])
                        if len(chunk) >= room:
                            overflow.set()
            except (OSError, ValueError) as exc:
                errors.append("pipe read: " + str(exc))
            finally:
                eof[which].set()

        try:
            if not cleanup and (not row["admitted_clock_before"] or self.counter_error):
                raise PermissionError("clock admission closed")
            checked = row["checked_ticks"] = self._tick(row, "admission")
            good_anchor = (anchor is not None and type(anchor.get("qpc_before_ticks")) is int
                           and type(anchor.get("qpc_after_ticks")) is int
                           and checked is not None and checked >= anchor["qpc_after_ticks"])
            if good_anchor:
                deadline = anchor["qpc_before_ticks"] + timeout_ms * frequency // 1000
                row["deadline_ticks"] = deadline
                remaining = (deadline - checked) * 10000000 // frequency
                if remaining <= 0:
                    if not cleanup:
                        row["timed_out"] = True
                        raise TimeoutError("shared envelope budget expired before dispatch")
                    row["emergency_timer_only"] = True
                    remaining = timeout_ms * 10000
            else:
                if not cleanup:
                    raise OSError("QPC unavailable or not contained after start bracket")
                row["emergency_timer_only"] = True
                remaining = timeout_ms * 10000
            # Arm BEFORE creating even the idle launcher. Failure sends no GO.
            row["timer_due_100ns"] = remaining
            timer = self.timer_factory(remaining)
            row["timer_armed"] = True
            process = subprocess.Popen([sys.executable, "-I", "-S", str(LAUNCHER), *argv], cwd=ROOT,
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       bufsize=0, creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
            row["owned_launcher_pid"] = process.pid
            job = self.job_factory(process)
            row["job_assigned_before_go"] = True
            for which, pipe in enumerate((process.stdout, process.stderr)):
                thread = threading.Thread(target=consume, args=(pipe, which), daemon=True)
                readers.append(thread)
                thread.start()
            if timer.expired():
                row["timer_signaled"] = row["timed_out"] = True
                raise TimeoutError("kernel cutoff before GO")
            row["go_before_ticks"] = self._tick(row, "GO-before")
            if row["go_before_ticks"] is None and not cleanup:
                raise OSError("QPC failure before GO")
            if (not row["emergency_timer_only"] and row["go_before_ticks"] is not None
                    and row["go_before_ticks"] >= row["deadline_ticks"]):
                row["timed_out"] = True
                raise TimeoutError("QPC deadline before GO")
            process.stdin.write(b"GO\n")
            process.stdin.close()
            row["launcher_go_sent"] = True
            row["go_after_ticks"] = self._tick(row, "GO-after")
            while True:
                if timer.expired():
                    row["timer_signaled"] = row["timed_out"] = True
                    break
                tick = self._tick(row, "wait")
                if tick is None:
                    if not cleanup:
                        break
                    row["emergency_timer_only"] = True
                elif not row["emergency_timer_only"] and tick >= row["deadline_ticks"]:
                    row["timed_out"] = True
                    break
                if overflow.is_set():
                    row["truncated"] = True
                    break
                if all(event.is_set() for event in eof) and process.poll() is not None:
                    break
                if timer.expired(5):
                    row["timer_signaled"] = row["timed_out"] = True
                    break
        except BaseException as exc:
            row["process_errors"].append(type(exc).__name__ + ": " + str(exc))
        finally:
            row["completion_observed_ticks"] = self._tick(row, "completion-observed")
            # Independent cleanup, even when no usable timestamp remains.
            try:
                cleanup_timer = self.timer_factory(20000000)
                row["cleanup_timer_armed"] = True
            except BaseException as exc:
                row["cleanup_errors"].append("cleanup timer: " + str(exc))
            try:
                if job is not None:
                    job.close()
                    row["job_closed"] = True
            except BaseException as exc:
                row["cleanup_errors"].append("owned job close: " + str(exc))
            try:
                if process is not None and process.poll() is None:
                    process.kill()  # only the owned launcher, never a name/PID sweep
            except BaseException as exc:
                row["cleanup_errors"].append("owned launcher kill: " + str(exc))
            if process is not None and cleanup_timer is not None:
                try:
                    cleanup_start = row["completion_observed_ticks"]
                    while process.poll() is None or any(thread.is_alive() for thread in readers):
                        if cleanup_timer.expired(5):
                            row["cleanup_timer_signaled"] = True
                            break
                        tick = self._tick(row, "cleanup-wait")
                        if tick is not None and cleanup_start is not None and (tick - cleanup_start) * NS >= 2 * NS * frequency:
                            break
                    row["process_reaped"] = process.poll() is not None
                    # Zero-time joins cannot create another clock/deadline budget.
                    for thread in readers:
                        thread.join(timeout=0)
                    row["reader_threads_joined"] = all(not thread.is_alive() for thread in readers)
                except BaseException as exc:
                    row["cleanup_errors"].append("reap/join: " + str(exc))
            elif process is not None:
                row["process_reaped"] = process.poll() is not None
                row["reader_threads_joined"] = all(not thread.is_alive() for thread in readers)
            if process is not None:
                if not row["process_reaped"] or not row["reader_threads_joined"]:
                    row["cleanup_errors"].append("owned client cleanup incomplete")
                else:
                    for pipe in (process.stdin, process.stdout, process.stderr):
                        try:
                            pipe.close()
                        except BaseException as exc:
                            row["cleanup_errors"].append("pipe close: " + str(exc))
                row["returncode"] = process.returncode
            for label, owned in (("command", timer), ("cleanup", cleanup_timer)):
                if owned is not None:
                    try:
                        owned.close()
                    except BaseException as exc:
                        row["cleanup_errors"].append(label + " timer close: " + str(exc))
            row["cleanup_completed_ticks"] = self._tick(row, "cleanup-completed")
            row["truncated"] = row["truncated"] or overflow.is_set()
            row["process_errors"].extend(errors)
            with mutex:
                raw_streams = [bytes(b) for b in buffers]
            for stream, raw in zip(("stdout", "stderr"), raw_streams):
                row[stream + "_base64"] = base64.b64encode(raw).decode("ascii")
                row[stream + "_sha256"] = hashlib.sha256(raw).hexdigest()
                try:
                    row[stream] = raw.decode("utf-8", "strict")
                    row[stream + "_utf8"] = True
                except UnicodeDecodeError:
                    row[stream] = raw.decode("utf-8", "replace")
                    row[stream + "_utf8"] = False
                    row["process_errors"].append(stream + ": invalid UTF-8, raw bytes retained")
            row["retained_output_bytes"] = sum(map(len, raw_streams))
            try:
                journal.checkpoint("process:" + str(sequence) + ":end", cleanup=cleanup)
            except BaseException as exc:
                row["cleanup_errors"].append("clock journal: " + type(exc).__name__ + ": " + str(exc))
            row["journal_event_after"] = len(journal.events)
            if len(journal.prefix.points) > before_count:
                row["end_point"] = len(journal.prefix.points)
            end = journal.prefix.points[-1] if row["end_point"] else None
            ticks = [row[k] for k in ("checked_ticks", "go_before_ticks", "go_after_ticks", "completion_observed_ticks", "cleanup_completed_ticks")]
            row["timing_valid"] = bool(
                not row["counter_error"] and not row["emergency_timer_only"] and not journal.failure and not journal.capture_failed
                and journal.prefix.status()["clock_capture_valid"] and anchor is not None and end is not None
                and all(type(t) is int for t in ticks)
                and anchor["qpc_after_ticks"] <= ticks[0] <= ticks[1] <= ticks[2] <= ticks[3] <= ticks[4] <= end["qpc_before_ticks"]
                and row["deadline_ticks"] is not None and ticks[3] < row["deadline_ticks"]
                and (ticks[4] - ticks[3]) * 1000 < 2000 * frequency)
            row["client_capture_complete"] = captured(row)
            row["complete"] = complete(row)
        return row


if __name__ == "__main__":
    raise SystemExit("No standalone execution endpoint; future committed protocol and approval gate required")
