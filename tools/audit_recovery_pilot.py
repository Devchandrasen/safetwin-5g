"""Independent raw-command replay and provenance audit, not a method comparison."""
from datetime import datetime
import argparse
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
ORDER = ["primitive_cleanup", "ue_restart", "core_gnb_ue_restart"]
JOBS = {"open5gs-amf", "open5gs-smf", "open5gs-upf"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replay_sample(sample, commands):
    rows = [commands[n] for n in sample["command_sequences"]]
    require([r["name"] for r in rows] == ["service-ping", "qdisc", "upf-state", "stress-workers", "targets"], "sample command linkage")
    require(all(r["returncode"] == 0 for r in rows[1:]) and rows[0]["returncode"] in (0, 1), "sample command return codes")
    match = re.search(r"(\d+) packets transmitted, (\d+) received, ([\d.]+)% packet loss", rows[0]["stdout"])
    require(match is not None, "missing raw ping summary")
    sent, received, loss = float(match[1]), float(match[2]), float(match[3])
    metrics = sample["metrics"]
    require((sent, received, loss) == (metrics["packets_transmitted"], metrics["packets_received"], metrics["packet_loss_pct"]), "raw ping differs from metrics")
    qdisc = rows[1]["stdout"]
    configured = 0.0 if "fq_codel" in qdisc and "loss" not in qdisc else None
    state = rows[2]["stdout"].strip()
    running = 1.0 if state and "T" not in state else 0.0
    workers = len(rows[3]["stdout"].splitlines())
    targets = json.loads(rows[4]["stdout"])["data"]["activeTargets"]
    target_count = sum(t["health"] == "up" for t in targets) if {t["labels"]["job"] for t in targets} == JOBS else -1
    require((configured, running, workers, target_count) == (metrics["configured_packet_loss_pct"], metrics["upf_process_running"], metrics["stress_workers_count"], metrics["prometheus_targets_up_count"]), "raw service state differs from metrics")
    return sent == received == 5 and 0 <= loss <= 1 and configured == 0 and running == 1 and workers == 0 and target_count == 3


def audit(run):
    run = Path(run)
    read = lambda name: json.loads((run / name).read_text(encoding="utf-8"))
    manifest = read("manifest.json")["captured_file_sha256"]
    require(set(manifest) == {p.name for p in run.iterdir() if p.is_file() and p.name != "manifest.json"}, "manifest inventory")
    for name, expected in manifest.items():
        require(Path(name).name == name and digest(run / name) == expected, "manifest mismatch: " + name)
    design, approval, summary = read("design.json"), read("approval.json"), read("summary.json")
    require(design["source_hash_mode"] == "utf8-lf-normalized", "source hash mode")
    for name, expected in design["source_sha256"].items():
        path = (ROOT / name).resolve()
        require(path.is_relative_to(ROOT), "source outside repository")
        require(hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest() == expected, "source changed: " + name)
    config = design["config"]
    require(config == json.loads((ROOT / "config/experiments/recovery-pilot-r1.json").read_text()), "design config changed")
    trials = design["trials"]
    require([t["hold_seconds"] for t in trials] == [0, 1, 30, 30, 45, 0], "fixed trial sequence")
    require(approval["status"] == "approved" and approval["environment"] == "sandbox" and bool(approval["rollback_plan"]), "sandbox approval")
    require(approval["trial_ids"] == [t["trial_id"] for t in trials] and approval["trial_holds"] == {t["trial_id"]: t["hold_seconds"] for t in trials}, "trial-scoped approval")
    require(set(approval["containers"]) == {"safetwin5g-open5gs", "safetwin5g-gnb", "safetwin5g-ue"}, "approval container scope")
    rows = [json.loads(line) for line in (run / "commands.jsonl").read_text().splitlines()]
    require([r["sequence"] for r in rows] == list(range(1, len(rows) + 1)), "command sequence")
    for row in rows:
        require(datetime.fromisoformat(approval["recorded_at"]) <= datetime.fromisoformat(row["started_at"]) <= datetime.fromisoformat(row["completed_at"]), "approval/command timing")
        require(hashlib.sha256(row["stdout"].encode()).hexdigest() == row["stdout_sha256"], "command stdout hash")
        argv = row["argv"]
        if argv[:2] in (["docker", "exec"], ["docker", "restart"]):
            require(argv[2] in approval["containers"], "out-of-scope container command")
    preflight = {r["name"]: r for r in rows if r["unit_id"] == "preflight"}
    net = json.loads(preflight["isolated-network"]["stdout"])[0]
    expected_names = set(approval["containers"]) | {"safetwin5g-mongodb", "safetwin5g-prometheus"}
    require(net["Name"] == "safetwin5g-isolated" and net["Internal"] is True and {v["Name"] for v in net["Containers"].values()} == expected_names, "isolated network preflight")
    identities = json.loads(preflight["container-identities"]["stdout"])
    versions = json.loads((ROOT / "sandbox/versions.lock.json").read_text())["components"]
    policy = json.loads((ROOT / "config/actions.json").read_text())
    require(policy["allow_live_actuation"] is False and policy["require_human_approval"] is True, "fail-closed policy")
    require({c["Name"].lstrip("/") for c in identities} == expected_names, "container identity inventory")
    for container in identities:
        require(set(container["NetworkSettings"]["Networks"]) == {net["Name"]}
                and not container["HostConfig"]["PortBindings"] and not container["HostConfig"]["Privileged"]
                and container["Config"]["Labels"]["com.docker.compose.project"] == "safetwin5g-sandbox"
                and container["State"]["Health"]["Status"] == "healthy", "container preflight")
        name = container["Name"].lstrip("/")
        if name in approval["containers"]:
            component = "open5gs" if name == "safetwin5g-open5gs" else "ueransim"
            require(container["Config"]["Labels"]["safetwin5g.upstream.commit"] == versions[component]["commit"], "source pin")
        else:
            component = "mongodb" if name.endswith("mongodb") else "prometheus"
            require(container["Config"]["Image"].endswith("@" + versions[component]["digest"]), "image pin")
    commands = {r["sequence"]: r for r in rows}
    samples = [json.loads(line) for line in (run / "samples.jsonl").read_text().splitlines()]
    # Replay ALL samples, including failed escalation steps, before accepting a bundle.
    sample_clean = {s["command_sequences"][0]: replay_sample(s, commands) for s in samples}
    require(len(sample_clean) == len(samples), "duplicate sample linkage")
    require({r["sequence"] for r in rows if r["name"] == "service-ping"} == set(sample_clean), "unretained or extra service sample")
    require(len(list(run.glob("trial-*.json"))) == 6, "incomplete pilot")
    failed_attempts = 0
    selected = []
    for i, expected in enumerate(trials, 1):
        trial = read(f"trial-{i:02d}.json")
        require(trial["trial"] == expected and trial["approval_id"] == approval["approval_id"], "trial identity")
        require(trial["errors"] == [] and trial["fault_state_verified"] is True, "trial errors/fault verification")
        def clean_window(window, label):
            require(len(window) == 3, "three samples required")
            originals = [s for s in samples if s["trial_id"] == expected["trial_id"] and s["window"] == label]
            require(len(originals) == 3, "durable sample count")
            for sample, original in zip(window, originals):
                require(all(original[k] == v for k, v in sample.items()), "trial sample differs from durable stream")
                require(all(commands[n]["unit_id"] == expected["trial_id"] for n in sample["command_sequences"]), "cross-trial sample")
            return all(sample_clean[s["command_sequences"][0]] for s in window)
        require(clean_window(trial["baseline"], "baseline"), "unclean baseline")
        attempts = trial["recovery_attempts"]
        require([a["step"] for a in attempts] == ORDER[:len(attempts)] and 1 <= len(attempts) <= 3, "recovery order")
        for j, attempt in enumerate(attempts):
            observed_clean = clean_window(attempt["samples"], attempt["step"]) if "samples" in attempt else False
            require(attempt["clean"] == observed_clean, "false recovery flag")
            require(not observed_clean or j == len(attempts) - 1, "continued after clean recovery")
            failed_attempts += not observed_clean
        require(attempts[-1]["clean"] and trial["passed"] and trial["recovery_clean"], "unclean final recovery")
        selected.append(attempts[-1]["step"])
        unit_commands = [r for r in rows if r["unit_id"] == expected["trial_id"]]
        expected_restarts = ([] if len(attempts) == 1 else ["safetwin5g-ue"] if len(attempts) == 2 else ["safetwin5g-ue", "safetwin5g-open5gs", "safetwin5g-gnb", "safetwin5g-ue"])
        actual_restarts = [r for r in unit_commands if r["argv"][:2] == ["docker", "restart"]]
        require([r["argv"][2] for r in actual_restarts] == expected_restarts, "exact restart order")
        require(all(r["returncode"] == 0 for r in actual_restarts), "restart command failed")
        stops = [r for r in unit_commands if r["name"] == "suspend-upf"]
        if expected["hold_seconds"] == 0:
            require(not stops and selected[-1] == "primitive_cleanup", "no-fault control mutated or escalated")
        else:
            require(len(stops) == 1 and stops[0]["returncode"] == 0, "single STOP required")
            state = next(r for r in unit_commands if r["name"] == "verify-stopped-upf")
            resume = next(r for r in unit_commands if r["name"] == "primary-resume-upf")
            require("T" in state["stdout"] and state["returncode"] == resume["returncode"] == 0, "STOP/CONT not verified")
            require(resume["argv"][-1] == stops[0]["argv"][-1], "STOP/CONT PID mismatch")
            require(stops[0]["sequence"] < state["sequence"] < resume["sequence"], "STOP/CONT command order")
            require(expected["hold_seconds"] <= trial["stop_to_cont_command_window_seconds"] < 65, "assigned suspension window")
            require(trial["watchdog_terminal_state"] == "disarmed", "watchdog not safely settled")
            barrier = [r for r in unit_commands if r["name"] == "watchdog-barrier"][-1]
            require(barrier["stdout"].strip() == "disarmed", "raw watchdog not settled")
            require(barrier["sequence"] < attempts[0]["samples"][0]["command_sequences"][0], "watchdog barrier order")
    require(summary["planned_trials"] == summary["completed_trials"] == 6 and summary["passed"] and not summary["errors"] and summary["final_service_restored"], "summary acceptance")
    require(summary["evidence_label"] == "sandbox-measured" and summary["radio_evidence_label"] == "simulated", "evidence tiers")
    for key in ("confirmatory_data", "long_campaign_ready", "hardware_measured", "operator_validated", "live_actuation", "TNSM_ready", "admission_budget_exceeded"):
        require(summary[key] is False, "claim or budget gate: " + key)
    return {"passed": True, "trials": 6, "raw_samples_replayed": len(samples),
            "commands": len(rows), "failed_recovery_attempts_retained": failed_attempts,
            "selected_recovery_steps": selected, "long_campaign_ready": False,
            "TNSM_ready": False, "manifest_sha256": digest(run / "manifest.json")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(audit(args.run), indent=2))
    except (ValueError, KeyError, OSError, StopIteration) as exc:
        print(json.dumps({"passed": False, "error": str(exc)}, indent=2))
        raise SystemExit(2)
