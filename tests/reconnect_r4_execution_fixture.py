"""Invented complete/stopped R4 protocol transport; no daemon or socket calls."""
import base64
from datetime import datetime, timezone
import json
from pathlib import Path

from tests.reconnect_r3_fixture import FakeDocker
from sandbox.run_reconnect_r4 import (R4Backend, CONFIG, IMAGES, CORE, UE, GNB, MINIMAL_THREE,
                                      COMMANDS, approval_expected, execute, save, sha, ROOT)
from sandbox.reconnect_r4_collection import INSPECT
from sandbox.reconnect_r4_host_guard import HostGuard, SleepGuard

EPOCH = 1788566400 * 10**9


class Transport:
    def __init__(self, output, case="complete"):
        old_case = case if case in ("bad-baseline", "incomplete-trace", "failed-switch") else "complete"
        self.engine = FakeDocker(output, old_case)
        self.clock = self.engine.monotonic.__self__
        self.case, self.missing_used = case, False
        self.backend = None
        for component in (CORE, GNB, UE):
            self.engine.event(component, "[fixture] component ready")

    def instant(self):
        return EPOCH + round(self.clock.monotonic() * 10**9)

    def render_logs(self, component):
        def stamp(value):
            return datetime.fromisoformat(value).strftime("%Y-%m-%dT%H:%M:%S.%f") + "000Z"
        return "".join(stamp(at) + " " + text + "\n" for at, text in self.engine.events[component])

    def invoke(self, argv):
        engine, backend = self.engine, self.backend
        engine.unit_id = backend.unit_id.replace("r4:", "trace:")
        name = getattr(backend, "current_name", "host-idle")
        if argv[0] == "powershell.exe":
            self.clock.sleep(0.01)
            return ("9876\n" if self.case == "busy-host" else ""), 0
        if argv[:4] == ["docker", "exec", UE, "ip"]:
            self.clock.sleep(0.01)
            source = "10.45.0.3" if self.case == "ineligible-source" and backend.unit_id != "final-rollback" else "10.45.0.2"
            return json.dumps([{"ifname": "uesimtun0", "flags": ["UP", "LOWER_UP"], "addr_info": [{"family": "inet", "scope": "global", "local": source}]}]), 0
        if argv[:2] == ["docker", "logs"]:
            self.clock.sleep(0.01)
            return self.render_logs(argv[-1]), 0
        if argv[:2] == ["docker", "inspect"] and argv[3] == INSPECT:
            self.clock.sleep(0.01)
            selected = []
            for component in argv[4:]:
                row = engine.containers[component]
                selected.append({"Id": row["Id"], "Name": row["Name"], "Image": row["Image"], "RestartCount": row["RestartCount"],
                                 "StartedAt": row["State"]["StartedAt"], "Running": row["State"]["Running"], "LogConfig": {"Type": "json-file", "Config": {}}})
            return "\n".join(json.dumps(row) for row in selected) + "\n", 0
        if len(argv) == 6 and argv[3:] == ["date", "-u", "+%s.%N"]:
            self.clock.sleep(0.01)
            value = self.instant() - 300_000_000
            sec, nanos = divmod(value, 10**9)
            return f"{sec}.{nanos:09d}\n", 0
        if backend.unit_id == "final-rollback":
            if self.case == "failed-health" and name == "health-" + CORE:
                self.clock.sleep(0.01)
                return "unhealthy\n", 0
            if self.case == "failed-final-switch" and name == "switch-official":
                return "fixture failed official replacement\n", 1
            if self.case == "failed-cleanup":
                if name == "rollback-inspect-eth0":
                    return '[{"kind":"netem","handle":"7157:","root":true}]', 0
                if name == "emergency-clear-owned-qdisc":
                    return "fixture failed owned cleanup\n", 1
            if self.case == "failed-reset" and argv == ["docker", "restart", CORE]:
                return "fixture failed core reset\n", 1
            if self.case == "failed-official-service" and name == "collection-8" and not self.missing_used:
                engine.loss_next = True
                self.missing_used = True
        result = engine.invoke(argv, False, 35)
        if argv[:2] == ["docker", "compose"] and "up" in argv and not (self.case == "stale-official-trace" and name == "switch-official"):
            # Compose force-recreate makes new containers with new log histories.
            # A docker restart, by contrast, must preserve the existing prefix.
            for component in (GNB, UE):
                engine.events[component] = []
                engine.event(component, "[fixture] newly created component ready")
        output = result.stdout.decode()
        if self.case == "missing-fresh-pdu" and argv == ["docker", "restart", UE] and not self.missing_used:
            engine.events[UE] = [(at, text) for at, text in engine.events[UE] if "PDU Session establishment is successful" not in text]
            self.missing_used = True
        code = result.returncode
        if argv[:4] == ["docker", "exec", UE, "ping"] and "-e" in argv:
            code = 0 if "0 received" not in output else 1  # ping without deadline: any reply gives zero
        return output, code

    def run(self, argv, *, sequence, timeout_seconds, max_output_bytes):
        started = self.instant()
        before = round(self.clock.monotonic() * 10**9)
        output, code = self.invoke(argv)
        if self.case == "window-budget" and getattr(self.backend, "current_name", "") == "collection-1" and self.backend.unit_id != "final-rollback":
            self.clock.sleep(30)
        if self.case == "window-budget" and getattr(self.backend, "current_name", "") in ("collection-2", "collection-3") and self.backend.unit_id != "final-rollback":
            self.clock.sleep(30)
        self.clock.sleep(0.001)
        row = {"sequence": sequence, "argv": list(argv), "timeout_seconds": timeout_seconds, "max_output_bytes": max_output_bytes,
               "wall_start_ns": started, "monotonic_start_ns": before, "wall_end_ns": self.instant(),
               "monotonic_end_ns": round(self.clock.monotonic() * 10**9), "returncode": code, "stdout": output, "stderr": "",
               "timed_out": False, "truncated": False, "capture_error": None, "job_assigned_before_go": True,
               "launcher_go_sent": True, "reader_threads_joined": True, "process_reaped": True, "cleanup_grace_seconds": 2,
               "monotonic_clock": {"api": "virtual-fixture", "implementation": "in-memory", "monotonic": True, "adjustable": False, "resolution": 1e-9}}
        if self.case == "timeout" and getattr(self.backend, "current_name", "") == "collection-9" and not self.missing_used:
            row["timed_out"], row["returncode"] = True, -999
            row["stdout"] = row["stdout"][:70]
            self.missing_used = True
        for stream in ("stdout", "stderr"):
            raw = row[stream].encode()
            row[stream + "_base64"] = base64.b64encode(raw).decode()
            row[stream + "_sha256"] = sha(raw)
        row["retained_output_bytes"] = len(row["stdout"].encode()) + len(row["stderr"].encode())
        return row


