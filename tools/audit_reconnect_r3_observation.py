"""Independent audit of the rejected R3 prefix and later read-only clock probe.

This certifies retained observations/rollback, never four-trial acceptance.
The frozen complete-protocol auditor remains unchanged and rejects this run.
"""
from datetime import datetime
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_reconnect_r3_network import raw_ping, raw_logs, raw_paths, replay_sample, audit_scope

RUN = ROOT / "evidence/engineering/20260905T131024Z-reconnect-r3-network"
CLOCK = ROOT / "evidence/engineering/20260905T132047Z-reconnect-r3-clock"
UE, GNB, CORE = "safetwin5g-ue", "safetwin5g-gnb", "safetwin5g-open5gs"
NAMES = [CORE, GNB, UE, "safetwin5g-mongodb", "safetwin5g-prometheus"]
SAMPLE = ["service-ping", "sample-qdisc", "upf-state", "stress-workers", "targets", "trace-" + UE, "trace-" + GNB]
ERROR = "ValueError: missing packet or fingerprint mismatch"


def require(value, message):
    if not value: raise ValueError(message)


def sha(data): return hashlib.sha256(data).hexdigest()
def read(path): return json.loads(Path(path).read_bytes())
def at(value): return datetime.fromisoformat(value)


def manifest(directory):
    directory = Path(directory)
    rows = read(directory / "manifest.json")["captured_file_sha256"]
    require(set(rows) == {p.name for p in directory.iterdir() if p.is_file() and p.name != "manifest.json"}, "artifact inventory")
    for name, digest in rows.items():
        require(Path(name).name == name and sha((directory / name).read_bytes()) == digest, "artifact hash")


def source_address(text):
    lines = [line for line in text.splitlines() if line.startswith("PING ")]
    require(len(lines) == 1, "one ping header required")
    match = re.fullmatch(r"PING 10\.45\.0\.1 \(10\.45\.0\.1\) from (10\.45\.0\.\d+) uesimtun0: 56\(84\) bytes of data\.", lines[0])
    require(match, "identified source/interface/payload header")
    return match.group(1)


def partial_paths(ue, gnb, since, until, identifier):
    """Describe only observed complete forwarding paths, never invent ingress."""
    packets, order = {}, {"ue": {}, "gnb": {}}
    for component, text in (("ue", ue), ("gnb", gnb)):
        for message in raw_logs(text, since, until):
            if "ST3" not in message: continue
            require(message.count("ST3 ") == 1, "trace marker")
            tokens = message.split("ST3 ", 1)[1].split()
            require([t.split("=", 1)[0] for t in tokens] == "stage psi actor cm mm ps pending ipid id seq bytes fp".split(), "trace schema")
            row = dict(t.split("=", 1) for t in tokens); stage = row.pop("stage")
            row = {k: int(v) for k, v in row.items()}
            require(row["id"] == identifier and row["psi"] == 1 and row["bytes"] == 84 and 1 <= row["seq"] <= 5, "trace scope")
            require(stage in ({"nas_in", "nas_forward", "ue_rls"} if component == "ue" else {"gnb_in", "gnb_resource"}), "observed forwarding stages")
            seq = row["seq"]; bucket = packets.setdefault(seq, {})
            require(stage not in bucket, "duplicate observed stage"); bucket[stage] = row
            order[component].setdefault(seq, []).append(stage)
    for seq, events in packets.items():
        require(set(events) == {"nas_in", "nas_forward", "ue_rls", "gnb_in", "gnb_resource"}, "incomplete present packet path")
        require(order["ue"][seq] == ["nas_in", "nas_forward", "ue_rls"] and order["gnb"][seq] == ["gnb_in", "gnb_resource"], "local stage order")
        require(len({(r["ipid"], r["bytes"], r["fp"]) for r in events.values()}) == 1, "observed fingerprint mismatch")
        require(events["nas_in"]["cm"] == events["nas_forward"]["cm"] == events["nas_forward"]["ps"] == 1, "forwarding state")
    return {"observed_sequences": sorted(packets), "unobserved_sequences": sorted(set(range(1, 6)) - set(packets)),
            "observed_paths_have_consistent_fingerprints": True if packets else None, "missing_trace_is_packet_loss_proof": False}


