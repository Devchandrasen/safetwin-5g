"""Execute the amended Phase 7 named-action sandbox campaign."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.contracts import ActionProposal  # noqa: E402
from safetwin5g.phase6 import OBSERVE_ONLY_ACTIONS, utc_now  # noqa: E402
from safetwin5g.phase7_design import (  # noqa: E402
    expand_phase7_design,
    load_phase7_design,
)
from safetwin5g.phase7_runner import Phase7UnitRunner  # noqa: E402
from safetwin5g.safety import Decision, SafetyPolicy  # noqa: E402
from sandbox.run_phase6 import (  # noqa: E402
    CommandRecorder,
    DockerPhase6Backend,
    preflight,
    sha256,
)


DESIGN_PATH = ROOT / "config" / "experiments" / "phase7-brace-v2a.json"
POLICY_PATH = ROOT / "config" / "actions.json"
AUTHORIZATION_BASIS = (
    "The user directed SafeTwin-5G to continue all locally executable work with "
    "safe defaults while preserving mandatory approval, rollback, and the ban on "
    "unrestricted live actuation. This approval is scoped only to the frozen "
    "Phase 7 isolated software-sandbox experiment."
)


class DockerPhase7Backend(DockerPhase6Backend):
    def apply_action(self, unit: dict[str, Any]) -> None:
        action_id = unit["action_id"]
        if action_id == "observe_only":
            self.control_events.append(
                {"event": "observe_only", "unit_id": unit["unit_id"], "at": utc_now()}
            )
        elif action_id == "clear_packet_impairment":
            self._clear_packet_impairment(unit, "action-clear-packet-impairment")
        elif action_id == "resume_upf":
            self._resume_upf(unit, "action-resume-upf")
        elif action_id == "stop_cpu_stress":
            self._stop_stress(unit, "action-stop-cpu-stress")
        elif action_id == "apply_packet_impairment_25":
            self._set_packet_loss(
                unit,
                float(unit["action_parameters"]["loss_pct"]),
                "action-apply-packet-impairment-25",
            )
        else:
            raise ValueError(f"unsupported named action: {action_id}")
        time.sleep(0.5)


def action_proposal(unit: dict[str, Any]) -> ActionProposal | None:
    action_id = unit["action_id"]
    if action_id == "observe_only":
        return None
    if action_id == "clear_packet_impairment":
        payload = {
            "kind": "network_impairment_clear",
            "target": "safetwin5g-ue/uesimtun0",
            "target_type": "ue_tunnel",
            "parameters": {"qdisc": "fq_codel"},
            "rollback_plan": "Cleanup restores fq_codel and verifies zero configured loss.",
            "estimated_risk": 0.05,
        }
    elif action_id == "resume_upf":
        payload = {
            "kind": "nf_process_resume",
            "target": "safetwin5g-open5gs/open5gs-upfd",
            "target_type": "upf",
            "parameters": {"signal": "CONT"},
            "rollback_plan": "Cleanup sends CONT and verifies the UPF process is running.",
            "estimated_risk": 0.15,
        }
    elif action_id == "stop_cpu_stress":
        payload = {
            "kind": "cpu_stress_stop",
            "target": "safetwin5g-open5gs",
            "target_type": "core_container",
            "parameters": {"process": "yes", "signal": "TERM"},
            "rollback_plan": "Cleanup terminates experiment-owned stress workers and verifies zero remain.",
            "estimated_risk": 0.10,
        }
    elif action_id == "apply_packet_impairment_25":
        payload = {
            "kind": "network_impairment_apply",
            "target": "safetwin5g-ue/uesimtun0",
            "target_type": "ue_tunnel",
            "parameters": {"loss_pct": 25.0},
            "rollback_plan": "Cleanup restores fq_codel and verifies zero configured loss.",
            "estimated_risk": 0.25,
        }
    else:
        raise ValueError(f"unsupported named action: {action_id}")
    payload["reversible"] = True
    return ActionProposal.from_dict(payload)


def build_approval(design: dict[str, Any], units: list[dict[str, Any]]) -> dict[str, Any]:
    approval_id = hashlib.sha256(
        (AUTHORIZATION_BASIS + design["experiment_id"]).encode("utf-8")
    ).hexdigest()
    return {
        "approval_id": approval_id,
        "approval_status": "approved",
        "approved_by": "user",
        "approval_type": "experiment-scoped-standing-sandbox-authorization",
        "environment": "sandbox",
        "experiment_id": design["experiment_id"],
        "unit_ids": [unit["unit_id"] for unit in units],
        "authorized_action_ids": [
            action["action_id"]
            for action in design["action_portfolio"]
            if action["mutates"]
        ],
        "authorization_basis": AUTHORIZATION_BASIS,
        "authorization_basis_sha256": hashlib.sha256(
            AUTHORIZATION_BASIS.encode("utf-8")
        ).hexdigest(),
        "recorded_at": utc_now(),
        "exclusions": [
            "live actuation",
            "private-5G hardware",
            "operator systems",
            "external systems",
            "publication submission",
        ],
    }


def select_pilot_blocks(
    units: list[dict[str, Any]], block_count: int
) -> list[dict[str, Any]]:
    if block_count < 1:
        raise ValueError("pilot block count must be positive")
    selected: list[str] = []
    for unit in units:
        block_id = unit["assignment_block_id"]
        if block_id not in selected:
            selected.append(block_id)
        if len(selected) == block_count:
            break
    selected_set = set(selected)
    return [unit for unit in units if unit["assignment_block_id"] in selected_set]


def validate_policy(
    units: list[dict[str, Any]], policy: SafetyPolicy
) -> None:
    if policy.allow_live or not policy.config.get("require_human_approval"):
        raise RuntimeError("fail-closed policy preflight failed")
    for unit in units:
        proposal = action_proposal(unit)
        if proposal is None:
            continue
        evaluation = policy.evaluate_action(
            proposal,
            environment="sandbox",
            decision_source="preregistered-experiment",
        )
        if evaluation.decision is not Decision.REQUIRE_APPROVAL:
            raise RuntimeError(f"action policy rejected {unit['unit_id']}: {evaluation}")


def _existing_results(output: Path) -> dict[str, dict[str, Any]]:
    results = {}
    units_dir = output / "units"
    if not units_dir.exists():
        return results
    for path in units_dir.glob("*.json"):
        trace = json.loads(path.read_text(encoding="utf-8"))
        results[trace["unit"]["unit_id"]] = trace
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pilot-blocks", type=int)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--resume", type=Path)
    args = parser.parse_args()
    if args.pilot_blocks is not None and args.resume is not None:
        parser.error("--pilot-blocks and --resume cannot be combined")

    design = load_phase7_design(DESIGN_PATH)
    all_units = expand_phase7_design(design)
    units = (
        select_pilot_blocks(all_units, args.pilot_blocks)
        if args.pilot_blocks is not None
        else all_units
    )
    policy = SafetyPolicy.from_path(POLICY_PATH)
    validate_policy(units, policy)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "experiment_id": design["experiment_id"],
                    "selected_unit_count": len(units),
                    "selected_block_count": len(
                        {unit["assignment_block_id"] for unit in units}
                    ),
                    "full_design_unit_count": len(all_units),
                    "full_design_block_count": len(
                        {unit["assignment_block_id"] for unit in all_units}
                    ),
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
    if args.resume is not None:
        output = args.resume if args.resume.is_absolute() else ROOT / args.resume
        if not output.is_dir():
            raise FileNotFoundError(output)
        stored_units = [
            json.loads(line)
            for line in (output / "design-units.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        units = stored_units
        approval = json.loads((output / "approval.json").read_text(encoding="utf-8"))
        if approval["experiment_id"] != design["experiment_id"]:
            raise RuntimeError("resume experiment id differs from active design")
        if (output / "manifest.json").exists():
            prior_manifest = json.loads(
                (output / "manifest.json").read_text(encoding="utf-8")
            )
            if prior_manifest.get("passed"):
                raise RuntimeError("refusing to resume an already-passed campaign")
    else:
        suffix = (
            "phase7-campaign-v2a"
            if len(units) == len(all_units)
            else "phase7-pilot-v2a"
        )
        run_id = started.strftime("%Y%m%dT%H%M%SZ-") + suffix
        output = ROOT / "evidence" / "scenarios" / run_id
        output.mkdir(parents=True, exist_ok=False)
        approval = build_approval(design, units)
        (output / "approval.json").write_text(
            json.dumps(approval, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (output / "design-units.jsonl").write_text(
            "".join(json.dumps(unit, sort_keys=True) + "\n" for unit in units),
            encoding="utf-8",
        )

    recorder = CommandRecorder(output / "commands.jsonl")
    environment = preflight(recorder)
    (output / "environment.json").write_text(
        json.dumps(environment, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    results_by_id = _existing_results(output)
    aborted_for_cleanup = any(
        not trace.get("cleanup_verified", False) for trace in results_by_id.values()
    )
    if aborted_for_cleanup:
        raise RuntimeError("existing run contains an unverified cleanup; resume is blocked")

    for index, unit in enumerate(units, start=1):
        if unit["unit_id"] in results_by_id:
            print(f"[{index}/{len(units)}] SKIP {unit['unit_id']}", flush=True)
            continue
        print(f"[{index}/{len(units)}] {unit['unit_id']}", flush=True)
        control_events: list[dict[str, Any]] = []
        backend = DockerPhase7Backend(recorder, design, control_events)
        proposal = action_proposal(unit)
        if proposal is None:
            evaluation = {
                "decision": "observe-only",
                "reasons": ["assigned named action has no sandbox mutation"],
                "policy_version": policy.policy_version,
            }
        else:
            evaluation = policy.evaluate_action(
                proposal,
                environment="sandbox",
                decision_source="preregistered-experiment",
            ).to_dict()
        trace = Phase7UnitRunner(
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
            "model_result": "not applicable during randomized data collection",
        }
        trace_path = output / "units" / f"{unit['unit_id']}.json"
        trace_path.parent.mkdir(parents=True, exist_ok=True)
        trace_path.write_text(
            json.dumps(trace, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        results_by_id[unit["unit_id"]] = trace
        if not trace["cleanup_verified"]:
            aborted_for_cleanup = True
            print("ABORT: cleanup could not be verified", flush=True)
            break

    results = [results_by_id[unit["unit_id"]] for unit in units if unit["unit_id"] in results_by_id]
    passed = (
        not aborted_for_cleanup
        and len(results) == len(units)
        and all(result["passed"] for result in results)
    )
    run_id = output.name
    split_counts = {
        split: sum(result["unit"]["split"] == split for result in results)
        for split in ("train", "calibration", "test", "ood")
    }
    summary = {
        "schema_version": 1,
        "run_id": run_id,
        "artifact_type": (
            "full-preregistered-campaign"
            if len(units) == len(all_units)
            else "complete-block-runner-pilot"
        ),
        "experiment_id": design["experiment_id"],
        "started_at": started.isoformat(),
        "completed_at": utc_now(),
        "passed": passed,
        "planned_unit_count": len(units),
        "planned_block_count": len({unit["assignment_block_id"] for unit in units}),
        "completed_unit_count": len(results),
        "completed_block_count": len(
            {result["unit"]["assignment_block_id"] for result in results}
        ),
        "passed_unit_count": sum(result["passed"] for result in results),
        "split_counts": split_counts,
        "aborted_for_cleanup": aborted_for_cleanup,
        "experimental_mutation_count": sum(
            result["unit"]["mutates"] for result in results
        ),
        "model_selected_action_count": 0,
        "evidence_label": "sandbox-measured" if results else "fixture",
        "radio_evidence_label": "simulated" if results else None,
        "hardware_evidence_label": None,
        "operator_validation": False,
        "design_sha256": sha256(DESIGN_PATH),
        "policy_sha256": sha256(POLICY_PATH),
        "runner_sha256": sha256(Path(__file__)),
        "phase7_module_sha256": sha256(
            ROOT / "src" / "safetwin5g" / "phase7_runner.py"
        ),
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
