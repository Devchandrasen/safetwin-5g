"""Evaluate, record, and hash-manifest the local TNSM manuscript gate."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.dataset_v1 import sha256  # noqa: E402
from safetwin5g.tnsm_gate import assess_tnsm_manuscript_gate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--end-to-end-verification", type=Path, required=True)
    args = parser.parse_args()
    analysis_path = args.analysis if args.analysis.is_absolute() else ROOT / args.analysis
    verification_path = (
        args.end_to_end_verification
        if args.end_to_end_verification.is_absolute()
        else ROOT / args.end_to_end_verification
    )
    report_path = analysis_path / "report.json"
    analysis_report = json.loads(report_path.read_text(encoding="utf-8"))
    end_to_end = json.loads(verification_path.read_text(encoding="utf-8"))
    result = assess_tnsm_manuscript_gate(analysis_report, end_to_end)
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ-tnsm-manuscript-gate")
    output = ROOT / "evidence" / "decisions" / run_id
    output.mkdir(parents=True, exist_ok=False)
    result.update(
        {
            "run_id": run_id,
            "evaluated_at": started.isoformat(),
            "analysis_report_sha256": sha256(report_path),
            "end_to_end_verification_sha256": sha256(verification_path),
        }
    )
    (output / "decision.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "passed": result["passed"],
        "local_manuscript_draft_gate": result["local_manuscript_draft_gate"],
        "publication_submission": "pending-external-authorization",
        "live_actuation": "no-go",
        "captured_file_sha256": {"decision.json": sha256(output / "decision.json")},
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(output)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
