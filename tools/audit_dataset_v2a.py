"""Independently audit a frozen Phase 7 public dataset release."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.dataset_v1 import sha256  # noqa: E402
from safetwin5g.dataset_v2a import ACTION_IDS, DATASET_VERSION  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, required=True)
    args = parser.parse_args()
    release = args.release if args.release.is_absolute() else ROOT / args.release
    manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
    expected = manifest["captured_file_sha256"]
    actual = {
        path.name for path in release.iterdir() if path.is_file() and path.name != "manifest.json"
    }
    assert actual == set(expected)
    for name, digest in expected.items():
        assert sha256(release / name) == digest, name
    records = [
        json.loads(line)
        for line in (release / "records.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    report = json.loads((release / "data-quality.json").read_text(encoding="utf-8"))
    serialized = json.dumps(records, sort_keys=True)
    assert manifest["dataset_version"] == DATASET_VERSION
    assert manifest["record_count"] == len(records) == 675
    assert manifest["passed"] is True and manifest["frozen"] is True
    assert report["release_eligible"] is True and all(report["checks"].values())
    assert {record["action_id"] for record in records} == set(ACTION_IDS)
    assert "authorization_basis" not in serialized and "approved_by" not in serialized
    assert all(record["operator_validation"] is False for record in records)
    print("PASS: v2a release hashes, 675 records, quality gates, and public-safe fields verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
