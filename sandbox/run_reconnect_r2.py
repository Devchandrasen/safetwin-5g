"""Execute the frozen official/derived comparison and restore the official image."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sandbox.run_reconnect import ReconnectBackend, run_trial, noqueue
from sandbox.run_recovery_pilot import CORE, GNB, UE, CONTAINERS, NETWORK, now, sha, source_sha, samples_clean, validate_environment
from tools.audit_reconnect_r2_build import audit as audit_build

LOCK = ROOT / "config/experiments/reconnect-r2-images.json"
BASE = "sandbox/compose.yaml"
OVERRIDE = "sandbox/compose.reconnect-r2.yaml"
ORDER = ["control-before", "drop-a", "drop-b", "control-after"]
HOST_FIELDS = ("CapAdd", "CapDrop", "Devices", "Sysctls", "Binds", "SecurityOpt", "Privileged", "PortBindings", "NetworkMode", "PidMode", "IpcMode", "ReadonlyRootfs")


def trials():
    return [{"trial_id": role + ":" + name, "drop_ue_egress": name.startswith("drop-")} for role in ("official", "derived") for name in ORDER]


def candidate_recovery(row, logs):
    ue, gnb = logs.get(UE, ""), logs.get(GNB, "")
    return bool(row["protocol_execution_valid"] and row["trial"]["drop_ue_egress"] and
                row["automatic_service_recovered"] and "Radio link failure detected" in ue and
                "Sending Service Request" in ue and "Service Accept received" in ue and
                ue.index("Radio link failure detected") < ue.index("Sending Service Request") < ue.index("Service Accept received") and
                "Initial Context Setup Request received" in gnb and
                "failed. Could not find a suitable AMF." not in gnb)


def stop_reason(row):
    if not row["protocol_execution_valid"]:
        return "invalid_trial"
    if row["trial"]["drop_ue_egress"]:
        if row["role"] == "official" and not row["reconnect_failure_reproduced"]:
            return "official_failure_not_reproduced"
        if row["role"] == "derived" and not row["candidate_recovery_verified"]:
            return "candidate_recovery_not_verified"
    return None


def validate_switch_approval(approval, role, images):
    if (role not in ("official", "derived") or approval.get("status") != "approved"
            or approval.get("environment") != "sandbox" or approval.get("image_container") != GNB
            or approval.get("image_ids") != [images["official_image_id"], images["derived_image_id"]]
            or not approval.get("rollback_plan")):
        raise PermissionError("image-scoped approval required")


class R2Backend(ReconnectBackend):
    def __init__(self, output, config, images, approval):
        super().__init__(output, config)
        self.images, self.approval = images, approval
        self.reference = None
        self.post_logs = {}
        self.candidate_touched = False

    def logs(self, label, since):
        result = super().logs(label, since)
        if label == "post":
            self.post_logs[self.unit_id] = result
        return result

    def scope(self, role, label):
        network = json.loads(self.cmd(label + "-network", ["docker", "network", "inspect", NETWORK]))[0]
        containers = json.loads(self.cmd(label + "-containers", ["docker", "inspect", *CONTAINERS]))
        validate_environment(network, containers, json.loads((ROOT / "sandbox/versions.lock.json").read_text())["components"])
        current = {c["Name"].lstrip("/"): c for c in containers}
        gnb = current[GNB]
        if (gnb["HostConfig"].get("CapAdd") or gnb["HostConfig"].get("Devices") or
                len(gnb["Mounts"]) != 1 or gnb["Mounts"][0]["RW"] or
                gnb["Mounts"][0]["Destination"] != "/etc/ueransim/gnb.yaml" or
                Path(gnb["Mounts"][0]["Source"]).resolve() != (ROOT / "sandbox/config/ueransim/gnb.yaml").resolve()):
            raise PermissionError("gNB attachment scope mismatch")
        if current[GNB]["Image"] != self.images[role + "_image_id"] or current[UE]["Image"] != self.images["official_image_id"]:
            raise PermissionError("selected image identity mismatch")
        if role == "derived" and current[GNB]["Config"]["Labels"].get("safetwin5g.derived.revision") != "reconnect-r2":
            raise PermissionError("derived label missing")
        if self.reference is None:
            if role != "official":
                raise PermissionError("official reference required")
            self.reference = current
        for name, container in current.items():
            original = self.reference[name]
            if name != GNB and container["Image"] != original["Image"]:
                raise PermissionError("unapproved component image change")
            if (container["Mounts"] != original["Mounts"] or
                    any(container["HostConfig"].get(k) != original["HostConfig"].get(k) for k in HOST_FIELDS) or
                    any(container["Config"].get(k) != original["Config"].get(k) for k in ("Cmd", "Entrypoint", "User", "WorkingDir"))):
                raise PermissionError("container execution scope changed")
        return containers

    def switch(self, role):
        validate_switch_approval(self.approval, role, self.images)
        image = json.loads(self.cmd("switch-" + role + "-image", ["docker", "image", "inspect", self.images[role + "_tag"]]))[0]
        if image["Id"] != self.images[role + "_image_id"]:
            raise PermissionError("image tag drift blocks replacement")
        args = ["docker", "compose", "-f", BASE]
        if role == "derived":
            args += ["-f", OVERRIDE]
            # Set BEFORE the command so interruption/failure also rolls back.
            self.candidate_touched = True
        self.cmd("switch-" + role, args + ["up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "ueransim-gnb"])
        until = time.monotonic() + 50
        while self.cmd("switch-health", ["docker", "inspect", "--format", "{{.State.Health.Status}}", GNB]).strip() != "healthy":
            if time.monotonic() >= until:
                raise TimeoutError("replacement gNB health timeout")
            time.sleep(2)
        self.scope(role, "switch-" + role + "-verified")

    def final_rollback(self):
        self.restoring, self.unit_id = True, "final-rollback"
        row = {"started_at": now(), "errors": [], "official_image_restored": False, "service_restored": False}
        try:
            self.clear_owned_fault()
        except BaseException as exc:
            # A cleanup failure must not suppress official-image restoration.
            row["errors"].append(f"cleanup: {type(exc).__name__}: {exc}")
        try:
            if self.candidate_touched:
                self.switch("official")
            self.restart([CORE, GNB, UE])
            row["samples"] = self.window("final-official")
            logs = self.logs("final-official", row["started_at"])
            row["fresh_registration"] = "Initial Registration is successful" in logs[UE]
            row["fresh_pdu"] = "PDU Session establishment is successful" in logs[UE]
            self.scope("official", "final-official")
            row["official_image_restored"] = True
            row["service_restored"] = bool(samples_clean(row["samples"]) and noqueue(self.eth0("final-eth0")) and row["fresh_registration"] and row["fresh_pdu"])
        except BaseException as exc:
            row["errors"].append(f"{type(exc).__name__}: {exc}")
        row["completed_at"] = now()
        return row


def main():
    images = json.loads(LOCK.read_text())
    build = audit_build(ROOT / images["build_run"])
    if build["derived_image_id"] != images["derived_image_id"] or build["patch_sha256"] != images["patch_sha256"]:
        raise PermissionError("audited build does not match execution lock")
    policy = json.loads((ROOT / "config/actions.json").read_text())
    if policy["allow_live_actuation"] is not False or policy["require_human_approval"] is not True:
        raise PermissionError("fail-closed sandbox policy required")
    output = ROOT / "evidence/engineering" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r2")
    output.mkdir(parents=True, exist_ok=False)
    def save(name, value):
        (output / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    config = json.loads((ROOT / "config/experiments/reconnect-r1.json").read_text()) | {"experiment_id": "safetwin5g-reconnect-engineering-r2", "maximum_total_seconds": 1500, "trials": trials()}
    approval = {"approval_id": "reconnect-r2-" + sha(LOCK), "recorded_at": now(), "status": "approved", "environment": "sandbox",
                "approved_by": "user", "type": "standing-project-authorization", "operator_validation": False,
                "authorization_basis": "User authorized scoped reversible local SafeTwin work and automatic sequential continuation.",
                "trials": trials(), "containers": [CORE, GNB, UE], "image_container": GNB,
                "image_ids": [images["official_image_id"], images["derived_image_id"]],
                "operations": ["fixed preparation core/gNB/UE restarts", "eight-second UE eth0 loss with handle 7157 and bounded EXIT rollback", "UE restart then full reset restoration", "gNB-only derived/official image replacement via scoped Compose override"],
                "rollback_plan": "Remove exact owned qdisc; restore official gNB image after any candidate attempt, restart core/gNB/UE and verify registration/PDU plus 15/15 packets.", "live_actuation": False}
    sources = {name: source_sha(ROOT / name) for name in ("sandbox/run_reconnect_r2.py", "sandbox/run_reconnect.py", "sandbox/run_recovery_pilot.py", "tools/audit_reconnect_r2.py", "tools/audit_recovery_pilot.py", "tools/audit_reconnect.py", "docs/RECONNECT_R2_PROTOCOL.md", "docs/RECONNECT_R2_EXECUTION.md", "config/experiments/reconnect-r2-images.json", "config/experiments/reconnect-r1.json", "sandbox/compose.yaml", OVERRIDE, "sandbox/versions.lock.json", "config/actions.json", "src/safetwin5g/phase7_runner.py")}
    save("approval.json", approval)
    save("design.json", {"config": config, "images": images, "source_sha256": sources, "source_hash_mode": "utf8-lf-normalized"})
    backend = R2Backend(output, config, images, approval)
    rows, errors, reason, mutations_started = [], [], None, False
    rollback = {"official_image_restored": False, "service_restored": False, "errors": ["preflight not completed"]}
    try:
        backend.cmd("git-head", ["git", "rev-parse", "HEAD"])
        backend.cmd("docker-version", ["docker", "version", "--format", "{{json .Server}}"])
        base_config = json.loads(backend.cmd("compose-base", ["docker", "compose", "-f", BASE, "config", "--format", "json"]))
        override_config = json.loads(backend.cmd("compose-derived", ["docker", "compose", "-f", BASE, "-f", OVERRIDE, "config", "--format", "json"]))
        if override_config["services"]["ueransim-gnb"]["image"] != images["derived_tag"]:
            raise PermissionError("override image mismatch")
        override_config["services"]["ueransim-gnb"]["image"] = base_config["services"]["ueransim-gnb"]["image"]
        if override_config != base_config:
            raise PermissionError("override changes more than gNB image")
        backend.scope("official", "preflight")
        if not noqueue(backend.eth0("preflight-eth0")):
            raise PermissionError("unknown pre-existing qdisc")
        for i, trial in enumerate(trials(), 1):
            role = trial["trial_id"].split(":")[0]
            backend.unit_id = trial["trial_id"]
            if i == 5:
                backend.switch("derived")
            backend.scope(role, "trial-scope")
            mutations_started = True
            print(f"[{i}/8] {trial['trial_id']}", flush=True)
            row = run_trial(backend, trial, approval)
            row["role"] = role
            row["candidate_recovery_verified"] = role == "derived" and candidate_recovery(row, backend.post_logs.get(trial["trial_id"], {}))
            rows.append(row)
            save(f"trial-{i:02d}.json", row)
            print(f"valid={row['protocol_execution_valid']} candidate_recovery={row['candidate_recovery_verified']} restored={row['final_service_restored']}", flush=True)
            reason = stop_reason(row)
            if reason:
                break
    except BaseException as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        if mutations_started or backend.candidate_touched:
            rollback = backend.final_rollback()
        save("final-rollback.json", rollback)
    valid = not errors and reason is None and len(rows) == 8 and all(r["protocol_execution_valid"] for r in rows) and rollback["official_image_restored"] and rollback["service_restored"] and not rollback["errors"] and time.monotonic() <= backend.deadline
    summary = {"experiment_id": config["experiment_id"], "completed_at": now(), "completed_trials": len(rows), "protocol_execution_valid": bool(valid),
               "official_failure_reproduced": len(rows) >= 4 and all(r["reconnect_failure_reproduced"] for r in rows[:4] if r["trial"]["drop_ue_egress"]),
               "network_fix_validated": bool(valid and all(r["candidate_recovery_verified"] for r in rows[4:] if r["trial"]["drop_ue_egress"])),
               "stop_reason": reason, "errors": errors, "official_image_restored": rollback["official_image_restored"], "final_service_restored": rollback["service_restored"],
               "candidate_image_applied": backend.candidate_touched, "admission_budget_exceeded": time.monotonic() > backend.deadline,
               "evidence_label": "sandbox-measured", "radio_evidence_label": "simulated", "confirmatory_data": False,
               "long_campaign_ready": False, "TNSM_ready": False, "live_actuation": False, "hardware_measured": False, "operator_validated": False}
    save("summary.json", summary)
    save("manifest.json", {"captured_file_sha256": {p.name: sha(p) for p in output.iterdir() if p.is_file()}})
    print(output, flush=True)
    print(json.dumps(summary), flush=True)
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
