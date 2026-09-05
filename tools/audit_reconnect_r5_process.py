"""Independent raw owned-client replay. No candidate process/clock imports."""
import base64
import hashlib
import json

from tools.audit_reconnect_r5_journal import audit as audit_journal
from tools.audit_reconnect_r5_clock import need

CONTRACT_ID = "safetwin5g-reconnect-r5-process-v1"
BOOLS = ("cleanup", "admitted_clock_before", "timer_armed", "timer_signaled", "cleanup_timer_armed",
         "cleanup_timer_signaled", "emergency_timer_only", "launcher_go_sent", "job_assigned_before_go", "job_closed",
         "process_reaped", "reader_threads_joined", "timed_out", "truncated", "timing_valid", "client_capture_complete", "complete",
         "stdout_utf8", "stderr_utf8")
TICKS = ("checked_ticks", "go_before_ticks", "go_after_ticks", "completion_observed_ticks", "cleanup_completed_ticks", "deadline_ticks")
KEYS = set(BOOLS) | set(TICKS) | {"contract_id", "sequence", "argv", "timeout_ms", "max_output_bytes", "cleanup_grace_ms",
       "clock_id", "journal_event_before", "journal_event_after", "start_point", "end_point", "counter_error",
       "timer_due_100ns", "owned_launcher_pid", "process_errors", "cleanup_errors", "returncode", "retained_output_bytes",
       "stdout", "stderr", "stdout_base64", "stderr_base64", "stdout_sha256", "stderr_sha256"}


def integer(v, lo=0, hi=2**63 - 1):
    return type(v) is int and lo <= v <= hi


