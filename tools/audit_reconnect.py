"""Independently replay reconnect data and distinguish reproduction from repair."""
from datetime import datetime
import argparse
import hashlib
import json
from pathlib import Path

try:
    from tools.audit_recovery_pilot import replay_sample, require
except ModuleNotFoundError:
    from audit_recovery_pilot import replay_sample, require

ROOT = Path(__file__).resolve().parents[1]
ORDER = ["control-before", "drop-a", "drop-b", "control-after"]
CORE, GNB, UE = "safetwin5g-open5gs", "safetwin5g-gnb", "safetwin5g-ue"


def verify_exposure_timing(row, command):
    start = datetime.fromisoformat(row["exposure_started_at"])
    end = datetime.fromisoformat(row["exposure_completed_at"])
    command_start = datetime.fromisoformat(command["started_at"])
    command_end = datetime.fromisoformat(command["completed_at"])
    require(start <= command_start <= command_end <= end, "exposure command time scope")
    require(8 <= (command_end - command_start).total_seconds() <= 35, "bounded exposure command interval")
    require(all((datetime.fromisoformat(s["observed_at"]) - end).total_seconds() >= 5
                for s in row["post"]), "post-rollback settling interval")


def audit(run):
    run = Path(run)
    read = lambda name: json.loads((run / name).read_text())
    manifest = read("manifest.json")["captured_file_sha256"]
    require(set(manifest) == {p.name for p in run.iterdir() if p.is_file() and p.name != "manifest.json"}, "manifest inventory")
    for name, value in manifest.items():
        require(Path(name).name == name and hashlib.sha256((run / name).read_bytes()).hexdigest() == value, "file hash: " + name)
    design, approval, summary = read("design.json"), read("approval.json"), read("summary.json")
    for name, value in design["source_sha256"].items():
        source = (ROOT / name).resolve()
        require(source.is_relative_to(ROOT) and hashlib.sha256(source.read_text(encoding="utf-8").encode()).hexdigest() == value, "source hash: " + name)
    require(design["config"] == json.loads((ROOT / "config/experiments/reconnect-r1.json").read_text()), "frozen config")
    require(approval["status"] == "approved" and approval["environment"] == "sandbox" and approval["rollback_plan"], "approval status")
    require(approval["trials"] == design["config"]["trials"] and set(approval["containers"]) == {CORE, GNB, UE}, "approval scope")
    rows = [json.loads(line) for line in (run / "commands.jsonl").read_text().splitlines()]
    commands = {r["sequence"]: r for r in rows}
    require(list(commands) == list(range(1, len(rows) + 1)), "command sequence")
    for row in rows:
        require(datetime.fromisoformat(approval["recorded_at"]) <= datetime.fromisoformat(row["started_at"]) <= datetime.fromisoformat(row["completed_at"]), "approval timing")
        require(hashlib.sha256(row["stdout"].encode()).hexdigest() == row["stdout_sha256"], "stdout hash")
        if row["argv"][:2] in (["docker", "exec"], ["docker", "restart"]):
            require(row["argv"][2] in {CORE, GNB, UE}, "out-of-scope action")
    preflight = {r["name"]: r for r in rows if r["unit_id"] == "preflight"}
    network = json.loads(preflight["isolated-network"]["stdout"])[0]
    require(network["Internal"] is True and network["Name"] == "safetwin5g-isolated", "isolated network")
    containers = json.loads(preflight["container-identities"]["stdout"])
    expected_containers = {CORE, GNB, UE, "safetwin5g-mongodb", "safetwin5g-prometheus"}
    require({c["Name"].lstrip("/") for c in containers} == {v["Name"] for v in network["Containers"].values()} == expected_containers, "container inventory")
    versions = json.loads((ROOT / "sandbox/versions.lock.json").read_text())["components"]
    for c in containers:
        require(set(c["NetworkSettings"]["Networks"]) == {network["Name"]} and not c["HostConfig"]["PortBindings"] and not c["HostConfig"]["Privileged"] and c["State"]["Health"]["Status"] == "healthy" and c["Config"]["Labels"]["com.docker.compose.project"] == "safetwin5g-sandbox", "container scope")
        name = c["Name"].lstrip("/")
        if name in {CORE, GNB, UE}:
            component = "open5gs" if name == CORE else "ueransim"
            require(c["Config"]["Labels"]["safetwin5g.upstream.commit"] == versions[component]["commit"], "source pin")
        else:
            component = "mongodb" if name.endswith("mongodb") else "prometheus"
            require(c["Config"]["Image"].endswith("@" + versions[component]["digest"]), "image pin")
    samples = [json.loads(line) for line in (run / "samples.jsonl").read_text().splitlines()]
    clean = {s["command_sequences"][0]: replay_sample(s, commands) for s in samples}
    require(len(clean) == len(samples) and set(clean) == {r["sequence"] for r in rows if r["name"] == "service-ping"}, "all raw samples retained")
    require(len(list(run.glob("trial-*.json"))) == 4, "incomplete reproduction protocol")
    reproduced, packet_counts = [], []
    for i, uid in enumerate(ORDER, 1):
        row = read(f"trial-{i:02d}.json")
        drop = uid.startswith("drop-")
        require(row["trial"] == {"trial_id": uid, "drop_ue_egress": drop} and row["approval_id"] == approval["approval_id"], "trial assignment")
        require(row["protocol_execution_valid"] is True and not row["errors"] and row["final_service_restored"], "invalid trial")
        unit = [r for r in rows if r["unit_id"] == uid]
        def named(name):
            found = [r for r in unit if r["name"] == name]
            require(len(found) == 1, "command missing/duplicate: " + name)
            return found[0]
        def window(label, measured):
            raw = [s for s in samples if s["trial_id"] == uid and s["window"] == label]
            require(len(raw) == len(measured) == 3, "window size")
            require(all(all(s[k] == value for k, value in t.items()) for s, t in zip(raw, measured)), "durable sample mismatch")
            require(all(all(commands[n]["unit_id"] == uid for n in s["command_sequences"]) for s in raw), "cross-trial sample linkage")
            return all(clean[s["command_sequences"][0]] for s in raw)
        require(window("baseline", row["baseline"]), "baseline service")
        prep = named("preparation-" + UE)["stdout"]
        require("Initial Registration is successful" in prep and "PDU Session establishment is successful" in prep and row["fresh_registration"] and row["fresh_pdu"], "fresh baseline registration/PDU")
        for label in ("preparation-eth0", "baseline-eth0", "post-exposure-eth0"):
            state = json.loads(named(label)["stdout"])
            require(len(state) == 1 and state[0]["kind"] == "noqueue" and state[0]["root"] is True, "eth0 state")
        require(row["eth0_rollback_verified"] is True, "rollback flag")
        post_clean = window("post", row["post"])
        require(row["automatic_service_recovered"] == post_clean, "automatic recovery flag")
        ue_log, gnb_log = named("post-" + UE)["stdout"], named("post-" + GNB)["stdout"]
        for name in ("post-" + UE, "post-" + GNB):
            require(named(name)["argv"][3] == row["exposure_started_at"], "post-log time scope")
        markers = ["Radio link failure detected" in ue_log, "Sending Service Request" in ue_log,
                   "failed. Could not find a suitable AMF." in gnb_log, "Uplink data failure, PDU session not found." in gnb_log]
        sent = sum(s["metrics"]["packets_transmitted"] for s in row["post"])
        received = sum(s["metrics"]["packets_received"] for s in row["post"])
        missing = sent == 15 and received == 0
        require(row["observations"] == dict(zip(("radio_link_failure", "service_request", "amf_selection_failure", "missing_pdu_resource", "zero_post_packets"), [*markers, missing])), "raw log classification mismatch")
        expected_restarts = [CORE, GNB, UE]
        verify_exposure_timing(row, named("bounded-link-drop" if drop else "control-wait"))
        if drop:
            fault = named("bounded-link-drop")
            require(fault["returncode"] == 0 and fault["argv"][2:7] == [UE, "timeout", "15", "sh", "-lc"] and fault["stdout"] == row["fault_transcript"], "bounded fault command")
            lines = fault["stdout"].splitlines()
            require(len(lines) == 4, "fault transcript shape")
            start, end = datetime.fromisoformat(lines[0]), datetime.fromisoformat(lines[2])
            require(8 <= (end - start).total_seconds() < 15, "in-container exposure interval")
            during, after = json.loads(lines[1]), json.loads(lines[3])
            require(len(during) == 1 and during[0]["kind"] == "netem" and during[0]["handle"] == "7157:" and during[0]["root"] is True, "owned fault state")
            require(during[0]["options"].get("loss-random", {}).get("loss") == 1.0, "100 percent loss configuration")
            require(len(after) == 1 and after[0]["kind"] == "noqueue", "trap rollback")
            require(1 <= len(row["restoration_attempts"]) <= 2, "restoration ladder")
            for j, attempt in enumerate(row["restoration_attempts"]):
                step = ("restore-ue", "restore-full")[j]
                require(attempt["step"] == step, "restoration step order")
                expected_restarts.extend([UE] if j == 0 else [CORE, GNB, UE])
                observed_clean = window(step, attempt["samples"]) if "samples" in attempt else False
                if attempt["clean"]:
                    log = named(step + "-" + UE)["stdout"]
                    require(observed_clean and "Initial Registration is successful" in log and "PDU Session establishment is successful" in log, "final registration/PDU/service")
                if j < len(row["restoration_attempts"]) - 1:
                    require(not attempt["clean"], "unexpected retry after success")
            require(row["restoration_attempts"][-1]["clean"], "final recovery")
        else:
            control = named("control-wait")
            require(control["returncode"] == 0 and control["argv"] == ["docker", "exec", UE, "sleep", "8"], "fixed no-fault control interval")
            require(post_clean and not any(markers) and not row["restoration_attempts"], "control failure or hidden recovery")
            require(not any(r["name"] == "bounded-link-drop" for r in unit), "control injected fault")
        require([r["argv"][2] for r in unit if r["argv"][:2] == ["docker", "restart"]] == expected_restarts, "restart scope/order")
        did_reproduce = drop and all(markers) and missing
        require(row["reconnect_failure_reproduced"] == did_reproduce, "reproduction flag")
        if drop:
            reproduced.append(did_reproduce)
        packet_counts.append({"trial": uid, "post_received": received, "post_sent": sent, "reproduced": did_reproduce})
    require(summary["completed_trials"] == 4 and summary["protocol_execution_valid"] and not summary["errors"] and summary["final_service_restored"], "summary execution gate")
    require(summary["reconnect_failure_reproduced"] == all(reproduced), "summary reproduction gate")
    for key in ("network_patch_applied", "long_campaign_ready", "confirmatory_data", "live_actuation", "hardware_measured", "operator_validated", "TNSM_ready", "admission_budget_exceeded"):
        require(summary[key] is False, "claim/budget gate: " + key)
    require(summary["evidence_label"] == "sandbox-measured" and summary["radio_evidence_label"] == "simulated", "evidence tier")
    return {"audit_passed": True, "protocol_execution_valid": True, "reconnect_failure_reproduced": all(reproduced),
            "commands_replayed": len(rows), "samples_replayed": len(samples), "post_packet_counts": packet_counts,
            "network_fix_validated": False, "long_campaign_ready": False, "TNSM_ready": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(audit(args.run), indent=2))
    except (ValueError, KeyError, OSError, IndexError) as exc:
        print(json.dumps({"audit_passed": False, "error": str(exc)}, indent=2))
        raise SystemExit(2)
