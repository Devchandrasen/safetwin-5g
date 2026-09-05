"""Prospective clock fixtures, arithmetic counterexamples and capture failures."""
import copy
import ast
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from sandbox import reconnect_r5_clock as candidate
from tools import audit_reconnect_r5_clock as independent

CLAIMS = {"network_commands_executed": 0, "clock_settings_changed": False, "network_execution_authorized": False,
          "historical_R4_verdict_changed": False, "network_fix_validated": False, "TNSM_ready": False,
          "hardware_measured": False, "operator_validated": False}


def descriptor(frequency=10000000):
    return dict(clock_id="1" * 32, counter_api="QueryPerformanceCounter", utc_api="GetSystemTimePreciseAsFileTime",
                frequency_hz=frequency, python={"implementation": "cpython", "version": [3, 12, 10]},
                python_executable_sha256="2" * 64, windows={"major": 10, "minor": 0, "build": 26100},
                pointer_bits=64, owner_pid=os.getpid(), utc_read_allowance_ns=1000)


def set_utc(row, utc_ns):
    row["utc_ns"] = utc_ns
    ticks = utc_ns // 100 + 116444736000000000
    row["filetime_low"], row["filetime_high"] = ticks % 2**32, ticks // 2**32


def points(count=4, frequency=10000000, width=20):
    result = []
    for i in range(count):
        start = 1000000000 + i * frequency
        row = dict(sequence=i + 1, clock_id="1" * 32, qpc_before_ticks=start, qpc_after_ticks=start + width,
                   filetime_low=0, filetime_high=0, utc_ns=0, capture_error=None)
        set_utc(row, 1788566400000000000 + i * 10**9 + (width // 2 * 10**9 // frequency // 100) * 100)
        result.append(row)
    return result


def bundle(d, rows, fixture=True):
    return dict(contract_id=candidate.CONTRACT_ID, evidence_label="fixture" if fixture else "sandbox-measured",
                measurement_scope="synthetic-clock-fixture" if fixture else "local-host-clock-api-only",
                descriptor=d, points=rows, reported=candidate.evaluate(d, rows), claims=copy.deepcopy(CLAIMS))


def fixture_cases():
    cases = {}
    def add(name, change=None, reason=None, frequency=10000000, width=20, count=4):
        d, rows = descriptor(frequency), points(count, frequency, width)
        if change:
            change(d, rows)
        cases[name] = {"bundle": bundle(d, rows), "expected_rejection": reason}
    add("complete")
    add("fractional-counter-period", frequency=3125000)
    add("constant-UTC-skew", lambda d, r: [set_utc(p, p["utc_ns"] - 10**15) for p in r])
    add("wide-read", width=1000, reason="bracket-too-wide")
    add("exact-bracket-bound", width=998)
    add("within-read-scheduling", lambda d, r: [set_utc(p, p["utc_ns"] + (45000 if i % 2 else -45000)) for i, p in enumerate(r)], width=900)
    add("forward-step", lambda d, r: [set_utc(p, p["utc_ns"] + 2000000) for p in r[2:]], "clock-discontinuity-observed")
    add("backward-step", lambda d, r: [set_utc(p, p["utc_ns"] - 2000000) for p in r[2:]], "clock-discontinuity-observed")
    add("near-positive-bound-ambiguous", lambda d, r: set_utc(r[2], r[2]["utc_ns"] + 999000), "clock-consistency-ambiguous")
    add("near-negative-bound-ambiguous", lambda d, r: set_utc(r[2], r[2]["utc_ns"] - 999000), "clock-consistency-ambiguous")
    add("within-bound", lambda d, r: [set_utc(p, p["utc_ns"] + 990000) for p in r[2:]])
    add("accumulated-small-steps", lambda d, r: [set_utc(p, p["utc_ns"] + i * 600000) for i, p in enumerate(r)], "clock-discontinuity-observed")
    add("nonadjacent-drift", lambda d, r: [set_utc(p, p["utc_ns"] + v) for p, v in zip(r, (0, 800000, 0, -800000))], "clock-discontinuity-observed")
    add("reordered-records", lambda d, r: r.reverse(), "point-order-or-domain")
    add("duplicate-record", lambda d, r: r.__setitem__(2, copy.deepcopy(r[1])), "point-order-or-domain")
    add("changed-clock-domain", lambda d, r: r[2].update(clock_id="3" * 32), "point-order-or-domain")
    add("counter-reversal", lambda d, r: r[2].update(qpc_after_ticks=r[2]["qpc_before_ticks"] - 1), "counter-reversal-or-overlap")
    add("overlapping-reads", lambda d, r: r[2].update(qpc_before_ticks=r[1]["qpc_after_ticks"] - 1), "counter-reversal-or-overlap")
    add("partial-UTC", lambda d, r: r[2].update(filetime_high=None), "filetime-integer")
    add("partial-counter", lambda d, r: r[2].update(qpc_after_ticks=None), "counter-integer")
    add("API-error-retained", lambda d, r: r[2].update(capture_error="OSError: failed", qpc_after_ticks=None), "capture-error")
    add("unchanged-FILETIME-sentinel", lambda d, r: r[2].update(filetime_low=2**32 - 1, filetime_high=2**32 - 1), "filetime-conversion")
    add("wrong-epoch", lambda d, r: r[2].update(utc_ns=r[2]["utc_ns"] + 100), "filetime-conversion")
    add("bool-as-counter", lambda d, r: r[2].update(qpc_before_ticks=True), "counter-integer")
    add("float-as-UTC", lambda d, r: r[2].update(utc_ns=float(r[2]["utc_ns"])), "utc-integer-or-range")
    add("coarse-wall-source", lambda d, r: d.update(utc_api="GetSystemTimeAsFileTime"), "unsupported-clock-api")
    add("coarse-counter", lambda d, r: d.update(frequency_hz=64), "unsupported-counter-resolution")
    add("float-frequency", lambda d, r: d.update(frequency_hz=1e7), "unsupported-counter-resolution")
    add("wrong-runtime", lambda d, r: d["python"].update(version=[3, 13, 0]), "unsupported-python")
    add("wrong-platform", lambda d, r: d["windows"].update(major=6), "unsupported-windows")
    add("wrong-bitness", lambda d, r: d.update(pointer_bits=32), "unsupported-process")
    add("relaxed-allowance", lambda d, r: d.update(utc_read_allowance_ns=1000000), "changed-read-allowance")
    add("missing-source-metadata", lambda d, r: d.pop("utc_api"), "descriptor-schema")
    add("extra-point-field", lambda d, r: r[1].update(midpoint_ns=123), "point-schema")
    add("incomplete-single-point", count=1, reason="point-count")
    add("record-limit", count=1025, reason="point-count")
    # A finite sample cannot observe a step and exact cancellation between reads.
    add("unobserved-cancelled-step-not-identifiable")
    return cases


@pytest.mark.parametrize("name", list(fixture_cases()))
def test_declared_cases_and_independent_replay(name):
    case = fixture_cases()[name]
    b = case["bundle"]
    actual = b["reported"]
    assert actual == independent.replay(b["descriptor"], b["points"])
    reason = case["expected_rejection"]
    assert actual["clock_capture_valid"] is (reason is None)
    assert actual["rejection"] is None if reason is None else actual["rejection"]["code"] == reason
    assert independent.audit_bundle(b, allow_fixture=True)["observation_audit_passed"]


def test_arithmetic_matches_on_varied_frequencies_and_perturbations():
    for frequency in (1000000, 3125000, 10000000, 24000000, 10000000000):
        for perturbation in (-2000000, -1000000, -997000, -100, 0, 100, 997000, 1000000, 2000000):
            d, rows = descriptor(frequency), points(frequency=frequency, width=max(1, frequency // 500000))
            set_utc(rows[2], rows[2]["utc_ns"] + perturbation)
            assert candidate.evaluate(d, rows) == independent.replay(d, rows)


def test_all_pairs_not_only_first_or_adjacent():
    rows = fixture_cases()["nonadjacent-drift"]["bundle"]["points"]
    assert abs((rows[3]["utc_ns"] - rows[0]["utc_ns"]) - 3 * 10**9) < 1000000
    assert candidate.evaluate(descriptor(), rows)["rejection"]["against_sequence"] == 2


def test_old_point_reads_cannot_resolve_scheduling():
    # No real clock step; coarse or unscheduled point reads are not adequate.
    qpc_gap_ns = 4652000
    coarse_wall_gap_ns = 0  # two values inside one 15.625 ms tick
    assert abs(coarse_wall_gap_ns - qpc_gap_ns) > 1000000
    d = descriptor()
    d["utc_api"] = "GetSystemTimeAsFileTime"
    assert candidate.evaluate(d, points())["rejection"]["code"] == "unsupported-clock-api"
    # A long read must be rejected as ambiguous acquisition, not forgiven as a step.
    assert candidate.evaluate(descriptor(), points(width=30000))["rejection"]["code"] == "bracket-too-wide"


def test_midpoint_overlap_is_not_enough_to_accept():
    b = fixture_cases()["near-positive-bound-ambiguous"]["bundle"]
    assert b["reported"]["rejection"]["code"] == "clock-consistency-ambiguous"
    assert not independent.audit_bundle(b, allow_fixture=True)["clock_capture_valid"]


def test_independent_audit_does_not_call_candidate():
    b = fixture_cases()["complete"]["bundle"]
    with patch.object(candidate, "evaluate", side_effect=AssertionError("candidate forbidden")), patch.object(candidate, "validate_descriptor", side_effect=AssertionError("candidate forbidden")):
        assert independent.audit_bundle(b, allow_fixture=True)["clock_capture_valid"]


@pytest.mark.parametrize("change", ["promote", "tier", "scope", "fixture-permission", "report", "contract", "extra"])
def test_evidence_wrapper_rejects_tampering(change):
    b = fixture_cases()["complete"]["bundle"]
    if change == "promote":
        b["claims"]["network_execution_authorized"] = True
    elif change == "tier":
        b["evidence_label"] = "operator-validated"
    elif change == "scope":
        b["measurement_scope"] = "network-recovery"
    elif change == "report":
        b["reported"]["comparisons"] += 1
    elif change == "contract":
        b["contract_id"] = "old-r4"
    elif change == "extra":
        b["midpoint"] = 0
    with pytest.raises(ValueError):
        independent.audit_bundle(b, allow_fixture=change != "fixture-permission")


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}', b" " * 1048576],
                         ids=["duplicate-key", "nan", "infinity", "byte-cap"])
def test_strict_json_rejects_ambiguity(raw):
    with pytest.raises(ValueError):
        independent.strict_json(raw)


def fake_native(fail_at=None, untouched=False):
    clock = candidate.WindowsClock.__new__(candidate.WindowsClock)
    clock.descriptor = descriptor()
    clock._next = 1
    class API:
        calls = 0
        def QueryPerformanceCounter(self, pointer):
            self.calls += 1
            pointer._obj.value = 123456789 + self.calls * 10
            return self.calls != fail_at
        def GetSystemTimePreciseAsFileTime(self, pointer):
            if fail_at == "utc":
                raise OSError("injected UTC failure")
            if not untouched:
                pointer._obj.dwLowDateTime = 3060637696
                pointer._obj.dwHighDateTime = 31256999
    clock._api = API()
    return clock


@pytest.mark.parametrize("failure", [1, 2, "utc"])
def test_partial_native_fields_and_sequence_are_preserved(failure):
    c = fake_native(failure)
    row = c.capture()
    assert row["sequence"] == 1 and row["capture_error"]
    assert c._next == 2
    if failure == 2:
        assert row["filetime_low"] is not None and row["qpc_after_ticks"] is None
    if failure == "utc":
        assert row["qpc_before_ticks"] is not None and row["filetime_low"] is None


def test_void_API_sentinel_does_not_become_valid_time():
    c = fake_native(untouched=True)
    result = candidate.evaluate(c.descriptor, [c.capture(), c.capture()])
    assert not result["clock_capture_valid"]
    assert result["rejection"]["code"] == "utc-integer-or-range"


def test_native_uses_one_QPC_epoch_and_refuses_other_process():
    c = fake_native()
    assert c.monotonic_ns() == 123456799 * 100
    c.descriptor["owner_pid"] += 1
    row = c.capture()
    assert row["qpc_before_ticks"] is None and "process changed" in row["capture_error"]


@pytest.mark.skipif(os.name != "nt", reason="Windows binding prerequisite")
def test_unavailable_native_API_has_no_fallback():
    with patch.object(candidate.ctypes, "WinDLL", side_effect=OSError("unavailable")), pytest.raises(OSError):
        candidate.WindowsClock()


def test_fixtures_do_not_execute_process_network_or_native_API():
    with patch("subprocess.Popen", side_effect=AssertionError("process forbidden")), patch("socket.socket", side_effect=AssertionError("network forbidden")), patch.object(candidate, "WindowsClock", side_effect=AssertionError("native API forbidden")):
        for case in fixture_cases().values():
            independent.audit_bundle(case["bundle"], allow_fixture=True)


@pytest.mark.parametrize("field,value", [("clock_settings_changed", 0), ("network_commands_executed", False)])
def test_claim_types_cannot_be_coerced(field, value):
    b = fixture_cases()["complete"]["bundle"]
    b["claims"][field] = value
    with pytest.raises(ValueError, match="claim boundary"):
        independent.audit_bundle(b, allow_fixture=True)


def test_float_python_version_cannot_be_coerced():
    d = descriptor()
    d["python"]["version"][2] = 10.0
    assert candidate.evaluate(d, points()) == independent.replay(d, points())
    assert candidate.evaluate(d, points())["rejection"]["code"] == "unsupported-python"


def test_sequence_cap_refuses_another_API_read():
    c = fake_native()
    c._next = 1025
    with pytest.raises(OSError, match="exhausted"):
        c.capture()
    assert c._api.calls == 0


def test_float_report_cannot_match_integer_raw_replay():
    b = fixture_cases()["complete"]["bundle"]
    b["reported"]["comparisons"] = float(b["reported"]["comparisons"])
    with pytest.raises(ValueError, match="reported verdict"):
        independent.audit_bundle(b, allow_fixture=True)


def test_primitive_has_no_network_process_or_clock_setting_interface():
    source = Path(candidate.__file__).read_text()
    tree = ast.parse(source)
    imports = {n.names[0].name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import)}
    assert not imports.intersection({"subprocess", "socket", "time", "requests"})
    assert "--execute" not in source and "SetSystemTime" not in source and "timeBeginPeriod" not in source
    api_calls = {n.func.attr for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Attribute) and n.func.value.attr == "_api"}
    assert api_calls == {"QueryPerformanceFrequency", "QueryPerformanceCounter", "GetSystemTimePreciseAsFileTime"}


def test_fake_native_complete_raw_conversion_and_capture_order():
    c = fake_native()
    rows = [c.capture(), c.capture()]
    assert [r["sequence"] for r in rows] == [1, 2]
    assert rows[0]["qpc_after_ticks"] < rows[1]["qpc_before_ticks"]
    assert candidate.evaluate(c.descriptor, rows)["clock_capture_valid"]
    assert candidate.evaluate(c.descriptor, rows) == independent.replay(c.descriptor, rows)


def test_clock_lock_cannot_omit_a_source_or_dependency(tmp_path, monkeypatch):
    # Once a source lock exists, malformed inventories fail before file checks.
    lock = {"lock_id": candidate.CONTRACT_ID, "network_execution_authorized": False,
            "source_sha256": {}, "immutable_dependency_sha256": {}}
    path = tmp_path / "lock.json"
    path.write_text(json.dumps(lock), encoding="utf-8")
    monkeypatch.setattr(independent, "LOCK_PATH", path)
    with pytest.raises(ValueError, match="source inventory"):
        independent.verify_lock()
