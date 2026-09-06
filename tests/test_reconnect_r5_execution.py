"""Whole-protocol fixtures are never promoted to measured network evidence."""
import copy
import base64
import hashlib
import json
from unittest.mock import patch

import pytest
from tests.reconnect_r5_execution_fixture import capture_case, CASES
from tools.audit_reconnect_r5_execution import audit_path, audit, strict_json


def test_complete_four_trial_fixture(tmp_path):
    b = capture_case(tmp_path/"complete")
    r = b["result"]
    assert r["protocol_execution_valid"], r["errors"] or r["trials"]
    assert len(r["trials"]) == 4
    assert [t["recovery_15_of_15"] for t in r["trials"]] == [True, False, False, True]
    assert r["rollback"]["service_restored"]
    assert not r["network_fix_validated"] and not r["TNSM_ready"]
    audit = audit_path(tmp_path/"complete")
    assert audit["protocol_execution_valid"]
    assert audit["drop_recovery_15_of_15"] == [False, False]


@pytest.mark.parametrize("case", [c for c in CASES if c != "complete"])
def test_negative_whole_protocol(tmp_path, case):
    path = tmp_path/case
    b = capture_case(path, case)
    r = b["result"]
    assert r["evidence_label"] == "fixture"
    assert r["actual_network_commands_executed"] == r["actual_power_requests_executed"] == 0
    assert not r["protocol_execution_valid"]
    if case in ("execution-fsync", "ledger-fsync", "journal-fsync"):
        with pytest.raises(ValueError, match="storage failed"):
            audit_path(path)
    else:
        report = audit_path(path)
        (path/"independent.json").write_text(json.dumps(report, indent=2)+"\n")
        assert report["observation_audit_passed"] and not report["protocol_execution_valid"]
    if case in ("bad-baseline", "missing-fresh-pdu", "clock-step", "wide-clock", "source-unavailable", "changed-approval", "client-timeout", "global-budget"):
        assert not any(t["exposure"] for t in r["trials"])
    if case in ("bad-approval", "future-approval", "prior-attempt", "wrong-receipt", "existing-receipt"):
        assert not r["commands"] and not r["candidate_switch_attempted"]
    if case == "existing-receipt":
        assert (path/"attempt-receipt.jsonl").read_bytes() == b"unowned sentinel: do not overwrite\n"
    if r["candidate_switch_attempted"]:
        labels = [s["label"] for s in r["steps"] if s["cleanup"]]
        for target in ("safetwin5g-gnb", "safetwin5g-ue"):
            assert "switch-official-tag-"+target in labels
            assert ("switch-official-apply-"+target in labels) is not (case == "official-tag-drift" and target == "safetwin5g-gnb")
        for target in ("safetwin5g-open5gs", "safetwin5g-gnb", "safetwin5g-ue"):
            assert "restart-"+target in labels and "health-"+target in labels
        assert all("final-official:"+str(i) in labels for i in range(3))
        assert labels[-1] == "host-close"
    if case in ("power-clear-failed", "power-close-failed"):
        assert [c["name"] for c in r["host"]["power"]["calls"]] == ["create", "set", "clear", "close"]


@pytest.fixture(scope="module")
def raw_complete(tmp_path_factory):
    path = tmp_path_factory.mktemp("r5-global-audit")/"complete"
    b = capture_case(path)
    return b, (path/"clock.jsonl").read_bytes(), (path/"identifiers.jsonl").read_bytes(), (path/"execution.jsonl").read_bytes()


def test_candidate_acceptance_disabled(raw_complete):
    from sandbox import run_reconnect_r5, reconnect_r5_budget, reconnect_r5_collection, reconnect_r5_host
    with patch.object(run_reconnect_r5.Runner, "execute", side_effect=AssertionError("candidate disabled")), \
         patch.object(run_reconnect_r5, "clean", side_effect=AssertionError("candidate disabled")), \
         patch.object(reconnect_r5_budget.RunnerBudget, "health", side_effect=AssertionError("candidate disabled")), \
         patch.object(reconnect_r5_collection.Collector, "collect", side_effect=AssertionError("candidate disabled")), \
         patch.object(reconnect_r5_host.HostGuard, "snapshot", side_effect=AssertionError("candidate disabled")):
        assert audit(*raw_complete)["protocol_execution_valid"]


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(evidence_label="sandbox-measured"),
    lambda r: r.update(network_fix_validated=True),
    lambda r: r.update(TNSM_ready=True),
    lambda r: r.update(protocol_execution_valid=False),
    lambda r: r["trials"][1].update(recovery_15_of_15=True),
    lambda r: r["rollback"].update(service_restored=False),
    lambda r: r["rollback"]["samples"].pop(),
    lambda r: r["steps"].pop(),
    lambda r: r["commands"][5].update(sequence=1),
    lambda r: r["commands"][40].update(cleanup=True),
    lambda r: r["budget"]["admissions"].pop(),
    lambda r: r["ledger"]["events"][2].update(identifier=10001),
    lambda r: r["host"]["lease"]["header"].update(revision_sha256="c"*64),
    lambda r: r.update(final_ticks=True),
    lambda r: r.update(final_ticks=1),
    lambda r: r.update(actual_network_commands_executed=False),
    lambda r: r.update(terminal_event_before=3),
    lambda r: r["windows"][0].update(collection_valid=False),
])
def test_tamper_not_hidden_by_summary(raw_complete, mutate):
    b, journal, ledger, execution = raw_complete
    changed = copy.deepcopy(b)
    mutate(changed["result"])
    with pytest.raises(ValueError):
        audit(changed, journal, ledger, execution)


