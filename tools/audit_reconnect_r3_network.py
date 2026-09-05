"""Independent raw ping, packet-path, command scope and trial/rollback replay.

Never import the execution runner or its ping/trace acceptance predicates.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
UE, GNB, CORE = "safetwin5g-ue", "safetwin5g-gnb", "safetwin5g-open5gs"
NAMES = [CORE, GNB, UE, "safetwin5g-mongodb", "safetwin5g-prometheus"]
BASE = ["docker", "compose", "-f", "sandbox/compose.yaml"]
DERIVED = BASE + ["-f", "sandbox/compose.reconnect-r3.yaml"]
UP = ["up", "-d", "--no-deps", "--no-build", "--pull", "never", "--force-recreate", "ueransim-gnb", "ueransim-ue"]
ORDER = ["trace:" + name for name in ("control-before", "drop-a", "drop-b", "control-after")]


def require(value, message):
    if not value: raise ValueError(message)


def sha(data): return hashlib.sha256(data).hexdigest()
def stamp(value): return datetime.fromisoformat(value)


def raw_ping(text):
    lines = text.splitlines()
    stats = [line for line in lines if "packets transmitted" in line]
    require(len(stats) == 1, "ping summary cardinality")
    fields = stats[0].split(", ")
    require(len(fields) in (3, 4) and fields[0] == "5 packets transmitted", "five transmitted packets required")
    require(re.fullmatch(r"[0-5] received", fields[1]) and re.fullmatch(r"(?:0|20|40|60|80|100)(?:\.0+)?% packet loss", fields[2]), "ping statistics syntax")
    if len(fields) == 4: require(re.fullmatch(r"time \d+ms", fields[3]), "ping time syntax")
    count, loss = int(fields[1].split()[0]), float(fields[2].split("%")[0])
    replies = []
    for line in lines:
        if "icmp_seq=" not in line: continue
        fields = line.split()
        require(len(fields) == 8 and fields[:4] == ["64", "bytes", "from", "10.45.0.1:"] and fields[-1] == "ms", "raw reply source/length")
        require(re.fullmatch(r"icmp_seq=[1-5]", fields[4]) and re.fullmatch(r"ttl=\d+", fields[5]) and re.fullmatch(r"time[=<][\d.]+", fields[6]), "raw reply syntax")
        replies.append(int(fields[4].split("=")[1]))
    require(len(replies) == len(set(replies)) == count and loss == 20 * (5 - count), "raw reply count/duplicates")
    return {"packets_transmitted": 5, "packets_received": count, "packet_loss_pct": loss, "reply_sequences": replies}


def raw_logs(text, since, until):
    lines, last, messages = text.splitlines(), None, []
    require(len(lines) < 2000, "log capture saturated")
    for line in lines:
        pair = line.split(" ", 1)
        require(len(pair) == 2, "missing Docker timestamp")
        at = stamp(pair[0]); require(stamp(since) <= at <= stamp(until) and (last is None or last <= at), "log scope/local order")
        last = at; messages.append(pair[1])
    return messages


def raw_paths(ue_text, gnb_text, since, until, identifier, replies):
    records = {seq: {} for seq in range(1, 6)}
    local = {"ue": {seq: [] for seq in records}, "gnb": {seq: [] for seq in records}}
    for component, text in (("ue", ue_text), ("gnb", gnb_text)):
        for message in raw_logs(text, since, until):
            if "ST3" not in message: continue
            require(message.count("ST3") == 1, "multiple trace markers")
            tokens = message.split("ST3 ", 1)[1].split(" ")
            keys = [token.split("=", 1)[0] for token in tokens]
            require(keys == "stage psi actor cm mm ps pending ipid id seq bytes fp".split(), "trace field schema")
            row = dict(token.split("=", 1) for token in tokens)
            stage = row.pop("stage")
            require(all(re.fullmatch(r"-?\d+", value) for value in row.values()), "trace integer syntax")
            row = {k: int(v) for k, v in row.items()}
            permitted = {"nas_in", "nas_idle", "nas_forward", "ue_rls"} if component == "ue" else {"gnb_in", "gnb_missing", "gnb_resource"}
            require(stage in permitted and row["id"] == identifier and row["psi"] == 1 and row["seq"] in records
                    and row["bytes"] == 84 and 0 <= row["ipid"] <= 65535 and 0 <= row["fp"] < 2**64, "trace identity/scope")
            seq = row["seq"]
            require(stage not in records[seq], "duplicate packet stage")
            records[seq][stage] = row; local[component][seq].append(stage)
    packets = []
    for seq, events in records.items():
        require(len({(r["ipid"], r["bytes"], r["fp"]) for r in events.values()}) == 1, "missing/mismatched packet fingerprint")
        if "nas_idle" in events:
            require(set(events) == {"nas_in", "nas_idle"} and local["ue"][seq] == ["nas_in", "nas_idle"] and seq not in replies, "idle path contradicts downstream/reply")
            require(events["nas_in"]["cm"] == events["nas_idle"]["cm"] == 0 and events["nas_idle"]["ps"] == 1, "idle state")
            fate = "nas_idle_nonretention_observed"
        else:
            terminal = "gnb_missing" if "gnb_missing" in events else "gnb_resource"
            require(set(events) == {"nas_in", "nas_forward", "ue_rls", "gnb_in", terminal}
                    and local["ue"][seq] == ["nas_in", "nas_forward", "ue_rls"] and local["gnb"][seq] == ["gnb_in", terminal], "incomplete/contradictory forwarding path")
            require(events["nas_in"]["cm"] == events["nas_forward"]["cm"] == 1 and events["nas_forward"]["ps"] == 1, "forward state")
            require(not (terminal == "gnb_missing" and seq in replies), "missing resource with reply")
            fate = "reply_observed" if seq in replies else "gnb_missing_resource_observed" if terminal == "gnb_missing" else "after_gnb_resource_unlocalized"
        packets.append({"sequence": seq, "fate": fate, "reply_observed": seq in replies})
    return {"trace_accounting_complete": True, "packets": packets, "received": len(replies), "sent": 5,
            "all_packets_returned": len(replies) == 5, "network_fix_validated": False}


def replay_sample(sample, commands, instrumented):
    rows = [commands[n] for n in range(sample["command_first"], sample["command_last"] + 1)]
    require([row["name"] for row in rows] == ["service-ping", "sample-qdisc", "upf-state", "stress-workers", "targets", "trace-" + UE, "trace-" + GNB], "sample command inventory")
    require(not sample["errors"] and all(row["unit_id"] == sample["unit_id"] for row in rows), "incomplete or cross-unit sample")
    identifier = sample["identifier"]
    require(10001 <= identifier <= 10099 and rows[0]["argv"] == ["docker", "exec", UE, "ping", "-I", "uesimtun0", "-e", str(identifier), "-s", "56", "-c", "5", "-i", "0.2", "-W", "1", "10.45.0.1"], "identified ping command")
    metrics = raw_ping(rows[0]["stdout"])
    qdisc = json.loads(rows[1]["stdout"])
    state = rows[2]["stdout"].split()
    targets = json.loads(rows[4]["stdout"])["data"]["activeTargets"]
    jobs = [target["labels"]["job"] for target in targets]
    metrics.update(configured_packet_loss_pct=0 if len(qdisc) == 1 and qdisc[0]["kind"] == "fq_codel" and qdisc[0].get("root") is True else None,
                   upf_process_running=int(len(state) == 1 and not any(letter in state[0] for letter in "TXZ")),
                   stress_workers_count=len(rows[3]["stdout"].splitlines()),
                   prometheus_targets_up_count=sum(target["health"] == "up" for target in targets)
                   if len(jobs) == 3 and set(jobs) == {"open5gs-amf", "open5gs-smf", "open5gs-upf"} else -1)
    require(metrics == sample["metrics"], "measured metrics differ from raw commands")
    since, until = sample["started_at"], sample["capture_until"]
    require(stamp(since) <= stamp(rows[0]["started_at"]) <= stamp(rows[0]["completed_at"]) <= stamp(until) <= stamp(rows[5]["started_at"]), "sample capture boundary")
    for row, container in zip(rows[5:], (UE, GNB)):
        require(row["argv"] == ["docker", "logs", "--timestamps", "--since", since, "--until", until, "--tail", "2000", container], "closed log interval")
    trace = raw_paths(rows[5]["stdout"], rows[6]["stdout"], since, until, identifier, metrics["reply_sequences"]) if instrumented else None
    if not instrumented:
        for row in rows[5:]: require(not any("ST3" in message for message in raw_logs(row["stdout"], since, until)), "instrumentation after official rollback")
    require(sample["trace"] == trace, "reported trace differs from independent packet path")
    required = {"packets_transmitted": 5, "packets_received": 5, "packet_loss_pct": 0, "configured_packet_loss_pct": 0,
                "upf_process_running": 1, "stress_workers_count": 0, "prometheus_targets_up_count": 3}
    return all(metrics[key] == value for key, value in required.items())


def audit_scope(network, containers, original, role, images):
    require(network["Name"] == "safetwin5g-isolated" and network["Internal"] is True
            and network["Labels"]["com.docker.compose.project"] == "safetwin5g-sandbox"
            and {r["Name"] for r in network["Containers"].values()} == set(NAMES), "isolated network scope")
    current = {row["Name"].lstrip("/"): row for row in containers}
    require(set(current) == set(NAMES) and len(containers) == 5, "five exact containers")
    require({key: value["Name"] for key, value in network["Containers"].items()} == {row["Id"]: name for name, row in current.items()}, "network attachment identity")
    versions = json.loads((ROOT / "sandbox/versions.lock.json").read_bytes())["components"]
    for name, row in current.items():
        hc, cfg = row["HostConfig"], row["Config"]
        require(row["State"]["Running"] is True and row["NetworkSettings"]["Networks"][network["Name"]]["NetworkID"] == network["Id"], "running/network ID")
        require(set(row["NetworkSettings"]["Networks"]) == {network["Name"]} and not hc["PortBindings"] and not hc["Privileged"]
                and not hc["PidMode"] and row["State"]["Health"]["Status"] == "healthy" and cfg["Labels"]["com.docker.compose.project"] == "safetwin5g-sandbox", "container isolation/health")
        require(set(hc.get("CapAdd") or []) == ({"CAP_NET_ADMIN", "CAP_NET_RAW"} if name in (CORE, UE) else set()) and not hc.get("CapDrop"), "capability scope")
        devices = [{"PathOnHost": "/dev/net/tun", "PathInContainer": "/dev/net/tun", "CgroupPermissions": "rwm"}] if name in (CORE, UE) else []
        require((hc.get("Devices") or []) == devices, "device scope")
        if name in (UE, GNB): require(row["Image"] == images[role + "_image_id"], "two-service selected image")
        elif original: require(row["Image"] == original[name]["Image"], "unrelated component image changed")
        if name in (CORE, GNB, UE):
            require(cfg["Labels"]["safetwin5g.upstream.commit"] == versions["open5gs" if name == CORE else "ueransim"]["commit"], "upstream pin")
        else: require(cfg["Image"].endswith("@" + versions["mongodb" if name.endswith("mongodb") else "prometheus"]["digest"]), "official image digest")
        destinations = [mount["Destination"] for mount in row["Mounts"]]
        require(len(destinations) == len(set(destinations)), "duplicate mount destinations")
        if original:
            reference = original[name]
            require(sorted(row["Mounts"], key=lambda m: m["Destination"]) == sorted(reference["Mounts"], key=lambda m: m["Destination"])
                    and hc == reference["HostConfig"] and all(cfg[k] == reference["Config"][k] for k in ("Cmd", "Entrypoint", "User", "WorkingDir")), "execution configuration changed")
    return current


def audit(run, allow_fixture=False):
    run = Path(run)
    read = lambda name: json.loads((run / name).read_bytes())
    manifest = read("manifest.json")["captured_file_sha256"]
    require(set(manifest) == {p.name for p in run.iterdir() if p.is_file() and p.name != "manifest.json"}, "artifact inventory")
    for name, digest in manifest.items(): require(Path(name).name == name and sha((run / name).read_bytes()) == digest, "artifact hash")
    design, approval, summary = read("design.json"), read("approval.json"), read("summary.json")
    fixture = design["execution_mode"] == "fixture"
    require(design["execution_mode"] in ("fixture", "sandbox") and (not fixture or allow_fixture), "fixture cannot pass as sandbox evidence")
    require(design["transport"] == ("fake-docker-no-io" if fixture else "docker-cli"), "transport evidence tier")
    if fixture: require(summary["actual_docker_commands_executed"] == 0, "fixture must perform no Docker commands")
    images = json.loads((ROOT / "config/experiments/reconnect-r3-images.json").read_bytes())
    config = json.loads((ROOT / "config/experiments/reconnect-r3-trace.json").read_bytes())
    require(design["images"] == images and design["config"] == config, "image/design contract")
    frozen = json.loads((ROOT / "config/experiments/reconnect-r3-execution-lock.json").read_bytes())
    require(frozen["lock_id"] == "reconnect-r3-execution-v1" and len(frozen["source_sha256"]) >= 16
            and design["source_sha256"] == frozen["source_sha256"], "frozen execution inventory")
    for name, digest in design["source_sha256"].items():
        path = (ROOT / name).resolve(); require(path.is_relative_to(ROOT) and sha(path.read_bytes()) == digest, "source drift")
    contract = json.loads((ROOT / "config/experiments/reconnect-r3-command-contract.json").read_bytes())
    require(approval["status"] == "approved" and approval["environment"] == "sandbox" and approval["type"] == "standing-project-authorization"
            and approval["trials"] == config["trials"] and approval["containers"] == [CORE, GNB, UE] and approval["image_containers"] == [GNB, UE]
            and approval["image_ids"] == [images["official_image_id"], images["derived_image_id"]] and approval["rollback_plan"]
            and approval["operator_validation"] is False and approval["live_actuation"] is False, "approval scope")
    rows = [json.loads(line) for line in (run / "commands.jsonl").read_text().splitlines()]
    require([r["sequence"] for r in rows] == list(range(1, len(rows) + 1)), "command sequence")
    unit_order = ["preflight", *ORDER, "final-rollback"]
    ranks = [unit_order.index(r["unit_id"]) for r in rows]
    require(ranks == sorted(ranks), "unit execution order")
    commands = {r["sequence"]: r for r in rows}
    def one(name, unit=None):
        found = [r for r in rows if r["name"] == name and (unit is None or r["unit_id"] == unit)]
        require(len(found) == 1, "missing/duplicate command: " + name); return found[0]
    previous = stamp(approval["recorded_at"])
    for row in rows:
        a, name = row["argv"], row["name"]
        require(previous <= stamp(row["started_at"]) <= stamp(row["completed_at"]), "approval/command chronology")
        previous = stamp(row["completed_at"])
        require(0 < row["timeout_seconds"] <= 35 and (row["timeout_seconds"] == 35 or name.startswith("health-"))
                and sha(row["stdout"].encode()) == row["stdout_sha256"] and sha(row["stderr"].encode()) == row["stderr_sha256"], "command byte linkage/bounds")
        allowed = contract["fixed_commands"].get(name)
        if allowed is not None: require(a == allowed, "fixed command scope: " + name)
        elif name.startswith("restart-"):
            require(a == ["docker", "restart", name.removeprefix("restart-")] and a[2] in (CORE, GNB, UE), "restart scope")
        elif name.startswith("health-"):
            require(a == ["docker", "inspect", "--format", "{{.State.Health.Status}}", name.removeprefix("health-")] and a[-1] in (CORE, GNB, UE), "health scope")
        elif name.endswith("-network"):
            require(a == ["docker", "network", "inspect", "safetwin5g-isolated"], "network inspection scope")
        elif name.endswith("-containers"):
            require(a == ["docker", "inspect", "--format", contract["inspect_format"], *NAMES], "minimal inspection scope")
        elif a[:2] == ["docker", "logs"]:
            require(len(a) == 10 and a[:4] == ["docker", "logs", "--timestamps", "--since"] and a[5] == "--until"
                    and a[7:9] == ["--tail", "2000"] and a[9] in (CORE, GNB, UE) and name.endswith(a[9]), "bounded log scope")
            require(stamp(a[4]) <= stamp(a[6]) <= stamp(row["started_at"]) and row["merged_streams"] is True, "log capture interval/stream handling")
        elif name == "service-ping":
            require(len(a) == 17 and a[0:7] == ["docker", "exec", UE, "ping", "-I", "uesimtun0", "-e"] and a[8:] == ["-s", "56", "-c", "5", "-i", "0.2", "-W", "1", "10.45.0.1"], "fixed ping scope")
        else: raise ValueError("unknown command: " + name)
        accepted = [0, 1] if name == "service-ping" else [0, 2] if name == "ping-help" else [0]
        require(row["accepted_returncodes"] == accepted and row["returncode"] in accepted, "failed or loosened command acceptance")
        require(row["unit_id"] in ["preflight", *ORDER, "final-rollback"], "unknown unit")
    base_cfg, derived_cfg = [json.loads(one(name)["stdout"]) for name in ("compose-base", "compose-derived")]
    for service in ("ueransim-gnb", "ueransim-ue"):
        require(derived_cfg["services"][service]["image"] == images["derived_tag"], "override image")
        derived_cfg["services"][service]["image"] = base_cfg["services"][service]["image"]
    require(base_cfg == derived_cfg, "two-image-only override")
    original = json.loads((ROOT / "config/experiments/reconnect-r3-scope-reference.json").read_bytes())["containers"]; scopes = 0
    for row in rows:
        if not row["name"].endswith("-containers"): continue
        label = row["name"].removesuffix("-containers")
        net = json.loads(one(label + "-network", row["unit_id"])["stdout"])[0]
        role = "official" if label in ("preflight", "switch-official-verified", "final-official") else "derived"
        current = audit_scope(net, [json.loads(line) for line in row["stdout"].splitlines()], original, role, images)
        if scopes == 0: require(label == "preflight", "official first scope")
        scopes += 1
    require(scopes == 8, "eight required scope snapshots")
    samples = [json.loads(line) for line in (run / "samples.jsonl").read_text().splitlines()]
    require([s["identifier"] for s in samples] == list(range(10001, 10001 + len(samples))), "identifier reuse/gap")
    require(len({s["command_first"] for s in samples}) == len(samples), "duplicate sample command assignment")
    require({s["command_first"] for s in samples} == {r["sequence"] for r in rows if r["name"] == "service-ping"}, "unretained or extra ping")
    clean = {s["identifier"]: replay_sample(s, commands, s["unit_id"] != "final-rollback") for s in samples}
    def window(uid, label, reported):
        selected = [s for s in samples if s["unit_id"] == uid and s["window"] == label]
        require(len(selected) == 3 and [s["index"] for s in selected] == [0, 1, 2] and selected == reported, "durable window linkage")
        return all(clean[s["identifier"]] for s in selected)
    def neutral(name, uid=None):
        qdisc = json.loads(one(name, uid)["stdout"])
        require(len(qdisc) == 1 and qdisc[0]["kind"] == "noqueue" and qdisc[0].get("root") is True, "neutral eth0")
    def messages(label, uid, since=None):
        result = {}
        for container in (CORE, GNB, UE):
            row = one(label + "-" + container, uid)
            if since is not None: require(row["argv"][4] == since, "event log start")
            result[container] = "\n".join(raw_logs(row["stdout"], row["argv"][4], row["argv"][6]))
        return result
    neutral("preflight-eth0")
    require(one("ping-help")["sequence"] < one("switch-derived")["sequence"], "preflight before switch")
    for role in ("official", "derived"):
        require(one(role + "-image")["stdout"].strip() == images[role + "_image_id"] and one("switch-" + role + "-image")["stdout"].strip() == images[role + "_image_id"], "measured image ID")
    count = len(list(run.glob("trial-*.json")))
    # A stopped/partial run is preserved, but cannot pass this complete-protocol
    # acceptance audit. Its actual error is returned; never manufacture success.
    require(count == summary["completed_trials"] == 4, "incomplete four-trial diagnostic")
    packet_counts = []
    for index, uid in enumerate(ORDER, 1):
        trial = read(f"trial-{index:02d}.json"); drop = uid in ORDER[1:3]
        require(trial["trial"] == config["trials"][index-1] and not trial["errors"] and trial["protocol_execution_valid"] is True and trial["network_fix_validated"] is False, "invalid or promoted trial")
        require(window(uid, "baseline", trial["baseline"]), "baseline not clean")
        prep = messages("preparation", uid, trial["started_at"])
        require("Initial Registration is successful" in prep[UE] and "PDU Session establishment is successful" in prep[UE] and trial["fresh_registration"] and trial["fresh_pdu"], "fresh registration/PDU")
        for name in ("preparation-eth0", "baseline-eth0", "post-exposure-eth0"): neutral(name, uid)
        exposure = one("bounded-link-drop" if drop else "control-wait", uid)
        require(trial["baseline"][-1]["command_last"] < exposure["sequence"] < trial["post"][0]["command_first"], "exposure order")
        require(stamp(trial["exposure_started_at"]) <= stamp(exposure["started_at"]) <= stamp(exposure["completed_at"]) <= stamp(trial["exposure_completed_at"]), "exposure timestamp linkage")
        require((stamp(trial["settling_completed_at"]) - stamp(trial["settling_started_at"])).total_seconds() >= 5
                and stamp(trial["exposure_completed_at"]) <= stamp(trial["settling_started_at"]) <= stamp(trial["settling_completed_at"]) <= stamp(trial["post"][0]["started_at"]), "fixed settling interval")
        if drop:
            require(exposure["stdout"] == trial["fault_transcript"], "fault transcript linkage")
            lines = exposure["stdout"].splitlines(); require(len(lines) == 4, "fault transcript shape")
            require(8 <= (stamp(lines[2]) - stamp(lines[0])).total_seconds() < 15, "eight-second fault interval")
            during, after = json.loads(lines[1]), json.loads(lines[3])
            require(len(during) == 1 and during[0]["kind"] == "netem" and during[0]["handle"] == "7157:" and during[0]["root"] is True
                    and during[0]["options"]["loss-random"]["loss"] == 1 and len(after) == 1 and after[0]["kind"] == "noqueue" and after[0]["root"] is True, "fault and trap state")
        else: require(8 <= (stamp(exposure["completed_at"]) - stamp(exposure["started_at"])).total_seconds() < 35, "control duration")
        recovered = window(uid, "post", trial["post"])
        post = messages("post", uid, trial["exposure_started_at"])
        require(trial["recovery_15_of_15"] == recovered and trial["trace_accounting_complete"] is True, "recovery versus trace flags")
        require(trial["service_accept_observed"] == ("Service Accept received" in post[UE]) and trial["initial_context_observed"] == ("Initial Context Setup Request received" in post[GNB]), "context markers")
        expected_restarts = [CORE, GNB, UE]
        if drop:
            require(1 <= len(trial["restoration_attempts"]) <= 2, "restoration ladder count")
            for j, attempt in enumerate(trial["restoration_attempts"]):
                step = ("restore-ue", "restore-full")[j]; require(attempt["step"] == step, "restoration order")
                expected_restarts += [UE] if j == 0 else [CORE, GNB, UE]
                restored = window(uid, step, attempt["samples"])
                logs = messages(step, uid, attempt["started_at"])
                fresh = "Initial Registration is successful" in logs[UE] and "PDU Session establishment is successful" in logs[UE]
                require(attempt["clean"] == (restored and fresh and not attempt["errors"]), "restoration result")
                if attempt["clean"]: neutral(step + "-eth0", uid)
                if j + 1 < len(trial["restoration_attempts"]): require(not attempt["clean"], "retry after successful restoration")
            require(trial["restoration_attempts"][-1]["clean"], "final trial restoration")
        else: require(recovered and "Radio link failure detected" not in post[UE] and not trial["restoration_attempts"], "no-fault control")
        restarts = [r for r in rows if r["unit_id"] == uid and r["argv"][:2] == ["docker", "restart"]]
        require([r["argv"][2] for r in restarts] == expected_restarts and one("trial-scope-containers", uid)["sequence"] < restarts[0]["sequence"] < restarts[2]["sequence"] < trial["baseline"][0]["command_first"], "preparation/reset sequence")
        require(all(r["sequence"] > one("post-" + UE, uid)["sequence"] for r in restarts[3:]), "restoration hidden before post measurements")
        packet_counts.append({"trial": uid, "received": sum(s["metrics"]["packets_received"] for s in trial["post"]), "sent": 15, "recovery_15_of_15": recovered})
    rollback = read("final-rollback.json")
    require(not rollback["errors"] and rollback["official_image_restored"] and rollback["service_restored"] and window("final-rollback", "final-official", rollback["samples"]), "final official rollback")
    logs = messages("final-official", "final-rollback", rollback["started_at"])
    require("Initial Registration is successful" in logs[UE] and "PDU Session establishment is successful" in logs[UE], "final fresh registration/PDU")
    neutral("final-eth0", "final-rollback")
    require([r["argv"][2] for r in rows if r["unit_id"] == "final-rollback" and r["argv"][:2] == ["docker", "restart"]] == [CORE, GNB, UE], "final reset order")
    switches = [r for r in rows if r["argv"][:2] == ["docker", "compose"] and "up" in r["argv"]]
    require([r["argv"] for r in switches] == [DERIVED + UP, BASE + UP] and switches[-1]["unit_id"] == "final-rollback", "two-service replacement/rollback")
    final_resets = [r for r in rows if r["unit_id"] == "final-rollback" and r["argv"][:2] == ["docker", "restart"]]
    require(switches[-1]["sequence"] < final_resets[0]["sequence"] < final_resets[-1]["sequence"] < rollback["samples"][0]["command_first"], "official switch before final reset/measurements")
    require(summary["protocol_execution_valid"] and not summary["errors"] and summary["candidate_image_applied"] and summary["official_image_restored"] and summary["final_service_restored"] and not summary["admission_budget_exceeded"], "terminal gate")
    require((stamp(summary["completed_at"]) - stamp(approval["recorded_at"])).total_seconds() <= 1501, "overall admission bound")
    for key in ("network_fix_validated", "confirmatory_data", "long_campaign_ready", "TNSM_ready", "live_actuation", "operator_validated", "hardware_measured"):
        require(summary[key] is False, "claim promotion: " + key)
    require(summary["evidence_label"] == ("fixture" if fixture else "sandbox-measured") and summary["radio_evidence_label"] == "simulated", "evidence tier")
    return {"audit_passed": True, "execution_mode": design["execution_mode"], "protocol_execution_valid": True,
            "completed_trials": 4, "commands_replayed": len(rows), "samples_replayed": len(samples), "scope_snapshots": scopes,
            "post_packet_counts": packet_counts, "official_image_restored": True, "network_fix_validated": False,
            "TNSM_ready": False, "evidence_label": summary["evidence_label"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--run", required=True); parser.add_argument("--allow-fixture", action="store_true")
    args = parser.parse_args()
    try: print(json.dumps(audit(args.run, args.allow_fixture), indent=2))
    except (ValueError, KeyError, IndexError, OSError) as exc:
        print(json.dumps({"audit_passed": False, "error": str(exc), "network_fix_validated": False})); raise SystemExit(2)
