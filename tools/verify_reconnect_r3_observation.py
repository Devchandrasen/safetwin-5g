"""Preserve negative R3 decision verification; never execute another trial."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / "evidence/verification" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r3-observation")
    output.mkdir(exist_ok=False)
    definitions = {
        "full-tests": ([sys.executable, "-m", "pytest", "-q"], 0),
        "observation-and-clock-audit": ([sys.executable, "tools/audit_reconnect_r3_observation.py"], 0),
        "original-protocol-rejection": ([sys.executable, "tools/audit_reconnect_r3_network.py", "--run", "evidence/engineering/20260905T131024Z-reconnect-r3-network"], 2),
        "frozen-source-audit": ([sys.executable, "tools/audit_reconnect_r3_source.py", "--run", "evidence/engineering/20260905T102301Z-reconnect-r3-freeze"], 0),
        "frozen-build-audit": ([sys.executable, "tools/audit_reconnect_r3_build_v2.py", "--run", "evidence/engineering/20260905T111542Z-reconnect-r3-build-release"], 0),
        "committed-execution-lock": ([sys.executable, "-c", "from sandbox.run_reconnect_r3 import verify_execution_lock; print(len(verify_execution_lock()['source_sha256']))"], 0),
        "statistical-lock": ([sys.executable, "-c", "from tools.run_phase7_analysis import verify_analysis_lock; print(verify_analysis_lock()['lock_id'])"], 0),
    }
    checks = {}
    for name, (argv, expected) in definitions.items():
        start = datetime.now(timezone.utc).isoformat()
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=55)
        (output / (name + ".log")).write_bytes(result.stdout + result.stderr)
        passed = result.returncode == expected
        if expected == 2: passed = passed and b"eight required scope snapshots" in result.stdout
        checks[name] = {"argv":argv, "exit_code":result.returncode, "expected_exit_code":expected, "check_passed":passed,
                        "started_at":start, "completed_at":datetime.now(timezone.utc).isoformat()}
    sha = lambda data:hashlib.sha256(data).hexdigest()
    save = lambda path, value:path.write_bytes((json.dumps(value, indent=2)+"\n").encode())
    report = {"verification_passed":all(c["check_passed"] for c in checks.values()), "checks":checks,
              "source_sha256":{name:sha((ROOT/name).read_bytes()) for name in ("tools/capture_reconnect_r3_clock.py", "tools/audit_reconnect_r3_observation.py", "tools/verify_reconnect_r3_observation.py", "tests/test_reconnect_r3_observation.py")},
              "verification_evidence_label":"fixture", "referenced_network_evidence_label":"sandbox-measured", "network_fix_validated":False, "protocol_execution_valid":False}
    save(output / "verification.json", report)
    save(output / "manifest.json", {"captured_file_sha256":{p.name:sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}})
    # Wrapper output was complete before this verification. Do not edit it.
    runtime = ROOT / "evidence/engineering/20260905T131020Z-reconnect-r3-runtime"
    if not (runtime / "manifest.json").exists():
        save(runtime / "provenance.json", {"wrapper_source":"tools/run_with_sleep_inhibition.ps1", "wrapper_source_sha256":sha((ROOT/"tools/run_with_sleep_inhibition.ps1").read_bytes()),
                                          "child_argv":[".venv/Scripts/python.exe", "sandbox/run_reconnect_r3.py", "--execute"], "working_directory":str(ROOT),
                                          "child_exit_code_in_transcript":2, "experiment_acceptance_from_wrapper_exit":False})
        save(runtime / "manifest.json", {"captured_file_sha256":{p.name:sha(p.read_bytes()) for p in runtime.iterdir() if p.is_file()}})
    print((output/"full-tests.log").read_text()); print(output); print(json.dumps({"verification_passed":report["verification_passed"]}))
    return 0 if report["verification_passed"] else 2


if __name__ == "__main__": raise SystemExit(main())
