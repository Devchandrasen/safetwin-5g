"""Injectable full R5 protocol. This software stage has NO network CLI.

Frozen clock/host/process/collection/budget components are reused unchanged.
The released harness supplies only synthetic clock, daemon and power objects.
"""
import copy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

from sandbox.reconnect_r5_budget import RunnerBudget
from sandbox.reconnect_r5_collection import Collector, IdentifierLedger
from sandbox.reconnect_r5_host import idle_query
from sandbox.reconnect_r4_collection import command_plan, identity, log_lines, INSPECT, IMAGES
from sandbox.run_reconnect_r3 import BASE, DERIVED, UP, verify_fault
from sandbox.reconnect_r5_scope import validate_scope
from sandbox.reconnect_r3_measurement import CORE, GNB, UE, CONTAINERS, NETWORK, INSPECT_FORMAT, state_metrics
from sandbox.run_reconnect import noqueue

ROOT = Path(__file__).resolve().parents[1]
ID = "safetwin5g-reconnect-r5-execution-v1"
TRIALS = [dict(trial_id="r5:"+n, drop_ue_egress=n.startswith("drop")) for n in ("control-before", "drop-a", "drop-b", "control-after")]
COMMANDS = json.loads((ROOT/"config/experiments/reconnect-r3-command-contract.json").read_bytes())["fixed_commands"]
MINIMAL = ["docker", "inspect", "--format", INSPECT, CORE, GNB, UE]
NEUTRAL = dict(configured_packet_loss_pct=0, upf_process_running=1, stress_workers_count=0, prometheus_targets_up_count=3)
RECEIPT = "evidence/private/reconnect-r5-runtime.lock"


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False, separators=(",", ":"))


def require(value, message):
    if not value:
        raise ValueError(message)


def stamp_ns(value):
    dt = datetime.fromisoformat(value)
    require(dt.tzinfo is not None, "timezone required")
    delta = dt-datetime(1970, 1, 1, tzinfo=timezone.utc)
    return (delta.days*86400+delta.seconds)*10**9+delta.microseconds*1000


def approval_expected(revision, lock_digest):
    return dict(experiment_id=ID, repository_head=revision, execution_lock_sha256=lock_digest,
                status="approved", environment="sandbox", type="standing-project-authorization", approved_by="user",
                trials=TRIALS, containers=[CORE, GNB, UE], image_containers=[GNB, UE],
                image_ids=[IMAGES["official_image_id"], IMAGES["derived_image_id"]],
                rollback_plan="owned qdisc; independent official gNB and UE images; core,gNB,UE reset and health; fresh PDU; all 15 packets; telemetry; scope; owned host cleanup",
                operator_validation=False, live_actuation=False)


def validate_approval(value, revision, lock_digest, before_ns):
    require(type(revision) is str and re.fullmatch("[0-9a-f]{40}", revision)
            and type(lock_digest) is str and re.fullmatch("[0-9a-f]{64}", lock_digest), "revision digest syntax")
    expected = approval_expected(revision, lock_digest)
    require(type(value) is dict and set(value) == set(expected)|{"recorded_at"}, "exact approval keys")
    require(canonical({k: value[k] for k in expected}) == canonical(expected), "exact standing-user approval")
    require(type(value["recorded_at"]) is str and stamp_ns(value["recorded_at"]) <= before_ns, "approval must precede initial observation")


def image_command(role, container):
    require(role in ("official", "derived") and container in (GNB, UE), "exact image target")
    return (BASE if role == "official" else DERIVED)+UP[:-2]+["ueransim-gnb" if container == GNB else "ueransim-ue"]