def audit_run(directory=RUN):
    directory = Path(directory); manifest(directory)
    design, approval, summary, trial, rollback = [read(directory / name) for name in
        ("design.json", "approval.json", "summary.json", "trial-01.json", "final-rollback.json")]
    config = read(ROOT / "config/experiments/reconnect-r3-trace.json")
    images = read(ROOT / "config/experiments/reconnect-r3-images.json")
    lock = read(ROOT / "config/experiments/reconnect-r3-execution-lock.json")
    contract = read(ROOT / "config/experiments/reconnect-r3-command-contract.json")
    reference = read(ROOT / "config/experiments/reconnect-r3-scope-reference.json")["containers"]
    require(design["execution_mode"] == "sandbox" and design["transport"] == "docker-cli" and design["config"] == config and design["images"] == images and design["source_sha256"] == lock["source_sha256"], "frozen design/source lock")
    for name, digest in design["source_sha256"].items(): require(sha((ROOT / name).read_bytes()) == digest, "frozen source drift")
    require(approval["approved_by"] == "user" and approval["status"] == "approved" and approval["type"] == "standing-project-authorization"
            and approval["environment"] == "sandbox" and approval["trials"] == config["trials"] and approval["containers"] == [CORE, GNB, UE]
            and approval["image_containers"] == [GNB, UE] and approval["image_ids"] == [images["official_image_id"], images["derived_image_id"]]
            and approval["rollback_plan"] and approval["operator_validation"] is False and approval["live_actuation"] is False, "scoped prior approval")
    rows = [json.loads(line) for line in (directory / "commands.jsonl").read_text().splitlines()]
    require([r["sequence"] for r in rows] == list(range(1, len(rows)+1)), "command sequence")
    commands = {r["sequence"]: r for r in rows}
    one = lambda name: next(r for r in rows if r["name"] == name)
    expected = ["repository-head", "docker-version", "compose-base", "compose-derived", "official-image", "derived-image", "preflight-network", "preflight-containers", "preflight-eth0", "ping-help",
                "switch-derived-image", "switch-derived", "switch-derived-verified-network", "switch-derived-verified-containers",
                "trial-scope-network", "trial-scope-containers", "preparation-eth0"]
    reset = ["restart-" + n for n in (CORE, GNB, UE)]
    expected += reset + SAMPLE + ["rollback-inspect-eth0", "restart-" + UE] + SAMPLE + reset + SAMPLE
    expected += ["rollback-inspect-eth0", "switch-official-image", "switch-official", "switch-official-verified-network", "switch-official-verified-containers"]
    expected += reset + SAMPLE * 3 + ["final-official-" + n for n in (CORE, GNB, UE)] + ["final-official-network", "final-official-containers", "final-eth0"]
    require([r["name"] for r in rows if not r["name"].startswith("health-")] == expected, "exact stopped command inventory; no fault/warmup/retry")
    previous = at(approval["recorded_at"])
    for row in rows:
        a, name = row["argv"], row["name"]
        require(previous <= at(row["started_at"]) <= at(row["completed_at"]), "command/approval chronology"); previous = at(row["completed_at"])
        require(0 < row["timeout_seconds"] <= 35, "bounded command")
        for stream in ("stdout", "stderr"): require(sha(row[stream].encode()) == row[stream + "_sha256"], "raw command hash")
        accepted = [0, 1] if name == "service-ping" else [0, 2] if name == "ping-help" else [0]
        require(row["accepted_returncodes"] == accepted and row["returncode"] in accepted, "command acceptance")
        if name in contract["fixed_commands"]: require(a == contract["fixed_commands"][name], "fixed command scope")
        elif name.startswith("restart-"): require(a == ["docker", "restart", name[8:]] and a[-1] in (CORE, GNB, UE), "reset scope")
        elif name.startswith("health-"):
            require(a == ["docker", "inspect", "--format", "{{.State.Health.Status}}", name[7:]] and a[-1] in (CORE, GNB, UE), "health scope")
        elif name.endswith("-network"): require(a == ["docker", "network", "inspect", "safetwin5g-isolated"], "network scope")
        elif name.endswith("-containers"): require(a == ["docker", "inspect", "--format", contract["inspect_format"], *NAMES], "minimal inspect scope")
        elif name == "service-ping": pass  # exact identifier-bound argv replayed below
        else:
            require(len(a) == 10 and a[:4] == ["docker", "logs", "--timestamps", "--since"] and a[5] == "--until" and a[7:9] == ["--tail", "2000"] and a[9] in (CORE, GNB, UE) and name.endswith(a[9]), "log scope")
            require(row["merged_streams"] is True and at(a[4]) <= at(a[6]) <= at(row["started_at"]), "log interval")
            raw_logs(row["stdout"], a[4], a[6])
        expected_unit = "preflight" if row["sequence"] < one("trial-scope-network")["sequence"] else "final-rollback" if row["sequence"] >= one("switch-official-image")["sequence"] - 1 else "trace:control-before"
        require(row["unit_id"] == expected_unit, "unit command linkage")
    groups = []
    for row in rows:
        if not row["name"].startswith("health-"): continue
        if not groups or groups[-1][-1]["sequence"] + 1 != row["sequence"] or groups[-1][-1]["name"] != row["name"]: groups.append([])
        groups[-1].append(row)
    require(len(groups) == 14, "health wait count")
    for group in groups:
        require(group[-1]["stdout"].strip() == "healthy" and all(r["stdout"].strip() == "starting" for r in group[:-1])
                and (at(group[-1]["completed_at"]) - at(group[0]["started_at"])).total_seconds() <= 50, "bounded terminal healthy wait")
    base, derived = [json.loads(one(name)["stdout"]) for name in ("compose-base", "compose-derived")]
    for name in ("ueransim-gnb", "ueransim-ue"):
        require(derived["services"][name]["image"] == images["derived_tag"], "derived Compose image")
        derived["services"][name]["image"] = base["services"][name]["image"]
    require(base == derived, "two-image-only Compose override")
    require(one("repository-head")["stdout"].strip() == "26baf9cc17bc10f56830a91b2ee0adcb04955b45", "pre-execution commit")
    for role in ("official", "derived"):
        for name in (role + "-image", "switch-" + role + "-image"): require(one(name)["stdout"].strip() == images[role + "_image_id"], "image pin")
    scopes = []
    for label, role in (("preflight", "official"), ("switch-derived-verified", "derived"), ("trial-scope", "derived"), ("switch-official-verified", "official"), ("final-official", "official")):
        scopes.append(audit_scope(json.loads(one(label + "-network")["stdout"])[0], [json.loads(line) for line in one(label + "-containers")["stdout"].splitlines()], reference, role, images))
    for name in NAMES:
        if name in (UE, GNB): continue
        require(all(scope[name]["Id"] == scopes[0][name]["Id"] for scope in scopes), "untargeted container replacement")
    for name in ("preflight-eth0", "preparation-eth0", "rollback-inspect-eth0", "final-eth0"):
        for row in (r for r in rows if r["name"] == name):
            state = json.loads(row["stdout"]); require(len(state) == 1 and state[0]["kind"] == "noqueue" and state[0]["root"] is True, "neutral eth0")
    samples = [json.loads(line) for line in (directory / "samples.jsonl").read_text().splitlines()]
    require([s["identifier"] for s in samples] == list(range(10001, 10007)), "six distinct durable packet windows")
    require([s["command_first"] for s in samples] == [r["sequence"] for r in rows if r["name"] == "service-ping"], "no unretained ping")
    observations = []
    for i, sample in enumerate(samples):
        selected = [commands[n] for n in range(sample["command_first"], sample["command_last"]+1)]
        require([r["name"] for r in selected] == SAMPLE and selected[0]["argv"] == ["docker", "exec", UE, "ping", "-I", "uesimtun0", "-e", str(sample["identifier"]), "-s", "56", "-c", "5", "-i", "0.2", "-W", "1", "10.45.0.1"], "exact measured ping")
        require(all(r["unit_id"] == sample["unit_id"] for r in selected), "sample unit")
        metrics = raw_ping(selected[0]["stdout"]); address = source_address(selected[0]["stdout"])
        require(all(sample["metrics"][k] == v for k, v in metrics.items()) and metrics["reply_sequences"] == [1,2,3,4,5], "raw packet delivery")
        qdisc, state = json.loads(selected[1]["stdout"]), selected[2]["stdout"].split()
        targets = json.loads(selected[4]["stdout"])["data"]["activeTargets"]
        require(len(qdisc) == 1 and qdisc[0]["kind"] == "fq_codel" and qdisc[0]["root"] is True
                and len(state) == 1 and not any(c in state[0] for c in "TXZ") and not selected[3]["stdout"].strip()
                and len(targets) == 3 and {t["labels"]["job"] for t in targets} == {"open5gs-amf", "open5gs-smf", "open5gs-upf"}
                and all(t["health"] == "up" for t in targets), "raw service telemetry")
        require(all(sample["metrics"][k] == v for k, v in {"configured_packet_loss_pct": 0, "upf_process_running": 1, "stress_workers_count": 0, "prometheus_targets_up_count": 3}.items()), "reported service telemetry")
        require(sample["command_last"] - sample["command_first"] == 6 and at(sample["started_at"]) <= at(selected[0]["started_at"]) <= at(selected[0]["completed_at"]) <= at(sample["capture_until"]), "sample boundaries")
        for row, container in zip(selected[5:], (UE, GNB)):
            require(row["argv"] == ["docker", "logs", "--timestamps", "--since", sample["started_at"], "--until", sample["capture_until"], "--tail", "2000", container], "raw closed capture")
        item = {"identifier": sample["identifier"], "window": sample["window"], "source_address": address, "sent": 5, "received": 5, "source_matches_fixed_trace_filter": address == "10.45.0.2"}
        if i < 3:
            require(sample["errors"] == [ERROR] and sample["trace"] is None and sample["index"] == 0 and sample["window"] == ("baseline", "restore-ue", "restore-full")[i], "retained failed first window")
            item.update(partial_paths(selected[5]["stdout"], selected[6]["stdout"], sample["started_at"], sample["capture_until"], sample["identifier"]))
            require(item["observed_sequences"] == ([2,3,4,5], [], [3,4,5])[i], "retained missing-prefix pattern")
            require(address == ("10.45.0.2", "10.45.0.3", "10.45.0.2")[i], "observed source address")
            try: raw_paths(selected[5]["stdout"], selected[6]["stdout"], sample["started_at"], sample["capture_until"], sample["identifier"], metrics["reply_sequences"])
            except ValueError: pass
            else: raise ValueError("incomplete trace wrongly passed")
        else: require(replay_sample(sample, commands, False) and address == "10.45.0.2", "official final service")
        observations.append(item)
    require(trial["trial"] == config["trials"][0] and trial["errors"] == [ERROR] and trial["preparation_started"] is True
            and trial["protocol_execution_valid"] is False and trial["final_service_restored"] is False and trial["network_fix_validated"] is False
            and "baseline" not in trial and "post" not in trial and "exposure_started_at" not in trial, "stopped initial baseline")
    attempts = trial["restoration_attempts"]
    require([a["step"] for a in attempts] == ["restore-ue", "restore-full"] and all(a["clean"] is False and a["errors"] == ["missing packet or fingerprint mismatch"] for a in attempts), "failed trace-gated ladder retained")
    require(rollback["samples"] == samples[3:] and not rollback["errors"] and rollback["official_image_restored"] and rollback["service_restored"] and rollback["fresh_registration"] and rollback["fresh_pdu"], "official rollback")
    final_ue = one("final-official-" + UE)
    require(final_ue["argv"][4] == rollback["started_at"] and "Initial Registration is successful" in final_ue["stdout"] and "PDU Session establishment is successful" in final_ue["stdout"], "fresh final registration/PDU")
    require(summary["completed_trials"] == 1 and summary["protocol_execution_valid"] is False and summary["candidate_image_applied"] and summary["official_image_restored"] and summary["final_service_restored"] and not summary["errors"] and not summary["admission_budget_exceeded"], "negative terminal flags")
    for key in ("network_fix_validated", "confirmatory_data", "long_campaign_ready", "TNSM_ready", "live_actuation", "operator_validated", "hardware_measured"):
        require(summary[key] is False, "claim promotion")
    require(summary["evidence_label"] == "sandbox-measured" and summary["radio_evidence_label"] == "simulated", "measured evidence tier")
    require((at(summary["completed_at"])-at(approval["recorded_at"])).total_seconds() < 1500, "admission budget")
    return {"observation_audit_passed": True, "commands_replayed": len(rows), "samples_replayed": len(samples), "scope_snapshots": len(scopes),
            "attempted_assignments": 1, "valid_completed_assignments": 0, "fault_exposures": 0, "control_exposures": 0,
            "observations": observations, "final_official_packets_returned": 15, "final_official_packets_sent": 15,
            "official_images_restored": True, "protocol_execution_valid": False, "network_fix_validated": False,
            "evidence_label": "sandbox-measured", "radio_evidence_label": "simulated"}


