"""Audit a Phase 7 pilot or campaign bundle without trusting its summary."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.phase7_runner import validate_named_action_trace  # noqa: E402


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
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--expected-units", type=int, required=True)
    parser.add_argument("--expected-blocks", type=int, required=True)
    args = parser.parse_args()
    run = args.run if args.run.is_absolute() else ROOT / args.run
    manifest = load_json(run / "manifest.json")
    expected_files = manifest["captured_file_sha256"]
    actual_files = {
        str(path.relative_to(run)).replace("\\", "/")
        for path in run.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    assert actual_files == set(expected_files), "manifest file coverage differs"
    for relative, expected_hash in expected_files.items():
        assert sha256(run / relative) == expected_hash, relative

    summary = load_json(run / "summary.json")
    approval = load_json(run / "approval.json")
    environment = load_json(run / "environment.json")
    design_units = [
        json.loads(line)
        for line in (run / "design-units.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    traces = [load_json(path) for path in sorted((run / "units").glob("*.json"))]
    commands = [
        json.loads(line)
        for line in (run / "commands.jsonl").read_text(encoding="utf-8").splitlines()
    ]

    assert manifest["passed"] is True
    assert summary["passed"] is True
    assert summary["completed_unit_count"] == args.expected_units
    assert summary["completed_block_count"] == args.expected_blocks
    assert summary["planned_unit_count"] == args.expected_units
    assert summary["planned_block_count"] == args.expected_blocks
    assert len(design_units) == len(traces) == args.expected_units
    assert len({unit["unit_id"] for unit in design_units}) == args.expected_units
    assert len({unit["assignment_block_id"] for unit in design_units}) == args.expected_blocks
    assert {unit["action_id"] for unit in design_units} == {
        "observe_only",
        "clear_packet_impairment",
        "resume_upf",
        "stop_cpu_stress",
        "apply_packet_impairment_25",
    }

    assert approval["approval_status"] == "approved"
    assert approval["environment"] == "sandbox"
    assert set(approval["unit_ids"]) == {unit["unit_id"] for unit in design_units}
    assert "live actuation" in approval["exclusions"]
    assert len(approval["authorized_action_ids"]) == 4
    assert all(
        state["status"] == "running" and state["health"] == "healthy"
        for state in environment["containers"].values()
    )
    assert commands
    assert all(command["returncode"] in command["accepted_returncodes"] for command in commands)

    mutation_count = 0
    for trace in traces:
        unit = trace["unit"]
        for stage in ("baseline", "recovery"):
            samples = trace["windows"][stage]["samples"]
            assert len(samples) == 3 and all(
                0.0 <= float(sample["metrics"].get("packet_loss_pct", float("inf"))) <= 1.0
                for sample in samples
            ), f"user-plane {stage} failed: {unit['unit_id']}"
        recomputed = validate_named_action_trace(unit, trace, 3)
        assert recomputed == trace["checks"], unit["unit_id"]
        assert trace["passed"] is True
        assert trace["cleanup_verified"] is True
        assert trace["approval_id"] == approval["approval_id"]
        assert trace["claim_boundaries"] == {
            "intervention": "sandbox-measured",
            "radio_access": "simulated",
            "hardware": "not measured",
            "operator_validation": "not performed",
            "model_result": "not applicable during randomized data collection",
        }
        if unit["mutates"]:
            mutation_count += 1
            proposal = trace["action_proposal"]
            assert proposal["reversible"] is True
            assert proposal["rollback_plan"]
            assert trace["safety_evaluation"]["decision"] == "require-human-approval"
        else:
            assert trace["action_proposal"] is None
            assert trace["safety_evaluation"]["decision"] == "observe-only"

    assert mutation_count == summary["experimental_mutation_count"]
    assert summary["model_selected_action_count"] == 0
    assert summary["aborted_for_cleanup"] is False
    assert summary["evidence_label"] == "sandbox-measured"
    assert summary["radio_evidence_label"] == "simulated"
    assert summary["hardware_evidence_label"] is None
    assert summary["operator_validation"] is False
    print(
        f"PASS: {args.expected_units} units, {args.expected_blocks} complete blocks, "
        f"{mutation_count} approved mutations, command hashes, states, and clean recovery verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