def allowlists(pid):
    base = [v for k, v in COMMANDS.items() if k not in ("switch-derived", "switch-official")]
    base += [MINIMAL, ["docker", "network", "inspect", NETWORK], ["docker", "inspect", "--format", INSPECT_FORMAT, *CONTAINERS], idle_query(pid)]
    for c in (CORE, GNB, UE):
        base += [["docker", "restart", c], ["docker", "inspect", "--format", "{{.State.Health.Status}}", c]]
    for role in ("official", "derived"):
        base += [image_command(role, c) for c in (GNB, UE)]
    for identifier in range(10001, 10100):
        base += command_plan(identifier)
    allowed = sorted({tuple(a) for a in base})
    excluded = {tuple(COMMANDS[k]) for k in ("bounded-link-drop", "control-wait", "compose-derived", "derived-image")}
    excluded.update(tuple(image_command("derived", c)) for c in (GNB, UE))
    return allowed, [a for a in allowed if a not in excluded and a[0] != "git" and a[0] != "powershell.exe"]


def mutable(argv):
    return argv[:2] == ["docker", "restart"] or argv[:2] == ["docker", "compose"] and "up" in argv or argv in (COMMANDS["bounded-link-drop"], COMMANDS["emergency-clear-owned-qdisc"])


class RunLog:
    def __init__(self, path):
        self.handle = Path(path).open("xb")
        self.events, self.failure = [], None

    def emit(self, value, cleanup=False):
        row = dict(copy.deepcopy(value), event=len(self.events)+1)
        self.events.append(row)
        try:
            self.handle.write((canonical(row)+"\n").encode())
            self.handle.flush()
            os.fsync(self.handle.fileno())
        except BaseException as exc:
            self.failure = self.failure or (type(exc).__name__+": "+str(exc))
            if not cleanup:
                raise

    def close(self):
        self.handle.close()


