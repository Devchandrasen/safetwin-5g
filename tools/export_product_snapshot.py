"""Export a deterministic, read-only product snapshot from verified evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.reporting import load_json, sha256, verify_manifest  # noqa: E402


BENCHMARK = ROOT / "evidence" / "benchmarks" / "20260824T054718Z-benchmark-report-v0"
SAFETY = ROOT / "evidence" / "benchmarks" / "20260824T054104Z-safety-integration-v0"
DATASET = ROOT / "data" / "releases" / "safetwin5g-interventions-v0"
OUTPUT = ROOT / "dashboard" / "app" / "data" / "status.json"


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def build_snapshot() -> dict:
    for bundle in (BENCHMARK, SAFETY, DATASET):
        verify_manifest(bundle / "manifest.json")
    benchmark = load_json(BENCHMARK / "report.json")
    safety = load_json(SAFETY / "report.json")
    splits = {
        record["scenario_id"]: record["split"]
        for record in load_jsonl(DATASET / "records.jsonl")
    }
    records = []
    for item in load_jsonl(SAFETY / "proposals.jsonl"):
        proposal = item["proposal"]
        evaluation = item["safety_evaluation"]
        records.append(
            {
                "record_id": proposal["record_id"],
                "scenario_id": proposal["scenario_id"],
                "split": splits[proposal["scenario_id"]],
                "fault_type": proposal["fault_type"],
                "action_kind": proposal["action"]["kind"],
                "decision": evaluation["decision"],
                "reasons": evaluation["reasons"],
                "model_confidence": proposal["model_confidence"],
                "ood_score": proposal["ood_score"],
                "human_approval_requested": item["human_approval_requested"],
                "execution_status": item["execution_status"],
                "live_sentinel_decision": item["live_sentinel_evaluation"]["decision"],
                "evidence_label": proposal["evidence_label"],
            }
        )
    records.sort(key=lambda record: (record["split"], record["scenario_id"]))
    return {
        "schema_version": 1,
        "api_version": "v1",
        "project": "SafeTwin-5G",
        "research_identity": "Trustworthy Autonomous Networks",
        "generated_from_completed_at": benchmark["completed_at"],
        "source_run_id": benchmark["run_id"],
        "evidence_label": benchmark["evidence_label"],
        "radio_evidence_label": benchmark["radio_evidence_label"],
        "overall_decision": benchmark["overall_decision"],
        "hypotheses": benchmark["hypotheses"],
        "diagnostic_gate": benchmark["diagnostic_gate"],
        "safety_lock": benchmark["safety_lock"],
        "proposal_audit": {
            "proposal_count": safety["proposal_count"],
            "abstain_count": safety["abstain_count"],
            "applied_action_count": safety["applied_action_count"],
            "live_sentinel_reject_count": safety["live_sentinel_reject_count"],
            "records": records,
        },
        "source_sha256": {
            "benchmark_manifest": sha256(BENCHMARK / "manifest.json"),
            "benchmark_report": sha256(BENCHMARK / "report.json"),
            "dataset_manifest": sha256(DATASET / "manifest.json"),
            "safety_manifest": sha256(SAFETY / "manifest.json"),
            "safety_proposals": sha256(SAFETY / "proposals.jsonl"),
        },
        "claim_boundary": benchmark["claim_boundary"],
    }


def serialize(snapshot: dict) -> str:
    return json.dumps(snapshot, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    content = serialize(build_snapshot())
    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != content:
            print(f"STALE: {OUTPUT}")
            return 1
        print(f"PASS: {OUTPUT}")
        return 0
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content, encoding="utf-8")
    print(OUTPUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
