"""Preserve a stopped campaign's provenance before the existing runner resumes it.

This reads design, approval, cleanup flags, command integrity, and file hashes.
It never summarizes telemetry, benefit, harm, model scores, or passed flags.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from sandbox.run_phase7 import (  # noqa: E402
    DESIGN_PATH, POLICY_PATH, expand_phase7_design, load_phase7_design, validate_policy,
)
from safetwin5g.safety import SafetyPolicy  # noqa: E402
from tools.run_phase7_analysis import verify_analysis_lock  # noqa: E402


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inspect_checkpoint(run: Path) -> dict:
    if (run / "manifest.json").exists() or (run / "summary.json").exists():
        raise ValueError("checkpoint must be an interrupted run without terminal artifacts")
    design = load_phase7_design(DESIGN_PATH)
    units = expand_phase7_design(design)
    saved_units = [json.loads(line) for line in (run / "design-units.jsonl").read_text().splitlines()]
    if saved_units != units:
        raise ValueError("saved assignment or order differs from frozen design")
    validate_policy(units, SafetyPolicy.from_path(POLICY_PATH))
    lock = verify_analysis_lock()
    approval = json.loads((run / "approval.json").read_text())
    if (approval["experiment_id"] != design["experiment_id"]
            or approval["approval_status"] != "approved"
            or approval["environment"] != "sandbox"
            or approval["unit_ids"] != [unit["unit_id"] for unit in units]):
        raise ValueError("saved approval does not cover the frozen campaign")
    by_id = {unit["unit_id"]: unit for unit in units}
    completed = set()
    for path in sorted((run / "units").glob("*.json")):
        trace = json.loads(path.read_text())
        uid = trace["unit"]["unit_id"]
        if uid in completed or trace["unit"] != by_id.get(uid) or path.stem != uid:
            raise ValueError("duplicate or mismatched saved unit identity")
        if trace.get("cleanup_verified") is not True or trace.get("approval_id") != approval["approval_id"]:
            raise ValueError(f"saved cleanup or approval invalid: {uid}")
        completed.add(uid)
    ordered_completed = [unit["unit_id"] for unit in units if unit["unit_id"] in completed]
    if ordered_completed != [unit["unit_id"] for unit in units[:len(completed)]]:
        raise ValueError("saved units are not a contiguous prefix of the design")
    command_count = 0
    unfinished = set()
    with (run / "commands.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            command = json.loads(line)
            command_count += 1
            actual = hashlib.sha256(command["stdout"].encode("utf-8")).hexdigest()
            if actual != command["stdout_sha256"]:
                raise ValueError("command output hash mismatch")
            if command["returncode"] not in command["accepted_returncodes"]:
                raise ValueError("unaccepted command return code in saved prefix")
            if command["unit_id"] != "preflight" and command["unit_id"] not in completed:
                unfinished.add(command["unit_id"])
    remaining = [unit["unit_id"] for unit in units if unit["unit_id"] not in completed]
    if not remaining or unfinished - {remaining[0]}:
        raise ValueError("interrupted command trail differs from the next missing unit")
    return {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "source_run": run.relative_to(ROOT).as_posix(),
        "verification_scope": "resume provenance and cleanup only, not campaign acceptance",
        "resume_preflight_passed": True,
        "campaign_accepted": False,
        "outcome_analysis_performed": False,
        "saved_unit_count": len(completed),
        "remaining_unit_count": len(remaining),
        "next_unit_id": remaining[0],
        "unfinished_command_unit_ids": sorted(unfinished),
        "verified_command_count": command_count,
        "analysis_lock_id": lock["lock_id"],
        "source_files": {
            path.relative_to(run).as_posix(): {"sha256": digest(path), "bytes": path.stat().st_size}
            for path in sorted(run.rglob("*")) if path.is_file()
        },
        "limitations": [
            "User requested a pause after 546 durable units on 2026-09-01; one unfinished unit has commands but no durable trace.",
            "Original commands are preserved; the existing runner reruns only the missing unit and appends commands with a new sequence counter.",
            "Resume overwrites environment.json and gives summary.started_at the resume time; this snapshot preserves the original environment and command timestamps.",
            "A host shutdown and four-day time gap split collection; time and shared-host effects must be disclosed in any downstream result.",
            "Complete block, recovery, command, dataset, and statistical audits remain required at terminal completion.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run = (ROOT / args.run).resolve()
    output = (ROOT / args.output).resolve()
    run.relative_to(ROOT / "evidence" / "scenarios")
    output.relative_to(ROOT / "evidence" / "environment")
    report = inspect_checkpoint(run)
    output.mkdir(parents=True, exist_ok=False)
    for name in ("approval.json", "design-units.jsonl", "environment.json", "commands.jsonl"):
        shutil.copyfile(run / name, output / ("before-resume-" + name))
    (output / "checkpoint.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    hashes = {path.name: digest(path) for path in sorted(output.iterdir()) if path.is_file()}
    (output / "manifest.json").write_text(json.dumps({"captured_file_sha256": hashes}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "resume_preflight_passed", "saved_unit_count", "remaining_unit_count", "next_unit_id",
        "verified_command_count", "campaign_accepted", "outcome_analysis_performed",
    )}, indent=2))
    print(output)


if __name__ == "__main__":
    main()
