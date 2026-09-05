"""Capture software-only R4 execution gate and read-only host prerequisites."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SOURCES = ["config/experiments/reconnect-r4-execution.json", "docs/RECONNECT_R4_EXECUTION.md",
           "sandbox/reconnect_r4_launcher.py", "sandbox/reconnect_r4_process.py", "sandbox/reconnect_r4_host_guard.py",
           "sandbox/run_reconnect_r4.py", "tools/reconnect_r4_window_audit.py", "tools/audit_reconnect_r4_execution.py",
           "tests/reconnect_r4_execution_fixture.py", "tests/reconnect_r4_process_child.py",
           "tests/test_reconnect_r4_process.py", "tests/test_reconnect_r4_execution.py",
           "tools/capture_reconnect_r4_development.py", "tools/fixture_reconnect_r4_execution.py", "tools/verify_reconnect_r4_execution.py"]


def main():
    from sandbox.run_reconnect_r4 import save, sha, IMAGES
    output = ROOT / "evidence/verification" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r4-execution")
    output.mkdir(exist_ok=False)
    definitions = {
        "full-tests": ([sys.executable, "-m", "pytest", "-q"], 0, 180),
        "r4-default-disabled": ([sys.executable, "sandbox/run_reconnect_r4.py"], 2, 20),
        "r4-locked-fixture-release": ([sys.executable, "tools/fixture_reconnect_r4_execution.py"], 0, 180),
        "r4-execution-lock": ([sys.executable, "-c", "from sandbox.run_reconnect_r4 import verify_lock; print(len(verify_lock(committed=False)[0]['source_sha256']))"], 0, 35),
        "r4-collection-committed-lock": ([sys.executable, "-c", "from tools.verify_reconnect_r4_collection import verify_lock; print(verify_lock(committed=True)['lock_id'])"], 0, 35),
        "r3-negative-observation-audit": ([sys.executable, "tools/audit_reconnect_r3_observation.py"], 0, 35),
        "r3-original-rejection": ([sys.executable, "tools/audit_reconnect_r3_network.py", "--run", "evidence/engineering/20260905T131024Z-reconnect-r3-network"], 2, 35),
        "r3-build-audit": ([sys.executable, "tools/audit_reconnect_r3_build_v2.py", "--run", IMAGES["build_release"]], 0, 35),
        "statistical-lock": ([sys.executable, "-c", "from tools.run_phase7_analysis import verify_analysis_lock; print(verify_analysis_lock()['lock_id'])"], 0, 35),
    }
    checks = {}
    for name, (argv, expected, seconds) in definitions.items():
        started = datetime.now(timezone.utc).isoformat()
        try:
            child = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=seconds, creationflags=subprocess.CREATE_NO_WINDOW,
                                   env=dict(os.environ, PYTHONPATH=str(ROOT / "src") + os.pathsep + str(ROOT)))
            code, stdout, stderr = child.returncode, child.stdout, child.stderr
        except subprocess.TimeoutExpired as exc:
            code, stdout, stderr = None, exc.stdout or b"", (exc.stderr or b"") + b"\nverification timeout\n"
        except OSError as exc:
            code, stdout, stderr = None, b"", str(exc).encode()
        (output / (name + ".stdout.log")).write_bytes(stdout)
        (output / (name + ".stderr.log")).write_bytes(stderr)
        passed = code == expected
        if name == "r3-original-rejection":
            passed = passed and b"eight required scope snapshots" in stdout
        if name == "r4-default-disabled":
            passed = passed and b"no mutation by default" in stderr
        checks[name] = {"argv": argv, "exit_code": code, "expected_exit_code": expected, "passed": passed,
                        "started_at": started, "completed_at": datetime.now(timezone.utc).isoformat()}
        print(json.dumps({"check": name, "passed": passed}), flush=True)
    # Only exact minimal daemon queries, bounded while reading, no ping or mutation.
    from sandbox.reconnect_r4_process import BoundedProcess, complete
    from sandbox.reconnect_r4_host_guard import idle_query
    definitions = {
        "official-services": ["docker", "inspect", "--format", '{{.Name}} {{.Id}} {{.Image}} {{json .HostConfig.LogConfig}} {{.State.Health.Status}}', "safetwin5g-ue", "safetwin5g-gnb"],
        "sandbox-status": ["docker", "ps", "--filter", "label=com.docker.compose.project=safetwin5g-sandbox", "--format", "{{.Names}} {{.Status}}"],
        "active-experiment-snapshot": idle_query(os.getpid()),
    }
    transport = BoundedProcess(definitions.values())
    for index, (name, argv) in enumerate(definitions.items(), 1):
        row = transport.run(argv, sequence=index)
        save(output / (name + ".json"), row)
        passed = complete(row) and row["returncode"] == 0 and not row["stderr"]
        if name == "official-services":
            lines = row["stdout"].splitlines()
            try:
                parsed = [line.split(" ", 4) for line in lines]
                passed = passed and len(parsed) == 2 and [p[0] for p in parsed] == ["/safetwin5g-ue", "/safetwin5g-gnb"]
                passed = passed and all(len(p[1]) == 64 and p[2] == IMAGES["official_image_id"] and json.loads(p[3]) == {"Type": "json-file", "Config": {}} and p[4] == "healthy" for p in parsed)
            except (ValueError, IndexError):
                passed = False
        elif name == "active-experiment-snapshot":
            passed = passed and not row["stdout"].strip()
        else:
            lines = row["stdout"].splitlines()
            expected = {"safetwin5g-ue", "safetwin5g-gnb", "safetwin5g-open5gs", "safetwin5g-mongodb", "safetwin5g-prometheus"}
            passed = passed and {line.split()[0] for line in lines} == expected and all("(healthy)" in line for line in lines)
        checks[name] = {"passed": passed, "read_only_environment_check": True}
        print(json.dumps({"check": name, "passed": passed}), flush=True)
    report = {"verification_passed": all(c["passed"] for c in checks.values()), "checks": checks,
              "source_sha256": {n: sha((ROOT / n).read_bytes()) for n in SOURCES}, "python_version": sys.version, "python_executable": sys.executable,
              "evidence_label": "fixture", "live_checks": "read-only process and daemon prerequisites, not network trials",
              "network_trials_executed": 0, "network_fix_validated": False, "network_execution_authorized": False,
              "actual_sleep_inhibition_requested": False, "actual_r4_rollback_verified": False}
    save(output / "verification.json", report)
    save(output / "manifest.json", {"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}})
    print((output / "full-tests.stdout.log").read_text())
    print(json.dumps({"output": str(output), "verification_passed": report["verification_passed"]}))
    return 0 if report["verification_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
