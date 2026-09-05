"""Verify that resume preserves completed units and the original command prefix."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.capture_phase7_resume import digest  # noqa: E402


def audit(checkpoint: Path, run: Path) -> dict:
    manifest = json.loads((checkpoint / "manifest.json").read_text(encoding="utf-8"))
    for name, expected in manifest["captured_file_sha256"].items():
        if digest(checkpoint / name) != expected:
            raise ValueError(f"checkpoint hash mismatch: {name}")
    saved = json.loads((checkpoint / "checkpoint.json").read_text(encoding="utf-8"))
    checked = 0
    for name, item in saved["source_files"].items():
        if name in {"environment.json", "commands.jsonl"}:
            original = checkpoint / ("before-resume-" + name)
        else:
            original = run / name
        if original.stat().st_size != item["bytes"] or digest(original) != item["sha256"]:
            raise ValueError(f"original source changed: {name}")
        checked += 1
    prefix = saved["source_files"]["commands.jsonl"]
    remaining = prefix["bytes"]
    hasher = hashlib.sha256()
    with (run / "commands.jsonl").open("rb") as stream:
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                raise ValueError("resumed command log lost original bytes")
            hasher.update(chunk)
            remaining -= len(chunk)
    if hasher.hexdigest() != prefix["sha256"]:
        raise ValueError("resumed command prefix changed")
    return {
        "passed": True,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "original_files_verified": checked,
        "original_command_prefix_bytes": prefix["bytes"],
        "saved_units_preserved": saved["saved_unit_count"],
        "outcome_analysis_performed": False,
        "campaign_acceptance_evaluated": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(ROOT / args.checkpoint, ROOT / args.run), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
