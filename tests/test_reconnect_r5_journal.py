"""Deterministic R5 integration-component fixtures, no network/process/power I/O."""
import copy
import json
from unittest.mock import patch

import pytest
from sandbox import reconnect_r5_journal as candidate
from sandbox.reconnect_r5_clock import evaluate as frozen_evaluate
from tests.test_reconnect_r5_clock import descriptor, points, fixture_cases, set_utc
from tools.audit_reconnect_r5_journal import audit


class FakeClock:
    def __init__(self, rows=None, fail_at=None):
        self.descriptor = descriptor()
        self.rows = rows if rows is not None else points(1024)
        self.index, self.fail_at = 0, fail_at

    def capture(self):
        self.index += 1
        if self.index == self.fail_at:
            raise OSError("fixture source unavailable after consuming sequence")
        return copy.deepcopy(self.rows[self.index - 1])


@pytest.fixture(autouse=True)
def no_external_apis():
    with patch("subprocess.Popen", side_effect=AssertionError("process forbidden")), \
         patch("socket.socket", side_effect=AssertionError("socket forbidden")), \
         patch("ctypes.WinDLL", side_effect=AssertionError("power/native API forbidden")):
        yield


def capture_case(path, case):
    rows = points(1024)
    if case in ("step", "ambiguous", "wide", "partial", "wrong-domain"):
        if case == "step":
            set_utc(rows[2], rows[2]["utc_ns"] + 2000000)
        elif case == "ambiguous":
            set_utc(rows[2], rows[2]["utc_ns"] + 999000)
        elif case == "wide":
            rows[2]["qpc_after_ticks"] += 2000
        elif case == "partial":
            rows[2].update(qpc_after_ticks=None, capture_error="OSError: fixture partial read")
        else:
            rows[2]["clock_id"] = "f" * 32
    clock = FakeClock(rows, fail_at=3 if case == "API-error" else None)
    journal = candidate.Journal(clock, path)
    calls = []
    try:
        for index in range(770 if case in ("reserve", "exhaustion") else 4):
            journal.checkpoint("normal:" + str(index))
        if case == "exhaustion":
            for index in range(260):
                journal.checkpoint("reserve:" + str(index), cleanup=True)
        def callback(name):
            calls.append(name)
            if case == "callback-error" and name == "first":
                raise TimeoutError("fixture callback timeout")
        cleanup = candidate.attempt_cleanup_steps(journal, [(name, lambda n=name: callback(n)) for name in ("first", "second", "third")])
        snapshot = journal.snapshot()
        independent = audit(snapshot, path.read_bytes())
        assert calls == ["first", "second", "third"]
        return dict(snapshot=snapshot, independent=independent, cleanup=cleanup, capture_calls=clock.index)
    finally:
        journal.close()


CASES = ("complete", "step", "ambiguous", "wide", "partial", "wrong-domain", "API-error", "reserve", "exhaustion", "callback-error")


@pytest.mark.parametrize("case", CASES)
def test_retained_journal_and_independent_cleanup_dispatch(tmp_path, case):
    result = capture_case(tmp_path / "journal.jsonl", case)
    assert result["independent"]["observation_audit_passed"]
    assert result["cleanup"]["all_callbacks_attempted"]
    assert not result["cleanup"]["service_restored"]
    if case in ("step", "ambiguous", "wide", "partial", "wrong-domain", "API-error", "reserve", "exhaustion"):
        assert not result["independent"]["admission_open"]
    if case == "exhaustion":
        assert result["capture_calls"] == 1024
    if case == "API-error":
        assert result["capture_calls"] == 3


