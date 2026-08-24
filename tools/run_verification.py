"""Run a verification command and preserve its output and source hashes."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--source", action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("a command is required after --")
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ") + f"-{args.name}"
    output_dir = ROOT / "evidence" / "verification" / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    (output_dir / "output.txt").write_text(result.stdout, encoding="utf-8")
    source_hashes = {
        relative: sha256(ROOT / relative)
        for relative in args.source
        if (ROOT / relative).is_file()
    }
    (output_dir / "source-sha256.json").write_text(
        json.dumps(source_hashes, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    command_record = {
        "started_at": started.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "argv": command,
        "returncode": result.returncode,
    }
    (output_dir / "command.json").write_text(
        json.dumps(command_record, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    captured = {
        path.name: sha256(path)
        for path in sorted(output_dir.iterdir())
        if path.is_file() and path.name != "manifest.json"
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_id,
                "artifact_type": "software-verification",
                "evidence_label": "fixture",
                "passed": result.returncode == 0,
                "captured_file_sha256": captured,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(output_dir)
    sys.stdout.buffer.write(result.stdout.encode("utf-8", errors="replace"))
    sys.stdout.buffer.flush()
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
