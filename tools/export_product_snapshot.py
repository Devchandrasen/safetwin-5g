"""Export a deterministic, read-only product snapshot from verified evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.reporting import load_json, sha256, verify_manifest  # noqa: E402


BENCHMARK = ROOT / "evidence" / "benchmarks" / "20260825T030431Z-phase6-analysis-v1"
DATASET = ROOT / "data" / "releases" / "safetwin5g-interventions-v1"
POLICY = ROOT / "config" / "actions.json"
OUTPUT = ROOT / "dashboard" / "app" / "data" / "status.json"


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def build_snapshot() -> dict:
    for bundle in (BENCHMARK, DATASET):
        verify_manifest(bundle / "manifest.json")

    benchmark = load_json(BENCHMARK / "report.json")
    quality = load_json(DATASET / "data-quality.json")
    policy = load_json(POLICY)
    dataset_records = {
        record["unit_id"]: record for record in load_jsonl(DATASET / "records.jsonl")
    }

    proposal_records = []
    for prediction in load_jsonl(BENCHMARK / "predictions.jsonl"):
        if prediction["split"] != "test" or prediction["action_arm"] == "no_action":
            continue
        assessment = prediction["assessment"]
        observed = dataset_records[prediction["unit_id"]]
        decision = assessment["decision"]
        proposal_records.append(
            {
                "record_id": f"phase6-{prediction['unit_id']}",
                "unit_id": prediction["unit_id"],
                "split": prediction["split"],
                "fault_type": prediction["fault_family"],
                "action_arm": prediction["action_arm"],
                "action_kind": observed["action_kind"],
                "decision": decision,
                "reasons": assessment["reasons"]
                or ["passed the offline selective gate; no model action was executed"],
                "predicted_benefit": assessment["predicted_benefit"],
                "contrast_margin": assessment["contrast_margin"],
                "ood_score": 1.0 if assessment["is_ood"] else 0.0,
                "observed_harmful_action": assessment["observed_harmful_action"],
                "human_approval_required_if_applied": policy["require_human_approval"],
                "human_approval_requested_by_model": False,
                "model_execution_status": "not-applied-offline-evaluation",
                "experimental_execution_status": (
                    "applied-approved-and-rolled-back"
                    if observed["action_applied"]
                    else "observe-only"
                ),
                "evidence_label": prediction["evidence_label"],
                "radio_evidence_label": prediction["radio_evidence_label"],
            }
        )

    proposal_records.sort(key=lambda record: record["unit_id"])
    eligible_count = sum(
        record["decision"].startswith("eligible") for record in proposal_records
    )
    abstain_count = sum(
        record["decision"] == "abstain" for record in proposal_records
    )
    experiment_action_count = sum(
        bool(record["action_applied"]) for record in dataset_records.values()
    )
    test_metrics = benchmark["baselines"]["evaluation"]["test"]
    uncertainty = benchmark["uncertainty"]
    hypotheses = benchmark["hypotheses"]

    return {
        "schema_version": 2,
        "api_version": "v2",
        "project": "SafeTwin-5G",
        "research_identity": "Trustworthy Autonomous Networks",
        "generated_from_completed_at": benchmark["completed_at"],
        "source_run_id": benchmark["run_id"],
        "evidence_label": benchmark["evidence_label"],
        "radio_evidence_label": benchmark["radio_evidence_label"],
        "hardware_evidence_label": benchmark["hardware_evidence_label"],
        "operator_validation": benchmark["operator_validation"],
        "overall_decision": {
            "model_promotion": benchmark["promotion"]["model_promotion"],
            "live_actuation": benchmark["promotion"]["live_actuation"],
            "positive_h1_h3_claims": "no-go",
            "local_phase6": "complete-negative-decision",
            "reasons": benchmark["promotion"]["reasons"],
        },
        "dataset": {
            "version": benchmark["dataset_version"],
            "record_count": quality["record_count"],
            "assignment_block_count": quality["assignment_block_count"],
            "telemetry_sample_count": quality["telemetry_sample_count"],
            "metric_cells": quality["metric_cells"],
            "missing_metric_cells": quality["missing_metric_cells"],
            "harmful_action_count": quality["harmful_action_count"],
            "false_remediation_count": quality["false_remediation_count"],
            "split_counts": quality["split_counts"],
            "quality_passed": quality["passed"],
        },
        "benchmark": {
            "test_winner": benchmark["baselines"]["test_winner"],
            "test_n": benchmark["split_sizes"]["test"],
            "test_mae": {
                name: metrics["mae"] for name, metrics in test_metrics.items()
            },
            "conformal": uncertainty["calibration"],
            "test_empirical_coverage": uncertainty["test_empirical_coverage"],
            "ood_empirical_coverage": uncertainty["ood_empirical_coverage"],
            "test_ood_count": benchmark["ood"]["test_ood_count"],
            "test_ood_n": benchmark["ood"]["test_n"],
            "designated_ood_count": benchmark["ood"]["ood_split_ood_count"],
            "designated_ood_n": benchmark["ood"]["ood_n"],
        },
        "hypotheses": hypotheses,
        "diagnostic_gate": {
            "finite_conformal_radius": uncertainty["calibration"]["status"] == "finite",
            "future_outcome_leakage_passed": benchmark["diagnostics"][
                "future_outcome_leakage"
            ]["passed"],
            "calibration_minimum_met": benchmark["diagnostics"][
                "calibration_minimum_met"
            ],
            "scientific_promotion_ready": False,
        },
        "safety_lock": {
            "allow_live_actuation": policy["allow_live_actuation"],
            "require_human_approval": policy["require_human_approval"],
            "model_actions_applied": 0,
            "experiment_actions_applied": experiment_action_count,
            "experiment_rollbacks_verified": experiment_action_count,
        },
        "proposal_audit": {
            "evaluation_mode": "offline-locked-test",
            "proposal_count": len(proposal_records),
            "eligible_count": eligible_count,
            "abstain_count": abstain_count,
            "applied_action_count": 0,
            "records": proposal_records,
        },
        "source_sha256": {
            "benchmark_manifest": sha256(BENCHMARK / "manifest.json"),
            "benchmark_report": sha256(BENCHMARK / "report.json"),
            "benchmark_predictions": sha256(BENCHMARK / "predictions.jsonl"),
            "dataset_manifest": sha256(DATASET / "manifest.json"),
            "dataset_records": sha256(DATASET / "records.jsonl"),
            "dataset_quality": sha256(DATASET / "data-quality.json"),
            "action_policy": sha256(POLICY),
        },
        "claim_boundary": (
            "The intervention outcomes are sandbox-measured and the radio is simulated. "
            "The dashboard is a read-only local view of locked offline analysis. It is not "
            "hardware-measured, operator-validated, or authorization for live actuation."
        ),
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
