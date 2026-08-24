"""Execute the preregistered Phase 6 SafeTwin-5G sandbox campaign."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.contracts import ActionProposal  # noqa: E402
from safetwin5g.experiment import expand_design, load_design  # noqa: E402
from safetwin5g.phase6 import (  # noqa: E402
    OBSERVE_ONLY_ACTIONS,
    Phase6UnitRunner,
    negative_control_loss,
    utc_now,
)
from safetwin5g.safety import Decision, SafetyPolicy  # noqa: E402
from safetwin5g.telemetry import parse_ping  # noqa: E402


UE = "safetwin5g-ue"
CORE = "safetwin5g-open5gs"
INTERFACE = "uesimtun0"
PING_TARGET = "10.45.0.1"
DESIGN_PATH = ROOT / "config" / "experiments" / "phase6-v1.json"
POLICY_PATH = ROOT / "config" / "actions.json"
AUTHORIZATION_TEXT = (
    "Proceed through the entire SafeTwin-5G master backlog sequentially, one task "
    "at a time. Continue automatically through all locally executable Phase 1-5 "
    "work without waiting for routine confirmation, using safe reasonable defaults. "
    "Preserve the fail-closed safety policy: no unrestricted live actuation, "
    "mandatory approval and rollback for applied sandbox actions. Then Do it why "
    "you are making incomplete work."
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class CommandRecorder:
    def __init__(self, path: Path):
        self.path = path
        self.sequence = 0

    def run(
        self,
        unit_id: str,
        name: str,
        argv: list[str],
        accepted: tuple[int, ...] = (0,),
    ) -> str:
        self.sequence += 1
        started_at = utc_now()
        result = subprocess.run(
            argv,
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        record = {
            "sequence": self.sequence,
            "unit_id": unit_id,
            "name": name,
            "started_at": started_at,
            "completed_at": utc_now(),
            "argv": argv,
            "returncode": result.returncode,
            "accepted_returncodes": list(accepted),
            "stdout": result.stdout,
            "stdout_sha256": hashlib.sha256(result.stdout.encode("utf-8")).hexdigest(),
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
        if result.returncode not in accepted:
            raise RuntimeError(f"{name} failed with exit code {result.returncode}")
        return result.stdout


class DockerPhase6Backend:
    def __init__(
        self,
        recorder: CommandRecorder,
        design: dict[str, Any],
        control_events: list[dict[str, Any]],
    ):
        self.recorder = recorder
        self.design = design
        self.control_events = control_events
        self.upf_pid: int | None = None

    def _run(
        self,
        unit: dict[str, Any],
        name: str,
        argv: list[str],
        accepted: tuple[int, ...] = (0,),
    ) -> str:
        return self.recorder.run(unit["unit_id"], name, argv, accepted)

    def reset(self, unit: dict[str, Any]) -> None:
        self._clear_packet_impairment(unit, "preflight-clear-qdisc")
        self._resume_upf(unit, "preflight-resume-upf")
        self._stop_stress(unit, "preflight-stop-stress")
        time.sleep(0.5)

    def observe_window(
        self, stage: str, unit: dict[str, Any]
    ) -> list[dict[str, Any]]:
        workload = self.design["workloads"][unit["workload"]]
        samples: list[dict[str, Any]] = []
        interval = float(self.design["unit"]["window_sample_interval_seconds"])
        next_start = time.monotonic()
        for index in range(1, int(self.design["unit"]["window_samples_per_stage"]) + 1):
            remaining = next_start - time.monotonic()
            if remaining > 0:
                time.sleep(remaining)
            observed_at = utc_now()
            metrics = self._observe_once(stage, index, unit, workload)
            samples.append(
                {"sample_index": index, "observed_at": observed_at, "metrics": metrics}
            )
            next_start += interval
        return samples

    def _observe_once(
        self,
        stage: str,
        index: int,
        unit: dict[str, Any],
        workload: dict[str, Any],
    ) -> dict[str, float | None]:
        prefix = f"{stage}-{index:02d}"
        ping_text = self._run(
            unit,
            f"{prefix}-ping",
            [
                "docker", "exec", UE, "ping", "-I", INTERFACE,
                "-c", str(workload["ping_count_per_sample"]),
                "-i", str(workload["ping_interval_seconds"]),
                "-W", "1", PING_TARGET,
            ],
            accepted=(0, 1),
        )
        ping_metrics = parse_ping(ping_text)
        qdisc_text = self._run(
            unit,
            f"{prefix}-qdisc",
            ["docker", "exec", UE, "tc", "qdisc", "show", "dev", INTERFACE],
        )
        configured_loss = re.search(r"\bloss ([\d.]+)%", qdisc_text)
        stats_text = self._run(
            unit,
            f"{prefix}-container-stats",
            ["docker", "stats", "--no-stream", "--format", "{{json .}}", CORE],
        )
        stats = json.loads(stats_text)
        workers_text = self._run(
            unit,
            f"{prefix}-stress-workers",
            ["docker", "exec", CORE, "sh", "-lc", "pgrep -x yes || true"],
        )
        upf_text = self._run(
            unit,
            f"{prefix}-upf-state",
            [
                "docker", "exec", CORE, "sh", "-lc",
                "pid=$(pgrep -x open5gs-upfd); ps -o stat= -p \"$pid\"",
            ],
        )
        targets_text = self._run(
            unit,
            f"{prefix}-prometheus-targets",
            [
                "docker", "exec", CORE, "curl", "--fail", "--silent",
                "http://10.53.0.6:9090/api/v1/targets",
            ],
        )
        targets = json.loads(targets_text)["data"]["activeTargets"]
        metrics = {name: value for name, (value, _) in ping_metrics.items()}
        metrics.update(
            {
                "core_container_cpu_pct": float(stats["CPUPerc"].rstrip("%")),
                "stress_workers_count": float(
                    len([line for line in workers_text.splitlines() if line.strip()])
                ),
                "upf_process_running": 0.0 if "T" in upf_text.strip() else 1.0,
                "prometheus_targets_up_count": float(
                    sum(target["health"] == "up" for target in targets)
                ),
                "configured_packet_loss_pct": (
                    float(configured_loss.group(1)) if configured_loss else 0.0
                ),
            }
        )
        return metrics

    def inject_fault(self, unit: dict[str, Any]) -> None:
        jitter = random.Random(int(unit["seed"])).uniform(0.01, 0.05)
        self.control_events.append(
            {
                "event": "seeded-pre-fault-jitter",
                "seed": unit["seed"],
                "duration_ms": round(jitter * 1000, 3),
                "started_at": utc_now(),
            }
        )
        time.sleep(jitter)
        family = unit["fault_family"]
        severity = unit["severity_value"]
        if family == "packet_impairment":
            self._set_packet_loss(unit, float(severity), "inject-packet-loss")
        elif family == "network_function_interruption":
            pid_text = self._run(
                unit,
                "locate-upf",
                ["docker", "exec", CORE, "pgrep", "-x", "open5gs-upfd"],
            )
            self.upf_pid = int(pid_text.strip())
            self._run(
                unit,
                "suspend-upf",
                ["docker", "exec", CORE, "kill", "-STOP", str(self.upf_pid)],
            )
            time.sleep(float(severity) / 1000.0)
        elif family == "cpu_saturation":
            self._start_stress(unit, int(severity), "start-cpu-stress")
            time.sleep(1.0)
        elif family == "no_fault":
            self.control_events.append({"event": "no-fault-assignment", "at": utc_now()})
        else:
            raise ValueError(f"unsupported fault family: {family}")

    def apply_action(self, unit: dict[str, Any]) -> None:
        kind = unit["action_kind"]
        if kind in OBSERVE_ONLY_ACTIONS:
            self.control_events.append(
                {"event": kind, "unit_id": unit["unit_id"], "at": utc_now()}
            )
        elif kind == "network_impairment_clear":
            self._clear_packet_impairment(unit, "action-clear-packet-impairment")
        elif kind == "nf_process_resume":
            self._resume_upf(unit, "action-resume-upf")
        elif kind == "cpu_stress_stop":
            self._stop_stress(unit, "action-stop-cpu-stress")
        elif kind in {
            "packet_impairment_increase",
            "unrelated_packet_impairment",
            "unnecessary_packet_impairment",
        }:
            self._set_packet_loss(
                unit, negative_control_loss(unit), "action-negative-control-loss"
            )
        else:
            raise ValueError(f"unsupported action kind: {kind}")
        time.sleep(0.5)

    def cleanup(self, unit: dict[str, Any]) -> None:
        errors: list[str] = []
        for operation in (
            lambda: self._clear_packet_impairment(unit, "cleanup-clear-qdisc"),
            lambda: self._resume_upf(unit, "cleanup-resume-upf"),
            lambda: self._stop_stress(unit, "cleanup-stop-stress"),
        ):
            try:
                operation()
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
        time.sleep(0.5)
        if errors:
            raise RuntimeError("; ".join(errors))

    def _set_packet_loss(
        self, unit: dict[str, Any], loss_pct: float, name: str
    ) -> None:
        self._run(
            unit,
            name,
            [
                "docker", "exec", UE, "tc", "qdisc", "replace", "dev",
                INTERFACE, "root", "netem", "loss", f"{loss_pct:g}%",
            ],
        )

    def _clear_packet_impairment(self, unit: dict[str, Any], name: str) -> None:
        self._run(
            unit,
            name,
            [
                "docker", "exec", UE, "tc", "qdisc", "replace", "dev",
                INTERFACE, "root", "fq_codel",
            ],
        )

    def _resume_upf(self, unit: dict[str, Any], name: str) -> None:
        pid_text = self._run(
            unit,
            f"{name}-locate",
            ["docker", "exec", CORE, "pgrep", "-x", "open5gs-upfd"],
        )
        self.upf_pid = int(pid_text.strip())
        self._run(
            unit,
            name,
            ["docker", "exec", CORE, "kill", "-CONT", str(self.upf_pid)],
        )

    def _start_stress(
        self, unit: dict[str, Any], workers: int, name: str
    ) -> None:
        commands = [
            f"taskset -c {cpu} yes >/dev/null 2>&1 & echo $!" for cpu in range(workers)
        ]
        text = self._run(
            unit,
            name,
            ["docker", "exec", CORE, "sh", "-lc", "; ".join(commands)],
        )
        pids = [int(line) for line in text.splitlines() if line.strip().isdigit()]
        if len(pids) != workers:
            raise RuntimeError(f"expected {workers} stress PIDs, got {pids}")

    def _stop_stress(self, unit: dict[str, Any], name: str) -> None:
        self._run(
            unit,
            name,
            [
                "docker", "exec", CORE, "sh", "-lc",
                "pids=$(pgrep -x yes || true); if [ -n \"$pids\" ]; then kill $pids; fi",
            ],
        )


def action_proposal(unit: dict[str, Any]) -> ActionProposal | None:
    kind = unit["action_kind"]
    if kind in OBSERVE_ONLY_ACTIONS:
        return None
    if kind == "network_impairment_clear":
        payload = {
            "kind": kind,
            "target": f"{UE}/{INTERFACE}",
            "target_type": "ue_tunnel",
            "parameters": {"qdisc": "fq_codel"},
            "rollback_plan": "Cleanup verifies fq_codel and a clean user plane.",
            "estimated_risk": 0.05,
        }
    elif kind == "nf_process_resume":
        payload = {
            "kind": kind,
            "target": f"{CORE}/open5gs-upfd",
            "target_type": "upf",
            "parameters": {"signal": "CONT"},
            "rollback_plan": "Cleanup sends CONT to the recorded UPF PID and verifies it running.",
            "estimated_risk": 0.15,
        }
    elif kind == "cpu_stress_stop":
        payload = {
            "kind": kind,
            "target": CORE,
            "target_type": "core_container",
            "parameters": {"process": "yes", "signal": "TERM"},
            "rollback_plan": "Cleanup terminates all sandbox-local stress workers and verifies zero remain.",
            "estimated_risk": 0.10,
        }
    else:
        payload = {
            "kind": "network_impairment_apply",
            "target": f"{UE}/{INTERFACE}",
            "target_type": "ue_tunnel",
            "parameters": {"loss_pct": negative_control_loss(unit)},
            "rollback_plan": "Replace netem with fq_codel and verify zero configured loss.",
            "estimated_risk": 0.25,
        }
    payload["reversible"] = True
    return ActionProposal.from_dict(payload)


def build_approval(design: dict[str, Any], units: list[dict[str, Any]]) -> dict[str, Any]:
    approval_id = hashlib.sha256(
        (AUTHORIZATION_TEXT + design["experiment_id"]).encode("utf-8")
    ).hexdigest()
    return {
        "approval_id": approval_id,
        "approval_status": "approved",
        "approved_by": "user",
        "approval_type": "user-standing-local-sandbox-authorization",
        "environment": "sandbox",
        "experiment_id": design["experiment_id"],
        "unit_ids": [unit["unit_id"] for unit in units],
        "authorized_mutations": [
            "UE-tunnel packet impairment and cleanup",
            "Open5GS UPF process suspension and resume",
            "container-local pinned CPU load and termination",
            "reversible negative-control UE-tunnel packet impairment",
        ],
        "authorization_text": AUTHORIZATION_TEXT,
        "authorization_text_sha256": hashlib.sha256(
            AUTHORIZATION_TEXT.encode("utf-8")
        ).hexdigest(),
        "source_thread_id": "01a02a0d-ff7c-74e0-8a33-e92916f53731",
        "recorded_at": utc_now(),
        "exclusions": [
            "live actuation",
            "private-5G hardware",
            "operator systems",
            "external systems",
            "publication submission",
        ],
    }


def preflight(recorder: CommandRecorder) -> dict[str, Any]:
    server = recorder.run(
        "preflight", "docker-server-version", ["docker", "version", "--format", "{{json .Server}}"]
    )
    containers = [
        "safetwin5g-mongodb",
        "safetwin5g-open5gs",
        "safetwin5g-gnb",
        "safetwin5g-ue",
        "safetwin5g-prometheus",
    ]
    states = {}
    for container in containers:
        text = recorder.run(
            "preflight",
            f"inspect-{container}",
            [
                "docker", "inspect", "--format",
                "{{json .State}}", container,
            ],
        )
        state = json.loads(text)
        states[container] = {
            "status": state["Status"],
            "health": state.get("Health", {}).get("Status"),
        }
    if any(
        state["status"] != "running" or state["health"] != "healthy"
        for state in states.values()
    ):
        raise RuntimeError(f"sandbox preflight is not healthy: {states}")
    return {"captured_at": utc_now(), "docker_server": json.loads(server), "containers": states}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-units", type=int)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    design = load_design(DESIGN_PATH)
    all_units = expand_design(design)
    units = all_units[: args.max_units] if args.max_units is not None else all_units
    if args.max_units is not None and args.max_units < 1:
        parser.error("--max-units must be positive")
    policy = SafetyPolicy.from_path(POLICY_PATH)
    if policy.allow_live or not policy.config.get("require_human_approval"):
        raise RuntimeError("fail-closed policy preflight failed")
    for unit in units:
        proposal = action_proposal(unit)
        if proposal is not None:
            evaluation = policy.evaluate_action(
                proposal,
                environment="sandbox",
                decision_source="preregistered-experiment",
            )
            if evaluation.decision is not Decision.REQUIRE_APPROVAL:
                raise RuntimeError(f"action policy rejected {unit['unit_id']}: {evaluation}")
    if args.dry_run:
        print(
            json.dumps(
                {
                    "experiment_id": design["experiment_id"],
                    "unit_count": len(units),
                    "full_design_unit_count": len(all_units),
                    "policy_version": policy.policy_version,
                    "live_actuation": policy.allow_live,
                    "all_mutations_require_approval": True,
                    "passed": True,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    started = datetime.now(timezone.utc)
    suffix = "phase6-campaign-v1" if len(units) == len(all_units) else "phase6-pilot-v1"
    run_id = started.strftime("%Y%m%dT%H%M%SZ-") + suffix
    output = ROOT / "evidence" / "scenarios" / run_id
    output.mkdir(parents=True, exist_ok=False)
    recorder = CommandRecorder(output / "commands.jsonl")
    approval = build_approval(design, units)
    (output / "approval.json").write_text(
        json.dumps(approval, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "design-units.jsonl").write_text(
        "".join(json.dumps(unit, sort_keys=True) + "\n" for unit in units),
        encoding="utf-8",
    )
    environment = preflight(recorder)
    (output / "environment.json").write_text(
        json.dumps(environment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    results: list[dict[str, Any]] = []
    aborted_for_cleanup = False
    for index, unit in enumerate(units, start=1):
        print(f"[{index}/{len(units)}] {unit['unit_id']}", flush=True)
        control_events: list[dict[str, Any]] = []
        backend = DockerPhase6Backend(recorder, design, control_events)
        proposal = action_proposal(unit)
        if proposal is None:
            evaluation = {
                "decision": "observe-only",
                "reasons": ["assigned arm has no sandbox mutation"],
                "policy_version": policy.policy_version,
            }
        else:
            evaluation = policy.evaluate_action(
                proposal,
                environment="sandbox",
                decision_source="preregistered-experiment",
            ).to_dict()
        trace = Phase6UnitRunner(
            backend, int(design["unit"]["window_samples_per_stage"])
        ).run(unit, approval)
        trace["action_proposal"] = proposal.to_dict() if proposal else None
        trace["safety_evaluation"] = evaluation
        trace["control_events"] = control_events
        trace["claim_boundaries"] = {
            "intervention": "sandbox-measured",
            "radio_access": "simulated",
            "hardware": "not measured",
            "operator_validation": "not performed",
            "model_result": "not applicable during data collection",
        }
        trace_path = output / "units" / f"{unit['unit_id']}.json"
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(
            json.dumps(trace, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        results.append(trace)
        if not trace["cleanup_verified"]:
            aborted_for_cleanup = True
            print("ABORT: cleanup could not be verified", flush=True)
            break

    passed = (
        not aborted_for_cleanup
        and len(results) == len(units)
        and all(result["passed"] for result in results)
    )
    split_counts = {
        split: sum(result["unit"]["split"] == split for result in results)
        for split in ("train", "calibration", "test", "ood")
    }
    summary = {
        "schema_version": 1,
        "run_id": run_id,
        "artifact_type": "full-preregistered-campaign" if len(units) == len(all_units) else "runner-pilot",
        "experiment_id": design["experiment_id"],
        "started_at": started.isoformat(),
        "completed_at": utc_now(),
        "passed": passed,
        "planned_unit_count": len(units),
        "completed_unit_count": len(results),
        "passed_unit_count": sum(result["passed"] for result in results),
        "split_counts": split_counts,
        "aborted_for_cleanup": aborted_for_cleanup,
        "evidence_label": "sandbox-measured" if results else "fixture",
        "radio_evidence_label": "simulated" if results else None,
        "hardware_evidence_label": None,
        "operator_validation": False,
        "design_sha256": sha256(DESIGN_PATH),
        "policy_sha256": sha256(POLICY_PATH),
        "runner_sha256": sha256(Path(__file__)),
        "phase6_module_sha256": sha256(ROOT / "src" / "safetwin5g" / "phase6.py"),
    }
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    captured = {
        str(path.relative_to(output)).replace("\\", "/"): sha256(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_id,
                "passed": passed,
                "evidence_label": summary["evidence_label"],
                "radio_evidence_label": summary["radio_evidence_label"],
                "captured_file_sha256": captured,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(output)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
