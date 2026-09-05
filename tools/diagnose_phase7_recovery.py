"""Preserve terminal recovery rejection without running policy/model analysis."""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from safetwin5g.dataset_v1 import sha256, verify_manifest  # noqa: E402
from safetwin5g.dataset_v2a import build_records, quality_report  # noqa: E402
from tools.run_phase7_analysis import verify_analysis_lock  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run = ROOT / args.run
    output = ROOT / args.output
    lock = verify_analysis_lock()
    verify_manifest(run / "manifest.json")
    records = build_records(run)
    quality = quality_report(records)
    affected = []
    first_bad = {}
    for path in sorted((run / "units").glob("*.json")):
        trace = json.loads(path.read_text(encoding="utf-8"))
        for stage in ("baseline", "recovery"):
            samples = trace["windows"][stage]["samples"]
            bad = [sample for sample in samples if sample["metrics"]["packet_loss_pct"] > 1.0]
            if not bad:
                continue
            row = {
                "unit_id": trace["unit"]["unit_id"],
                "block_id": trace["unit"]["assignment_block_id"],
                "split": trace["unit"]["split"],
                "stage": stage,
                "started_at": trace["started_at"],
                "sample_count": len(samples),
                "failed_sample_count": len(bad),
                "loss_percentages": [sample["metrics"]["packet_loss_pct"] for sample in samples],
                "observed_at": [sample["observed_at"] for sample in samples],
                "configuration_clean": all(
                    sample["metrics"]["configured_packet_loss_pct"] == 0
                    and sample["metrics"]["upf_process_running"] == 1
                    and sample["metrics"]["stress_workers_count"] == 0
                    for sample in samples
                ),
            }
            affected.append(row)
            if stage not in first_bad or row["started_at"] < first_bad[stage]["started_at"]:
                first_bad[stage] = row
    summary = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_run": args.run.as_posix(),
        "source_manifest_sha256": sha256(run / "manifest.json"),
        "analysis_lock_verified": lock["lock_id"],
        "collection_completed": len(records) == 675,
        "dataset_release_eligible": quality["release_eligible"],
        "failed_dataset_checks": [key for key, value in quality["checks"].items() if not value],
        "affected_unit_counts": dict(Counter(row["stage"] for row in affected)),
        "affected_sample_counts": {
            stage: sum(row["failed_sample_count"] for row in affected if row["stage"] == stage)
            for stage in ("baseline", "recovery")
        },
        "first_failed_windows": first_bad,
        "mttr_status_counts": quality["mttr_status_counts"],
        "configuration_clean_but_service_failed_windows": sum(row["configuration_clean"] for row in affected),
        "model_fitted": False,
        "policy_comparisons_run": False,
        "TNSM_manuscript_gate": "no-go-data-quality",
        "live_actuation": "no-go",
        "submission_authorized": False,
        "decision": "Preserve all 675 traces as rejected operational evidence; no v2a release or confirmatory analysis.",
        "limitations": [
            "P1: collection spans September 1 and September 5 with a host restart; original prefix is preserved separately.",
            "D1: software sandbox shares host resources with unrelated containers; no exclusive-host evidence.",
            "The Phase 7 runner's original clean predicate checks configured fault state but omits observed packet loss; the frozen dataset gate checks both.",
            "This diagnosis inspects baseline/recovery telemetry and censoring status only; it is not BRACE or comparator evidence.",
            "Intervention is sandbox-measured, radio simulated, hardware not measured, operator not validated.",
        ],
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "diagnosis.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "affected-windows.jsonl").write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in affected), encoding="utf-8")
    # Keep only structural QA, not action-benefit or harmful-action aggregates.
    structural = {key: quality[key] for key in (
        "checks", "record_count", "split_counts", "assignment_block_count",
        "telemetry_sample_count", "metric_cells", "missing_metric_cells", "mttr_status_counts",
    )}
    (output / "structural-quality.json").write_text(json.dumps(structural, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    hashes = {path.name: sha256(path) for path in output.iterdir() if path.is_file()}
    (output / "manifest.json").write_text(json.dumps({"captured_file_sha256": hashes, "dataset_release_eligible": False}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in (
        "dataset_release_eligible", "failed_dataset_checks", "affected_unit_counts", "affected_sample_counts",
        "mttr_status_counts", "TNSM_manuscript_gate",
    )}, indent=2))
    print(output)


if __name__ == "__main__":
    main()
