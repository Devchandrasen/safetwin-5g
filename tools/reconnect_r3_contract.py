"""Serialize fixed command spellings for an independently implemented auditor."""
import json
from sandbox.run_reconnect_r3 import BASE, DERIVED, UP, FAULT_SCRIPT, CONFIG_PATH, IMAGE_PATH
from sandbox.reconnect_r3_measurement import CORE, UE, INSPECT_FORMAT


def command_contract():
    images = json.loads(IMAGE_PATH.read_bytes())
    commands = {
        "repository-head": ["git", "rev-parse", "HEAD"],
        "docker-version": ["docker", "version", "--format", "{{json .Server}}"],
        "compose-base": BASE + ["config", "--format", "json"], "compose-derived": DERIVED + ["config", "--format", "json"],
        "switch-derived": DERIVED + UP, "switch-official": BASE + UP,
        "ping-help": ["docker", "exec", UE, "ping", "-h"],
        "bounded-link-drop": ["docker", "exec", UE, "timeout", "15", "sh", "-lc", FAULT_SCRIPT],
        "control-wait": ["docker", "exec", UE, "sleep", "8"],
        "sample-qdisc": ["docker", "exec", UE, "tc", "-j", "qdisc", "show", "dev", "uesimtun0"],
        "upf-state": ["docker", "exec", CORE, "sh", "-lc", 'pid=$(pgrep -x open5gs-upfd); ps -o stat= -p "$pid"'],
        "stress-workers": ["docker", "exec", CORE, "sh", "-lc", "pgrep -x yes || true"],
        "targets": ["docker", "exec", CORE, "curl", "--fail", "--silent", "http://10.53.0.6:9090/api/v1/targets"],
        "emergency-clear-owned-qdisc": ["docker", "exec", UE, "tc", "qdisc", "del", "dev", "eth0", "root", "handle", "7157:"],
    }
    for name in ("preflight-eth0", "preparation-eth0", "baseline-eth0", "post-exposure-eth0", "rollback-inspect-eth0", "rollback-verify-eth0", "restore-ue-eth0", "restore-full-eth0", "final-eth0"):
        commands[name] = ["docker", "exec", UE, "tc", "-j", "qdisc", "show", "dev", "eth0"]
    for role in ("official", "derived"):
        for name in (role + "-image", "switch-" + role + "-image"):
            commands[name] = ["docker", "image", "inspect", "--format", "{{.Id}}", images[role + "_tag"]]
    return {"experiment_id": json.loads(CONFIG_PATH.read_bytes())["experiment_id"], "inspect_format": INSPECT_FORMAT, "fixed_commands": commands}


if __name__ == "__main__": print(json.dumps(command_contract(), indent=2))
