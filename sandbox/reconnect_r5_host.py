"""R5 host component, not an execution runner or network authorization.

No native request occurs at import/construction. The future locked caller owns
approval, exact repository/attempt scope and the complete protocol inventory.
"""
import copy
import ctypes
import json
import os
from pathlib import Path
import uuid

CONTRACT_ID = "safetwin5g-reconnect-r5-host-v1"
REASON = "SafeTwin-5G separately approved bounded sandbox diagnostic"


def idle_query(pid):
    if type(pid) is not int or not 1 <= pid < 2**32:
        raise ValueError("owner PID")
    # Strict errors and an explicit marker distinguish empty output from a
    # failed/truncated CIM query. This is not general host mutual exclusion.
    script = ("$ErrorActionPreference='Stop'; $busy=@(Get-CimInstance Win32_Process | "
              "Where-Object { $_.Name -match '^python(?:w)?(?:[.]exe)?$' "
              + f"-and $_.ProcessId -ne {pid} "
              + "-and ($_.CommandLine -eq $null -or $_.CommandLine -match "
              "'run_(?:phase7|recovery_pilot|reconnect(?:_r[0-9]+)?)[.]py') }); "
              "if ($busy.Count -ne 0) { $busy | Select-Object -ExpandProperty ProcessId; exit 3 }; "
              "[Console]::Out.WriteLine('SAFETWIN_R5_IDLE_V1')")
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script]


class KernelPower:
    """Owned PowerRequestSystemRequired handle; never alter a thread's request."""
    def __init__(self, api=None):
        if os.name != "nt" or ctypes.sizeof(ctypes.c_void_p) != 8:
            raise OSError("64-bit Windows power API required")
        class Detailed(ctypes.Structure):
            _fields_ = [("module", ctypes.c_void_p), ("id", ctypes.c_uint32),
                        ("count", ctypes.c_uint32), ("strings", ctypes.c_void_p)]
        class ReasonUnion(ctypes.Union):
            _fields_ = [("detailed", Detailed), ("simple", ctypes.c_wchar_p)]
        class Context(ctypes.Structure):
            _fields_ = [("version", ctypes.c_uint32), ("flags", ctypes.c_uint32), ("reason", ReasonUnion)]
        self.context = Context()
        self.context.version, self.context.flags = 0, 1
        self.context.reason.simple = REASON
        self.api = api if api is not None else ctypes.WinDLL("kernel32", use_last_error=True)
        for name, args, result in (
            ("PowerCreateRequest", [ctypes.POINTER(Context)], ctypes.c_void_p),
            ("PowerSetRequest", [ctypes.c_void_p, ctypes.c_int], ctypes.c_int),
            ("PowerClearRequest", [ctypes.c_void_p, ctypes.c_int], ctypes.c_int),
            ("CloseHandle", [ctypes.c_void_p], ctypes.c_int),
        ):
            fn = getattr(self.api, name)
            fn.argtypes, fn.restype = args, result

    def create(self):
        return self.api.PowerCreateRequest(ctypes.byref(self.context))

    def set(self, handle):
        return self.api.PowerSetRequest(handle, 1)

    def clear(self, handle):
        return self.api.PowerClearRequest(handle, 1)

    def close(self, handle):
        return self.api.CloseHandle(handle)


class PowerLease:
    def __init__(self, factory=KernelPower):
        self.factory, self.api, self.handle = factory, None, None
        self.record = dict(mechanism="PowerRequestSystemRequired", calls=[], closed=False)
        self.enable_attempted, self.close_attempted = False, False

    def _call(self, name):
        row = dict(name=name, result=None, error=None)
        self.record["calls"].append(row)
        try:
            if name == "create":
                self.api = self.factory()
            row["result"] = getattr(self.api, name)(*(() if name == "create" else (self.handle,)))
            value = row["result"]
            valid = (type(value) is int and 0 < value < 2**64 - 1) if name == "create" else (type(value) is int and value != 0)
            if not valid:
                raise OSError(name + " API returned failure")
            return value
        except BaseException as exc:
            row["error"] = type(exc).__name__ + ": " + str(exc)
            raise

    def enable(self):
        if self.enable_attempted or self.close_attempted:
            raise PermissionError("power request is once-only")
        self.enable_attempted = True
        self.handle = self._call("create")
        self._call("set")

    def close(self):
        if self.close_attempted:
            return
        self.close_attempted = True
        if self.handle is None:
            self.record["closed"] = True
            return
        errors = []
        # A set call that raised could be operationally uncertain. Retain its
        # failure and independently attempt clear AND close on only this handle.
        for name in ("clear", "close"):
            try:
                self._call(name)
                if name == "close":
                    self.record["closed"] = True
            except BaseException as exc:
                errors.append(type(exc).__name__ + ": " + str(exc))
        if errors:
            raise OSError("; ".join(errors))


