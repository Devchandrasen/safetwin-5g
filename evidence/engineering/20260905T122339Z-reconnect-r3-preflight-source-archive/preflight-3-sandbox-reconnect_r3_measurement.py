"""Fixed packet/trace collection contract. Does not expose a mutation endpoint."""
from datetime import datetime
import json
import re

from tools.reconnect_r3_trace import parse as parse_trace, account_window

UE = "safetwin5g-ue"
GNB = "safetwin5g-gnb"
CORE = "safetwin5g-open5gs"
CONTAINERS = [CORE, GNB, UE, "safetwin5g-mongodb", "safetwin5g-prometheus"]
NETWORK = "safetwin5g-isolated"
HOST_FIELDS = ("CapAdd", "CapDrop", "Devices", "Sysctls", "Binds", "SecurityOpt", "Privileged", "PortBindings", "NetworkMode", "PidMode", "IpcMode", "ReadonlyRootfs", "RestartPolicy")


def object_format(fields):
    return "{" + ",".join(json.dumps(key) + ":{{json " + expr + "}}" for key, expr in fields.items()) + "}"


# No Env, arbitrary labels, health logs, or unrelated containers are collected.
CONFIG_FORMAT = object_format({key: ".Config." + key for key in ("Image", "Cmd", "Entrypoint", "User", "WorkingDir")})
LABEL_FORMAT = object_format({key: '(index .Config.Labels "' + key + '")' for key in
                              ("com.docker.compose.project", "safetwin5g.upstream.commit", "safetwin5g.derived.revision")})
INSPECT_FORMAT = (object_format({key: "." + key for key in ("Id", "Name", "Image", "RestartCount", "Mounts")})[:-1]
                  + ',"Config":' + CONFIG_FORMAT[:-1] + ',"Labels":' + LABEL_FORMAT + '}'
                  + ',"HostConfig":' + object_format({key: '(index .HostConfig "' + key + '")' for key in HOST_FIELDS})
                  + ',"NetworkSettings":{"Networks":{{json .NetworkSettings.Networks}}}'
                  + ',"State":{"StartedAt":{{json .State.StartedAt}},"Running":{{json .State.Running}},'
                  + '"Health":{"Status":{{json .State.Health.Status}}}}}')


def ping_argv(identifier):
    if type(identifier) is not int or not 10001 <= identifier <= 10099:
        raise ValueError("ICMP identifier budget exhausted or invalid")
    return ["docker", "exec", UE, "ping", "-I", "uesimtun0", "-e", str(identifier), "-s", "56", "-c", "5", "-i", "0.2", "-W", "1", "10.45.0.1"]


def ping_result(text):
    summaries = re.findall(r"(?m)^5 packets transmitted, (\d+) received, ([\d.]+)% packet loss(?:, time \d+ms)?$", text)
    if len(summaries) != 1 or text.count("packets transmitted") != 1:
        raise ValueError("exactly one five-packet summary required")
    count, loss = int(summaries[0][0]), float(summaries[0][1])
    replies = []
    for line in text.splitlines():
        if "icmp_seq=" not in line: continue
        match = re.fullmatch(r"64 bytes from 10\.45\.0\.1: icmp_seq=([1-5]) ttl=\d+ time[=<][\d.]+ ms", line)
        if not match: raise ValueError("unexpected ping reply/error/duplicate line")
        replies.append(int(match[1]))
    if len(replies) != len(set(replies)) or len(replies) != count or count > 5 or loss != (5 - count) * 20:
        raise ValueError("raw replies disagree with summary")
    return {"packets_transmitted": 5, "packets_received": count, "packet_loss_pct": loss, "reply_sequences": replies}


def log_text(text, since, until):
    lines = text.splitlines()
    if len(lines) >= 2000: raise ValueError("saturated log capture")
    first, last = datetime.fromisoformat(since), datetime.fromisoformat(until)
    messages, previous = [], None
    for line in lines:
        stamp, separator, body = line.partition(" ")
        if not separator: raise ValueError("untimestamped Docker log line")
        try: at = datetime.fromisoformat(stamp)
        except ValueError as exc: raise ValueError("invalid Docker timestamp") from exc
        if not first <= at <= last or (previous is not None and at < previous):
            raise ValueError("out-of-scope or unordered component log")
        previous = at; messages.append(body)
    return "\n".join(messages)


def trace_result(ue, gnb, since, until, identifier, replies):
    rows = parse_trace(log_text(ue, since, until), "ue") + parse_trace(log_text(gnb, since, until), "gnb")
    if any(row["id"] != identifier for row in rows):
        raise ValueError("another identifier in the closed capture")
    if any(row["bytes"] != 84 for row in rows): raise ValueError("fixed 56-byte ping payload required")
    return account_window(rows, identifier, replies)


def state_metrics(qdisc, state, workers, targets):
    tasks = json.loads(targets)["data"]["activeTargets"]
    jobs = [task["labels"]["job"] for task in tasks]
    disciplines = json.loads(qdisc)
    neutral = len(disciplines) == 1 and disciplines[0].get("kind") == "fq_codel" and disciplines[0].get("root") is True
    states = state.split()
    return {"configured_packet_loss_pct": 0 if neutral else None,
            "upf_process_running": int(len(states) == 1 and not any(c in states[0] for c in "TXZ")),
            "stress_workers_count": len(workers.splitlines()),
            "prometheus_targets_up_count": sum(task["health"] == "up" for task in tasks)
            if len(jobs) == 3 and set(jobs) == {"open5gs-amf", "open5gs-smf", "open5gs-upf"} else -1}


def clean(samples):
    required = {"packets_transmitted": 5, "packets_received": 5, "packet_loss_pct": 0,
                "configured_packet_loss_pct": 0, "upf_process_running": 1, "stress_workers_count": 0, "prometheus_targets_up_count": 3}
    return len(samples) == 3 and all(not row["errors"] and all(row["metrics"].get(k) == v for k, v in required.items()) for row in samples)
