"""Verify the captured-file hashes in a SafeTwin-5G evidence manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_bundle(bundle: Path) -> list[str]:
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    errors: list[str] = []
    for relative, expected in manifest["captured_file_sha256"].items():
        path = bundle / relative
        if not path.is_file():
            errors.append(f"missing: {relative}")
        elif file_sha256(path) != expected:
            errors.append(f"hash mismatch: {relative}")
    expected_files = set(manifest["captured_file_sha256"])
    actual_files = {
        str(path.relative_to(bundle)).replace("\\", "/")
        for path in bundle.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    for relative in sorted(actual_files - expected_files):
        errors.append(f"unmanifested: {relative}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    errors = verify_bundle(args.bundle.resolve())
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"PASS: {args.bundle}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
