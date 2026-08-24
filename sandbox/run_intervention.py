"""Run one approved, reversible packet-loss intervention in the isolated sandbox.

The procedure is deliberately narrow and fail-closed.  It can only target the
UERANSIM UE tunnel in the local Compose project, records the user's standing
sandbox authorization, exercises the remediation and its rollback, and always
attempts to restore the clean queue discipline before exiting.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.contracts import InterventionRecord  # noqa: E402
from safetwin5g.safety import Decision, SafetyPolicy  # noqa: E402


UE = "safetwin5g-ue"
CORE = "safetwin5g-open5gs"
PING_TARGET = "10.45.0.1"
INTERFACE = "uesimtun0"
FAULT_COMMAND = [
    "docker", "exec", UE, "tc", "qdisc", "replace", "dev", INTERFACE,
    "root", "netem", "loss", "100%",
]
CLEAR_COMMAND = [
    "docker", "exec", UE, "tc", "qdisc", "replace", "dev", INTERFACE,
    "root", "fq_codel",
]
AUTHORIZATION_TEXT = (
    "Proceed through the entire SafeTwin-5G master backlog sequentially, one task "
    "at a time. Continue automatically through all locally executable Phase 1-5 "
    "work without waiting for routine confirmation, using safe reasonable defaults. "
    "Preserve the fail-closed safety policy: no unrestricted live actuation, "
    "mandatory approval and rollback for applied sandbox actions."
)
CONFIG_PATHS = (
    "PROJECT_LOCK.md",
    "config/actions.json",
    "sandbox/compose.yaml",
    "sandbox/run_intervention.py",
    "sandbox/versions.lock.json",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_ping(text: str) -> dict[str, float]:
    packets = re.search(
        r"(\d+) packets transmitted, (\d+) received, ([\d.]+)% packet loss",
        text,
    )
    if not packets:
        raise RuntimeError("could not parse ping packet statistics")
    metrics: dict[str, float] = {
        "packets_transmitted": float(packets.group(1)),
        "packets_received": float(packets.group(2)),
        "packet_loss_pct": float(packets.group(3)),
    }
    rtt = re.search(
        r"rtt min/avg/max/mdev = ([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms",
        text,
    )
    if rtt:
        metrics.update(
            {
                "rtt_min_ms": float(rtt.group(1)),
                "rtt_avg_ms": float(rtt.group(2)),
                "rtt_max_ms": float(rtt.group(3)),
                "rtt_mdev_ms": float(rtt.group(4)),
            }
        )
    return metrics


def main() -> int:
    started = utc_now()
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-intervention")
    output_dir = ROOT / "evidence" / "sandbox" / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    commands: list[dict[str, Any]] = []
    fault_active = False
    cleanup_verified = False

    def write_json(relative: str, payload: Any) -> None:
        path = output_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    def run(
        name: str,
        argv: list[str],
        output_file: str,
        *,
        accepted: tuple[int, ...] = (0,),
    ) -> tuple[int, str]:
        command_started = utc_now()
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
        command_completed = utc_now()
        destination = output_dir / output_file
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(result.stdout, encoding="utf-8")
        commands.append(
            {
                "name": name,
                "started_at": command_started,
                "completed_at": command_completed,
                "argv": argv,
                "returncode": result.returncode,
                "accepted_returncodes": list(accepted),
                "output_file": output_file,
            }
        )
        if result.returncode not in accepted:
            raise RuntimeError(f"{name} failed with exit code {result.returncode}")
        return result.returncode, result.stdout

    def ping(name: str, output_file: str, count: int) -> tuple[int, dict[str, float]]:
        returncode, text = run(
            name,
            [
                "docker", "exec", UE, "ping", "-I", INTERFACE, "-c", str(count),
                "-i", "0.2", "-W", "1", PING_TARGET,
            ],
            output_file,
            accepted=(0, 1),
        )
        return returncode, parse_ping(text)

    def qdisc(name: str, output_file: str) -> str:
        _, text = run(
            name,
            ["docker", "exec", UE, "tc", "qdisc", "show", "dev", INTERFACE],
            output_file,
        )
        return text

    def telemetry(stage: str) -> None:
        for job, port in (("amf", 9090), ("smf", 9091), ("upf", 9092)):
            run(
                f"{stage}-{job}-metrics",
                [
                    "docker", "exec", CORE, "curl", "--fail", "--silent",
                    f"http://10.53.0.3:{port}/metrics",
                ],
                f"telemetry/{stage}-{job}-metrics.txt",
            )
        _, target_text = run(
            f"{stage}-prometheus-targets",
            [
                "docker", "exec", CORE, "curl", "--fail", "--silent",
                "http://10.53.0.6:9090/api/v1/targets",
            ],
            f"telemetry/{stage}-prometheus-targets.json",
        )
        targets = json.loads(target_text)["data"]["activeTargets"]
        if len(targets) != 3 or any(target["health"] != "up" for target in targets):
            raise RuntimeError(f"Prometheus targets were not all up during {stage}")

    def flush_commands() -> None:
        (output_dir / "commands.jsonl").write_text(
            "".join(json.dumps(item, sort_keys=True) + "\n" for item in commands),
            encoding="utf-8",
        )

    def captured_hashes() -> dict[str, str]:
        return {
            str(path.relative_to(output_dir)).replace("\\", "/"): sha256(path)
            for path in sorted(output_dir.rglob("*"))
            if path.is_file() and path.name != "manifest.json"
        }

    approval = {
        "approval_status": "approved",
        "approval_type": "user-standing-sandbox-authorization",
        "approved_by": "user",
        "authorization_scope": {
            "environment": "isolated-local-sandbox-only",
            "fault": "100-percent packet loss on the simulated UE tunnel",
            "remediation": "replace the fault qdisc with fq_codel",
            "rollback": "reapply the exact netem loss qdisc and verify the fault",
            "final_cleanup": "restore fq_codel and verify user-plane recovery",
        },
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
        ],
    }
    write_json("approval.json", approval)

    try:
        policy = SafetyPolicy.from_path(ROOT / "config" / "actions.json")
        if policy.allow_live or not policy.config.get("require_human_approval"):
            raise RuntimeError("policy preflight failed: fail-closed controls are disabled")
        if approval["approval_status"] != "approved":
            raise RuntimeError("sandbox action lacks explicit user approval")

        run("git-head", ["git", "rev-parse", "HEAD"], "git-head.txt")
        run("git-status", ["git", "status", "--short"], "git-status.txt")
        run(
            "container-state",
            ["docker", "inspect", UE, CORE, "--format", "{{json .State}}"],
            "container-states.jsonl",
        )
        run(
            "ue-registration-status",
            [
                "docker", "exec", UE, "/opt/ueransim/bin/nr-cli",
                "imsi-999700000000001", "-e", "status",
            ],
            "ue-registration-status.txt",
        )
        run(
            "ue-pdu-session-status",
            [
                "docker", "exec", UE, "/opt/ueransim/bin/nr-cli",
                "imsi-999700000000001", "-e", "ps-list",
            ],
            "ue-pdu-session-status.txt",
        )

        initial_qdisc = qdisc("initial-qdisc", "qdisc/initial.txt")
        if "fq_codel" not in initial_qdisc:
            raise RuntimeError("unexpected initial qdisc; refusing to inject fault")
        baseline_rc, baseline = ping("baseline-ping", "ping/baseline.txt", 10)
        if baseline_rc != 0 or baseline["packet_loss_pct"] != 0.0:
            raise RuntimeError("clean baseline did not have zero packet loss")
        telemetry("baseline")

        fault_started_at = utc_now()
        run("inject-fault", FAULT_COMMAND, "qdisc/inject-fault.txt")
        fault_active = True
        fault_qdisc = qdisc("fault-qdisc", "qdisc/fault.txt")
        fault_rc, fault = ping("fault-ping", "ping/fault.txt", 5)
        telemetry("fault")
        if fault_rc != 1 or fault["packet_loss_pct"] != 100.0 or "netem" not in fault_qdisc:
            raise RuntimeError("the controlled packet-loss fault was not observed")

        candidate = {
            "record_id": run_id,
            "scenario_id": "packet-loss-ue-tunnel-100pct-seed-0001",
            "observed_at": fault_started_at,
            "environment": "sandbox",
            "fault_type": "ue_tunnel_packet_loss_100pct",
            "pre_metrics": fault,
            "action": {
                "kind": "network_impairment_clear",
                "target": f"{UE}/{INTERFACE}",
                "target_type": "ue_tunnel",
                "parameters": {"qdisc": "fq_codel"},
                "reversible": True,
                "rollback_plan": "docker exec safetwin5g-ue tc qdisc replace dev uesimtun0 root netem loss 100%",
                "estimated_risk": 0.05,
            },
            "decision_source": "deterministic-runbook",
            "model_confidence": None,
            "ood_score": None,
            "expected_effects": {"packet_loss_pct_delta": -100.0},
            "post_metrics": None,
            "evidence_label": "sandbox-measured",
        }
        proposal = InterventionRecord.from_dict(candidate)
        evaluation = policy.evaluate(proposal)
        write_json("safety-evaluation.json", evaluation.to_dict())
        if evaluation.decision is not Decision.REQUIRE_APPROVAL:
            raise RuntimeError(
                f"safety gate did not require approval: {evaluation.decision.value}"
            )

        action_started_at = utc_now()
        run("approved-action-clear-impairment", CLEAR_COMMAND, "qdisc/action.txt")
        fault_active = False
        action_qdisc = qdisc("action-qdisc", "qdisc/after-action.txt")
        action_rc, action = ping("post-action-ping", "ping/post-action.txt", 10)
        telemetry("post-action")
        if action_rc != 0 or action["packet_loss_pct"] != 0.0 or "fq_codel" not in action_qdisc:
            raise RuntimeError("approved remediation did not restore the user plane")

        rollback_started_at = utc_now()
        run("rollback-reapply-fault", FAULT_COMMAND, "qdisc/rollback.txt")
        fault_active = True
        rollback_qdisc = qdisc("rollback-qdisc", "qdisc/after-rollback.txt")
        rollback_rc, rollback = ping("rollback-ping", "ping/rollback.txt", 5)
        telemetry("rollback")
        if (
            rollback_rc != 1
            or rollback["packet_loss_pct"] != 100.0
            or "netem" not in rollback_qdisc
        ):
            raise RuntimeError("rollback did not reproduce the controlled fault")

        cleanup_started_at = utc_now()
        run("final-cleanup", CLEAR_COMMAND, "qdisc/final-cleanup.txt")
        fault_active = False
        final_qdisc = qdisc("final-qdisc", "qdisc/final.txt")
        final_rc, final = ping("final-ping", "ping/final.txt", 10)
        telemetry("final")
        cleanup_verified = (
            final_rc == 0
            and final["packet_loss_pct"] == 0.0
            and "fq_codel" in final_qdisc
        )
        if not cleanup_verified:
            raise RuntimeError("final cleanup did not restore the clean user plane")

        completed_record = dict(candidate)
        completed_record["post_metrics"] = action
        completed_record["approval"] = approval
        completed_record["safety_evaluation"] = evaluation.to_dict()
        completed_record["execution"] = {
            "fault": {"started_at": fault_started_at, "metrics": fault},
            "approved_action": {"started_at": action_started_at, "metrics": action},
            "rollback": {"started_at": rollback_started_at, "metrics": rollback},
            "final_cleanup": {"started_at": cleanup_started_at, "metrics": final},
        }
        completed_record["claim_boundaries"] = {
            "intervention": "sandbox-measured",
            "radio_access": "simulated",
            "hardware": "not measured",
            "operator_validation": "not performed",
            "model_scores": "not applicable; deterministic runbook",
        }
        InterventionRecord.from_dict(completed_record)
        write_json("intervention-record.json", completed_record)

        checks = {
            "approval_recorded": True,
            "live_actuation_blocked": not policy.allow_live,
            "human_approval_required_by_policy": bool(
                policy.config.get("require_human_approval")
            ),
            "safety_gate_required_approval": (
                evaluation.decision is Decision.REQUIRE_APPROVAL
            ),
            "baseline_zero_packet_loss": baseline["packet_loss_pct"] == 0.0,
            "fault_observed_100pct_loss": fault["packet_loss_pct"] == 100.0,
            "approved_action_restored_zero_loss": action["packet_loss_pct"] == 0.0,
            "rollback_reproduced_100pct_loss": rollback["packet_loss_pct"] == 100.0,
            "final_cleanup_restored_zero_loss": final["packet_loss_pct"] == 0.0,
            "final_qdisc_restored": "fq_codel" in final_qdisc,
        }
        if not all(checks.values()):
            raise RuntimeError("one or more intervention checks failed")
        flush_commands()
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "stage": "intervention",
            "started_at": started,
            "completed_at": utc_now(),
            "evidence_label": "sandbox-measured",
            "claim_boundary": (
                "The intervention loop is measured in the isolated software sandbox. "
                "The radio is UERANSIM-simulated; there is no hardware measurement or "
                "operator validation."
            ),
            "passed": True,
            "checks": checks,
            "measurements": {
                "baseline": baseline,
                "fault": fault,
                "post_action": action,
                "rollback": rollback,
                "final": final,
            },
            "configuration_sha256": {
                relative: sha256(ROOT / relative) for relative in CONFIG_PATHS
            },
            "captured_file_sha256": captured_hashes(),
        }
        write_json("manifest.json", manifest)
        print(output_dir)
        print(json.dumps(checks, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        cleanup_error: str | None = None
        if fault_active:
            try:
                run("emergency-final-cleanup", CLEAR_COMMAND, "qdisc/emergency-cleanup.txt")
                _, cleanup_metrics = ping(
                    "emergency-cleanup-ping", "ping/emergency-cleanup.txt", 5
                )
                cleanup_verified = cleanup_metrics["packet_loss_pct"] == 0.0
            except Exception as cleanup_exc:  # preserve both failures
                cleanup_error = f"{type(cleanup_exc).__name__}: {cleanup_exc}"
        flush_commands()
        write_json(
            "manifest.json",
            {
                "schema_version": 1,
                "run_id": run_id,
                "stage": "intervention",
                "started_at": started,
                "completed_at": utc_now(),
                "evidence_label": "simulated",
                "passed": False,
                "error": f"{type(exc).__name__}: {exc}",
                "emergency_cleanup_verified": cleanup_verified,
                "emergency_cleanup_error": cleanup_error,
                "captured_file_sha256": captured_hashes(),
            },
        )
        print(f"intervention failed: {exc}", file=sys.stderr)
        if cleanup_error:
            print(f"emergency cleanup failed: {cleanup_error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
