"""Independent host lifecycle replay. No candidate implementation imports."""
import json
import re

from tools.audit_reconnect_r5_journal import audit as audit_journal
from tools.audit_reconnect_r5_process import audit as audit_process
from tools.audit_reconnect_r5_clock import need, strict_json

CONTRACT = "safetwin5g-reconnect-r5-host-v1"


def idle_command(pid):
    return ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
            "$ErrorActionPreference='Stop'; $busy=@(Get-CimInstance Win32_Process | "
            "Where-Object { $_.Name -match '^python(?:w)?(?:[.]exe)?$' "
            + f"-and $_.ProcessId -ne {pid} "
            + "-and ($_.CommandLine -eq $null -or $_.CommandLine -match "
            "'run_(?:phase7|recovery_pilot|reconnect(?:_r[0-9]+)?)[.]py') }); "
            "if ($busy.Count -ne 0) { $busy | Select-Object -ExpandProperty ProcessId; exit 3 }; "
            "[Console]::Out.WriteLine('SAFETWIN_R5_IDLE_V1')"]


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


def integer(value):
    return type(value) is int and 0 <= value < 2**63


def errors(value):
    return type(value) is list and all(type(v) is str and v for v in value)


def audit(host, snapshot, raw_journal, receipt):
    clock_audit = audit_journal(snapshot, raw_journal)
    expected_keys = {"contract_id", "owner_pid", "clock_id", "operations", "idle_command", "idle_ok", "start_point",
                     "admission_deadline_ticks", "admitted", "closed", "errors", "counter_error", "lease", "power",
                     "component_complete", "network_execution_authorized", "whole_protocol_verified", "service_restored", "network_fix_validated"}
    need(type(host) is dict and set(host) == expected_keys and host["contract_id"] == CONTRACT, "host schema")
    for name in ("idle_ok", "admitted", "closed", "component_complete", "network_execution_authorized", "whole_protocol_verified", "service_restored", "network_fix_validated"):
        need(type(host[name]) is bool, "typed host flags")
    need(not any(host[k] for k in ("network_execution_authorized", "whole_protocol_verified", "service_restored", "network_fix_validated")), "host claim promotion")
    need(host["closed"] and errors(host["errors"]), "host final lifecycle/errors")
    d, ps, events = snapshot["descriptor"], snapshot["points"], snapshot["events"]
    need(type(host["owner_pid"]) is int and host["owner_pid"] == d["owner_pid"] and host["clock_id"] == d["clock_id"], "host domain")
    bad = clock_audit["clock"]["rejection"]
    bad_at = bad["sequence"] if bad else None
    failures = [e["event"] for e in events if e["kind"] == "source-error"]
    def good(n, event):
        return n >= 2 and (bad_at is None or n < bad_at) and not any(e <= event for e in failures)
    ops = host["operations"]
    need(type(ops) is list and [o.get("name") for o in ops] in
         (["clear", "release"], ["acquire", "clear", "release"], ["acquire", "enable", "clear", "release"]), "host operation order")
    need(sum(str(e.get("label", "")).startswith("host:") for e in events) == len(ops), "unreferenced host checkpoint")
    first_event = ops[0]["event_before"]
    initial_n = sum(e["kind"] == "point" for e in events[:first_event])
    need(type(host["start_point"]) is type(initial_n or None) and host["start_point"] == (initial_n or None), "host starting anchor")
    initially_admissible = good(initial_n, first_event) and initial_n + 3 <= 768
    expected_deadline = ps[initial_n - 1]["qpc_before_ticks"] + 35 * d["frequency_hz"] if initially_admissible else None
    need(type(host["admission_deadline_ticks"]) is type(expected_deadline) and host["admission_deadline_ticks"] == expected_deadline, "host 35 s shared budget")
    need((ops[0]["name"] == "acquire") == initially_admissible, "initial point reservation bypass")
    accepted, last_event, latch = {}, first_event, None
    for o in ops:
        need(set(o) == {"name", "cleanup", "start_point", "end_point", "event_before", "event_after", "checked_ticks", "returned_ticks", "deadline_ticks", "called", "returned", "errors", "timing_valid", "counter_error"}, "host operation schema")
        for k in ("cleanup", "called", "returned", "timing_valid"):
            need(type(o[k]) is bool, "typed operation flag")
        need(errors(o["errors"]) and (o["counter_error"] is None or type(o["counter_error"]) is str and o["counter_error"]), "host operation errors")
        need(latch is None or o["counter_error"] == latch, "host counter latch erased")
        latch = o["counter_error"] or latch
        a, b = o["event_before"], o["event_after"]
        need(type(a) is int and type(b) is int and last_event <= a < b <= len(events) and b == a + 1, "host journal event linkage")
        last_event = b
        terminal = events[b - 1]
        cleanup = o["name"] in ("clear", "release")
        need(o["cleanup"] == cleanup and terminal["cleanup"] == cleanup and terminal["label"] == "host:" + o["name"] + ":end", "host terminal checkpoint")
        n = sum(e["kind"] == "point" for e in events[:a])
        m = n + (terminal["kind"] == "point")
        for key, val in (("start_point", n or None), ("end_point", m if m > n else None)):
            need(type(o[key]) is type(val) and o[key] == val, "host envelope reference")
        start, end = ps[n - 1] if n else None, ps[m - 1] if m > n else None
        deadline = (start["qpc_before_ticks"] + 2 * d["frequency_hz"] if cleanup and start is not None and type(start["qpc_before_ticks"]) is int
                    else None if cleanup else expected_deadline)
        need(type(o["deadline_ticks"]) is type(deadline) and o["deadline_ticks"] == deadline, "host callback bound changed")
        x, y = o["checked_ticks"], o["returned_ticks"]
        need(all(v is None or integer(v) for v in (x, y)), "host QPC integer")
        need(not cleanup or o["called"], "earlier failure suppressed mandatory host cleanup")
        if o["called"] and not cleanup:
            need(good(n, a) and n < 768 and integer(x) and deadline is not None and start["qpc_after_ticks"] <= x < deadline, "host callback admission")
        timing = bool(latch is None and good(m, b) and start is not None and end is not None and integer(x) and integer(y)
                      and deadline is not None and start["qpc_after_ticks"] <= x <= y <= end["qpc_before_ticks"] and y < deadline)
        need(o["timing_valid"] == timing and (timing or "host callback timing unavailable or rejected" in o["errors"]), "host timing verdict")
        need(not o["returned"] or o["called"], "callback returned without call")
        accepted[o["name"]] = o["returned"] and timing and not o["errors"]
    need(host["counter_error"] == latch, "host final counter latch")
    idle = host["idle_command"]
    idle_ok = False
    if idle is not None:
        need(accepted.get("acquire") is True, "idle before acquired receipt")
        pa = audit_process([idle], snapshot, raw_journal, [idle_command(d["owner_pid"])])
        acquire = ops[0]
        following = ops[1]
        need(idle["journal_event_before"] == acquire["event_after"] and idle["journal_event_after"] == following["event_before"], "idle/host exact event order")
        remaining = (expected_deadline - ps[idle["start_point"] - 1]["qpc_before_ticks"]) * 1000 // d["frequency_hz"]
        need(idle["timeout_ms"] == min(35000, remaining) and idle["max_output_bytes"] == 1048576 and not idle["cleanup"], "idle residual shared budget")
        idle_ok = pa["decisions"][0]["complete"] and idle["returncode"] == 0 and idle["stderr"] == "" and idle["stdout"] in ("SAFETWIN_R5_IDLE_V1\n", "SAFETWIN_R5_IDLE_V1\r\n")
    else:
        need(not any(str(e.get("label", "")).startswith("process:") for e in events), "omitted idle process")
    need(host["idle_ok"] == idle_ok and ("enable" in accepted) == idle_ok, "idle admission verdict")
    lease = host["lease"]
    need(type(lease) is dict and set(lease) == {"header", "acquire_attempted", "created", "header_persisted", "close_attempted", "footer_persisted", "handle_closed", "errors"}, "receipt schema")
    need(all(type(lease[k]) is bool for k in lease if k not in ("header", "errors")) and errors(lease["errors"]), "receipt flags/errors")
    header = lease["header"]
    need(set(header) == {"kind", "contract_id", "owner_pid", "clock_id", "revision_sha256", "token"}
         and header["kind"] == "created" and header["contract_id"] == CONTRACT and header["owner_pid"] == d["owner_pid"]
         and type(header["owner_pid"]) is int and header["clock_id"] == d["clock_id"]
         and type(header["revision_sha256"]) is str and re.fullmatch("[0-9a-f]{64}", header["revision_sha256"])
         and type(header["token"]) is str and re.fullmatch("[0-9a-f]{32}", header["token"]), "receipt ownership/revision")
    acquire_op = next((o for o in ops if o["name"] == "acquire"), None)
    need(lease["acquire_attempted"] == bool(acquire_op and acquire_op["called"]) and lease["close_attempted"], "receipt lifecycle calls")
    need(not lease["created"] or lease["acquire_attempted"], "receipt created without exclusive attempt")
    need(not lease["header_persisted"] or lease["created"], "receipt persistence without owned file")
    if acquire_op:
        need(acquire_op["returned"] == (lease["created"] and lease["header_persisted"]), "receipt acquisition return claim")
    need(not lease["acquire_attempted"] or lease["created"] or bool(lease["errors"]), "missing failed exclusive-create result")
    if lease["created"]:
        need(not lease["errors"], "receipt storage/ownership failed; no durability claim")
        need(lease["header_persisted"] and lease["footer_persisted"] and lease["handle_closed"] and type(receipt) is bytes and receipt.endswith(b"\n"), "receipt durability/closure")
        need(canonical([strict_json(line) for line in receipt.splitlines()]) == canonical([header, dict(kind="close-intent", token=header["token"])]), "raw receipt changed")
    else:
        need(receipt is None and not lease["header_persisted"] and not lease["footer_persisted"] and not lease["handle_closed"], "unowned receipt must not be read/claimed")
    release_op = next(o for o in ops if o["name"] == "release")
    need(release_op["returned"] == (not lease["created"] or lease["footer_persisted"] and lease["handle_closed"]), "receipt closure return claim")
    power = host["power"]
    need(set(power) == {"mechanism", "calls", "closed"} and power["mechanism"] == "PowerRequestSystemRequired" and type(power["closed"]) is bool, "owned power schema")
    calls = power["calls"]
    need(type(calls) is list and [c.get("name") for c in calls] in ([], ["create"], ["create", "set", "clear", "close"]), "power call sequence")
    for c in calls:
        need(set(c) == {"name", "result", "error"} and (c["error"] is None or type(c["error"]) is str and c["error"]), "power result/error schema")
        need(c["result"] is None or type(c["result"]) is int, "typed power return")
        valid = type(c["result"]) is int and (0 < c["result"] < 2**64 - 1 if c["name"] == "create" else c["result"] != 0)
        need(valid or c["error"] is not None, "missing native failure")
    enable_op = next((o for o in ops if o["name"] == "enable"), None)
    need(bool(calls) == bool(enable_op and enable_op["called"]), "power call without admitted callback")
    created = bool(calls and calls[0]["error"] is None)
    need((len(calls) == 4) == created, "clear/close skipped after acquired power handle")
    need(power["closed"] == (not created or calls[-1]["error"] is None), "power handle closure claim")
    if enable_op:
        need(enable_op["returned"] == bool(created and calls[1]["error"] is None), "power enable return claim")
    clear_op = next(o for o in ops if o["name"] == "clear")
    need(clear_op["returned"] == (not created or all(c["error"] is None for c in calls[2:])), "power cleanup return claim")
    admitted = bool(accepted.get("acquire") and idle_ok and accepted.get("enable"))
    need(host["admitted"] == admitted and bool(host["errors"]) == (not admitted), "host admission result")
    complete = admitted and all(accepted.values()) and lease["header_persisted"] and lease["footer_persisted"] and lease["handle_closed"] and power["closed"]
    need(host["component_complete"] == complete, "host component completion")
    return dict(observation_audit_passed=True, host_component_complete=complete, admitted=admitted,
                operations_replayed=len(ops), idle_commands_replayed=int(idle is not None),
                clock_points=len(ps), clock=clock_audit["clock"],
                network_execution_authorized=False, whole_protocol_verified=False, service_restored=False,
                network_fix_validated=False)
