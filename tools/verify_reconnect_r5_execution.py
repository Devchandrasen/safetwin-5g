"""Software-only full integration verification; preserve pre-test sources.

Never invokes a network, clock-native or power verifier. Generated failed
directories are immutable evidence, not retries under the same pathname.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SOURCES = ["sandbox/run_reconnect_r5.py", "sandbox/reconnect_r5_scope.py",
           "tools/reconnect_r5_global_budget_audit.py", "tools/reconnect_r5_global_collection_audit.py",
           "tools/reconnect_r5_global_host_audit.py", "tools/audit_reconnect_r5_execution.py",
           "tools/verify_reconnect_r5_execution.py", "tests/reconnect_r5_execution_fixture.py",
           "tests/test_reconnect_r5_execution.py", "docs/RECONNECT_R5_EXECUTION.md", "tools/package_reconnect_r5_execution.py", "pytest.ini"]
LOCK = "config/experiments/reconnect-r5-execution-lock.json"


def verify_lock(committed=False):
    from tools.verify_reconnect_r5_budget import verify_lock as prior
    prior(committed=True)
    lock = json.loads((ROOT/LOCK).read_bytes())
    assert set(lock) == {"lock_id", "source_sha256", "immutable_budget_lock_sha256", "network_execution_authorized", "native_execution_enabled", "evidence_label"}
    assert lock["lock_id"] == "safetwin5g-reconnect-r5-execution-v1" and lock["evidence_label"] == "fixture"
    assert lock["network_execution_authorized"] is False and lock["native_execution_enabled"] is False
    assert lock["immutable_budget_lock_sha256"] == hashlib.sha256((ROOT/"config/experiments/reconnect-r5-budget-lock.json").read_bytes()).hexdigest()
    assert set(lock["source_sha256"]) == set(SOURCES)
    for name in SOURCES:
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == lock["source_sha256"][name], name
    if committed:
        for name in [*SOURCES, LOCK]:
            assert subprocess.check_output(["git", "show", "HEAD:"+name], cwd=ROOT, timeout=15) == (ROOT/name).read_bytes(), name
    return lock


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+"\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--full", action="store_true")
    args = parser.parse_args()
    output = ROOT/"evidence/verification"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-reconnect-r5-execution")
    output.mkdir(exist_ok=False)
    hashes = {}
    for name in [*SOURCES, LOCK]:
        path = ROOT/name
        if path.is_file():
            raw = path.read_bytes()
            target = output/"sources"/name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
            hashes[name] = hashlib.sha256(raw).hexdigest()
    save(output/"source-before.json", hashes)
    checks = {}
    if args.full:
        try:
            verify_lock()
            checks["source-locks"] = dict(passed=True)
        except (AssertionError, ValueError, OSError) as exc:
            checks["source-locks"] = dict(passed=False, error=str(exc))
        from tools.verify_reconnect_r5_host import environment
        checks["metadata-before"] = environment(output, "before")
    argv = [sys.executable, "-m", "pytest", "-q", "tests" if args.full else "tests/test_reconnect_r5_execution.py",
            "--basetemp", str(output/"pytest-temp")]
    # File-backed output preserves failure/traceback without truncation.
    with (output/"pytest.txt").open("wb") as stream:
        completed = subprocess.run(argv, cwd=ROOT, stdout=stream, stderr=subprocess.STDOUT, check=False, timeout=600)
    if args.full:
        commands = {
            "default-test-discovery": [sys.executable, "-m", "pytest", "--collect-only", "-q"],
            "r4-negative-observation": [sys.executable, "-m", "tools.audit_reconnect_r4_observation"],
            "r3-redacted-build": [sys.executable, "tools/audit_reconnect_r3_build_v2.py", "--run", "evidence/engineering/20260905T111542Z-reconnect-r3-build-release"],
            "statistical-lock": [sys.executable, "-c", "from tools.run_phase7_analysis import verify_analysis_lock; print(verify_analysis_lock()['lock_id'])"],
        }
        for label, command in commands.items():
            started = datetime.now(timezone.utc).isoformat()
            check = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=60)
            (output/(label+".stdout.log")).write_bytes(check.stdout)
            (output/(label+".stderr.log")).write_bytes(check.stderr)
            passed = check.returncode == 0
            if label == "r4-negative-observation" and passed:
                value = json.loads(check.stdout)
                passed = value["observation_audit_passed"] is True and value["protocol_execution_valid"] is False
            if label == "default-test-discovery" and passed:
                passed = all(line.startswith(b"tests/") for line in check.stdout.splitlines() if b"::" in line)
            checks[label] = dict(passed=passed, argv=command, exit_code=check.returncode, started_at=started, completed_at=datetime.now(timezone.utc).isoformat())
        checks["metadata-after"] = environment(output, "after")
        checks["unchanged-official-identities"] = dict(passed=checks["metadata-before"].get("states") is not None and checks["metadata-before"].get("states") == checks["metadata-after"].get("states"))
    report = dict(evidence_label="fixture", command=argv, pytest_exit=completed.returncode, full_regression=args.full, checks=checks,
                  network_execution_authorized=False, network_fix_validated=False, TNSM_ready=False,
                  source_sha256=hashes, source_unchanged=all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() == h for n, h in hashes.items()))
    report["verification_passed"] = completed.returncode == 0 and report["source_unchanged"] and all(v["passed"] for v in checks.values())
    save(output/"report.json", report)
    save(output/"manifest.json", {"sha256": {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                          for p in sorted(output.rglob("*")) if p.is_file()}})
    print(str(output), flush=True)
    print((output/"pytest.txt").read_text(errors="replace")[-22000:], flush=True)
    print(json.dumps(dict(verification_passed=report["verification_passed"], checks={k: v["passed"] for k, v in checks.items()})))
    raise SystemExit(0 if report["verification_passed"] else 1)


if __name__ == "__main__":
    main()
