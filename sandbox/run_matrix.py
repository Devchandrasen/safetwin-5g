"""Execute the approved multi-family SafeTwin-5G sandbox matrix."""

from __future__ import annotations

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
from safetwin5g.safety import Decision, SafetyPolicy  # noqa: E402
from safetwin5g.scenario import ScenarioRunner, ScenarioSpec  # noqa: E402
from safetwin5g.telemetry import parse_ping  # noqa: E402


UE = "safetwin5g-ue"
CORE = "safetwin5g-open5gs"
INTERFACE = "uesimtun0"
PING_TARGET = "10.45.0.1"
MATRIX_PATH = ROOT / "config" / "scenarios" / "matrix-v0.json"
AUTHORIZATION_TEXT = (
    "Continue automatically through all locally executable Phase 1-5 work "
    "without waiting for routine confirmation, using safe reasonable defaults. "
    "Preserve the fail-closed safety policy: no unrestricted live actuation, "
    "mandatory approval and rollback for applied sandbox actions."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class MatrixBackend:
    def __init__(
        self,
        spec: ScenarioSpec,
        scenario_dir: Path,
        command_log: list[dict[str, Any]],
    ):
        self.spec = spec
        self.scenario_dir = scenario_dir
        self.command_log = command_log
        self.stress_pids: list[int] = []
        self.upf_pid: int | None = None
        self.control_events: list[dict[str, Any]] = []

    def run(
        self,
        name: str,
        argv: list[str],
        *,
        accepted: tuple[int, ...] = (0,),
    ) -> tuple[int, str]:
        started = utc_now()
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
        relative = f"commands/{len(self.command_log):04d}-{name}.txt"
        path = self.scenario_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(result.stdout, encoding="utf-8")
        self.command_log.append(
            {
                "scenario_id": self.spec.scenario_id,
                "name": name,
                "started_at": started,
                "completed_at": utc_now(),
                "argv": argv,
                "returncode": result.returncode,
                "accepted_returncodes": list(accepted),
                "output_file": str(path.relative_to(self.scenario_dir.parents[1])).replace("\\", "/"),
            }
        )
        if result.returncode not in accepted:
            raise RuntimeError(f"{name} failed with exit code {result.returncode}")
        return result.returncode, result.stdout

    def observe(self, stage: str) -> dict[str, float]:
        packet_count = "20" if self.spec.fault_family == "packet_impairment" else "10"
        _, ping_text = self.run(
            f"{stage}-ping",
            [
                "docker", "exec", UE, "ping", "-I", INTERFACE, "-c", packet_count,
                "-i", "0.1", "-W", "1", PING_TARGET,
            ],
            accepted=(0, 1),
        )
        ping_metrics = parse_ping(ping_text)
        _, qdisc_text = self.run(
            f"{stage}-qdisc",
            ["docker", "exec", UE, "tc", "qdisc", "show", "dev", INTERFACE],
        )
        configured_loss = re.search(r"\bloss ([\d.]+)%", qdisc_text)
        _, stats_text = self.run(
            f"{stage}-container-stats",
            [
                "docker", "stats", "--no-stream", "--format", "{{json .}}", CORE,
            ],
        )
        stats = json.loads(stats_text)
        cpu_pct = float(stats["CPUPerc"].rstrip("%"))
        _, workers_text = self.run(
            f"{stage}-stress-workers",
            ["docker", "exec", CORE, "sh", "-lc", "pgrep -x yes || true"],
        )
        worker_count = len([line for line in workers_text.splitlines() if line.strip()])
        _, upf_text = self.run(
            f"{stage}-upf-state",
            [
                "docker", "exec", CORE, "sh", "-lc",
                "pid=$(pgrep -x open5gs-upfd); ps -o stat= -p \"$pid\"",
            ],
        )
        upf_state = upf_text.strip()
        _, targets_text = self.run(
            f"{stage}-prometheus-targets",
            [
                "docker", "exec", CORE, "curl", "--fail", "--silent",
                "http://10.53.0.6:9090/api/v1/targets",
            ],
        )
        targets = json.loads(targets_text)["data"]["activeTargets"]
        metrics = {name: value for name, (value, _) in ping_metrics.items()}
        metrics.update(
            {
                "core_container_cpu_pct": cpu_pct,
                "stress_workers_count": float(worker_count),
                "upf_process_running": 0.0 if "T" in upf_state else 1.0,
                "prometheus_targets_up_count": float(
                    sum(target["health"] == "up" for target in targets)
                ),
                "configured_packet_loss_pct": (
                    float(configured_loss.group(1)) if configured_loss else 0.0
                ),
            }
        )
        return metrics

    def inject_fault(self, spec: ScenarioSpec) -> None:
        jitter = random.Random(spec.seed).uniform(0.01, 0.15)
        self.control_events.append(
            {
                "event": "seeded-pre-fault-jitter",
                "seed": spec.seed,
                "duration_ms": round(jitter * 1000, 3),
                "started_at": utc_now(),
            }
        )
        time.sleep(jitter)
        severity = next(iter(spec.fault_parameters.values()))
        if spec.fault_family == "packet_impairment":
            self.run(
                "inject-packet-loss",
                [
                    "docker", "exec", UE, "tc", "qdisc", "replace", "dev",
                    INTERFACE, "root", "netem", "loss", f"{severity}%",
                ],
            )
        elif spec.fault_family == "network_function_interruption":
            _, pid_text = self.run(
                "locate-upf", ["docker", "exec", CORE, "pgrep", "-x", "open5gs-upfd"]
            )
            self.upf_pid = int(pid_text.strip())
            self.run(
                "suspend-upf",
                ["docker", "exec", CORE, "kill", "-STOP", str(self.upf_pid)],
            )
            time.sleep(float(severity) / 1000.0)
        elif spec.fault_family == "cpu_saturation":
            self._start_stress(int(severity), "start-cpu-stress")
            time.sleep(1.0)
        else:
            raise ValueError(f"unsupported fault family: {spec.fault_family}")

    def apply_action(self, spec: ScenarioSpec) -> None:
        if spec.fault_family == "packet_impairment":
            self._clear_packet_impairment("clear-packet-impairment")
        elif spec.fault_family == "network_function_interruption":
            self._resume_upf("resume-upf")
        elif spec.fault_family == "cpu_saturation":
            self._stop_stress("stop-cpu-stress")
        time.sleep(0.5)

    def rollback_action(self, spec: ScenarioSpec) -> None:
        severity = next(iter(spec.fault_parameters.values()))
        if spec.fault_family == "packet_impairment":
            self.run(
                "rollback-packet-loss",
                [
                    "docker", "exec", UE, "tc", "qdisc", "replace", "dev",
                    INTERFACE, "root", "netem", "loss", f"{severity}%",
                ],
            )
        elif spec.fault_family == "network_function_interruption":
            if self.upf_pid is None:
                raise RuntimeError("UPF PID was not captured")
            self.run(
                "rollback-suspend-upf",
                ["docker", "exec", CORE, "kill", "-STOP", str(self.upf_pid)],
            )
        elif spec.fault_family == "cpu_saturation":
            self._start_stress(int(severity), "rollback-cpu-stress")
        time.sleep(0.5)

    def cleanup(self, spec: ScenarioSpec) -> None:
        if spec.fault_family == "packet_impairment":
            self._clear_packet_impairment("cleanup-packet-impairment")
        elif spec.fault_family == "network_function_interruption":
            self._resume_upf("cleanup-resume-upf")
        elif spec.fault_family == "cpu_saturation":
            self._stop_stress("cleanup-cpu-stress")
        time.sleep(0.5)

    def _clear_packet_impairment(self, name: str) -> None:
        self.run(
            name,
            [
                "docker", "exec", UE, "tc", "qdisc", "replace", "dev",
                INTERFACE, "root", "fq_codel",
            ],
        )

    def _resume_upf(self, name: str) -> None:
        pid = self.upf_pid
        if pid is None:
            _, pid_text = self.run(
                f"{name}-locate", ["docker", "exec", CORE, "pgrep", "-x", "open5gs-upfd"]
            )
            pid = int(pid_text.strip())
            self.upf_pid = pid
        self.run(name, ["docker", "exec", CORE, "kill", "-CONT", str(pid)])

    def _start_stress(self, workers: int, name: str) -> None:
        commands = [
            f"taskset -c {cpu} yes >/dev/null 2>&1 & echo $!" for cpu in range(workers)
        ]
        _, text = self.run(
            name,
            ["docker", "exec", CORE, "sh", "-lc", "; ".join(commands)],
        )
        self.stress_pids = [int(line) for line in text.splitlines() if line.strip().isdigit()]
        if len(self.stress_pids) != workers:
            raise RuntimeError(f"expected {workers} stress PIDs, got {self.stress_pids}")

    def _stop_stress(self, name: str) -> None:
        self.run(
            name,
            [
                "docker", "exec", CORE, "sh", "-lc",
                "pids=$(pgrep -x yes || true); if [ -n \"$pids\" ]; then kill $pids; fi",
            ],
        )
        self.stress_pids = []


def action_for(spec: ScenarioSpec) -> ActionProposal:
    if spec.action_kind == "network_impairment_clear":
        target_type, parameters, rollback, risk = (
            "ue_tunnel",
            {"qdisc": "fq_codel"},
            "Reapply the scenario's exact netem loss percentage.",
            0.05,
        )
    elif spec.action_kind == "nf_process_resume":
        target_type, parameters, rollback, risk = (
            "upf",
            {"signal": "CONT"},
            "Send STOP to the same recorded Open5GS UPF PID.",
            0.15,
        )
    elif spec.action_kind == "cpu_stress_stop":
        target_type, parameters, rollback, risk = (
            "core_container",
            {"signal": "TERM", "process": "yes"},
            "Restart the same number of pinned CPU workers.",
            0.10,
        )
    else:
        raise ValueError(f"unsupported action kind: {spec.action_kind}")
    return ActionProposal.from_dict(
        {
            "kind": spec.action_kind,
            "target": spec.target,
            "target_type": target_type,
            "parameters": parameters,
            "reversible": True,
            "rollback_plan": rollback,
            "estimated_risk": risk,
        }
    )


def validate_trace(spec: ScenarioSpec, trace: dict[str, Any]) -> dict[str, bool]:
    stages = {item["stage"]: item["metrics"] for item in trace["stages"]}
    checks = {
        "trace_passed": trace["passed"] is True,
        "cleanup_verified": trace["cleanup_verified"] is True,
        "post_action_user_plane_available": stages["post-action"]["packet_loss_pct"] == 0.0,
        "final_user_plane_available": stages["final"]["packet_loss_pct"] == 0.0,
        "final_upf_running": stages["final"]["upf_process_running"] == 1.0,
        "final_cpu_stress_absent": stages["final"]["stress_workers_count"] == 0.0,
    }
    severity = float(next(iter(spec.fault_parameters.values())))
    if spec.fault_family == "packet_impairment":
        checks.update(
            {
                "fault_control_matches_severity": (
                    stages["fault"]["configured_packet_loss_pct"] == severity
                ),
                "rollback_control_matches_severity": (
                    stages["rollback"]["configured_packet_loss_pct"] == severity
                ),
                "fault_observed": (
                    stages["fault"]["packet_loss_pct"]
                    > stages["baseline"]["packet_loss_pct"]
                ),
                "rollback_observed": (
                    stages["rollback"]["packet_loss_pct"]
                    > stages["post-action"]["packet_loss_pct"]
                ),
            }
        )
    elif spec.fault_family == "network_function_interruption":
        checks.update(
            {
                "fault_observed": stages["fault"]["upf_process_running"] == 0.0,
                "rollback_observed": stages["rollback"]["upf_process_running"] == 0.0,
            }
        )
    elif spec.fault_family == "cpu_saturation":
        checks.update(
            {
                "fault_observed": stages["fault"]["stress_workers_count"] == severity,
                "rollback_observed": stages["rollback"]["stress_workers_count"] == severity,
            }
        )
    return checks


def expand_matrix(config: dict[str, Any]) -> list[ScenarioSpec]:
    specs: list[ScenarioSpec] = []
    for family in config["families"]:
        for severity in family["severities"]:
            for seed in family["seeds"]:
                parameter = family["severity_parameter"]
                scenario_id = f"{family['fault_family']}-{parameter}-{severity}-seed-{seed}"
                specs.append(
                    ScenarioSpec.from_dict(
                        {
                            "scenario_id": scenario_id,
                            "environment": config["environment"],
                            "seed": seed,
                            "fault_family": family["fault_family"],
                            "fault_parameters": {parameter: severity},
                            "action_kind": family["action_kind"],
                            "target": family["target"],
                            "rollback_required": True,
                        }
                    )
                )
    return specs


def main() -> int:
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ-scenario-matrix-v0")
    output = ROOT / "evidence" / "scenarios" / run_id
    output.mkdir(parents=True, exist_ok=False)
    config = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    specs = expand_matrix(config)
    approval = {
        "approval_id": hashlib.sha256(
            (AUTHORIZATION_TEXT + config["matrix_id"]).encode("utf-8")
        ).hexdigest(),
        "approval_status": "approved",
        "approved_by": "user",
        "approval_type": "user-standing-sandbox-authorization",
        "environment": "sandbox",
        "matrix_id": config["matrix_id"],
        "scenario_ids": [spec.scenario_id for spec in specs],
        "authorized_faults": [
            "UE-tunnel packet impairment",
            "Open5GS UPF process suspension",
            "container-local pinned CPU load",
        ],
        "authorization_text": AUTHORIZATION_TEXT,
        "authorization_text_sha256": hashlib.sha256(
            AUTHORIZATION_TEXT.encode("utf-8")
        ).hexdigest(),
        "source_thread_id": "01a02a0d-ff7c-74e0-8a33-e92916f53731",
        "recorded_at": utc_now(),
        "exclusions": ["live actuation", "hardware", "operator systems", "external systems"],
    }
    (output / "approval.json").write_text(
        json.dumps(approval, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    command_log: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    policy = SafetyPolicy.from_path(ROOT / "config" / "actions.json")
    if policy.allow_live or not policy.config.get("require_human_approval"):
        raise RuntimeError("fail-closed policy preflight failed")

    for index, spec in enumerate(specs, start=1):
        print(f"[{index}/{len(specs)}] {spec.scenario_id}", flush=True)
        scenario_dir = output / "scenarios" / spec.scenario_id
        scenario_dir.mkdir(parents=True, exist_ok=False)
        action = action_for(spec)
        evaluation = policy.evaluate_action(
            action,
            environment="sandbox",
            decision_source="deterministic-runbook",
        )
        (scenario_dir / "safety-evaluation.json").write_text(
            json.dumps(evaluation.to_dict(), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        if evaluation.decision is not Decision.REQUIRE_APPROVAL:
            raise RuntimeError(f"scenario safety rejection: {spec.scenario_id}")
        backend = MatrixBackend(spec, scenario_dir, command_log)
        try:
            trace = ScenarioRunner(backend).run(spec, approval).to_dict()
            trace["control_events"] = backend.control_events
            trace["action"] = action.to_dict()
            trace["safety_evaluation"] = evaluation.to_dict()
            trace["claim_boundaries"] = {
                "intervention": "sandbox-measured",
                "radio_access": "simulated",
                "hardware": "not measured",
                "operator_validation": "not performed",
                "model_scores": "not applicable; deterministic runbook",
            }
            trace["checks"] = validate_trace(spec, trace)
            trace["passed"] = all(trace["checks"].values())
        except Exception as exc:
            trace = {
                "scenario": spec.__dict__,
                "passed": False,
                "error": f"{type(exc).__name__}: {exc}",
                "control_events": backend.control_events,
                "claim_boundaries": {
                    "intervention": "incomplete",
                    "radio_access": "simulated",
                    "hardware": "not measured",
                    "operator_validation": "not performed",
                },
            }
        (scenario_dir / "trace.json").write_text(
            json.dumps(trace, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        results.append(trace)

    (output / "commands.jsonl").write_text(
        "".join(json.dumps(item, sort_keys=True) + "\n" for item in command_log),
        encoding="utf-8",
    )
    family_counts: dict[str, dict[str, int]] = {}
    for result in results:
        family = result["scenario"]["fault_family"]
        counts = family_counts.setdefault(family, {"total": 0, "passed": 0})
        counts["total"] += 1
        counts["passed"] += int(result["passed"])
    passed = len(results) == len(specs) and all(result["passed"] for result in results)
    summary = {
        "schema_version": 1,
        "run_id": run_id,
        "matrix_id": config["matrix_id"],
        "started_at": started.isoformat(),
        "completed_at": utc_now(),
        "passed": passed,
        "scenario_count": len(results),
        "family_counts": family_counts,
        "seeds": sorted({spec.seed for spec in specs}),
        "evidence_label": "sandbox-measured" if passed else "simulated",
        "claim_boundary": (
            "Measured isolated software-sandbox interventions with simulated UERANSIM "
            "radio; no hardware measurement, operator validation, or model result."
        ),
        "matrix_configuration_sha256": sha256(MATRIX_PATH),
        "policy_sha256": sha256(ROOT / "config" / "actions.json"),
        "scenario_runner_sha256": sha256(ROOT / "src" / "safetwin5g" / "scenario.py"),
        "execution_script_sha256": sha256(Path(__file__)),
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
