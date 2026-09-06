# Separately versioned whole-run adapter derived from the frozen standalone
# auditor. Full global journal/rows stay intact; no slicing or renumbering.
# global_context is constructed by the root auditor after whole-process replay.
"""Independent R5 collector replay; no runtime collector acceptance imports.

Standalone component inventory only. Full runner replay must keep its complete
global journal and every non-collection process record, not slice/renumber them.
"""
from datetime import datetime
from fractions import Fraction
import json
import re

from tools.audit_reconnect_r5_process import audit as process_audit, integer
from tools.audit_reconnect_r5_journal import audit as journal_audit
from tools.reconnect_r4_window_audit import expected_commands, ping_read, address_read, logs_read, path_read, IMAGES, UE, GNB, check

CONTRACT_ID = "safetwin5g-reconnect-r5-collection-v1"
FLAGS = ("reservation_persisted", "collection_valid", "network_execution_authorized", "whole_protocol_verified", "rollback_verified", "network_fix_validated")
KEYS = set(FLAGS) | set("contract_id number label mode cleanup clock_id start_point start_event identifier reservation_event reservation_ticks command_first commands checks deadline_ticks final_check_ticks closure_event_before closure_event_after end_point counter_error failures parsed_result result".split())


def read_identity(text, name, mode):
    v = json.loads(text)
    check(set(v) == set("Id Name Image RestartCount StartedAt Running LogConfig".split()), "minimal identity")
    check(type(v["Id"]) is str and re.fullmatch("[0-9a-f]{64}", v["Id"]) and v["Name"] == "/"+name
          and v["Running"] is True and integer(v["RestartCount"]), "running identity")
    check(v["Image"] == IMAGES["derived_image_id" if mode == "trace" else "official_image_id"], "immutable image")
    check(datetime.fromisoformat(v["StartedAt"]).tzinfo is not None and v["LogConfig"] == {"Type": "json-file", "Config": {}}, "start/log driver")
    return v


def read_precheck(rows, identifier, mode):
    states = [read_identity(rows[i]["stdout"], c, mode) for i, c in enumerate((UE, GNB))]
    check(states[0]["Id"] != states[1]["Id"], "distinct containers")
    source = address_read(rows[2]["stdout"], mode)
    for i in (3, 4):
        check(re.fullmatch(r"\d+\.\d{9}\n", rows[i]["stdout"]), "source clock precision")
    for i, component in ((5, "ue"), (6, "gnb")):
        for line in logs_read(rows[i]["stdout"]):
            if "ST3" not in line:
                continue
            check(mode == "trace" and line.count("ST3") == 1 and "ST3 " in line, "historical trace marker")
            tail = line.split("ST3 ", 1)[1]
            tokens = tail.split()
            check(" ".join(tokens) == tail and [t.split("=")[0] for t in tokens] == "stage psi actor cm mm ps pending ipid id seq bytes fp".split(), "historical trace schema")
            fields = dict(t.split("=") for t in tokens)
            stage = fields.pop("stage")
            check(all(re.fullmatch(r"-?\d+", v) for v in fields.values()), "historical integers")
            v = {k: int(n) for k, n in fields.items()}
            stages = ("nas_in", "nas_idle", "nas_forward", "ue_rls") if component == "ue" else ("gnb_in", "gnb_resource", "gnb_missing")
            check(stage in stages and v["psi"] == 1 and 10001 <= v["id"] <= 10099 and v["id"] != identifier
                  and 1 <= v["seq"] <= 5 and 0 <= v["ipid"] <= 65535 and 28 <= v["bytes"] <= 65535 and 0 <= v["fp"] < 2**64, "historical identity/reused ID")
    return states, source


