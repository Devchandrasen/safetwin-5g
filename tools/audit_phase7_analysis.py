"""Audit the frozen Phase 7 statistical output without trusting its summary."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.dataset_v1 import sha256  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", type=Path, required=True)
    args = parser.parse_args()
    output = args.analysis if args.analysis.is_absolute() else ROOT / args.analysis
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    expected = manifest["captured_file_sha256"]
    actual = {
        path.name for path in output.iterdir() if path.is_file() and path.name != "manifest.json"
    }
    assert actual == set(expected)
    for name, digest in expected.items():
        assert sha256(output / name) == digest, name

    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    sources = json.loads((output / "source-evidence.json").read_text(encoding="utf-8"))
    rows = [
        json.loads(line)
        for line in (output / "policy-decisions.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert report["split_block_counts"] == {"train": 28, "calibration": 21, "test": 70, "ood": 16}
    assert report["gates"]["G1"]["block_n"] == 70
    assert report["gates"]["G2"]["faulty_test_block_n"] == 60
    assert report["gates"]["G3"]["matched_faulty_block_n"] == 60
    assert report["model"]["calibration_used_for_model_selection"] is False
    assert report["model"]["test_or_ood_used_for_fit_or_selection"] is False
    assert set(report["model"]["fitted_block_ids"]) and len(report["model"]["fitted_block_ids"]) == 28
    assert sources["test_labels_opened_after_lock_verification"] is True
    assert report["decision"]["live_actuation"] == "no-go"
    assert report["decision"]["submission_authorized"] is False
    assert report["claim_boundaries"] == {
        "evidence_label": "sandbox-measured",
        "radio_evidence_label": "simulated",
        "hardware_evidence_label": None,
        "operator_validation": False,
        "conditional_coverage_claimed": False,
        "live_network_claimed": False,
    }
    assert len(rows) == 586
    assert all(row["split"] in {"test", "ood"} for row in rows)
    all_gates = all(report["gates"][key]["passed"] for key in ("G1", "G2", "G3", "G4"))
    assert (report["decision"]["TNSM_claim_gate"] == "go") == all_gates
    assert manifest["TNSM_claim_gate"] == report["decision"]["TNSM_claim_gate"]
    print("PASS: Phase 7 hashes, sealed split boundaries, exact denominators, gates, and claims verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
