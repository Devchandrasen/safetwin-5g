"""Frozen, bounded instrumentation diagnostic with explicit official rollback."""
from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sandbox.reconnect_r3_measurement import (CORE, GNB, UE, CONTAINERS, NETWORK, HOST_FIELDS, INSPECT_FORMAT,
    ping_argv, ping_result, log_text, trace_result, state_metrics, clean)
from sandbox.run_reconnect import FAULT_SCRIPT, noqueue
from sandbox.run_recovery_pilot import validate_environment

BASE = ["docker", "compose", "-f", "sandbox/compose.yaml"]
DERIVED = BASE + ["-f", "sandbox/compose.reconnect-r3.yaml"]
UP = ["up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "ueransim-gnb", "ueransim-ue"]
CONFIG_PATH = ROOT / "config/experiments/reconnect-r3-trace.json"
IMAGE_PATH = ROOT / "config/experiments/reconnect-r3-images.json"
LOCK_PATH = ROOT / "config/experiments/reconnect-r3-execution-lock.json"


def now(): return datetime.now(timezone.utc).isoformat()
def sha(data): return hashlib.sha256(data).hexdigest()
def save(path, value): path.write_bytes((json.dumps(value, indent=2) + "\n").encode())


def validate_approval(approval, config, images):
    expected = {"status": "approved", "environment": "sandbox", "type": "standing-project-authorization",
                "trials": config["trials"], "containers": [CORE, GNB, UE], "image_containers": [GNB, UE],
                "image_ids": [images["official_image_id"], images["derived_image_id"]],
                "operator_validation": False, "live_actuation": False}
    if any(approval.get(k) != v for k, v in expected.items()) or not approval.get("rollback_plan"):
        raise PermissionError("exact R3 sandbox approval required")


def verify_execution_lock():
    lock = json.loads(LOCK_PATH.read_bytes())
    for name, digest in lock["source_sha256"].items():
        path = (ROOT / name).resolve()
        if not path.is_relative_to(ROOT) or sha(path.read_bytes()) != digest:
            raise PermissionError("frozen execution source drift: " + name)
        committed = subprocess.run(["git", "show", "HEAD:" + name], cwd=ROOT, capture_output=True, timeout=15)
        if committed.returncode or sha(committed.stdout) != digest:
            raise PermissionError("execution source not committed: " + name)
    committed = subprocess.run(["git", "show", "HEAD:" + LOCK_PATH.relative_to(ROOT).as_posix()], cwd=ROOT, capture_output=True, timeout=15)
    if committed.returncode or committed.stdout != LOCK_PATH.read_bytes(): raise PermissionError("execution lock not committed")
    return lock


def verify_fault(text):
    lines = text.splitlines()
    if len(lines) != 4: raise ValueError("incomplete fault/trap transcript")
    elapsed = (datetime.fromisoformat(lines[2]) - datetime.fromisoformat(lines[0])).total_seconds()
    during, after = json.loads(lines[1]), json.loads(lines[3])
    if not (8 <= elapsed < 15 and len(during) == 1 and during[0].get("kind") == "netem"
            and during[0].get("handle") == "7157:" and during[0].get("root") is True
            and during[0]["options"]["loss-random"]["loss"] == 1 and noqueue(after)):
        raise ValueError("fault exposure or trap cleanup not verified")


class R3Backend:
    def __init__(self, output, config, images, approval, clock=None):
        self.output, self.config, self.images, self.approval = Path(output), config, images, approval
        self.now = clock.now if clock else now
        self.monotonic = clock.monotonic if clock else time.monotonic
        self.sleep = clock.sleep if clock else time.sleep
        self.deadline = self.monotonic() + 1500
        self.sequence, self.identifier = 0, 10001
        self.unit_id, self.role = "preflight", "official"
        self.restoring, self.candidate_touched, self.authorized = False, False, False
        self.reference = None

    def invoke(self, argv, merged):
        return subprocess.run(argv, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT if merged else subprocess.PIPE, timeout=35)

    def cmd(self, name, argv, accepted=(0,), merged=False):
        if not self.restoring and self.monotonic() >= self.deadline: raise TimeoutError("admission budget exhausted")
        mutation = argv[:2] == ["docker", "restart"] or (argv[:2] == ["docker", "compose"] and "up" in argv) or name in ("bounded-link-drop", "emergency-clear-owned-qdisc")
        if mutation:
            validate_approval(self.approval, self.config, self.images)
            if not self.authorized: raise PermissionError("preflight has not enabled scoped mutations")
        self.sequence += 1
        row = {"sequence": self.sequence, "unit_id": self.unit_id, "name": name, "argv": argv,
               "started_at": self.now(), "timeout_seconds": 35, "merged_streams": merged}
        try:
            result = self.invoke(argv, merged)
            code, stdout, stderr = result.returncode, result.stdout or b"", result.stderr or b""
        except subprocess.TimeoutExpired as exc:
            code, stdout, stderr = -999, exc.stdout or b"", (exc.stderr or b"") + b"\nBOUNDED_COMMAND_TIMEOUT"
        row.update(completed_at=self.now(), returncode=code, accepted_returncodes=list(accepted),
                   stdout=stdout.decode("utf-8", "strict"), stderr=stderr.decode("utf-8", "strict"),
                   stdout_sha256=sha(stdout), stderr_sha256=sha(stderr))
        with (self.output / "commands.jsonl").open("ab") as stream:
            stream.write((json.dumps(row) + "\n").encode())
        if code not in accepted: raise RuntimeError(name + ": exit " + str(code))
        return row["stdout"]

    def eth0(self, label):
        return json.loads(self.cmd(label, ["docker", "exec", UE, "tc", "-j", "qdisc", "show", "dev", "eth0"]))

    def clear_owned_fault(self):
        state = self.eth0("rollback-inspect-eth0")
        if noqueue(state): return
        if len(state) != 1 or state[0].get("kind") != "netem" or state[0].get("handle") != "7157:":
            raise PermissionError("unknown qdisc: will not delete it")
        self.cmd("emergency-clear-owned-qdisc", ["docker", "exec", UE, "tc", "qdisc", "del", "dev", "eth0", "root", "handle", "7157:"])
        if not noqueue(self.eth0("rollback-verify-eth0")): raise RuntimeError("owned qdisc remains")

    def scope(self, role, label):
        network = json.loads(self.cmd(label + "-network", ["docker", "network", "inspect", NETWORK]))[0]
        text = self.cmd(label + "-containers", ["docker", "inspect", "--format", INSPECT_FORMAT, *CONTAINERS])
        containers = [json.loads(line) for line in text.splitlines()]
        validate_environment(network, containers, json.loads((ROOT / "sandbox/versions.lock.json").read_bytes())["components"])
        current = {row["Name"].lstrip("/"): row for row in containers}
        for name, row in current.items():
            hc = row["HostConfig"]
            caps = {"NET_ADMIN", "NET_RAW"} if name in (CORE, UE) else set()
            if set(hc.get("CapAdd") or []) != caps or hc.get("CapDrop") or hc.get("PidMode") or hc.get("Privileged") or hc.get("PortBindings"):
                raise PermissionError("capability/namespace scope")
            devices = [{"PathOnHost": "/dev/net/tun", "PathInContainer": "/dev/net/tun", "CgroupPermissions": "rwm"}] if name in (CORE, UE) else []
            if (hc.get("Devices") or []) != devices: raise PermissionError("device scope")
            if name in (GNB, UE):
                if row["Image"] != self.images[role + "_image_id"]: raise PermissionError("both UERANSIM image IDs must match")
                if role == "derived" and row["Config"]["Labels"].get("safetwin5g.derived.revision") != "reconnect-r3-trace": raise PermissionError("R3 revision missing")
                component = "gnb" if name == GNB else "ue"
                if len(row["Mounts"]) != 1: raise PermissionError("UERANSIM mount count")
                mount = row["Mounts"][0]
                if mount["RW"] or mount["Destination"] != f"/etc/ueransim/{component}.yaml" or Path(mount["Source"]).resolve() != (ROOT / f"sandbox/config/ueransim/{component}.yaml").resolve():
                    raise PermissionError("UERANSIM mount source/destination")
                if row["Config"]["Cmd"] != [f"/opt/ueransim/bin/nr-{component}", "-c", f"/etc/ueransim/{component}.yaml"]:
                    raise PermissionError("UERANSIM command drift")
        if self.reference is None:
            if role != "official": raise PermissionError("official baseline reference required")
            self.reference = current
        for name, row in current.items():
            original = self.reference[name]
            if name not in (GNB, UE) and row["Image"] != original["Image"]: raise PermissionError("other component image changed")
            mounts = lambda data: sorted(data["Mounts"], key=lambda m: m["Destination"])
            if (mounts(row) != mounts(original) or any(row["HostConfig"].get(k) != original["HostConfig"].get(k) for k in HOST_FIELDS)
                    or any(row["Config"].get(k) != original["Config"].get(k) for k in ("Cmd", "Entrypoint", "User", "WorkingDir"))):
                raise PermissionError("container execution scope changed")
        return containers

    def preflight(self):
        self.cmd("repository-head", ["git", "rev-parse", "HEAD"])
        self.cmd("docker-version", ["docker", "version", "--format", "{{json .Server}}"])
        original = json.loads(self.cmd("compose-base", BASE + ["config", "--format", "json"]))
        modified = json.loads(self.cmd("compose-derived", DERIVED + ["config", "--format", "json"]))
        for service in ("ueransim-gnb", "ueransim-ue"):
            if modified["services"][service]["image"] != self.images["derived_tag"]: raise PermissionError("override image mismatch")
            modified["services"][service]["image"] = original["services"][service]["image"]
        if original != modified: raise PermissionError("override changes more than two images")
        for role in ("official", "derived"):
            image = self.cmd(role + "-image", ["docker", "image", "inspect", "--format", "{{.Id}}", self.images[role + "_tag"]]).strip()
            if image != self.images[role + "_image_id"]: raise PermissionError("image tag drift")
        self.scope("official", "preflight")
        if not noqueue(self.eth0("preflight-eth0")): raise PermissionError("pre-existing fault blocks preparation")
        help_text = self.cmd("ping-help", ["docker", "exec", UE, "ping", "-h"], (0, 2), merged=True)
        if "-e <identifier>" not in help_text: raise PermissionError("explicit ICMP identifier unsupported")

    def health(self, container):
        until = self.monotonic() + 50
        while self.cmd("health-" + container, ["docker", "inspect", "--format", "{{.State.Health.Status}}", container]).strip() != "healthy":
            if self.monotonic() >= until: raise TimeoutError("health wait exhausted: " + container)
            self.sleep(2)

    def restart(self, containers):
        for container in containers:
            if container not in (CORE, GNB, UE): raise PermissionError("restart outside exact scope")
            self.cmd("restart-" + container, ["docker", "restart", container]); self.health(container)

    def switch(self, role):
        validate_approval(self.approval, self.config, self.images)
        if role not in ("official", "derived"): raise PermissionError("unknown image role")
        image = self.cmd("switch-" + role + "-image", ["docker", "image", "inspect", "--format", "{{.Id}}", self.images[role + "_tag"]]).strip()
        if image != self.images[role + "_image_id"]: raise PermissionError("replacement tag drift")
        if role == "derived": self.candidate_touched = True
        self.cmd("switch-" + role, (DERIVED if role == "derived" else BASE) + UP)
        self.role = role
        for container in (GNB, UE): self.health(container)
        self.scope(role, "switch-" + role + "-verified")

    def logs(self, label, since, until=None):
        until = until or self.now()
        result = {}
        for container in (CORE, GNB, UE):
            raw = self.cmd(label + "-" + container, ["docker", "logs", "--timestamps", "--since", since, "--until", until, "--tail", "2000", container], merged=True)
            result[container] = log_text(raw, since, until)
        return result

    def window(self, label):
        samples = []
        for index in range(3):
            identifier = self.identifier
            argv = ping_argv(identifier)  # reserve before any command, no reuse after errors
            self.identifier += 1
            sample = {"unit_id": self.unit_id, "window": label, "index": index, "identifier": identifier,
                      "started_at": self.now(), "command_first": self.sequence + 1, "metrics": {}, "errors": [], "trace": None}
            try:
                sample["metrics"] = ping_result(self.cmd("service-ping", argv, (0, 1)))
                qdisc = self.cmd("sample-qdisc", ["docker", "exec", UE, "tc", "-j", "qdisc", "show", "dev", "uesimtun0"])
                state = self.cmd("upf-state", ["docker", "exec", CORE, "sh", "-lc", 'pid=$(pgrep -x open5gs-upfd); ps -o stat= -p "$pid"'])
                workers = self.cmd("stress-workers", ["docker", "exec", CORE, "sh", "-lc", "pgrep -x yes || true"])
                targets = self.cmd("targets", ["docker", "exec", CORE, "curl", "--fail", "--silent", "http://10.53.0.6:9090/api/v1/targets"])
                sample["metrics"].update(state_metrics(qdisc, state, workers, targets))
                sample["capture_until"] = self.now()
                captured = []
                for container in (UE, GNB):
                    captured.append(self.cmd("trace-" + container, ["docker", "logs", "--timestamps", "--since", sample["started_at"], "--until", sample["capture_until"], "--tail", "2000", container], merged=True))
                if self.role == "derived":
                    sample["trace"] = trace_result(*captured, sample["started_at"], sample["capture_until"], identifier, sample["metrics"]["reply_sequences"])
                else:
                    for text in captured:
                        if "ST3" in log_text(text, sample["started_at"], sample["capture_until"]): raise ValueError("trace remains after official rollback")
            except Exception as exc:
                sample["errors"].append(f"{type(exc).__name__}: {exc}")
                raise
            finally:
                sample.update(completed_at=self.now(), command_last=self.sequence)
                with (self.output / "samples.jsonl").open("ab") as stream: stream.write((json.dumps(sample) + "\n").encode())
            samples.append(sample)
        return samples

    def restore(self):
        attempts = []
        for step, containers in (("restore-ue", [UE]), ("restore-full", [CORE, GNB, UE])):
            row = {"step": step, "started_at": self.now(), "errors": [], "clean": False}
            try:
                self.restart(containers)
                row["samples"] = self.window(step)
                logs = self.logs(step, row["started_at"])
                row["fresh_registration"] = "Initial Registration is successful" in logs[UE]
                row["fresh_pdu"] = "PDU Session establishment is successful" in logs[UE]
                row["clean"] = clean(row["samples"]) and noqueue(self.eth0(step + "-eth0")) and row["fresh_registration"] and row["fresh_pdu"]
            except Exception as exc: row["errors"].append(str(exc))
            row["completed_at"] = self.now(); attempts.append(row)
            if row["clean"]: break
        return attempts

    def final_rollback(self):
        self.restoring, self.unit_id = True, "final-rollback"
        row = {"started_at": self.now(), "errors": [], "official_image_restored": False, "service_restored": False}
        try: self.clear_owned_fault()
        except BaseException as exc: row["errors"].append("qdisc: " + str(exc))
        try:
            if self.candidate_touched: self.switch("official")
        except BaseException as exc: row["errors"].append("image: " + str(exc))
        # A failed cleanup/switch must not suppress a separately attempted reset.
        try:
            self.restart([CORE, GNB, UE])
            row["samples"] = self.window("final-official")
            logs = self.logs("final-official", row["started_at"])
            self.scope("official", "final-official")
            row["official_image_restored"] = True
            row["fresh_registration"] = "Initial Registration is successful" in logs[UE]
            row["fresh_pdu"] = "PDU Session establishment is successful" in logs[UE]
            row["service_restored"] = clean(row["samples"]) and noqueue(self.eth0("final-eth0")) and row["fresh_registration"] and row["fresh_pdu"]
        except BaseException as exc: row["errors"].append("service: " + str(exc))
        row["completed_at"] = self.now()
        return row


def run_trial(backend, trial):
    validate_approval(backend.approval, backend.config, backend.images)
    if trial not in backend.config["trials"]: raise PermissionError("trial not assigned")
    backend.unit_id = trial["trial_id"]
    row = {"trial": trial, "started_at": backend.now(), "errors": [], "restoration_attempts": [], "preparation_started": False}
    try:
        if backend.monotonic() + 180 > backend.deadline: raise TimeoutError("insufficient trial admission budget")
        backend.scope("derived", "trial-scope")
        if not noqueue(backend.eth0("preparation-eth0")): raise PermissionError("unknown fault before preparation")
        row["preparation_started"] = True
        backend.restart([CORE, GNB, UE])
        row["baseline"] = backend.window("baseline")
        prep = backend.logs("preparation", row["started_at"])
        row["fresh_registration"] = "Initial Registration is successful" in prep[UE]
        row["fresh_pdu"] = "PDU Session establishment is successful" in prep[UE]
        if not (clean(row["baseline"]) and row["fresh_registration"] and row["fresh_pdu"] and noqueue(backend.eth0("baseline-eth0"))):
            raise RuntimeError("invalid baseline blocks exposure")
        row["exposure_started_at"] = backend.now()
        if trial["drop_ue_egress"]:
            row["fault_transcript"] = backend.cmd("bounded-link-drop", ["docker", "exec", UE, "timeout", "15", "sh", "-lc", FAULT_SCRIPT])
            verify_fault(row["fault_transcript"])
        else: backend.cmd("control-wait", ["docker", "exec", UE, "sleep", "8"])
        row["exposure_completed_at"] = backend.now()
        if not noqueue(backend.eth0("post-exposure-eth0")): raise RuntimeError("exposure rollback not verified")
        row["settling_started_at"] = backend.now(); backend.sleep(5); row["settling_completed_at"] = backend.now()
        row["post"] = backend.window("post")
        logs = backend.logs("post", row["exposure_started_at"])
        row["service_accept_observed"] = "Service Accept received" in logs[UE]
        row["initial_context_observed"] = "Initial Context Setup Request received" in logs[GNB]
        row["trace_accounting_complete"] = all(sample["trace"]["trace_accounting_complete"] for sample in row["post"])
        row["recovery_15_of_15"] = clean(row["post"])
        if not trial["drop_ue_egress"] and (not row["recovery_15_of_15"] or "Radio link failure detected" in logs[UE]):
            raise RuntimeError("no-fault control failed")
    except BaseException as exc: row["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        backend.restoring = True
        try: backend.clear_owned_fault()
        except BaseException as exc: row["errors"].append("cleanup: " + str(exc))
        if row["preparation_started"] and (trial["drop_ue_egress"] or row["errors"]):
            row["restoration_attempts"] = backend.restore()
            row["final_service_restored"] = row["restoration_attempts"][-1]["clean"]
        else: row["final_service_restored"] = row.get("recovery_15_of_15", False)
        backend.restoring = False
    row["protocol_execution_valid"] = bool(not row["errors"] and row.get("trace_accounting_complete") and row["final_service_restored"])
    row["network_fix_validated"] = False
    row["completed_at"] = backend.now()
    return row


def approval_record(config, images, recorded_at):
    return {"approval_id": "reconnect-r3-" + sha(IMAGE_PATH.read_bytes()), "recorded_at": recorded_at,
            "status": "approved", "environment": "sandbox", "approved_by": "user", "type": "standing-project-authorization",
            "authorization_basis": "User authorized exact scoped reversible local SafeTwin work and automatic sequential continuation.",
            "trials": config["trials"], "containers": [CORE, GNB, UE], "image_containers": [GNB, UE],
            "image_ids": [images["official_image_id"], images["derived_image_id"]],
            "operations": ["fixed preparation core/gNB/UE resets", "two eight-second UE eth0 loss trials, owned 7157 handle, 15-second timeout/EXIT cleanup",
                           "UE restart then full reset restoration", "exact two-service derived/official image replacement"],
            "rollback_plan": "Remove only owned qdisc; attempt official image restoration for both UE and gNB after any switch attempt; reset core/gNB/UE and verify fresh registration/PDU plus 15/15.",
            "operator_validation": False, "live_actuation": False}


def execute(backend, save_result):
    rows, errors, rollback = [], [], {"official_image_restored": False, "service_restored": False, "errors": ["no image switch attempted"]}
    try:
        backend.preflight()
        backend.authorized = True
        backend.switch("derived")
        for i, trial in enumerate(backend.config["trials"], 1):
            row = run_trial(backend, trial); rows.append(row); save_result(f"trial-{i:02d}.json", row)
            if not row["protocol_execution_valid"]: break
    except BaseException as exc: errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        if backend.candidate_touched: rollback = backend.final_rollback()
        save_result("final-rollback.json", rollback)
    valid = bool(len(rows) == 4 and not errors and all(row["protocol_execution_valid"] for row in rows)
                 and rollback["official_image_restored"] and rollback["service_restored"] and not rollback["errors"]
                 and backend.monotonic() <= backend.deadline)
    summary = {"experiment_id": backend.config["experiment_id"], "completed_at": backend.now(), "completed_trials": len(rows),
               "protocol_execution_valid": valid, "errors": errors, "candidate_image_applied": backend.candidate_touched,
               "official_image_restored": rollback["official_image_restored"], "final_service_restored": rollback["service_restored"],
               "admission_budget_exceeded": backend.monotonic() > backend.deadline, "evidence_label": "sandbox-measured",
               "radio_evidence_label": "simulated", "network_fix_validated": False, "confirmatory_data": False,
               "long_campaign_ready": False, "TNSM_ready": False, "live_actuation": False, "operator_validated": False, "hardware_measured": False}
    save_result("summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser(); parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if not args.execute: raise SystemExit("No mutation by default. Use the separately audited preflight tool; --execute requires committed execution lock.")
    lock = verify_execution_lock()
    config, images = json.loads(CONFIG_PATH.read_bytes()), json.loads(IMAGE_PATH.read_bytes())
    policy = json.loads((ROOT / "config/actions.json").read_bytes())
    if policy["allow_live_actuation"] is not False or policy["require_human_approval"] is not True: raise PermissionError("fail-closed policy required")
    from tools.audit_reconnect_r3_build_v2 import audit
    if audit(ROOT / images["build_release"])["derived_image_id"] != images["derived_image_id"]: raise PermissionError("build gate drift")
    if any((ROOT / "evidence/engineering").glob("*-reconnect-r3-network")): raise PermissionError("an R3 attempt already exists; inspect it, never repeat automatically")
    guard = ROOT / "evidence/private/reconnect-r3-runtime.lock"
    guard.parent.mkdir(parents=True, exist_ok=True)
    guard_token = now().encode()
    with guard.open("xb") as stream: stream.write(guard_token)
    try:
        output = ROOT / "evidence/engineering" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r3-network")
        output.mkdir(parents=True, exist_ok=False)
        approval = approval_record(config, images, now())
        save(output / "approval.json", approval)
        save(output / "design.json", {"config": config, "images": images, "source_sha256": lock["source_sha256"], "execution_mode": "sandbox"})
        backend = R3Backend(output, config, images, approval)
        result = execute(backend, lambda name, value: save(output / name, value))
        save(output / "manifest.json", {"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}})
        print(output); print(json.dumps(result, indent=2))
        return 0 if result["protocol_execution_valid"] else 2
    finally:
        if guard.exists() and guard.read_bytes() == guard_token: guard.unlink()


if __name__ == "__main__": raise SystemExit(main())
