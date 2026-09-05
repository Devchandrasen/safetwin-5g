"""Preserve software, immutable build and optional network verification separately."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run")
    args = parser.parse_args()
    output = ROOT / "evidence/verification" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r2")
    output.mkdir(parents=True, exist_ok=False)
    checks = {}
    def execute(name, argv):
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=55)
        (output / (name + ".log")).write_text(result.stdout + result.stderr, encoding="utf-8")
        checks[name] = {"argv": argv, "exit_code": result.returncode}
        return result.returncode == 0
    software = execute("full-tests", [sys.executable, "-m", "pytest", "-q"])
    software &= execute("statistical-lock", [sys.executable, "-c", "from tools.run_phase7_analysis import verify_analysis_lock; print(verify_analysis_lock()['lock_id'])"])
    build = execute("independent-build-audit", [sys.executable, "tools/audit_reconnect_r2_build.py", "--run", "evidence/engineering/20260905T071413Z-reconnect-r2-build"])
    measured = execute("independent-network-audit", [sys.executable, "tools/audit_reconnect_r2.py", "--run", args.run]) if args.run else None
    sources = {str(p.relative_to(ROOT)).replace("\\", "/"): hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest()
               for pattern in ("tools/*reconnect_r2*.py", "tests/*reconnect_r2*.py", "sandbox/*reconnect_r2*.py", "config/experiments/reconnect-r2*.json") for p in ROOT.glob(pattern)}
    report = {"software_verification_passed": bool(software), "build_audit_passed": build,
              "measured_network_audit_passed": measured, "checks": checks,
              "source_sha256": sources, "source_hash_mode": "utf8-lf-normalized",
              "build_evidence_label": "fixture", "long_campaign_ready": False, "TNSM_ready": False}
    (output / "verification.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}
    (output / "manifest.json").write_text(json.dumps({"captured_file_sha256": hashes}, indent=2) + "\n", encoding="utf-8")
    print((output / "full-tests.log").read_text())
    print(output)
    return 0 if software and build and measured is not False else 2


if __name__ == "__main__":
    raise SystemExit(main())
