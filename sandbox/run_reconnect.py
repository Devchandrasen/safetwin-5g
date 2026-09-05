"""Bounded, separately approved simulated-link reconnect reproduction."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sandbox.run_recovery_pilot import (  # noqa: E402
    Backend, CORE, GNB, UE, CONTAINERS, NETWORK, now, sha, source_sha,
    samples_clean, validate_environment,
)

CONFIG = ROOT / "config/experiments/reconnect-r1.json"
FAULT_SCRIPT = """set -eu
owned=0
cleanup() {
    if [ "$owned" = 1 ]; then
        tc qdisc del dev eth0 root handle 7157:
        date -u +%Y-%m-%dT%H:%M:%S.%NZ
        tc -j qdisc show dev eth0
    fi
}
trap cleanup EXIT
trap 'exit 130' INT TERM HUP
tc qdisc add dev eth0 root handle 7157: netem loss 100%
owned=1
date -u +%Y-%m-%dT%H:%M:%S.%NZ
tc -j qdisc show dev eth0
sleep 8
"""


def noqueue(rows):
    return len(rows) == 1 and rows[0].get("kind") == "noqueue" and rows[0].get("root") is True


def validate_config(config):
    expected = [{"trial_id": name, "drop_ue_egress": drop} for name, drop in
                (("control-before", False), ("drop-a", True), ("drop-b", True), ("control-after", False))]
    fixed = {"environment": "sandbox", "trials": expected, "exposure_seconds": 8,
             "settle_seconds": 5, "maximum_total_seconds": 900, "maximum_command_seconds": 35,
             "maximum_container_health_seconds": 50, "in_container_timeout_seconds": 15,
             "fault_handle": "7157:", "samples_per_window": 3, "packets_per_sample": 5,
             "confirmatory_data": False, "long_campaign_ready": False}
    if any(config.get(key) != value for key, value in fixed.items()):
        raise PermissionError("fixed reconnect protocol required")


def classify(exposure, ue_log, gnb_log):
    metrics = [s["metrics"] for s in exposure]
    return {
        "radio_link_failure": "Radio link failure detected" in ue_log,
        "service_request": "Sending Service Request" in ue_log,
        "amf_selection_failure": "failed. Could not find a suitable AMF." in gnb_log,
        "missing_pdu_resource": "Uplink data failure, PDU session not found." in gnb_log,
        "zero_post_packets": len(metrics) == 3 and all(m.get("packets_transmitted") == 5 and m.get("packets_received") == 0 and m.get("packet_loss_pct") == 100 for m in metrics),
    }


class ReconnectBackend(Backend):
    def logs(self, label, since):
        result = {}
        for container in (CORE, GNB, UE):
            result[container] = self.cmd(label + "-" + container, ["docker", "logs", "--since", since, "--tail", "2000", container])
        return result

    def eth0(self, label):
        return json.loads(self.cmd(label, ["docker", "exec", UE, "tc", "-j", "qdisc", "show", "dev", "eth0"]))

    def clear_owned_fault(self):
        state = self.eth0("rollback-inspect-eth0")
        if noqueue(state):
            return
        if len(state) != 1 or state[0].get("kind") != "netem" or state[0].get("handle") != "7157:":
            raise RuntimeError("unknown eth0 qdisc: refuse to delete another owner's state")
        self.cmd("emergency-clear-owned-qdisc", ["docker", "exec", UE, "tc", "qdisc", "del", "dev", "eth0", "root", "handle", "7157:"])
        if not noqueue(self.eth0("rollback-verify-eth0")):
            raise RuntimeError("eth0 rollback failed")

    def restore(self):
        attempts = []
        for label, containers in (("restore-ue", [UE]), ("restore-full", [CORE, GNB, UE])):
            row = {"step": label, "started_at": now(), "errors": []}
            started = time.monotonic()
            try:
                self.restart(containers)
                row["samples"] = self.window(label)
                logs = self.logs(label, row["started_at"])
                row["fresh_registration"] = "Initial Registration is successful" in logs[UE]
                row["fresh_pdu"] = "PDU Session establishment is successful" in logs[UE]
                row["clean"] = samples_clean(row["samples"]) and noqueue(self.eth0(label + "-eth0")) and row["fresh_registration"] and row["fresh_pdu"]
            except Exception as exc:
                row["errors"].append(str(exc))
                row["clean"] = False
            row.update(completed_at=now(), elapsed_seconds=time.monotonic() - started)
            attempts.append(row)
            if row["clean"]:
                break
        return attempts


def run_trial(backend, trial, approval):
    if (approval.get("status") != "approved" or approval.get("environment") != "sandbox"
            or trial not in approval.get("trials", [])
            or set(approval.get("containers", [])) != {CORE, GNB, UE}
            or not approval.get("rollback_plan")):
        raise PermissionError("trial-scoped sandbox approval required")
    backend.unit_id = trial["trial_id"]
    row = {"trial": trial, "started_at": now(), "errors": [], "approval_id": approval["approval_id"], "restoration_attempts": []}
    try:
        if time.monotonic() + 180 > backend.deadline:
            raise TimeoutError("insufficient admission budget")
        # Refuse pre-existing unrelated qdisc BEFORE even preparation resets.
        if not noqueue(backend.eth0("preparation-eth0")):
            raise RuntimeError("baseline eth0 must be noqueue")
        backend.restart([CORE, GNB, UE])
        row["baseline"] = backend.window("baseline")
        preparation = backend.logs("preparation", row["started_at"])
        row["fresh_registration"] = "Initial Registration is successful" in preparation[UE]
        row["fresh_pdu"] = "PDU Session establishment is successful" in preparation[UE]
        if not (samples_clean(row["baseline"]) and row["fresh_registration"] and row["fresh_pdu"] and noqueue(backend.eth0("baseline-eth0"))):
            raise RuntimeError("invalid baseline blocks exposure")
        row["exposure_started_at"] = now()
        started = time.monotonic()
        if trial["drop_ue_egress"]:
            row["fault_transcript"] = backend.cmd("bounded-link-drop", ["docker", "exec", UE, "timeout", "15", "sh", "-lc", FAULT_SCRIPT])
        else:
            backend.cmd("control-wait", ["docker", "exec", UE, "sleep", "8"])
        row["exposure_completed_at"] = now()
        row["exposure_command_seconds"] = time.monotonic() - started
        row["eth0_rollback_verified"] = noqueue(backend.eth0("post-exposure-eth0"))
        if not row["eth0_rollback_verified"]:
            raise RuntimeError("fault not rolled back")
        time.sleep(5)
        row["post"] = backend.window("post")
        logs = backend.logs("post", row["exposure_started_at"])
        row["observations"] = classify(row["post"], logs[UE], logs[GNB])
        row["automatic_service_recovered"] = samples_clean(row["post"])
        if not trial["drop_ue_egress"] and (not row["automatic_service_recovered"] or any(row["observations"].values())):
            raise RuntimeError("no-fault control failed")
    except BaseException as exc:
        row["errors"].append(f"{type(exc).__name__}: {exc}")
    finally:
        backend.restoring = True
        try:
            backend.clear_owned_fault()
            if trial["drop_ue_egress"] or row["errors"]:
                row["restoration_attempts"] = backend.restore()
                row["final_service_restored"] = row["restoration_attempts"][-1]["clean"]
            else:
                row["final_service_restored"] = row.get("automatic_service_recovered", False)
        except Exception as exc:
            row["errors"].append("restoration: " + str(exc))
            row["final_service_restored"] = False
        backend.restoring = False
    row["protocol_execution_valid"] = bool(not row["errors"] and row.get("eth0_rollback_verified") and row["final_service_restored"])
    row["reconnect_failure_reproduced"] = bool(row["protocol_execution_valid"] and trial["drop_ue_egress"] and all(row.get("observations", {}).values()))
    row["completed_at"] = now()
    return row


def main():
    config = json.loads(CONFIG.read_text())
    validate_config(config)
    policy = json.loads((ROOT / "config/actions.json").read_text())
    if config["environment"] != "sandbox" or policy["allow_live_actuation"] is not False or policy["require_human_approval"] is not True:
        raise PermissionError("fail-closed sandbox policy required")
    from datetime import datetime, timezone
    output = ROOT / "evidence/engineering" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r1")
    output.mkdir(parents=True, exist_ok=False)
    def save(name, value):
        (output / name).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sources = {name: source_sha(ROOT / name) for name in (
        "sandbox/run_reconnect.py", "sandbox/run_recovery_pilot.py", "config/experiments/reconnect-r1.json",
        "docs/RECONNECT_R1_PROTOCOL.md", "tools/audit_reconnect.py", "tools/audit_recovery_pilot.py",
        "src/safetwin5g/phase7_runner.py", "sandbox/versions.lock.json", "sandbox/compose.yaml", "config/actions.json")}
    approval = {"approval_id": "reconnect-r1-" + sha(CONFIG), "status": "approved", "environment": "sandbox",
                "recorded_at": now(), "approved_by": "user", "type": "standing-project-authorization",
                "authorization_basis": "User authorized local reversible SafeTwin sandbox work and automatic sequential continuation.",
                "trials": config["trials"], "containers": [CORE, GNB, UE],
                "operations": ["fixed core/gNB/UE preparation resets", "UE eth0 100% egress loss for 8 seconds, handle 7157:", "15-second in-container timeout and EXIT rollback", "UE restart then full reset for restoration"],
                "rollback_plan": "Remove exact owned eth0 qdisc in shell trap and verify noqueue; always restore service with UE restart then full core/gNB/UE reset if required.",
                "live_actuation": False, "operator_validation": False}
    save("approval.json", approval)
    save("design.json", {"config": config, "source_sha256": sources, "source_hash_mode": "utf8-lf-normalized"})
    backend = ReconnectBackend(output, config)
    rows, errors = [], []
    try:
        backend.cmd("git-head", ["git", "rev-parse", "HEAD"])
        backend.cmd("docker-version", ["docker", "version", "--format", "{{json .Server}}"])
        backend.cmd("tc-version", ["docker", "exec", UE, "tc", "-V"])
        backend.cmd("timeout-version", ["docker", "exec", UE, "timeout", "--version"])
        network = json.loads(backend.cmd("isolated-network", ["docker", "network", "inspect", NETWORK]))[0]
        containers = json.loads(backend.cmd("container-identities", ["docker", "inspect", *CONTAINERS]))
        validate_environment(network, containers, json.loads((ROOT / "sandbox/versions.lock.json").read_text())["components"])
        for i, trial in enumerate(config["trials"], 1):
            print(f"[{i}/4] {trial['trial_id']}", flush=True)
            row = run_trial(backend, trial, approval)
            rows.append(row)
            save(f"trial-{i:02d}.json", row)
            print(f"valid={row['protocol_execution_valid']} reproduced={row['reconnect_failure_reproduced']} restored={row['final_service_restored']}", flush=True)
            if not row["protocol_execution_valid"]:
                break
    except BaseException as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    valid = not errors and len(rows) == 4 and all(r["protocol_execution_valid"] for r in rows)
    summary = {"experiment_id": config["experiment_id"], "completed_at": now(), "completed_trials": len(rows),
               "protocol_execution_valid": valid,
               "reconnect_failure_reproduced": valid and all(r["reconnect_failure_reproduced"] for r in rows if r["trial"]["drop_ue_egress"]),
               "final_service_restored": bool(rows and rows[-1]["final_service_restored"]), "errors": errors,
               "admission_budget_exceeded": time.monotonic() > backend.deadline,
               "evidence_label": "sandbox-measured", "radio_evidence_label": "simulated",
               "network_patch_applied": False, "long_campaign_ready": False, "confirmatory_data": False,
               "live_actuation": False, "hardware_measured": False, "operator_validated": False, "TNSM_ready": False}
    save("summary.json", summary)
    save("manifest.json", {"captured_file_sha256": {p.name: sha(p) for p in output.iterdir() if p.is_file()}})
    print(output, flush=True)
    print(json.dumps(summary), flush=True)
    return 0 if valid else 2


if __name__ == "__main__":
    raise SystemExit(main())
