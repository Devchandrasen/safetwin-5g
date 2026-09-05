"""Post-run read-only clock/identity probe. No pings, faults or image changes."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sandbox.reconnect_r3_measurement import INSPECT_FORMAT, CONTAINERS, NETWORK, UE, GNB

RUN = ROOT / "evidence/engineering/20260905T131024Z-reconnect-r3-network"


def now(): return datetime.now(timezone.utc).isoformat()
def sha(data): return hashlib.sha256(data).hexdigest()
def save(path, data): path.write_bytes((json.dumps(data, indent=2) + "\n").encode())


def clock_bounds(row):
    host_start, host_end = [datetime.fromisoformat(row[k]) for k in ("started_at", "completed_at")]
    remote = datetime.fromisoformat(row["stdout"].strip())
    if host_end < host_start or abs((host_end-host_start).total_seconds() - row["monotonic_elapsed_seconds"]) > 0.05:
        raise ValueError("host wall-clock step makes bracket unreliable")
    return {"container_minus_host_lower_seconds": (remote-host_end).total_seconds(),
            "container_minus_host_upper_seconds": (remote-host_start).total_seconds()}


def main():
    if not (RUN / "manifest.json").exists() or (ROOT / "evidence/private/reconnect-r3-runtime.lock").exists():
        raise PermissionError("terminal R3 run and no active runtime lock required")
    output = ROOT / "evidence/engineering" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r3-clock")
    output.mkdir(exist_ok=False)
    rows = []
    def command(name, argv):
        row = {"sequence": len(rows)+1, "name": name, "argv": argv, "started_at": now(), "timeout_seconds": 10}
        tick = time.monotonic()
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, timeout=10)
        row.update(completed_at=now(), monotonic_elapsed_seconds=time.monotonic()-tick, returncode=result.returncode,
                   stdout=result.stdout.decode(), stderr=result.stderr.decode(), stdout_sha256=sha(result.stdout), stderr_sha256=sha(result.stderr))
        rows.append(row); save(output / "commands.json", rows)
        if result.returncode: raise RuntimeError("read-only command failed: " + name)
        return row
    errors = []
    try:
        for phase in ("before", "after"):
            command(phase + "-network", ["docker", "network", "inspect", NETWORK])
            command(phase + "-containers", ["docker", "inspect", "--format", INSPECT_FORMAT, *CONTAINERS])
            if phase == "after": break
            for container in (UE, GNB):
                for i in range(5): command(f"clock-{container}-{i+1}", ["docker", "exec", container, "date", "-u", "+%Y-%m-%dT%H:%M:%S.%NZ"])
            command("ue-address", ["docker", "exec", UE, "ip", "-j", "-4", "address", "show", "dev", "uesimtun0"])
    except Exception as exc: errors.append(f"{type(exc).__name__}: {exc}")
    clocks = [{"command_sequence": row["sequence"], "container": row["argv"][2], **clock_bounds(row)} for row in rows if row["name"].startswith("clock-")]
    report = {"captured_at": now(), "errors": errors, "clock_brackets": clocks,
              "all_remote_clocks_behind_host": bool(len(clocks) == 10 and all(row["container_minus_host_upper_seconds"] < 0 for row in clocks)),
              "scope": "post-run read-only clock and address measurement", "evidence_label": "sandbox-measured",
              "network_trials": 0, "live_actuation": False, "network_fix_validated": False,
              "historical_missing_trace_recovered": False,
              "referenced_manifest_sha256": sha((RUN / "manifest.json").read_bytes()),
              "source_sha256": {name: sha((ROOT / name).read_bytes()) for name in
                  ("tools/capture_reconnect_r3_clock.py", "sandbox/reconnect_r3_measurement.py")}}
    save(output / "summary.json", report)
    save(output / "manifest.json", {"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}})
    print(output); print(json.dumps({"errors": errors, "clock_brackets": clocks}, indent=2))
    return int(bool(errors))


if __name__ == "__main__": raise SystemExit(main())