def test_duplicate_and_nonfinite_json_rejected():
    for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}'):
        with pytest.raises(ValueError):
            strict_json(raw)


@pytest.mark.parametrize("mutation", ["first-packet", "backdated-dispatch", "extra-scope", "renamed-cleanup"])
def test_consistently_rehashed_global_tamper(raw_complete, mutation):
    from tools.audit_reconnect_r5_execution import canonical, digest
    b, journal, ledger, _ = raw_complete
    b = copy.deepcopy(b)
    r = b["result"]
    target = next(row["sequence"] for row in r["commands"] if row["argv"][:4] == ["docker", "exec", "safetwin5g-ue", "ping"] and "10001" in row["argv"])
    def recurse(value):
        if type(value) is dict:
            if value.get("contract_id") == "safetwin5g-reconnect-r5-process-v1" and value["sequence"] == target:
                if mutation == "first-packet":
                    raw = "\n".join(line for line in value["stdout"].splitlines() if "icmp_seq=1 " not in line)+"\n"
                    raw = raw.replace("5 received, 0%", "4 received, 20%")
                    value.update(stdout=raw, stdout_base64=base64.b64encode(raw.encode()).decode(),
                                 stdout_sha256=hashlib.sha256(raw.encode()).hexdigest(), retained_output_bytes=len(raw.encode()))
                elif mutation == "backdated-dispatch":
                    value["go_after_ticks"] = value["go_before_ticks"]-1
                elif mutation == "extra-scope":
                    value["argv"][-1] = "8.8.8.8"
            if mutation == "extra-scope" and value.get("kind") == "command-intent" and value["sequence"] == target:
                value["argv"][-1] = "8.8.8.8"
            if mutation == "renamed-cleanup" and value.get("label") == "final-eth0":
                value["label"] = "unplanned-probe"
            for v in value.values():
                recurse(v)
        elif type(value) is list:
            for v in value:
                recurse(v)
    recurse(r)
    for event in r["execution_events"]:
        if event["kind"] == "command-result":
            event["record_sha256"] = digest(r["commands"][event["sequence"]-1])
    execution = "".join(canonical(e)+"\n" for e in r["execution_events"]).encode()
    with pytest.raises(ValueError):
        audit(b, journal, ledger, execution)


def test_cleanup_metadata_is_not_timing_or_unrestricted_permission(raw_complete):
    from sandbox.run_reconnect_r5 import cleanup_tag_usable
    r = raw_complete[0]["result"]
    base = next(row for row in r["commands"] if row["cleanup"] and row["argv"][:3] == ["docker", "image", "inspect"])
    clock_rejected = dict(base, complete=False, timing_valid=False)
    assert cleanup_tag_usable(clock_rejected)
    for key, value in (("timed_out", True), ("truncated", True), ("job_closed", False), ("process_reaped", False),
                       ("reader_threads_joined", False), ("returncode", True), ("returncode", 1), ("stdout_utf8", False),
                       ("stderr", "failed"), ("process_errors", ["failed"]), ("cleanup_errors", ["job close failed"])):
        assert not cleanup_tag_usable(dict(clock_rejected, **{key: value}))


def test_native_execution_mode_is_disabled():
    from sandbox.run_reconnect_r5 import Runner
    with pytest.raises(ValueError, match="fixture-only"):
        Runner(None, None, None, None, None, None, None, None, None, fixture=False)


def test_execution_lock_binds_all_sources_and_prior_components():
    from tools.verify_reconnect_r5_execution import verify_lock
    assert verify_lock()["native_execution_enabled"] is False
