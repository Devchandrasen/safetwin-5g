"""Separately versioned R4 execution integration. No mutation by default."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sandbox.run_reconnect_r3 import R3Backend, BASE, DERIVED, UP, verify_fault, verify_execution_lock as r3_lock
from sandbox.reconnect_r3_measurement import CORE, GNB, UE, CONTAINERS, NETWORK, INSPECT_FORMAT, state_metrics
from sandbox.run_reconnect import noqueue
from sandbox.reconnect_r4_collection import (IMAGES, INSPECT, command_plan, precheck, evaluate, log_lines)
from sandbox.reconnect_r4_process import BoundedProcess, complete
from sandbox.reconnect_r4_host_guard import HostGuard, SleepGuard, idle_query

CONFIG_PATH = ROOT / "config/experiments/reconnect-r4-execution.json"
CONFIG = json.loads(CONFIG_PATH.read_bytes())
COMMANDS = json.loads((ROOT / "config/experiments/reconnect-r3-command-contract.json").read_bytes())["fixed_commands"]
MINIMAL_THREE = ["docker", "inspect", "--format", INSPECT, CORE, GNB, UE]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, data):
    with Path(path).open("xb") as handle:
        handle.write((json.dumps(data, indent=2) + "\n").encode())
        handle.flush()
        os.fsync(handle.fileno())


def append(path, data):
    with Path(path).open("ab") as handle:
        handle.write((json.dumps(data) + "\n").encode())
        handle.flush()
        os.fsync(handle.fileno())


def allowed_commands():
    commands = list(COMMANDS.values()) + [MINIMAL_THREE, ["docker", "network", "inspect", NETWORK],
                                          ["docker", "inspect", "--format", INSPECT_FORMAT, *CONTAINERS]]
    for container in (CORE, GNB, UE):
        commands += [["docker", "restart", container], ["docker", "inspect", "--format", "{{.State.Health.Status}}", container]]
    for identifier in range(10001, 10100):
        commands.extend(command_plan(identifier))
    # In particular, there is no timestamp-filtered Docker log command.
    return sorted({tuple(c) for c in commands})


def approval_expected(lock_digest):
    return {"experiment_id": CONFIG["experiment_id"], "execution_lock_sha256": lock_digest,
            "status": "approved", "environment": "sandbox", "type": "standing-project-authorization",
            "approved_by": "user", "trials": CONFIG["trials"], "containers": [CORE, GNB, UE], "image_containers": [GNB, UE],
            "image_ids": [IMAGES["official_image_id"], IMAGES["derived_image_id"]],
            "rollback_plan": "owned qdisc cleanup; both official images; independent core,gNB,UE resets; fresh PDU and 15/15 plus scope and telemetry",
            "operator_validation": False, "live_actuation": False}


def validate_approval(approval, lock_digest):
    if any(approval.get(k) != v for k, v in approval_expected(lock_digest).items()):
        raise PermissionError("exact R4 standing-user approval required")
    if datetime.fromisoformat(approval["recorded_at"]).tzinfo is None:
        raise PermissionError("approval timestamp must have timezone")


def verify_lock(committed=True):
    from tools.verify_reconnect_r4_collection import verify_lock as collection_lock
    collection_lock(committed=committed)
    r3_lock()
    path = ROOT / "config/experiments/reconnect-r4-execution-lock.json"
    lock = json.loads(path.read_bytes())
    from tools.verify_reconnect_r4_execution import SOURCES
    if lock["lock_id"] != CONFIG["experiment_id"] or set(lock["source_sha256"]) != set(SOURCES):
        raise PermissionError("R4 execution lock identity")
    prior = ROOT / "config/experiments/reconnect-r4-collection-lock.json"
    if lock["immutable_collection_lock_sha256"] != sha(prior.read_bytes()):
        raise PermissionError("R4 immutable collection lock drift")
    import subprocess
    for name, digest in lock["source_sha256"].items():
        source = (ROOT / name).resolve()
        if not source.is_relative_to(ROOT) or sha(source.read_bytes()) != digest:
            raise PermissionError("execution source drift: " + name)
        if committed and subprocess.check_output(["git", "show", "HEAD:" + name], cwd=ROOT, timeout=15) != source.read_bytes():
            raise PermissionError("uncommitted execution source: " + name)
    if committed and subprocess.check_output(["git", "show", "HEAD:" + path.relative_to(ROOT).as_posix()], cwd=ROOT, timeout=15) != path.read_bytes():
        raise PermissionError("uncommitted execution lock")
    return lock, sha(path.read_bytes())


class R4Backend(R3Backend):
    def __init__(self, output, transport, approval, lock_digest, *, clock=None, fixture=False):
        super().__init__(output, CONFIG, IMAGES, approval, clock)
        self.transport, self.lock_digest, self.fixture = transport, lock_digest, fixture
        self.allowed = set(allowed_commands())
        self.records, self.events, self.windows = [], [], []
        self.operation = 0
        self.transport.backend = self
        self.monotonic = clock.monotonic if clock else time.perf_counter
        self.monotonic_ns = (lambda: round(clock.monotonic() * 10**9)) if clock else time.perf_counter_ns
        self.admission_started_ns = self.monotonic_ns()
        self.deadline = self.monotonic() + 1500

    def event(self, kind, start, **fields):
        row = {"kind": kind, "unit_id": self.unit_id, "first": start, "last": self.sequence, **fields}
        self.events.append(row)
        append(self.output / "operations.jsonl", row)
        return row

    def cmd(self, name, argv, accepted=(0,), merged=False, timeout=35):
        if tuple(argv) not in self.allowed or not 0 < timeout <= 35:
            raise PermissionError("command outside R4 allowlist/bounds")
        expected = (0, 2) if argv == COMMANDS["ping-help"] else (0, 1) if argv[:4] == ["docker", "exec", UE, "ping"] else (0,)
        if accepted != expected:
            raise PermissionError("loosened exit-code contract")
        if not self.restoring and self.monotonic() >= self.deadline:
            raise TimeoutError("admission ended")
        mutation = argv[:2] == ["docker", "restart"] or (argv[:2] == ["docker", "compose"] and "up" in argv) or argv == COMMANDS["bounded-link-drop"] or argv == COMMANDS["emergency-clear-owned-qdisc"]
        if mutation:
            validate_approval(self.approval, self.lock_digest)
            if not self.authorized:
                raise PermissionError("preflight has not enabled scoped mutation")
        self.sequence += 1
        self.current_name = name
        append(self.output / "command-intents.jsonl", {"sequence": self.sequence, "unit_id": self.unit_id, "name": name, "argv": argv})
        row = self.transport.run(argv, sequence=self.sequence, timeout_seconds=timeout, max_output_bytes=1048576)
        elapsed = row["monotonic_end_ns"] - row["monotonic_start_ns"]
        if abs(row["wall_end_ns"] - row["wall_start_ns"] - elapsed) > 1000000:
            row["capture_error"] = "observed host clock step"
        if self.records and abs(row["wall_start_ns"] - self.records[-1]["wall_end_ns"] - (row["monotonic_start_ns"] - self.records[-1]["monotonic_end_ns"])) > 1000000:
            row["capture_error"] = "observed host inter-command clock step"
        if elapsed > timeout * 10**9 and not row["timed_out"]:
            row["capture_error"] = "command exceeded its declared duration"
        row.update(name=name, unit_id=self.unit_id, accepted_returncodes=list(accepted),
                   started_at=datetime.fromtimestamp(row["wall_start_ns"] / 1e9, timezone.utc).isoformat(),
                   completed_at=datetime.fromtimestamp(row["wall_end_ns"] / 1e9, timezone.utc).isoformat())
        self.records.append(row)
        append(self.output / "commands.jsonl", row)
        if not complete(row) or row["returncode"] not in accepted:
            raise RuntimeError(name + ": incomplete or failed command")
        # Collection commands retain separate streams. Only old CLI-help callers
        # requesting merged output receive concatenated text, with raw streams saved.
        return row["stdout"] + row["stderr"] if merged else row["stdout"]

    def preflight(self):
        super().preflight()
        from sandbox.reconnect_r4_collection import identity
        for component in (UE, GNB):
            raw = self.cmd("preflight-collection-" + component, ["docker", "inspect", "--format", INSPECT, component])
            identity(raw, component, "official-service")

    def scope(self, role, label):
        start = self.sequence + 1
        try:
            result = super().scope(role, label)
        except BaseException as exc:
            self.event("scope", start, role=role, label=label, ok=False, error=str(exc))
            raise
        self.event("scope", start, role=role, label=label, ok=True)
        return result

    def capture_logs(self, component, label):
        text = self.cmd(label, ["docker", "logs", "--timestamps", "--tail", "2000", component])
        if self.records[-1]["stderr"]:
            raise ValueError("unsupported separate log stream")
        log_lines(text)
        return text

    def fresh_reset(self, label, containers):
        start, errors = self.sequence + 1, []
        before = prefix = after = suffix = None
        reset_sequences = []
        try:
            before = self.cmd(label + "-before-identities", MINIMAL_THREE)
            prefix = self.capture_logs(UE, label + "-before-log")
        except BaseException as exc:
            errors.append("before: " + str(exc))
        # Always attempt each requested reset independently, even during failure.
        for container in containers:
            if container not in (CORE, GNB, UE):
                raise PermissionError("reset outside scope")
            try:
                reset_sequences.append(self.sequence + 1)
                self.cmd("restart-" + container, ["docker", "restart", container])
                self.health(container)
            except BaseException as exc:
                errors.append(container + ": " + str(exc))
        try:
            after = self.cmd(label + "-after-identities", MINIMAL_THREE)
            suffix = self.capture_logs(UE, label + "-after-log")
            first, last = [json.loads(line) for line in before.splitlines()], [json.loads(line) for line in after.splitlines()]
            if len(first) != 3 or len(last) != 3 or [r["Name"] for r in first] != ["/" + c for c in (CORE, GNB, UE)]:
                raise ValueError("exact fresh-reset identity inventory")
            for old, new in zip(first, last):
                if old["Name"] != new["Name"] or old["Id"] != new["Id"] or old["Image"] != new["Image"]:
                    raise ValueError("reset identity/image changed")
                if old["Name"].lstrip("/") in containers and old["StartedAt"] == new["StartedAt"]:
                    raise ValueError("reset lacks fresh start")
            pre, post = log_lines(prefix), log_lines(suffix)
            if post[:len(pre)] != pre:
                raise ValueError("fresh registration prefix lost")
            messages = "\n".join(post[len(pre):])
            if messages.count("Initial Registration is successful") != 1 or messages.count("PDU Session establishment is successful") != 1:
                raise ValueError("fresh registration/PDU not uniquely observed")
        except BaseException as exc:
            errors.append("after: " + str(exc))
        return self.event("reset", start, label=label, containers=containers, reset_sequences=reset_sequences,
                          before=before, after=after, prefix=prefix, post=suffix, ok=not errors, errors=errors)

    def sample(self, label, index, mode):
        identifier = self.identifier
        plan = command_plan(identifier)
        # Append+flush+fsync reservation before any command, not just an in-memory increment.
        append(self.output / "identifiers.jsonl", {"identifier": identifier, "unit_id": self.unit_id, "window": label,
                                                  "index": index, "command_first": self.sequence + 1})
        self.identifier += 1
        start = self.sequence + 1
        capture_started = self.monotonic_ns()
        capture_deadline = capture_started + 120 * 10**9
        bundle = {"unit_id": self.unit_id, "window": label, "index": index, "identifier": identifier, "mode": mode,
                  "commands": [], "result": None, "telemetry": {}, "errors": [], "evidence_label": "fixture" if self.fixture else "sandbox-measured",
                  "contract_id": "reconnect-r4-collection-v1", "transport": "in-memory-no-io" if self.fixture else "bounded-windows-job",
                  "network_execution_authorized": not self.fixture, "network_fix_validated": False,
                  "capture_started_ns": capture_started, "capture_deadline_ns": capture_deadline, "admission_abort": None}
        try:
            for local, argv in enumerate(plan, 1):
                checked = self.monotonic_ns()
                if checked + 35 * 10**9 > capture_deadline:
                    bundle["admission_abort"] = {"reason": "collection-budget", "next_local_command": local, "checked_monotonic_ns": checked}
                    raise TimeoutError("insufficient bounded collection window")
                if not self.restoring and self.monotonic() >= self.deadline:
                    bundle["admission_abort"] = {"reason": "experiment-budget", "next_local_command": local, "checked_monotonic_ns": checked}
                    raise TimeoutError("experiment admission ended")
                self.cmd("collection-" + str(local), argv, (0, 1) if local == 8 else (0,))
                record = dict(self.records[-1], sequence=local, global_sequence=self.sequence)
                bundle["commands"].append(record)
                if local == 7:
                    precheck(bundle["commands"], identifier, mode)
            bundle["result"] = evaluate(bundle["commands"], identifier, mode)
            telemetry = []
            for name in ("sample-qdisc", "upf-state", "stress-workers", "targets"):
                telemetry.append(self.cmd(name, COMMANDS[name]))
            bundle["telemetry"] = state_metrics(*telemetry)
            if bundle["telemetry"] != {"configured_packet_loss_pct": 0, "upf_process_running": 1, "stress_workers_count": 0, "prometheus_targets_up_count": 3}:
                raise ValueError("unclean telemetry")
        except BaseException as exc:
            # Failed collection commands are retained in the global journal too.
            if self.records and self.records[-1]["sequence"] == self.sequence and self.sequence >= start and (not bundle["commands"] or bundle["commands"][-1]["global_sequence"] < self.sequence) and self.records[-1]["name"].startswith("collection-"):
                bundle["commands"].append(dict(self.records[-1], sequence=len(bundle["commands"]) + 1, global_sequence=self.sequence))
            bundle["errors"].append(type(exc).__name__ + ": " + str(exc))
        bundle.update(command_first=start, command_last=self.sequence, actual_docker_commands_executed=0 if self.fixture else len(bundle["commands"]))
        self.windows.append(bundle)
        append(self.output / "samples.jsonl", bundle)
        return bundle

    def window(self, label):
        samples = []
        for index in range(3):
            sample = self.sample(label, index, "trace" if self.role == "derived" else "official-service")
            samples.append(sample)
            if sample["errors"]:
                break
        return samples

    def restore(self):
        attempts = []
        for label, containers in (("restore-ue", [UE]), ("restore-full", [CORE, GNB, UE])):
            reset = self.fresh_reset(label, containers)
            samples = self.window(label) if reset["ok"] else []
            ok = reset["ok"] and clean_window(samples)
            attempts.append({"step": label, "reset": reset, "samples": samples, "clean": ok})
            if ok:
                break
        return attempts

    def final_rollback(self):
        self.restoring, self.unit_id = True, "final-rollback"
        errors = []
        try:
            self.clear_owned_fault()
        except BaseException as exc:
            errors.append("qdisc: " + str(exc))
        try:
            self.switch("official")
        except BaseException as exc:
            errors.append("image: " + str(exc))
        # Do not infer actual image role from a failed Compose/health command.
        self.role = "official"
        reset = self.fresh_reset("final-official", [CORE, GNB, UE])
        if not reset["ok"]:
            errors.extend(reset["errors"])
        samples = self.window("final-official") if reset["ok"] else []
        official = False
        try:
            self.scope("official", "final-official")
            official = True
            if not noqueue(self.eth0("final-eth0")):
                raise ValueError("non-neutral final eth0")
        except BaseException as exc:
            errors.append("scope: " + str(exc))
        return {"errors": errors, "reset": reset, "samples": samples, "official_image_restored": official,
                "service_restored": bool(not errors and reset["ok"] and clean_window(samples)), "network_fix_validated": False}


def clean_window(samples):
    if len(samples) != 3 or any(s["errors"] or not s["result"] or not s["result"]["packet_delivery_complete"] for s in samples):
        return False
    if [s["identifier"] for s in samples] != list(range(samples[0]["identifier"], samples[0]["identifier"] + 3)):
        return False
    contexts = [[s["result"]["source_ip"], *[json.loads(s["commands"][i]["stdout"]) for i in (0, 1)]] for s in samples]
    return all(context == contexts[0] for context in contexts)


def run_trial(backend, trial):
    backend.unit_id = trial["trial_id"]
    row = {"trial": trial, "errors": [], "baseline": [], "post": [], "restoration_attempts": [], "exposure_command": None}
    prepared = False
    try:
        if backend.monotonic() + 180 > backend.deadline:
            raise TimeoutError("insufficient admission budget")
        backend.scope("derived", "trial-scope")
        if not noqueue(backend.eth0("preparation-eth0")):
            raise ValueError("pre-existing fault")
        prepared = True
        row["reset"] = backend.fresh_reset("preparation", [CORE, GNB, UE])
        if not row["reset"]["ok"]:
            raise ValueError("fresh baseline reset failed")
        row["baseline"] = backend.window("baseline")
        if not clean_window(row["baseline"]) or not noqueue(backend.eth0("baseline-eth0")):
            raise ValueError("invalid baseline blocks exposure")
        prefix = {c: backend.capture_logs(c, "exposure-before-" + c) for c in (UE, GNB)}
        name = "bounded-link-drop" if trial["drop_ue_egress"] else "control-wait"
        row["exposure_command"] = backend.sequence + 1
        raw = backend.cmd(name, COMMANDS[name])
        if trial["drop_ue_egress"]:
            verify_fault(raw)
        if not noqueue(backend.eth0("post-exposure-eth0")):
            raise ValueError("exposure cleanup failed")
        row["settle_started_ns"] = backend.monotonic_ns()
        backend.sleep(5)
        row["settle_completed_ns"] = backend.monotonic_ns()
        row["post"] = backend.window("post")
        suffix = {c: backend.capture_logs(c, "exposure-after-" + c) for c in (UE, GNB)}
        messages = {}
        for c in (UE, GNB):
            pre, post = log_lines(prefix[c]), log_lines(suffix[c])
            if post[:len(pre)] != pre:
                raise ValueError("exposure log prefix lost")
            messages[c] = "\n".join(post[len(pre):])
        row["context"] = {"before": prefix, "after": suffix,
                          "service_accept_observed": "Service Accept received" in messages[UE],
                          "initial_context_observed": "Initial Context Setup Request received" in messages[GNB]}
        row["recovery_15_of_15"] = clean_window(row["post"])
        if len(row["post"]) != 3 or any(s["errors"] for s in row["post"]):
            raise ValueError("incomplete post collection")
        if not trial["drop_ue_egress"] and (not row["recovery_15_of_15"] or "Radio link failure detected" in messages[UE]):
            raise ValueError("control failed")
    except BaseException as exc:
        row["errors"].append(type(exc).__name__ + ": " + str(exc))
    finally:
        backend.restoring = True
        try:
            backend.clear_owned_fault()
        except BaseException as exc:
            row["errors"].append("cleanup: " + str(exc))
        if prepared and (trial["drop_ue_egress"] or row["errors"]):
            row["restoration_attempts"] = backend.restore()
            row["final_service_restored"] = row["restoration_attempts"][-1]["clean"]
        else:
            row["final_service_restored"] = row.get("recovery_15_of_15", False)
        backend.restoring = False
    row["protocol_execution_valid"] = not row["errors"] and row["final_service_restored"]
    row["network_fix_validated"] = False
    return row


def execute(backend, host):
    trials, errors, rollback = [], [], None
    try:
        validate_approval(backend.approval, backend.lock_digest)
        host.start()
        save(backend.output / "host-admission.json", host.record)
        backend.preflight()
        backend.authorized = True
        backend.switch("derived")
        for index, trial in enumerate(CONFIG["trials"], 1):
            row = run_trial(backend, trial)
            trials.append(row)
            save(backend.output / f"trial-{index:02d}.json", row)
            if not row["protocol_execution_valid"]:
                break
    except BaseException as exc:
        errors.append(type(exc).__name__ + ": " + str(exc))
    finally:
        try:
            if backend.candidate_touched:
                rollback = backend.final_rollback()
            save(backend.output / "final-rollback.json", rollback)
        finally:
            try:
                host.close()
            except BaseException as exc:
                errors.append("host cleanup: " + str(exc))
            save(backend.output / "host-guard.json", host.record)
    valid = bool(len(trials) == 4 and all(r["protocol_execution_valid"] for r in trials) and not errors
                 and rollback and rollback["service_restored"] and rollback["official_image_restored"] and backend.monotonic() <= backend.deadline)
    summary = {"experiment_id": CONFIG["experiment_id"], "attempted_assignments": len(trials),
               "valid_completed_assignments": sum(r["protocol_execution_valid"] for r in trials),
               "protocol_execution_valid": valid, "errors": errors, "candidate_switch_attempted": backend.candidate_touched,
               "admission_budget_exceeded": backend.monotonic() > backend.deadline,
               "admission_started_monotonic_ns": backend.admission_started_ns,
               "completed_monotonic_ns": backend.monotonic_ns(),
               "official_image_restored": bool(rollback and rollback["official_image_restored"]),
               "final_service_restored": bool(rollback and rollback["service_restored"]),
               "evidence_label": "fixture" if backend.fixture else "sandbox-measured", "radio_evidence_label": "simulated",
               "actual_docker_commands_executed": 0 if backend.fixture else len(backend.records),
               "network_fix_validated": False, "TNSM_ready": False, "confirmatory_data": False,
               "live_actuation": False, "hardware_measured": False, "operator_validated": False}
    save(backend.output / "summary.json", summary)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--approval", type=Path)
    args = parser.parse_args()
    if not args.execute or args.approval is None:
        parser.error("no mutation by default; a separate committed gate and exact approval file are mandatory")
    lock, digest = verify_lock()
    approval = json.loads(args.approval.read_bytes())
    validate_approval(approval, digest)
    if datetime.fromisoformat(approval["recorded_at"]) > datetime.now(timezone.utc):
        raise PermissionError("approval is not prior to execution")
    policy = json.loads((ROOT / "config/actions.json").read_bytes())
    if policy["allow_live_actuation"] is not False or policy["require_human_approval"] is not True:
        raise PermissionError("fail-closed policy")
    from tools.audit_reconnect_r3_build_v2 import audit
    audit(ROOT / IMAGES["build_release"])
    if any((ROOT / "evidence/engineering").glob("*-reconnect-r4-network")):
        raise PermissionError("prior R4 attempt exists; no automatic retry")
    guard = ROOT / "evidence/private/reconnect-r4-runtime.lock"
    guard.parent.mkdir(exist_ok=True, parents=True)
    if (ROOT / "evidence/private/reconnect-r3-runtime.lock").exists():
        raise PermissionError("existing R3 runtime lock requires inspection")
    save(guard, {"pid": os.getpid(), "execution_lock_sha256": digest})
    try:
        output = ROOT / "evidence/engineering" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r4-network")
        output.mkdir(exist_ok=False)
        save(output / "approval.json", approval)
        save(output / "design.json", {"config": CONFIG, "images": IMAGES, "execution_lock": lock,
                                      "execution_lock_sha256": digest, "execution_mode": "sandbox", "transport": "bounded-windows-job"})
        transport = BoundedProcess(allowed_commands())
        backend = R4Backend(output, transport, approval, digest)
        host = HostGuard(BoundedProcess([idle_query(os.getpid())]), SleepGuard(), os.getpid())
        result = execute(backend, host)
        save(output / "manifest.json", {"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}})
        print(json.dumps(result, indent=2))
        return 0 if result["protocol_execution_valid"] else 2
    finally:
        if json.loads(guard.read_bytes())["pid"] == os.getpid():
            guard.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
