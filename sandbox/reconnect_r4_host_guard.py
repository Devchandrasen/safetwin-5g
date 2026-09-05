"""Current-process sleep inhibition and read-only admission exclusion checks."""
import ctypes
from ctypes import wintypes
import os
import time

from sandbox.reconnect_r4_process import complete


def idle_query(pid):
    script = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(?:w)?(?:[.]exe)?$' "
              + f"-and $_.ProcessId -ne {int(pid)} "
              + "-and $_.CommandLine -match 'run_(?:phase7|recovery_pilot|reconnect(?:_r[234])?)[.]py' } | Select-Object -ExpandProperty ProcessId")
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script]


class SleepGuard:
    def __init__(self, setter=None):
        if setter is None:
            if os.name != "nt":
                raise OSError("Windows sleep guard required")
            api = ctypes.WinDLL("kernel32", use_last_error=True)
            api.SetThreadExecutionState.argtypes = [wintypes.DWORD]
            api.SetThreadExecutionState.restype = wintypes.DWORD
            setter = api.SetThreadExecutionState
        self.setter = setter
        self.record = {"mechanism": "SetThreadExecutionState", "requested_flags": 0x80000001,
                       "enabled": False, "cleared": False}

    def enable(self):
        state = self.setter(0x80000001)
        self.record["previous_state"] = state
        if state == 0:
            raise OSError("sleep inhibition failed")
        self.record["enabled"] = True

    def close(self):
        if self.record["enabled"]:
            self.record["cleared"] = self.setter(0x80000000) != 0
            if not self.record["cleared"]:
                raise OSError("sleep inhibition could not be cleared")


class HostGuard:
    """Bounded idle snapshot plus an owned, always-cleared sleep request.

    The idle snapshot is not a lock against unrelated tools or future processes.
    The main entrypoint separately owns an exclusive on-disk R4 admission lock.
    """
    def __init__(self, transport, sleeper, pid, *, fixture=False, monotonic_ns=time.perf_counter_ns):
        self.transport, self.sleeper, self.pid = transport, sleeper, pid
        self.monotonic_ns = monotonic_ns
        self.record = {"fixture": fixture, "owner_pid": pid, "idle_command": None,
                       "admitted": False, "errors": [], "sleep": sleeper.record}

    def start(self):
        self.record["started_monotonic_ns"] = self.monotonic_ns()
        try:
            row = self.transport.run(idle_query(self.pid), sequence=0, timeout_seconds=35, max_output_bytes=1048576)
            self.record["idle_command"] = row
            elapsed = row["monotonic_end_ns"] - row["monotonic_start_ns"]
            if (not complete(row) or row["returncode"] != 0 or row["stdout"].strip() or row["stderr"]
                    or elapsed > 35 * 10**9 or abs(row["wall_end_ns"] - row["wall_start_ns"] - elapsed) > 1000000):
                raise PermissionError("experiment process snapshot is not empty and complete")
            self.sleeper.enable()
            self.record["admitted"] = True
        except BaseException as exc:
            self.record["errors"].append(type(exc).__name__ + ": " + str(exc))
            raise
        finally:
            self.record["admission_completed_monotonic_ns"] = self.monotonic_ns()

    def close(self):
        try:
            self.sleeper.close()
        except BaseException as exc:
            self.record["errors"].append(type(exc).__name__ + ": " + str(exc))
            raise
        finally:
            self.record["completed_monotonic_ns"] = self.monotonic_ns()
