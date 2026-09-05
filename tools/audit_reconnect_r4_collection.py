"""Independent fixture-window replay. No import of the R4 collector predicates.

Command spellings/configuration are frozen inputs; parsing, clock arithmetic,
prefix admission, source eligibility and packet-path accounting are independent.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
C = json.loads((ROOT / "config/experiments/reconnect-r4-collection.json").read_bytes())
IMAGES = json.loads((ROOT / "config/experiments/reconnect-r3-images.json").read_bytes())
UE, GNB = "safetwin5g-ue", "safetwin5g-gnb"
INSPECT = ('{"Id":{{json .Id}},"Name":{{json .Name}},"Image":{{json .Image}},'
           '"RestartCount":{{json .RestartCount}},"StartedAt":{{json .State.StartedAt}},'
           '"Running":{{json .State.Running}},"LogConfig":{{json .HostConfig.LogConfig}}}')


def check(value, message):
    if not value:
        raise ValueError(message)


def expected_commands(identifier):
    snapshots = [["docker", "inspect", "--format", INSPECT, c] for c in (UE, GNB)]
    clocks = [["docker", "exec", c, "date", "-u", "+%s.%N"] for c in (UE, GNB)]
    captures = [["docker", "logs", "--timestamps", "--tail", "2000", c] for c in (UE, GNB)]
    ip = ["docker", "exec", UE, "ip", "-j", "-4", "address", "show", "dev", "uesimtun0"]
    ping = ["docker", "exec", UE, "ping", "-I", "uesimtun0", "-e", str(identifier), "-s", "56", "-c", "5", "-i", "0.2", "-W", "1", "10.45.0.1"]
    return snapshots + [ip] + clocks + captures + [ping] + captures + clocks + [ip] + snapshots


def ping_read(text, source):
    lines = text.splitlines()
    headers = [line for line in lines if line.startswith("PING ")]
    check(headers == [f"PING 10.45.0.1 (10.45.0.1) from {source} uesimtun0: 56(84) bytes of data."], "raw ping source")
    summaries = [line for line in lines if "packets transmitted" in line]
    check(len(summaries) == 1, "one ping summary")
    match = re.fullmatch(r"5 packets transmitted, ([0-5]) received, (0|20|40|60|80|100)(?:\.0+)?% packet loss(?:, time \d+ms)?", summaries[0])
    check(match is not None, "ping summary format")
    count, loss = map(int, match.groups())
    sequences = []
    for line in lines:
        if "icmp_seq=" not in line:
            continue
        parts = line.split()
        check(len(parts) == 8 and parts[:4] == ["64", "bytes", "from", "10.45.0.1:"] and parts[-1] == "ms", "reply origin/size")
        check(re.fullmatch(r"icmp_seq=[1-5]", parts[4]) and re.fullmatch(r"ttl=\d+", parts[5]) and re.fullmatch(r"time[=<][\d.]+", parts[6]), "reply fields")
        sequences.append(int(parts[4][-1]))
    check(len(sequences) == len(set(sequences)) == count and loss == (5 - count) * 20, "reply count/loss/duplicates")
    return {"packets_transmitted": 5, "packets_received": count, "packet_loss_pct": loss, "reply_sequences": sequences}


def address_read(text, mode):
    interfaces = json.loads(text)
    check(isinstance(interfaces, list) and len(interfaces) == 1, "one PDU interface")
    interface = interfaces[0]
    check(interface["ifname"] == "uesimtun0" and "UP" in interface["flags"], "PDU up")
    addresses = [a["local"] for a in interface["addr_info"] if a["family"] == "inet" and a["scope"] == "global"]
    check(len(addresses) == 1, "one global IPv4 source")
    ip = ipaddress.IPv4Address(addresses[0])
    check(ipaddress.IPv4Address("10.45.0.1") < ip < ipaddress.IPv4Address("10.45.255.255"), "sandbox PDU source")
    check(mode != "trace" or str(ip) == "10.45.0.2", "ineligible trace source")
    return str(ip)


def logs_read(text):
    check(text.endswith("\n"), "unterminated or empty log capture")
    lines = text.splitlines()
    check(0 < len(lines) < C["log_tail_limit"], "saturated capture")
    last = None
    for line in lines:
        timestamp, separator, message = line.partition(" ")
        check(separator and message and re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{9}Z", timestamp), "Docker timestamp framing")
        seconds, ns = timestamp[:-1].split(".")
        instant = int(datetime.fromisoformat(seconds).replace(tzinfo=timezone.utc).timestamp()) * 10**9 + int(ns)
        check(last is None or instant >= last, "component time reversal")
        last = instant
    return lines


def path_read(messages, identifier, replies):
    events = {n: {} for n in range(1, 6)}
    orders = {c: {n: [] for n in events} for c in ("ue", "gnb")}
    for component, lines in messages.items():
        for line in lines:
            if "ST3" not in line:
                continue
            check(line.count("ST3") == 1 and "ST3 " in line, "trace marker")
            tail = line.split("ST3 ", 1)[1]
            fields = tail.split()
            check(" ".join(fields) == tail, "trace spacing")
            check([f.split("=")[0] for f in fields] == "stage psi actor cm mm ps pending ipid id seq bytes fp".split(), "trace schema")
            raw = dict(f.split("=") for f in fields)
            stage = raw.pop("stage")
            check(all(re.fullmatch(r"-?\d+", v) for v in raw.values()), "trace integers")
            row = {k: int(v) for k, v in raw.items()}
            allowed = {"nas_in", "nas_idle", "nas_forward", "ue_rls"} if component == "ue" else {"gnb_in", "gnb_resource", "gnb_missing"}
            check(stage in allowed and row["id"] == identifier and row["seq"] in events and row["psi"] == 1 and row["bytes"] == 84
                  and 0 <= row["ipid"] <= 65535 and 0 <= row["fp"] < 2**64, "trace identity")
            seq = row["seq"]
            check(stage not in events[seq], "duplicate packet stage")
            events[seq][stage] = row
            orders[component][seq].append(stage)
    packets = []
    for seq, stages in events.items():
        check(len({(r["ipid"], r["bytes"], r["fp"]) for r in stages.values()}) == 1, "missing packet or inconsistent fingerprint")
        if "nas_idle" in stages:
            check(set(stages) == {"nas_in", "nas_idle"} and orders["ue"][seq] == ["nas_in", "nas_idle"]
                  and stages["nas_in"]["cm"] == stages["nas_idle"]["cm"] == 0 and stages["nas_idle"]["ps"] == 1 and seq not in replies, "contradictory idle path")
            fate = "nas_idle_nonretention_observed"
        else:
            terminal = "gnb_missing" if "gnb_missing" in stages else "gnb_resource"
            check(set(stages) == {"nas_in", "nas_forward", "ue_rls", "gnb_in", terminal} and orders["ue"][seq] == ["nas_in", "nas_forward", "ue_rls"]
                  and orders["gnb"][seq] == ["gnb_in", terminal], "forward path order/completeness")
            check(stages["nas_in"]["cm"] == stages["nas_forward"]["cm"] == 1 and stages["nas_forward"]["ps"] == 1, "forward state")
            check(not (terminal == "gnb_missing" and seq in replies), "missing resource with reply")
            fate = "reply_observed" if seq in replies else "gnb_missing_resource_observed" if terminal == "gnb_missing" else "after_gnb_resource_unlocalized"
        packets.append({"sequence": seq, "fate": fate, "reply_observed": seq in replies})
    return {"trace_accounting_complete": True, "packets": packets, "received": len(replies), "sent": 5,
            "all_packets_returned": len(replies) == 5, "network_fix_validated": False}


def audit(bundle, *, allow_fixture=False):
    check(allow_fixture and bundle["evidence_label"] == "fixture" and bundle["transport"] == "in-memory-no-io", "explicit fixture permission required")
    check(bundle["contract_id"] == C["contract_id"] and bundle["actual_docker_commands_executed"] == 0
          and bundle["network_execution_authorized"] is False and bundle["network_fix_validated"] is False, "claim boundary")
    identifier, mode, rows = bundle["identifier"], bundle["mode"], bundle["commands"]
    check(type(identifier) is int and 10001 <= identifier <= 10099 and mode in ("trace", "official-service"), "invocation contract")
    check(not bundle["errors"] and len(rows) == 15, "incomplete or rejected collection")
    check([r["argv"] for r in rows] == expected_commands(identifier), "exact command inventory")
    for index, row in enumerate(rows):
        check(row["sequence"] == index + 1 and row["timeout_seconds"] == 35 and row["max_output_bytes"] == 1048576, "command budget/sequence")
        check(row["timed_out"] is False and row["truncated"] is False and row["stderr"] == "", "partial command/unsupported stream")
        check(type(row["returncode"]) is int and row["returncode"] in ((0, 1) if index == 7 else (0,)), "command status")
        for stream in ("stdout", "stderr"):
            raw = row[stream].encode()
            check(len(raw) < 1048576 and hashlib.sha256(raw).hexdigest() == row[stream + "_sha256"], "stream size/hash")
        for f in ("wall_start_ns", "wall_end_ns", "monotonic_start_ns", "monotonic_end_ns"):
            check(type(row[f]) is int and row[f] >= 0, "integer time")
        elapsed = row["monotonic_end_ns"] - row["monotonic_start_ns"]
        check(0 <= elapsed <= 35 * 10**9 and abs(row["wall_end_ns"] - row["wall_start_ns"] - elapsed) <= C["clock_resolution_tolerance_ns"], "duration/host step")
        if index:
            gap = row["monotonic_start_ns"] - rows[index - 1]["monotonic_end_ns"]
            check(gap >= 0 and abs(row["wall_start_ns"] - rows[index - 1]["wall_end_ns"] - gap) <= C["clock_resolution_tolerance_ns"], "inter-command clock step/order")
    check(rows[-1]["monotonic_end_ns"] - rows[0]["monotonic_start_ns"] <= C["window_budget_seconds"] * 10**9, "window budget")
    ids = []
    for a, b, name in ((0, 13, UE), (1, 14, GNB)):
        before, after = (json.loads(rows[i]["stdout"]) for i in (a, b))
        check(before == after and set(before) == {"Id", "Name", "Image", "RestartCount", "StartedAt", "Running", "LogConfig"}, "stable minimal identity")
        check(re.fullmatch(r"[0-9a-f]{64}", before["Id"]) and before["Name"] == "/" + name and before["Running"] is True
              and type(before["RestartCount"]) is int and before["RestartCount"] >= 0, "running container")
        check(before["Image"] == IMAGES["derived_image_id" if mode == "trace" else "official_image_id"], "expected immutable image")
        check(datetime.fromisoformat(before["StartedAt"]).tzinfo is not None and before["LogConfig"] == {"Type": "json-file", "Config": {}}, "start/log driver")
        ids.append(before["Id"])
    check(len(set(ids)) == 2, "distinct containers")
    source = address_read(rows[2]["stdout"], mode)
    check(address_read(rows[12]["stdout"], mode) == source, "changed PDU source")
    ping = ping_read(rows[7]["stdout"], source)
    check(rows[7]["returncode"] == (1 if ping["packets_received"] == 0 else 0), "ping status inconsistent")
    brackets = []
    for a, b in ((3, 10), (4, 11)):
        instants = []
        for row in (rows[a], rows[b]):
            check(re.fullmatch(r"\d+\.\d{9}\n", row["stdout"]), "source clock precision")
            seconds, nanos = row["stdout"].strip().split(".")
            instants.append(int(seconds) * 10**9 + int(nanos))
        delta = instants[1] - instants[0]
        lo = rows[b]["monotonic_start_ns"] - rows[a]["monotonic_end_ns"]
        hi = rows[b]["monotonic_end_ns"] - rows[a]["monotonic_start_ns"]
        check(lo - C["clock_resolution_tolerance_ns"] <= delta <= hi + C["clock_resolution_tolerance_ns"], "source clock elapsed bracket")
        brackets.append({"source_delta_ns": delta, "elapsed_lower_ns": lo, "elapsed_upper_ns": hi})
    messages, lengths = {}, []
    for a, b, component in ((5, 8, "ue"), (6, 9, "gnb")):
        before, after = logs_read(rows[a]["stdout"]), logs_read(rows[b]["stdout"])
        check(len(after) >= len(before) and all(x == y for x, y in zip(before, after)), "prefix continuity")
        # Never discard malformed historical ST3 lines just because they predate this ID.
        for line in before:
            if "ST3" not in line:
                continue
            check(mode == "trace" and line.count("ST3") == 1 and "ST3 " in line, "official/ambiguous historical trace")
            tail = line.split("ST3 ", 1)[1]
            tokens = tail.split()
            check(" ".join(tokens) == tail, "historical trace spacing")
            check([t.split("=")[0] for t in tokens] == "stage psi actor cm mm ps pending ipid id seq bytes fp".split(), "historical trace schema")
            fields = dict(t.split("=") for t in tokens)
            stage = fields.pop("stage")
            check(all(re.fullmatch(r"-?\d+", v) for v in fields.values()), "historical integers")
            vals = {k: int(v) for k, v in fields.items()}
            permitted = {"nas_in", "nas_idle", "nas_forward", "ue_rls"} if component == "ue" else {"gnb_in", "gnb_resource", "gnb_missing"}
            check(stage in permitted and vals["psi"] == 1 and 10001 <= vals["id"] <= 10099 and vals["id"] != identifier
                  and 1 <= vals["seq"] <= 5 and 0 <= vals["ipid"] <= 65535 and 28 <= vals["bytes"] <= 65535 and 0 <= vals["fp"] < 2**64, "historical identity/reused ID")
        messages[component] = [line.split(" ", 1)[1] for line in after[len(before):]]
        lengths.append({"before": len(before), "after": len(after)})
    if mode == "official-service":
        check(not any("ST3" in line for lines in messages.values() for line in lines), "trace after official rollback")
    trace = path_read(messages, identifier, ping["reply_sequences"]) if mode == "trace" else None
    result = {"collection_valid": True, "source_ip": source, "trace_eligible": mode == "trace", "ping": ping, "trace": trace,
              "clock_brackets": brackets, "log_lengths": lengths, "packet_delivery_complete": ping["packets_received"] == 5,
              "rollback_verified": False, "network_fix_validated": False}
    check(result == bundle["result"], "reported result differs from independent replay")
    return {"collection_audit_passed": True, "commands_replayed": 15, "evidence_label": "fixture",
            "packet_delivery_complete": result["packet_delivery_complete"], "rollback_verified": False, "network_fix_validated": False}


def audit_recovery_candidate(windows):
    """Independently recheck all raw windows; actual reset/rollback remains pending."""
    candidate = len(windows) == 3
    try:
        identifiers = [w["identifier"] for w in windows]
        check(len(set(identifiers)) == len(identifiers) and identifiers == list(range(identifiers[0], identifiers[0] + 3)), "three distinct consecutive IDs")
        context = None
        for window in windows:
            check(window["mode"] == "official-service", "official packet-only windows")
            candidate = audit(window, allow_fixture=True)["packet_delivery_complete"] and candidate
            current = [address_read(window["commands"][2]["stdout"], "official-service"),
                       json.loads(window["commands"][0]["stdout"]), json.loads(window["commands"][1]["stdout"])]
            check(context is None or current == context, "service context changed between windows")
            context = current
    except (ValueError, KeyError, TypeError, IndexError):
        candidate = False
    return {"packet_delivery_candidate": bool(candidate), "required_packets": 15,
            "fresh_registration_pdu_scope_telemetry_audit": "pending-execution-integration",
            "rollback_verified": False, "network_fix_validated": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--allow-fixture", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(audit(json.loads(args.bundle.read_bytes()), allow_fixture=args.allow_fixture)))
        return 0
    except (ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"collection_audit_passed": False, "error": str(exc), "network_fix_validated": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
