"""Capture software verification and optional independently audited reproduction."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sandbox.run_reconnect import FAULT_SCRIPT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run")
    args = parser.parse_args()
    output = ROOT / "evidence/verification" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r1")
    output.mkdir(parents=True, exist_ok=False)
    checks = {}
    def execute(name, argv):
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=55)
        (output / (name + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
        checks[name] = {"argv": argv, "exit_code": result.returncode}
        return result.returncode == 0
    software = execute("full-tests", [sys.executable, "-m", "pytest", "-q"])
    software &= execute("statistical-lock", [sys.executable, "-c", "from tools.run_phase7_analysis import verify_analysis_lock; print(verify_analysis_lock()['lock_id'])"])
    software &= execute("fault-shell-syntax", ["docker", "exec", "safetwin5g-ue", "sh", "-n", "-c", FAULT_SCRIPT])
    measured = execute("independent-audit", [sys.executable, "tools/audit_reconnect.py", "--run", args.run]) if args.run else None
    sources = {}
    for name in ("sandbox/run_reconnect.py", "config/experiments/reconnect-r1.json", "docs/RECONNECT_R1_PROTOCOL.md", "tools/audit_reconnect.py", "tools/verify_reconnect.py", "tests/test_reconnect.py"):
        sources[name] = hashlib.sha256((ROOT / name).read_text(encoding="utf-8").encode()).hexdigest()
    report = {"software_verification_passed": bool(software), "measured_audit_passed": measured,
              "source_sha256": sources, "source_hash_mode": "utf8-lf-normalized", "checks": checks,
              "network_fix_validated": False, "long_campaign_ready": False, "TNSM_ready": False}
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
    (output / "manifest.json").write_text(json.dumps({"captured_file_sha256": hashes}, indent=2) + "\n", encoding="utf-8")
    print((output / "full-tests.log").read_text())
    print(output)
    return 0 if software and measured is not False else 2


if __name__ == "__main__":
    raise SystemExit(main())
