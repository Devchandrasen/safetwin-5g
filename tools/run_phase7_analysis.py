"""Open the sealed v2a labels and run the frozen Phase 7 analysis exactly once."""

from __future__ import annotations

from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.analysis_v2a import analyze, load_records  # noqa: E402
from safetwin5g.dataset_v1 import sha256, verify_manifest  # noqa: E402


DEFAULT_DATASET = ROOT / "data" / "releases" / "safetwin5g-named-actions-v2a"
LOCK_PATH = ROOT / "config" / "experiments" / "phase7-analysis-v2a-lock.json"


def verify_analysis_lock() -> dict:
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    if lock.get("frozen_before_test_labels") is not True:
        raise ValueError("analysis lock is not marked frozen before test labels")
    for item in lock["files"]:
        path = ROOT / item["path"]
        if sha256(path) != item["sha256"]:
            raise ValueError(f"analysis source changed after freeze: {item['path']}")
    return lock


def render_markdown(report: dict) -> str:
    gates = report["gates"]
    lines = [
        "# SafeTwin-5G Phase 7 BRACE Decision",
        "",
        "Evidence: `sandbox-measured` intervention; `simulated` radio.  ",
        "Hardware measured: `no`; operator validated: `no`; live actuation: `no-go`.",
        "",
        "## Outcome",
        "",
        f"- TNSM claim gate: **{report['decision']['TNSM_claim_gate'].upper()}**",
        f"- G1 simultaneous coverage: `{gates['G1']['passed']}`",
        f"- G2 certificate validity/utility: `{gates['G2']['passed']}`",
        f"- G3 comparative safety: `{gates['G3']['passed']}`",
        f"- G4 operational recovery: `{gates['G4']['passed']}`",
        "",
        "## Primary denominators",
        "",
        f"- G1: `{gates['G1']['covered_block_n']}/{gates['G1']['block_n']}` complete test blocks covered.",
        f"- G2: `{gates['G2']['certified_mutation_n']}/{gates['G2']['faulty_test_block_n']}` faulty blocks certified; "
        f"`{gates['G2']['margin_violation_n']}` margin violations.",
        f"- G3: BRACE `{gates['G3']['brace_harm_n']}` harms versus matched point policy "
        f"`{gates['G3']['point_policy_harm_n']}` across `{gates['G3']['matched_faulty_block_n']}` paired faulty blocks.",
        "",
        "## Claim boundary",
        "",
        "The result is a single-host isolated software-sandbox experiment with a simulated UERANSIM radio. "
        "It is not hardware-measured, operator-validated, conditional-coverage, or live-network evidence. "
        "A no-go result remains a valid outcome and is not retuned after test-label opening.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    args = parser.parse_args()
    dataset = args.dataset if args.dataset.is_absolute() else ROOT / args.dataset
    lock = verify_analysis_lock()
    verify_manifest(dataset / "manifest.json")
    dataset_manifest = json.loads((dataset / "manifest.json").read_text(encoding="utf-8"))
    if (
        dataset_manifest.get("dataset_version") != "safetwin5g-named-actions-v2a"
        or dataset_manifest.get("record_count") != 675
        or dataset_manifest.get("passed") is not True
    ):
        raise ValueError("analysis requires the complete passing frozen v2a release")

    started = datetime.now(timezone.utc)
    report, policy_rows = analyze(load_records(dataset / "records.jsonl"))
    run_id = started.strftime("%Y%m%dT%H%M%SZ-phase7-brace-v2a")
    output = ROOT / "evidence" / "benchmarks" / run_id
    output.mkdir(parents=True, exist_ok=False)
    report.update(
        {
            "run_id": run_id,
            "started_at": started.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "execution_passed": True,
            "analysis_lock_sha256": sha256(LOCK_PATH),
            "dataset_manifest_sha256": sha256(dataset / "manifest.json"),
        }
    )
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "report.md").write_text(render_markdown(report), encoding="utf-8")
    (output / "policy-decisions.jsonl").write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in policy_rows
        ),
        encoding="utf-8",
    )
    source_evidence = {
        "schema_version": 1,
        "analysis_lock": lock,
        "analysis_lock_sha256": sha256(LOCK_PATH),
        "dataset_manifest": str((dataset / "manifest.json").relative_to(ROOT)).replace("\\", "/"),
        "dataset_manifest_sha256": sha256(dataset / "manifest.json"),
        "test_labels_opened_after_lock_verification": True,
    }
    (output / "source-evidence.json").write_text(
        json.dumps(source_evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    captured = {
        path.name: sha256(path)
        for path in sorted(output.iterdir())
        if path.is_file() and path.name != "manifest.json"
    }
    manifest = {
        "schema_version": 1,
        "run_id": run_id,
        "passed": True,
        "TNSM_claim_gate": report["decision"]["TNSM_claim_gate"],
        "live_actuation": "no-go",
        "evidence_label": "sandbox-measured",
        "radio_evidence_label": "simulated",
        "hardware_evidence_label": None,
        "operator_validation": False,
        "captured_file_sha256": captured,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(output)
    print(json.dumps(report["decision"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
