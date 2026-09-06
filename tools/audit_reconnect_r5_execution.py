"""Independent whole R5 replay over ONE unchanged journal and command stream.

No execution-runner, clock, host, collection or budget candidate acceptance
code is imported. Component adapters consume global references, never sliced
or renumbered sub-journals. Rejection is different from a valid negative run.
"""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import re

from tools.audit_reconnect_r5_clock import need
from tools.audit_reconnect_r5_journal import audit as audit_journal
from tools.audit_reconnect_r5_process import audit as audit_process
from tools.reconnect_r5_global_host_audit import audit as audit_host, idle_command
from tools.reconnect_r5_global_collection_audit import audit as audit_collection, read_identity
from tools.reconnect_r5_global_budget_audit import audit as audit_budget
from tools.reconnect_r4_window_audit import expected_commands, logs_read
from tools.audit_reconnect_r3_network import audit_scope, CORE, GNB, UE, NAMES, BASE, DERIVED, UP

ROOT = Path(__file__).resolve().parents[1]
ID = "safetwin5g-reconnect-r5-execution-v1"
COMMANDS = json.loads((ROOT/"config/experiments/reconnect-r3-command-contract.json").read_bytes())["fixed_commands"]
IMAGES = json.loads((ROOT/"config/experiments/reconnect-r3-images.json").read_bytes())
REFERENCE = json.loads((ROOT/"config/experiments/reconnect-r3-scope-reference.json").read_bytes())["containers"]
from tools.reconnect_r4_window_audit import INSPECT
MINIMAL = ["docker", "inspect", "--format", INSPECT, CORE, GNB, UE]
FULL = ["docker", "inspect", "--format", json.loads((ROOT/"config/experiments/reconnect-r3-command-contract.json").read_bytes())["inspect_format"], *NAMES]
NETWORK = ["docker", "network", "inspect", "safetwin5g-isolated"]
TRIALS = [dict(trial_id="r5:"+n, drop_ue_egress=n.startswith("drop")) for n in ("control-before", "drop-a", "drop-b", "control-after")]
NEUTRAL = dict(configured_packet_loss_pct=0, upf_process_running=1, stress_workers_count=0, prometheus_targets_up_count=3)
RECEIPT = "evidence/private/reconnect-r5-runtime.lock"


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def strict_json(raw):
    # Aggregate evidence repeats bounded raw command records in the component
    # snapshots. This is NOT an increase of the 1 MiB per-process byte limit.
    need(type(raw) in (str, bytes) and len(raw) <= 128*1024*1024, "whole-run JSON byte cap")
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "duplicate JSON key")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite JSON")))


def jsonl(raw):
    need(type(raw) is bytes and raw.endswith(b"\n"), "incomplete JSONL")
    return [strict_json(line) for line in raw.splitlines()]


def normalized(value):
    if type(value) is dict:
        result = {}
        for k, v in value.items():
            if k == "errors":
                need(type(v) is list and all(type(e) is str and e for e in v), "typed errors")
                result[k] = bool(v)
            else:
                result[k] = normalized(v)
        return result
    if type(value) is list:
        return [normalized(v) for v in value]
    return value


def same(a, b, message):
    need(canonical(a) == canonical(b), message)


class Stop(Exception):
    """A raw, faithfully recorded protocol rejection, NOT an audit mismatch."""


def require(value):
    if not value:
        raise Stop("raw predicate rejected")


def parse(fn, *args):
    try:
        return fn(*args)
    except (ValueError, TypeError, KeyError, IndexError, AttributeError) as exc:
        raise Stop(str(exc)) from exc


def attempt(errors, fn):
    try:
        return fn()
    except Stop:
        errors.append("raw rejection")
        return None


def neutral_qdisc(value):
    return type(value) is list and len(value) == 1 and value[0].get("kind") == "noqueue" and value[0].get("root") is True


def image_command(role, container):
    return (BASE if role == "official" else DERIVED)+UP[:-2]+["ueransim-gnb" if container == GNB else "ueransim-ue"]