def read_window(rows, identifier, mode, frequency):
    states, source = read_precheck(rows[:7], identifier, mode)
    check(all(read_identity(rows[i+13]["stdout"], c, mode) == states[i] for i, c in enumerate((UE, GNB))), "changed container context")
    check(address_read(rows[12]["stdout"], mode) == source, "changed PDU source")
    ping = ping_read(rows[7]["stdout"], source)
    check(rows[7]["returncode"] == int(ping["packets_received"] == 0), "ping exit/count mismatch")
    brackets = []
    for a, b in ((3, 10), (4, 11)):
        instants = []
        for i in (a, b):
            check(re.fullmatch(r"\d+\.\d{9}\n", rows[i]["stdout"]), "source clock precision")
            s, ns = rows[i]["stdout"].strip().split(".")
            instants.append(int(s)*10**9+int(ns))
        delta = instants[1]-instants[0]
        low = rows[b]["go_before_ticks"]-rows[a]["completion_observed_ticks"]
        high = rows[b]["completion_observed_ticks"]-rows[a]["go_before_ticks"]
        check(Fraction(low, frequency)-Fraction(1, 1000) <= Fraction(delta, 10**9) <= Fraction(high, frequency)+Fraction(1, 1000), "source elapsed interval")
        brackets.append(dict(source_delta_ns=delta, elapsed_lower_ticks=low, elapsed_upper_ticks=high, frequency_hz=frequency))
    messages, lengths = {}, []
    for a, b, c in ((5, 8, "ue"), (6, 9, "gnb")):
        before, after = logs_read(rows[a]["stdout"]), logs_read(rows[b]["stdout"])
        check(len(after) >= len(before) and all(x == y for x, y in zip(before, after)), "prefix continuity")
        messages[c] = [line.split(" ", 1)[1] for line in after[len(before):]]
        lengths.append(dict(before=len(before), after=len(after)))
    if mode == "official-service":
        check(not any("ST3" in line for lines in messages.values() for line in lines), "official trace")
    trace = path_read(messages, identifier, ping["reply_sequences"]) if mode == "trace" else None
    return dict(source_ip=source, trace_eligible=mode == "trace", ping=ping, trace=trace, clock_brackets=brackets,
                log_lengths=lengths, packet_delivery_complete=ping["packets_received"] == 5, rollback_verified=False, network_fix_validated=False)


def ledger_replay(snapshot, raw, clock_id):
    check(type(snapshot) is dict and set(snapshot) == set("contract_id clock_id events next_identifier failure".split()), "ledger schema")
    check(snapshot["failure"] is None, "identifier ledger storage failed; no durability claim")
    check(type(raw) is bytes and raw.endswith(b"\n"), "incomplete identifier ledger")
    events = [json.loads(line) for line in raw.splitlines()]
    check(events == snapshot["events"] and snapshot["contract_id"] == CONTRACT_ID and snapshot["clock_id"] == clock_id, "ledger raw/domain mismatch")
    check(events and type(events[0]["event"]) is int and events[0] == dict(kind="header", contract_id=CONTRACT_ID, clock_id=clock_id, first=10001, last=10099, event=1), "ledger header")
    check(len(events) <= 100 and type(snapshot["next_identifier"]) is int and snapshot["next_identifier"] == 10000+len(events), "ledger capacity/next ID")
    for index, e in enumerate(events[1:], 2):
        check(type(e) is dict and set(e) == set("kind identifier label mode cleanup clock_event point ticks command_before event".split()), "reservation schema")
        check(e["kind"] == "reserve" and type(e["identifier"]) is int and e["identifier"] == 9999+index and type(e["event"]) is int and e["event"] == index, "reservation order/reuse")
    return events[1:]


