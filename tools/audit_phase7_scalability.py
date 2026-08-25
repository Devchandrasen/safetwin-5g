"""Audit BRACE scalability artifact hashes and bounded claims."""

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
    parser.add_argument("--benchmark", type=Path, required=True)
    args = parser.parse_args()
    output = args.benchmark if args.benchmark.is_absolute() else ROOT / args.benchmark
    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    expected = manifest["captured_file_sha256"]
    actual = {
        path.name for path in output.iterdir() if path.is_file() and path.name != "manifest.json"
    }
    assert actual == set(expected)
    for name, digest in expected.items():
        assert sha256(output / name) == digest, name
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert [row["block_n"] for row in report["calibration"]] == [21, 100, 500, 1000, 5000]
    assert all(row["status"] == "finite" for row in report["calibration"])
    assert report["decision_batch"]["decision"] == "require-human-approval"
    assert report["decision_batch"]["apply_allowed"] is False
    assert report["input_evidence_label"] == "fixture"
    assert report["network_performance_claim"] is False
    assert report["hardware_or_operator_claim"] is False
    print("PASS: scalability hashes, denominators, fail-closed decision, and fixture claims verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
