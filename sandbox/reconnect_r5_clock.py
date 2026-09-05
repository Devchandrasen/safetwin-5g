"""Prospective R5 clock primitive only. No subprocess, network or clock setting.

Raw QPC ticks bracket one precise UTC read. All decisions use integer rational
bounds. This module is NOT integrated with any frozen execution runner.
"""
import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import re
import sys
import uuid

CONTRACT_ID = "safetwin5g-reconnect-r5-clock-v1"
NS = 10**9
EPOCH_TICKS = 116444736000000000
TOLERANCE_NS = 1000000
MAX_BRACKET_NS = 100000
UTC_READ_ALLOWANCE_NS = 1000
MAX_POINTS = 1024
DESCRIPTOR_KEYS = {"clock_id", "counter_api", "utc_api", "frequency_hz", "python", "python_executable_sha256",
                   "windows", "pointer_bits", "owner_pid", "utc_read_allowance_ns"}
POINT_KEYS = {"sequence", "clock_id", "qpc_before_ticks", "qpc_after_ticks", "filetime_low", "filetime_high", "utc_ns", "capture_error"}


def integer(value, low, high):
    return type(value) is int and low <= value <= high


def require(value, reason):
    if not value:
        raise ValueError(reason)


def validate_descriptor(d):
    require(type(d) is dict and set(d) == DESCRIPTOR_KEYS, "descriptor-schema")
    require(type(d["clock_id"]) is str and re.fullmatch(r"[0-9a-f]{32}", d["clock_id"]), "clock-domain")
    require(d["counter_api"] == "QueryPerformanceCounter" and d["utc_api"] == "GetSystemTimePreciseAsFileTime", "unsupported-clock-api")
    require(integer(d["frequency_hz"], 10**6, 10**10), "unsupported-counter-resolution")
    require(type(d["python"]) is dict and d["python"] == {"implementation": "cpython", "version": [3, 12, 10]}
            and type(d["python"]["version"]) is list and all(type(v) is int for v in d["python"]["version"]), "unsupported-python")
    require(type(d["python_executable_sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", d["python_executable_sha256"]), "executable-hash")
    require(type(d["windows"]) is dict and set(d["windows"]) == {"major", "minor", "build"}
            and all(type(v) is int for v in d["windows"].values())
            and d["windows"]["major"] == 10 and d["windows"]["minor"] == 0 and d["windows"]["build"] >= 17763, "unsupported-windows")
    require(type(d["pointer_bits"]) is int and d["pointer_bits"] == 64 and integer(d["owner_pid"], 1, 2**32 - 1), "unsupported-process")
    require(type(d["utc_read_allowance_ns"]) is int and d["utc_read_allowance_ns"] == UTC_READ_ALLOWANCE_NS, "changed-read-allowance")


class WindowsClock:
    """One process-local QPC domain; unavailable APIs never fall back."""
    def __init__(self):
        if os.name != "nt" or sys.implementation.name != "cpython" or tuple(sys.version_info[:3]) != (3, 12, 10):
            raise OSError("R5 clock requires Windows CPython 3.12.10")
        self._api = ctypes.WinDLL("kernel32", use_last_error=True)
        self._api.QueryPerformanceFrequency.argtypes = [ctypes.POINTER(ctypes.c_longlong)]
        self._api.QueryPerformanceFrequency.restype = wintypes.BOOL
        self._api.QueryPerformanceCounter.argtypes = [ctypes.POINTER(ctypes.c_longlong)]
        self._api.QueryPerformanceCounter.restype = wintypes.BOOL
        self._api.GetSystemTimePreciseAsFileTime.argtypes = [ctypes.POINTER(wintypes.FILETIME)]
        self._api.GetSystemTimePreciseAsFileTime.restype = None
        frequency = ctypes.c_longlong()
        if not self._api.QueryPerformanceFrequency(ctypes.byref(frequency)):
            raise OSError("QueryPerformanceFrequency failed")
        version = sys.getwindowsversion()
        self.descriptor = {"clock_id": uuid.uuid4().hex, "counter_api": "QueryPerformanceCounter",
                           "utc_api": "GetSystemTimePreciseAsFileTime", "frequency_hz": frequency.value,
                           "python": {"implementation": sys.implementation.name, "version": list(sys.version_info[:3])},
                           "python_executable_sha256": hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
                           "windows": {"major": version.major, "minor": version.minor, "build": version.build},
                           "pointer_bits": ctypes.sizeof(ctypes.c_void_p) * 8, "owner_pid": os.getpid(),
                           "utc_read_allowance_ns": UTC_READ_ALLOWANCE_NS}
        validate_descriptor(self.descriptor)
        self._next = 1

    def ticks(self):
        if os.getpid() != self.descriptor["owner_pid"]:
            raise OSError("clock process changed")
        value = ctypes.c_longlong()
        if not self._api.QueryPerformanceCounter(ctypes.byref(value)) or value.value < 0:
            raise OSError("QueryPerformanceCounter failed")
        return value.value

    def monotonic_ns(self):
        # Deadline-only view, rounded down by <1 ns. Same raw QPC domain.
        return self.ticks() * NS // self.descriptor["frequency_hz"]

    def capture(self):
        # A failed read consumes the sequence and retains any completed fields.
        if self._next > MAX_POINTS:
            raise OSError("clock sequence exhausted; no wrap or retry")
        row = dict(sequence=self._next, clock_id=self.descriptor["clock_id"], qpc_before_ticks=None,
                   qpc_after_ticks=None, filetime_low=None, filetime_high=None, utc_ns=None, capture_error=None)
        self._next += 1
        try:
            row["qpc_before_ticks"] = self.ticks()
            value = wintypes.FILETIME(0xFFFFFFFF, 0xFFFFFFFF)
            self._api.GetSystemTimePreciseAsFileTime(ctypes.byref(value))
            row["filetime_low"], row["filetime_high"] = value.dwLowDateTime, value.dwHighDateTime
            row["qpc_after_ticks"] = self.ticks()
            row["utc_ns"] = (((row["filetime_high"] << 32) | row["filetime_low"]) - EPOCH_TICKS) * 100
        except (OSError, ValueError, AttributeError) as exc:
            row["capture_error"] = type(exc).__name__ + ": " + str(exc)
        return row


def evaluate(descriptor, points):
    """Worst-case all-pair residual inclusion, not mere interval overlap.

Sampling cannot exclude sub-tolerance or cancelling steps between readings.
The return value concerns this sampled clock trace only, never network safety.
"""
    result = dict(clock_capture_valid=False, accepted_points=0, comparisons=0,
                  max_bracket_ns_ceil=0, max_abs_residual_ns_ceil=0, rejection=None)
    current = against = None
    try:
        validate_descriptor(descriptor)
        require(type(points) is list and 2 <= len(points) <= MAX_POINTS, "point-count")
        f = descriptor["frequency_hz"]
        for index, row in enumerate(points, 1):
            current, against = index, None
            require(type(row) is dict and set(row) == POINT_KEYS, "point-schema")
            require(integer(row["sequence"], 1, MAX_POINTS) and row["sequence"] == index
                    and row["clock_id"] == descriptor["clock_id"], "point-order-or-domain")
            require(row["capture_error"] is None, "capture-error")
            require(all(integer(row[k], 0, 2**63 - 1) for k in ("qpc_before_ticks", "qpc_after_ticks")), "counter-integer")
            require(all(integer(row[k], 0, 2**32 - 1) for k in ("filetime_low", "filetime_high")), "filetime-integer")
            require(integer(row["utc_ns"], 0, 253402300799999999900), "utc-integer-or-range")
            require(row["utc_ns"] == (((row["filetime_high"] << 32) | row["filetime_low"]) - EPOCH_TICKS) * 100, "filetime-conversion")
            low, high = row["qpc_before_ticks"], row["qpc_after_ticks"]
            require(low <= high and (index == 1 or low >= points[index - 2]["qpc_after_ticks"]), "counter-reversal-or-overlap")
            span = (high - low + 2) * NS  # one counter tick at each endpoint
            result["max_bracket_ns_ceil"] = max(result["max_bracket_ns_ceil"], (span + f - 1) // f)
            require(span <= MAX_BRACKET_NS * f, "bracket-too-wide")
            for previous in points[:index - 1]:
                against = previous["sequence"]
                delta = (row["utc_ns"] - previous["utc_ns"]) * f
                allowance = 2 * UTC_READ_ALLOWANCE_NS * f + 2 * NS
                lower = delta - (high - previous["qpc_before_ticks"]) * NS - allowance
                upper = delta - (low - previous["qpc_after_ticks"]) * NS + allowance
                result["comparisons"] += 1
                result["max_abs_residual_ns_ceil"] = max(result["max_abs_residual_ns_ceil"], (max(abs(lower), abs(upper)) + f - 1) // f)
                require(lower <= TOLERANCE_NS * f and upper >= -TOLERANCE_NS * f, "clock-discontinuity-observed")
                require(lower >= -TOLERANCE_NS * f and upper <= TOLERANCE_NS * f, "clock-consistency-ambiguous")
            result["accepted_points"] += 1
        result["clock_capture_valid"] = True
    except ValueError as exc:
        result["rejection"] = dict(code=str(exc), sequence=current, against_sequence=against)
    return result
