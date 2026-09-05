"""Closed-window trace accounting. Never substitute this for a packet-loss gate."""
import re

STAGES = {"nas_in", "nas_forward", "nas_idle", "ue_rls", "gnb_in", "gnb_missing", "gnb_resource"}
FIELDS = "psi actor cm mm ps pending ipid id seq bytes fp".split()
PATTERN = re.compile(r"ST3 stage=(\w+) " + " ".join(key + r"=(-?\d+)" for key in FIELDS) + r"$")


def parse(text, component):
    if component not in ("ue", "gnb"):
        raise ValueError("unknown trace component")
    rows = []
    for line in text.splitlines():
        if "ST3" not in line:
            continue
        match = PATTERN.search(line)
        if not match:
            raise ValueError("malformed trace line")
        stage = match.group(1)
        row = {key: int(value) for key, value in zip(FIELDS, match.groups()[1:])}
        if stage not in STAGES or stage.startswith("gnb_") != (component == "gnb"):
            raise ValueError("stage/component mismatch")
        if (row["psi"] != 1 or not 10001 <= row["id"] <= 10099 or not 1 <= row["seq"] <= 5
                or not 0 <= row["ipid"] <= 65535 or not 28 <= row["bytes"] <= 65535 or not 0 <= row["fp"] < 2**64):
            raise ValueError("trace identity outside contract")
        rows.append({"stage": stage, **row})
    return rows


def account_window(rows, identifier, replies):
    """Caller must separately verify log scope/completeness and raw ping count."""
    if not 10001 <= identifier <= 10099 or not set(replies) <= set(range(1, 6)) or len(replies) != len(set(replies)):
        raise ValueError("window identity/replies")
    selected = [r for r in rows if r["id"] == identifier]
    packets = []
    for seq in range(1, 6):
        events = [r for r in selected if r["seq"] == seq]
        stages = [r["stage"] for r in events]
        if len(stages) != len(set(stages)):
            raise ValueError("duplicate stage identity")
        if len({(r["ipid"], r["bytes"], r["fp"]) for r in events}) != 1:
            raise ValueError("missing packet or fingerprint mismatch")
        by_stage = {r["stage"]: r for r in events}
        if "nas_idle" in stages:
            if set(stages) != {"nas_in", "nas_idle"} or stages != ["nas_in", "nas_idle"] or seq in replies:
                raise ValueError("idle packet has inconsistent downstream/reply evidence")
            if by_stage["nas_in"]["cm"] != 0 or by_stage["nas_idle"]["cm"] != 0 or by_stage["nas_idle"]["ps"] != 1:
                raise ValueError("idle branch state mismatch")
            fate = "nas_idle_nonretention_observed"
        else:
            terminal = "gnb_missing" if "gnb_missing" in stages else "gnb_resource"
            if set(stages) != {"nas_in", "nas_forward", "ue_rls", "gnb_in", terminal}:
                raise ValueError("incomplete or contradictory forwarded path")
            ue_order = [stage for stage in stages if not stage.startswith("gnb_")]
            gnb_order = [stage for stage in stages if stage.startswith("gnb_")]
            if ue_order != ["nas_in", "nas_forward", "ue_rls"] or gnb_order != ["gnb_in", terminal]:
                raise ValueError("within-component event order")
            if by_stage["nas_in"]["cm"] != 1 or by_stage["nas_forward"]["cm"] != 1 or by_stage["nas_forward"]["ps"] != 1:
                raise ValueError("forward branch state mismatch")
            if terminal == "gnb_missing" and seq in replies:
                raise ValueError("missing-resource packet has reply")
            fate = ("reply_observed" if seq in replies else "gnb_missing_resource_observed"
                    if terminal == "gnb_missing" else "after_gnb_resource_unlocalized")
        packets.append({"sequence": seq, "fate": fate, "reply_observed": seq in replies})
    return {"trace_accounting_complete": True, "packets": packets, "received": len(replies), "sent": 5,
            "all_packets_returned": len(replies) == 5, "network_fix_validated": False}