class AttemptLease:
    """Exclusive, fsynced once-only receipt. NEVER delete or truncate a path.

    A completed receipt remains on disk and blocks another R5 attempt. This
    avoids deleting a substituted/stale lock path; crash receipts need review.
    It is cooperative file exclusion, not protection against privileged edits.
    """
    def __init__(self, path, *, owner_pid, clock_id, revision_sha256):
        self.path, self.handle = Path(path), None
        self.header = dict(kind="created", contract_id=CONTRACT_ID, owner_pid=owner_pid,
                           clock_id=clock_id, revision_sha256=revision_sha256, token=uuid.uuid4().hex)
        self.record = dict(header=copy.deepcopy(self.header), acquire_attempted=False, created=False,
                           header_persisted=False, close_attempted=False, footer_persisted=False,
                           handle_closed=False, errors=[])

    def _write(self, value):
        self.handle.write((json.dumps(value, allow_nan=False) + "\n").encode())
        self.handle.flush()
        os.fsync(self.handle.fileno())

    def acquire(self):
        if self.record["acquire_attempted"] or self.record["close_attempted"]:
            raise PermissionError("attempt receipt is once-only")
        self.record["acquire_attempted"] = True
        try:
            self.handle = self.path.open("xb")
            self.record["created"] = True
            self._write(self.header)
            self.record["header_persisted"] = True
        except BaseException as exc:
            self.record["errors"].append(type(exc).__name__ + ": " + str(exc))
            raise

    def close(self):
        if self.record["close_attempted"]:
            return
        self.record["close_attempted"] = True
        if self.handle is None:
            return
        try:
            self._write(dict(kind="close-intent", token=self.header["token"]))
            self.record["footer_persisted"] = True
        except BaseException as exc:
            self.record["errors"].append(type(exc).__name__ + ": " + str(exc))
            raise
        finally:
            try:
                self.handle.close()
                self.record["handle_closed"] = True
            except BaseException as exc:
                self.record["errors"].append(type(exc).__name__ + ": " + str(exc))
                raise


