"""Evaluate risk-coverage and harm endpoints without inventing denominators."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.baselines import load_records  # noqa: E402
from safetwin5g.selective import selective_endpoints  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def main() -> int:
    dataset = ROOT / "data" / "releases" / "safetwin5g-interventions-v0"
    uncertainty = (
        ROOT
        / "evidence"
        / "benchmarks"
        / "20260824T053654Z-uncertainty-ood-v0"
    )
    records = [
        record
        for record in load_records(dataset / "records.jsonl")
        if record["split"] in {"test", "ood"}
    ]
    assessments = load_jsonl(uncertainty / "assessments.jsonl")
    endpoints = selective_endpoints(records, assessments)
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ-selective-evaluation-v0")
    output = ROOT / "evidence" / "benchmarks" / run_id
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": started.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "execution_passed": True,
        "endpoints": endpoints,
        "hypothesis_status": {
            "H2": "not-supported",
            "reason": (
                "zero coverage and no observed harmful actions prevent testing whether "
                "abstention materially lowers harm"
            ),
        },
        "go_no_go": "no-go-for-model-promotion",
        "required_next_evidence": [
            "at least 19 independent calibration scenarios for finite 90% split conformal rank",
            "no-fault scenarios for false-remediation rate",
            "scenarios with observed harmful or ineffective actions",
            "continuous SLA windows for violation duration and sustained recovery",
            "an uncertainty score with non-degenerate ranking",
        ],
        "evidence_label": "sandbox-measured",
        "radio_evidence_label": "simulated",
        "dataset_manifest_sha256": sha256(dataset / "manifest.json"),
        "uncertainty_manifest_sha256": sha256(uncertainty / "manifest.json"),
        "claim_boundary": (
            "Endpoint availability audit on six held-out sandbox scenarios; undefined "
            "metrics remain null and no harm-reduction claim is made."
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