def make_bundle(output, case="complete", lock=None):
    output = Path(output)
    output.mkdir(exist_ok=False, parents=True)
    if lock is None:
        lock_path = ROOT / "config/experiments/reconnect-r4-execution-lock.json"
        lock = json.loads(lock_path.read_bytes()) if lock_path.exists() else {"lock_id": CONFIG["experiment_id"], "source_sha256": {}}
    digest = sha((json.dumps(lock, indent=2) + "\n").encode())
    transport = Transport(output, case)
    approval = {**approval_expected(digest), "recorded_at": transport.clock.now()}
    backend = R4Backend(output, transport, approval, digest, clock=transport.clock, fixture=True)
    def setter(flags):
        if case == "sleep-enable-failed" and flags == 0x80000001:
            return 0
        if case == "sleep-clear-failed" and flags == 0x80000000:
            return 0
        return 0x80000000
    host = HostGuard(transport, SleepGuard(setter), 4242, fixture=True, monotonic_ns=backend.monotonic_ns)
    save(output / "approval.json", approval)
    save(output / "design.json", {"config": CONFIG, "images": IMAGES, "execution_lock": lock,
                                 "execution_lock_sha256": digest, "execution_mode": "fixture", "transport": "in-memory-no-io"})
    result = execute(backend, host)
    save(output / "manifest.json", {"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}})
    return result
