"""Run the frozen rule, ridge-tabular, and temporal-persistence baselines."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.baselines import (  # noqa: E402
    load_records,
    metrics,
    prediction_rows,
    rule_prediction,
    select_ridge_alpha,
    temporal_persistence_prediction,
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
    by_split = {
        split: [record for record in records if record["split"] == split]
        for split in ("train", "calibration", "test", "ood")
    }
    if any(len(rows) != 3 for rows in by_split.values()):
        raise RuntimeError("frozen v0 split sizes changed")
    ridge, alpha_trials = select_ridge_alpha(
        by_split["train"], by_split["calibration"]
    )
    predictors = {
        "deterministic_rule": rule_prediction,
        "tabular_ridge": ridge.predict,
        "temporal_persistence": temporal_persistence_prediction,
    }
    evaluation = {
        split: {name: metrics(rows, predictor) for name, predictor in predictors.items()}
        for split, rows in by_split.items()
    }
    ranking = sorted(
        predictors,
        key=lambda name: (evaluation["test"][name]["mae"], name),
    )
    winner = ranking[0]
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ-baselines-v0")
    output = ROOT / "evidence" / "benchmarks" / run_id
    output.mkdir(parents=True, exist_ok=False)
    predictions = prediction_rows(records, predictors)
    (output / "predictions.jsonl").write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in predictions
        ),
        encoding="utf-8",
    )
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": started.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "passed": True,
        "dataset_version": "safetwin5g-interventions-v0",
        "dataset_manifest_sha256": sha256(dataset / "manifest.json"),
        "split_sizes": {split: len(rows) for split, rows in by_split.items()},
        "preprocessing_fit_split": "train",
        "hyperparameter_selection_split": "calibration",
        "ridge_alpha": ridge.alpha,
        "ridge_alpha_trials": alpha_trials,
        "evaluation": evaluation,
        "test_ranking_by_mae": ranking,
        "test_winner": winner,
        "promotion_decision": "do-not-promote",
        "promotion_reasons": [
            "Only three rows are available in each split.",
            "The deterministic rule is the test-MAE winner." if winner == "deterministic_rule" else "No robust superiority test is possible.",
            "Alternative-action positivity is absent.",
            "The rollback proxy is action-first and may contain order effects.",
        ],
        "evidence_label": "sandbox-measured",
        "radio_evidence_label": "simulated",
        "claim_boundary": (
            "Derived feasibility benchmark on 12 software-sandbox scenarios; no "
            "hardware, operator, or general causal superiority claim."
        ),
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    captured = {
        path.name: sha256(path)
        for path in sorted(output.iterdir())
        if path.is_file() and path.name != "manifest.json"
    }
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