def audit_clock(directory=CLOCK):
    directory = Path(directory); manifest(directory)
    summary, rows = read(directory / "summary.json"), read(directory / "commands.json")
    require(not summary["errors"] and summary["referenced_manifest_sha256"] == sha((RUN / "manifest.json").read_bytes()), "clock provenance")
    for name, digest in summary["source_sha256"].items(): require(sha((ROOT / name).read_bytes()) == digest, "clock source hash")
    expected = ["before-network", "before-containers"] + [f"clock-{name}-{i}" for name in (UE, GNB) for i in range(1,6)] + ["ue-address", "after-network", "after-containers"]
    require([r["name"] for r in rows] == expected and [r["sequence"] for r in rows] == list(range(1,16)), "read-only probe inventory")
    contract = read(ROOT / "config/experiments/reconnect-r3-command-contract.json")
    brackets = []
    for row in rows:
        for stream in ("stdout", "stderr"): require(sha(row[stream].encode()) == row[stream+"_sha256"], "probe byte linkage")
        require(row["returncode"] == 0 and row["timeout_seconds"] == 10, "probe result/bound")
        name, argv = row["name"], row["argv"]
        if name.endswith("-network"): require(argv == ["docker", "network", "inspect", "safetwin5g-isolated"], "probe network scope")
        elif name.endswith("-containers"): require(argv == ["docker", "inspect", "--format", contract["inspect_format"], *NAMES], "probe inspect scope")
        elif name == "ue-address": require(argv == ["docker", "exec", UE, "ip", "-j", "-4", "address", "show", "dev", "uesimtun0"], "probe IP scope")
        else:
            require(argv == ["docker", "exec", UE if "-ue-" in name else GNB, "date", "-u", "+%Y-%m-%dT%H:%M:%S.%NZ"], "date only, no time adjustment")
            start, end, remote = at(row["started_at"]), at(row["completed_at"]), at(row["stdout"].strip())
            require(start <= end and abs((end-start).total_seconds()-row["monotonic_elapsed_seconds"]) <= 0.05, "wall clock bracket")
            brackets.append({"command_sequence": row["sequence"], "container": argv[2], "container_minus_host_lower_seconds": (remote-end).total_seconds(), "container_minus_host_upper_seconds": (remote-start).total_seconds()})
    require(brackets == summary["clock_brackets"] and summary["all_remote_clocks_behind_host"] == all(r["container_minus_host_upper_seconds"] < 0 for r in brackets), "independent clock intervals")
    before, after = [[json.loads(line) for line in rows[index]["stdout"].splitlines()] for index in (1,14)]
    def canonical(containers):
        return {c["Name"]: {**c, "Mounts": sorted(c["Mounts"], key=lambda m:m["Destination"])} for c in containers}
    require(canonical(before) == canonical(after), "read-only probe changed service snapshot")
    images = read(ROOT / "config/experiments/reconnect-r3-images.json")
    reference = read(ROOT / "config/experiments/reconnect-r3-scope-reference.json")["containers"]
    audit_scope(json.loads(rows[0]["stdout"])[0], before, reference, "official", images)
    audit_scope(json.loads(rows[13]["stdout"])[0], after, reference, "official", images)
    require(summary["network_trials"] == 0 and summary["network_fix_validated"] is False and summary["live_actuation"] is False and summary["historical_missing_trace_recovered"] is False, "clock claim boundary")
    return {"clock_audit_passed": True, "read_only_commands": 15, "paired_clock_probes": 10,
            "all_clock_upper_bounds_negative": all(r["container_minus_host_upper_seconds"] < 0 for r in brackets),
            "minimum_offset_lower_seconds": min(r["container_minus_host_lower_seconds"] for r in brackets),
            "maximum_offset_upper_seconds": max(r["container_minus_host_upper_seconds"] for r in brackets),
            "official_service_snapshots_unchanged": True, "historical_missing_trace_recovered": False,
            "historical_prefix_cause": "clock clipping is supported but not uniquely proven by later probes",
            "evidence_label": "sandbox-measured", "network_fix_validated": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--run", default=str(RUN)); parser.add_argument("--clock", default=str(CLOCK))
    args = parser.parse_args()
    print(json.dumps({"run": audit_run(args.run), "clock": audit_clock(args.clock)}, indent=2))
