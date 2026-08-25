"""Independent arithmetic and hash audit for the v1 BRACE feasibility result."""

from __future__ import annotations

import argparse
import hashlib
import json
from math import ceil
from pathlib import Path


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
        item.name for item in root.iterdir() if item.is_file() and item.name != "manifest.json"
    }
    assert actual == set(expected)
    for name, expected_hash in expected.items():
        assert sha256(root / name) == expected_hash, name


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

    records_path = ROOT / "data" / "releases" / "safetwin5g-interventions-v1" / "records.jsonl"
    records = [json.loads(line) for line in records_path.read_text(encoding="utf-8").splitlines()]
    block_counts = {
        split: len(
            {row["assignment_block_id"] for row in records if row["split"] == split}
        )
        for split in ("train", "calibration", "test", "ood")
    }
    assert block_counts == {"train": 14, "calibration": 7, "test": 7, "ood": 16}
    calibration_n = block_counts["calibration"]
    assert ceil((calibration_n + 1) * 0.90) == 8
    assert report["legacy_block_calibration"]["calibration_block_n"] == 7
    assert report["legacy_block_calibration"]["rank"] == 8
    assert report["legacy_block_calibration"]["status"] == "unbounded"
    assert report["legacy_block_calibration"]["radius"] is None
    assert report["legacy_test"]["certified_block_n"] == 0
    assert report["legacy_ood"]["certified_block_n"] == 0
    assert report["legacy_limitations"]["strict_phase7_named_action_complete_blocks"] == 0
    assert report["confirmatory_claim_allowed"] is False
    assert report["phase6_decision_changed"] is False
    assert report["decision"]["legacy_v1_BRACE_promotion"] == "no-go"
    assert report["decision"]["live_actuation"] == "no-go"
    print("PASS: hashes, split blocks, unbounded rank, zero certificates, and no-go verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
