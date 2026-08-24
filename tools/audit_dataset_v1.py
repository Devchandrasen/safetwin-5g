"""Audit the frozen SafeTwin-5G intervention dataset v1."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
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
        str(item.relative_to(root)).replace("\\", "/")
        for item in root.rglob("*")
        if item.is_file() and item.name != "manifest.json"
    }
    assert actual == set(expected), f"manifest coverage mismatch: {root}"
    for relative, expected_hash in expected.items():
        assert sha256(root / relative) == expected_hash, f"hash mismatch: {relative}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", type=Path, required=True)
    args = parser.parse_args()
    release = args.release if args.release.is_absolute() else ROOT / args.release
    manifest = load_json(release / "manifest.json")
    verify_manifest(release / "manifest.json")
    source = ROOT / manifest["source_bundle"]
    verify_manifest(source / "manifest.json")
    assert sha256(source / "manifest.json") == manifest["source_manifest_sha256"]
    assert manifest["frozen"] is True
    assert manifest["passed"] is True
    assert manifest["record_count"] == 132
    assert manifest["evidence_label"] == "sandbox-measured"
    assert manifest["radio_evidence_label"] == "simulated"
    assert manifest["hardware_evidence_label"] is None
    assert manifest["operator_validation"] is False

    records = [
        json.loads(line)
        for line in (release / "records.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(records) == 132
    assert len({record["unit_id"] for record in records}) == 132
    assert Counter(record["split"] for record in records) == {
        "train": 42,
        "calibration": 21,
        "test": 21,
        "ood": 48,
    }
    assert Counter(record["action_arm"] for record in records) == {
        "effective": 44,
        "no_action": 44,
        "negative_control": 44,
    }
    blocks = defaultdict(list)
    for record in records:
        blocks[record["assignment_block_id"]].append(record)
        assert set(record["windows"]) == {
            "baseline",
            "fault",
            "post_action",
            "recovery",
        }
        assert all(len(window["samples"]) == 3 for window in record["windows"].values())
        assert record["evidence_label"] == "sandbox-measured"
        assert record["radio_evidence_label"] == "simulated"
        assert record["hardware_evidence_label"] is None
        assert record["operator_validation"] is False
        if record["action_applied"]:
            assert record["safety_evaluation"]["decision"] == "require-human-approval"
        else:
            assert record["safety_evaluation"]["decision"] == "observe-only"
    assert len(blocks) == 44
    assert all(
        len(block) == 3
        and {record["action_arm"] for record in block}
        == {"effective", "no_action", "negative_control"}
        for block in blocks.values()
    )

    report = load_json(release / "data-quality.json")
    assert report["passed"] is True
    assert all(report["checks"].values())
    assert report["telemetry_sample_count"] == 1584
    assert report["metric_cells"] == 19008
    assert report["missing_metric_cells"] == 764
    assert report["harmful_action_count"] == 31
    assert report["false_remediation_count"] == 8
    assert report["mttr_status_counts"] == {"not-triggered": 42, "observed": 90}
    print(
        "PASS: frozen v1 manifest/source hashes, 132 units, 44 complete action "
        "blocks, 1,584 samples, approvals, endpoints, and claim boundaries verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
