"""Independent raw-command audit; an honest stopped comparison is not a fix."""
from datetime import datetime
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_recovery_pilot import replay_sample, require
from tools.audit_reconnect import verify_exposure_timing
from tools.audit_reconnect_r2_build import audit as audit_build

CORE, GNB, UE = "safetwin5g-open5gs", "safetwin5g-gnb", "safetwin5g-ue"
NAMES = {CORE, GNB, UE, "safetwin5g-mongodb", "safetwin5g-prometheus"}
ORDER = [r + ":" + n for r in ("official", "derived") for n in ("control-before", "drop-a", "drop-b", "control-after")]


def audit_endpoints(role, drop, post_clean, ue, gnb, missing):
    flags = ["Radio link failure detected" in ue, "Sending Service Request" in ue,
             "failed. Could not find a suitable AMF." in gnb, "Uplink data failure, PDU session not found." in gnb]
    reproduced = drop and all(flags) and missing
    corrected = bool(role == "derived" and drop and post_clean and flags[0] and flags[1] and not flags[2] and
                     "Service Accept received" in ue and "Initial Context Setup Request received" in gnb and
                     ue.index("Radio link failure detected") < ue.index("Sending Service Request") < ue.index("Service Accept received"))
    reason = "official_failure_not_reproduced" if role == "official" and drop and not reproduced else "candidate_recovery_not_verified" if role == "derived" and drop and not corrected else None
    return reproduced, corrected, reason


