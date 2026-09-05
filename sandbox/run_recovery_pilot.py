"""Run a bounded, separately approved sandbox recovery engineering pilot."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from safetwin5g.phase7_runner import _is_clean  # noqa: E402
from safetwin5g.telemetry import parse_ping  # noqa: E402

CONFIG = ROOT / "config/experiments/recovery-pilot-r1.json"
CORE = "safetwin5g-open5gs"
UE = "safetwin5g-ue"
GNB = "safetwin5g-gnb"
CONTAINERS = [CORE, GNB, UE, "safetwin5g-mongodb", "safetwin5g-prometheus"]
NETWORK = "safetwin5g-isolated"
ORDER = ["primitive_cleanup", "ue_restart", "core_gnb_ue_restart"]


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def source_sha(path):
    return hashlib.sha256(Path(path).read_text(encoding="utf-8").encode()).hexdigest()


def samples_clean(samples):
    return len(samples) == 3 and all(
        _is_clean(sample)
        and sample["metrics"].get("packets_transmitted") == 5
        and sample["metrics"].get("packets_received") == 5
        and sample["metrics"].get("prometheus_targets_up_count") == 3
        for sample in samples
    )


def validate_config(config, policy):
    if (config["environment"] != "sandbox" or config["confirmatory_data_reuse"] is not False
            or policy["allow_live_actuation"] is not False
            or policy["require_human_approval"] is not True
            or config["trial_hold_seconds"] != [0, 1, 30, 30, 45, 0]
            or config["recovery_order"] != ORDER
            or config["fault_watchdog_seconds"] != 65
            or config["maximum_total_seconds"] != 900
            or config["maximum_command_seconds"] != 35
            or config["maximum_container_health_seconds"] != 50
            or config["samples_per_window"] != 3
            or config["packets_per_sample"] != 5
            or config["maximum_packet_loss_percent"] != 1.0):
        raise PermissionError("fixed sandbox pilot and fail-closed policy required")


def validate_environment(network, containers, versions):
    if (network["Name"] != NETWORK or network["Internal"] is not True
            or network["Labels"].get("com.docker.compose.project") != "safetwin5g-sandbox"
            or {v["Name"] for v in network["Containers"].values()} != set(CONTAINERS)
            or {c["Name"].lstrip("/") for c in containers} != set(CONTAINERS)):
        raise PermissionError("exact isolated SafeTwin network required")
    for container in containers:
        labels = container["Config"]["Labels"]
        if (labels.get("com.docker.compose.project") != "safetwin5g-sandbox"
                or set(container["NetworkSettings"]["Networks"]) != {NETWORK}
                or container["HostConfig"].get("PortBindings")
                or container["HostConfig"].get("Privileged")
                or container["State"].get("Health", {}).get("Status") != "healthy"):
            raise PermissionError("container isolation or health failed")
        name = container["Name"].lstrip("/")
        if name in (CORE, GNB, UE):
            component = "open5gs" if name == CORE else "ueransim"
            if labels.get("safetwin5g.upstream.commit") != versions[component]["commit"]:
                raise PermissionError("source version drift")
        else:
            component = "mongodb" if name.endswith("mongodb") else "prometheus"
            if not container["Config"]["Image"].endswith("@" + versions[component]["digest"]):
                raise PermissionError("image digest drift")


class Backend:
    def __init__(self, output, config):
        self.output, self.config = output, config
        self.sequence = 0
        self.unit_id = "preflight"
        self.deadline = time.monotonic() + config["maximum_total_seconds"]
        self.restoring = False

    def cmd(self, name, argv, accepted=(0,)):
        if not self.restoring and time.monotonic() >= self.deadline:
            raise TimeoutError("pilot admission budget reached; rollback remains enabled")
        self.sequence += 1
        started = now()
        try:
            result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace",
                                    timeout=self.config["maximum_command_seconds"])
            code, stdout, stderr = result.returncode, result.stdout, result.stderr
        except subprocess.TimeoutExpired as exc:
            code = -999
            stdout = (exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
            stderr = "command timed out"
        row = {"sequence": self.sequence, "unit_id": self.unit_id, "name": name,
               "started_at": started, "completed_at": now(), "argv": argv,
               "returncode": code, "accepted_returncodes": list(accepted),
               "stdout": stdout, "stderr": stderr,
               "stdout_sha256": hashlib.sha256(stdout.encode()).hexdigest()}
        with (self.output / "commands.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
        if code not in accepted:
            raise RuntimeError(f"{name}: exit {code}")
        return stdout

    def shell(self, name, text, container=CORE):
        return self.cmd(name, ["docker", "exec", container, "sh", "-lc", text])

    def neutralize(self):
        errors = []
        for name, argv in (
            ("resume-upf", ["docker", "exec", CORE, "sh", "-lc", 'pid=$(pgrep -x open5gs-upfd); test -n "$pid" && kill -CONT "$pid"']),
            ("clear-qdisc", ["docker", "exec", UE, "tc", "qdisc", "replace", "dev", "uesimtun0", "root", "fq_codel"]),
        ):
            try:
                self.cmd(name, argv)
            except Exception as exc:
                errors.append(str(exc))
        if errors:
            raise RuntimeError("; ".join(errors))

    def window(self, label):
        samples = []
        for index in range(3):
            at = now()
            first = self.sequence + 1
            ping = self.cmd("service-ping", ["docker", "exec", UE, "ping", "-I", "uesimtun0", "-c", "5", "-i", "0.2", "-W", "1", "10.45.0.1"], (0, 1))
            metrics = {key: value[0] for key, value in parse_ping(ping).items()}
            qdisc = self.cmd("qdisc", ["docker", "exec", UE, "tc", "qdisc", "show", "dev", "uesimtun0"])
            state = self.shell("upf-state", 'pid=$(pgrep -x open5gs-upfd); ps -o stat= -p "$pid"').strip()
            workers = self.shell("stress-workers", "pgrep -x yes || true").splitlines()
            targets = json.loads(self.cmd("targets", ["docker", "exec", CORE, "curl", "--fail", "--silent", "http://10.53.0.6:9090/api/v1/targets"]))["data"]["activeTargets"]
            metrics.update(configured_packet_loss_pct=0.0 if "fq_codel" in qdisc and "loss" not in qdisc else None,
                           upf_process_running=1.0 if state and "T" not in state else 0.0,
                           stress_workers_count=len(workers),
                           prometheus_targets_up_count=sum(t["health"] == "up" for t in targets)
                           if {t["labels"]["job"] for t in targets} == {"open5gs-amf", "open5gs-smf", "open5gs-upf"} else -1)
            samples.append({"observed_at": at, "metrics": metrics,
                            "command_sequences": list(range(first, self.sequence + 1))})
            # Persist every completed sample even if a later command fails.
            with (self.output / "samples.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps({"trial_id": self.unit_id, "window": label,
                                         "index": index, **samples[-1]}, sort_keys=True) + "\n")
            time.sleep(0.5)
        return samples

    def restart(self, containers):
        for container in containers:
            if container not in (CORE, GNB, UE):
                raise ValueError("container outside pilot scope")
            self.cmd("restart-" + container, ["docker", "restart", container])
            until = time.monotonic() + self.config["maximum_container_health_seconds"]
            while True:
                health = self.cmd("health-" + container, ["docker", "inspect", "--format", "{{.State.Health.Status}}", container]).strip()
                if health == "healthy":
                    break
                if time.monotonic() >= until:
                    raise TimeoutError("container health timeout: " + container)
                time.sleep(2)

    def recovery(self):
        attempts = []
        for step in self.config["recovery_order"]:
            started = time.monotonic()
            row = {"step": step, "started_at": now(), "errors": []}
            try:
                if step == "primitive_cleanup":
                    self.neutralize()
                elif step == "ue_restart":
                    self.restart([UE])
                elif step == "core_gnb_ue_restart":
                    self.restart([CORE, GNB, UE])
                else:
                    raise ValueError("unknown recovery step")
                row["samples"] = self.window(step)
                row["clean"] = samples_clean(row["samples"])
            except Exception as exc:
                row["errors"].append(f"{type(exc).__name__}: {exc}")
                row["clean"] = False
            row.update(completed_at=now(), elapsed_seconds=time.monotonic() - started)
            attempts.append(row)
            if row["clean"]:
                break
        return attempts


    def arm_watchdog(self, pid):
        marker = "/tmp/safetwin-recovery-" + uuid.uuid4().hex
        # A unique marker and a completion barrier prevent late CONT in a later trial.
        start_ticks = int(self.shell("upf-start-ticks", f"cut -d ' ' -f22 /proc/{pid}/stat").strip())
        self.shell("resume-watchdog", f"touch {marker}.armed; "
                   f"(sleep 65; if [ -f {marker}.armed ] && "
                   f"[ \"$(cut -d ' ' -f22 /proc/{pid}/stat 2>/dev/null)\" = '{start_ticks}' ]; "
                   f"then kill -CONT {pid}; echo fired > {marker}.done; "
                   f"else echo disarmed > {marker}.done; fi) </dev/null >/dev/null 2>&1 & echo $!")
        return {"marker": marker, "armed_monotonic": time.monotonic()}

    def settle_watchdog(self, watchdog):
        marker = watchdog["marker"]
        self.shell("disarm-watchdog", f"mv {marker}.armed {marker}.disarmed")
        # Do not restart the core or enter the next trial until the helper has exited.
        until = watchdog["armed_monotonic"] + 80
        while True:
            state = self.shell("watchdog-barrier", f"if [ -f {marker}.done ]; then cat {marker}.done; fi").strip()
            if state:
                if state != "disarmed":
                    raise RuntimeError("watchdog fired; assigned hold not established")
                return state
            if time.monotonic() >= until:
                raise TimeoutError("watchdog completion not established")
            time.sleep(2)


def run_trial(backend, trial, approval):
    uid = trial["trial_id"]
    if (approval.get("status") != "approved" or approval.get("environment") != "sandbox"
            or uid not in approval.get("trial_ids", [])
            or set(approval.get("containers", [])) != {CORE, GNB, UE}
            or approval.get("trial_holds", {}).get(uid) != trial["hold_seconds"]
            or not approval.get("rollback_plan")
            or trial["hold_seconds"] not in backend.config["trial_hold_seconds"]):
        raise PermissionError("approved sandbox trial required")
    backend.unit_id = uid
    row = {"trial": trial, "approval_id": approval["approval_id"], "started_at": now(), "errors": []}
    started = time.monotonic()
    fault_started = None
    watchdog = None
    try:
        if time.monotonic() >= backend.deadline:
            raise TimeoutError("pilot wall-time budget reached")
        backend.neutralize()
        row["baseline"] = backend.window("baseline")
        if not samples_clean(row["baseline"]):
            raise RuntimeError("invalid service baseline blocks injection")
        hold = trial["hold_seconds"]
        if hold:
            if time.monotonic() + 100 >= backend.deadline:
                raise TimeoutError("insufficient time for bounded fault and watchdog")
            pid = int(backend.shell("locate-upf", "pgrep -x open5gs-upfd").strip())
            watchdog = backend.arm_watchdog(pid)
            fault_started = time.monotonic()
            row["stop_command_started_at"] = now()
            backend.cmd("suspend-upf", ["docker", "exec", CORE, "kill", "-STOP", str(pid)])
            suspended = time.monotonic()
            state = backend.shell("verify-stopped-upf", f"ps -o stat= -p {pid}").strip()
            row["fault_state_verified"] = "T" in state
            if not row["fault_state_verified"]:
                raise RuntimeError("UPF was not stopped")
            time.sleep(max(0, hold - (time.monotonic() - suspended)))
        else:
            row["fault_state_verified"] = True
    except BaseException as exc:
        row["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        backend.restoring = True
        # CONT is the first rollback operation, even after the admission deadline.
        try:
            if fault_started is not None:
                backend.cmd("primary-resume-upf", ["docker", "exec", CORE, "kill", "-CONT", str(pid)])
                row["cont_command_completed_at"] = now()
                row["stop_to_cont_command_window_seconds"] = time.monotonic() - fault_started
            backend.neutralize()
        except Exception as exc:
            row["errors"].append("rollback: " + str(exc))
        if watchdog:
            try:
                row["watchdog_terminal_state"] = backend.settle_watchdog(watchdog)
            except Exception as exc:
                row["errors"].append("watchdog: " + str(exc))
        row["recovery_attempts"] = backend.recovery()
        backend.restoring = False
    final = row["recovery_attempts"][-1]
    row["recovery_clean"] = final["clean"]
    row["passed"] = bool(not row["errors"] and row.get("fault_state_verified")
                         and samples_clean(row.get("baseline", [])) and final["clean"]
                         and (trial["hold_seconds"] > 0 or final["step"] == "primitive_cleanup"))
    row.update(completed_at=now(), elapsed_seconds=time.monotonic() - started)
    return row


def main():
    config = json.loads(CONFIG.read_text())
    validate_config(config, json.loads((ROOT / "config/actions.json").read_text()))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output = ROOT / "evidence" / "engineering" / (stamp + "-recovery-pilot-r1")
    output.mkdir(parents=True, exist_ok=False)
    trials = [{"trial_id": config["experiment_id"] + f"-{i:02d}", "hold_seconds": value}
              for i, value in enumerate(config["trial_hold_seconds"], 1)]
    approval = {
        "approval_id": hashlib.sha256((config["experiment_id"] + sha(CONFIG)).encode()).hexdigest(),
        "status": "approved", "environment": "sandbox", "recorded_at": now(),
        "approved_by": "user", "type": "standing-project-authorization",
        "authorization_basis": "User authorized all local SafeTwin implementation and reversible sandbox work, then requested SafeTwin continue karo on 2026-09-05.",
        "trial_ids": [t["trial_id"] for t in trials], "containers": [CORE, GNB, UE],
        "trial_holds": {t["trial_id"]: t["hold_seconds"] for t in trials},
        "operations": ["UPF STOP/CONT", "bounded CONT watchdog", "neutralize qdisc", "UE restart", "Open5GS/gNB/UE dependency-order restart"],
        "rollback_plan": "Always CONT and neutralize qdisc; settle watchdog; verify three service samples; escalate UE then full dependency-order restart; abort if clean service is not restored.",
        "excluded": ["live actuation", "hardware", "operator systems", "unrelated containers", "publication"],
    }
    sources = {name: source_sha(ROOT / name) for name in (
        "sandbox/run_recovery_pilot.py", "config/experiments/recovery-pilot-r1.json",
        "docs/RECOVERY_PILOT_R1_PROTOCOL.md", "src/safetwin5g/phase7_runner.py",
        "sandbox/versions.lock.json", "sandbox/compose.yaml", "config/actions.json",
        "tools/audit_recovery_pilot.py")}
    for name, value in (("approval.json", approval), ("design.json", {"config": config, "trials": trials, "source_sha256": sources, "source_hash_mode": "utf8-lf-normalized"})):
        (output / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    backend = Backend(output, config)
    rows = []
    errors = []
    try:
        backend.cmd("git-head", ["git", "rev-parse", "HEAD"])
        backend.cmd("docker-server", ["docker", "version", "--format", "{{json .Server}}"])
        network = json.loads(backend.cmd("isolated-network", ["docker", "network", "inspect", NETWORK]))[0]
        containers = json.loads(backend.cmd("container-identities", ["docker", "inspect", *CONTAINERS]))
        validate_environment(network, containers, json.loads((ROOT / "sandbox/versions.lock.json").read_text())["components"])
        for i, trial in enumerate(trials, 1):
            print(f"[{i}/{len(trials)}] {trial['trial_id']} hold={trial['hold_seconds']}s", flush=True)
            row = run_trial(backend, trial, approval)
            rows.append(row)
            (output / f"trial-{i:02d}.json").write_text(json.dumps(row, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            backend.restoring = True
            for container in (CORE, GNB, UE):
                backend.cmd("trial-log-" + container, ["docker", "logs", "--since", row["started_at"], "--tail", "500", container])
            backend.cmd("trial-ue-address", ["docker", "exec", UE, "ip", "-j", "addr", "show", "dev", "uesimtun0"])
            backend.restoring = False
            print(f"trial_passed={row['passed']} final_recovery={row['recovery_attempts'][-1]['step']}", flush=True)
            if not row["passed"]:
                break
    except BaseException as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    summary = {"experiment_id": config["experiment_id"], "completed_at": now(),
               "planned_trials": len(trials), "completed_trials": len(rows),
               "passed": not errors and len(rows) == len(trials) and all(r["passed"] for r in rows),
               "errors": errors,
               "admission_budget_exceeded": time.monotonic() > backend.deadline,
               "final_service_restored": bool(rows and rows[-1]["recovery_clean"]),
               "evidence_label": "sandbox-measured", "radio_evidence_label": "simulated",
               "confirmatory_data": False, "long_campaign_ready": False,
               "hardware_measured": False, "operator_validated": False,
               "live_actuation": False, "TNSM_ready": False}
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    captured = {p.name: sha(p) for p in output.iterdir() if p.is_file()}
    (output / "manifest.json").write_text(json.dumps({"captured_file_sha256": captured}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output, flush=True)
    print(json.dumps(summary), flush=True)
    return 0 if summary["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