def allowlists(pid):
    normal = [v for k, v in COMMANDS.items() if k not in ("switch-derived", "switch-official")]
    normal += [MINIMAL, FULL, NETWORK, idle_command(pid)]
    for c in (CORE, GNB, UE):
        normal += [["docker", "restart", c], ["docker", "inspect", "--format", "{{.State.Health.Status}}", c]]
    for role in ("official", "derived"):
        normal += [image_command(role, c) for c in (GNB, UE)]
    for identifier in range(10001, 10100):
        normal += expected_commands(identifier)
    excluded = [COMMANDS[k] for k in ("bounded-link-drop", "control-wait", "compose-derived", "derived-image")]
    excluded += [image_command("derived", c) for c in (GNB, UE)]
    return normal, [a for a in normal if a not in excluded and a[0] not in ("git", "powershell.exe")]


def approval_valid(r):
    expected = dict(experiment_id=ID, repository_head=r["revision"], execution_lock_sha256=r["execution_lock_sha256"],
                    status="approved", environment="sandbox", type="standing-project-authorization", approved_by="user",
                    trials=TRIALS, containers=[CORE, GNB, UE], image_containers=[GNB, UE],
                    image_ids=[IMAGES["official_image_id"], IMAGES["derived_image_id"]],
                    rollback_plan="owned qdisc; independent official gNB and UE images; core,gNB,UE reset and health; fresh PDU; all 15 packets; telemetry; scope; owned host cleanup",
                    operator_validation=False, live_actuation=False)
    a = r["approval"]
    if type(a) is not dict or set(a) != set(expected)|{"recorded_at"}:
        return False
    try:
        instant = datetime.fromisoformat(a["recorded_at"])
        delta = instant-datetime(1970, 1, 1, tzinfo=timezone.utc)
        ns = (delta.days*86400+delta.seconds)*10**9+delta.microseconds*1000
        return canonical({k: a[k] for k in expected}) == canonical(expected) and ns <= r["journal"]["points"][0]["utc_ns"]
    except (ValueError, TypeError):
        return False


