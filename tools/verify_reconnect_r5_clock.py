"""R5 software-gate evidence capture. No network execution or clock setting."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SOURCES = ["sandbox/reconnect_r5_clock.py", "tools/audit_reconnect_r5_clock.py", "tests/test_reconnect_r5_clock.py",
           "tools/verify_reconnect_r5_clock.py", "docs/RECONNECT_R5_CLOCK.md"]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def directory(suffix):
    output = ROOT / "evidence/engineering" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + suffix)
    output.mkdir(exist_ok=False)
    return output


def development():
    output = directory("-reconnect-r5-clock-development")
    argv = [sys.executable, "-m", "pytest", "tests/test_reconnect_r5_clock.py::test_strict_json_rejects_ambiguity", "-q", "--tb=short", "-rN"]
    started = datetime.now(timezone.utc).isoformat()
    child = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=35, creationflags=subprocess.CREATE_NO_WINDOW)
    entries = {n: (ROOT / n).read_bytes() for n in SOURCES if (ROOT / n).is_file()}
    entries.update({"capture/stdout.log": child.stdout, "capture/stderr.log": child.stderr})
    with zipfile.ZipFile(output / "failure.zip", "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, raw in entries.items():
            archive.writestr(name, raw)
    with zipfile.ZipFile(output / "failure.zip") as archive:
        assert all(archive.read(n) == raw for n, raw in entries.items())
    save(output / "failure.json", dict(argv=argv, started_at=started, completed_at=datetime.now(timezone.utc).isoformat(),
                                       exit_code=child.returncode, member_sha256={n: sha(raw) for n, raw in entries.items()},
                                       purpose="pre-correction-test-harness-failure-not-network-trial", evidence_label="fixture",
                                       source_snapshot_before_correction=True, actual_docker_commands=0))
    save(output / "manifest.json", {"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}})
    print(re.sub(r" {100,}", "<oversized-param-id>", child.stdout.decode("utf-8", "replace"))[-6000:])
    print(json.dumps(dict(output=str(output), exit_code=child.returncode, captured_stdout_bytes=len(child.stdout))))


def environment(output, prefix):
    from sandbox.reconnect_r4_process import BoundedProcess, complete
    from sandbox.reconnect_r4_host_guard import idle_query
    from tools.audit_reconnect_r3_network import audit_scope, NAMES
    from tools.audit_reconnect_r4_observation import CONTRACT, IMAGES
    commands = {
        "idle": idle_query(os.getpid()),
        "network": ["docker", "network", "inspect", "safetwin5g-isolated"],
        "containers": ["docker", "inspect", "--format", CONTRACT["inspect_format"], *NAMES],
    }
    adapter = BoundedProcess(commands.values())
    captured = {}
    for index, (name, argv) in enumerate(commands.items(), 1):
        row = adapter.run(argv, sequence=index)
        captured[name] = row
        save(output / (prefix + "-" + name + ".json"), row)
    try:
        assert all(complete(r) and r["returncode"] == 0 and not r["stderr"] for r in captured.values())
        assert not captured["idle"]["stdout"].strip()
        assert not (ROOT / "evidence/private/reconnect-r4-runtime.lock").exists()
        network = json.loads(captured["network"]["stdout"])
        assert len(network) == 1
        containers = [json.loads(line) for line in captured["containers"]["stdout"].splitlines()]
        reference = json.loads((ROOT / "config/experiments/reconnect-r3-scope-reference.json").read_bytes())["containers"]
        states = audit_scope(network[0], containers, reference, "official", IMAGES)
        return dict(passed=True, states={n: {k: r[k] for k in ("Id", "Image", "RestartCount", "State")} for n, r in states.items()})
    except (ValueError, AssertionError, KeyError, TypeError) as exc:
        return dict(passed=False, error=type(exc).__name__ + ": " + str(exc))


def gate():
    from tools.audit_reconnect_r5_clock import verify_lock, audit_bundle, strict_json
    from tests.test_reconnect_r5_clock import fixture_cases, bundle
    from sandbox.reconnect_r5_clock import WindowsClock
    lock = verify_lock(committed=False)
    if any((ROOT / "evidence/verification").glob("*-reconnect-r5-clock/native-clock.json")):
        raise PermissionError("native R5 clock observation already exists; independently replay it, do not replace it")
    output = ROOT / "evidence/verification" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r5-clock")
    output.mkdir(exist_ok=False)
    save(output / "source-lock.json", lock)
    checks, cases = {}, {}
    checks["environment-before"] = environment(output, "before")
    # Synthetic execution cannot invoke the Windows clock, a process or socket.
    with patch("subprocess.Popen", side_effect=AssertionError("fixture subprocess forbidden")), patch("socket.socket", side_effect=AssertionError("fixture socket forbidden")):
        for name, entry in fixture_cases().items():
            path = output / ("fixture-" + name + ".json")
            save(path, entry["bundle"])
            try:
                replayed = audit_bundle(strict_json(path.read_bytes()), allow_fixture=True)
                expected = entry["expected_rejection"]
                assert replayed["clock_capture_valid"] is (expected is None)
                assert replayed["rejection"] is None if expected is None else replayed["rejection"]["code"] == expected
                cases[name] = dict(passed=True, expected_rejection=expected, independent=replayed, file=path.name)
            except (ValueError, AssertionError, KeyError, TypeError) as exc:
                cases[name] = dict(passed=False, error=str(exc), file=path.name)
    checks["serialized-independent-fixtures"] = dict(passed=all(v["passed"] for v in cases.values()), cases=len(cases))
    save(output / "fixtures.json", cases)
    print(json.dumps(dict(check="serialized-independent-fixtures", **checks["serialized-independent-fixtures"])), flush=True)
    # Native local-host observation is separate from synthetic cases, fixed at
    # 64 attempted reads with no selected replacements or discarded warm-ups.
    if checks["environment-before"]["passed"]:
        try:
            clock = WindowsClock()
            rows = []
            for _ in range(64):
                row = clock.capture()
                rows.append(row)
                with (output / "native-points.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
                    handle.write(json.dumps(row) + "\n")
                    handle.flush()
                    os.fsync(handle.fileno())
                time.sleep(0.001)
            captured = bundle(clock.descriptor, rows, fixture=False)
            save(output / "native-clock.json", captured)
            replayed = audit_bundle(strict_json((output / "native-clock.json").read_bytes()))
            assert [json.loads(line) for line in (output / "native-points.jsonl").read_text().splitlines()] == rows
            checks["native-clock-observation"] = dict(passed=replayed["clock_capture_valid"], independent=replayed)
        except (OSError, ValueError, AssertionError, KeyError, TypeError) as exc:
            checks["native-clock-observation"] = dict(passed=False, error=type(exc).__name__ + ": " + str(exc))
    else:
        checks["native-clock-observation"] = dict(passed=False, error="not attempted: current environment prerequisite rejected")
    save(output / "native-audit.json", checks["native-clock-observation"])
    print(json.dumps(dict(check="native-clock-observation", **checks["native-clock-observation"])), flush=True)
    definitions = {
        "full-tests": ([sys.executable, "-m", "pytest", "-q"], 180),
        "r4-committed-execution-lock": ([sys.executable, "-c", "from sandbox.run_reconnect_r4 import verify_lock; print(len(verify_lock(committed=True)[0]['source_sha256']))"], 35),
        "r4-negative-observation-audit": ([sys.executable, "-m", "tools.audit_reconnect_r4_observation"], 35),
        "r3-build-audit": ([sys.executable, "tools/audit_reconnect_r3_build_v2.py", "--run", "evidence/engineering/20260905T111542Z-reconnect-r3-build-release"], 35),
        "statistical-lock": ([sys.executable, "-c", "from tools.run_phase7_analysis import verify_analysis_lock; print(verify_analysis_lock()['lock_id'])"], 35),
    }
    for name, (argv, seconds) in definitions.items():
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
        passed = code == 0
        if name == "r4-negative-observation-audit" and passed:
            original = json.loads(stdout)
            passed = original["observation_audit_passed"] is True and original["protocol_execution_valid"] is False
        checks[name] = dict(passed=passed, argv=argv, exit_code=code, started_at=started, completed_at=datetime.now(timezone.utc).isoformat())
        print(json.dumps(dict(check=name, passed=passed)), flush=True)
    checks["environment-after"] = environment(output, "after")
    checks["unchanged-official-identities"] = dict(passed=checks["environment-before"].get("states") is not None and
                                                 checks["environment-before"].get("states") == checks["environment-after"].get("states"))
    verify_lock(committed=False)
    checks["clock-source-lock"] = dict(passed=True, sources=len(lock["source_sha256"]))
    failures = list((ROOT / "evidence/engineering").glob("*-reconnect-r5-clock-development"))
    for failure in failures:
        meta = json.loads((failure / "failure.json").read_bytes())
        manifest = json.loads((failure / "manifest.json").read_bytes())["captured_file_sha256"]
        assert all(sha((failure / n).read_bytes()) == digest for n, digest in manifest.items())
        with zipfile.ZipFile(failure / "failure.zip") as archive:
            assert set(archive.namelist()) == set(meta["member_sha256"])
            assert all(sha(archive.read(n)) == digest for n, digest in meta["member_sha256"].items())
        assert meta["exit_code"] == 1 and meta["actual_docker_commands"] == 0
    checks["retained-development-rejection"] = dict(passed=len(failures) == 1, archives=len(failures))
    report = dict(verification_passed=all(c["passed"] for c in checks.values()), checks=checks,
                  source_sha256=lock["source_sha256"], lock_sha256=sha((ROOT / "config/experiments/reconnect-r5-clock-lock.json").read_bytes()),
                  evidence_label="fixture", native_evidence_scope="separately captured local-host-clock-api-only",
                  actual_network_trials=0, actual_clock_settings_changed=False, actual_image_changes=0,
                  network_execution_authorized=False, network_fix_validated=False, TNSM_ready=False)
    save(output / "verification.json", report)
    save(output / "manifest.json", {"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}})
    print((output / "full-tests.stdout.log").read_text())
    print(json.dumps(dict(output=str(output), verification_passed=report["verification_passed"])))
    return 0 if report["verification_passed"] else 2


if __name__ == "__main__":
    if sys.argv[1:] == ["--capture-development"]:
        development()
    else:
        if sys.argv[1:]:
            raise SystemExit("only --capture-development is supported; no execution mode")
        raise SystemExit(gate())
