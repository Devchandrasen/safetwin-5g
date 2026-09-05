"""Retained software-only R5 clock-journal subgate, not a network runner gate."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SOURCES = ("sandbox/reconnect_r5_journal.py", "tools/audit_reconnect_r5_journal.py",
           "tests/test_reconnect_r5_journal.py", "tools/verify_reconnect_r5_journal.py", "docs/RECONNECT_R5_JOURNAL.md")
LOCK = "config/experiments/reconnect-r5-journal-lock.json"
DEPENDENCY = "config/experiments/reconnect-r5-clock-lock.json"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    with path.open("xb") as handle:
        handle.write((json.dumps(value, indent=2, allow_nan=False) + "\n").encode())
        handle.flush()
        os.fsync(handle.fileno())


def verify_lock(committed=False):
    from tools.audit_reconnect_r5_clock import verify_lock as prior_lock
    prior_lock(committed=True)
    lock = json.loads((ROOT / LOCK).read_bytes())
    assert lock["lock_id"] == "safetwin5g-reconnect-r5-journal-v1" and lock["network_execution_authorized"] is False
    assert set(lock["source_sha256"]) == set(SOURCES)
    assert lock["immutable_clock_lock_sha256"] == sha((ROOT / DEPENDENCY).read_bytes())
    for name in SOURCES:
        assert sha((ROOT / name).read_bytes()) == lock["source_sha256"][name], name
    if committed:
        for name in (*SOURCES, LOCK):
            assert subprocess.check_output(["git", "show", "HEAD:" + name], cwd=ROOT, timeout=15) == (ROOT / name).read_bytes(), name
    return lock


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    from tests.test_reconnect_r5_journal import capture_case, CASES
    from tools.audit_reconnect_r5_journal import audit
    from tools.verify_reconnect_r5_clock import environment
    output = ROOT / "evidence/verification" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r5-journal")
    output.mkdir(exist_ok=False)
    source_names = [n for n in (*SOURCES, LOCK) if (ROOT / n).exists()]
    source_hashes = {n: sha((ROOT / n).read_bytes()) for n in source_names}
    # Every gate attempt keeps the exact sources, including failed development.
    with zipfile.ZipFile(output / "sources.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in source_names:
            archive.writestr(name, (ROOT / name).read_bytes())
    checks, cases = {}, {}
    def check(name, fn):
        try:
            value = fn()
            checks[name] = dict(passed=True, result=value)
        except (AssertionError, ValueError, KeyError, TypeError, OSError) as exc:
            checks[name] = dict(passed=False, error=type(exc).__name__ + ": " + str(exc))
        print(json.dumps(dict(check=name, passed=checks[name]["passed"])), flush=True)
    if not args.development:
        check("committed-clock-and-journal-lock", lambda: verify_lock())
        checks["environment-before"] = environment(output, "before")
    definitions = {
        "tests": ([sys.executable, "-m", "pytest", "-q", *(["tests/test_reconnect_r5_journal.py"] if args.development else [])], 180),
    }
    if not args.development:
        definitions.update({
            "r4-committed-execution-lock": ([sys.executable, "-c", "from sandbox.run_reconnect_r4 import verify_lock; print(len(verify_lock(committed=True)[0]['source_sha256']))"], 35),
            "r4-negative-observation": ([sys.executable, "-m", "tools.audit_reconnect_r4_observation"], 35),
            "r3-build-audit": ([sys.executable, "tools/audit_reconnect_r3_build_v2.py", "--run", "evidence/engineering/20260905T111542Z-reconnect-r3-build-release"], 35),
            "statistical-lock": ([sys.executable, "-c", "from tools.run_phase7_analysis import verify_analysis_lock; print(verify_analysis_lock()['lock_id'])"], 35),
        })
    for name, (argv, timeout) in definitions.items():
        start = datetime.now(timezone.utc).isoformat()
        try:
            result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=timeout,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                    env=dict(os.environ, PYTHONPATH=str(ROOT / "src") + os.pathsep + str(ROOT)))
            code, stdout, stderr = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired as exc:
            code, stdout, stderr = None, exc.stdout or b"", (exc.stderr or b"") + b"\nverification timeout\n"
        (output / (name + ".stdout.log")).write_bytes(stdout)
        (output / (name + ".stderr.log")).write_bytes(stderr)
        checks[name] = dict(passed=code == 0, exit_code=code, argv=argv, started_at=start,
                            completed_at=datetime.now(timezone.utc).isoformat())
        if name == "r4-negative-observation" and code == 0:
            replayed = json.loads(stdout)
            checks[name]["passed"] = replayed["observation_audit_passed"] is True and replayed["protocol_execution_valid"] is False
        print(json.dumps(dict(check=name, passed=checks[name]["passed"])), flush=True)
    with patch("subprocess.Popen", side_effect=AssertionError("fixture process forbidden")), \
         patch("socket.socket", side_effect=AssertionError("fixture socket forbidden")), \
         patch("ctypes.WinDLL", side_effect=AssertionError("fixture native/power API forbidden")):
        for name in CASES:
            def run_case(name=name):
                directory = output / name
                directory.mkdir(exist_ok=False)
                result = capture_case(directory / "journal.jsonl", name)
                save(directory / "capture.json", result)
                # Replay bytes freshly copied out of a lossless archive.
                with zipfile.ZipFile(directory / "capture.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
                    for entry in ("journal.jsonl", "capture.json"):
                        archive.writestr(entry, (directory / entry).read_bytes())
                with tempfile.TemporaryDirectory(prefix="safetwin-r5-journal-") as temporary:
                    with zipfile.ZipFile(directory / "capture.zip") as archive:
                        assert archive.namelist() == ["journal.jsonl", "capture.json"]
                        archive.extractall(temporary)
                    fresh = Path(temporary)
                    assert all((fresh / e).read_bytes() == (directory / e).read_bytes() for e in ("journal.jsonl", "capture.json"))
                    replayed = audit(json.loads((fresh / "capture.json").read_bytes())["snapshot"], (fresh / "journal.jsonl").read_bytes())
                    assert replayed == result["independent"]
                cases[name] = dict(points=replayed["points_replayed"], admission_open=replayed["admission_open"],
                                   all_cleanup_callbacks_attempted=result["cleanup"]["all_callbacks_attempted"],
                                   clock_capture_valid=replayed["clock"]["clock_capture_valid"])
                return cases[name]
            check("fixture-" + name, run_case)
    if not args.development:
        checks["environment-after"] = environment(output, "after")
        checks["unchanged-official-identities"] = dict(passed=checks["environment-before"].get("states") is not None
                    and checks["environment-before"].get("states") == checks["environment-after"].get("states"))
        check("source-lock-after", lambda: verify_lock())
    check("captured-source-equality", lambda: all(sha((ROOT / n).read_bytes()) == h for n, h in source_hashes.items()) or (_ for _ in ()).throw(ValueError("sources changed during gate")))
    report = dict(verification_passed=all(c["passed"] for c in checks.values()), development_only=args.development,
                  checks=checks, cases=cases, source_sha256=source_hashes, evidence_label="fixture",
                  measurement_scope="clock-journal-component-only", network_trials_executed=0,
                  actual_sleep_inhibition_requested=False, native_clock_probe_repeated=False,
                  network_execution_authorized=False, command_containment_verified=False,
                  whole_protocol_verified=False, service_restored=False, network_fix_validated=False, TNSM_ready=False)
    save(output / "verification.json", report)
    save(output / "manifest.json", {"captured_file_sha256": {p.relative_to(output).as_posix(): sha(p.read_bytes()) for p in output.rglob("*") if p.is_file()}})
    print(json.dumps(dict(output=str(output), verification_passed=report["verification_passed"], cases=len(cases))))
    return 0 if report["verification_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
