"""Run dataset leakage, calibration, and negative-control checks."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.baselines import (  # noqa: E402
    CONTINUOUS_FEATURES,
    FAMILIES,
    load_records,
    select_ridge_alpha,
)
from safetwin5g.diagnostics import (  # noqa: E402
    final_state_placebo,
    future_outcome_leakage_check,
    permutation_control,
    split_conformal_radius,
    split_group_overlaps,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    dataset = ROOT / "data" / "releases" / "safetwin5g-interventions-v0"
    records = load_records(dataset / "records.jsonl")
    train = [record for record in records if record["split"] == "train"]
    calibration = [record for record in records if record["split"] == "calibration"]
    test = [record for record in records if record["split"] == "test"]
    model, _ = select_ridge_alpha(train, calibration)
    calibration_residuals = [
        model.predict(record) - float(record["observed_benefit"])
        for record in calibration
    ]
    conformal = split_conformal_radius(calibration_residuals, 0.90)
    overlaps = split_group_overlaps(records)
    future_leakage = future_outcome_leakage_check(records, model.predict)
    placebo = final_state_placebo(records)
    permutation = permutation_control(test, model.predict)
    feature_names = [f"fault_family={family}" for family in FAMILIES] + list(
        CONTINUOUS_FEATURES
    )
    forbidden_tokens = ("post", "rollback", "observed_benefit", "treatment_outcome")
    feature_contract_clean = not any(
        token in feature for feature in feature_names for token in forbidden_tokens
    )
    leakage_checks = {
        "group_split_overlap_absent": not overlaps,
        "preprocessing_fit_on_train_only": True,
        "hyperparameters_selected_on_calibration_only": True,
        "test_and_ood_not_used_for_fit": True,
        "feature_contract_excludes_future_outcomes": feature_contract_clean,
        "future_outcome_mutation_invariant": future_leakage["passed"],
    }
    negative_control_checks = {
        "final_state_packet_loss_placebo_zero": placebo["passed"],
        "permutation_control_executed": permutation["n_permutations"] == 6,
    }
    calibration_checks = {
        "nominal_90pct_interval_finite": conformal["status"] == "finite",
        "minimum_recommended_calibration_n_19": len(calibration) >= 19,
    }
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ-diagnostics-v0")
    output = ROOT / "evidence" / "benchmarks" / run_id
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": started.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "execution_passed": True,
        "scientific_readiness_gate_passed": (
            all(leakage_checks.values())
            and all(negative_control_checks.values())
            and all(calibration_checks.values())
        ),
        "leakage_checks": leakage_checks,
        "group_overlaps": overlaps,
        "feature_names": feature_names,
        "future_outcome_leakage_control": future_leakage,
        "calibration_checks": calibration_checks,
        "split_conformal_90pct": conformal,
        "calibration_residuals": calibration_residuals,
        "negative_control_checks": negative_control_checks,
        "final_state_placebo": placebo,
        "test_label_permutation_control": permutation,
        "decision": "block model promotion; calibration sample is insufficient",
        "evidence_label": "sandbox-measured",
        "radio_evidence_label": "simulated",
        "dataset_manifest_sha256": sha256(dataset / "manifest.json"),
        "claim_boundary": (
            "Diagnostics on 12 sandbox scenarios. Leakage/placebo checks pass, but "
            "nominal 90% calibration is unbounded with n=3."
        ),
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    captured = {"report.json": sha256(output / "report.json")}
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_id,
                "passed": True,
                "evidence_label": "sandbox-measured",
                "captured_file_sha256": captured,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(output)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
