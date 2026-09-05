"""Deterministic invented command data. Never calls Docker, a socket or a clock."""
import copy
from datetime import datetime, timezone
import hashlib
import json

from sandbox.reconnect_r4_collection import command_plan, IMAGES, UE, GNB

EPOCH = 1788566400 * 10**9


def rehash(row):
    for stream in ("stdout", "stderr"):
        row[stream + "_sha256"] = hashlib.sha256(row[stream].encode()).hexdigest()


def timestamp(ns):
    seconds, nanos = divmod(ns, 10**9)
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + f".{nanos:09d}Z"


def script(identifier=10001, mode="trace", *, skew_ns=-10**9, source="10.45.0.2", first_idle=False):
    rows = []
    now = (identifier - 10000) * 100 * 10**9
    for i, argv in enumerate(command_plan(identifier)):
        duration = 10**9 if i == 7 else 100_000_000
        rows.append({"sequence": i + 1, "argv": argv, "timeout_seconds": 35, "max_output_bytes": 1048576,
                     "returncode": 0, "timed_out": False, "truncated": False, "stdout": "", "stderr": "",
                     "wall_start_ns": EPOCH + now, "wall_end_ns": EPOCH + now + duration,
                     "monotonic_start_ns": now, "monotonic_end_ns": now + duration})
        now += duration + 10_000_000
    for a, b, name, digit in ((0, 13, UE, "a"), (1, 14, GNB, "b")):
        identity = {"Id": digit * 64, "Name": "/" + name,
                    "Image": IMAGES["derived_image_id" if mode == "trace" else "official_image_id"],
                    "StartedAt": "2026-09-05T00:00:00.000000000Z", "Running": True, "RestartCount": 0,
                    "LogConfig": {"Type": "json-file", "Config": {}}}
        rows[a]["stdout"] = rows[b]["stdout"] = json.dumps(identity) + "\n"
    ip = [{"ifname": "uesimtun0", "flags": ["POINTOPOINT", "UP", "LOWER_UP"],
           "addr_info": [{"family": "inet", "scope": "global", "local": source, "prefixlen": 24}]}]
    rows[2]["stdout"] = rows[12]["stdout"] = json.dumps(ip) + "\n"
    # Components may be arbitrarily skewed relative to host AND each other.
    for a, b, skew in ((3, 10, skew_ns), (4, 11, -skew_ns * 2)):
        for i in (a, b):
            value = EPOCH + rows[i]["monotonic_start_ns"] + 50_000_000 + skew
            seconds, nanos = divmod(value, 10**9)
            rows[i]["stdout"] = f"{seconds}.{nanos:09d}\n"
    replies = list(range(2 if first_idle else 1, 6))
    ping = f"PING 10.45.0.1 (10.45.0.1) from {source} uesimtun0: 56(84) bytes of data.\n"
    ping += "".join(f"64 bytes from 10.45.0.1: icmp_seq={n} ttl=64 time=1.0 ms\n" for n in replies)
    ping += f"\n--- 10.45.0.1 ping statistics ---\n5 packets transmitted, {len(replies)} received, {20 * (5 - len(replies))}% packet loss, time 801ms\n"
    rows[7]["stdout"] = ping
    for a, b, component, skew in ((5, 8, "ue", skew_ns), (6, 9, "gnb", -skew_ns * 2)):
        prefix = timestamp(EPOCH + rows[0]["monotonic_start_ns"] - 10**9 + skew) + " [fixture] component ready\n"
        rows[a]["stdout"] = rows[b]["stdout"] = prefix
        if mode != "trace":
            continue
        for seq in range(1, 6):
            idle = seq == 1 and first_idle
            stages = (["nas_in", "nas_idle"] if idle else ["nas_in", "nas_forward", "ue_rls"]) if component == "ue" else ([] if idle else ["gnb_in", "gnb_resource"])
            for order, stage in enumerate(stages):
                at = EPOCH + rows[7]["monotonic_start_ns"] + (seq - 1) * 200_000_000 + order * 1000 + skew
                rows[b]["stdout"] += timestamp(at) + f" ST3 stage={stage} psi=1 actor=0 cm={int(not idle)} mm=7 ps=1 pending=0 ipid={seq} id={identifier} seq={seq} bytes=84 fp={seq + 900}\n"
    for row in rows:
        rehash(row)
    return rows


class FakeTransport:
    evidence_label = "fixture"
    io_enabled = False

    def __init__(self, mode="trace", mutate=None, **kwargs):
        self.mode, self.mutate, self.kwargs = mode, mutate, kwargs
        self.invocation = 0
        self.calls = []

    def run(self, argv, *, sequence, timeout_seconds, max_output_bytes):
        if sequence == 1:
            self.rows = script(10001 + self.invocation, self.mode, **self.kwargs)
            self.invocation += 1
            if self.mutate:
                self.mutate(self.rows)
                for row in self.rows:
                    rehash(row)
        row = copy.deepcopy(self.rows[sequence - 1])
        if row["argv"] != argv or timeout_seconds != 35 or max_output_bytes != 1048576:
            raise ValueError("fixture request not in exact script")
        self.calls.append(copy.deepcopy(argv))
        return row


def change_identity(rows, index, **updates):
    obj = json.loads(rows[index]["stdout"])
    obj.update(updates)
    rows[index]["stdout"] = json.dumps(obj) + "\n"


def missing_early(rows):
    for index in (8, 9):
        rows[index]["stdout"] = "".join(line + "\n" for line in rows[index]["stdout"].splitlines() if "seq=1 " not in line)


def source_step(rows):
    row = rows[10]
    seconds, nanos = row["stdout"].strip().split(".")
    row["stdout"] = f"{int(seconds) + 5}.{nanos}\n"


def saturated(rows):
    rows[8]["stdout"] += rows[8]["stdout"].splitlines()[-1] + "\n"
    last = rows[8]["stdout"].splitlines()[-1] + "\n"
    rows[8]["stdout"] += last * (2000 - len(rows[8]["stdout"].splitlines()))


def short_recovery(rows):
    rows[7]["stdout"] = "\n".join(line for line in rows[7]["stdout"].splitlines() if "icmp_seq=1" not in line) + "\n"
    rows[7]["stdout"] = rows[7]["stdout"].replace("5 received, 0%", "4 received, 20%")


CASES = {
    "complete-skewed": {},
    "complete-idle-loss": {"first_idle": True},
    "source-ineligible": {"source": "10.45.0.3"},
    "missing-first-packet-trace": {"mutate": missing_early},
    "source-clock-step": {"mutate": source_step},
    "saturated-capture": {"mutate": saturated},
    "partial-command": {"mutate": lambda rows: rows[8].update(timed_out=True)},
    "container-restarted": {"mutate": lambda rows: change_identity(rows, 13, RestartCount=1)},
    "official-service-changed-source": {"mode": "official-service", "source": "10.45.0.3"},
    "official-rollback-wrong-image": {"mode": "official-service", "mutate": lambda rows: change_identity(rows, 13, Image=IMAGES["derived_image_id"])},
    "official-service-4-of-5": {"mode": "official-service", "mutate": short_recovery},
}