class Replay:
    def __init__(self, result, journal):
        self.r, self.j = result, journal
        self.steps, self.rows, self.events = result["steps"], result["commands"], result["execution_events"]
        self.si = self.ri = self.li = self.ai = self.wi = self.bi = 0
        self.ev, self.cleanup, self.unit, self.role = 3, False, "preflight", "official"
        self.candidate = False
        self.approval_hash = digest(result["approval"])

    def admission(self, a, label, points, seconds, ev):
        values = self.r["budget"]["admissions"]
        need(self.ai < len(values), "missing global admission")
        same(a, values[self.ai], "global admission order/linkage")
        same([a["label"], a["points_needed"], a["seconds_needed"], a["event"]], [label, points, seconds, ev], "reservation request drift")
        self.ai += 1

    def leaf(self, kind, label):
        need(self.si < len(self.steps), "missing whole-protocol step: "+label)
        s = self.steps[self.si]
        self.si += 1
        need(set(s) == set("kind label unit cleanup event_before command_before result error event_after command_after".split()), "step schema")
        same([s[k] for k in ("kind", "label", "unit", "cleanup", "event_before", "command_before")],
             [kind, label, self.unit, self.cleanup, self.ev, self.ri], "whole-protocol step order: "+label)
        need(s["error"] is None or type(s["error"]) is str and s["error"], "step error type")
        chunk = []
        while self.li < len(self.events) and self.events[self.li]["kind"] != "step":
            chunk.append(self.events[self.li]); self.li += 1
        need(self.li < len(self.events), "missing durable step")
        same(self.events[self.li], dict(kind="step", step=s, event=self.li+1), "raw step linkage")
        self.li += 1
        if kind == "reserve":
            need(not chunk, "reserve cannot issue a process")
        if kind == "settle":
            op = self.r["budget"]["operations"][self.bi]
            self.admission(op["checks"][0], label, 1, 5, self.ev)
        before = self.ri
        consumed, terminals, blocked = [], [], []
        index = 0
        while index < len(chunk):
            e = chunk[index]
            need(e["kind"] in ("command-intent", "command-blocked"), "orphaned execution event")
            required = set("kind unit label sequence argv cleanup clock_event point approval_sha256 admission event".split())
            need(set(e) == required | ({"error"} if e["kind"] == "command-blocked" else set()), "intent schema")
            same([e["unit"], e["label"], e["cleanup"], e["sequence"]], [self.unit, label, self.cleanup, self.ri+1], "command context/global order")
            need(type(e["clock_event"]) is int and self.ev <= e["clock_event"] <= s["event_after"], "intent event position")
            need(e["point"] == sum(v["kind"] == "point" for v in self.r["journal"]["events"][:e["clock_event"]]), "intent point reference")
            authority = e["approval_sha256"] == self.approval_hash
            if e["admission"] is not None:
                need(not self.cleanup and authority, "admission despite changed authority")
                seconds = (self.rows[self.ri]["timeout_ms"]+999)//1000 if e["kind"] == "command-intent" else e["admission"]["seconds_needed"]
                need(1 <= seconds <= 35, "blocked timeout bound")
                self.admission(e["admission"], "command", 1, seconds, e["clock_event"])
            if e["kind"] == "command-blocked":
                need(not self.cleanup and (not authority or e["admission"] is not None and not e["admission"]["admitted"]), "unexplained blocked dispatch")
                need(type(e["error"]) is str and e["error"], "blocked reason")
                blocked.append(e)
                index += 1
                continue
            need(self.cleanup or authority and e["admission"] is not None and e["admission"]["admitted"], "dispatch without normal authority/admission")
            row = self.rows[self.ri]
            same([e["argv"], e["cleanup"], e["clock_event"], e["point"]], [row["argv"], row["cleanup"], row["journal_event_before"], row["start_point"]], "intent/process linkage")
            if e["admission"] is not None and row["checked_ticks"] is not None:
                need(row["checked_ticks"] >= e["admission"]["ticks"], "process precedes global admission")
            need(index+1 < len(chunk), "missing durable command result")
            same(chunk[index+1], dict(kind="command-result", sequence=self.ri+1, record_sha256=digest(row), event=chunk[index+1]["event"]), "raw command hash")
            consumed.append(row); terminals.append(row["journal_event_after"])
            self.ri += 1; index += 2
        if kind in ("health", "settle"):
            op = self.r["budget"]["operations"][self.bi]; self.bi += 1
            same(op["commands"], consumed, "global budget command coverage")
            same([op["kind"], op["label"], op["cleanup"], op["start_event"]], [kind, label.removeprefix("health-") if kind == "health" else label, self.cleanup, self.ev], "budget leaf scope")
            terminals.append(op["terminal_after"])
            same(s["result"], op, "timing result copy")
            need(s["error"] is None, "unexpected timing throw")
        elif kind == "collection":
            w = self.r["windows"][self.wi]; self.wi += 1
            same(w["commands"], consumed, "global collection command coverage")
            same([w["label"], w["mode"], w["cleanup"], w["start_event"]], [label, "trace" if self.role == "derived" else "official-service", self.cleanup, self.ev], "collection leaf scope")
            terminals.append(w["closure_event_after"])
            same(s["result"], w, "collection result copy")
            need(s["error"] is None, "unexpected collection throw")
        elif kind in ("host-start", "host-close"):
            host = self.r["host"]
            selected = [o for o in host["operations"] if o["cleanup"] is (kind == "host-close")]
            terminals += [o["event_after"] for o in selected]
            same(consumed, [host["idle_command"]] if kind == "host-start" and host["idle_command"] is not None else [], "host global command coverage")
            same(s["result"], host["admitted"] if kind == "host-start" else None, "host result copy")
            need(s["error"] is None, "host leaf throw")
        need(sorted(terminals) == list(range(self.ev+1, s["event_after"]+1)), "orphaned or missing global clock event")
        same(s["command_after"], self.ri, "step command terminal")
        self.ev = s["event_after"]
        return s, consumed, blocked

    def reserve(self, label, points, seconds):
        if self.cleanup:
            return
        s, rows, blocked = self.leaf("reserve", label)
        a = self.r["budget"]["admissions"][self.ai]
        self.admission(a, label, points, seconds, self.ev)
        same(s["result"], a if a["admitted"] else None, "reserve return")
        need(bool(s["error"]) == (not a["admitted"]), "reserve rejection claim")
        require(a["admitted"])

    def cmd(self, label, argv, *, cleanup_tag=False):
        need(not cleanup_tag or self.cleanup and argv == COMMANDS["official-image"], "cleanup tag scope")
        s, rows, blocked = self.leaf("cleanup-tag" if cleanup_tag else "command", label)
        need(len(rows)+len(blocked) == 1, "single command invocation")
        same((rows or blocked)[0]["argv"], argv, "exact protocol argv: "+label)
        if rows:
            row = rows[0]
            same([row["timeout_ms"], row["max_output_bytes"]], [35000, 1048576], "runner command bounds")
            good = row["complete"] and row["stdout_utf8"] and row["stderr_utf8"] and type(row["returncode"]) is int and row["returncode"] in ((0, 2) if argv == COMMANDS["ping-help"] else (0,)) and (not row["stderr"] or argv == COMMANDS["ping-help"])
            if cleanup_tag:
                good = (all(row[k] is True for k in ("launcher_go_sent", "job_assigned_before_go", "job_closed", "process_reaped", "reader_threads_joined", "stdout_utf8", "stderr_utf8"))
                        and row["timed_out"] is False and row["truncated"] is False and not row["process_errors"]
                        and all(e.startswith("clock journal: ") for e in row["cleanup_errors"])
                        and type(row["returncode"]) is int and row["returncode"] == 0 and not row["stderr"])
            value = row["stdout"]+(row["stderr"] if argv == COMMANDS["ping-help"] else "") if good else None
        else:
            good, value = False, None
        same(s["result"], value, "command return")
        need(bool(s["error"]) == (not good), "command failure claim")
        require(good)
        return value

    def health(self, target):
        s, _, _ = self.leaf("health", "health-"+target)
        require(s["result"]["accepted"])
        return s["result"]

    def eth0(self, label):
        return parse(json.loads, self.cmd(label, COMMANDS["preflight-eth0"]))

    def logs(self, target, label):
        text = self.cmd(label, ["docker", "logs", "--timestamps", "--tail", "2000", target])
        parse(logs_read, text)
        return text

    def scope(self, role, label):
        self.reserve(label, 2, 70)
        errors = []
        network = attempt(errors, lambda: self.cmd(label+"-network", NETWORK))
        containers = attempt(errors, lambda: self.cmd(label+"-containers", FULL))
        require(not errors)
        networks = parse(json.loads, network)
        require(len(networks) == 1)
        rows = parse(lambda: [json.loads(line) for line in containers.splitlines()])
        parse(audit_scope, networks[0], rows, REFERENCE, role, IMAGES)
        for row in rows:
            if row["Name"] in ("/"+GNB, "/"+UE) and role == "derived":
                require(row["Config"]["Labels"].get("safetwin5g.derived.revision") == "reconnect-r3-trace")
        return rows

    def clear_owned(self):
        self.reserve("owned-qdisc", 3, 105)
        value = self.eth0("rollback-inspect-eth0")
        if neutral_qdisc(value):
            return
        require(len(value) == 1 and value[0].get("kind") == "netem" and value[0].get("handle") == "7157:")
        self.cmd("emergency-clear-owned-qdisc", COMMANDS["emergency-clear-owned-qdisc"])
        require(neutral_qdisc(self.eth0("rollback-verify-eth0")))

    def preflight(self):
        require(self.cmd("repository-head", COMMANDS["repository-head"]).strip() == self.r["revision"])
        parse(json.loads, self.cmd("docker-version", COMMANDS["docker-version"]))
        original = parse(json.loads, self.cmd("compose-base", COMMANDS["compose-base"]))
        modified = parse(json.loads, self.cmd("compose-derived", COMMANDS["compose-derived"]))
        def config():
            for service in ("ueransim-gnb", "ueransim-ue"):
                require(modified["services"][service]["image"] == IMAGES["derived_tag"])
                modified["services"][service]["image"] = original["services"][service]["image"]
            require(original == modified)
        parse(config)
        for role in ("official", "derived"):
            require(self.cmd(role+"-image", COMMANDS[role+"-image"]).strip() == IMAGES[role+"_image_id"])
        self.scope("official", "preflight")
        require(neutral_qdisc(self.eth0("preflight-eth0")))
        require("-e <identifier>" in self.cmd("ping-help", COMMANDS["ping-help"]))
        for c in (UE, GNB):
            parse(read_identity, self.cmd("preflight-minimal-"+c, ["docker", "inspect", "--format", INSPECT, c]), c, "official-service")

    def switch(self, role):
        self.reserve("switch-"+role, 58, 310)
        errors = []
        for c in (GNB, UE):
            def apply():
                require(self.cmd("switch-"+role+"-tag-"+c, COMMANDS[role+"-image"], cleanup_tag=self.cleanup).strip() == IMAGES[role+"_image_id"])
                if role == "derived":
                    self.candidate = True
                self.cmd("switch-"+role+"-apply-"+c, image_command(role, c))
            attempt(errors, apply)
            attempt(errors, lambda: self.health(c))
        attempt(errors, lambda: self.scope(role, "switch-"+role+"-verified"))
        require(not errors)
        self.role = role

    def reset(self, label, targets):
        self.reserve(label, 4+27*len(targets), 140+85*len(targets))
        errors = []
        before = attempt(errors, lambda: self.cmd(label+"-before-identities", MINIMAL))
        oldlog = attempt(errors, lambda: self.logs(UE, label+"-before-log"))
        for c in targets:
            attempt(errors, lambda: self.cmd("restart-"+c, ["docker", "restart", c]))
            attempt(errors, lambda: self.health(c))
        after = attempt(errors, lambda: self.cmd(label+"-after-identities", MINIMAL))
        newlog = attempt(errors, lambda: self.logs(UE, label+"-after-log"))
        def fresh():
            a, b = [[json.loads(line) for line in text.splitlines()] for text in (before, after)]
            require(len(a) == len(b) == 3 and [v["Name"] for v in a] == ["/"+c for c in (CORE, GNB, UE)])
            for x, y in zip(a, b):
                require(all(x[k] == y[k] for k in ("Name", "Id", "Image")))
                require(x["Running"] is True and y["Running"] is True and x["LogConfig"] == y["LogConfig"] == {"Type": "json-file", "Config": {}})
                require(x["Name"][1:] not in targets or datetime.fromisoformat(y["StartedAt"]) > datetime.fromisoformat(x["StartedAt"]))
            pre, post = logs_read(oldlog), logs_read(newlog)
            require(post[:len(pre)] == pre)
            suffix = "\n".join(post[len(pre):])
            require(suffix.count("Initial Registration is successful") == 1 and suffix.count("PDU Session establishment is successful") == 1)
        attempt(errors, lambda: parse(fresh))
        return dict(label=label, targets=targets, ok=not errors, errors=errors)

    def telemetry(self):
        errors, raw = [], []
        for key in ("sample-qdisc", "upf-state", "stress-workers", "targets"):
            raw.append(attempt(errors, lambda: self.cmd(key, COMMANDS[key])))
        def metrics():
            qdisc, state = json.loads(raw[0]), raw[1].split()
            targets = json.loads(raw[3])["data"]["activeTargets"]
            jobs = [t["labels"]["job"] for t in targets]
            return dict(configured_packet_loss_pct=0 if len(qdisc) == 1 and qdisc[0]["kind"] == "fq_codel" and qdisc[0].get("root") is True else None,
                        upf_process_running=int(len(state) == 1 and not any(x in state[0] for x in "TXZ")),
                        stress_workers_count=len(raw[2].splitlines()), prometheus_targets_up_count=sum(t["health"] == "up" for t in targets)
                        if len(jobs) == 3 and set(jobs) == {"open5gs-amf", "open5gs-smf", "open5gs-upf"} else -1)
        value = attempt(errors, lambda: parse(metrics))
        return dict(raw=raw, value=value, ok=not errors and value == NEUTRAL, errors=errors)

    def window(self, label):
        self.reserve(label, 60, 780)
        samples = []
        for i in range(3):
            step, _, _ = self.leaf("collection", label+":"+str(i))
            w = step["result"]
            telemetry = self.telemetry()
            samples.append(dict(window=w, telemetry=telemetry))
            if not self.cleanup and (not w["collection_valid"] or not telemetry["ok"]):
                break
        return samples

    def trial(self, design):
        self.unit = design["trial_id"]
        row = dict(trial=design, errors=[], baseline=[], post=[], restoration=[], prepared=False, exposure=False, recovery_15_of_15=False)
        try:
            self.scope("derived", "trial-scope")
            require(neutral_qdisc(self.eth0("preparation-eth0")))
            row["prepared"] = True
            row["reset"] = self.reset("preparation", [CORE, GNB, UE])
            require(row["reset"]["ok"])
            row["baseline"] = self.window("baseline")
            require(clean(row["baseline"]))
            require(neutral_qdisc(self.eth0("baseline-eth0")))
            before = {c: self.logs(c, "exposure-before-"+c) for c in (UE, GNB)}
            name = "bounded-link-drop" if design["drop_ue_egress"] else "control-wait"
            row["exposure"] = True
            raw = self.cmd(name, COMMANDS[name])
            process = self.rows[self.ri-1]
            require(process["completion_observed_ticks"]-process["go_before_ticks"] >= 8*self.r["journal"]["descriptor"]["frequency_hz"])
            if design["drop_ue_egress"]:
                def fault():
                    lines = raw.splitlines()
                    require(len(lines) == 4)
                    a, b = datetime.fromisoformat(lines[0]), datetime.fromisoformat(lines[2])
                    require(a.tzinfo is not None and b.tzinfo is not None and 8 <= (b-a).total_seconds() < 15)
                    q = json.loads(lines[1])
                    require(len(q) == 1 and q[0]["kind"] == "netem" and q[0]["handle"] == "7157:" and q[0]["root"] is True
                            and q[0]["options"]["loss-random"]["loss"] == 1 and neutral_qdisc(json.loads(lines[3])))
                parse(fault)
            require(neutral_qdisc(self.eth0("post-exposure-eth0")))
            step, _, _ = self.leaf("settle", "post-exposure")
            require(step["result"]["accepted"])
            row["post"] = self.window("post")
            after = {c: self.logs(c, "exposure-after-"+c) for c in (UE, GNB)}
            messages = {}
            for c in (UE, GNB):
                pre, post = parse(logs_read, before[c]), parse(logs_read, after[c])
                require(post[:len(pre)] == pre)
                messages[c] = "\n".join(post[len(pre):])
            row["context"] = dict(before=before, after=after, service_accept_observed="Service Accept received" in messages[UE], initial_context_observed="Initial Context Setup Request received" in messages[GNB])
            row["recovery_15_of_15"] = clean(row["post"])
            require(len(row["post"]) == 3 and all(s["window"]["collection_valid"] and s["telemetry"]["ok"] for s in row["post"]))
            require(design["drop_ue_egress"] or row["recovery_15_of_15"] and "Radio link failure detected" not in messages[UE])
        except Stop:
            row["errors"].append("raw rejection")
        finally:
            attempt(row["errors"], self.clear_owned)
            if row["prepared"] and (design["drop_ue_egress"] or row["errors"]):
                for label, targets in (("restore-ue", [UE]), ("restore-full", [CORE, GNB, UE])):
                    errors = []
                    reset = attempt(errors, lambda: self.reset(label, targets))
                    samples = attempt(errors, lambda: self.window(label)) if reset and reset["ok"] else []
                    item = dict(step=label, reset=reset, samples=samples or [], errors=errors, clean=bool(reset and reset["ok"] and samples and clean(samples)))
                    row["restoration"].append(item)
                    if item["clean"]:
                        break
        row["final_service_restored"] = row["restoration"][-1]["clean"] if row["restoration"] else row["recovery_15_of_15"]
        row["protocol_execution_valid"] = not row["errors"] and row["final_service_restored"]
        return row

    def rollback(self):
        self.cleanup, self.unit = True, "final-rollback"
        start = sum(e["kind"] == "point" for e in self.r["journal"]["events"][:self.ev])
        errors = []
        attempt(errors, self.clear_owned)
        attempt(errors, lambda: self.switch("official"))
        self.role = "official"
        reset = attempt(errors, lambda: self.reset("final-official", [CORE, GNB, UE]))
        samples = attempt(errors, lambda: self.window("final-official"))
        scope = attempt(errors, lambda: self.scope("official", "final-official"))
        eth0 = attempt(errors, lambda: self.eth0("final-eth0"))
        telemetry = attempt(errors, self.telemetry)
        end = sum(e["kind"] == "point" for e in self.r["journal"]["events"][:self.ev])
        return dict(errors=errors, reset=reset, samples=samples, scope=scope, eth0=eth0, telemetry=telemetry,
                    point_start=start, point_end=end, official_images=scope is not None,
                    service_restored=bool(not errors and reset and reset["ok"] and samples and clean(samples) and scope and eth0 is not None and neutral_qdisc(eth0) and telemetry and telemetry["ok"]))


