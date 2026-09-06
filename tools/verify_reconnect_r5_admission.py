"""Retain source snapshots, real-file fixtures and logs; no network/native gate."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sandbox.reconnect_r5_admission import NEW_SOURCES, LOCK, dependency_hashes


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--full", action="store_true")
    args = p.parse_args()
    output = ROOT/"evidence/verification"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")+"-reconnect-r5-admission")
    output.mkdir(exist_ok=False)
    names = sorted(set(dependency_hashes(ROOT)) | set(NEW_SOURCES) | ({LOCK} if (ROOT/LOCK).exists() else set()))
    before = {n: sha((ROOT/n).read_bytes()) for n in names}
    with zipfile.ZipFile(output/"sources.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.writestr(name, (ROOT/name).read_bytes())
    save(output/"source-before.json", before)
    command = [sys.executable, "-m", "pytest", "-q", "tests" if args.full else "tests/test_reconnect_r5_admission.py",
               "--basetemp", str(output/"pytest-temp")]
    started = datetime.now(timezone.utc).isoformat()
    error, code = None, None
    with (output/"pytest.log").open("xb") as stream:
        try:
            code = subprocess.run(command, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, timeout=900,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode
        except subprocess.TimeoutExpired as exc:
            error = type(exc).__name__+": "+str(exc)
    unchanged = all(sha((ROOT/n).read_bytes()) == h for n, h in before.items())
    report = dict(started_at=started, completed_at=datetime.now(timezone.utc).isoformat(), command=command,
        exit_code=code, error=error, full_regression=args.full, source_unchanged=unchanged,
        verification_passed=code == 0 and unchanged, evidence_label="fixture", actual_network_commands_executed=0,
        actual_power_requests_executed=0, native_clock_recaptures=0, native_execution_enabled=False,
        network_execution_authorized=False, network_fix_validated=False, TNSM_ready=False,
        source_sha256=before)
    # Keep all generated test artifacts locally. Publish the new admission
    # cases losslessly; unchanged large old-protocol cases remain local only.
    members = [f for f in (output/"pytest-temp").rglob("*") if f.is_file() and not f.is_symlink()
               and "admission-fixture" in f.relative_to(output).parts]
    with zipfile.ZipFile(output/"admission-fixtures.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for f in members:
            archive.writestr(f.relative_to(output).as_posix(), f.read_bytes())
        for pattern in ("admission-report.json", "independent-report.json", "case.json"):
            for f in (output/"pytest-temp").rglob(pattern):
                archive.writestr(f.relative_to(output).as_posix(), f.read_bytes())
    with zipfile.ZipFile(output/"admission-fixtures.zip") as archive:
        report["fixture_archive_lossless"] = all(archive.read(n) == (output/n).read_bytes() for n in archive.namelist())
        report["fixture_archive_members"] = len(archive.namelist())
    report["verification_passed"] = report["verification_passed"] and report["fixture_archive_lossless"]
    save(output/"report.json", report)
    save(output/"manifest.json", {"sha256": {f.relative_to(output).as_posix(): sha(f.read_bytes())
         for f in sorted(output.rglob("*")) if f.is_file() and not f.is_symlink()}})
    print(output, flush=True)
    print((output/"pytest.log").read_text(errors="replace")[-14000:], flush=True)
    print(json.dumps({k: report[k] for k in ("verification_passed", "full_regression", "fixture_archive_lossless", "fixture_archive_members")}))
    return 0 if report["verification_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
