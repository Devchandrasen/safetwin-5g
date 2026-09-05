"""R5 collection component. No execution CLI, process creation or authority.

The future locked runner supplies the exact approved, scope-checked transport.
Only clock-free raw parsers/command spellings are reused from frozen R4/R3.
"""
import copy
import json
import os
from pathlib import Path
import re

from sandbox.reconnect_r4_collection import (command_plan, identity, source_address, log_lines, trace_rows,
                                             ping_result, account_window, UE, GNB)

CONTRACT_ID = "safetwin5g-reconnect-r5-collection-v1"


def require(value, message):
    if not value:
        raise ValueError(message)


class IdentifierLedger:
    """Exclusive durable reservations. Allocation is never rolled back."""
    def __init__(self, path, clock_id):
        require(type(clock_id) is str and re.fullmatch("[0-9a-f]{32}", clock_id), "ledger clock domain")
        self.path, self.clock_id = Path(path), clock_id
        self.handle = self.path.open("xb")
        self.events, self.next_identifier, self.failure, self.closed = [], 10001, None, False
        try:
            self._emit(dict(kind="header", contract_id=CONTRACT_ID, clock_id=clock_id, first=10001, last=10099))
        except BaseException:
            self.close()
            raise

    def _emit(self, row):
        row = dict(copy.deepcopy(row), event=len(self.events)+1)
        self.events.append(row)
        try:
            self.handle.write((json.dumps(row, allow_nan=False)+"\n").encode())
            self.handle.flush()
            os.fsync(self.handle.fileno())
        except BaseException as exc:
            self.failure = self.failure or (type(exc).__name__+": "+str(exc))
            raise

    def reserve(self, label, mode, cleanup, *, clock_event, point, ticks, command_before):
        require(not self.closed and self.failure is None, "identifier ledger unavailable")
        require(type(label) is str and 0 < len(label) <= 80 and mode in ("trace", "official-service")
                and type(cleanup) is bool, "reservation scope")
        require(self.next_identifier <= 10099, "identifier capacity exhausted; no wrap or reuse")
        identifier = self.next_identifier
        self.next_identifier += 1
        self._emit(dict(kind="reserve", identifier=identifier, label=label, mode=mode, cleanup=cleanup,
                        clock_event=clock_event, point=point, ticks=ticks, command_before=command_before))
        return copy.deepcopy(self.events[-1])

    def snapshot(self):
        return dict(contract_id=CONTRACT_ID, clock_id=self.clock_id, events=copy.deepcopy(self.events),
                    next_identifier=self.next_identifier, failure=self.failure)

    def close(self):
        try:
            self.handle.close()
        finally:
            self.closed = True


def validate_row(row, argv, sequence, cleanup):
    require(row["argv"] == argv and row["sequence"] == sequence and row["cleanup"] is cleanup, "command scope/order")
    require(row["timeout_ms"] == 35000 and row["max_output_bytes"] == 1048576, "command limits")
    require(row["complete"] is True and row["stdout_utf8"] is True and row["stderr_utf8"] is True, "partial/untimed command")
    require(type(row["returncode"]) is int and row["returncode"] in ((0, 1) if argv[0:4] == ["docker", "exec", UE, "ping"] else (0,)), "command status")
    require(row["stderr"] == "" and len(row["stdout"].encode()) < 1048576, "unsupported stream or byte cap")


def precheck(rows, identifier, mode):
    require(len(rows) == 7 and mode in ("trace", "official-service"), "precheck inventory")
    states = [identity(rows[i]["stdout"], c, mode) for i, c in enumerate((UE, GNB))]
    require(states[0]["Id"] != states[1]["Id"], "distinct identities")
    source = source_address(rows[2]["stdout"], mode)
    for i in (3, 4):
        require(re.fullmatch(r"\d+\.\d{9}\n", rows[i]["stdout"]), "source clock syntax")
    for index, component in ((5, "ue"), (6, "gnb")):
        messages = "\n".join(line.split(" ", 1)[1] for line in log_lines(rows[index]["stdout"]))
        historical = trace_rows(messages, component)
        require(not any(r["id"] == identifier for r in historical), "identifier already in prefix")
        require(mode != "official-service" or "ST3" not in messages, "trace on official service")
    return states, source


