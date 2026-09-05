"""Independent journal replay. Imports no candidate implementation."""
import json

from tools.audit_reconnect_r5_clock import replay, bounded_int, need

CONTRACT_ID = "safetwin5g-reconnect-r5-journal-v1"


def first_point_valid(d, p):
    # A one-point prefix is never admission evidence. This checks only whether
    # its local schema/read can be retained awaiting a second point.
    if type(p) is not dict or set(p) != {"sequence", "clock_id", "qpc_before_ticks", "qpc_after_ticks",
                                      "filetime_low", "filetime_high", "utc_ns", "capture_error"}:
        return False
    if not (type(p["sequence"]) is int and p["sequence"] == 1 and p["clock_id"] == d["clock_id"] and p["capture_error"] is None):
        return False
    if not (all(bounded_int(p[k], 0, 2**63 - 1) for k in ("qpc_before_ticks", "qpc_after_ticks"))
            and all(bounded_int(p[k], 0, 2**32 - 1) for k in ("filetime_low", "filetime_high"))
            and bounded_int(p["utc_ns"], 0, 253402300799999999900)):
        return False
    return (p["utc_ns"] == (p["filetime_high"] * 2**32 + p["filetime_low"] - 116444736000000000) * 100
            and p["qpc_before_ticks"] <= p["qpc_after_ticks"]
            and (p["qpc_after_ticks"] - p["qpc_before_ticks"] + 2) * 10**9 <= 100000 * d["frequency_hz"])


def audit(snapshot, raw_journal):
    need(type(snapshot) is dict and set(snapshot) == {"contract_id", "descriptor", "points", "events", "reported",
         "journal_failure", "capture_source_failed", "admission_open"}, "snapshot schema")
    need(snapshot["contract_id"] == CONTRACT_ID, "journal contract")
    d, rows, events = snapshot["descriptor"], snapshot["points"], snapshot["events"]
    need(replay(d, [])["rejection"]["code"] == "point-count", "journal clock descriptor")
    need(type(rows) is list and len(rows) <= 1024 and type(events) is list and 1 <= len(events) <= 8192, "journal inventory")
    need(snapshot["journal_failure"] is None, "journal storage failed; no durability claim")
    need(type(raw_journal) is bytes and len(raw_journal) < 8 * 1048576 and raw_journal.endswith(b"\n"), "journal framing/bytes")
    from tools.audit_reconnect_r5_clock import strict_json
    decoded = [strict_json(line) for line in raw_journal.splitlines()]
    need(json.dumps(decoded, sort_keys=True) == json.dumps(events, sort_keys=True), "raw journal differs from snapshot")
    header = dict(kind="header", contract_id=CONTRACT_ID, descriptor=d,
                  admission_point_limit=768, reserved_cleanup_points=256, max_points=1024, event=1)
    need(json.dumps(events[0], sort_keys=True) == json.dumps(header, sort_keys=True), "header or fixed reserve changed")
    expected = replay(d, rows)
    need(json.dumps(expected, sort_keys=True) == json.dumps(snapshot["reported"], sort_keys=True), "independent clock report mismatch")
    captured, source_failed = [], False
    # The first rejected point identifies every later rejected prefix without
    # cubic replays. All-pair arithmetic is independently replayed above.
    bad_at = expected["rejection"]["sequence"] if expected["rejection"] else None
    if rows and not first_point_valid(d, rows[0]):
        bad_at = 1
    for number, event in enumerate(events[1:], 2):
        need(type(event) is dict and type(event.get("event")) is int and event["event"] == number, "event order")
        kind = event.get("kind")
        extra = {"point"} if kind == "point" else {"error"} if kind == "source-error" else {"reason"} if kind == "blocked" else None
        need(extra is not None and set(event) == {"kind", "event", "label", "cleanup"} | extra, "event schema")
        need(type(event["label"]) is str and 0 < len(event["label"]) <= 128 and type(event["cleanup"]) is bool, "event label or scope")
        n, cleanup = len(captured), event["cleanup"]
        reason = ("capture-source-unavailable" if source_failed else
                  "point-capacity" if cleanup and n >= 1024 else
                  "cleanup-reserve" if not cleanup and n >= 768 else
                  "latched-clock-rejection" if not cleanup and bad_at is not None and n >= bad_at else None)
        if reason:
            need(kind == "blocked" and event["reason"] == reason, "missing or altered fail-closed stop")
        else:
            need(kind in ("point", "source-error"), "unexplained blocked read")
            if kind == "point":
                captured.append(event["point"])
            else:
                need(type(event["error"]) is str and bool(event["error"]), "missing source error")
                source_failed = True
    need(json.dumps(captured, sort_keys=True) == json.dumps(rows, sort_keys=True), "point journal mismatch")
    need(type(snapshot["capture_source_failed"]) is bool and snapshot["capture_source_failed"] == source_failed, "source failure claim")
    # Snapshots are explicitly pre-close; closed handles are not admitted.
    admission = bool(expected["clock_capture_valid"] and not source_failed and len(rows) < 768)
    need(type(snapshot["admission_open"]) is bool and snapshot["admission_open"] == admission, "admission claim")
    return dict(observation_audit_passed=True, events_replayed=len(events), points_replayed=len(rows),
                admission_open=admission, capture_source_failed=source_failed, clock=expected,
                network_execution_authorized=False, command_containment_verified=False,
                whole_protocol_verified=False, service_restored=False, network_fix_validated=False)
