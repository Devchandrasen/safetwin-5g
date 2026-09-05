"""Explicit deterministic fake Docker transport. Never contacts the daemon."""
import copy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess

from sandbox.run_reconnect_r3 import R3Backend, CONFIG_PATH, IMAGE_PATH, approval_record, execute, save, sha, BASE, DERIVED, UP
from sandbox.reconnect_r3_measurement import CORE, GNB, UE

ROOT = Path(__file__).resolve().parents[1]
PREFLIGHT = ROOT / "evidence/engineering/20260905T122339Z-reconnect-r3-preflight"


class Clock:
    def __init__(self): self.value = 0.0
    def now(self): return (datetime(2026, 9, 5, tzinfo=timezone.utc) + timedelta(seconds=self.value)).isoformat()
    def monotonic(self): return self.value
    def sleep(self, seconds): self.value += seconds


class FakeDocker(R3Backend):
    def __init__(self, output, mode="complete"):
        clock = Clock()
        config, images = json.loads(CONFIG_PATH.read_bytes()), json.loads(IMAGE_PATH.read_bytes())
        super().__init__(output, config, images, approval_record(config, images, clock.now()), clock)
        captured = [json.loads(line) for line in (PREFLIGHT / "commands.jsonl").read_text().splitlines()]
        self.cached = {tuple(row["argv"]): row for row in captured}
        self.containers = {row["Name"].lstrip("/"): row for row in [json.loads(line) for line in next(r for r in captured if r["name"] == "preflight-containers")["stdout"].splitlines()]}
        self.network = json.loads(next(r for r in captured if r["name"] == "preflight-network")["stdout"])[0]
        self.events = {name: [] for name in (CORE, GNB, UE)}
        self.fake_role, self.mode, self.loss_next, self.used_bad_baseline, self.fake_trial = "official", mode, False, False, 0
        self.ping_calls = 0

    def event(self, container, body):
        self.sleep(0.001); self.events[container].append((self.now(), body))

    def invoke(self, argv, merged, timeout):
        self.sleep(0.01)
        out, code = "", 0
        if argv[:2] == ["docker", "compose"] and "up" in argv:
            self.fake_role = "derived" if argv == DERIVED + UP else "official"
            for n, name in enumerate((GNB, UE), 1):
                row = self.containers[name]
                row["Id"] = sha((self.fake_role + name).encode())
                row["Image"] = self.images[self.fake_role + "_image_id"]
                row["Config"]["Image"] = self.images[self.fake_role + "_tag"]
                row["Config"]["Labels"]["safetwin5g.derived.revision"] = "reconnect-r3-trace" if self.fake_role == "derived" else None
                row["State"]["StartedAt"] = self.now()
            if self.mode == "failed-switch" and self.fake_role == "derived": code = 1
        elif argv[:2] == ["docker", "restart"]:
            name = argv[2]; self.containers[name]["State"]["StartedAt"] = self.now(); self.loss_next = False
            if name == UE:
                self.event(UE, "[nas] Initial Registration is successful")
                self.event(UE, "[nas] PDU Session establishment is successful")
            out = name + "\n"
        elif argv[:3] == ["docker", "network", "inspect"]:
            network = copy.deepcopy(self.network)
            network["Containers"] = {self.containers[row["Name"]]["Id"]: row for row in network["Containers"].values()}
            out = json.dumps([network])
        elif argv[:3] == ["docker", "inspect", "--format"]:
            if argv[3] == "{{.State.Health.Status}}": out = "healthy\n"
            else: out = "\n".join(json.dumps(self.containers[name]) for name in argv[4:]) + "\n"
        elif argv[:3] == ["docker", "image", "inspect"]:
            role = "derived" if argv[-1] == self.images["derived_tag"] else "official"
            out = self.images[role + "_image_id"] + "\n"
        elif argv[:2] == ["docker", "logs"]:
            since, until, container = argv[4], argv[6], argv[-1]
            out = "".join(f"{at} {body}\n" for at, body in self.events[container] if since <= at <= until)
        elif argv[:4] == ["docker", "exec", UE, "ping"] and "-e" in argv:
            identifier = int(argv[7]); self.ping_calls += 1
            lose = self.loss_next
            if self.mode == "bad-baseline" and not self.used_bad_baseline:
                lose = True; self.used_bad_baseline = True
            self.loss_next = False
            replies = list(range(2 if lose else 1, 6))
            out = "PING 10.45.0.1 (10.45.0.1) from 10.45.0.2 uesimtun0: 56(84) bytes of data.\n"
            for seq in range(1, 6):
                idle = lose and seq == 1
                if self.fake_role == "derived":
                    stages = ["nas_in", "nas_idle"] if idle else ["nas_in", "nas_forward", "ue_rls", "gnb_in", "gnb_resource"]
                    if self.mode == "incomplete-trace" and self.unit_id == "trace:drop-a" and lose and seq == 2: stages.remove("gnb_resource")
                    for stage in stages:
                        context = f"psi=1 actor=0 cm={int(not idle)} mm=7 ps=1 pending=0 ipid={seq} id={identifier} seq={seq} bytes=84 fp={identifier * 1000 + seq}"
                        self.event(GNB if stage.startswith("gnb_") else UE, f"[debug] ST3 stage={stage} {context}")
                if seq in replies: out += f"64 bytes from 10.45.0.1: icmp_seq={seq} ttl=64 time=0.1 ms\n"
                self.sleep(0.2)
            out += f"\n--- 10.45.0.1 ping statistics ---\n5 packets transmitted, {len(replies)} received, {(5-len(replies))*20}% packet loss, time 800ms\n"
            code = int(lose)
        elif argv[:4] == ["docker", "exec", UE, "timeout"]:
            first = self.now(); self.sleep(8); last = self.now()
            out = first + '\n[{"kind":"netem","handle":"7157:","root":true,"options":{"loss-random":{"loss":1}}}]\n' + last + '\n[{"kind":"noqueue","root":true}]\n'
            self.loss_next = True
            self.event(UE, "Radio link failure detected")
            self.event(UE, "Sending Service Request")
            self.event(UE, "Service Accept received")
            self.event(GNB, "Initial Context Setup Request received")
        elif argv == ["docker", "exec", UE, "sleep", "8"]: self.sleep(8)
        elif argv[:4] == ["docker", "exec", UE, "tc"]:
            out = json.dumps([{"kind": "fq_codel" if argv[-1] == "uesimtun0" else "noqueue", "root": True}])
        elif argv[:5] == ["docker", "exec", CORE, "sh", "-lc"]:
            out = "S\n" if "ps -o" in argv[-1] else ""
        elif argv[:4] == ["docker", "exec", CORE, "curl"]:
            out = json.dumps({"data": {"activeTargets": [{"health": "up", "labels": {"job": "open5gs-" + name}} for name in ("amf", "smf", "upf")]}})
        elif tuple(argv) in self.cached:
            cached = self.cached[tuple(argv)]; out, code = cached["stdout"], cached["returncode"]
        else: raise AssertionError("unmodelled command: " + repr(argv))
        return subprocess.CompletedProcess(argv, code, out.encode(), b"")


def make_bundle(output, mode="complete", source_hashes=None):
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    backend = FakeDocker(output, mode)
    save(output / "approval.json", backend.approval)
    if source_hashes is None:
        source_hashes = json.loads((ROOT / "config/experiments/reconnect-r3-execution-lock.json").read_bytes())["source_sha256"]
    save(output / "design.json", {"config": backend.config, "images": backend.images, "source_sha256": source_hashes,
                                 "execution_mode": "fixture", "transport": "fake-docker-no-io"})
    result = execute(backend, lambda name, value: save(output / name, value))
    result["evidence_label"] = "fixture"
    result["actual_docker_commands_executed"] = 0
    save(output / "summary.json", result)
    save(output / "manifest.json", {"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}})
    return result
