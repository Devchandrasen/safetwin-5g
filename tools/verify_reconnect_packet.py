"""Capture test, source-fixture audit and immutable R2 evidence checks."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / "evidence/verification" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-packet")
    output.mkdir(parents=True, exist_ok=False)
    checks = {}
    commands = {
        "full-tests": [sys.executable, "-m", "pytest", "-q"],
        "statistical-lock": [sys.executable, "-c", "from tools.run_phase7_analysis import verify_analysis_lock; print(verify_analysis_lock()['lock_id'])"],
        "independent-packet-audit": [sys.executable, "tools/audit_reconnect_packet.py", "--run", "evidence/engineering/20260905T091635Z-reconnect-packet-diagnosis"],
        "unchanged-r2-build-audit": [sys.executable, "tools/audit_reconnect_r2_build.py", "--run", "evidence/engineering/20260905T071413Z-reconnect-r2-build"],
        "unchanged-r2-network-audit": [sys.executable, "tools/audit_reconnect_r2.py", "--run", "evidence/engineering/20260905T082014Z-reconnect-r2"],
    }
    for name, argv in commands.items():
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=55)
        (output / (name + ".log")).write_bytes(result.stdout + result.stderr)
        checks[name] = {"argv": argv, "exit_code": result.returncode}
    local = ("tools/diagnose_reconnect_packet.py", "tools/audit_reconnect_packet.py", "tools/packet_diagnosis/fixture.cpp",
             "tests/test_reconnect_packet_diagnosis.py", "tools/verify_reconnect_packet.py")
    report = {"checks": checks, "verification_passed": all(r["exit_code"] == 0 for r in checks.values()),
              "source_sha256": {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in local},
              "new_network_trials": 0, "network_fix_validated": False, "TNSM_ready": False}
    (output / "verification.json").write_bytes((json.dumps(report, indent=2) + "\n").encode())
    manifest = {"captured_file_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}}
    (output / "manifest.json").write_bytes((json.dumps(manifest, indent=2) + "\n").encode())
    print((output / "full-tests.log").read_text())
    print(output)
    return 0 if report["verification_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
