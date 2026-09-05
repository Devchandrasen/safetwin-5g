"""Windows-owned job, byte-bounded concurrent pipes and monotonic termination.

This is process plumbing, NOT network authorization. Only an explicit argv
allowlist is accepted. The R4 runner separately enforces approval and scope.
"""
import base64
import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "sandbox/reconnect_r4_launcher.py"


class BasicLimit(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount", "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class ExtendedLimit(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", BasicLimit), ("IoInfo", IoCounters), ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class OwnedJob:
    def __init__(self, process):
        self.api = ctypes.WinDLL("kernel32", use_last_error=True)
        self.api.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        self.api.CreateJobObjectW.restype = wintypes.HANDLE
        self.api.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        self.api.SetInformationJobObject.restype = wintypes.BOOL
        self.api.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        self.api.AssignProcessToJobObject.restype = wintypes.BOOL
        self.api.CloseHandle.argtypes = [wintypes.HANDLE]
        self.api.CloseHandle.restype = wintypes.BOOL
        self.handle = self.api.CreateJobObjectW(None, None)  # unnamed, non-inheritable
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            limits = ExtendedLimit()
            limits.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE, no breakaway flags
            if not self.api.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            # Popen's owned Windows process handle, not a PID-name search/kill.
            if not self.api.AssignProcessToJobObject(self.handle, int(process._handle)):
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.handle:
            if not self.api.CloseHandle(self.handle):
                raise ctypes.WinError(ctypes.get_last_error())
            self.handle = None


class BoundedProcess:
    def __init__(self, allowed, *, job_factory=OwnedJob):
        if os.name != "nt":
            raise OSError("this verified adapter supports Windows only")
        self.clock_info = vars(time.get_clock_info("perf_counter"))
        if not self.clock_info["monotonic"] or self.clock_info["adjustable"] or self.clock_info["resolution"] > 1e-6:
            raise OSError("high-resolution monotonic performance counter required")
        self.allowed = frozenset(tuple(a) for a in allowed)
        self.job_factory = job_factory

    def run(self, argv, *, sequence, timeout_seconds=35, max_output_bytes=1048576):
        if tuple(argv) not in self.allowed or not 0 < timeout_seconds <= 35 or not 0 < max_output_bytes <= 1048576:
            raise PermissionError("unapproved argv or capture bounds")
        row = {"sequence": sequence, "argv": list(argv), "timeout_seconds": timeout_seconds, "max_output_bytes": max_output_bytes,
               "wall_start_ns": time.time_ns(), "monotonic_start_ns": time.perf_counter_ns(), "timed_out": False,
               "truncated": False, "capture_error": None, "job_assigned_before_go": False, "launcher_go_sent": False,
               "reader_threads_joined": False, "process_reaped": False, "cleanup_grace_seconds": 2,
               "monotonic_clock": {"api": "perf_counter_ns", **self.clock_info}}
        deadline = row["monotonic_start_ns"] + int(timeout_seconds * 10**9)
        buffers = [bytearray(), bytearray()]
        guard, overflow = threading.Lock(), threading.Event()
        finished = [threading.Event(), threading.Event()]
        read_errors, readers = [], []
        process = job = None

        def consume(pipe, index):
            try:
                while True:
                    block = pipe.read(4096)  # unbuffered pipe: at most one bounded chunk
                    if not block:
                        break
                    with guard:
                        room = max_output_bytes - sum(len(b) for b in buffers)
                        buffers[index].extend(block[:max(0, room)])
                        if len(block) >= room:
                            overflow.set()
                    # Keep draining/discarding after the cap until the job is killed.
            except (OSError, ValueError) as exc:
                read_errors.append(str(exc))
            finally:
                finished[index].set()

        try:
            process = subprocess.Popen([sys.executable, "-I", "-S", str(LAUNCHER), *argv], cwd=ROOT,
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       bufsize=0, creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
            row["owned_launcher_pid"] = process.pid
            job = self.job_factory(process)
            row["job_assigned_before_go"] = True
            for index, pipe in enumerate((process.stdout, process.stderr)):
                reader = threading.Thread(target=consume, args=(pipe, index), daemon=True)
                readers.append(reader)
                reader.start()
            process.stdin.write(b"GO\n")
            process.stdin.close()
            row["launcher_go_sent"] = True
            while True:
                if overflow.is_set():
                    row["truncated"] = True
                    break
                if all(e.is_set() for e in finished) and process.poll() is not None:
                    break
                if time.perf_counter_ns() >= deadline:
                    row["timed_out"] = True
                    break
                overflow.wait(0.005)
        except BaseException as exc:
            row["capture_error"] = type(exc).__name__ + ": " + str(exc)
        finally:
            # Closing the owned job kills descendants too, including inherited-pipe holders.
            try:
                if job is not None:
                    job.close()
                elif process is not None and process.poll() is None:
                    process.kill()  # no GO was sent, so only our idle launcher exists
            except OSError as exc:
                row["capture_error"] = "job cleanup: " + str(exc)
            cleanup_deadline = time.perf_counter() + 2
            if process is not None:
                try:
                    process.wait(timeout=max(0.001, cleanup_deadline - time.perf_counter()))
                    row["process_reaped"] = True
                except subprocess.TimeoutExpired:
                    row["capture_error"] = "owned launcher not reaped within cleanup grace"
                for reader in readers:
                    reader.join(timeout=max(0, cleanup_deadline - time.perf_counter()))
                row["reader_threads_joined"] = all(not t.is_alive() for t in readers)
                # Close only joined pipes; a blocked reader must be reported, not hidden.
                if row["reader_threads_joined"]:
                    for pipe in (process.stdin, process.stdout, process.stderr):
                        if pipe is not None:
                            pipe.close()
                else:
                    row["capture_error"] = "pipe readers not joined within cleanup grace"
            row["returncode"] = process.returncode if process is not None else -998
            row["truncated"] = row["truncated"] or overflow.is_set()
            if read_errors:
                row["capture_error"] = "pipe read: " + "; ".join(read_errors)
            with guard:
                data = [bytes(b) for b in buffers]
            for stream, raw in zip(("stdout", "stderr"), data):
                row[stream + "_base64"] = base64.b64encode(raw).decode("ascii")
                row[stream + "_sha256"] = hashlib.sha256(raw).hexdigest()
                try:
                    row[stream] = raw.decode("utf-8", "strict")
                except UnicodeDecodeError:
                    row[stream] = raw.decode("utf-8", "replace")
                    row["capture_error"] = "non-UTF8 captured bytes, base64 preserved"
            row["retained_output_bytes"] = sum(len(raw) for raw in data)
            row["wall_end_ns"], row["monotonic_end_ns"] = time.time_ns(), time.perf_counter_ns()
        return row


def complete(row):
    return (row["capture_error"] is None and row["job_assigned_before_go"] is True and row["launcher_go_sent"] is True
            and row["reader_threads_joined"] is True and row["process_reaped"] is True
            and row["timed_out"] is False and row["truncated"] is False)
