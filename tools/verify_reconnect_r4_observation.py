"""Seal read-only replay, regression tests and current minimal daemon checks.

Never launches the R4 runner, an image change, restart, fault or packet probe.
"""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_reconnect_r4_observation import sha, IMAGES, sealed

SOURCES = ["tools/preflight_reconnect_r4.py", "tools/capture_reconnect_r4_aftercare.py",
           "tools/probe_reconnect_r4_wall_clock.py", "tools/audit_reconnect_r4_observation.py",
           "tools/verify_reconnect_r4_observation.py", "tests/test_reconnect_r4_observation.py"]


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main():
    output = ROOT / "evidence/verification" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r4-observation")
    output.mkdir(exist_ok=False)
    definitions = {
        "full-tests": ([sys.executable, "-m", "pytest", "-q"], 0, 180),
        "r4-observation-audit": ([sys.executable, "-m", "tools.audit_reconnect_r4_observation"], 0, 35),
        "r4-original-rejection-replay": ([sys.executable, "-m", "tools.audit_reconnect_r4_execution", "--run", "evidence/engineering/20260905T170131Z-reconnect-r4-network"], 0, 35),
        "r4-committed-execution-lock": ([sys.executable, "-c", "from sandbox.run_reconnect_r4 import verify_lock; print(len(verify_lock(committed=True)[0]['source_sha256']))"], 0, 35),
        "r4-committed-collection-lock": ([sys.executable, "-c", "from tools.verify_reconnect_r4_collection import verify_lock; print(verify_lock(committed=True)['lock_id'])"], 0, 35),
        "r3-negative-observation-audit": ([sys.executable, "tools/audit_reconnect_r3_observation.py"], 0, 35),
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
        if name in ("r4-observation-audit", "r4-original-rejection-replay") and passed:
            result = json.loads(stdout)
            passed = result["observation_audit_passed"] is True and result["protocol_execution_valid"] is False
        checks[name] = dict(argv=argv, exit_code=code, expected_exit_code=expected, passed=passed,
                            started_at=started, completed_at=datetime.now(timezone.utc).isoformat())
        print(json.dumps(dict(check=name, passed=passed)), flush=True)
    from sandbox.reconnect_r4_process import BoundedProcess, complete
    from sandbox.reconnect_r4_host_guard import idle_query
    queries = {
        "official-services": ["docker", "inspect", "--format", '{{.Name}} {{.Id}} {{.Image}} {{json .HostConfig.LogConfig}} {{.State.Health.Status}}', "safetwin5g-ue", "safetwin5g-gnb"],
        "sandbox-status": ["docker", "ps", "--filter", "label=com.docker.compose.project=safetwin5g-sandbox", "--format", "{{.Names}} {{.Status}}"],
        "active-experiment-snapshot": idle_query(os.getpid()),
    }
    adapter = BoundedProcess(queries.values())
    for sequence, (name, argv) in enumerate(queries.items(), 1):
        row = adapter.run(argv, sequence=sequence)
        save(output / (name + ".json"), row)
        passed = complete(row) and row["returncode"] == 0 and not row["stderr"]
        if name == "official-services":
            try:
                parsed = [line.split(" ", 4) for line in row["stdout"].splitlines()]
                passed = passed and len(parsed) == 2 and [p[0] for p in parsed] == ["/safetwin5g-ue", "/safetwin5g-gnb"]
                passed = passed and all(len(p[1]) == 64 and p[2] == IMAGES["official_image_id"] and
                                        json.loads(p[3]) == {"Type": "json-file", "Config": {}} and p[4] == "healthy" for p in parsed)
            except (ValueError, IndexError):
                passed = False
        elif name == "active-experiment-snapshot":
            passed = passed and not row["stdout"].strip() and not (ROOT / "evidence/private/reconnect-r4-runtime.lock").exists()
        else:
            records = row["stdout"].splitlines()
            expected = {"safetwin5g-ue", "safetwin5g-gnb", "safetwin5g-open5gs", "safetwin5g-mongodb", "safetwin5g-prometheus"}
            passed = passed and {line.split()[0] for line in records} == expected and all("(healthy)" in line for line in records)
        checks[name] = dict(passed=passed, read_only_environment_check=True)
        print(json.dumps(dict(check=name, passed=passed)), flush=True)
    sealed(ROOT / "evidence/engineering/20260905T165847Z-reconnect-r4-preflight")
    checks["preflight-sealed-inventory"] = dict(passed=True)
    report = dict(verification_passed=all(c["passed"] for c in checks.values()), checks=checks,
                  source_sha256={n: sha((ROOT / n).read_bytes()) for n in SOURCES}, python_version=sys.version,
                  python_executable=sys.executable, evidence_label="fixture",
                  observation_replay="separate sandbox-measured records, not new network trials",
                  current_environment="read-only daemon/process checks", mutations_executed=0,
                  protocol_execution_valid=False, network_fix_validated=False, TNSM_ready=False)
    save(output / "verification.json", report)
    save(output / "manifest.json", {"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}})
    print((output / "full-tests.stdout.log").read_text())
    print(json.dumps(dict(output=str(output), verification_passed=report["verification_passed"])))
    return 0 if report["verification_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