class HostGuard:
    """One idle command and four bounded-observation host callbacks at most.

    Native power/filesystem calls are synchronous: bounds reject late returns,
    not a hard real-time guarantee or cancellation of a blocked kernel API.
    Cleanup dispatch remains enabled after every clock/storage/source failure.
    """
    def __init__(self, journal, transport, lease, power):
        if transport.journal is not journal or transport.clock is not journal.clock:
            raise ValueError("host and process must share one journal and QPC source")
        self.journal, self.transport, self.lease, self.power = journal, transport, lease, power
        self.clock = journal.clock
        self.last_tick, self.counter_error = None, None
        self.record = dict(contract_id=CONTRACT_ID, owner_pid=journal.prefix.descriptor["owner_pid"],
                           clock_id=journal.prefix.descriptor["clock_id"], operations=[], idle_command=None,
                           idle_ok=False, start_point=None, admission_deadline_ticks=None,
                           admitted=False, closed=False, errors=[], counter_error=None,
                           lease=lease.record, power=power.record)
        expected = dict(owner_pid=self.record["owner_pid"], clock_id=self.record["clock_id"])
        if any(lease.header[k] != v for k, v in expected.items()):
            raise ValueError("attempt receipt domain")
        revision = lease.header["revision_sha256"]
        if type(revision) is not str or len(revision) != 64 or any(c not in "0123456789abcdef" for c in revision):
            raise ValueError("future exact execution revision digest required")
        self.started = False

    def _tick(self):
        if self.counter_error is None:
            try:
                if json.dumps(self.clock.descriptor, sort_keys=True) != json.dumps(self.journal.prefix.descriptor, sort_keys=True):
                    raise OSError("host clock descriptor changed")
                value = self.clock.ticks()
                if type(value) is not int or not 0 <= value < 2**63 or (self.last_tick is not None and value < self.last_tick):
                    raise OSError("invalid or reversing host raw QPC")
                self.last_tick = value
                return value
            except BaseException as exc:
                self.counter_error = type(exc).__name__ + ": " + str(exc)
        return None

    def _operation(self, name, callback, *, cleanup=False):
        j = self.journal
        n = len(j.prefix.points)
        start = j.prefix.points[-1] if n else None
        f = j.prefix.descriptor["frequency_hz"]
        deadline = (start["qpc_before_ticks"] + 2 * f if cleanup and start is not None
                    and type(start["qpc_before_ticks"]) is int else self.record["admission_deadline_ticks"] if not cleanup else None)
        row = dict(name=name, cleanup=cleanup, start_point=n or None, end_point=None,
                   event_before=len(j.events), event_after=None, checked_ticks=self._tick(), returned_ticks=None,
                   deadline_ticks=deadline, called=False, returned=False, errors=[], timing_valid=False,
                   counter_error=None)
        self.record["operations"].append(row)
        try:
            if not cleanup and (not j.admitted() or row["checked_ticks"] is None or deadline is None
                                or row["checked_ticks"] >= deadline or start is None
                                or row["checked_ticks"] < start["qpc_after_ticks"]):
                raise PermissionError("host clock admission or deadline rejected")
            row["called"] = True
            callback()
            row["returned"] = True
        except BaseException as exc:
            row["errors"].append(type(exc).__name__ + ": " + str(exc))
        row["returned_ticks"] = self._tick()
        try:
            j.checkpoint("host:" + name + ":end", cleanup=cleanup)
        except BaseException as exc:
            row["errors"].append("journal: " + type(exc).__name__ + ": " + str(exc))
        row["event_after"] = len(j.events)
        row["end_point"] = len(j.prefix.points) if len(j.prefix.points) > n else None
        end = j.prefix.points[-1] if row["end_point"] else None
        row["counter_error"] = self.counter_error
        a, b = row["checked_ticks"], row["returned_ticks"]
        row["timing_valid"] = bool(not self.counter_error and not j.failure and not j.capture_failed
                and j.prefix.status()["clock_capture_valid"] and start is not None and end is not None
                and type(a) is int and type(b) is int and deadline is not None
                and start["qpc_after_ticks"] <= a <= b <= end["qpc_before_ticks"] and b < deadline)
        if not row["timing_valid"]:
            row["errors"].append("host callback timing unavailable or rejected")
        return row["returned"] and row["timing_valid"] and not row["errors"]

    def start(self):
        if self.started or self.record["closed"]:
            raise PermissionError("host lifecycle is once-only")
        self.started = True
        j, r = self.journal, self.record
        r["start_point"] = len(j.prefix.points) or None
        anchor = j.prefix.points[-1] if j.prefix.points else None
        try:
            if not j.admitted(points_needed=3):
                raise PermissionError("three normal host points unavailable")
            r["admission_deadline_ticks"] = anchor["qpc_before_ticks"] + 35 * j.prefix.descriptor["frequency_hz"]
            if not self._operation("acquire", self.lease.acquire):
                raise PermissionError("exclusive attempt receipt failed")
            # Charge all overhead against the original 35 s host deadline.
            remaining = (r["admission_deadline_ticks"] - j.prefix.points[-1]["qpc_before_ticks"]) * 1000 // j.prefix.descriptor["frequency_hz"]
            if remaining < 1:
                raise PermissionError("idle command admission expired")
            row = self.transport.run(idle_query(r["owner_pid"]), sequence=1, timeout_ms=min(35000, remaining), max_output_bytes=1048576)
            r["idle_command"] = row
            r["idle_ok"] = bool(row["complete"] and row["returncode"] == 0 and row["stdout"] in
                                ("SAFETWIN_R5_IDLE_V1\n", "SAFETWIN_R5_IDLE_V1\r\n") and row["stderr"] == "")
            if not r["idle_ok"]:
                raise PermissionError("idle snapshot incomplete, busy, or malformed")
            if not self._operation("enable", self.power.enable):
                raise PermissionError("owned host power admission failed")
            r["admitted"] = True
        except BaseException as exc:
            r["errors"].append(type(exc).__name__ + ": " + str(exc))
        return r["admitted"]

    def close(self):
        if self.record["closed"]:
            return
        # Never allow an earlier callback or timestamp to suppress either step.
        self._operation("clear", self.power.close, cleanup=True)
        self._operation("release", self.lease.close, cleanup=True)
        self.record["closed"] = True

    def snapshot(self):
        r = copy.deepcopy(self.record)
        r["counter_error"] = self.counter_error
        r["component_complete"] = bool(r["admitted"] and r["closed"] and not r["errors"]
                and all(o["returned"] and o["timing_valid"] and not o["errors"] for o in r["operations"])
                and r["lease"]["header_persisted"] and r["lease"]["footer_persisted"] and r["lease"]["handle_closed"]
                and r["power"]["closed"])
        r.update(network_execution_authorized=False, whole_protocol_verified=False, service_restored=False,
                 network_fix_validated=False)
        return r


if __name__ == "__main__":
    raise SystemExit("No execution CLI. Complete committed R5 runner and separate authority gate required.")
