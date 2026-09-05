"""Independent rational replay. Never imports the candidate clock module."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_ID = "safetwin5g-reconnect-r5-clock-v1"
LOCK_PATH = ROOT / "config/experiments/reconnect-r5-clock-lock.json"


def need(value, message):
    if not value:
        raise ValueError(message)


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    need(len(raw) < 1048576, "JSON byte cap")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def bounded_int(v, lo, hi):
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi


def replay(d, rows):
    report = dict(clock_capture_valid=False, accepted_points=0, comparisons=0,
                  max_bracket_ns_ceil=0, max_abs_residual_ns_ceil=0, rejection=None)
    current = other = None
    ceil = lambda x: -(-x.numerator // x.denominator)
    try:
        need(type(d) is dict and set(d) == {"clock_id", "counter_api", "utc_api", "frequency_hz", "python", "python_executable_sha256",
                                            "windows", "pointer_bits", "owner_pid", "utc_read_allowance_ns"}, "descriptor-schema")
        need(isinstance(d["clock_id"], str) and re.fullmatch("[0-9a-f]{32}", d["clock_id"]), "clock-domain")
        need(d["counter_api"] == "QueryPerformanceCounter" and d["utc_api"] == "GetSystemTimePreciseAsFileTime", "unsupported-clock-api")
        need(bounded_int(d["frequency_hz"], 1000000, 10000000000), "unsupported-counter-resolution")
        need(type(d["python"]) is dict and d["python"] == {"implementation": "cpython", "version": [3, 12, 10]}
             and type(d["python"]["version"]) is list and all(type(v) is int for v in d["python"]["version"]), "unsupported-python")
        need(isinstance(d["python_executable_sha256"], str) and re.fullmatch("[0-9a-f]{64}", d["python_executable_sha256"]), "executable-hash")
        w = d["windows"]
        need(type(w) is dict and set(w) == {"major", "minor", "build"} and all(type(v) is int for v in w.values())
             and w["major"] == 10 and w["minor"] == 0 and w["build"] >= 17763, "unsupported-windows")
        need(type(d["pointer_bits"]) is int and d["pointer_bits"] == 64 and bounded_int(d["owner_pid"], 1, 2**32 - 1), "unsupported-process")
        need(type(d["utc_read_allowance_ns"]) is int and d["utc_read_allowance_ns"] == 1000, "changed-read-allowance")
        need(type(rows) is list and 2 <= len(rows) <= 1024, "point-count")
        tick = Fraction(1000000000, d["frequency_hz"])
        prior = []
        for index, r in enumerate(rows, 1):
            current, other = index, None
            need(type(r) is dict and set(r) == {"sequence", "clock_id", "qpc_before_ticks", "qpc_after_ticks", "filetime_low", "filetime_high", "utc_ns", "capture_error"}, "point-schema")
            need(bounded_int(r["sequence"], 1, 1024) and r["sequence"] == index and r["clock_id"] == d["clock_id"], "point-order-or-domain")
            need(r["capture_error"] is None, "capture-error")
            need(all(bounded_int(r[k], 0, 2**63 - 1) for k in ("qpc_before_ticks", "qpc_after_ticks")), "counter-integer")
            need(all(bounded_int(r[k], 0, 4294967295) for k in ("filetime_low", "filetime_high")), "filetime-integer")
            need(bounded_int(r["utc_ns"], 0, 253402300799999999900), "utc-integer-or-range")
            need(r["utc_ns"] == (r["filetime_high"] * 4294967296 + r["filetime_low"]) * 100 - 11644473600000000000, "filetime-conversion")
            a, b = r["qpc_before_ticks"], r["qpc_after_ticks"]
            need(a <= b and (not prior or a >= prior[-1]["qpc_after_ticks"]), "counter-reversal-or-overlap")
            width = (b - a + 2) * tick
            report["max_bracket_ns_ceil"] = max(report["max_bracket_ns_ceil"], ceil(width))
            need(width <= 100000, "bracket-too-wide")
            # Alternative derivation: subtract two absolute interval endpoints.
            # These are internal algebra only, not exported fitted clock offsets.
            r_lo = r["utc_ns"] - b * tick - 1000 - tick
            r_hi = r["utc_ns"] - a * tick + 1000 + tick
            for p in prior:
                other = p["sequence"]
                p_lo = p["utc_ns"] - p["qpc_after_ticks"] * tick - 1000 - tick
                p_hi = p["utc_ns"] - p["qpc_before_ticks"] * tick + 1000 + tick
                low, high = r_lo - p_hi, r_hi - p_lo
                report["comparisons"] += 1
                report["max_abs_residual_ns_ceil"] = max(report["max_abs_residual_ns_ceil"], ceil(max(abs(low), abs(high))))
                if low > 1000000 or high < -1000000:
                    raise ValueError("clock-discontinuity-observed")
                if low < -1000000 or high > 1000000:
                    raise ValueError("clock-consistency-ambiguous")
            prior.append(r)
            report["accepted_points"] += 1
        report["clock_capture_valid"] = True
    except ValueError as exc:
        report["rejection"] = dict(code=str(exc), sequence=current, against_sequence=other)
    return report


def audit_bundle(bundle, *, allow_fixture=False):
    need(set(bundle) == {"contract_id", "evidence_label", "measurement_scope", "descriptor", "points", "reported", "claims"}, "bundle schema")
    need(bundle["contract_id"] == CONTRACT_ID, "contract identity")
    fixture = bundle["evidence_label"] == "fixture"
    need(bundle["evidence_label"] in ("fixture", "sandbox-measured") and (not fixture or allow_fixture), "explicit fixture permission")
    need(bundle["measurement_scope"] == ("synthetic-clock-fixture" if fixture else "local-host-clock-api-only"), "measurement scope")
    expected_claims = {"network_commands_executed": 0, "clock_settings_changed": False, "network_execution_authorized": False,
                              "historical_R4_verdict_changed": False, "network_fix_validated": False, "TNSM_ready": False,
                              "hardware_measured": False, "operator_validated": False}
    need(type(bundle["claims"]) is dict and set(bundle["claims"]) == set(expected_claims)
         and all(type(bundle["claims"][k]) is type(v) and bundle["claims"][k] == v for k, v in expected_claims.items()), "claim boundary")
    expected = replay(bundle["descriptor"], bundle["points"])
    need(json.dumps(bundle["reported"], sort_keys=True) == json.dumps(expected, sort_keys=True), "reported verdict differs from independent raw replay")
    return dict(observation_audit_passed=True, evidence_label=bundle["evidence_label"], measurement_scope=bundle["measurement_scope"], **expected)


def verify_lock(*, committed=False):
    import subprocess
    lock = strict_json(LOCK_PATH.read_bytes())
    need(lock["lock_id"] == CONTRACT_ID and lock["network_execution_authorized"] is False, "clock lock boundary")
    need(set(lock["source_sha256"]) == {"sandbox/reconnect_r5_clock.py", "tools/audit_reconnect_r5_clock.py",
         "tests/test_reconnect_r5_clock.py", "tools/verify_reconnect_r5_clock.py", "docs/RECONNECT_R5_CLOCK.md"}, "clock source inventory")
    need(set(lock["immutable_dependency_sha256"]) == {"config/experiments/reconnect-r4-execution-lock.json",
         "config/experiments/reconnect-r4-collection-lock.json", "config/experiments/reconnect-r3-execution-lock.json",
         "config/experiments/phase7-analysis-v2a-lock.json",
         "evidence/engineering/20260905T170131Z-reconnect-r4-network/manifest.json",
         "evidence/engineering/20260905T170620Z-reconnect-r4-aftercare/manifest.json",
         "evidence/engineering/20260905T170956Z-reconnect-r4-wall-clock/manifest.json"}, "immutable dependency inventory")
    for name, digest in {**lock["source_sha256"], **lock["immutable_dependency_sha256"]}.items():
        path = (ROOT / name).resolve()
        need(path.is_relative_to(ROOT) and hashlib.sha256(path.read_bytes()).hexdigest() == digest, "clock lock hash: " + name)
        if committed:
            need(subprocess.check_output(["git", "show", "HEAD:" + name], cwd=ROOT) == path.read_bytes(), "uncommitted source: " + name)
    if committed:
        need(subprocess.check_output(["git", "show", "HEAD:" + LOCK_PATH.relative_to(ROOT).as_posix()], cwd=ROOT) == LOCK_PATH.read_bytes(), "uncommitted clock lock")
    return lock


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--allow-fixture", action="store_true")
    args = parser.parse_args()
    verify_lock(committed=True)
    need(args.bundle.stat().st_size < 1048576, "bundle byte cap")
    print(json.dumps(audit_bundle(strict_json(args.bundle.read_bytes()), allow_fixture=args.allow_fixture), indent=2))
