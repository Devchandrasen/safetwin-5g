"""Independent whole-protocol cursor replay, including stopped/failed rollback.

No execution runner or runtime acceptance predicate is imported. A rejected
protocol may have a valid evidence record; the two decisions stay separate.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from tools.reconnect_r4_window_audit import replay as replay_window, expected_commands, logs_read, IMAGES, UE, GNB
from tools.audit_reconnect_r3_network import audit_scope

ROOT = Path(__file__).resolve().parents[1]
CORE = "safetwin5g-open5gs"
NAMES = [CORE, GNB, UE, "safetwin5g-mongodb", "safetwin5g-prometheus"]
CONFIG = json.loads((ROOT / "config/experiments/reconnect-r4-execution.json").read_bytes())
CONTRACT = json.loads((ROOT / "config/experiments/reconnect-r3-command-contract.json").read_bytes())
FIXED = CONTRACT["fixed_commands"]
REFERENCE = json.loads((ROOT / "config/experiments/reconnect-r3-scope-reference.json").read_bytes())["containers"]
MINIMAL = expected_commands(10001)[0][3]
IDENTITIES = ["docker", "inspect", "--format", MINIMAL, CORE, GNB, UE]


def require(value, message):
    if not value:
        raise ValueError(message)


def utc_ns(value):
    delta = datetime.fromisoformat(value) - datetime(1970, 1, 1, tzinfo=timezone.utc)
    return ((delta.days * 86400 + delta.seconds) * 10**9 + delta.microseconds * 1000)


class Rejected(Exception):
    """A faithfully recorded command or scientific admission gate failed."""


def audit_host(host, admission, fixture):
    require(host["fixture"] is fixture, "host guard evidence tier")
    pid = host["owner_pid"]
    require(type(pid) is int and pid > 0, "owned host process")
    script = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python(?:w)?(?:[.]exe)?$' "
              + f"-and $_.ProcessId -ne {pid} "
              + "-and $_.CommandLine -match 'run_(?:phase7|recovery_pilot|reconnect(?:_r[234])?)[.]py' } | Select-Object -ExpandProperty ProcessId")
    row, sleep = host["idle_command"], host["sleep"]
    audit_clock(row, fixture)
    require(row["argv"] == ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script]
            and row["sequence"] == 0 and row["timeout_seconds"] == 35 and row["max_output_bytes"] == 1048576, "idle snapshot command")
    total = 0
    for stream in ("stdout", "stderr"):
        raw = base64.b64decode(row[stream + "_base64"], validate=True)
        require(hashlib.sha256(raw).hexdigest() == row[stream + "_sha256"] and raw.decode("utf-8", "replace") == row[stream], "idle raw byte linkage")
        total += len(raw)
    elapsed = row["monotonic_end_ns"] - row["monotonic_start_ns"]
    require(total == row["retained_output_bytes"] <= 1048576 and 0 <= elapsed <= 37.1e9
            and row["cleanup_grace_seconds"] == 2, "idle capture bounds")
    idle_ok = (not row["timed_out"] and not row["truncated"] and row["capture_error"] is None
               and row["job_assigned_before_go"] and row["launcher_go_sent"] and row["reader_threads_joined"] and row["process_reaped"]
               and row["returncode"] == 0 and not row["stdout"].strip() and not row["stderr"]
               and elapsed <= 35 * 10**9 and abs(row["wall_end_ns"] - row["wall_start_ns"] - elapsed) <= 1000000)
    require(sleep["mechanism"] == "SetThreadExecutionState" and sleep["requested_flags"] == 0x80000001
            and sleep["enabled"] is bool(idle_ok and sleep.get("previous_state", 0) != 0), "sleep enable outcome")
    admitted = idle_ok and sleep["enabled"]
    require(host["admitted"] is admitted and bool(host["errors"]) is (not admitted or not sleep["cleared"]), "host verdict")
    require(host["started_monotonic_ns"] <= row["monotonic_start_ns"] <= row["monotonic_end_ns"]
            <= host["admission_completed_monotonic_ns"] <= host["completed_monotonic_ns"], "host guard order")
    if admitted:
        expected = {k: v for k, v in host.items() if k != "completed_monotonic_ns"}
        expected["sleep"] = dict(sleep, cleared=False)
        expected["errors"] = []
        require(admission == expected, "durable host admission before network")
    else:
        require(admission is None, "host rejection cannot grant admission")
    return admitted, bool(host["errors"])


def audit_clock(row, fixture):
    state = row["monotonic_clock"]
    require(state["api"] == ("virtual-fixture" if fixture else "perf_counter_ns") and state["monotonic"] is True
            and state["adjustable"] is False and 0 < state["resolution"] <= 1e-6, "monotonic counter implementation")


def command_ok(row):
    return (not row["timed_out"] and not row["truncated"] and row["capture_error"] is None
            and row["job_assigned_before_go"] and row["launcher_go_sent"] and row["reader_threads_joined"] and row["process_reaped"]
            and row["returncode"] in row["accepted_returncodes"])


def clean_samples(samples, states):
    if len(samples) != 3 or not all(states[s["identifier"]]["clean"] for s in samples):
        return False
    ids = [s["identifier"] for s in samples]
    if ids != list(range(ids[0], ids[0] + 3)):
        return False
    contexts = [[s["result"]["source_ip"], json.loads(s["commands"][0]["stdout"]), json.loads(s["commands"][1]["stdout"])] for s in samples]
    return all(c == contexts[0] for c in contexts)


class Cursor:
    def __init__(self, rows, operations, samples, fixture):
        self.rows, self.operations, self.samples, self.fixture = rows, operations, samples, fixture
        self.index, self.uid = 0, "preflight"
        self.sample_index = 0
        self.states, self.seen_operations = {}, []

    def take(self, name, argv, *, success=True):
        require(self.index < len(self.rows), "missing command: " + name)
        row = self.rows[self.index]
        require(row["name"] == name and row["argv"] == argv and row["unit_id"] == self.uid, "command cursor mismatch: " + name)
        self.index += 1
        if success and not command_ok(row):
            raise Rejected(name + " failed")
        return row

    def operation(self, kind, start, label, actual_ok):
        selected = [r for r in self.operations if r["kind"] == kind and r["unit_id"] == self.uid and r["first"] == start]
        require(len(selected) == 1, "operation linkage")
        op = selected[0]
        require(op["last"] == self.index and op["label"] == label and op["ok"] is actual_ok, "operation verdict differs from raw commands")
        self.seen_operations.append(op)
        return op

    def scope(self, role, label):
        start, ok = self.index + 1, False
        try:
            network = self.take(label + "-network", ["docker", "network", "inspect", "safetwin5g-isolated"])
            containers = self.take(label + "-containers", ["docker", "inspect", "--format", CONTRACT["inspect_format"], *NAMES])
            try:
                audit_scope(json.loads(network["stdout"])[0], [json.loads(line) for line in containers["stdout"].splitlines()], REFERENCE, role, IMAGES)
                ok = True
            except (ValueError, KeyError, TypeError) as exc:
                raise Rejected("scope: " + str(exc)) from exc
        finally:
            op = self.operation("scope", start, label, ok)
            require(op["role"] == role, "scope image role")

    def neutral(self, name):
        row = self.take(name, ["docker", "exec", UE, "tc", "-j", "qdisc", "show", "dev", "eth0"])
        data = json.loads(row["stdout"])
        if len(data) != 1 or data[0].get("kind") != "noqueue" or data[0].get("root") is not True:
            raise Rejected("non-neutral qdisc")

    def cleanup(self):
        row = self.take("rollback-inspect-eth0", FIXED["rollback-inspect-eth0"])
        data = json.loads(row["stdout"])
        if len(data) == 1 and data[0].get("kind") == "noqueue" and data[0].get("root") is True:
            return
        if len(data) != 1 or data[0].get("kind") != "netem" or data[0].get("handle") != "7157:":
            raise Rejected("unknown qdisc")
        self.take("emergency-clear-owned-qdisc", FIXED["emergency-clear-owned-qdisc"])
        self.neutral("rollback-verify-eth0")

    def health(self, container):
        first = None
        while True:
            row = self.take("health-" + container, ["docker", "inspect", "--format", "{{.State.Health.Status}}", container])
            first = row["monotonic_start_ns"] if first is None else first
            require(row["monotonic_end_ns"] - first <= 50 * 10**9 + 2 * 10**9, "health wait beyond bound")
            require(row["timeout_seconds"] <= min(35, 50 - (row["monotonic_start_ns"] - first) / 1e9) + 0.01, "health poll reset budget")
            if row["stdout"].strip() == "healthy":
                return
            if self.index == len(self.rows) or self.rows[self.index]["name"] != "health-" + container:
                raise Rejected("health never became healthy")

    def switch(self, role):
        row = self.take("switch-" + role + "-image", FIXED["switch-" + role + "-image"])
        if row["stdout"].strip() != IMAGES[role + "_image_id"]:
            raise Rejected("replacement tag drift")
        self.take("switch-" + role, FIXED["switch-" + role])
        self.health(GNB)
        self.health(UE)
        self.scope(role, "switch-" + role + "-verified")

    def logs(self, name, component):
        row = self.take(name, ["docker", "logs", "--timestamps", "--tail", "2000", component])
        if row["stderr"]:
            raise Rejected("unsupported log stream")
        try:
            logs_read(row["stdout"])
        except ValueError as exc:
            raise Rejected(str(exc)) from exc
        return row["stdout"]

    def reset(self, label, containers):
        start = self.index + 1
        valid, before, after, prefix, post, resets = True, None, None, None, None, []
        try:
            before = self.take(label + "-before-identities", IDENTITIES)["stdout"]
            prefix = self.logs(label + "-before-log", UE)
        except Rejected:
            valid = False
        for container in containers:
            resets.append(self.index + 1)
            try:
                self.take("restart-" + container, ["docker", "restart", container])
                self.health(container)
            except Rejected:
                valid = False
        try:
            after = self.take(label + "-after-identities", IDENTITIES)["stdout"]
            post = self.logs(label + "-after-log", UE)
            old, new = [json.loads(line) for line in before.splitlines()], [json.loads(line) for line in after.splitlines()]
            if len(old) != 3 or len(new) != 3 or [r["Name"] for r in old] != ["/" + c for c in (CORE, GNB, UE)]:
                valid = False
            for a, b in zip(old, new):
                if any(a[k] != b[k] for k in ("Name", "Id", "Image")) or (a["Name"].lstrip("/") in containers and a["StartedAt"] == b["StartedAt"]):
                    valid = False
            a, b = logs_read(prefix), logs_read(post)
            messages = "\n".join(b[len(a):])
            if b[:len(a)] != a or messages.count("Initial Registration is successful") != 1 or messages.count("PDU Session establishment is successful") != 1:
                valid = False
        except (Rejected, ValueError, AttributeError, TypeError, KeyError):
            valid = False
        op = self.operation("reset", start, label, valid)
        require(op["containers"] == containers and op["reset_sequences"] == resets
                and op["before"] == before and op["after"] == after and op["prefix"] == prefix and op["post"] == post
                and bool(op["errors"]) is (not valid), "reset raw artifact linkage")
        return op

    def window(self, label, mode):
        selected = []
        for index in range(3):
            require(self.sample_index < len(self.samples), "missing durable sample")
            sample = self.samples[self.sample_index]
            self.sample_index += 1
            require(sample["unit_id"] == self.uid and sample["window"] == label and sample["index"] == index and sample["mode"] == mode
                    and sample["command_first"] == self.index + 1, "sample cursor linkage")
            plan = expected_commands(sample["identifier"])
            for i, local in enumerate(sample["commands"]):
                require(i < 15, "extra collection command")
                raw = self.take("collection-" + str(i + 1), plan[i], success=False)
                expected = dict(raw, sequence=i + 1, global_sequence=raw["sequence"])
                require(local == expected, "sample differs from global raw command")
            raw_result, collection_ok, metrics_ok = None, False, False
            try:
                raw_result = replay_window(sample, allow_fixture=self.fixture)
                collection_ok = all(command_ok(r) for r in sample["commands"])
            except (ValueError, KeyError, TypeError):
                pass
            require(sample["capture_deadline_ns"] - sample["capture_started_ns"] == 120 * 10**9, "collection admission bound")
            if sample["commands"]:
                require(sample["capture_started_ns"] <= sample["commands"][0]["monotonic_start_ns"], "collection start linkage")
                require(all(r["monotonic_start_ns"] + 35 * 10**9 <= sample["capture_deadline_ns"] for r in sample["commands"]), "command after collection admission ended")
            abort = sample["admission_abort"]
            if abort:
                require(len(sample["commands"]) < 15 and abort["next_local_command"] == len(sample["commands"]) + 1
                        and abort["reason"] in ("collection-budget", "experiment-budget"), "collection admission abort")
                checked = abort["checked_monotonic_ns"]
                prior_end = sample["commands"][-1]["monotonic_end_ns"] if sample["commands"] else sample["capture_started_ns"]
                require(checked >= prior_end, "abort precedes its command prefix")
                if abort["reason"] == "collection-budget":
                    require(checked + 35 * 10**9 > sample["capture_deadline_ns"], "invented collection budget failure")
                else:
                    require(checked >= self.admission_end_ns and self.uid != "final-rollback" and not label.startswith("restore-"), "invented experiment budget failure")
            if not abort and len(sample["commands"]) < 15 and all(command_ok(r) for r in sample["commands"]):
                # The only ordinary pre-ping stop is a genuinely rejected precheck.
                require(len(sample["commands"]) == 7, "unexplained partial collection prefix")
                from tools.reconnect_r4_window_audit import address_read
                rejected = False
                try:
                    address_read(sample["commands"][2]["stdout"], mode)
                    identities = [json.loads(sample["commands"][j]["stdout"]) for j in (0, 1)]
                    for state, component in zip(identities, (UE, GNB)):
                        if state["Image"] != IMAGES["derived_image_id" if mode == "trace" else "official_image_id"] or state["Name"] != "/" + component or state["Running"] is not True or state["LogConfig"] != {"Type": "json-file", "Config": {}}:
                            rejected = True
                    if identities[0]["Id"] == identities[1]["Id"]:
                        rejected = True
                    if any(not re.fullmatch(r"\d+\.\d{9}\n", sample["commands"][j]["stdout"]) for j in (3, 4)):
                        rejected = True
                    for j, component in ((5, "ue"), (6, "gnb")):
                        text = sample["commands"][j]["stdout"]
                        logs_read(text)
                        if mode == "official-service" and "ST3" in text:
                            rejected = True
                        if f"id={sample['identifier']} " in text:
                            rejected = True
                except (ValueError, TypeError, KeyError):
                    rejected = True
                require(rejected, "invented precheck rejection")
            telemetry = []
            if collection_ok:
                try:
                    for name in ("sample-qdisc", "upf-state", "stress-workers", "targets"):
                        telemetry.append(self.take(name, FIXED[name])["stdout"])
                    qdisc, status, workers, targets = telemetry
                    q = json.loads(qdisc)
                    tasks = json.loads(targets)["data"]["activeTargets"]
                    jobs = [t["labels"]["job"] for t in tasks]
                    metrics = {"configured_packet_loss_pct": 0 if len(q) == 1 and q[0].get("kind") == "fq_codel" and q[0].get("root") is True else None,
                               "upf_process_running": int(len(status.split()) == 1 and not any(c in status for c in "TXZ")),
                               "stress_workers_count": len(workers.splitlines()),
                               "prometheus_targets_up_count": sum(t["health"] == "up" for t in tasks) if len(jobs) == 3 and set(jobs) == {"open5gs-amf", "open5gs-smf", "open5gs-upf"} else -1}
                    require(metrics == sample["telemetry"], "telemetry report differs from raw values")
                    metrics_ok = metrics == {"configured_packet_loss_pct": 0, "upf_process_running": 1, "stress_workers_count": 0, "prometheus_targets_up_count": 3}
                except Rejected:
                    metrics_ok = False
            require(sample["command_last"] == self.index, "sample command range")
            require(sample["result"] == raw_result, "reported raw-window result mismatch")
            require(bool(sample["errors"]) == (not collection_ok or not metrics_ok), "sample validity differs from independent replay")
            self.states[sample["identifier"]] = {"valid": collection_ok and metrics_ok,
                                                 "clean": collection_ok and metrics_ok and raw_result["packet_delivery_complete"]}
            selected.append(sample)
            if sample["errors"]:
                break
        return selected

    def restoration(self):
        attempts = []
        for label, containers in (("restore-ue", [UE]), ("restore-full", [CORE, GNB, UE])):
            reset = self.reset(label, containers)
            samples = self.window(label, "trace") if reset["ok"] else []
            clean = reset["ok"] and clean_samples(samples, self.states)
            attempts.append({"step": label, "reset": reset, "samples": samples, "clean": clean})
            if clean:
                break
        return attempts


def audit(run, allow_fixture=False, allow_unfrozen_fixture=False):
    run = Path(run)
    read = lambda name: json.loads((run / name).read_bytes())
    lines = lambda name: [json.loads(line) for line in (run / name).read_text().splitlines()] if (run / name).exists() else []
    manifest = read("manifest.json")["captured_file_sha256"]
    require(set(manifest) == {p.name for p in run.iterdir() if p.is_file() and p.name != "manifest.json"}, "artifact inventory")
    for name, digest in manifest.items():
        require(Path(name).name == name and hashlib.sha256((run / name).read_bytes()).hexdigest() == digest, "artifact hash")
    design, approval, summary = read("design.json"), read("approval.json"), read("summary.json")
    fixture = design["execution_mode"] == "fixture"
    require(design["execution_mode"] in ("fixture", "sandbox") and (not fixture or allow_fixture), "fixture cannot become measured evidence")
    require(design["transport"] == ("in-memory-no-io" if fixture else "bounded-windows-job") and design["config"] == CONFIG and design["images"] == IMAGES, "execution design")
    if not (fixture and allow_unfrozen_fixture):
        from tools.verify_reconnect_r4_execution import SOURCES
        lock_path = ROOT / "config/experiments/reconnect-r4-execution-lock.json"
        require(design["execution_lock"] == json.loads(lock_path.read_bytes()) and design["execution_lock_sha256"] == hashlib.sha256(lock_path.read_bytes()).hexdigest(), "frozen execution linkage")
        require(design["execution_lock"]["lock_id"] == CONFIG["experiment_id"] and set(design["execution_lock"]["source_sha256"]) == set(SOURCES), "exact execution source inventory")
        require(design["execution_lock"]["immutable_collection_lock_sha256"] == hashlib.sha256((ROOT / "config/experiments/reconnect-r4-collection-lock.json").read_bytes()).hexdigest(), "immutable collection linkage")
        for name, digest in design["execution_lock"]["source_sha256"].items():
            require((ROOT / name).resolve().is_relative_to(ROOT) and hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, "frozen source hash")
    require(approval["experiment_id"] == CONFIG["experiment_id"] and approval["execution_lock_sha256"] == design["execution_lock_sha256"]
            and approval["status"] == "approved" and approval["environment"] == "sandbox" and approval["type"] == "standing-project-authorization"
            and approval["approved_by"] == "user" and approval["trials"] == CONFIG["trials"] and approval["containers"] == [CORE, GNB, UE]
            and approval["image_containers"] == [GNB, UE] and approval["image_ids"] == [IMAGES["official_image_id"], IMAGES["derived_image_id"]]
            and approval["rollback_plan"] == "owned qdisc cleanup; both official images; independent core,gNB,UE resets; fresh PDU and 15/15 plus scope and telemetry"
            and approval["operator_validation"] is False and approval["live_actuation"] is False, "approval scope")
    rows, intents, samples, operations = lines("commands.jsonl"), lines("command-intents.jsonl"), lines("samples.jsonl"), lines("operations.jsonl")
    require([r["sequence"] for r in rows] == list(range(1, len(rows) + 1)), "global sequence")
    require(intents == [{k: r[k] for k in ("sequence", "unit_id", "name", "argv")} for r in rows], "unresolved intent or command provenance")
    host = read("host-guard.json")
    admitted, host_failed = audit_host(host, read("host-admission.json") if (run / "host-admission.json").exists() else None, fixture)
    require(utc_ns(approval["recorded_at"]) <= host["idle_command"]["wall_start_ns"], "approval must precede commands")
    if rows:
        require(admitted and host["admission_completed_monotonic_ns"] <= rows[0]["monotonic_start_ns"]
                and host["completed_monotonic_ns"] >= rows[-1]["monotonic_end_ns"], "network commands outside host guard")
    previous = None
    for row in rows:
        audit_clock(row, fixture)
        expected = [0, 2] if row["argv"] == FIXED["ping-help"] else [0, 1] if row["argv"][:4] == ["docker", "exec", UE, "ping"] else [0]
        require(row["accepted_returncodes"] == expected and 0 < row["timeout_seconds"] <= 35 and row["max_output_bytes"] == 1048576, "command acceptance/bounds")
        total = 0
        for stream in ("stdout", "stderr"):
            raw = base64.b64decode(row[stream + "_base64"], validate=True)
            require(hashlib.sha256(raw).hexdigest() == row[stream + "_sha256"] and raw.decode("utf-8", "replace") == row[stream], "raw byte/hash/text linkage")
            total += len(raw)
        require(total == row["retained_output_bytes"] <= 1048576, "bounded retained bytes")
        elapsed = row["monotonic_end_ns"] - row["monotonic_start_ns"]
        require(0 <= elapsed <= (row["timeout_seconds"] + 2.1) * 1e9 and row["cleanup_grace_seconds"] == 2, "bounded command and cleanup")
        require(previous is None or row["monotonic_start_ns"] >= previous["monotonic_end_ns"], "global monotonic order")
        clock_bad = abs(row["wall_end_ns"] - row["wall_start_ns"] - elapsed) > 1000000
        if previous:
            clock_bad = clock_bad or abs(row["wall_start_ns"] - previous["wall_end_ns"] - (row["monotonic_start_ns"] - previous["monotonic_end_ns"])) > 1000000
        if clock_bad or elapsed > row["timeout_seconds"] * 1e9:
            require(not command_ok(row), "invalid clock/duration accepted as successful command")
        previous = row
    ids = lines("identifiers.jsonl")
    require([r["identifier"] for r in ids] == list(range(10001, 10001 + len(ids))) and len(ids) <= 99, "durable ID reservation sequence")
    require(ids == [{k: s[k] for k in ("identifier", "unit_id", "window", "index", "command_first")} for s in samples], "reservation-to-sample linkage")
    cursor = Cursor(rows, operations, samples, fixture)
    cursor.admission_end_ns = summary["admission_started_monotonic_ns"] + 1500 * 10**9
    errors, attempted, valid_trials, switched, rollback_valid = False, 0, 0, False, False
    reported_trials = [read(p.name) for p in sorted(run.glob("trial-*.json"))]
    try:
        if not admitted:
            raise Rejected("host admission rejected")
        for name in ("repository-head", "docker-version", "compose-base", "compose-derived", "official-image", "derived-image"):
            row = cursor.take(name, FIXED[name])
            if name.endswith("-image") and row["stdout"].strip() != IMAGES[name.removesuffix("-image") + "_image_id"]:
                raise Rejected("preflight image")
        base, derived = (json.loads(rows[i]["stdout"]) for i in (2, 3))
        for service in ("ueransim-gnb", "ueransim-ue"):
            require(derived["services"][service]["image"] == IMAGES["derived_tag"], "derived override")
            derived["services"][service]["image"] = base["services"][service]["image"]
        require(base == derived, "override changed configuration")
        cursor.scope("official", "preflight")
        cursor.neutral("preflight-eth0")
        help_row = cursor.take("ping-help", FIXED["ping-help"])
        if "-e <identifier>" not in help_row["stdout"] + help_row["stderr"]:
            raise Rejected("identifier CLI unsupported")
        for component in (UE, GNB):
            row = cursor.take("preflight-collection-" + component, ["docker", "inspect", "--format", MINIMAL, component])
            state = json.loads(row["stdout"])
            if state["Image"] != IMAGES["official_image_id"] or state["LogConfig"] != {"Type": "json-file", "Config": {}} or state["Running"] is not True:
                raise Rejected("R4 collection preflight")
        # Switch attempt flag is set only after the immutable image check passes.
        start = cursor.index
        try:
            cursor.switch("derived")
        finally:
            switched = any(r["name"] == "switch-derived" for r in rows[start:cursor.index])
        for i, trial in enumerate(CONFIG["trials"]):
            require(i < len(reported_trials), "missing assigned trial")
            report = reported_trials[i]
            attempted += 1
            cursor.uid = trial["trial_id"]
            bad, prepared, recovered, post_valid = False, False, False, False
            exposure_seq, baseline, post, restoration = None, [], [], []
            try:
                cursor.scope("derived", "trial-scope")
                cursor.neutral("preparation-eth0")
                prepared = True
                reset = cursor.reset("preparation", [CORE, GNB, UE])
                require(report["reset"] == reset, "preparation reset linkage")
                if not reset["ok"]:
                    raise Rejected("fresh baseline failed")
                baseline = cursor.window("baseline", "trace")
                if not clean_samples(baseline, cursor.states):
                    raise Rejected("baseline invalid")
                cursor.neutral("baseline-eth0")
                prefix = {c: cursor.logs("exposure-before-" + c, c) for c in (UE, GNB)}
                name = "bounded-link-drop" if trial["drop_ue_egress"] else "control-wait"
                exposure_seq = cursor.index + 1
                exposure = cursor.take(name, FIXED[name])
                if trial["drop_ue_egress"]:
                    data = exposure["stdout"].splitlines()
                    require(len(data) == 4 and 8 <= (datetime.fromisoformat(data[2]) - datetime.fromisoformat(data[0])).total_seconds() < 15, "fault interval")
                    during, after = json.loads(data[1]), json.loads(data[3])
                    require(len(during) == 1 and during[0]["kind"] == "netem" and during[0]["handle"] == "7157:" and during[0]["root"] is True
                            and during[0]["options"]["loss-random"]["loss"] == 1 and len(after) == 1 and after[0]["kind"] == "noqueue", "fault/trap observation")
                else:
                    require(8 <= (exposure["monotonic_end_ns"] - exposure["monotonic_start_ns"]) / 1e9 < 35, "control exposure duration")
                cursor.neutral("post-exposure-eth0")
                require(report["settle_completed_ns"] - report["settle_started_ns"] >= 5 * 10**9 and report["settle_started_ns"] >= rows[cursor.index - 1]["monotonic_end_ns"], "settling delay")
                post = cursor.window("post", "trace")
                require(post[0]["commands"][0]["monotonic_start_ns"] >= report["settle_completed_ns"], "settling before post")
                suffix = {c: cursor.logs("exposure-after-" + c, c) for c in (UE, GNB)}
                messages = {}
                for c in (UE, GNB):
                    a, b = logs_read(prefix[c]), logs_read(suffix[c])
                    require(b[:len(a)] == a, "exposure prefix continuity")
                    messages[c] = "\n".join(b[len(a):])
                require(report["context"] == {"before": prefix, "after": suffix, "service_accept_observed": "Service Accept received" in messages[UE],
                                               "initial_context_observed": "Initial Context Setup Request received" in messages[GNB]}, "context marker report")
                recovered = clean_samples(post, cursor.states)
                require(report["recovery_15_of_15"] is recovered, "15/15 outcome rounding")
                post_valid = len(post) == 3 and all(cursor.states[s["identifier"]]["valid"] for s in post)
                if not post_valid or (not trial["drop_ue_egress"] and (not recovered or "Radio link failure detected" in messages[UE])):
                    raise Rejected("post/control failed")
            except Rejected:
                bad = True
            try:
                cursor.cleanup()
            except Rejected:
                bad = True
            if prepared and (trial["drop_ue_egress"] or bad):
                restoration = cursor.restoration()
                restored = restoration[-1]["clean"]
            else:
                restored = recovered
            accepted = not bad and restored
            require(report["trial"] == trial and report["baseline"] == baseline and report["post"] == post
                    and report["exposure_command"] == exposure_seq and report["restoration_attempts"] == restoration
                    and bool(report["errors"]) is bad and report["final_service_restored"] is restored
                    and report["protocol_execution_valid"] is accepted and report["network_fix_validated"] is False, "trial state-machine verdict")
            valid_trials += accepted
            if not accepted:
                break
    except Rejected:
        errors = True
    require(len(reported_trials) == attempted, "extra or omitted assignments")
    rollback = read("final-rollback.json")
    official, restored = False, False
    if switched:
        cursor.uid = "final-rollback"
        failed = False
        for action in (cursor.cleanup, lambda: cursor.switch("official")):
            try:
                action()
            except Rejected:
                failed = True
        reset = cursor.reset("final-official", [CORE, GNB, UE])
        failed = failed or not reset["ok"]
        final_samples = cursor.window("final-official", "official-service") if reset["ok"] else []
        try:
            cursor.scope("official", "final-official")
            official = True
            cursor.neutral("final-eth0")
        except Rejected:
            failed = True
        restored = not failed and reset["ok"] and clean_samples(final_samples, cursor.states)
        require(rollback["reset"] == reset and rollback["samples"] == final_samples and bool(rollback["errors"]) is failed
                and rollback["official_image_restored"] is official and rollback["service_restored"] is restored
                and rollback["network_fix_validated"] is False, "official rollback verdict")
    else:
        require(rollback is None, "rollback without switch attempt")
    require(cursor.index == len(rows) and cursor.sample_index == len(samples) and len(cursor.seen_operations) == len(operations), "unconsumed command/sample/operation")
    require(summary["admission_started_monotonic_ns"] <= host["started_monotonic_ns"]
            and summary["completed_monotonic_ns"] >= host["completed_monotonic_ns"]
            and summary["admission_budget_exceeded"] is (summary["completed_monotonic_ns"] - summary["admission_started_monotonic_ns"] > 1500 * 10**9), "admission budget replay")
    errors = errors or host_failed
    accepted = attempted == 4 and valid_trials == 4 and not errors and official and restored and not summary["admission_budget_exceeded"]
    require(summary["experiment_id"] == CONFIG["experiment_id"] and summary["attempted_assignments"] == attempted and summary["valid_completed_assignments"] == valid_trials
            and bool(summary["errors"]) is errors and summary["candidate_switch_attempted"] is switched
            and summary["protocol_execution_valid"] is accepted and summary["official_image_restored"] is official and summary["final_service_restored"] is restored, "terminal verdict")
    require(summary["evidence_label"] == ("fixture" if fixture else "sandbox-measured") and summary["radio_evidence_label"] == "simulated"
            and summary["actual_docker_commands_executed"] == (0 if fixture else len(rows)), "terminal evidence tier")
    for field in ("network_fix_validated", "TNSM_ready", "confirmatory_data", "live_actuation", "hardware_measured", "operator_validated"):
        require(summary[field] is False, "claim promotion: " + field)
    return {"observation_audit_passed": True, "protocol_execution_valid": accepted, "commands_replayed": len(rows),
            "samples_replayed": len(samples), "attempted_assignments": attempted, "valid_completed_assignments": valid_trials,
            "official_image_restored": official, "final_service_restored": restored, "evidence_label": summary["evidence_label"],
            "network_fix_validated": False, "TNSM_ready": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    parser.add_argument("--allow-fixture", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(audit(args.run, args.allow_fixture), indent=2))
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        print(json.dumps({"observation_audit_passed": False, "error": str(exc), "network_fix_validated": False}))
        raise SystemExit(2)