def clean(samples):
    if len(samples) != 3 or any(not s["window"]["collection_valid"] or not s["window"]["result"]["packet_delivery_complete"] or not s["telemetry"]["ok"] for s in samples):
        return False
    windows = [s["window"] for s in samples]
    contexts = [[w["result"]["source_ip"], *[json.loads(w["commands"][i]["stdout"]) for i in (0, 1)]] for w in windows]
    return [w["identifier"] for w in windows] == list(range(windows[0]["identifier"], windows[0]["identifier"]+3)) and contexts[0] == contexts[1] == contexts[2]


def audit(bundle, raw_journal, raw_ledger, raw_execution):
    r = bundle["result"]
    need(bundle["fixture_scope"] == "invented-whole-protocol-no-process-no-network-no-power" and r["evidence_label"] == "fixture", "fixture-only integration boundary")
    need(r["experiment_id"] == ID and all(type(r[k]) is int and r[k] == 0 for k in ("actual_network_commands_executed", "actual_power_requests_executed")), "execution identity/tier")
    need(all(r[k] is False for k in ("network_execution_authorized", "network_fix_validated", "TNSM_ready")), "unauthorized promotion")
    need(type(r["revision"]) is str and re.fullmatch("[0-9a-f]{40}", r["revision"]) and type(r["execution_lock_sha256"]) is str and re.fullmatch("[0-9a-f]{64}", r["execution_lock_sha256"]), "frozen identifiers")
    need(r["log_failure"] is None, "execution storage failed; no durability claim")
    same([] if raw_execution == b"" else jsonl(raw_execution), r["execution_events"], "execution durable bytes")
    need([e["event"] for e in r["execution_events"]] == list(range(1, len(r["execution_events"])+1)), "execution sequence")
    if raw_ledger is not None:
        jsonl(raw_ledger)
    allowed, cleanup_allowed = allowlists(r["journal"]["descriptor"]["owner_pid"])
    if r["commands"]:
        process = audit_process(r["commands"], r["journal"], raw_journal, allowed, cleanup_allowed)
        journal = process["clock_journal"]
    else:
        journal = audit_journal(r["journal"], raw_journal)
        need(not any(str(e.get("label", "")).startswith("process:") for e in r["journal"]["events"]), "unreported process")
        process = dict(decisions=[], observation_audit_passed=True)
    context = dict(journal=journal, process=process, rows=r["commands"], final_ticks=r["final_ticks"])
    host = audit_host(r["host"], r["journal"], raw_journal, bundle["owned_receipt"].encode() if bundle["owned_receipt"] is not None else None, context) if r["host"] else None
    if r["host"]:
        need(r["host"]["lease"]["header"]["revision_sha256"] == r["execution_lock_sha256"], "receipt execution lock binding")
    collection = audit_collection(r["windows"], r["journal"], raw_journal, r["ledger"], raw_ledger, context)
    budget = audit_budget(r["budget"], r["journal"], raw_journal, context)
    c = Replay(r, journal)
    need([e.get("label") for e in r["journal"]["events"][:3]] == [None, "bootstrap:0", "bootstrap:1"] and r["budget"]["start_point"] == 2, "exact two-point bootstrap")
    expected_prereqs = dict(committed_sources=True, prior_r5_attempt=False, older_guards_absent=True, receipt_path=RECEIPT, ledger_path="identifiers.jsonl", fixture=True)
    admitted = approval_valid(r) and canonical(r["prerequisites"]) == canonical(expected_prereqs)
    # A deliberately wrong fixture receipt path is a negative provider case.
    # It must be recorded explicitly; path is not inferred from case's name.
    admitted = admitted and Path(r["receipt_path_observed"]) == Path(r["output_path"])/"attempt-receipt.jsonl"
    trials, errors, rollback = [], [], None
    try:
        require(admitted)
        step, _, _ = c.leaf("host-start", "host-start")
        require(step["result"])
        c.preflight()
        c.switch("derived")
        for trial in TRIALS:
            value = c.trial(trial); trials.append(value)
            if not value["protocol_execution_valid"]:
                break
    except Stop:
        errors.append("raw rejection")
    if c.candidate:
        rollback = c.rollback()
    c.cleanup = True
    if r["host"]:
        c.leaf("host-close", "host-close")
    same(normalized(trials), normalized(r["trials"]), "raw trial decision differs from summary")
    same(normalized(rollback), normalized(r["rollback"]), "raw official rollback differs from summary")
    need(bool(errors) == bool(r["errors"]) and c.candidate is r["candidate_switch_attempted"], "top-level failure/mutation accounting")
    need(c.si == len(c.steps) and c.ri == len(c.rows) and c.li == len(c.events) and c.wi == len(r["windows"])
         and c.bi == len(r["budget"]["operations"]) and c.ai == len(r["budget"]["admissions"]), "unreplayed step/command/window/admission")
    events, points = r["journal"]["events"], r["journal"]["points"]
    need(r["terminal_event_before"] == c.ev and len(events) == c.ev+1 and events[-1]["label"] == "execution:end" and events[-1]["cleanup"] is True, "exact whole-run terminal")
    tick, f = r["final_ticks"], r["journal"]["descriptor"]["frequency_hz"]
    need(tick is None or type(tick) is int and tick >= 0, "final raw counter")
    timing = bool(tick is not None and not r["budget"]["counter_error"] and not r["journal"]["journal_failure"] and not r["journal"]["capture_source_failed"]
                  and journal["clock"]["clock_capture_valid"] and events[-1]["kind"] == "point" and points[-2]["qpc_after_ticks"] <= tick <= points[-1]["qpc_before_ticks"]
                  and points[-1]["qpc_after_ticks"] < points[1]["qpc_before_ticks"]+1500*f)
    capacity = rollback is None or len(points)-rollback["point_start"] <= 216
    valid = bool(len(trials) == 4 and all(t["protocol_execution_valid"] for t in trials) and not errors and rollback and rollback["service_restored"] and host and host["host_component_complete"] and timing and capacity)
    same([r["execution_timing_valid"], r["cleanup_inventory_fits"], r["protocol_execution_valid"]], [timing, capacity, valid], "whole-protocol acceptance promotion")
    return dict(observation_audit_passed=True, protocol_execution_valid=valid, commands_replayed=len(c.rows), windows_replayed=c.wi,
                clock_points=len(points), trials_replayed=len(trials), exposure_attempts=sum(t["exposure"] for t in trials),
                drop_recovery_15_of_15=[t["recovery_15_of_15"] for t in trials if t["trial"]["drop_ue_egress"]],
                official_rollback_verified=bool(rollback and rollback["service_restored"]), execution_timing_valid=timing,
                cleanup_points=0 if rollback is None else len(points)-rollback["point_start"],
                evidence_label="fixture", actual_processes_executed=0, actual_network_commands_executed=0, actual_power_requests_executed=0,
                network_execution_authorized=False, network_fix_validated=False, TNSM_ready=False)


def audit_path(path):
    path = Path(path)
    ledger = path/"identifiers.jsonl"
    return audit(strict_json((path/"capture.json").read_bytes()), (path/"clock.jsonl").read_bytes(),
                 ledger.read_bytes() if ledger.exists() else None, (path/"execution.jsonl").read_bytes())