def audit(rows, snapshot, raw_journal, allowed, cleanup_allowed=()):
    journal = audit_journal(snapshot, raw_journal)
    need(type(rows) is list and 0 < len(rows) <= 2048, "process inventory")
    permitted, cleanup_permitted = {tuple(a) for a in allowed}, {tuple(a) for a in cleanup_allowed}
    need(cleanup_permitted <= permitted, "cleanup allowlist")
    points, events = snapshot["points"], snapshot["events"]
    frequency = snapshot["descriptor"]["frequency_hz"]
    rejection = journal["clock"]["rejection"]
    first_bad = rejection["sequence"] if rejection else None
    source_errors = [e["event"] for e in events if e["kind"] == "source-error"]
    need(sum(type(e.get("label")) is str and e["label"].startswith("process:") for e in events) == len(rows), "missing process checkpoint record")
    prior_event, prior_counter_error = 1, None
    decisions = []
    for seq, r in enumerate(rows, 1):
        need(type(r) is dict and set(r) == KEYS and r["contract_id"] == CONTRACT_ID, "process schema")
        need(type(r["sequence"]) is int and r["sequence"] == seq, "process sequence")
        need(all(type(r[k]) is bool for k in BOOLS), "typed process flags")
        need(type(r["argv"]) is list and all(type(a) is str for a in r["argv"]) and tuple(r["argv"]) in permitted, "process argv")
        need(not r["cleanup"] or tuple(r["argv"]) in cleanup_permitted, "unapproved cleanup argv")
        need(r["clock_id"] == snapshot["descriptor"]["clock_id"], "process clock domain")
        need(integer(r["timeout_ms"], 1, 35000) and integer(r["max_output_bytes"], 1, 1048576)
             and type(r["cleanup_grace_ms"]) is int and r["cleanup_grace_ms"] == 2000, "process bounds")
        for name in TICKS:
            need(r[name] is None or integer(r[name]), "QPC field integer")
        need(r["counter_error"] is None or (type(r["counter_error"]) is str and r["counter_error"]), "counter error")
        need(prior_counter_error is None or r["counter_error"] == prior_counter_error, "counter error latch cleared")
        prior_counter_error = r["counter_error"] or prior_counter_error
        for name in ("process_errors", "cleanup_errors"):
            need(type(r[name]) is list and all(type(e) is str and e for e in r[name]), "error inventory")
        a, b = r["journal_event_before"], r["journal_event_after"]
        need(integer(a, 1, len(events)) and integer(b, 1, len(events)) and a >= prior_event and b == a + 1, "process/journal event order")
        terminal = events[b - 1]
        need(terminal["label"] == "process:" + str(seq) + ":end" and terminal["cleanup"] == r["cleanup"], "terminal clock checkpoint")
        n = sum(e["kind"] == "point" for e in events[:a])
        m = n + int(terminal["kind"] == "point")
        need(r["start_point"] == (n or None) and type(r["start_point"]) is type(n or None), "start envelope reference")
        need(r["end_point"] == (m if m > n else None) and type(r["end_point"]) is type(m if m > n else None), "end envelope reference")
        prior_event = b
        def prefix_ok(count, through_event):
            return (count >= 2 and (first_bad is None or count < first_bad)
                    and not any(event <= through_event for event in source_errors))
        admitted = prefix_ok(n, a) and n < 768
        need(r["admitted_clock_before"] == admitted, "clock admission before process")
        need(r["cleanup"] or not r["launcher_go_sent"] or (admitted and r["counter_error"] is None
             or admitted and r["go_before_ticks"] is not None), "normal dispatch despite failed initial clock admission")
        size = 0
        for stream in ("stdout", "stderr"):
            need(type(r[stream + "_base64"]) is str, "base64 string")
            raw = base64.b64decode(r[stream + "_base64"], validate=True)
            need(hashlib.sha256(raw).hexdigest() == r[stream + "_sha256"], "raw process stream hash")
            try:
                value, valid = raw.decode("utf-8", "strict"), True
            except UnicodeDecodeError:
                value, valid = raw.decode("utf-8", "replace"), False
            need(r[stream] == value and r[stream + "_utf8"] == valid, "stream decode claim")
            need(valid or any("invalid UTF-8" in e for e in r["process_errors"]), "missing decode rejection")
            size += len(raw)
        need(integer(r["retained_output_bytes"], 0, r["max_output_bytes"]) and r["retained_output_bytes"] == size, "retained byte cap")
        need(size < r["max_output_bytes"] or r["truncated"], "saturated output accepted")
        need(r["owned_launcher_pid"] is None or integer(r["owned_launcher_pid"], 1, 2**32 - 1), "owned PID")
        need(r["returncode"] is None or type(r["returncode"]) is int, "return code")
        need(not r["launcher_go_sent"] or (r["job_assigned_before_go"] and r["timer_armed"] and r["owned_launcher_pid"] is not None), "GO without owned containment/timer")
        need(not r["timer_signaled"] or r["timed_out"], "timer expiration not rejected")
        need(r["timer_due_100ns"] is None or integer(r["timer_due_100ns"], 1, r["timeout_ms"] * 10000), "relative timer bound")
        need(not r["timer_armed"] or r["timer_due_100ns"] is not None, "missing armed timer duration")
        start, end = points[n - 1] if n else None, points[m - 1] if m > n else None
        if start is not None and type(start.get("qpc_before_ticks")) is int and r["deadline_ticks"] is not None:
            need(r["deadline_ticks"] == start["qpc_before_ticks"] + r["timeout_ms"] * frequency // 1000, "unaccounted envelope overhead/deadline")
            if r["checked_ticks"] is not None and r["timer_due_100ns"] is not None:
                remaining = (r["deadline_ticks"] - r["checked_ticks"]) * 10000000 // frequency
                need(r["timer_due_100ns"] == (remaining if remaining > 0 else r["timeout_ms"] * 10000), "relative timer enlarged/changed")
        timing = False
        ts = [r[k] for k in TICKS[:-1]]
        if (not r["counter_error"] and not r["emergency_timer_only"] and prefix_ok(m, b)
                and start is not None and end is not None and all(type(t) is int for t in ts)
                and r["deadline_ticks"] is not None):
            timing = (start["qpc_after_ticks"] <= ts[0] <= ts[1] <= ts[2] <= ts[3] <= ts[4] <= end["qpc_before_ticks"]
                      and ts[3] < r["deadline_ticks"] and (ts[4] - ts[3]) * 1000 < 2000 * frequency)
        captured = bool(r["launcher_go_sent"] and r["job_assigned_before_go"] and r["job_closed"] and r["process_reaped"]
                        and r["reader_threads_joined"] and not r["timed_out"] and not r["truncated"]
                        and not r["process_errors"] and not r["cleanup_errors"])
        need(r["timing_valid"] == timing and r["client_capture_complete"] == captured and r["complete"] == (timing and captured), "process completion/containment claim")
        decisions.append(dict(sequence=seq, timing_valid=timing, client_capture_complete=captured,
                              complete=timing and captured, returncode=r["returncode"]))
    return dict(observation_audit_passed=True, commands_replayed=len(rows), decisions=decisions,
                clock_journal=journal, network_execution_authorized=False, whole_protocol_verified=False,
                official_rollback_verified=False, network_fix_validated=False)
