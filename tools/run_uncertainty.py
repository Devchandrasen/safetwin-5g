"""Evaluate uncertainty and OOD behavior on the frozen v0 splits."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.baselines import load_records, select_ridge_alpha  # noqa: E402
from safetwin5g.uncertainty import (  # noqa: E402
    ConformalCalibration,
    RangeOODDetector,
    selective_assessment,
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
    model, _ = select_ridge_alpha(by_split["train"], by_split["calibration"])
    calibration = ConformalCalibration.fit(
        [model.predict(record) for record in by_split["calibration"]],
        [float(record["observed_benefit"]) for record in by_split["calibration"]],
        0.90,
    )
    detector = RangeOODDetector.fit(by_split["train"] + by_split["calibration"])
    assessments = []
    for split in ("test", "ood"):
        for record in by_split[split]:
            item = selective_assessment(
                model.predict(record), calibration, detector.evaluate(record)
            )
            item.update(
                {
                    "scenario_id": record["scenario_id"],
                    "fault_family": record["fault_family"],
                    "split": split,
                    "observed_benefit": record["observed_benefit"],
                    "evidence_label": record["evidence_label"],
                    "radio_evidence_label": record["radio_evidence_label"],
                }
            )
            assessments.append(item)
    split_summary = {
        split: {
            "n": sum(item["split"] == split for item in assessments),
            "ood_count": sum(
                item["split"] == split and item["is_ood"] for item in assessments
            ),
            "abstain_count": sum(
                item["split"] == split and item["decision"] == "abstain"
                for item in assessments
            ),
        }
        for split in ("test", "ood")
    }
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ-uncertainty-ood-v0")
    output = ROOT / "evidence" / "benchmarks" / run_id
    output.mkdir(parents=True, exist_ok=False)
    (output / "assessments.jsonl").write_text(
        "".join(
            json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n"
            for item in assessments
        ),
        encoding="utf-8",
    )
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": started.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "execution_passed": True,
        "calibration": calibration.to_dict(),
        "ood_detector": {
            "kind": "development severity-range detector",
            "severity_ranges": detector.severity_ranges,
            "fitted_scenario_ids": list(detector.fitted_scenario_ids),
            "probabilistic_calibration": "not claimed",
        },
        "split_summary": split_summary,
        "test_split_is_severity_shifted": split_summary["test"]["ood_count"]
        == split_summary["test"]["n"],
        "ood_split_is_distinguishable_from_test": False,
        "selective_policy": "abstain when interval is unbounded or severity is outside development range",
        "eligible_count": sum(
            item["decision"] == "eligible-for-safety-gate" for item in assessments
        ),
        "abstain_count": sum(item["decision"] == "abstain" for item in assessments),
        "promotion_decision": "blocked",
        "promotion_reasons": [
            "The nominal 90% conformal interval is unbounded at calibration n=3.",
            "Both test and designated OOD rows are outside the development severity range.",
            "The designated OOD split is not distinguishable from test by the current observed design variables.",
        ],
        "evidence_label": "sandbox-measured",
        "radio_evidence_label": "simulated",
        "dataset_manifest_sha256": sha256(dataset / "manifest.json"),
        "claim_boundary": (
            "Fail-closed uncertainty/OOD feasibility result; OOD score is a design-range "
            "indicator, not a calibrated probability."
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
