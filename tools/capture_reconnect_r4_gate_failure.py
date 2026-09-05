"""Preserve exact pre-correction R4 software-gate sources, no network calls."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.verify_reconnect_r4_execution import SOURCES
from tools.fixture_reconnect_r4_execution import archive, extract_verified
from sandbox.run_reconnect_r4 import save, sha


def main():
    expected = json.loads((ROOT / "evidence/verification/20260905T163556Z-reconnect-r4-execution/verification.json").read_bytes())["source_sha256"]
    if any(sha((ROOT / name).read_bytes()) != digest for name, digest in expected.items()):
        raise ValueError("historical source bytes are no longer current; use the preserved archive, never recapture under its old description")
    output = ROOT / "evidence/engineering" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r4-gate-failure")
    output.mkdir(exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="safetwin-r4-source-preserve-") as temporary:
        root = Path(temporary)
        source = root / "sources"
        for name in SOURCES + ["config/experiments/reconnect-r4-execution-lock.json"]:
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT / name).read_bytes())
        inventory = archive(source, output / "sources.zip")
        extract_verified(output / "sources.zip", root / "replay", inventory)
    save(output / "failure.json", {"verification": "evidence/verification/20260905T163556Z-reconnect-r4-execution",
                                  "fixture_release": "evidence/engineering/20260905T163558Z-reconnect-r4-execution-fixtures",
                                  "source_archive_member_sha256": inventory, "evidence_label": "fixture",
                                  "verification_passed": False, "network_trials_executed": 0,
                                  "findings": ["system Python lacks src package on import path", "wrong Compose project filter",
                                               "JSON object ordering compared textually", "hidden descendant did not inherit intended test pipes",
                                               "Python 3.12 Windows GetTickCount64 resolution 0.015625 exceeds 1ms audit tolerance; use monotonic QPC without relaxing tolerance"]})
    save(output / "manifest.json", {"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}})
    print(output)


if __name__ == "__main__":
    main()
