"""Independent raw health/wait/budget replay and prospective count check.

No candidate budget/clock/process acceptance imports. Not whole-run replay.
"""
import json
from tools.audit_reconnect_r5_journal import audit as journal_audit
from tools.audit_reconnect_r5_process import audit as process_audit, integer
from tools.audit_reconnect_r5_clock import need

CONTRACT = "safetwin5g-reconnect-r5-budget-v1"
TARGETS = ("safetwin5g-open5gs", "safetwin5g-gnb", "safetwin5g-ue")


def audit_inventory(p):
    # Independent enumeration of proposed cleanup command/terminal groups.
    groups = {
        "owned_qdisc": ["inspect", "delete-owned", "verify"],
        "both_image_attempts": [f"{c}:{s}" for c in ("gnb", "ue") for s in ["tag", "apply", *[f"poll-{i}" for i in range(25)], "health-end"]],
        "post_image_scope": ["network", "containers"],
        "independent_reset": ["before-ids", "before-log", *[f"{c}:{s}" for c in TARGETS for s in ["restart", *[f"poll-{i}" for i in range(25)], "health-end"]], "after-ids", "after-log"],
        "three_packet_telemetry_windows": [f"{i}:{s}" for i in range(3) for s in [*[f"capture-{j}" for j in range(15)], "capture-end", "qdisc", "upf", "workers", "targets"]],
        "final_scope": ["network", "containers"], "final_eth0": ["qdisc"], "final_telemetry": ["qdisc", "upf", "workers", "targets"],
        "host_close": ["power", "receipt"], "execution_terminal": ["end"],
    }
    terms = {k: len(v) for k, v in groups.items()}
    expected = dict(contract_id=CONTRACT, normal_limit=768, total_limit=1024, reserved_cleanup=256,
                    health_max_polls=25, health_waits_max=24, health_points_max=26, collection_with_telemetry_points=20,
                    normal_nominal_points=741, unpruned_normal_upper_points=1895, cleanup_point_terms=terms,
                    cleanup_points_max=216, admitted_prefix_plus_cleanup_max=984, capacity_headroom=40,
                    packet_identifier_upper_unpruned=51, guarantees_four_complete_trials=False, runner_implemented=False,
                    whole_protocol_verified=False, network_execution_authorized=False, evidence_label="fixture")
    need(json.dumps(p, sort_keys=True) == json.dumps(expected, sort_keys=True), "prospective inventory/claim drift")
    return dict(inventory_audit_passed=True, enumerated_cleanup_points=sum(terms.values()), nominal_normal_fits=True,
                unpruned_upper_fits=False, bounded_prefix_plus_cleanup_fits=True, actual_runner_conformance_verified=False)


