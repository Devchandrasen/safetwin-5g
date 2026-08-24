"""Audit a Phase 6 pilot bundle before accepting the runner gate."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot", type=Path, required=True)
    args = parser.parse_args()
    pilot = args.pilot if args.pilot.is_absolute() else ROOT / args.pilot
    manifest = load_json(pilot / "manifest.json")
    expected = manifest["captured_file_sha256"]
    actual_files = {
        str(path.relative_to(pilot)).replace("\\", "/")
        for path in pilot.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    assert actual_files == set(expected), "manifest coverage mismatch"
    for relative, expected_hash in expected.items():
        assert sha256(pilot / relative) == expected_hash, f"hash mismatch: {relative}"

    summary = load_json(pilot / "summary.json")
    assert summary["artifact_type"] == "runner-pilot"
    assert summary["passed"] is True
    assert summary["planned_unit_count"] == 3
    assert summary["completed_unit_count"] == 3
    assert summary["passed_unit_count"] == 3
    assert summary["aborted_for_cleanup"] is False
    assert summary["evidence_label"] == "sandbox-measured"
    assert summary["radio_evidence_label"] == "simulated"
    assert summary["hardware_evidence_label"] is None
    assert summary["operator_validation"] is False

    approval = load_json(pilot / "approval.json")
    assert approval["approval_status"] == "approved"
    assert approval["environment"] == "sandbox"
    assert "live actuation" in approval["exclusions"]
    assert "private-5G hardware" in approval["exclusions"]

    traces = [load_json(path) for path in sorted((pilot / "units").glob("*.json"))]
    assert len(traces) == 3
    assert {trace["unit"]["action_arm"] for trace in traces} == {
        "effective",
        "no_action",
        "negative_control",
    }
    assert {trace["unit"]["fault_family"] for trace in traces} == {
        "cpu_saturation",
        "network_function_interruption",
        "packet_impairment",
    }
    for trace in traces:
        assert trace["passed"] is True
        assert trace["cleanup_verified"] is True
        assert trace["claim_boundaries"]["intervention"] == "sandbox-measured"
        assert trace["claim_boundaries"]["radio_access"] == "simulated"
        assert set(trace["windows"]) == {
            "baseline",
            "fault",
            "post_action",
            "recovery",
        }
        for window in trace["windows"].values():
            assert len(window["samples"]) == 3
            timestamps = [
                datetime.fromisoformat(sample["observed_at"])
                for sample in window["samples"]
            ]
            assert timestamps == sorted(timestamps)
        if trace["action_proposal"] is None:
            assert trace["safety_evaluation"]["decision"] == "observe-only"
        else:
            assert trace["action_proposal"]["reversible"] is True
            assert trace["action_proposal"]["rollback_plan"]
            assert (
                trace["safety_evaluation"]["decision"]
                == "require-human-approval"
            )

    command_lines = (pilot / "commands.jsonl").read_text(encoding="utf-8").splitlines()
    assert command_lines
    for line in command_lines:
        record = json.loads(line)
        assert hashlib.sha256(record["stdout"].encode("utf-8")).hexdigest() == record[
            "stdout_sha256"
        ]
        assert record["returncode"] in record["accepted_returncodes"]

    print(
        "PASS: 3/3 sandbox-measured pilot units; all action arms, three-sample "
        "windows, approvals, command outputs, hashes, and clean recovery verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