@pytest.mark.parametrize("name", [name for name in fixture_cases() if name != "record-limit"])
def test_incremental_all_prefixes_equal_frozen_primitive(name):
    b = fixture_cases()[name]["bundle"]
    if frozen_evaluate(b["descriptor"], b["points"])["rejection"] and frozen_evaluate(b["descriptor"], b["points"])["rejection"]["sequence"] is None and name != "incomplete-single-point":
        with pytest.raises(ValueError):
            candidate.Prefix(b["descriptor"])
        return
    prefix = candidate.Prefix(b["descriptor"])
    for i, row in enumerate(b["points"], 1):
        assert prefix.add(row) == frozen_evaluate(b["descriptor"], b["points"][:i])


def test_full_capacity_comparisons_are_quadratic_and_immutable(tmp_path):
    d, data = descriptor(), points(1024)
    prefix = candidate.Prefix(d)
    d["clock_id"] = "f" * 32
    for row in data:
        prefix.add(row)
    assert prefix.status() == frozen_evaluate(descriptor(), data)
    assert prefix.status()["comparisons"] == 523776
    with pytest.raises(ValueError, match="capacity"):
        prefix.add(data[-1])
    report = prefix.status()
    report["clock_capture_valid"] = False
    assert prefix.status()["clock_capture_valid"]


def test_no_skipped_cumulative_or_nonadjacent_pairs():
    for frequency in (1000000, 3125000, 10000000, 24000000, 10000000000):
        for step in (-600000, 0, 100, 600000):
            data = points(12, frequency=frequency, width=2)
            prefix = candidate.Prefix(descriptor(frequency))
            for i, row in enumerate(data):
                set_utc(row, row["utc_ns"] + i * step)
                prefix.add(row)
                assert prefix.status() == frozen_evaluate(descriptor(frequency), data[:i + 1])


def test_source_and_storage_failures_never_suppress_later_cleanup_callbacks(tmp_path):
    journal = candidate.Journal(FakeClock(), tmp_path / "journal.jsonl")
    calls = []
    try:
        with patch("os.fsync", side_effect=OSError("fixture disk unavailable")):
            report = candidate.attempt_cleanup_steps(journal, [(str(i), lambda n=i: calls.append(n)) for i in range(3)])
        assert calls == [0, 1, 2]
        assert all(row["errors"] for row in report["steps"])
        assert not journal.admitted()
        with pytest.raises(ValueError, match="storage failed"):
            audit(journal.snapshot(), (tmp_path / "journal.jsonl").read_bytes())
    finally:
        journal.close()


def test_first_read_and_returned_snapshot_cannot_admit_or_mutate(tmp_path):
    journal = candidate.Journal(FakeClock(), tmp_path / "journal.jsonl")
    try:
        assert journal.checkpoint("first") is None and not journal.admitted()
        assert audit(journal.snapshot(), (tmp_path / "journal.jsonl").read_bytes())["points_replayed"] == 1
        assert journal.checkpoint("second") == 2 and journal.admitted(points_needed=766)
        assert not journal.admitted(points_needed=767)
        snapshot = journal.snapshot()
        snapshot["descriptor"]["clock_id"] = "f" * 32
        snapshot["points"][0]["utc_ns"] = 0
        assert journal.admitted()
    finally:
        journal.close()
    assert not journal.admitted()


def test_bad_first_read_stays_negative_with_no_replacement(tmp_path):
    data = points(4)
    data[0]["capture_error"] = "fixture first failure"
    journal = candidate.Journal(FakeClock(data), tmp_path / "journal.jsonl")
    try:
        journal.checkpoint("first")
        journal.checkpoint("second-blocked")
        assert audit(journal.snapshot(), (tmp_path / "journal.jsonl").read_bytes())["points_replayed"] == 1
        assert journal.clock.index == 1
    finally:
        journal.close()


def test_independent_replay_survives_disabled_candidate(tmp_path):
    result = capture_case(tmp_path / "journal.jsonl", "step")
    with patch.object(candidate.Prefix, "add", side_effect=AssertionError("candidate forbidden")), \
         patch.object(candidate, "validate_descriptor", side_effect=AssertionError("candidate forbidden")), \
         patch("sandbox.reconnect_r5_clock.evaluate", side_effect=AssertionError("candidate forbidden")):
        assert audit(result["snapshot"], (tmp_path / "journal.jsonl").read_bytes())["observation_audit_passed"]