def audit(windows, snapshot, raw_journal, ledger_snapshot, raw_ledger, global_context):
    check(type(windows) is list and 0 <= len(windows) <= 99, "collection inventory")
    j = global_context["journal"]
    points, events, f = snapshot["points"], snapshot["events"], snapshot["descriptor"]["frequency_hz"]
    reservations = ledger_replay(ledger_snapshot, raw_ledger, snapshot["descriptor"]["clock_id"]) if ledger_snapshot is not None else []
    check(ledger_snapshot is not None or raw_ledger is None, "unowned/failed ledger bytes")
    check(len(reservations) == len(windows), "unaccounted reservation")
    rows = [r for w in windows for r in w["commands"]]
    allowed = [a for w in windows for a in expected_commands(w["identifier"])]
    process = None
    check(all(r == global_context["rows"][r["sequence"]-1] for r in rows), "collection global row linkage")
    check(sum(str(e.get("label", "")).startswith("collection:") for e in events) == len(windows), "missing collection terminal")
    bad = j["clock"]["rejection"]
    source_events = [e["event"] for e in events if e["kind"] == "source-error"]
    def prefix_ok(n, ev):
        return n >= 2 and (bad is None or n < bad["sequence"]) and not any(x <= ev for x in source_events)
    def count(ev):
        return sum(e["kind"] == "point" for e in events[:ev])
    decisions, next_command, previous_end, last_tick, counter_error = [], 1, 1, None, None
    for index, (w, reservation) in enumerate(zip(windows, reservations), 1):
        check(type(w) is dict and set(w) == KEYS and w["contract_id"] == CONTRACT_ID and type(w["number"]) is int and w["number"] == index, "window schema/order")
        check(all(type(w[k]) is bool for k in FLAGS) and type(w["cleanup"]) is bool and all(w[k] is False for k in FLAGS[2:]), "typed collection/authority flags")
        check(type(w["label"]) is str and 0 < len(w["label"]) <= 80 and w["mode"] in ("trace", "official-service"), "window scope")
        check(w["clock_id"] == snapshot["descriptor"]["clock_id"] and integer(w["start_event"], previous_end, len(events)), "window domain/event")
        next_command = 1+sum(r["journal_event_after"] <= w["start_event"] for r in global_context["rows"])
        n = count(w["start_event"])
        check(type(w["start_point"]) is type(n or None) and w["start_point"] == (n or None) and type(w["command_first"]) is int and w["command_first"] == next_command, "collection anchor/command reference")
        check(w["reservation_persisted"] is True and type(w["reservation_event"]) is int and type(w["identifier"]) is int and w["reservation_event"] == reservation["event"] and w["identifier"] == reservation["identifier"], "unpersisted reservation")
        for a, b in (("label", "label"), ("mode", "mode"), ("cleanup", "cleanup"), ("clock_event", "start_event"), ("point", "start_point"), ("ticks", "reservation_ticks")):
            check(type(reservation[a]) is type(w[b]) and reservation[a] == w[b], "reservation/window linkage")
        check(reservation["command_before"] == next_command-1, "reservation before dispatch")
        deadline = points[n-1]["qpc_before_ticks"]+120*f if n and integer(points[n-1]["qpc_before_ticks"]) else None
        check(type(w["deadline_ticks"]) is type(deadline) and w["deadline_ticks"] == deadline, "window deadline/charged anchor")
        check(w["counter_error"] is None or type(w["counter_error"]) is str and w["counter_error"], "counter failure schema")
        check(counter_error is None or counter_error == w["counter_error"], "collection counter latch cleared")
        counter_error = w["counter_error"] or counter_error
        def tick(value):
            nonlocal last_tick
            if value is None:
                check(w["counter_error"] is not None, "unreported missing counter")
                return False
            check(integer(value) and (last_tick is None or value >= last_tick), "reversing raw collection counter")
            last_tick = value
            return True
        tick(w["reservation_ticks"])
        check(type(w["commands"]) is list and len(w["commands"]) <= 15 and type(w["checks"]) is list and len(w["checks"]) <= 15, "window inventory cap")
        commands, expected_phase, ev = w["commands"], None, w["start_event"]
        plan = expected_commands(w["identifier"])
        check([r["argv"] for r in commands] == plan[:len(commands)], "fixed command prefix")
        for local, c in enumerate(w["checks"], 1):
            check(expected_phase is None and set(c) == set("local clock_event point ticks points_needed admitted".split()) and type(c["local"]) is int and c["local"] == local, "continued after failure/check schema")
            m = count(ev)
            check(c["clock_event"] == ev and type(c["point"]) is type(m or None) and c["point"] == (m or None)
                  and type(c["points_needed"]) is int and c["points_needed"] == 17-local and type(c["admitted"]) is bool, "collection admission references/inventory")
            available = tick(c["ticks"])
            admitted = bool(available and prefix_ok(m, ev) and m+17-local <= (1024 if w["cleanup"] else 768)
                            and c["ticks"] >= points[m-1]["qpc_after_ticks"] and deadline is not None and c["ticks"]+35*f <= deadline)
            check(c["admitted"] == admitted, "collection admission claim")
            if not admitted:
                check(len(commands) == local-1, "dispatch after rejected admission")
                expected_phase = "admission"
                continue
            if local > len(commands):
                expected_phase = "transport"
                continue
            r = commands[local-1]
            check(r["journal_event_before"] == ev and r["sequence"] == next_command and r["cleanup"] is w["cleanup"]
                  and r["timeout_ms"] == 35000 and r["max_output_bytes"] == 1048576, "command linkage/limits")
            if r["checked_ticks"] is not None:
                check(r["checked_ticks"] >= c["ticks"], "dispatch predates admission")
            ev, next_command = r["journal_event_after"], next_command+1
            good = (r["complete"] and r["stdout_utf8"] and r["stderr_utf8"] and not r["stderr"]
                    and len(r["stdout"].encode()) < 1048576 and type(r["returncode"]) is int and r["returncode"] in ((0, 1) if local == 8 else (0,)))
            if not good:
                expected_phase = "command"
            elif local == 7:
                try:
                    read_precheck(commands[:7], w["identifier"], w["mode"])
                except (ValueError, KeyError, TypeError):
                    expected_phase = "precheck"
        check(len(commands) <= len(w["checks"]) and (len(commands) == 15 or expected_phase is not None or deadline is None), "unexplained partial window")
        parsed = None
        if expected_phase is None and len(commands) == 15:
            try:
                parsed = read_window(commands, w["identifier"], w["mode"], f)
            except (ValueError, KeyError, TypeError):
                expected_phase = "evaluation"
        elif deadline is None:
            expected_phase = "admission"
        check(w["parsed_result"] == parsed, "raw parser claim mismatch")
        final_available = tick(w["final_check_ticks"])
        if final_available and commands and commands[-1]["cleanup_completed_ticks"] is not None:
            check(w["final_check_ticks"] >= commands[-1]["cleanup_completed_ticks"], "result closure predates final command")
        a, b = w["closure_event_before"], w["closure_event_after"]
        check(type(a) is int and type(b) is int and a == ev and b == a+1 and b <= len(events), "terminal collection event linkage")
        terminal = events[b-1]
        check(terminal["label"] == "collection:"+str(index)+":end" and terminal["cleanup"] is w["cleanup"], "collection terminal label")
        m = count(b)
        end = m if terminal["kind"] == "point" else None
        check(type(w["end_point"]) is type(end) and w["end_point"] == end, "collection terminal point")
        closed = bool(final_available and w["counter_error"] is None and end and prefix_ok(m, b) and deadline is not None
                      and w["final_check_ticks"] <= points[m-1]["qpc_before_ticks"] and points[m-1]["qpc_after_ticks"] < deadline)
        phases = ([expected_phase] if expected_phase else [])+([] if closed else ["closure"])
        check(type(w["failures"]) is list and all(set(e) == {"phase", "error"} and type(e["error"]) is str and e["error"] for e in w["failures"])
              and [e["phase"] for e in w["failures"]] == phases, "failure phase accounting")
        valid = parsed is not None and not phases
        check(w["collection_valid"] == valid and w["result"] == (dict(parsed, collection_valid=True) if valid else None), "collection acceptance claim")
        decisions.append(dict(number=index, identifier=w["identifier"], collection_valid=valid, failure_phases=phases, packet_delivery_complete=bool(valid and parsed["packet_delivery_complete"])))
        previous_end = b
    # The root cursor accounts for ALL intervening/trailing global work.
    return dict(observation_audit_passed=True, collections_replayed=len(windows), commands_replayed=len(rows), clock_points=len(points),
                decisions=decisions, process_audit=process, clock_journal=j if process is None else None,
                network_execution_authorized=False, whole_protocol_verified=False, rollback_verified=False, network_fix_validated=False)


def packet_candidate(windows, report):
    valid = len(windows) == len(report["decisions"]) == 3 and all(d["collection_valid"] and d["packet_delivery_complete"] for d in report["decisions"])
    if valid:
        ids = [w["identifier"] for w in windows]
        contexts = [(w["result"]["source_ip"], *[json.loads(w["commands"][i]["stdout"]) for i in (0, 1)]) for w in windows]
        valid = all(w["mode"] == "official-service" for w in windows) and ids == list(range(ids[0], ids[0]+3)) and contexts[0] == contexts[1] == contexts[2]
    return dict(packet_delivery_candidate=bool(valid), required_packets=15, rollback_verified=False, network_fix_validated=False)
