"""Read-only R4 host/scope/log compatibility capture; never enables mutation."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sandbox.run_reconnect_r4 import R4Backend, BoundedProcess, allowed_commands, verify_lock, save, sha, IMAGES, UE, GNB
from sandbox.reconnect_r4_process import complete
from sandbox.reconnect_r4_host_guard import idle_query
from tools.audit_reconnect_r3_build_v2 import audit as build_audit
from tools.audit_reconnect_r3_network import audit_scope
from tools.reconnect_r4_window_audit import logs_read


def main():
    output = ROOT / "evidence/engineering" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r4-preflight")
    output.mkdir(exist_ok=False)
    report = {"preflight_passed": False, "mutation_enabled": False, "network_trials_executed": 0,
              "candidate_image_applied": False, "sleep_inhibition_requested": False,
              "evidence_label": "sandbox-measured", "purpose": "read-only-environment-prerequisites-not-network-trial",
              "errors": [], "source_sha256": sha(Path(__file__).read_bytes())}
    backend = None
    try:
        lock, digest = verify_lock(committed=True)
        report["execution_lock_sha256"] = digest
        report["source_lock"] = lock
        report["build_audit"] = build_audit(ROOT / IMAGES["build_release"])
        guards = {name: (ROOT / "evidence/private" / name).exists() for name in ("reconnect-r3-runtime.lock", "reconnect-r4-runtime.lock")}
        attempts = [p.name for p in (ROOT / "evidence/engineering").glob("*-reconnect-r4-network")]
        report.update(runtime_locks=guards, prior_r4_attempts=attempts)
        if any(guards.values()) or attempts:
            raise PermissionError("existing guard or attempt requires inspection")
        argv = idle_query(os.getpid())
        row = BoundedProcess([argv]).run(argv, sequence=0)
        save(output / "idle-processes.json", row)
        if not complete(row) or row["returncode"] != 0 or row["stdout"].strip() or row["stderr"]:
            raise PermissionError("active/incomplete experiment process snapshot")
        backend = R4Backend(output, BoundedProcess(allowed_commands()), {}, digest)
        backend.preflight()  # empty approval and authorized=False throughout
        reference = json.loads((ROOT / "config/experiments/reconnect-r3-scope-reference.json").read_bytes())["containers"]
        by_name = {r["name"]: r for r in backend.records}
        audit_scope(json.loads(by_name["preflight-network"]["stdout"])[0],
                    [json.loads(line) for line in by_name["preflight-containers"]["stdout"].splitlines()], reference, "official", IMAGES)
        for component in (UE, GNB):
            raw = backend.capture_logs(component, "preflight-log-" + component)
            logs_read(raw)
        if backend.authorized or backend.candidate_touched:
            raise PermissionError("read-only preflight unexpectedly enabled mutation")
        report["preflight_passed"] = True
    except BaseException as exc:
        report["errors"].append(type(exc).__name__ + ": " + str(exc))
    if backend:
        report["command_records"] = len(backend.records)
        report["actual_docker_commands_executed"] = sum(r["argv"][0] == "docker" for r in backend.records)
    save(output / "preflight.json", report)
    save(output / "manifest.json", {"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}})
    print(json.dumps({"output": str(output), "preflight_passed": report["preflight_passed"], "errors": report["errors"]}))
    return 0 if report["preflight_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