@pytest.mark.parametrize("mutation", ("reserve", "clock", "source", "admission", "report", "drop-event", "duplicate-event", "float-event", "invented-block", "promote", "partial-line"))
def test_resealed_journal_tampering_rejected(tmp_path, mutation):
    result = capture_case(tmp_path / "journal.jsonl", "API-error")
    s = result["snapshot"]
    if mutation == "reserve":
        s["events"][0]["reserved_cleanup_points"] = 0
    elif mutation == "clock":
        s["descriptor"]["clock_id"] = "f" * 32
    elif mutation == "source":
        s["capture_source_failed"] = False
    elif mutation == "admission":
        s["admission_open"] = True
    elif mutation == "report":
        s["reported"]["clock_capture_valid"] = False
    elif mutation == "drop-event":
        s["events"].pop(2)
    elif mutation == "duplicate-event":
        s["events"].insert(2, copy.deepcopy(s["events"][2]))
    elif mutation == "float-event":
        s["events"][1]["event"] = 2.0
    elif mutation == "invented-block":
        s["events"][-1]["reason"] = "cleanup-reserve"
    elif mutation == "promote":
        s["network_execution_authorized"] = True
    raw = ("\n".join(json.dumps(e) for e in s["events"]) + "\n").encode()
    if mutation == "partial-line":
        raw = raw[:-1]
    with pytest.raises(ValueError):
        audit(s, raw)


def test_journal_exclusive_create_and_duplicate_cleanup_denied(tmp_path):
    path = tmp_path / "journal.jsonl"
    journal = candidate.Journal(FakeClock(), path)
    try:
        with pytest.raises(FileExistsError):
            candidate.Journal(FakeClock(), path)
        with pytest.raises(ValueError):
            candidate.attempt_cleanup_steps(journal, [("same", lambda: None)] * 2)
    finally:
        journal.close()


def test_header_write_failure_closes_owned_handle_without_clock_read(tmp_path):
    path = tmp_path / "journal.jsonl"
    handle = path.open("xb")
    clock = FakeClock()
    with patch("pathlib.Path.open", return_value=handle), patch("os.fsync", side_effect=OSError("header sync unavailable")):
        with pytest.raises(OSError, match="header sync"):
            candidate.Journal(clock, path)
    assert handle.closed and clock.index == 0


@pytest.mark.parametrize("exception", [KeyboardInterrupt, SystemExit, TimeoutError, OSError])
def test_each_cleanup_step_runs_after_base_exceptions(tmp_path, exception):
    journal = candidate.Journal(FakeClock(fail_at=1), tmp_path / "journal.jsonl")
    calls = []
    def fails():
        calls.append("failed")
        raise exception("fixture interruption")
    try:
        result = candidate.attempt_cleanup_steps(journal, [("failed", fails), ("later", lambda: calls.append("later"))])
        assert calls == ["failed", "later"]
        assert result["all_callbacks_attempted"] and not result["steps"][0]["callback_returned"]
        replayed = audit(journal.snapshot(), (tmp_path / "journal.jsonl").read_bytes())
        assert replayed["points_replayed"] == 0 and replayed["capture_source_failed"]
    finally:
        journal.close()


def test_every_attempt_fsyncs_before_admission_or_audit(tmp_path):
    import os
    sync = os.fsync
    with patch("os.fsync", wraps=sync) as observed:
        journal = candidate.Journal(FakeClock(fail_at=3), tmp_path / "journal.jsonl")
        try:
            for i in range(5):
                journal.checkpoint(str(i))
            assert observed.call_count == 6  # header, two points, error, two blocked attempts
            assert not journal.admitted()
            audit(journal.snapshot(), (tmp_path / "journal.jsonl").read_bytes())
        finally:
            journal.close()
