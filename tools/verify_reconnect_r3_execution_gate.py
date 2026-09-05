"""Preserve fixture-only execution verification; never apply an image or fault."""
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sandbox.run_reconnect_r3 import save, sha, LOCK_PATH
from tests.reconnect_r3_fixture import make_bundle
from tools.audit_reconnect_r3_network import audit


def main():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "evidence/verification" / (stamp + "-reconnect-r3-execution")
    output.mkdir(parents=True, exist_ok=False)
    fixtures = ROOT / "evidence/engineering" / (stamp + "-reconnect-r3-execution-fixtures")
    fixtures.mkdir(parents=True, exist_ok=False)
    results = {}
    for mode in ("complete", "bad-baseline", "incomplete-trace", "failed-switch"):
        directory = fixtures / mode
        with patch.object(subprocess, "run", side_effect=AssertionError("fixture attempted actual subprocess I/O")):
            result = make_bundle(directory, mode)
        try: replay = audit(directory, allow_fixture=True)
        except (ValueError, KeyError, IndexError, OSError) as exc:
            replay = {"audit_passed": False, "error": str(exc), "network_fix_validated": False}
        results[mode] = {"runtime_summary": result, "independent_replay": replay,
                         "check_passed": replay["audit_passed"] == (mode == "complete")
                         and result["protocol_execution_valid"] == (mode == "complete")
                         and result["official_image_restored"] and result["final_service_restored"]}
    save(fixtures / "fixture-verification.json", {"variants": results, "transport": "fake-docker-no-io", "actual_docker_commands_executed": 0,
                                                  "evidence_label": "fixture", "network_fix_validated": False})
    save(fixtures / "manifest.json", {"captured_file_sha256": {p.relative_to(fixtures).as_posix(): sha(p.read_bytes()) for p in fixtures.rglob("*") if p.is_file()}})
    release = "evidence/engineering/20260905T111542Z-reconnect-r3-build-release"
    definitions = {
        "full-tests": ([sys.executable, "-m", "pytest", "-q"], 0),
        "fixture-replay": ([sys.executable, "tools/audit_reconnect_r3_network.py", "--run", str(fixtures / "complete"), "--allow-fixture"], 0),
        "fixture-promotion-rejected": ([sys.executable, "tools/audit_reconnect_r3_network.py", "--run", str(fixtures / "complete")], 2),
        "release-build-v2-audit": ([sys.executable, "tools/audit_reconnect_r3_build_v2.py", "--run", release], 0),
        "private-build-v2-audit": ([sys.executable, "tools/audit_reconnect_r3_build_v2.py", "--run", release.removesuffix("-release")], 0),
        "private-redaction-audit": ([sys.executable, "-m", "tools.audit_reconnect_r3_release", "--private"], 0),
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
        if expected == 2: passed = passed and b"fixture cannot pass as sandbox evidence" in result.stdout
        checks[name] = {"argv": argv, "exit_code": result.returncode, "expected_exit_code": expected,
                        "check_passed": passed, "started_at": start, "completed_at": datetime.now(timezone.utc).isoformat()}
    report = {"verification_passed": all(row["check_passed"] for row in checks.values()) and all(row["check_passed"] for row in results.values()),
              "checks": checks, "fixture_variants": {name: row["check_passed"] for name, row in results.items()},
              "fixture_bundle": fixtures.relative_to(ROOT).as_posix(), "evidence_label": "fixture", "network_trials": 0,
              "source_sha256": json.loads(LOCK_PATH.read_bytes())["source_sha256"], "network_fix_validated": False, "TNSM_ready": False}
    save(output / "verification.json", report)
    save(output / "manifest.json", {"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}})
    print((output / "full-tests.log").read_text()); print(output); print(json.dumps({"verification_passed": report["verification_passed"], "fixture_bundle": report["fixture_bundle"]}))
    return 0 if report["verification_passed"] else 2


if __name__ == "__main__": raise SystemExit(main())
