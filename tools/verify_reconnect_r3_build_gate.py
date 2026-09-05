"""Retain verification logs, including the deliberately failing original audit."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RAW = "evidence/engineering/20260905T111542Z-reconnect-r3-build"
RELEASE = RAW + "-release"


def main():
    output = ROOT / "evidence/verification" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r3-build")
    output.mkdir(parents=True, exist_ok=False)
    definitions = {
        "original-audit-rejection": ([sys.executable, "tools/audit_reconnect_r3_build.py", "--run", RAW], 1),
        "private-v2-audit": ([sys.executable, "tools/audit_reconnect_r3_build_v2.py", "--run", RAW], 0),
        "release-v2-audit": ([sys.executable, "tools/audit_reconnect_r3_build_v2.py", "--run", RELEASE], 0),
        "private-redaction-audit": ([sys.executable, "-m", "tools.audit_reconnect_r3_release", "--private"], 0),
        "full-tests": ([sys.executable, "-m", "pytest", "-q"], 0),
        "r3-source-audit": ([sys.executable, "tools/audit_reconnect_r3_source.py", "--run", "evidence/engineering/20260905T102301Z-reconnect-r3-freeze"], 0),
        "r2-negative-network-audit": ([sys.executable, "tools/audit_reconnect_r2.py", "--run", "evidence/engineering/20260905T082014Z-reconnect-r2"], 0),
        "statistical-lock": ([sys.executable, "-c", "from tools.run_phase7_analysis import verify_analysis_lock; print(verify_analysis_lock()['lock_id'])"], 0),
    }
    checks = {}
    for name, (argv, expected) in definitions.items():
        start = datetime.now(timezone.utc).isoformat()
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=55)
        (output / (name + ".log")).write_bytes(result.stdout + result.stderr)
        passed = result.returncode == expected
        if expected == 1: passed = passed and b"container changed: /safetwin5g-mongodb:Mounts" in result.stderr
        checks[name] = {"argv": argv, "exit_code": result.returncode, "expected_exit_code": expected, "check_passed": passed,
                        "started_at": start, "completed_at": datetime.now(timezone.utc).isoformat()}
    paths = [p for pattern in ("tools/*r3*.py", "tests/*r3*.py", "sandbox/build/reconnect-r3/*", "config/experiments/reconnect-r3*.json", "docs/RECONNECT_R3*.md") for p in ROOT.glob(pattern) if p.is_file()]
    sha = lambda data: hashlib.sha256(data).hexdigest()
    report = {"verification_passed": all(row["check_passed"] for row in checks.values()), "checks": checks,
              "source_sha256": {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in paths},
              "evidence_label": "fixture", "network_trials": 0, "network_fix_validated": False, "TNSM_ready": False}
    (output / "verification.json").write_bytes((json.dumps(report, indent=2) + "\n").encode())
    (output / "manifest.json").write_bytes((json.dumps({"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}}, indent=2) + "\n").encode())
    print((output / "full-tests.log").read_text()); print(output)
    return 0 if report["verification_passed"] else 2


if __name__ == "__main__": raise SystemExit(main())
