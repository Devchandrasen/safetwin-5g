"""Preserve software/source-audit acceptance separately from image/network gates."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / "evidence/verification" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r3")
    output.mkdir(parents=True, exist_ok=False)
    commands = {
        "full-tests": [sys.executable, "-m", "pytest", "-q"],
        "independent-r3-source-audit": [sys.executable, "tools/audit_reconnect_r3_source.py", "--run", "evidence/engineering/20260905T102301Z-reconnect-r3-freeze"],
        "prior-packet-audit": [sys.executable, "tools/audit_reconnect_packet.py", "--run", "evidence/engineering/20260905T091635Z-reconnect-packet-diagnosis"],
        "prior-r2-build-audit": [sys.executable, "tools/audit_reconnect_r2_build.py", "--run", "evidence/engineering/20260905T071413Z-reconnect-r2-build"],
        "prior-r2-network-audit": [sys.executable, "tools/audit_reconnect_r2.py", "--run", "evidence/engineering/20260905T082014Z-reconnect-r2"],
        "statistical-lock": [sys.executable, "-c", "from tools.run_phase7_analysis import verify_analysis_lock; print(verify_analysis_lock()['lock_id'])"],
    }
    checks = {}
    for name, argv in commands.items():
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=55)
        (output / (name + ".log")).write_bytes(result.stdout + result.stderr)
        checks[name] = {"argv": argv, "exit_code": result.returncode}
    paths = [p for pattern in ("tools/*r3*.py", "tests/*r3*.py", "config/experiments/reconnect-r3*.json", "sandbox/patches/ueransim-reconnect-r3-trace/*", "docs/RECONNECT_R3*.md") for p in ROOT.glob(pattern) if p.is_file()]
    report = {"verification_passed": all(row["exit_code"] == 0 for row in checks.values()), "checks": checks,
              "source_sha256": {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
              "new_image_built": False, "network_trials": 0, "network_fix_validated": False, "TNSM_ready": False}
    (output / "verification.json").write_bytes((json.dumps(report, indent=2) + "\n").encode())
    manifest = {"captured_file_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}}
    (output / "manifest.json").write_bytes((json.dumps(manifest, indent=2) + "\n").encode())
    print((output / "full-tests.log").read_text()); print(output)
    return 0 if report["verification_passed"] else 2


if __name__ == "__main__": raise SystemExit(main())