def audit(b, snapshot, raw_journal):
    journal = journal_audit(snapshot, raw_journal)
    need(set(b) == set("contract_id clock_id start_point global_deadline_ticks admissions operations counter_error whole_protocol_verified network_execution_authorized rollback_verified network_fix_validated".split()) and b["contract_id"] == CONTRACT, "budget schema")
    need(all(b[k] is False for k in ("whole_protocol_verified", "network_execution_authorized", "rollback_verified", "network_fix_validated")), "budget authority promotion")
    points, events, f = snapshot["points"], snapshot["events"], snapshot["descriptor"]["frequency_hz"]
    need(b["clock_id"] == snapshot["descriptor"]["clock_id"] and integer(b["start_point"], 2, len(points)), "budget starting domain")
    global_due = points[b["start_point"]-1]["qpc_before_ticks"]+1500*f
    need(type(b["global_deadline_ticks"]) is int and b["global_deadline_ticks"] == global_due, "global deadline reset")
    bad = journal["clock"]["rejection"]
    unavailable = [e["event"] for e in events if e["kind"] == "source-error"]
    def n_at(ev):
        return sum(e["kind"] == "point" for e in events[:ev])
    def prefix(n, ev):
        return n >= 2 and (bad is None or n < bad["sequence"]) and not any(x <= ev for x in unavailable)
    def tick(value):
        need(value is None or integer(value), "budget tick type")
        return value is not None
    need(type(b["operations"]) is list and 0 < len(b["operations"]) <= 128 and type(b["admissions"]) is list, "budget operation inventory")
    rows = [r for w in b["operations"] for r in w["commands"]]
    allow = [["docker", "inspect", "--format", "{{.State.Health.Status}}", c] for c in TARGETS]
    process = process_audit(rows, snapshot, raw_journal, allow, allow) if rows else None
    need(sum(str(e.get("label", "")).startswith("budget:") for e in events) == len(b["operations"]), "unaccounted budget terminal")
    for a in b["admissions"]:
        need(set(a) == set("label point event ticks points_needed seconds_needed global_deadline_ticks counter_error admitted".split())
             and type(a["label"]) is str and 0 < len(a["label"]) <= 80 and integer(a["event"], 1, len(events)), "admission schema")
        n = n_at(a["event"])
        need(type(a["point"]) is int and a["point"] == n and integer(a["points_needed"], 1, 768) and integer(a["seconds_needed"], 1, 1500)
             and a["global_deadline_ticks"] == global_due, "admission bounds")
        ok = bool(tick(a["ticks"]) and prefix(n, a["event"]) and n+a["points_needed"] <= 768
                  and points[n-1]["qpc_after_ticks"] <= a["ticks"] and a["ticks"]+a["seconds_needed"]*f <= global_due)
        need(type(a["admitted"]) is bool and a["admitted"] == ok, "admission claim")
        need(a["ticks"] is not None or type(a["counter_error"]) is str and a["counter_error"], "unreported admission counter failure")
    decisions, last_event, seq, counter = [], None, 1, None
    last_budget_tick, budget_tick_failed = None, False
    for number, w in enumerate(b["operations"], 1):
        need(set(w) == set("number kind label cleanup start_point start_event deadline_ticks checks commands waits final_ticks end_point terminal_before terminal_after counter_error errors accepted".split()), "timing operation schema")
        need(type(w["number"]) is int and w["number"] == number and w["kind"] in ("health", "settle") and type(w["cleanup"]) is bool
             and type(w["accepted"]) is bool and type(w["errors"]) is list and all(type(e) is str and e for e in w["errors"]), "operation types")
        need(w["counter_error"] is None or type(w["counter_error"]) is str and w["counter_error"], "operation counter error")
        need(counter is None or w["counter_error"] == counter, "counter failure latch erased")
        counter = w["counter_error"] or counter
        ev = w["start_event"]
        need(integer(ev, 1, len(events)) and (ev == last_event if last_event is not None else all(e["kind"] == "point" and str(e.get("label", "")).startswith("bootstrap:") for e in events[1:ev])), "standalone timing event inventory")
        n = n_at(ev)
        need(type(w["start_point"]) is int and w["start_point"] == n and type(w["checks"]) is list and type(w["commands"]) is list and type(w["waits"]) is list, "timing inventory")
        checks, cmds, waits = w["checks"], w["commands"], w["waits"]
        expected_failure = False
        if w["kind"] == "settle":
            need(not w["cleanup"] and w["deadline_ticks"] is None and len(checks) == 1 and not cmds and len(waits) <= 1, "settle contract")
            a = checks[0]
            need(a in b["admissions"] and a["label"] == w["label"] and a["event"] == ev and a["points_needed"] == 1 and a["seconds_needed"] == 5, "settle admission linkage")
            expected_failure = not a["admitted"]
            need(len(waits) == int(a["admitted"]), "settle wait dispatch")
        else:
            need(w["label"] in TARGETS and 1 <= len(checks) <= 26 and len(cmds) <= 25 and len(waits) <= 24, "health fixed inventory")
            deadline = points[n-1]["qpc_before_ticks"]+50*f if integer(points[n-1]["qpc_before_ticks"]) else None
            need(type(w["deadline_ticks"]) is type(deadline) and w["deadline_ticks"] == deadline, "health deadline reset")
            a = checks[0]
            need(set(a) == set("ticks event point points_needed admitted".split()) and a["event"] == ev and a["point"] == n and type(a["points_needed"]) is int and a["points_needed"] == 26, "health whole-operation reservation")
            initial_ok = bool(tick(a["ticks"]) and prefix(n, ev) and n+26 <= (1024 if w["cleanup"] else 768)
                              and points[n-1]["qpc_after_ticks"] <= a["ticks"] and deadline is not None and a["ticks"] < deadline
                              and (w["cleanup"] or a["ticks"]+50*f <= global_due))
            need(type(a["admitted"]) is bool and a["admitted"] == initial_ok, "health admission claim")
            expected_failure, healthy = not initial_ok, False
            for poll, c in enumerate(checks[1:], 1):
                need(not expected_failure and not healthy and set(c) == set("ticks event point poll timeout_ms admitted".split())
                     and type(c["poll"]) is int and c["poll"] == poll, "extra health poll")
                n = n_at(ev)
                due = deadline if w["cleanup"] else min(deadline, global_due)
                timeout = min(35000, (due-points[n-1]["qpc_before_ticks"])*1000//f) if integer(points[n-1]["qpc_before_ticks"]) else None
                ok = bool(tick(c["ticks"]) and prefix(n, ev) and points[n-1]["qpc_after_ticks"] <= c["ticks"] < due and timeout is not None and timeout >= 1)
                need(c["event"] == ev and c["point"] == n and type(c["timeout_ms"]) is type(timeout) and c["timeout_ms"] == timeout
                     and type(c["admitted"]) is bool and c["admitted"] == ok, "health poll budget claim")
                if not ok or poll > len(cmds):
                    expected_failure = True
                    need(len(cmds) == poll-1, "health command after rejected poll")
                    continue
                r = cmds[poll-1]
                need(r["sequence"] == seq and r["journal_event_before"] == ev and r["argv"] == allow[TARGETS.index(w["label"])]
                     and r["cleanup"] is w["cleanup"] and r["timeout_ms"] == timeout and r["max_output_bytes"] == 1048576, "health process linkage")
                need(r["checked_ticks"] is None or r["checked_ticks"] >= c["ticks"], "health dispatch before check")
                ev, seq = r["journal_event_after"], seq+1
                valid = r["complete"] and type(r["returncode"]) is int and r["returncode"] == 0 and r["stdout_utf8"] and r["stderr_utf8"] and not r["stderr"]
                status = r["stdout"].strip()
                healthy = bool(valid and status == "healthy")
                if not valid or status not in ("healthy", "unhealthy", "starting") or not healthy and poll == 25:
                    expected_failure = True
                if not healthy and not expected_failure:
                    need(poll <= len(waits), "missing health wait")
                    wait = waits[poll-1]
                    need(wait["event"] == ev and wait["point"] == n_at(ev), "wait/health linkage")
                    if not wait["returned"] or wait["error"] or wait["after_ticks"] is None or wait["before_ticks"] is None or (wait["after_ticks"]-wait["before_ticks"])*1000 < 2000*f:
                        expected_failure = True
                    if poll < len(cmds) and wait["after_ticks"] is not None:
                        need(cmds[poll]["checked_ticks"] is None or cmds[poll]["checked_ticks"] >= wait["after_ticks"], "poll before wait returned")
            need(len(cmds) <= len(checks)-1 and (expected_failure or healthy), "unexplained health termination")
            need(len(waits) == sum(r["complete"] and r["returncode"] == 0 and not r["stderr"] and r["stdout"].strip() in ("unhealthy", "starting") and i < 24 for i, r in enumerate(cmds)), "unaccounted wait")
        for wait in waits:
            need(set(wait) == set("milliseconds event point before_ticks after_ticks called returned error".split()) and type(wait["milliseconds"]) is int
                 and wait["milliseconds"] == (5000 if w["kind"] == "settle" else 2000) and type(wait["called"]) is bool and type(wait["returned"]) is bool, "wait schema")
            need(wait["error"] is None or type(wait["error"]) is str and wait["error"], "wait error")
            need(integer(wait["event"], w["start_event"], len(events)) and wait["point"] == n_at(wait["event"]), "wait anchor")
            available = tick(wait["before_ticks"])
            need(wait["called"] == available and (not wait["returned"] or wait["called"]), "wait dispatch accounting")
            if available:
                need(wait["before_ticks"] >= points[wait["point"]-1]["qpc_after_ticks"], "wait before preceding envelope")
            if tick(wait["after_ticks"]):
                need(wait["before_ticks"] is not None and wait["after_ticks"] >= wait["before_ticks"], "wait counter reversal")
            if not wait["returned"] or wait["error"] or wait["after_ticks"] is None or wait["before_ticks"] is None or (wait["after_ticks"]-wait["before_ticks"])*1000 < wait["milliseconds"]*f:
                expected_failure = True
        # Reconstruct every helper counter read in call order. Individual
        # anchor containment is insufficient: a check cannot precede its
        # initial admission or the return of the previous poll's wait.
        ordered = [checks[0]["ticks"]]
        if w["kind"] == "health":
            for poll, check in enumerate(checks[1:]):
                ordered.append(check["ticks"])
                if poll < len(waits):
                    ordered.extend((waits[poll]["before_ticks"], waits[poll]["after_ticks"]))
        else:
            for wait in waits:
                ordered.extend((wait["before_ticks"], wait["after_ticks"]))
        ordered.append(w["final_ticks"])
        for value in ordered:
            if not tick(value):
                budget_tick_failed = True
            else:
                need(not budget_tick_failed and (last_budget_tick is None or value >= last_budget_tick), "budget raw counter order/latch")
                last_budget_tick = value
        need(not budget_tick_failed or w["counter_error"] is not None, "missing raw counter failure latch")
        need(w["terminal_before"] == ev and w["terminal_after"] == ev+1 and ev+1 <= len(events), "timing closure event")
        terminal = events[ev]
        need(terminal["label"] == "budget:"+str(number)+":end" and terminal["cleanup"] is w["cleanup"], "timing closure label")
        end = n_at(ev+1) if terminal["kind"] == "point" else None
        need(type(w["end_point"]) is type(end) and w["end_point"] == end, "timing closure point")
        valid_end = bool(tick(w["final_ticks"]) and end and prefix(end, ev+1) and w["counter_error"] is None and w["final_ticks"] <= points[end-1]["qpc_before_ticks"])
        if cmds and cmds[-1]["cleanup_completed_ticks"] is not None and w["final_ticks"] is not None:
            need(w["final_ticks"] >= cmds[-1]["cleanup_completed_ticks"], "timing closure before process")
        for wait in waits:
            if wait["after_ticks"] is not None and w["final_ticks"] is not None:
                need(wait["after_ticks"] <= w["final_ticks"], "timing closure before wait")
        if w["kind"] == "health":
            valid_end = bool(valid_end and w["deadline_ticks"] is not None and points[end-1]["qpc_after_ticks"] < w["deadline_ticks"])
        if not w["cleanup"]:
            valid_end = bool(valid_end and points[end-1]["qpc_after_ticks"] < global_due)
        ok = not expected_failure and valid_end
        need(w["accepted"] == ok and bool(w["errors"]) == (not ok), "timing acceptance claim")
        decisions.append(dict(number=number, accepted=ok, commands=len(cmds), waits=len(waits)))
        last_event = ev+1
    need(last_event == len(events) and b["counter_error"] == counter, "unaccounted terminal/latch")
    return dict(observation_audit_passed=True, decisions=decisions, process_audit=process, journal_audit=journal if process is None else None,
                whole_protocol_verified=False, rollback_verified=False, network_execution_authorized=False)
