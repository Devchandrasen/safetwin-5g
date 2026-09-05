"""Capture R4 software verification and minimal read-only live prerequisites.

Never runs a ping/fault/restart/build/image switch. Every output is immutable.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ["config/experiments/reconnect-r4-collection.json", "docs/RECONNECT_R4_COLLECTION.md",
           "sandbox/reconnect_r4_collection.py", "tools/audit_reconnect_r4_collection.py",
           "tests/reconnect_r4_fixture.py", "tests/test_reconnect_r4_collection.py",
           "tools/fixture_reconnect_r4_collection.py", "tools/verify_reconnect_r4_collection.py"]


def save(path, data):
    path.write_bytes((json.dumps(data, indent=2) + "\n").encode())


def verify_lock(committed=False):
    lock_path = ROOT / "config/experiments/reconnect-r4-collection-lock.json"
    lock = json.loads(lock_path.read_bytes())
    if lock["lock_id"] != "reconnect-r4-collection-v1" or set(lock["source_sha256"]) != set(SOURCES):
        raise ValueError("R4 source inventory drift")
    for name, digest in lock["source_sha256"].items():
        raw = (ROOT / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("R4 source drift: " + name)
        if committed and subprocess.check_output(["git", "show", "HEAD:" + name], cwd=ROOT) != raw:
            raise ValueError("uncommitted R4 source: " + name)
    if committed and subprocess.check_output(["git", "show", "HEAD:config/experiments/reconnect-r4-collection-lock.json"], cwd=ROOT) != lock_path.read_bytes():
        raise ValueError("uncommitted R4 lock")
    prior = ROOT / "config/experiments/reconnect-r3-execution-lock.json"
    if hashlib.sha256(prior.read_bytes()).hexdigest() != lock["immutable_r3_lock_sha256"]:
        raise ValueError("immutable R3 lock drift")
    return lock


def main():
    output = ROOT / "evidence/verification" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r4-collection")
    output.mkdir(exist_ok=False)
    definitions = {
        "full-tests": ([sys.executable, "-m", "pytest", "-q"], 0),
        "r4-fixture-capture": ([sys.executable, "tools/fixture_reconnect_r4_collection.py"], 0),
        "r4-source-lock": ([sys.executable, "-c", "from tools.verify_reconnect_r4_collection import verify_lock; print(verify_lock()['lock_id'])"], 0),
        "r3-negative-observation-audit": ([sys.executable, "tools/audit_reconnect_r3_observation.py"], 0),
        "r3-original-protocol-rejection": ([sys.executable, "tools/audit_reconnect_r3_network.py", "--run", "evidence/engineering/20260905T131024Z-reconnect-r3-network"], 2),
        "r3-committed-execution-lock": ([sys.executable, "-c", "from sandbox.run_reconnect_r3 import verify_execution_lock; print(len(verify_execution_lock()['source_sha256']))"], 0),
        "r3-source-audit": ([sys.executable, "tools/audit_reconnect_r3_source.py", "--run", "evidence/engineering/20260905T102301Z-reconnect-r3-freeze"], 0),
        "r3-build-audit": ([sys.executable, "tools/audit_reconnect_r3_build_v2.py", "--run", "evidence/engineering/20260905T111542Z-reconnect-r3-build-release"], 0),
        "statistical-lock": ([sys.executable, "-c", "from tools.run_phase7_analysis import verify_analysis_lock; print(verify_analysis_lock()['lock_id'])"], 0),
        "read-only-existing-scope-preflight": ([sys.executable, "tools/preflight_reconnect_r3.py"], 0),
        "read-only-r4-logging-compatibility": (["docker", "inspect", "--format", '{{.Name}} {{.Image}} {{json .HostConfig.LogConfig}} {{.State.Running}}', "safetwin5g-ue", "safetwin5g-gnb"], 0),
    }
    checks = {}
    for name, (argv, expected) in definitions.items():
        started = datetime.now(timezone.utc).isoformat()
        try:
            child = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=55)
            code, stdout, stderr = child.returncode, child.stdout, child.stderr
        except subprocess.TimeoutExpired as exc:
            code, stdout, stderr = None, exc.stdout or b"", (exc.stderr or b"") + b"\nverification command timed out\n"
        except OSError as exc:
            code, stdout, stderr = None, b"", str(exc).encode()
        (output / (name + ".stdout.log")).write_bytes(stdout)
        (output / (name + ".stderr.log")).write_bytes(stderr)
        passed = code == expected
        if expected == 2:
            passed = passed and b"eight required scope snapshots" in stdout
        if name == "read-only-r4-logging-compatibility":
            image = json.loads((ROOT / "config/experiments/reconnect-r3-images.json").read_bytes())["official_image_id"]
            passed = passed and stdout.decode().splitlines() == [f'/{n} {image} {{"Type":"json-file","Config":{{}}}} true' for n in ("safetwin5g-ue", "safetwin5g-gnb")]
        checks[name] = {"argv": argv, "exit_code": code, "expected_exit_code": expected, "check_passed": passed,
                        "started_at": started, "completed_at": datetime.now(timezone.utc).isoformat()}
        print(json.dumps({"check": name, "passed": passed}), flush=True)
    report = {"verification_passed": all(c["check_passed"] for c in checks.values()), "checks": checks,
              "source_sha256": {n: hashlib.sha256((ROOT / n).read_bytes()).hexdigest() for n in SOURCES},
              "evidence_label": "fixture", "live_checks": "read-only environment prerequisites, not network trials",
              "network_trials_executed": 0, "network_fix_validated": False, "network_execution_authorized": False,
              "rollback_verified_by_r4": False}
    save(output / "verification.json", report)
    save(output / "manifest.json", {"captured_file_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}})
    print((output / "full-tests.stdout.log").read_text())
    print(json.dumps({"output": str(output), "verification_passed": report["verification_passed"]}))
    return 0 if report["verification_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
