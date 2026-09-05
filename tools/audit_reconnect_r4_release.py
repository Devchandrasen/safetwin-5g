"""Read-only independent release/inventory replay; does not execute any network command."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_reconnect_r4_execution import audit

CURRENT = "evidence/engineering/20260905T164133Z-reconnect-r4-execution-fixtures"
OLD = "evidence/engineering/20260905T163558Z-reconnect-r4-execution-fixtures"
VERIFIED = "evidence/verification/20260905T164055Z-reconnect-r4-execution"
FAILED = "evidence/verification/20260905T163556Z-reconnect-r4-execution"
SNAPSHOT = "evidence/engineering/20260905T163900Z-reconnect-r4-gate-failure"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def manifest(directory):
    expected = json.loads((directory / "manifest.json").read_bytes())["captured_file_sha256"]
    require(set(expected) == {p.name for p in directory.iterdir() if p.is_file() and p.name != "manifest.json"}, "release file inventory")
    for name, digest in expected.items():
        require(Path(name).name == name and sha((directory / name).read_bytes()) == digest, "release file bytes")
    return expected


def unpack(path, expected, target):
    with zipfile.ZipFile(path) as handle:
        require(len(handle.namelist()) == len(expected) and set(handle.namelist()) == set(expected), "zip member inventory")
        for name, digest in expected.items():
            require((target / name).resolve().is_relative_to(target.resolve()) and sha(handle.read(name)) == digest, "zip member bytes/path")
        handle.extractall(target)


def main():
    inventories = {name: manifest(ROOT / name) for name in (CURRENT, OLD, VERIFIED, FAILED, SNAPSHOT)}
    read = lambda path: json.loads((ROOT / path).read_bytes())
    require(read(VERIFIED + "/verification.json")["verification_passed"] is True, "current software gate")
    require(read(FAILED + "/verification.json")["verification_passed"] is False, "original gate rejection changed")
    require(read(OLD + "/summary.json")["fixture_gate_passed"] is False, "original fixture rejection changed")
    report = read(CURRENT + "/summary.json")
    require(report["fixture_gate_passed"] is True and report["actual_docker_commands_executed"] == 0
            and report["actual_sleep_inhibition_requested"] is False, "fixture tier")
    replays = {}
    for name, entry in report["cases"].items():
        with tempfile.TemporaryDirectory(prefix="safetwin-r4-independent-release-") as temporary:
            target = Path(temporary) / "extracted"
            unpack(ROOT / CURRENT / (name + ".zip"), entry["archive_member_sha256"], target)
            replays[name] = audit(target, allow_fixture=True)
            require(replays[name] == entry["independent"], "released audit verdict drift")
    for release in (CURRENT, OLD):
        for name, entry in read(release + "/summary.json")["development_failures"].items():
            with tempfile.TemporaryDirectory(prefix="safetwin-r4-historical-release-") as temporary:
                unpack(ROOT / release / (name + ".zip"), entry["archive_member_sha256"], Path(temporary) / "extracted")
    snapshot = read(SNAPSHOT + "/failure.json")
    with tempfile.TemporaryDirectory(prefix="safetwin-r4-old-lock-") as temporary:
        target = Path(temporary) / "extracted"
        unpack(ROOT / SNAPSHOT / "sources.zip", snapshot["source_archive_member_sha256"], target)
        old_lock = json.loads((target / "config/experiments/reconnect-r4-execution-lock.json").read_bytes())
        for name, digest in old_lock["source_sha256"].items():
            require(sha((target / name).read_bytes()) == digest, "historical lock source bytes")
    staged = subprocess.check_output(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"], cwd=ROOT).decode().split("\0")
    staged = [n for n in staged if n]
    require(staged, "no staged release")
    for name in staged:
        require(not name.startswith(("evidence/private/", "evidence/engineering/20260905T111542Z-reconnect-r3-build/", "evidence/verification/20260825T081310Z-phase7-analysis-freeze/")), "protected/private path staged")
        require(subprocess.check_output(["git", "show", ":" + name], cwd=ROOT) == (ROOT / name).read_bytes(), "staged bytes differ: " + name)
    result = {"release_audit_passed": True, "protocol_cases_replayed": len(replays), "replays": replays,
              "manifest_files_verified": sum(len(v) for v in inventories.values()), "staged_files_verified": len(staged),
              "staged_file_sha256": {n: sha((ROOT / n).read_bytes()) for n in staged},
              "negative_gates_preserved": True, "historical_source_lock_verified": True,
              "network_trials_executed": 0, "network_fix_validated": False, "evidence_label": "fixture",
              "auditor_sha256": sha(Path(__file__).read_bytes())}
    output = ROOT / "evidence/engineering" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r4-release-audit")
    output.mkdir(exist_ok=False)
    with (output / "release.json").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(result, indent=2) + "\n")
    with (output / "manifest.json").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps({"captured_file_sha256": {"release.json": sha((output / "release.json").read_bytes())}}, indent=2) + "\n")
    print(json.dumps({"output": str(output), "release_audit_passed": True, "staged_files": len(staged), "replayed_cases": len(replays)}))


if __name__ == "__main__":
    main()