class GuardedTransport:
    """One global cursor, durable command intents and immutable cleanup scope."""
    def __init__(self, inner, runner):
        self.inner, self.runner = inner, runner
        self.journal, self.clock = inner.journal, inner.clock

    @property
    def next_sequence(self):
        return self.inner.next_sequence

    def run(self, argv, *, sequence, timeout_ms, max_output_bytes, cleanup=False):
        r = self.runner
        admission = None
        context = dict(unit=r.unit, label=r.label, sequence=sequence, argv=argv, cleanup=cleanup,
                       clock_event=len(self.journal.events), point=len(self.journal.prefix.points),
                       approval_sha256=hashlib.sha256(canonical(r.approval).encode()).hexdigest())
        try:
            require(tuple(argv) in (r.cleanup_allowed if cleanup else r.allowed), "global command allowlist")
            if not cleanup:
                require(r.log.failure is None and canonical(r.approval) == r.approved_bytes, "normal authority/storage changed")
                admission = r.budget.admit("command", points_needed=1, seconds_needed=(timeout_ms+999)//1000)
                require(admission["admitted"], "global command admission closed")
            if mutable(argv):
                require(r.authorized and r.approved_bytes is not None, "no mutation before exact approval and scope")
        except BaseException as exc:
            r.log.emit(dict(context, kind="command-blocked", admission=admission, error=type(exc).__name__+": "+str(exc)), cleanup)
            raise
        intent = dict(context, kind="command-intent", admission=admission)
        r.log.emit(intent, cleanup)
        row = self.inner.run(argv, sequence=sequence, timeout_ms=timeout_ms, max_output_bytes=max_output_bytes, cleanup=cleanup)
        r.rows.append(copy.deepcopy(row))
        r.log.emit(dict(kind="command-result", sequence=sequence, record_sha256=hashlib.sha256(canonical(row).encode()).hexdigest()), cleanup)
        return row


class Runner:
    def __init__(self, output, journal, inner, host_factory, wait_ms, approval, revision, lock_digest, prerequisites, *, fixture=True):
        require(fixture is True, "this release is fixture-only; native admission and authority remain disabled")
        self.fixture = fixture
        self.output, self.journal = Path(output), journal
        self.approval, self.revision, self.lock_digest = approval, revision, lock_digest
        self.prerequisites = copy.deepcopy(prerequisites)
        self.approved_bytes = None
        self.log = RunLog(self.output/"execution.jsonl")
        self.rows, self.steps, self.samples = [], [], []
        self.allowed, self.cleanup_allowed = map(set, allowlists(journal.prefix.descriptor["owner_pid"]))
        self.transport = GuardedTransport(inner, self)
        self.budget = RunnerBudget(journal, self.transport, wait_ms)
        self.host = host_factory(self.transport)
        self.ledger, self.collector = None, None
        self.unit, self.label, self.role = "preflight", "host", "official"
        self.authorized, self.candidate_touched, self.host_used, self.cleanup = False, False, False, False
        self.reference = json.loads((ROOT/"config/experiments/reconnect-r3-scope-reference.json").read_bytes())["containers"]
        self.images = IMAGES

    def leaf(self, kind, label, call):
        self.label = label
        step = dict(kind=kind, label=label, unit=self.unit, cleanup=self.cleanup, event_before=len(self.journal.events),
                    command_before=len(self.rows), result=None, error=None)
        self.steps.append(step)
        try:
            step["result"] = call()
            return copy.deepcopy(step["result"])
        except BaseException as exc:
            step["error"] = type(exc).__name__+": "+str(exc)
            raise
        finally:
            step.update(event_after=len(self.journal.events), command_after=len(self.rows))
            self.log.emit(dict(kind="step", step=step), self.cleanup)

    def reserve(self, label, points, seconds):
        if self.cleanup:
            return
        def check():
            value = self.budget.admit(label, points_needed=points, seconds_needed=seconds)
            require(value["admitted"], "whole operation reservation rejected: "+label)
            return value
        self.leaf("reserve", label, check)

    def cmd(self, name, argv):
        def invoke():
            row = self.transport.run(argv, sequence=self.transport.next_sequence, timeout_ms=35000, max_output_bytes=1048576, cleanup=self.cleanup)
            accepted = (0, 2) if argv == COMMANDS["ping-help"] else (0,)
            require(row["complete"] is True and type(row["returncode"]) is int and row["returncode"] in accepted
                    and row["stdout_utf8"] is True and row["stderr_utf8"] is True, "incomplete/failed command: "+name)
            require(not row["stderr"] or argv == COMMANDS["ping-help"], "unsupported stderr: "+name)
            return row["stdout"]+(row["stderr"] if argv == COMMANDS["ping-help"] else "")
        return self.leaf("command", name, invoke)

    def attempt(self, errors, label, call):
        try:
            return call()
        except BaseException as exc:
            errors.append(label+": "+type(exc).__name__+": "+str(exc))
            return None

    def health(self, target):
        row = self.leaf("health", "health-"+target, lambda: self.budget.health(target, cleanup=self.cleanup))
        require(row["accepted"], "health rejected: "+target)
        return row

    def eth0(self, label):
        return json.loads(self.cmd(label, COMMANDS["preflight-eth0"]))

    def logs(self, target, label):
        raw = self.cmd(label, ["docker", "logs", "--timestamps", "--tail", "2000", target])
        log_lines(raw)
        return raw

    def scope(self, role, label):
        self.reserve(label, 2, 70)
        errors = []
        network = self.attempt(errors, "network", lambda: self.cmd(label+"-network", ["docker", "network", "inspect", NETWORK]))
        containers = self.attempt(errors, "containers", lambda: self.cmd(label+"-containers", ["docker", "inspect", "--format", INSPECT_FORMAT, *CONTAINERS]))
        require(not errors, "scope capture failed: "+repr(errors))
        return validate_scope(network, containers, role, self.reference, self.images)

    def clear_owned(self):
        self.reserve("owned-qdisc", 3, 105)
        state = self.eth0("rollback-inspect-eth0")
        if noqueue(state):
            return
        require(len(state) == 1 and state[0].get("kind") == "netem" and state[0].get("handle") == "7157:", "unknown qdisc untouched")
        self.cmd("emergency-clear-owned-qdisc", COMMANDS["emergency-clear-owned-qdisc"])
        require(noqueue(self.eth0("rollback-verify-eth0")), "owned qdisc remains")

    def preflight(self):
        require(self.cmd("repository-head", COMMANDS["repository-head"]).strip() == self.revision, "repository revision changed")
        json.loads(self.cmd("docker-version", COMMANDS["docker-version"]))
        original = json.loads(self.cmd("compose-base", COMMANDS["compose-base"]))
        modified = json.loads(self.cmd("compose-derived", COMMANDS["compose-derived"]))
        for service in ("ueransim-gnb", "ueransim-ue"):
            require(modified["services"][service]["image"] == IMAGES["derived_tag"], "override image")
            modified["services"][service]["image"] = original["services"][service]["image"]
        require(original == modified, "override expands scope")
        for role in ("official", "derived"):
            require(self.cmd(role+"-image", COMMANDS[role+"-image"]).strip() == IMAGES[role+"_image_id"], "immutable tag drift")
        self.scope("official", "preflight")
        require(noqueue(self.eth0("preflight-eth0")), "pre-existing fault")
        require("-e <identifier>" in self.cmd("ping-help", COMMANDS["ping-help"]), "identifier support")
        for c in (UE, GNB):
            identity(self.cmd("preflight-minimal-"+c, ["docker", "inspect", "--format", INSPECT, c]), c, "official-service")

    def switch(self, role):
        self.reserve("switch-"+role, 58, 310)
        errors = []
        for c in (GNB, UE):
            def replace():
                label = "switch-"+role+"-tag-"+c
                if self.cleanup:
                    def inspect_tag():
                        row = self.transport.run(COMMANDS["official-image"], sequence=self.transport.next_sequence,
                                                 timeout_ms=35000, max_output_bytes=1048576, cleanup=True)
                        require(cleanup_tag_usable(row), "official tag metadata unavailable; unsafe replacement blocked")
                        return row["stdout"]
                    tag = self.leaf("cleanup-tag", label, inspect_tag)
                else:
                    tag = self.cmd(label, COMMANDS[role+"-image"])
                require(tag.strip() == IMAGES[role+"_image_id"], "replacement tag drift")
                if role == "derived":
                    self.candidate_touched = True
                self.cmd("switch-"+role+"-apply-"+c, image_command(role, c))
            self.attempt(errors, "image-"+c, replace)
            self.attempt(errors, "health-"+c, lambda: self.health(c))
        self.attempt(errors, "post-image-scope", lambda: self.scope(role, "switch-"+role+"-verified"))
        require(not errors, "image switch failed: "+repr(errors))
        self.role = role

    def reset(self, label, targets):
        self.reserve(label, 4+len(targets)*27, 140+len(targets)*85)
        errors, old, new = [], {}, {}
        old["ids"] = self.attempt(errors, "before-ids", lambda: self.cmd(label+"-before-identities", MINIMAL))
        old["logs"] = self.attempt(errors, "before-logs", lambda: self.logs(UE, label+"-before-log"))
        for c in targets:
            self.attempt(errors, "restart-"+c, lambda: self.cmd("restart-"+c, ["docker", "restart", c]))
            self.attempt(errors, "health-"+c, lambda: self.health(c))
        new["ids"] = self.attempt(errors, "after-ids", lambda: self.cmd(label+"-after-identities", MINIMAL))
        new["logs"] = self.attempt(errors, "after-logs", lambda: self.logs(UE, label+"-after-log"))
        def validate():
            a, b = [[json.loads(line) for line in v["ids"].splitlines()] for v in (old, new)]
            require(len(a) == len(b) == 3 and [v["Name"] for v in a] == ["/"+c for c in (CORE, GNB, UE)], "reset identity inventory")
            for x, y in zip(a, b):
                require(all(x[k] == y[k] for k in ("Name", "Id", "Image")), "reset identity/image changed")
                require(x["Running"] is True and y["Running"] is True and x["LogConfig"] == y["LogConfig"] == {"Type": "json-file", "Config": {}}, "running reset/log context")
                require(x["Name"][1:] not in targets or stamp_ns(y["StartedAt"]) > stamp_ns(x["StartedAt"]), "missing fresh increasing start")
            pre, post = log_lines(old["logs"]), log_lines(new["logs"])
            require(post[:len(pre)] == pre, "lost reset prefix")
            suffix = "\n".join(post[len(pre):])
            require(suffix.count("Initial Registration is successful") == 1 and suffix.count("PDU Session establishment is successful") == 1, "unique fresh registration/PDU required")
        self.attempt(errors, "fresh-context", validate)
        return dict(label=label, targets=targets, ok=not errors, errors=errors)

    def telemetry(self):
        errors, raw = [], []
        for key in ("sample-qdisc", "upf-state", "stress-workers", "targets"):
            raw.append(self.attempt(errors, key, lambda: self.cmd(key, COMMANDS[key])))
        value = self.attempt(errors, "parse-telemetry", lambda: state_metrics(*raw))
        return dict(raw=raw, value=value, ok=not errors and value == NEUTRAL, errors=errors)

    def window(self, label):
        self.reserve(label, 60, 780)
        samples = []
        for i in range(3):
            w = self.leaf("collection", label+":"+str(i), lambda: self.collector.collect(label+":"+str(i), "trace" if self.role == "derived" else "official-service", cleanup=self.cleanup))
            # Always attempt all four telemetry commands, even after collection failure.
            t = self.telemetry()
            sample = dict(window=w, telemetry=t)
            self.samples.append(sample)
            samples.append(sample)
            if not self.cleanup and (not w["collection_valid"] or not t["ok"]):
                break
        return samples

    def trial(self, trial):
        self.unit = trial["trial_id"]
        row = dict(trial=trial, errors=[], baseline=[], post=[], restoration=[], prepared=False, exposure=False, recovery_15_of_15=False)
        try:
            self.scope("derived", "trial-scope")
            require(noqueue(self.eth0("preparation-eth0")), "pre-existing fault")
            row["prepared"] = True
            row["reset"] = self.reset("preparation", [CORE, GNB, UE])
            require(row["reset"]["ok"], "reset failed")
            row["baseline"] = self.window("baseline")
            require(clean(row["baseline"]), "invalid baseline blocks exposure")
            require(noqueue(self.eth0("baseline-eth0")), "baseline fault")
            before = {c: self.logs(c, "exposure-before-"+c) for c in (UE, GNB)}
            name = "bounded-link-drop" if trial["drop_ue_egress"] else "control-wait"
            row["exposure"] = True
            raw = self.cmd(name, COMMANDS[name])
            if trial["drop_ue_egress"]:
                verify_fault(raw)
            require(noqueue(self.eth0("post-exposure-eth0")), "exposure trap failed")
            settling = self.leaf("settle", "post-exposure", self.budget.settle)
            require(settling["accepted"], "settling failed")
            row["post"] = self.window("post")
            after = {c: self.logs(c, "exposure-after-"+c) for c in (UE, GNB)}
            messages = {}
            for c in (UE, GNB):
                pre, post = log_lines(before[c]), log_lines(after[c])
                require(post[:len(pre)] == pre, "exposure prefix lost")
                messages[c] = "\n".join(post[len(pre):])
            row["context"] = dict(before=before, after=after, service_accept_observed="Service Accept received" in messages[UE],
                                  initial_context_observed="Initial Context Setup Request received" in messages[GNB])
            row["recovery_15_of_15"] = clean(row["post"])
            require(len(row["post"]) == 3 and all(s["window"]["collection_valid"] and s["telemetry"]["ok"] for s in row["post"]), "incomplete post collection")
            require(trial["drop_ue_egress"] or row["recovery_15_of_15"] and "Radio link failure detected" not in messages[UE], "control failed")
        except BaseException as exc:
            row["errors"].append(type(exc).__name__+": "+str(exc))
        finally:
            self.attempt(row["errors"], "trial-qdisc", self.clear_owned)
            if row["prepared"] and (trial["drop_ue_egress"] or row["errors"]):
                for label, targets in (("restore-ue", [UE]), ("restore-full", [CORE, GNB, UE])):
                    errors = []
                    reset = self.attempt(errors, label, lambda: self.reset(label, targets))
                    samples = self.attempt(errors, label+"-packets", lambda: self.window(label)) if reset and reset["ok"] else []
                    attempt = dict(step=label, reset=reset, samples=samples or [], errors=errors,
                                   clean=bool(reset and reset["ok"] and samples and clean(samples)))
                    row["restoration"].append(attempt)
                    if attempt["clean"]:
                        break
        row["final_service_restored"] = row["restoration"][-1]["clean"] if row["restoration"] else row["recovery_15_of_15"]
        row["protocol_execution_valid"] = not row["errors"] and row["final_service_restored"]
        return row

    def rollback(self):
        self.cleanup, self.unit = True, "final-rollback"
        start, errors = len(self.journal.prefix.points), []
        self.attempt(errors, "qdisc", self.clear_owned)
        self.attempt(errors, "images", lambda: self.switch("official"))
        self.role = "official"  # requested verification mode, not an image-success claim
        reset = self.attempt(errors, "reset", lambda: self.reset("final-official", [CORE, GNB, UE]))
        samples = self.attempt(errors, "packets", lambda: self.window("final-official"))
        scope = self.attempt(errors, "scope", lambda: self.scope("official", "final-official"))
        eth0 = self.attempt(errors, "eth0", lambda: self.eth0("final-eth0"))
        telemetry = self.attempt(errors, "telemetry", self.telemetry)
        return dict(errors=errors, reset=reset, samples=samples, scope=scope, eth0=eth0, telemetry=telemetry,
                    point_start=start, point_end=len(self.journal.prefix.points),
                    official_images=scope is not None, service_restored=bool(not errors and reset and reset["ok"] and samples and clean(samples)
                        and scope and eth0 is not None and noqueue(eth0) and telemetry and telemetry["ok"]))

    def execute(self):
        trials, errors, rollback = [], [], None
        approval_initial = copy.deepcopy(self.approval)
        try:
            validate_approval(self.approval, self.revision, self.lock_digest, self.journal.prefix.points[0]["utc_ns"])
            require(canonical(self.prerequisites) == canonical(dict(committed_sources=True, prior_r5_attempt=False, older_guards_absent=True,
                    receipt_path=RECEIPT, ledger_path="identifiers.jsonl", fixture=self.fixture)), "prior attempt/source/path prerequisites")
            expected_receipt = self.output/"attempt-receipt.jsonl" if self.fixture else ROOT/RECEIPT
            require(self.host.lease.path.resolve() == expected_receipt.resolve(), "exact receipt path binding")
            self.approved_bytes = canonical(self.approval)
            self.host_used = True
            require(self.leaf("host-start", "host-start", self.host.start), "host admission failed")
            self.ledger = IdentifierLedger(self.output/"identifiers.jsonl", self.journal.prefix.descriptor["clock_id"])
            self.collector = Collector(self.journal, self.transport, self.ledger)
            self.preflight()
            self.authorized = True
            self.switch("derived")
            for trial in TRIALS:
                row = self.trial(trial)
                trials.append(row)
                if not row["protocol_execution_valid"]:
                    break
        except BaseException as exc:
            errors.append(type(exc).__name__+": "+str(exc))
        finally:
            if self.candidate_touched:
                rollback = self.attempt(errors, "outer rollback", self.rollback)
            self.cleanup = True
            if self.ledger:
                self.attempt(errors, "ledger-close", self.ledger.close)
            if self.host_used:
                self.attempt(errors, "host-close", lambda: self.leaf("host-close", "host-close", self.host.close))
            tick = self.budget._tick()
            terminal_before = len(self.journal.events)
            self.attempt(errors, "execution-terminal", lambda: self.journal.checkpoint("execution:end", cleanup=True))
        host = self.host.snapshot() if self.host_used else None
        points = self.journal.prefix.points
        last = points[-1]
        timing = bool(tick is not None and not self.budget.counter_error and not self.journal.failure and not self.journal.capture_failed
                      and self.journal.prefix.status()["clock_capture_valid"] and self.journal.events[-1]["label"] == "execution:end"
                      and points[-2]["qpc_after_ticks"] <= tick <= last["qpc_before_ticks"] and last["qpc_after_ticks"] < self.budget.global_deadline)
        capacity = rollback is None or len(points)-rollback["point_start"] <= 216
        valid = bool(len(trials) == 4 and all(t["protocol_execution_valid"] for t in trials) and not errors and rollback and rollback["service_restored"]
                     and host and host["component_complete"] and timing and capacity and self.log.failure is None)
        result = dict(experiment_id=ID, evidence_label="fixture" if self.fixture else "sandbox-measured",
                      actual_network_commands_executed=0 if self.fixture else sum(r["argv"][0] == "docker" and r["launcher_go_sent"] for r in self.rows),
                      actual_power_requests_executed=0 if self.fixture else int(bool(host and host["power"]["calls"])),
                      network_execution_authorized=False, network_fix_validated=False, TNSM_ready=False,
                      revision=self.revision, execution_lock_sha256=self.lock_digest, approval=approval_initial, approval_at_end=copy.deepcopy(self.approval),
                      output_path=str(self.output.resolve()), receipt_path_observed=str(self.host.lease.path.resolve()),
                      prerequisites=self.prerequisites, steps=copy.deepcopy(self.steps), commands=copy.deepcopy(self.rows),
                      trials=trials, errors=errors, rollback=rollback, host=host, budget=self.budget.snapshot(),
                      windows=copy.deepcopy(self.collector.windows) if self.collector else [],
                      ledger=self.ledger.snapshot() if self.ledger else None, journal=self.journal.snapshot(),
                      final_ticks=tick, terminal_event_before=terminal_before, candidate_switch_attempted=self.candidate_touched,
                      execution_timing_valid=timing, cleanup_inventory_fits=capacity, protocol_execution_valid=valid,
                      log_failure=self.log.failure, execution_events=copy.deepcopy(self.log.events))
        self.log.close()
        return result


def clean(samples):
    if len(samples) != 3 or any(not s["window"]["collection_valid"] or not s["window"]["result"]["packet_delivery_complete"] or not s["telemetry"]["ok"] for s in samples):
        return False
    windows = [s["window"] for s in samples]
    contexts = [[w["result"]["source_ip"], *[json.loads(w["commands"][i]["stdout"]) for i in (0, 1)]] for w in windows]
    return [w["identifier"] for w in windows] == list(range(windows[0]["identifier"], windows[0]["identifier"]+3)) and contexts[0] == contexts[1] == contexts[2]


def cleanup_tag_usable(row):
    """Byte identity for emergency cleanup, explicitly NOT timing acceptance.

Only journal failures are separable from otherwise bounded, completed client
capture. Unknown tag/bytes, timer/job/reader errors still block replacement.
"""
    return (all(row[k] is True for k in ("launcher_go_sent", "job_assigned_before_go", "job_closed", "process_reaped",
                                       "reader_threads_joined", "stdout_utf8", "stderr_utf8"))
            and row["timed_out"] is False and row["truncated"] is False and not row["process_errors"]
            and all(e.startswith("clock journal: ") for e in row["cleanup_errors"])
            and type(row["returncode"]) is int and row["returncode"] == 0 and not row["stderr"])


if __name__ == "__main__":
    raise SystemExit("Software-only integration: no execution CLI is enabled. A later separately committed diagnostic authority gate is required.")
