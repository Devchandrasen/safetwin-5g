"""Read-only replay and tamper tests; no daemon/process execution."""
import base64
import copy
import json
from pathlib import Path
import shutil

import pytest
from tools import audit_reconnect_r4_observation as audit


def rewrite(path, name, value):
    (path / name).write_text(json.dumps(value) + "\n", encoding="utf-8")
    seal(path)


def seal(path):
    inventory = {p.name: audit.sha(p.read_bytes()) for p in path.iterdir() if p.name != "manifest.json"}
    (path / "manifest.json").write_text(json.dumps({"captured_file_sha256": inventory}), encoding="utf-8")


@pytest.fixture
def aftercare(tmp_path):
    return Path(shutil.copytree(audit.AFTERCARE, tmp_path / "aftercare"))


@pytest.fixture
def probe(tmp_path):
    return Path(shutil.copytree(audit.PROBE, tmp_path / "probe"))


def test_original_rejection_and_later_service_are_separate():
    result = audit.audit()
    assert result["observation_audit_passed"]
    assert result["actual_docker_commands"] == 54
    assert result["original"]["commands_replayed"] == 55
    assert not result["original"]["final_service_restored"]
    assert result["later_service"]["packets_received"] == 15
    assert not result["later_service"]["R4_clock_consistency_accepted"]
    assert not result["protocol_execution_valid"] and not result["TNSM_ready"]
    assert [r["sequence"] for r in result["original_clock_flags"]] == [25, 36, 51]


@pytest.mark.parametrize("field,value", [
    ("mutations_authorized", True), ("original_R4_verdict_unchanged", False),
    ("R4_clock_consistency_acceptance_claimed", True), ("evidence_label", "hardware-measured"),
    ("source_sha256", "0" * 64), ("original_manifest_sha256", "0" * 64),
])
def test_design_promotion_rejected(aftercare, field, value):
    design = audit.read(aftercare / "design.json")
    design[field] = value
    rewrite(aftercare, "design.json", design)
    with pytest.raises(ValueError):
        audit.audit_aftercare(aftercare)


def test_unsealed_extra_file_rejected(aftercare):
    (aftercare / "extra.txt").write_text("not captured", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory"):
        audit.audit_aftercare(aftercare)


@pytest.mark.parametrize("mutation", ["truncated", "wrong_id", "wrong_command", "bad_bytes", "missing_reply",
                                    "repeated_reply", "wrong_source", "wrong_image", "unhealthy", "lost_prefix"])
def test_raw_tampering_rejected_even_when_resealed(aftercare, mutation):
    rows = audit.lines((aftercare / "commands.jsonl").read_text())
    if mutation == "truncated":
        rows[4]["truncated"] = True
    elif mutation == "wrong_id":
        rows[4]["argv"][7] = "10092"
    elif mutation == "wrong_command":
        rows[4]["argv"] = ["docker", "restart", audit.UE]
    elif mutation == "bad_bytes":
        rows[4]["stdout_base64"] = base64.b64encode(b"wrong").decode()
    else:
        index = 4 if mutation in ("missing_reply", "repeated_reply", "wrong_source") else 1 if mutation == "unhealthy" else 2 if mutation == "wrong_image" else 12
        row = rows[index]
        if mutation == "missing_reply":
            row["stdout"] = "\n".join(line for line in row["stdout"].splitlines() if "icmp_seq=1" not in line) + "\n"
        elif mutation == "repeated_reply":
            row["stdout"] = row["stdout"].replace("icmp_seq=2", "icmp_seq=1")
        elif mutation == "wrong_source":
            row["stdout"] = row["stdout"].replace("10.45.0.2", "10.45.0.4")
        elif mutation == "wrong_image":
            row["stdout"] = row["stdout"].replace(audit.IMAGES["official_image_id"], audit.IMAGES["derived_image_id"])
        elif mutation == "unhealthy":
            row["stdout"] = row["stdout"].replace('"healthy"', '"starting"')
        else:
            row["stdout"] = "\n".join(row["stdout"].splitlines()[1:]) + "\n"
        raw = row["stdout"].encode()
        row["stdout_base64"], row["stdout_sha256"] = base64.b64encode(raw).decode(), audit.sha(raw)
        row["retained_output_bytes"] = len(raw) + len(base64.b64decode(row["stderr_base64"]))
    (aftercare / "commands.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    seal(aftercare)
    with pytest.raises(ValueError):
        audit.audit_aftercare(aftercare)


def test_later_probe_does_not_reproduce_historical_failure():
    result = audit.audit_probe()
    assert result["comparisons"]["python_wall"]["beyond_1ms"] == 0
    assert result["comparisons"]["precise_UTC"]["beyond_1ms"] == 0
    assert not result["historical_R4_clock_step_proven"]
    assert not result["historical_timestamps_repaired"]


@pytest.mark.parametrize("mutation", ["epoch", "bracket", "index", "count", "source", "claim"])
def test_probe_tamper_rejected(probe, mutation):
    data = audit.read(probe / "probe.json")
    if mutation == "epoch":
        data["rows"][0]["precise_unix_ns"] += 100
    elif mutation == "bracket":
        data["rows"][0]["qpc_between_ns"] = data["rows"][0]["qpc_after_ns"] + 1
    elif mutation == "index":
        data["rows"][0]["index"] = 1
    elif mutation == "count":
        data["rows"].pop()
    elif mutation == "source":
        data["source_sha256"] = "0" * 64
    else:
        data["historical_R4_verdict_unchanged"] = False
    rewrite(probe, "probe.json", data)
    with pytest.raises(ValueError):
        audit.audit_probe(probe)


def test_quantization_can_exceed_frozen_guard_without_any_real_clock_step():
    # Deterministic counterexample only, not a replay or attribution of R4.
    quantum = 15625000
    true_a, true_b = 1000000, 5652000
    coarse_a, coarse_b = (t // quantum * quantum for t in (true_a, true_b))
    assert true_b - true_a == 4652000
    assert abs((coarse_b - coarse_a) - (true_b - true_a)) > 1000000
    assert (true_b - true_a) - (true_b - true_a) == 0


def test_bracket_includes_read_scheduling_uncertainty_without_midpoint():
    a = dict(wall=10, lo=0, hi=5)
    b = dict(wall=19, lo=10, hi=20)
    assert audit.interval_disagreement(a, b, "wall", "lo", "hi") == 0
    b["wall"] = 40
    assert audit.interval_disagreement(a, b, "wall", "lo", "hi") == 10
