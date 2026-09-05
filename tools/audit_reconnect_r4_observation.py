"""Independent stopped-R4, later service and local clock observation audit.

No runtime or capture-tool acceptance functions are imported. This does not
repair timestamps, accept the rejected protocol, or authorize another trial.
"""
import base64
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.audit_reconnect_r4_execution import audit as audit_execution
from tools.audit_reconnect_r3_network import audit_scope, NAMES
from tools.reconnect_r4_window_audit import expected_commands, address_read, ping_read, logs_read, IMAGES, UE, GNB

RUN = ROOT / "evidence/engineering/20260905T170131Z-reconnect-r4-network"
AFTERCARE = ROOT / "evidence/engineering/20260905T170620Z-reconnect-r4-aftercare"
PROBE = ROOT / "evidence/engineering/20260905T170956Z-reconnect-r4-wall-clock"
CONTRACT = json.loads((ROOT / "config/experiments/reconnect-r3-command-contract.json").read_bytes())


def check(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def lines(text):
    return [json.loads(line) for line in text.splitlines()]


def sealed(path):
    manifest = read(path / "manifest.json")["captured_file_sha256"]
    check(set(manifest) == {p.name for p in path.iterdir() if p.is_file() and p.name != "manifest.json"}, "sealed inventory")
    for name, digest in manifest.items():
        check(Path(name).name == name and sha((path / name).read_bytes()) == digest, "sealed hash")


def expected_aftercare():
    snapshots = ["docker", "inspect", "--format", CONTRACT["inspect_format"], *NAMES]
    identities = ["docker", "inspect", "--format", expected_commands(10091)[0][3], UE, GNB]
    network = ["docker", "network", "inspect", "safetwin5g-isolated"]
    address = expected_commands(10091)[2]
    result = [("before-network", network), ("before-containers", snapshots),
              ("before-identities", identities), ("before-address", address)]
    result += [("service-" + str(i), expected_commands(i)[7]) for i in (10091, 10092, 10093)]
    result += [(n, CONTRACT["fixed_commands"][n]) for n in
               ("sample-qdisc", "upf-state", "stress-workers", "targets", "rollback-inspect-eth0")]
    result += [("after-ue-log", expected_commands(10091)[5]), ("after-gnb-log", expected_commands(10091)[6]),
               ("after-address", address), ("after-identities", identities),
               ("after-network", network), ("after-containers", snapshots)]
    return result


def raw_command(row):
    check(row["timed_out"] is False and row["truncated"] is False and row["capture_error"] is None, "incomplete command")
    check(all(row[k] is True for k in ("job_assigned_before_go", "launcher_go_sent", "reader_threads_joined", "process_reaped")), "process ownership/cleanup")
    check(row["returncode"] == 0 and row["stderr"] == "", "command status/stream")
    check(row["timeout_seconds"] == 35 and row["max_output_bytes"] == 1048576 and row["cleanup_grace_seconds"] == 2, "command bounds")
    size = 0
    for stream in ("stdout", "stderr"):
        raw = base64.b64decode(row[stream + "_base64"], validate=True)
        check(sha(raw) == row[stream + "_sha256"] and raw.decode("utf-8", "replace") == row[stream], "raw stream linkage")
        size += len(raw)
    check(size == row["retained_output_bytes"] <= 1048576, "output bound")
    check(0 <= row["monotonic_end_ns"] - row["monotonic_start_ns"] <= 35 * 10**9, "duration bound")
    clock = row["monotonic_clock"]
    check(clock["api"] == "perf_counter_ns" and clock["monotonic"] is True and clock["adjustable"] is False
          and 0 < clock["resolution"] <= 1e-6, "QPC properties")
    # Intentionally no wall/QPC consistency acceptance or historical re-timing.


def audit_aftercare(path=AFTERCARE, original=RUN):
    sealed(path)
    design, capture = read(path / "design.json"), read(path / "capture.json")
    check(design["purpose"] == "later-read-only-official-service-observation-not-R4-retry"
          and design["evidence_label"] == "sandbox-measured" and design["radio_evidence_label"] == "simulated"
          and design["mutations_authorized"] is False and design["original_R4_verdict_unchanged"] is True
          and design["R4_clock_consistency_acceptance_claimed"] is False, "aftercare claim boundary")
    check(design["original_run"] == RUN.relative_to(ROOT).as_posix()
          and design["original_manifest_sha256"] == sha((original / "manifest.json").read_bytes()), "original linkage")
    check(design["source_sha256"] == sha((ROOT / "tools/capture_reconnect_r4_aftercare.py").read_bytes()), "capture source hash")
    rows = lines((path / "commands.jsonl").read_text())
    expected = expected_aftercare()
    check(len(rows) == len(expected) == 18 and design["commands"] == [list(p) for p in expected], "exact command design")
    check(lines((path / "intents.jsonl").read_text()) == [dict(sequence=i, name=n, argv=a) for i, (n, a) in enumerate(expected, 1)], "intent inventory")
    for index, (row, (name, argv)) in enumerate(zip(rows, expected), 1):
        check(row["sequence"] == index and row["name"] == name and row["argv"] == argv, "command inventory")
        raw_command(row)
        if index > 1:
            check(row["monotonic_start_ns"] >= rows[index - 2]["monotonic_end_ns"], "command order")
    check(capture == dict(capture_complete=True, errors=[], command_records=18, mutations_executed=0, original_R4_verdict_unchanged=True), "capture status")
    check(lines((path / "identifiers.jsonl").read_text()) == [dict(identifier=i, sequence=n) for n, i in enumerate((10091, 10092, 10093), 5)], "unique reserved identifiers")
    by = {r["name"]: r for r in rows}
    reference = read(ROOT / "config/experiments/reconnect-r3-scope-reference.json")["containers"]
    scopes = []
    for prefix in ("before", "after"):
        networks = json.loads(by[prefix + "-network"]["stdout"])
        check(len(networks) == 1, "one network")
        scopes.append(audit_scope(networks[0], lines(by[prefix + "-containers"]["stdout"]), reference, "official", IMAGES))
    for name in NAMES:
        check(all(scopes[0][name][k] == scopes[1][name][k] for k in ("Id", "Image", "RestartCount", "State")), "stable service scope")
    identities = lines(by["before-identities"]["stdout"])
    check(identities == lines(by["after-identities"]["stdout"]) and len(identities) == 2, "stable radio identities")
    reset = read(original / "final-rollback.json")["reset"]
    reset_after = {r["Name"]: r for r in lines(reset["after"])}
    for identity, name in zip(identities, (UE, GNB)):
        check(identity == reset_after["/" + name] and identity["Id"] == scopes[0][name]["Id"]
              and identity["Image"] == IMAGES["official_image_id"] and identity["Running"] is True
              and identity["LogConfig"] == {"Type": "json-file", "Config": {}}, "official reset identity linkage")
    source = address_read(by["before-address"]["stdout"], "official-service")
    check(source == address_read(by["after-address"]["stdout"], "official-service"), "stable PDU source")
    pings = [ping_read(by["service-" + str(i)]["stdout"], source) for i in (10091, 10092, 10093)]
    check(all(p["packets_received"] == 5 for p in pings), "later service not 15/15")
    for name, kind in (("sample-qdisc", "fq_codel"), ("rollback-inspect-eth0", "noqueue")):
        qdisc = json.loads(by[name]["stdout"])
        check(len(qdisc) == 1 and qdisc[0]["kind"] == kind and qdisc[0]["root"] is True, "neutral qdisc")
    state = by["upf-state"]["stdout"].split()
    check(len(state) == 1 and not any(c in state[0] for c in "TXZ") and not by["stress-workers"]["stdout"], "UPF/workers")
    targets = json.loads(by["targets"]["stdout"])
    active = targets["data"]["activeTargets"]
    check(targets["status"] == "success" and len(active) == 3 and {t["labels"]["job"] for t in active} ==
          {"open5gs-amf", "open5gs-smf", "open5gs-upf"} and all(t["health"] == "up" and not t["lastError"] for t in active), "target health")
    ue_log, gnb_log = logs_read(by["after-ue-log"]["stdout"]), logs_read(by["after-gnb-log"]["stdout"])
    prefix, post = logs_read(reset["prefix"]), logs_read(reset["post"])
    check(post[:len(prefix)] == prefix and ue_log[:len(post)] == post, "reset and later log prefix continuity")
    fresh = post[len(prefix):]
    markers = ["Initial Registration is successful", "PDU Session establishment is successful PSI[1]",
               "TUN interface[uesimtun0, " + source + "] is up."]
    positions = [[i for i, line in enumerate(fresh) if marker in line] for marker in markers]
    check(all(len(p) == 1 for p in positions) and positions[0][0] < positions[1][0] < positions[2][0], "fresh registration/PDU order")
    check(all("ST3" not in line for line in ue_log + gnb_log), "official logs cannot claim trace instrumentation")
    return dict(observation_audit_passed=True, commands_replayed=18, scopes_replayed=2, packets_received=15,
                packets_transmitted=15, source_ip=source, identities=identities, fresh_PDU_log_markers=[fresh[p[0]] for p in positions],
                original_R4_verdict_unchanged=True, R4_clock_consistency_accepted=False,
                protocol_execution_valid=False, network_fix_validated=False, TNSM_ready=False,
                evidence_label="sandbox-measured", radio_evidence_label="simulated")


def interval_disagreement(a, b, value, lo, hi):
    """Distance from wall delta to the QPC read brackets, never a midpoint."""
    delta = b[value] - a[value]
    lower, upper = b[lo] - a[hi], b[hi] - a[lo]
    return max(lower - delta, delta - upper, 0)


def audit_probe(path=PROBE):
    sealed(path)
    probe = read(path / "probe.json")
    check(probe["source_sha256"] == sha((ROOT / "tools/probe_reconnect_r4_wall_clock.py").read_bytes()), "probe source hash")
    check(probe["purpose"] == "later-local-clock-observation-not-historical-timestamp-repair"
          and probe["historical_R4_verdict_unchanged"] is True and probe["network_commands_executed"] == 0
          and probe["clock_changes_executed"] == 0, "probe boundary")
    rows = probe["rows"]
    check(len(rows) == 1000, "probe cardinality")
    for index, row in enumerate(rows):
        check(row["index"] == index and all(type(v) is int for v in row.values()), "probe integer identity")
        check(row["qpc_before_ns"] <= row["qpc_between_ns"] <= row["qpc_after_ns"], "probe bracket order")
        check(row["precise_unix_ns"] == (row["precise_filetime_ticks"] - 116444736000000000) * 100, "FILETIME epoch conversion")
        if index:
            check(rows[index - 1]["qpc_after_ns"] <= row["qpc_before_ns"], "probe sequence order")
    errors = {}
    for label, value, lo, hi in (("python_wall", "python_wall_ns", "qpc_before_ns", "qpc_between_ns"),
                                ("precise_UTC", "precise_unix_ns", "qpc_between_ns", "qpc_after_ns")):
        residuals = [interval_disagreement(a, b, value, lo, hi) for a, b in zip(rows, rows[1:])]
        errors[label] = dict(pairs=len(residuals), beyond_1ms=sum(v > 1000000 for v in residuals), max_disagreement_ns=max(residuals))
    return dict(observation_audit_passed=True, samples=1000, clock_info=probe["python_wall_clock"], comparisons=errors,
                historical_R4_clock_step_proven=False, historical_timestamps_repaired=False,
                observed_resolution_does_not_prove_historical_cause=True, network_fix_validated=False)


def audit():
    original = audit_execution(RUN)
    check(original["observation_audit_passed"] is True and original["protocol_execution_valid"] is False
          and original["official_image_restored"] is False and original["final_service_restored"] is False
          and original["samples_replayed"] == 0 and original["valid_completed_assignments"] == 0, "original rejection preserved")
    rows = lines((RUN / "commands.jsonl").read_text())
    flags = []
    for i, row in enumerate(rows):
        if row["capture_error"]:
            previous = rows[i - 1]
            gap = row["monotonic_start_ns"] - previous["monotonic_end_ns"]
            flags.append(dict(sequence=row["sequence"], name=row["name"], capture_error=row["capture_error"],
                              inter_command_residual_ns=row["wall_start_ns"] - previous["wall_end_ns"] - gap))
    return dict(observation_audit_passed=True, original=original, actual_docker_commands=sum(r["argv"][0] == "docker" for r in rows),
                original_clock_flags=flags, later_service=audit_aftercare(), later_clock_probe=audit_probe(),
                protocol_execution_valid=False, network_fix_validated=False, TNSM_ready=False)


if __name__ == "__main__":
    print(json.dumps(audit(), indent=2))
