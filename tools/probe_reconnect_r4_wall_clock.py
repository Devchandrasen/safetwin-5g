"""Local read-only clock-resolution comparison. No network, settings or actuation."""
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sandbox.run_reconnect_r4 import save, sha


def main():
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    api.GetSystemTimePreciseAsFileTime.argtypes = [ctypes.POINTER(wintypes.FILETIME)]
    api.GetSystemTimePreciseAsFileTime.restype = None
    rows = []
    for index in range(1000):
        before = time.perf_counter_ns()
        coarse = time.time_ns()
        between = time.perf_counter_ns()
        result = wintypes.FILETIME()
        api.GetSystemTimePreciseAsFileTime(ctypes.byref(result))
        after = time.perf_counter_ns()
        ticks = (result.dwHighDateTime << 32) | result.dwLowDateTime
        rows.append({"index": index, "qpc_before_ns": before, "python_wall_ns": coarse,
                     "qpc_between_ns": between, "precise_filetime_ticks": ticks,
                     "precise_unix_ns": (ticks - 116444736000000000) * 100, "qpc_after_ns": after})
        time.sleep(0.001)
    output = ROOT / "evidence/engineering" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r4-wall-clock")
    output.mkdir(exist_ok=False)
    save(output / "probe.json", {"rows": rows, "python_version": sys.version, "python_executable": sys.executable,
                                "python_wall_clock": vars(time.get_clock_info("time")),
                                "qpc_clock": vars(time.get_clock_info("perf_counter")),
                                "legacy_monotonic_clock": vars(time.get_clock_info("monotonic")),
                                "source_sha256": sha(Path(__file__).read_bytes()),
                                "purpose": "later-local-clock-observation-not-historical-timestamp-repair",
                                "evidence_label": "sandbox-measured", "network_commands_executed": 0,
                                "clock_changes_executed": 0, "historical_R4_verdict_unchanged": True})
    save(output / "manifest.json", {"captured_file_sha256": {"probe.json": sha((output / "probe.json").read_bytes())}})
    print(json.dumps({"output": str(output), "observations": len(rows)}))


if __name__ == "__main__":
    main()
