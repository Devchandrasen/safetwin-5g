"""Prospective R4 collection logic. In-memory transport only; no execution CLI.

No host/container timestamp is used to select logs. Each component's complete,
unsaturated pre-capture must be an exact prefix of its post-capture. A future
live adapter and the surrounding approval/scope/rollback runner are separate gates.
"""
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import re

from sandbox.reconnect_r3_measurement import ping_argv, ping_result
from tools.reconnect_r3_trace import parse, account_window

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "config/experiments/reconnect-r4-collection.json").read_bytes())
IMAGES = json.loads((ROOT / "config/experiments/reconnect-r3-images.json").read_bytes())
UE, GNB = "safetwin5g-ue", "safetwin5g-gnb"
INSPECT = ('{"Id":{{json .Id}},"Name":{{json .Name}},"Image":{{json .Image}},'
           '"RestartCount":{{json .RestartCount}},"StartedAt":{{json .State.StartedAt}},'
           '"Running":{{json .State.Running}},"LogConfig":{{json .HostConfig.LogConfig}}}')
IP = ["docker", "exec", UE, "ip", "-j", "-4", "address", "show", "dev", "uesimtun0"]
MODES = {"trace", "official-service"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def command_plan(identifier):
    ping = ping_argv(identifier)
    inspect = lambda c: ["docker", "inspect", "--format", INSPECT, c]
    clock = lambda c: ["docker", "exec", c, "date", "-u", "+%s.%N"]
    logs = lambda c: ["docker", "logs", "--timestamps", "--tail", "2000", c]
    return [inspect(UE), inspect(GNB), IP, clock(UE), clock(GNB), logs(UE), logs(GNB),
            ping, logs(UE), logs(GNB), clock(UE), clock(GNB), IP, inspect(UE), inspect(GNB)]


def validate_records(rows, identifier):
    plan = command_plan(identifier)
    require(0 < len(rows) <= len(plan), "command inventory")
    previous = None
    for index, row in enumerate(rows):
        require(row["sequence"] == index + 1 and row["argv"] == plan[index], "command scope/order")
        require(row["timeout_seconds"] == CONFIG["command_timeout_seconds"]
                and row["max_output_bytes"] == CONFIG["max_output_bytes"], "command limits")
        require(row["timed_out"] is False and row["truncated"] is False, "partial command")
        require(type(row["returncode"]) is int and row["returncode"] in ((0, 1) if index == 7 else (0,)), "command failed")
        require(isinstance(row["stdout"], str) and row["stderr"] == "", "unexpected stderr/stream")
        require(len(row["stdout"].encode()) < CONFIG["max_output_bytes"], "byte cap reached")
        for stream in ("stdout", "stderr"):
            require(sha(row[stream]) == row[stream + "_sha256"], "raw stream hash")
        for field in ("wall_start_ns", "wall_end_ns", "monotonic_start_ns", "monotonic_end_ns"):
            require(type(row[field]) is int and row[field] >= 0, "integer clock record")
        start, end = row["monotonic_start_ns"], row["monotonic_end_ns"]
        require(0 <= end - start <= CONFIG["command_timeout_seconds"] * 10**9, "command duration")
        require(abs(row["wall_end_ns"] - row["wall_start_ns"] - (end - start)) <= CONFIG["clock_resolution_tolerance_ns"], "host clock step")
        if previous:
            require(start >= previous["monotonic_end_ns"], "overlapping commands")
            require(abs(row["wall_start_ns"] - previous["wall_end_ns"] - (start - previous["monotonic_end_ns"])) <= CONFIG["clock_resolution_tolerance_ns"], "host inter-command clock step")
        previous = row
    require(rows[-1]["monotonic_end_ns"] - rows[0]["monotonic_start_ns"] <= CONFIG["window_budget_seconds"] * 10**9, "window budget")


def source_address(text, mode):
    data = json.loads(text)
    require(len(data) == 1 and data[0]["ifname"] == "uesimtun0" and "UP" in data[0]["flags"], "PDU interface")
    addresses = [a["local"] for a in data[0]["addr_info"] if a["family"] == "inet" and a["scope"] == "global"]
    require(len(addresses) == 1, "unique PDU source")
    address = ipaddress.IPv4Address(addresses[0])
    require(address in ipaddress.IPv4Network("10.45.0.0/16") and address not in
            (ipaddress.IPv4Address("10.45.0.0"), ipaddress.IPv4Address("10.45.0.1"), ipaddress.IPv4Address("10.45.255.255")), "PDU address range")
    if mode == "trace":
        require(str(address) == CONFIG["source_ip"], "source outside immutable trace filter")
    return str(address)


def identity(text, component, mode):
    row = json.loads(text)
    require(set(row) == {"Id", "Name", "Image", "RestartCount", "StartedAt", "Running", "LogConfig"}, "minimal identity schema")
    require(re.fullmatch(r"[0-9a-f]{64}", row["Id"]) and row["Name"] == "/" + component, "container identity")
    require(row["Image"] == IMAGES["derived_image_id" if mode == "trace" else "official_image_id"]
            and row["Running"] is True and type(row["RestartCount"]) is int and row["RestartCount"] >= 0, "selected running image")
    require(datetime.fromisoformat(row["StartedAt"]).tzinfo is not None, "container start timezone")
    # Do not reconfigure logging. Unsupported options must block prospective use.
    require(row["LogConfig"] == {"Type": "json-file", "Config": {}}, "unrotated default logging required")
    return row


def log_lines(text):
    require(text.endswith("\n"), "missing complete line/anchor")
    lines = text.splitlines()
    require(0 < len(lines) < CONFIG["log_tail_limit"], "empty or saturated log capture")
    previous = None
    for line in lines:
        match = re.fullmatch(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)\.(\d{9})Z (.+)", line)
        require(match is not None, "RFC3339Nano log framing")
        epoch = int(datetime.fromisoformat(match[1]).replace(tzinfo=timezone.utc).timestamp()) * 10**9 + int(match[2])
        require(previous is None or previous <= epoch, "component clock reversal")
        previous = epoch
    return lines


def precheck(rows, identifier, mode):
    require(mode in MODES and len(rows) == 7, "precheck contract")
    validate_records(rows, identifier)
    states = [identity(rows[i]["stdout"], component, mode) for i, component in enumerate((UE, GNB))]
    require(states[0]["Id"] != states[1]["Id"], "distinct container identities")
    address = source_address(rows[2]["stdout"], mode)
    for i in (3, 4):
        require(re.fullmatch(r"\d+\.\d{9}\n", rows[i]["stdout"]), "source clock syntax before ping")
    for index, component in ((5, "ue"), (6, "gnb")):
        messages = "\n".join(line.split(" ", 1)[1] for line in log_lines(rows[index]["stdout"]))
        require(not any(r["id"] == identifier for r in trace_rows(messages, component)), "identifier already in component history")
        if mode == "official-service":
            require("ST3" not in messages, "instrumentation on official service")
    return states, address


def trace_rows(messages, component):
    require(all(line.count("ST3") == 1 for line in messages.splitlines() if "ST3" in line), "ambiguous trace marker")
    return parse(messages, component)


def clock_interval(before, after):
    values = []
    for row in (before, after):
        match = re.fullmatch(r"(\d+)\.(\d{9})\n", row["stdout"])
        require(match is not None, "source clock syntax")
        values.append(int(match[1]) * 10**9 + int(match[2]))
    delta = values[1] - values[0]
    lower = after["monotonic_start_ns"] - before["monotonic_end_ns"]
    upper = after["monotonic_end_ns"] - before["monotonic_start_ns"]
    tolerance = CONFIG["clock_resolution_tolerance_ns"]
    require(lower - tolerance <= delta <= upper + tolerance, "observed source clock step")
    return {"source_delta_ns": delta, "elapsed_lower_ns": lower, "elapsed_upper_ns": upper}


def evaluate(rows, identifier, mode):
    require(len(rows) == 15, "incomplete window commands")
    states, address = precheck(rows[:7], identifier, mode)
    validate_records(rows, identifier)
    for index, component in enumerate((UE, GNB)):
        require(identity(rows[13 + index]["stdout"], component, mode) == states[index], "container changed during window")
    require(source_address(rows[12]["stdout"], mode) == address, "PDU source changed during window")
    headers = re.findall(r"(?m)^PING 10\.45\.0\.1 \(10\.45\.0\.1\) from (\d+\.\d+\.\d+\.\d+) uesimtun0: 56\(84\) bytes of data\.$", rows[7]["stdout"])
    require(headers == [address] and rows[7]["stdout"].count("PING ") == 1, "ping source header")
    ping = ping_result(rows[7]["stdout"])
    require(rows[7]["returncode"] == int(ping["packets_received"] == 0), "ping exit/count mismatch")
    clocks = [clock_interval(rows[a], rows[b]) for a, b in ((3, 10), (4, 11))]
    traces = []
    lengths = []
    for a, b, component in ((5, 8, "ue"), (6, 9, "gnb")):
        before, after = log_lines(rows[a]["stdout"]), log_lines(rows[b]["stdout"])
        require(after[:len(before)] == before, "log prefix lost/rotated/rewritten")
        messages = "\n".join(line.split(" ", 1)[1] for line in after[len(before):])
        current = trace_rows(messages, component)
        require(all(r["id"] == identifier and r["bytes"] == 84 for r in current), "foreign trace in window")
        if mode == "official-service":
            require(not current, "instrumentation on official service")
        traces.extend(current)
        lengths.append({"before": len(before), "after": len(after)})
    trace = account_window(traces, identifier, ping["reply_sequences"]) if mode == "trace" else None
    return {"collection_valid": True, "source_ip": address, "trace_eligible": mode == "trace",
            "ping": ping, "trace": trace, "clock_brackets": clocks, "log_lengths": lengths,
            "packet_delivery_complete": ping["packets_received"] == 5,
            "rollback_verified": False, "network_fix_validated": False}


class FixtureCollector:
    """Execute the fixed algorithm against an explicitly non-I/O fake transport.

    This class is not a security boundary against arbitrary Python objects. Tests
    additionally disable subprocesses/sockets. There is deliberately no live port.
    """
    def __init__(self, transport):
        require(transport.evidence_label == "fixture" and transport.io_enabled is False, "fixture transport only")
        self.transport = transport
        self.next_identifier = CONFIG["icmp_id_first"]

    def collect(self, mode="trace"):
        require(mode in MODES, "window mode")
        identifier = self.next_identifier
        plan = command_plan(identifier)
        self.next_identifier += 1  # A failed/partial attempt still consumes the ID.
        bundle = {"contract_id": CONFIG["contract_id"], "evidence_label": "fixture",
                  "transport": "in-memory-no-io", "identifier": identifier, "mode": mode,
                  "commands": [], "result": None, "errors": [], "actual_docker_commands_executed": 0,
                  "network_execution_authorized": False, "network_fix_validated": False}
        try:
            for index, argv in enumerate(plan):
                row = self.transport.run(argv, sequence=index + 1,
                                         timeout_seconds=CONFIG["command_timeout_seconds"], max_output_bytes=CONFIG["max_output_bytes"])
                bundle["commands"].append(row)
                validate_records(bundle["commands"], identifier)
                if index == 6:
                    precheck(bundle["commands"], identifier, mode)
            bundle["result"] = evaluate(bundle["commands"], identifier, mode)
        except (ValueError, KeyError, TypeError, OSError) as exc:
            bundle["errors"].append(type(exc).__name__ + ": " + str(exc))
        return bundle


def recovery_candidate(windows):
    """Packet-only candidate, never a substitute for the pending rollback audit."""
    valid = len(windows) == 3
    previous = None
    context = None
    for window in windows:
        try:
            require(window["evidence_label"] == "fixture" and not window["errors"] and window["mode"] == "official-service", "service window")
            result = evaluate(window["commands"], window["identifier"], window["mode"])
            require(result == window["result"] and window["network_execution_authorized"] is False
                    and window["network_fix_validated"] is False and window["actual_docker_commands_executed"] == 0, "service result/claim drift")
            current_context = [result["source_ip"], *[json.loads(window["commands"][i]["stdout"]) for i in (0, 1)]]
            require(context is None or context == current_context, "service context changed between windows")
            context = current_context
            valid = valid and result["packet_delivery_complete"] and (previous is None or window["identifier"] == previous + 1)
            previous = window["identifier"]
        except (ValueError, KeyError, TypeError):
            valid = False
    return {"packet_delivery_candidate": bool(valid), "required_packets": 15,
            "fresh_registration_pdu_scope_telemetry_audit": "pending-execution-integration",
            "rollback_verified": False, "network_fix_validated": False}