def evaluate(rows, identifier, mode, frequency):
    require(len(rows) == 15, "incomplete collection")
    states, source = precheck(rows[:7], identifier, mode)
    for i, c in enumerate((UE, GNB)):
        require(identity(rows[13+i]["stdout"], c, mode) == states[i], "changed container context")
    require(source_address(rows[12]["stdout"], mode) == source, "changed PDU source")
    headers = re.findall(r"(?m)^PING .*", rows[7]["stdout"])
    require(headers == [f"PING 10.45.0.1 (10.45.0.1) from {source} uesimtun0: 56(84) bytes of data."], "ping source header")
    ping = ping_result(rows[7]["stdout"])
    require(rows[7]["returncode"] == int(ping["packets_received"] == 0), "ping exit/count mismatch")
    brackets = []
    for a, b in ((3, 10), (4, 11)):
        values = []
        for i in (a, b):
            match = re.fullmatch(r"(\d+)\.(\d{9})\n", rows[i]["stdout"])
            require(match is not None, "source clock syntax")
            values.append(int(match[1])*10**9+int(match[2]))
        delta = values[1]-values[0]
        lower = rows[b]["go_before_ticks"]-rows[a]["completion_observed_ticks"]
        upper = rows[b]["completion_observed_ticks"]-rows[a]["go_before_ticks"]
        require(lower*10**9-1000000*frequency <= delta*frequency <= upper*10**9+1000000*frequency, "source elapsed interval rejected")
        brackets.append(dict(source_delta_ns=delta, elapsed_lower_ticks=lower, elapsed_upper_ticks=upper, frequency_hz=frequency))
    traces, lengths = [], []
    for a, b, c in ((5, 8, "ue"), (6, 9, "gnb")):
        before, after = log_lines(rows[a]["stdout"]), log_lines(rows[b]["stdout"])
        require(after[:len(before)] == before, "log prefix lost/rotated/rewritten")
        messages = "\n".join(line.split(" ", 1)[1] for line in after[len(before):])
        current = trace_rows(messages, c)
        require(all(r["id"] == identifier and r["bytes"] == 84 for r in current), "foreign trace")
        require(mode != "official-service" or not current, "trace on official service")
        traces.extend(current)
        lengths.append(dict(before=len(before), after=len(after)))
    trace = account_window(traces, identifier, ping["reply_sequences"]) if mode == "trace" else None
    return dict(source_ip=source, trace_eligible=mode == "trace", ping=ping, trace=trace, clock_brackets=brackets,
                log_lengths=lengths, packet_delivery_complete=ping["packets_received"] == 5,
                rollback_verified=False, network_fix_validated=False)