def audit(run):
    run = Path(run)
    read = lambda name: json.loads((run / name).read_text())
    manifest = read("manifest.json")["captured_file_sha256"]
    require(set(manifest) == {p.name for p in run.iterdir() if p.is_file() and p.name != "manifest.json"}, "manifest inventory")
    for name, value in manifest.items():
        require(Path(name).name == name and hashlib.sha256((run / name).read_bytes()).hexdigest() == value, "file hash: " + name)
    design, approval, summary = read("design.json"), read("approval.json"), read("summary.json")
    for name, value in design["source_sha256"].items():
        p = (ROOT / name).resolve()
        require(p.is_relative_to(ROOT) and hashlib.sha256(p.read_text(encoding="utf-8").encode()).hexdigest() == value, "source hash: " + name)
    images = json.loads((ROOT / "config/experiments/reconnect-r2-images.json").read_text())
    require(design["images"] == images and audit_build(ROOT / images["build_run"])["derived_image_id"] == images["derived_image_id"], "audited image lock")
    assignments = [{"trial_id": uid, "drop_ue_egress": ":drop-" in uid} for uid in ORDER]
    config = json.loads((ROOT / "config/experiments/reconnect-r1.json").read_text()) | {"experiment_id": "safetwin5g-reconnect-engineering-r2", "maximum_total_seconds": 1500, "trials": assignments}
    require(design["config"] == config, "frozen trial design")
    require(summary["experiment_id"] == config["experiment_id"], "experiment identity")
    require(approval["status"] == "approved" and approval["environment"] == "sandbox" and approval["rollback_plan"] and
            approval["trials"] == assignments and set(approval["containers"]) == {CORE, GNB, UE} and approval["image_container"] == GNB and
            approval["image_ids"] == [images["official_image_id"], images["derived_image_id"]], "approval scope")
    require(approval["type"] == "standing-project-authorization" and approval["operator_validation"] is False and approval["live_actuation"] is False, "approval boundary")
    rows = [json.loads(line) for line in (run / "commands.jsonl").read_text().splitlines()]
    commands = {row["sequence"]: row for row in rows}
    require(list(commands) == list(range(1, len(rows) + 1)), "contiguous commands")
    compose_base = ["docker", "compose", "-f", "sandbox/compose.yaml"]
    compose_derived = compose_base + ["-f", "sandbox/compose.reconnect-r2.yaml"]
    up = ["up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "ueransim-gnb"]
    switches = []
    for row in rows:
        require(datetime.fromisoformat(approval["recorded_at"]) <= datetime.fromisoformat(row["started_at"]) <= datetime.fromisoformat(row["completed_at"]), "approval/command timing")
        require(hashlib.sha256(row["stdout"].encode()).hexdigest() == row["stdout_sha256"], "command output hash")
        require(row["returncode"] == 0 or (row["name"] == "service-ping" and row["returncode"] == 1), "failed command")
        argv = row["argv"]
        if argv[:2] in (["docker", "exec"], ["docker", "restart"]):
            require(argv[2] in {CORE, GNB, UE}, "out-of-scope container")
        if argv[:2] == ["docker", "compose"]:
            require(argv in (compose_base + ["config", "--format", "json"], compose_derived + ["config", "--format", "json"], compose_base + up, compose_derived + up), "out-of-scope compose")
            if argv[-1] == "ueransim-gnb":
                switches.append((row["unit_id"], row["name"], argv))
    def single(name, unit=None):
        found = [r for r in rows if r["name"] == name and (unit is None or r["unit_id"] == unit)]
        require(len(found) == 1, "missing/duplicate command: " + name)
        return found[0]
    base_cfg = json.loads(single("compose-base")["stdout"])
    derived_cfg = json.loads(single("compose-derived")["stdout"])
    require(derived_cfg["services"]["ueransim-gnb"]["image"] == images["derived_tag"], "override target")
    derived_cfg["services"]["ueransim-gnb"]["image"] = base_cfg["services"]["ueransim-gnb"]["image"]
    require(base_cfg == derived_cfg, "override scope")
    original = {c["Name"].lstrip("/"): c for c in json.loads(single("preflight-containers")["stdout"])}
    versions = json.loads((ROOT / "sandbox/versions.lock.json").read_text())["components"]
    scope_count = 0
    for command in rows:
        if command["name"].endswith("-network"):
            network = json.loads(command["stdout"])[0]
            require(network["Name"] == "safetwin5g-isolated" and network["Internal"] is True and {v["Name"] for v in network["Containers"].values()} == NAMES, "isolated network")
        if not command["name"].endswith("-containers"):
            continue
        scope_count += 1
        role = "derived" if command["unit_id"].startswith("derived:") else "official"
        containers = json.loads(command["stdout"])
        require({c["Name"].lstrip("/") for c in containers} == NAMES, "container inventory")
        for c in containers:
            name = c["Name"].lstrip("/")
            if name == GNB:
                require(not c["HostConfig"].get("CapAdd") and not c["HostConfig"].get("Devices") and
                        len(c["Mounts"]) == 1 and c["Mounts"][0]["RW"] is False and
                        c["Mounts"][0]["Destination"] == "/etc/ueransim/gnb.yaml" and
                        Path(c["Mounts"][0]["Source"]).resolve() == (ROOT / "sandbox/config/ueransim/gnb.yaml").resolve(), "gNB attachment scope")
            require(set(c["NetworkSettings"]["Networks"]) == {"safetwin5g-isolated"} and not c["HostConfig"]["PortBindings"] and not c["HostConfig"]["Privileged"] and c["State"]["Health"]["Status"] == "healthy", "container isolation/health")
            require(c["Config"]["Labels"]["com.docker.compose.project"] == "safetwin5g-sandbox", "container ownership")
            expected = images[role + "_image_id"] if name == GNB else original[name]["Image"]
            require(c["Image"] == expected and (name != UE or expected == images["official_image_id"]), "selected image")
            require(c["Mounts"] == original[name]["Mounts"] and all(c["HostConfig"].get(k) == original[name]["HostConfig"].get(k) for k in
                    ("CapAdd", "CapDrop", "Devices", "Sysctls", "Binds", "SecurityOpt", "Privileged", "PortBindings", "NetworkMode", "PidMode", "IpcMode", "ReadonlyRootfs")), "capability/device/mount drift")
            require(all(c["Config"].get(k) == original[name]["Config"].get(k) for k in ("Cmd", "Entrypoint", "User", "WorkingDir")), "runtime configuration drift")
            if name in {CORE, GNB, UE}:
                component = "open5gs" if name == CORE else "ueransim"
                require(c["Config"]["Labels"]["safetwin5g.upstream.commit"] == versions[component]["commit"], "upstream source pin")
            else:
                component = "mongodb" if name.endswith("mongodb") else "prometheus"
                require(c["Config"]["Image"].endswith("@" + versions[component]["digest"]), "official image digest")
    samples = [json.loads(line) for line in (run / "samples.jsonl").read_text().splitlines()]
    clean = {s["command_sequences"][0]: replay_sample(s, commands) for s in samples}
    require(len(clean) == len(samples) and set(clean) == {r["sequence"] for r in rows if r["name"] == "service-ping"}, "complete raw sample inventory")
    def window(uid, label, measured):
        raw = [s for s in samples if s["trial_id"] == uid and s["window"] == label]
        require(len(raw) == len(measured) == 3 and all(all(s[k] == v for k, v in m.items()) for s, m in zip(raw, measured)), "window/durable linkage")
        require(all(commands[n]["unit_id"] == uid for s in raw for n in s["command_sequences"]), "cross-trial samples")
        return all(clean[s["command_sequences"][0]] for s in raw)
    count = len(list(run.glob("trial-*.json")))
    require(1 <= count <= 8 and summary["completed_trials"] == count, "trial prefix size")
    packet_counts, reproduced, corrected, reasons = [], [], [], []
    for i, uid in enumerate(ORDER[:count], 1):
        trial = read(f"trial-{i:02d}.json")
        role, drop = uid.split(":")[0], ":drop-" in uid
        require(trial["trial"] == assignments[i - 1] and trial["role"] == role and trial["approval_id"] == approval["approval_id"], "trial assignment")
        require(trial["protocol_execution_valid"] and not trial["errors"] and trial["final_service_restored"], "invalid trial cannot pass execution audit")
        require(single("trial-scope-containers", uid)["sequence"] < single("preparation-eth0", uid)["sequence"], "scope before action")
        require(window(uid, "baseline", trial["baseline"]), "baseline packets")
        prep = single("preparation-" + UE, uid)["stdout"]
        require("Initial Registration is successful" in prep and "PDU Session establishment is successful" in prep, "fresh baseline registration/PDU")
        for label in ("preparation-eth0", "baseline-eth0", "post-exposure-eth0"):
            state = json.loads(single(label, uid)["stdout"])
            require(len(state) == 1 and state[0]["kind"] == "noqueue" and state[0]["root"] is True, "eth0 rollback")
        post_clean = window(uid, "post", trial["post"])
        require(post_clean == trial["automatic_service_recovered"] and trial["eth0_rollback_verified"] is True, "recovery/rollback flags")
        ue, gnb = [single("post-" + container, uid)["stdout"] for container in (UE, GNB)]
        for container in (CORE, GNB, UE):
            require(single("post-" + container, uid)["argv"][3] == trial["exposure_started_at"], "pre-restoration log window")
        flags = ["Radio link failure detected" in ue, "Sending Service Request" in ue, "failed. Could not find a suitable AMF." in gnb, "Uplink data failure, PDU session not found." in gnb]
        sent = sum(s["metrics"]["packets_transmitted"] for s in trial["post"])
        received = sum(s["metrics"]["packets_received"] for s in trial["post"])
        missing = sent == 15 and received == 0
        require(trial["observations"] == dict(zip(("radio_link_failure", "service_request", "amf_selection_failure", "missing_pdu_resource", "zero_post_packets"), [*flags, missing])), "raw marker mismatch")
        exposure = single("bounded-link-drop" if drop else "control-wait", uid)
        verify_exposure_timing(trial, exposure)
        expected_restarts = [CORE, GNB, UE]
        if drop:
            require(exposure["argv"][2:7] == [UE, "timeout", "15", "sh", "-lc"] and exposure["stdout"] == trial["fault_transcript"], "bounded fault command")
            lines = exposure["stdout"].splitlines()
            require(len(lines) == 4 and 8 <= (datetime.fromisoformat(lines[2]) - datetime.fromisoformat(lines[0])).total_seconds() < 15, "fault interval")
            during, after = json.loads(lines[1]), json.loads(lines[3])
            require(len(during) == 1 and during[0]["kind"] == "netem" and during[0]["handle"] == "7157:" and during[0]["options"]["loss-random"]["loss"] == 1 and len(after) == 1 and after[0]["kind"] == "noqueue", "fault and trap rollback")
            require(1 <= len(trial["restoration_attempts"]) <= 2, "restoration ladder")
            for j, attempt in enumerate(trial["restoration_attempts"]):
                step = ("restore-ue", "restore-full")[j]
                require(attempt["step"] == step, "restoration step order")
                expected_restarts.extend([UE] if j == 0 else [CORE, GNB, UE])
                restored = window(uid, step, attempt["samples"]) if "samples" in attempt else False
                if attempt["clean"]:
                    log = single(step + "-" + UE, uid)["stdout"]
                    require(restored and "Initial Registration is successful" in log and "PDU Session establishment is successful" in log, "restored registration/PDU/packets")
                if j + 1 < len(trial["restoration_attempts"]):
                    require(not attempt["clean"], "retry after successful restoration")
            require(trial["restoration_attempts"][-1]["clean"], "final trial restoration")
        else:
            require(post_clean and not any(flags) and not trial["restoration_attempts"] and exposure["argv"] == ["docker", "exec", UE, "sleep", "8"], "no-fault control")
        restart_commands = [r for r in rows if r["unit_id"] == uid and r["argv"][:2] == ["docker", "restart"]]
        require([r["argv"][2] for r in restart_commands] == expected_restarts, "unexpected restart")
        require(restart_commands[2]["sequence"] < trial["baseline"][0]["command_sequences"][0], "preparation before baseline")
        require(all(r["sequence"] > single("post-" + UE, uid)["sequence"] for r in restart_commands[3:]), "restoration before post evidence")
        require(exposure["sequence"] > trial["baseline"][-1]["command_sequences"][-1] and
                trial["post"][0]["command_sequences"][0] > single("post-exposure-eth0", uid)["sequence"], "baseline/exposure/post sequence")
        require(not any(trial["post"][0]["command_sequences"][0] <= r["sequence"] <= single("post-" + UE, uid)["sequence"] for r in restart_commands), "restart hidden in post window")
        reproduced_here, corrected_here, reason = audit_endpoints(role, drop, post_clean, ue, gnb, missing)
        require(trial["reconnect_failure_reproduced"] == reproduced_here and trial["candidate_recovery_verified"] == corrected_here, "derived evidence flag")
        reasons.append(reason)
        if role == "official" and drop:
            reproduced.append(reproduced_here)
        if role == "derived" and drop:
            corrected.append(corrected_here)
        packet_counts.append({"trial": uid, "post_received": received, "post_sent": sent, "candidate_recovery": corrected_here})
    require(not any(reasons[:-1]) and summary["stop_reason"] == reasons[-1], "stop at first failed comparison endpoint")
    require(count == 8 or reasons[-1] is not None, "unexplained incomplete prefix")
    rollback = read("final-rollback.json")
    require(not rollback["errors"] and rollback["official_image_restored"] and rollback["service_restored"] and window("final-rollback", "final-official", rollback["samples"]), "final official rollback")
    final_log = single("final-official-" + UE)["stdout"]
    require("Initial Registration is successful" in final_log and "PDU Session establishment is successful" in final_log, "final fresh registration/PDU")
    single("final-official-containers")
    final_qdisc = json.loads(single("final-eth0")["stdout"])
    require(len(final_qdisc) == 1 and final_qdisc[0]["kind"] == "noqueue", "final qdisc")
    require([r["argv"][2] for r in rows if r["unit_id"] == "final-rollback" and r["argv"][:2] == ["docker", "restart"]] == [CORE, GNB, UE], "final reset sequence")
    expected_switches = [("derived:control-before", "switch-derived", compose_derived + up), ("final-rollback", "switch-official", compose_base + up)] if count > 4 else []
    require(switches == expected_switches and summary["candidate_image_applied"] == (count > 4), "image replacement/rollback sequence")
    valid = count == 8 and not any(reasons) and not summary["admission_budget_exceeded"]
    require(not valid or (datetime.fromisoformat(summary["completed_at"]) - datetime.fromisoformat(approval["recorded_at"])).total_seconds() <= 1501, "independent wall-time bound")
    require(not summary["errors"] and summary["protocol_execution_valid"] == valid and summary["network_fix_validated"] == (valid and len(corrected) == 2 and all(corrected)), "terminal execution/fix gate")
    require(summary["official_failure_reproduced"] == (count >= 4 and len(reproduced) == 2 and all(reproduced)), "official reproduction gate")
    require(summary["official_image_restored"] and summary["final_service_restored"], "terminal rollback flags")
    for key in ("long_campaign_ready", "TNSM_ready", "confirmatory_data", "live_actuation", "hardware_measured", "operator_validated"):
        require(summary[key] is False, "claim tier: " + key)
    require(summary["evidence_label"] == "sandbox-measured" and summary["radio_evidence_label"] == "simulated", "evidence labels")
    return {"audit_passed": True, "protocol_execution_valid": valid, "network_fix_validated": summary["network_fix_validated"], "completed_trials": count,
            "commands_replayed": len(rows), "samples_replayed": len(samples), "scope_snapshots": scope_count, "post_packet_counts": packet_counts,
            "stop_reason": summary["stop_reason"], "official_image_restored": True, "final_service_restored": True, "long_campaign_ready": False, "TNSM_ready": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(audit(args.run), indent=2))
    except (ValueError, KeyError, OSError, IndexError) as exc:
        print(json.dumps({"audit_passed": False, "error": str(exc)}))
        raise SystemExit(2)
