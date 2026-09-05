"""Owned local-process fixtures only; never a measured network invocation."""
from datetime import datetime, timezone
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
from tools.verify_reconnect_r5_journal import save, sha

SOURCES = ("sandbox/reconnect_r5_process.py", "tools/audit_reconnect_r5_process.py", "tests/test_reconnect_r5_process.py",
           "tools/verify_reconnect_r5_process.py", "docs/RECONNECT_R5_PROCESS.md")
LOCK = "config/experiments/reconnect-r5-process-lock.json"
PRIOR = "config/experiments/reconnect-r5-journal-lock.json"


def verify_lock(committed=False):
    from tools.verify_reconnect_r5_journal import verify_lock as journal_lock
    from sandbox.run_reconnect_r4 import verify_lock as r4_lock
    journal_lock(committed=True)
    r4_lock(committed=True)
    lock = json.loads((ROOT / LOCK).read_bytes())
    assert set(lock) == {"lock_id", "source_sha256", "immutable_journal_lock_sha256", "network_execution_authorized", "whole_protocol_verified"}
    assert lock["lock_id"] == "safetwin5g-reconnect-r5-process-v1"
    assert lock["network_execution_authorized"] is False and lock["whole_protocol_verified"] is False
    assert set(lock["source_sha256"]) == set(SOURCES) and lock["immutable_journal_lock_sha256"] == sha((ROOT / PRIOR).read_bytes())
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
    from tests.test_reconnect_r5_process import capture_case, check_case, CASES
    from tools.audit_reconnect_r5_process import audit
    from tools.verify_reconnect_r5_clock import environment
    output = ROOT / "evidence/verification" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r5-process")
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
            checks["immutable-and-process-locks"] = dict(passed=True)
        except (ValueError, AssertionError, OSError) as exc:
            checks["immutable-and-process-locks"] = dict(passed=False, error=str(exc))
        checks["environment-before"] = environment(output, "before")
    definitions = {"tests": ([sys.executable, "-m", "pytest", "-q", *(["tests/test_reconnect_r5_process.py"] if args.development else [])], 300)}
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
    selected = [name for name in CASES if name != "native-shared-envelopes"]
    if not args.development:
        selected.append("native-shared-envelopes")
    with patch("socket.socket", side_effect=AssertionError("fixture socket forbidden")):
        for case in selected:
            if case == "native-shared-envelopes" and (not all(c["passed"] for c in checks.values())
                    or any((ROOT / "evidence/verification").glob("*-reconnect-r5-process/native-shared-envelopes.zip"))):
                checks["fixture-" + case] = dict(passed=False, error="native owned-process observation not repeated or admitted after failed prerequisites")
                continue
            with tempfile.TemporaryDirectory(prefix="safetwin-r5-process-") as temporary:
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
                    if case == "journal-failed":
                        try:
                            audit(fresh["records"], fresh["snapshot"], (target / "extracted/clock.jsonl").read_bytes(), fresh["allowed"], fresh["cleanup_allowed"])
                        except ValueError as exc:
                            assert "storage failed" in str(exc)
                        else:
                            raise ValueError("failed durability journal was accepted")
                    else:
                        assert audit(fresh["records"], fresh["snapshot"], (target / "extracted/clock.jsonl").read_bytes(), fresh["allowed"], fresh["cleanup_allowed"]) == fresh["independent"]
                    cases[case] = dict(passed=True, member_sha256=members, independent=fresh["independent"],
                                       expected_audit_error=fresh["audit_error"], clock_scope=fresh["clock_scope"],
                                       raw_client_results=[{k: r[k] for k in ("sequence", "complete", "timing_valid", "client_capture_complete", "launcher_go_sent", "returncode", "timed_out")} for r in fresh["records"]])
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
                  checks=checks, cases=cases, source_sha256=hashes, evidence_label="fixture", measurement_scope="owned-local-process-component-only",
                  network_trials_executed=0, actual_sleep_inhibition_requested=False, network_execution_authorized=False,
                  whole_protocol_verified=False, official_rollback_verified=False, network_fix_validated=False, TNSM_ready=False)
    save(output / "verification.json", report)
    save(output / "manifest.json", {"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}})
    print(json.dumps(dict(output=str(output), verification_passed=report["verification_passed"], cases=len(cases))))
    return 0 if report["verification_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
