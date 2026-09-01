from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit(diagnostic_root: Path, source_run: Path) -> dict[str, Any]:
    errors: list[str] = []
    manifest = _load(diagnostic_root / "manifest.json")
    diagnostic = _load(diagnostic_root / "diagnostic.json")
    events = _load(diagnostic_root / "power-events.json")
    source_index = _load(diagnostic_root / "source-index.json")

    for name, expected in manifest["captured_file_sha256"].items():
        path = diagnostic_root / name
        if not path.is_file():
            errors.append(f"missing captured file: {name}")
        elif _sha256(path) != expected:
            errors.append(f"captured hash mismatch: {name}")

    indexed_paths = set()
    for item in source_index:
        relative = item["path"]
        indexed_paths.add(relative)
        path = source_run / Path(relative)
        if not path.is_file():
            errors.append(f"missing source file: {relative}")
        elif _sha256(path) != item["sha256"]:
            errors.append(f"source hash mismatch: {relative}")

    current_paths = {
        path.relative_to(source_run).as_posix()
        for path in source_run.rglob("*")
        if path.is_file()
    }
    if indexed_paths != current_paths:
        errors.append("source index membership mismatch")

    unit_count = sum(1 for path in current_paths if path.startswith("units/"))
    if unit_count != diagnostic["completed_trace_count"]:
        errors.append("completed trace count mismatch")
    if diagnostic["planned_unit_count"] != 675:
        errors.append("unexpected planned unit count")
    if diagnostic["design_unit_count"] != 675:
        errors.append("unexpected design unit count")
    if diagnostic["completed_trace_count"] >= diagnostic["planned_unit_count"]:
        errors.append("interrupted campaign is not partial")
    if diagnostic["final_manifest_present"]:
        errors.append("source unexpectedly has a final manifest")
    if diagnostic["summary_present"]:
        errors.append("source unexpectedly has a summary")
    if diagnostic["campaign_process_present_at_capture"]:
        errors.append("campaign process was present at capture")
    if diagnostic["stderr_bytes"] != 0:
        errors.append("runner stderr was not empty")

    event_ids = [event["event_id"] for event in events]
    if event_ids != [42, 107]:
        errors.append(f"unexpected power-event sequence: {event_ids}")
    if "Sleep Reason: Application API" not in events[0]["message"]:
        errors.append("sleep event lacks Application API reason")

    admissibility = diagnostic["admissibility"]
    for field in (
        "campaign_complete",
        "dataset_release_eligible",
        "outcome_analysis_eligible",
        "partial_trace_reusable",
        "resume_permitted",
    ):
        if admissibility[field]:
            errors.append(f"inadmissible field is true: {field}")

    return {
        "schema_version": 1,
        "passed": not errors,
        "errors": errors,
        "source_file_count": len(current_paths),
        "completed_trace_count": unit_count,
        "last_progress_line": diagnostic["last_progress_line"],
        "outcome_analysis_performed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnostic", type=Path, required=True)
    parser.add_argument("--source-run", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.diagnostic.resolve(), args.source_run.resolve())
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