class Collector:
    def __init__(self, journal, transport, ledger):
        require(transport.journal is journal and transport.clock is journal.clock and ledger.clock_id == journal.prefix.descriptor["clock_id"], "one collection clock/journal required")
        self.journal, self.transport, self.ledger = journal, transport, ledger
        self.clock, self.last_tick, self.counter_error = journal.clock, None, None
        self.windows = []

    def _tick(self):
        if self.counter_error is None:
            try:
                require(json.dumps(self.clock.descriptor, sort_keys=True) == json.dumps(self.journal.prefix.descriptor, sort_keys=True), "changed collection clock domain")
                value = self.clock.ticks()
                require(type(value) is int and 0 <= value < 2**63 and (self.last_tick is None or value >= self.last_tick), "invalid/reversing collection QPC")
                self.last_tick = value
                return value
            except BaseException as exc:
                self.counter_error = type(exc).__name__+": "+str(exc)
        return None

    def _space(self, points, cleanup):
        j = self.journal
        return bool(not j.closed and not j.failure and not j.capture_failed and j.prefix.status()["clock_capture_valid"]
                    and len(j.prefix.points)+points <= (1024 if cleanup else 768))

    def collect(self, label, mode="trace", *, cleanup=False):
        require(type(label) is str and 0 < len(label) <= 80 and mode in ("trace", "official-service") and type(cleanup) is bool, "collection request")
        j, ledger = self.journal, self.ledger
        start = len(j.prefix.points)
        anchor = j.prefix.points[-1] if start else None
        w = dict(contract_id=CONTRACT_ID, number=len(self.windows)+1, label=label, mode=mode, cleanup=cleanup,
                 clock_id=j.prefix.descriptor["clock_id"], start_point=start or None, start_event=len(j.events),
                 identifier=None, reservation_event=None, reservation_ticks=self._tick(), reservation_persisted=False,
                 command_first=self.transport.next_sequence, commands=[], checks=[], deadline_ticks=None,
                 final_check_ticks=None, closure_event_before=None, closure_event_after=None, end_point=None,
                 counter_error=None, failures=[], parsed_result=None, result=None, collection_valid=False,
                 network_execution_authorized=False, whole_protocol_verified=False, rollback_verified=False, network_fix_validated=False)
        self.windows.append(w)
        phase = "reservation"
        try:
            # Consume before any collection command, even if later clock, source,
            # image, capacity or prefix admission fails. Failed fsync blocks I/O.
            reservation = ledger.reserve(label, mode, cleanup, clock_event=len(j.events), point=start or None,
                                         ticks=w["reservation_ticks"], command_before=w["command_first"]-1)
            w["identifier"], w["reservation_event"], w["reservation_persisted"] = reservation["identifier"], reservation["event"], True
            phase = "admission"
            require(anchor is not None and type(anchor["qpc_before_ticks"]) is int, "missing collection anchor")
            w["deadline_ticks"] = anchor["qpc_before_ticks"]+120*j.prefix.descriptor["frequency_hz"]
            for local, argv in enumerate(command_plan(w["identifier"]), 1):
                phase = "admission"
                tick = self._tick()
                check = dict(local=local, clock_event=len(j.events), point=len(j.prefix.points) or None,
                             ticks=tick, points_needed=16-len(w["commands"]), admitted=False)
                w["checks"].append(check)
                require(self.counter_error is None and tick is not None and self._space(check["points_needed"], cleanup)
                        and tick >= j.prefix.points[-1]["qpc_after_ticks"], "collection clock/point admission rejected")
                require(tick+35*j.prefix.descriptor["frequency_hz"] <= w["deadline_ticks"], "collection deadline lacks full command budget")
                check["admitted"] = True
                phase = "transport"
                row = self.transport.run(argv, sequence=self.transport.next_sequence, timeout_ms=35000, max_output_bytes=1048576, cleanup=cleanup)
                w["commands"].append(row)
                phase = "command"
                validate_row(row, argv, w["command_first"]+local-1, cleanup)
                if local == 7:
                    phase = "precheck"
                    precheck(w["commands"], w["identifier"], mode)
            phase = "evaluation"
            w["parsed_result"] = evaluate(w["commands"], w["identifier"], mode, j.prefix.descriptor["frequency_hz"])
        except BaseException as exc:
            w["failures"].append(dict(phase=phase, error=type(exc).__name__+": "+str(exc)))
        finally:
            w["final_check_ticks"] = self._tick()
            w["closure_event_before"] = len(j.events)
            before = len(j.prefix.points)
            try:
                j.checkpoint("collection:"+str(w["number"])+":end", cleanup=cleanup)
            except BaseException as exc:
                w["failures"].append(dict(phase="closure", error=type(exc).__name__+": "+str(exc)))
            w["closure_event_after"] = len(j.events)
            if len(j.prefix.points) > before:
                w["end_point"] = len(j.prefix.points)
            end = j.prefix.points[-1] if w["end_point"] else None
            w["counter_error"] = self.counter_error
            tick = w["final_check_ticks"]
            closure_ok = bool(self.counter_error is None and not j.failure and not j.capture_failed and j.prefix.status()["clock_capture_valid"]
                              and end is not None and type(tick) is int and w["deadline_ticks"] is not None
                              and tick <= end["qpc_before_ticks"] and end["qpc_after_ticks"] < w["deadline_ticks"])
            if not closure_ok:
                w["failures"].append(dict(phase="closure", error="collection terminal timing unaccepted or unavailable"))
            if not w["failures"] and w["parsed_result"] is not None:
                w["collection_valid"] = True
                w["result"] = dict(copy.deepcopy(w["parsed_result"]), collection_valid=True)
        return copy.deepcopy(w)


def recovery_candidate(windows):
    valid, context, previous = len(windows) == 3, None, None
    for w in windows:
        try:
            require(w["collection_valid"] and w["result"]["packet_delivery_complete"] and w["mode"] == "official-service", "complete official packet window")
            current = [w["result"]["source_ip"], *[json.loads(w["commands"][i]["stdout"]) for i in (0, 1)]]
            require(context is None or context == current, "changed service context")
            require(previous is None or w["identifier"] == previous+1, "nonconsecutive packet IDs")
            context, previous = current, w["identifier"]
        except (ValueError, TypeError, KeyError):
            valid = False
    return dict(packet_delivery_candidate=bool(valid), required_packets=15, rollback_verified=False, network_fix_validated=False)


if __name__ == "__main__":
    raise SystemExit("No execution CLI. Full committed runner, scope, approval and rollback gate remain required.")
