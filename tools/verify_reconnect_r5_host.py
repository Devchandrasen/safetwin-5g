"""Retained fake-host software gate. No actual power/native-clock probe."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.verify_reconnect_r5_journal import save, sha

SOURCES = ("sandbox/reconnect_r5_host.py", "tools/audit_reconnect_r5_host.py", "tests/test_reconnect_r5_host.py",
           "tools/verify_reconnect_r5_host.py", "docs/RECONNECT_R5_HOST.md")
LOCK = "config/experiments/reconnect-r5-host-lock.json"
PRIOR = "config/experiments/reconnect-r5-process-lock.json"


def verify_lock(committed=False):
    from tools.verify_reconnect_r5_process import verify_lock as process_lock
    process_lock(committed=True)
    lock = json.loads((ROOT / LOCK).read_bytes())
    assert set(lock) == {"lock_id", "source_sha256", "immutable_process_lock_sha256", "network_execution_authorized", "whole_protocol_verified"}
    assert lock["lock_id"] == "safetwin5g-reconnect-r5-host-v1"
    assert lock["network_execution_authorized"] is False and lock["whole_protocol_verified"] is False
    assert set(lock["source_sha256"]) == set(SOURCES) and lock["immutable_process_lock_sha256"] == sha((ROOT / PRIOR).read_bytes())
    for name in SOURCES:
        assert sha((ROOT / name).read_bytes()) == lock["source_sha256"][name], name
    if committed:
        for name in (*SOURCES, LOCK):
            assert subprocess.check_output(["git", "show", "HEAD:" + name], cwd=ROOT, timeout=15) == (ROOT / name).read_bytes(), name
    return lock


def environment(output, prefix):
    from tools.verify_reconnect_r5_clock import environment as old_scope
    from sandbox.reconnect_r4_process import BoundedProcess, complete
    from sandbox.reconnect_r5_host import idle_query
    state = old_scope(output, prefix)
    command = idle_query(os.getpid())
    # Metadata-only use of the old bounded client, not R5 timing acceptance.
    row = BoundedProcess([command]).run(command, sequence=1)
    save(output / (prefix + "-r5-idle.json"), row)
    state["r5_idle_passed"] = bool(complete(row) and row["returncode"] == 0 and not row["stderr"]
                                 and row["stdout"] in ("SAFETWIN_R5_IDLE_V1\n", "SAFETWIN_R5_IDLE_V1\r\n"))
    state["no_r5_receipt"] = not (ROOT / "evidence/private/reconnect-r5-runtime.lock").exists()
    state["passed"] = state["passed"] and state["r5_idle_passed"] and state["no_r5_receipt"]
    return state


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--development", action="store_true")
    args = parser.parse_args()
    from tests.test_reconnect_r5_host import capture_case, check_case, CASES
    from tools.audit_reconnect_r5_host import audit
    output = ROOT / "evidence/verification" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r5-host")
    output.mkdir(exist_ok=False)
    names = [n for n in (*SOURCES, LOCK) if (ROOT / n).exists()]
    hashes = {n: sha((ROOT / n).read_bytes()) for n in names}
    with zipfile.ZipFile(output / "sources.zip", "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.writestr(name, (ROOT / name).read_bytes())
    checks, cases = {}, {}
    if not args.development:
        try:
            verify_lock()
            checks["immutable-and-host-locks"] = dict(passed=True)
        except (ValueError, AssertionError, OSError) as exc:
            checks["immutable-and-host-locks"] = dict(passed=False, error=str(exc))
        checks["environment-before"] = environment(output, "before")
    definitions = {"tests": ([sys.executable, "-m", "pytest", "-q", *(["tests/test_reconnect_r5_host.py"] if args.development else [])], 300)}
    if not args.development:
        definitions.update({
            "r4-negative-observation": ([sys.executable, "-m", "tools.audit_reconnect_r4_observation"], 35),
            "r3-build-audit": ([sys.executable, "tools/audit_reconnect_r3_build_v2.py", "--run", "evidence/engineering/20260905T111542Z-reconnect-r3-build-release"], 35),
            "statistical-lock": ([sys.executable, "-c", "from tools.run_phase7_analysis import verify_analysis_lock; print(verify_analysis_lock()['lock_id'])"], 35),
        })
    for name, (argv, timeout) in definitions.items():
        started = datetime.now(timezone.utc).isoformat()
        try:
            child = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW,
                                   env=dict(os.environ, PYTHONPATH=str(ROOT / "src") + os.pathsep + str(ROOT)))
            code, stdout, stderr = child.returncode, child.stdout, child.stderr
        except subprocess.TimeoutExpired as exc:
            code, stdout, stderr = None, exc.stdout or b"", (exc.stderr or b"") + b"\nverification timeout\n"
        (output / (name + ".stdout.log")).write_bytes(stdout)
        (output / (name + ".stderr.log")).write_bytes(stderr)
        checks[name] = dict(passed=code == 0, argv=argv, exit_code=code, started_at=started, completed_at=datetime.now(timezone.utc).isoformat())
        if name == "r4-negative-observation" and code == 0:
            old = json.loads(stdout)
            checks[name]["passed"] = old["observation_audit_passed"] is True and old["protocol_execution_valid"] is False
        print(json.dumps(dict(check=name, passed=checks[name]["passed"])), flush=True)
    for case in CASES:
        with tempfile.TemporaryDirectory(prefix="safetwin-r5-host-") as temporary:
            target = Path(temporary)
            try:
                bundle = capture_case(target / "raw", case)
                save(target / "raw/capture.json", bundle)
                members = {p.name: sha(p.read_bytes()) for p in (target / "raw").iterdir()}
                with zipfile.ZipFile(output / (case + ".zip"), "x", compression=zipfile.ZIP_DEFLATED) as archive:
                    for name in sorted(members):
                        archive.writestr(name, (target / "raw" / name).read_bytes())
                with zipfile.ZipFile(output / (case + ".zip")) as archive:
                    assert set(archive.namelist()) == set(members)
                    archive.extractall(target / "extracted")
                assert all(sha((target / "extracted" / n).read_bytes()) == h for n, h in members.items())
                fresh = json.loads((target / "extracted/capture.json").read_bytes())
                check_case(fresh)
                receipt = (target / "extracted/attempt.receipt.jsonl").read_bytes() if fresh["receipt_owned"] else None
                if fresh["audit_error"]:
                    try:
                        audit(fresh["host"], fresh["snapshot"], (target / "extracted/clock.jsonl").read_bytes(), receipt)
                    except ValueError as exc:
                        assert str(exc) == fresh["audit_error"]
                    else:
                        raise ValueError("failed host integrity accepted")
                else:
                    assert audit(fresh["host"], fresh["snapshot"], (target / "extracted/clock.jsonl").read_bytes(), receipt) == fresh["independent"]
                cases[case] = dict(passed=True, member_sha256=members, independent=fresh["independent"], expected_audit_error=fresh["audit_error"])
            except (ValueError, AssertionError, OSError, KeyError, TypeError) as exc:
                cases[case] = dict(passed=False, error=type(exc).__name__ + ": " + str(exc))
            checks["fixture-" + case] = dict(passed=cases[case]["passed"])
            print(json.dumps(dict(check="fixture-" + case, **checks["fixture-" + case])), flush=True)
    if not args.development:
        checks["environment-after"] = environment(output, "after")
        checks["unchanged-official-identities"] = dict(passed=checks["environment-before"].get("states") is not None
                and checks["environment-before"].get("states") == checks["environment-after"].get("states"))
    checks["source-bytes-unchanged"] = dict(passed=all(sha((ROOT / n).read_bytes()) == h for n, h in hashes.items()))
    report = dict(verification_passed=all(c["passed"] for c in checks.values()), development_only=args.development,
                  checks=checks, cases=cases, source_sha256=hashes, evidence_label="fixture", measurement_scope="synthetic-host-component-only",
                  network_trials_executed=0, actual_sleep_inhibition_requested=False, new_native_clock_observation=False,
                  network_execution_authorized=False, whole_protocol_verified=False, official_rollback_verified=False, network_fix_validated=False, TNSM_ready=False)
    save(output / "verification.json", report)
    save(output / "manifest.json", {"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}})
    print(json.dumps(dict(output=str(output), verification_passed=report["verification_passed"], cases=len(cases))))
    return 0 if report["verification_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
