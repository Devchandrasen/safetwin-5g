"""Independently audit the locked Phase 6 statistical decision."""

from __future__ import annotations

from collections import defaultdict
from itertools import product
import argparse
import hashlib
import json
from math import ceil, sqrt
from pathlib import Path
import statistics


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify_manifest(path: Path) -> None:
    manifest = load_json(path)
    root = path.parent
    expected = manifest["captured_file_sha256"]
    actual = {
        item.name
        for item in root.iterdir()
        if item.is_file() and item.name != "manifest.json"
    }
    assert actual == set(expected), f"manifest coverage mismatch: {root}"
    for relative, expected_hash in expected.items():
        assert sha256(root / relative) == expected_hash, f"hash mismatch: {relative}"


def exact_less(block_values: dict[str, list[float]]) -> float:
    values = [statistics.fmean(block_values[key]) for key in sorted(block_values)]
    observed = statistics.fmean(values)
    null = [
        statistics.fmean([sign * value for sign, value in zip(signs, values)])
        for signs in product((-1.0, 1.0), repeat=len(values))
    ]
    return sum(value <= observed + 1e-12 for value in null) / len(null)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--benchmark", type=Path, required=True)
    args = parser.parse_args()
    benchmark = args.benchmark if args.benchmark.is_absolute() else ROOT / args.benchmark
    verify_manifest(benchmark / "manifest.json")
    report = load_json(benchmark / "report.json")
    source = load_json(benchmark / "source-evidence.json")
    for item in source["files"]:
        assert sha256(ROOT / item["path"]) == item["sha256"], item["path"]

    dataset = ROOT / "data" / "releases" / "safetwin5g-interventions-v1"
    assert sha256(dataset / "manifest.json") == report["dataset_manifest_sha256"]
    records = {
        record["unit_id"]: record
        for record in (
            json.loads(line)
            for line in (dataset / "records.jsonl").read_text(encoding="utf-8").splitlines()
        )
    }
    predictions = [
        json.loads(line)
        for line in (benchmark / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    contrasts = [
        json.loads(line)
        for line in (benchmark / "contrasts.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(predictions) == 132
    assert len(contrasts) == 88
    assert len({row["unit_id"] for row in predictions}) == 132

    test_rows = [row for row in predictions if row["split"] == "test"]
    assert len(test_rows) == 21
    recomputed = {}
    for predictor in (
        "action_conditional_ridge",
        "deterministic_rule",
        "temporal_persistence",
    ):
        errors = [
            row["predictions"][predictor]
            - row["observed_post_action_user_plane_burden"]
            for row in test_rows
        ]
        recomputed[predictor] = {
            "mae": statistics.fmean(abs(error) for error in errors),
            "rmse": sqrt(statistics.fmean(error * error for error in errors)),
            "median_absolute_error": statistics.median(abs(error) for error in errors),
        }
        reported = report["baselines"]["evaluation"]["test"][predictor]
        assert abs(recomputed[predictor]["mae"] - reported["mae"]) < 1e-12
        assert abs(recomputed[predictor]["rmse"] - reported["rmse"]) < 1e-12
        assert (
            abs(
                recomputed[predictor]["median_absolute_error"]
                - reported["absolute_error_distribution"]["median"]
            )
            < 1e-12
        )
    assert report["baselines"]["test_winner"] == "deterministic_rule"

    calibration_rows = [row for row in predictions if row["split"] == "calibration"]
    residuals = sorted(
        abs(
            row["predictions"]["action_conditional_ridge"]
            - row["observed_post_action_user_plane_burden"]
        )
        for row in calibration_rows
    )
    rank = ceil((len(residuals) + 1) * 0.90)
    radius = residuals[rank - 1]
    assert len(residuals) == 21
    assert rank == 20
    assert abs(radius - report["uncertainty"]["calibration"]["radius"]) < 1e-12
    for split in ("test", "ood"):
        rows = [row for row in predictions if row["split"] == split]
        covered = sum(
            abs(
                row["predictions"]["action_conditional_ridge"]
                - row["observed_post_action_user_plane_burden"]
            )
            <= radius
            for row in rows
        )
        reported = report["uncertainty"][f"{split}_empirical_coverage"]
        assert covered == reported["covered"]
        assert abs(covered / len(rows) - reported["coverage"]) < 1e-12

    h1_blocks = defaultdict(list)
    for row in test_rows:
        target = row["observed_post_action_user_plane_burden"]
        difference = abs(
            row["predictions"]["action_conditional_ridge"] - target
        ) - abs(row["predictions"]["temporal_persistence"] - target)
        h1_blocks[row["assignment_block_id"]].append(difference)
    assert len(h1_blocks) == 7
    h1_p = exact_less(h1_blocks)
    assert h1_p == 0.03125
    assert h1_p == report["hypotheses"]["H1"]["exact_test"]["exact_one_sided_pvalue"]

    h2_blocks = defaultdict(list)
    action_candidates = [
        row
        for row in test_rows
        if records[row["unit_id"]]["action_arm"] != "no_action"
    ]
    assert len(action_candidates) == 14
    eligible = 0
    always_harm = 0
    selective_harm = 0
    for row in action_candidates:
        assessment = row["assessment"]
        record = records[row["unit_id"]]
        eligible += assessment["decision"] != "abstain"
        always = int(record["harmful_action"])
        selective = int(assessment["harm_if_selective"])
        always_harm += always
        selective_harm += selective
        h2_blocks[row["assignment_block_id"]].append(selective - always)
    assert eligible == 3
    assert always_harm == 5
    assert selective_harm == 0
    assert eligible / len(action_candidates) == report["hypotheses"]["H2"]["coverage"]
    h2_p = exact_less(h2_blocks)
    assert h2_p == 0.03125
    assert h2_p == report["hypotheses"]["H2"]["exact_test"]["exact_one_sided_pvalue"]
    assert report["hypotheses"]["multiplicity"]["adjusted_pvalues"] == {
        "H1": 0.0625,
        "H2": 0.0625,
    }

    fitted = set(report["model"]["fitted_unit_ids"])
    assert fitted == {
        unit_id for unit_id, record in records.items() if record["split"] == "train"
    }
    assert not fitted.intersection(
        unit_id
        for unit_id, record in records.items()
        if record["split"] in {"test", "ood"}
    )
    assert report["diagnostics"]["future_outcome_leakage"]["passed"] is True
    assert report["ood"]["test_ood_count"] == 0
    assert report["ood"]["ood_split_ood_count"] == 48
    assert report["hypotheses"]["H1"]["status"] == "not-supported"
    assert report["hypotheses"]["H2"]["status"] == "not-supported"
    assert report["hypotheses"]["H3"]["status"] == "gated-not-run"
    assert report["promotion"]["model_promotion"] == "no-go"
    assert report["promotion"]["live_actuation"] == "no-go"
    assert report["evidence_label"] == "sandbox-measured"
    assert report["radio_evidence_label"] == "simulated"
    assert report["hardware_evidence_label"] is None
    assert report["operator_validation"] is False
    print(
        "PASS: hashes, split isolation, MAE/RMSE/median, conformal rank/radius/coverage, "
        "H1/H2 denominators and exact tests, Holm correction, OOD, and no-go decision verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
