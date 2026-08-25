"""Build the public-safe Phase 7 named-action intervention dataset v2a."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from safetwin5g.dataset_v1 import sha256, verify_manifest


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATASET_VERSION = "safetwin5g-named-actions-v2a"
EXPERIMENT_ID = "safetwin5g-phase7-brace-v2a"
REQUIRED_STAGES = ("baseline", "fault", "post_action", "recovery")
ACTION_IDS = (
    "observe_only",
    "clear_packet_impairment",
    "resume_upf",
    "stop_cpu_stress",
    "apply_packet_impairment_25",
)
MUTATING_ACTION_IDS = tuple(action for action in ACTION_IDS if action != "observe_only")
EXPECTED_SPLIT_UNITS = {"train": 140, "calibration": 105, "test": 350, "ood": 80}
EXPECTED_SPLIT_BLOCKS = {"train": 28, "calibration": 21, "test": 70, "ood": 16}
EXPECTED_METRICS = {
    "packets_transmitted",
    "packets_received",
    "packet_loss_pct",
    "rtt_min_ms",
    "rtt_avg_ms",
    "rtt_max_ms",
    "rtt_mdev_ms",
    "core_container_cpu_pct",
    "stress_workers_count",
    "upf_process_running",
    "prometheus_targets_up_count",
    "configured_packet_loss_pct",
}
TARGETS = {
    "packet_impairment": ("packet_loss_pct", "lower-is-better"),
    "network_function_interruption": ("upf_process_running", "higher-is-better"),
    "cpu_saturation": ("stress_workers_count", "lower-is-better"),
    "no_fault": ("packet_loss_pct", "lower-is-better"),
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp lacks timezone: {value}")
    return parsed


def _mean_metric(trace: dict[str, Any], stage: str, metric: str) -> float:
    values = [
        sample["metrics"].get(metric)
        for sample in trace["windows"][stage]["samples"]
    ]
    measured = [float(value) for value in values if value is not None]
    if not measured:
        raise ValueError(
            f"{trace['unit']['unit_id']} has no {metric} measurements in {stage}"
        )
    return sum(measured) / len(measured)


def _violates_user_plane(sample: dict[str, Any]) -> bool:
    metrics = sample["metrics"]
    return (
        float(metrics["packet_loss_pct"]) > 1.0
        or float(metrics["upf_process_running"]) < 1.0
    )


def _user_plane_burden(trace: dict[str, Any], stage: str) -> float:
    """Return the frozen 0--100 service burden used for all action contrasts."""

    packet_loss = _mean_metric(trace, stage, "packet_loss_pct")
    upf_down = 100.0 * (1.0 - _mean_metric(trace, stage, "upf_process_running"))
    return max(packet_loss, upf_down)


def _action_time(
    trace: dict[str, Any], commands: dict[str, list[dict[str, Any]]]
) -> datetime:
    unit_id = trace["unit"]["unit_id"]
    action_commands = [
        command
        for command in commands.get(unit_id, [])
        if command["name"].startswith("action-")
    ]
    if action_commands:
        return _iso(action_commands[0]["started_at"])
    events = [
        event
        for event in trace.get("control_events", [])
        if event.get("event") == "observe_only"
    ]
    if len(events) != 1:
        raise ValueError(f"{unit_id} lacks exactly one assigned-action timestamp")
    return _iso(events[0]["at"])


def _sla_endpoints(trace: dict[str, Any], action_at: datetime) -> dict[str, Any]:
    post_samples = trace["windows"]["post_action"]["samples"]
    recovery_samples = trace["windows"]["recovery"]["samples"]
    ordered = post_samples + recovery_samples
    states = [_violates_user_plane(sample) for sample in ordered]
    timestamps = [_iso(sample["observed_at"]) for sample in ordered]
    violation_duration = 0.0
    previous_time = action_at
    previous_state = states[0]
    for timestamp, state in zip(timestamps, states, strict=True):
        if previous_state:
            violation_duration += max(0.0, (timestamp - previous_time).total_seconds())
        previous_time = timestamp
        previous_state = state

    fault_active = _violates_user_plane(trace["windows"]["fault"]["samples"][-1])
    trigger_index = 0 if fault_active else next(
        (index for index, state in enumerate(states) if state), -1
    )
    if not fault_active and trigger_index < 0:
        mttr = 0.0
        status = "not-triggered"
    else:
        clean_index = next(
            (index for index in range(max(trigger_index, 0), len(states)) if not states[index]),
            None,
        )
        if clean_index is None:
            mttr = None
            status = "right-censored"
        else:
            mttr = max(0.0, (timestamps[clean_index] - action_at).total_seconds())
            status = "observed"
    return {
        "post_action_sla_violation_samples": sum(states[: len(post_samples)]),
        "post_action_sla_sample_count": len(post_samples),
        "sla_violation_duration_seconds": violation_duration,
        "mttr_seconds": mttr,
        "mttr_status": status,
    }


def _record_from_trace(
    trace: dict[str, Any], commands: dict[str, list[dict[str, Any]]]
) -> dict[str, Any]:
    if trace.get("passed") is not True or trace.get("cleanup_verified") is not True:
        raise ValueError(f"failed or unclean unit cannot enter v2a: {trace.get('unit', {})}")
    unit = trace["unit"]
    if unit["action_id"] not in ACTION_IDS:
        raise ValueError(f"unknown Phase 7 action: {unit['action_id']}")
    target_metric, target_direction = TARGETS[unit["fault_family"]]
    action_at = _action_time(trace, commands)
    fault_target = _mean_metric(trace, "fault", target_metric)
    post_target = _mean_metric(trace, "post_action", target_metric)
    benefit_sign = -1.0 if target_direction == "lower-is-better" else 1.0
    proposal = trace.get("action_proposal")
    record = {
        "schema_version": 2,
        "dataset_version": DATASET_VERSION,
        "unit_id": unit["unit_id"],
        "assignment_block_id": unit["assignment_block_id"],
        "split": unit["split"],
        "fault_family": unit["fault_family"],
        "severity_name": unit["severity_name"],
        "severity_value": float(unit["severity_value"]),
        "seed": int(unit["seed"]),
        "workload": unit["workload"],
        "action_id": unit["action_id"],
        "action_kind": unit["action_kind"],
        "action_applied": bool(unit["mutates"]),
        "action_at": action_at.isoformat(),
        "target_kpi": target_metric,
        "target_direction": target_direction,
        "fault_target_mean": fault_target,
        "post_action_target_mean": post_target,
        "within_unit_target_change": benefit_sign * (post_target - fault_target),
        "post_action_user_plane_burden": _user_plane_burden(trace, "post_action"),
        "no_action_user_plane_burden": None,
        "observed_action_benefit": None,
        "benefit_margin_points": 5.0,
        "violates_benefit_margin": None,
        "false_remediation": unit["fault_family"] == "no_fault" and bool(unit["mutates"]),
        "harmful_action": None,
        "harm_definition": (
            "mutating action whose observed benefit is below -5 burden points, "
            "or any mutation in a no-fault block"
        ),
        **_sla_endpoints(trace, action_at),
        "windows": {stage: trace["windows"][stage] for stage in REQUIRED_STAGES},
        "approval_id": trace["approval_id"],
        "safety_decision": trace["safety_evaluation"]["decision"],
        "reversible": bool(proposal and proposal.get("reversible")),
        "rollback_plan_recorded": bool(proposal and proposal.get("rollback_plan")),
        "cleanup_verified": True,
        "evidence_label": "sandbox-measured",
        "radio_evidence_label": "simulated",
        "hardware_evidence_label": None,
        "operator_validation": False,
        "contrast_design": "independent clean-reset complete named-action block",
    }
    if not unit["mutates"]:
        record["reversible"] = False
        record["rollback_plan_recorded"] = False
    return record


def build_records(
    source_bundle: Path, *, require_complete: bool = True
) -> list[dict[str, Any]]:
    """Build records from a verified run; releases require the full 675-unit campaign."""

    source_bundle = source_bundle.resolve()
    verify_manifest(source_bundle / "manifest.json")
    summary = _load_json(source_bundle / "summary.json")
    base_checks = (
        summary.get("passed") is True
        and summary.get("experiment_id") == EXPERIMENT_ID
        and summary.get("evidence_label") == "sandbox-measured"
        and summary.get("radio_evidence_label") == "simulated"
        and summary.get("hardware_evidence_label") is None
        and summary.get("operator_validation") is False
        and summary.get("completed_unit_count") == summary.get("planned_unit_count")
    )
    if not base_checks:
        raise ValueError("source is not a complete passing Phase 7 run")
    if require_complete and (
        summary.get("artifact_type") != "full-preregistered-campaign"
        or summary.get("completed_unit_count") != 675
        or summary.get("completed_block_count") != 135
    ):
        raise ValueError("v2a release requires the full 675-unit, 135-block campaign")

    commands: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for line in (source_bundle / "commands.jsonl").read_text(encoding="utf-8").splitlines():
        command = json.loads(line)
        commands[command["unit_id"]].append(command)
    records = [
        _record_from_trace(_load_json(path), commands)
        for path in sorted((source_bundle / "units").glob("*.json"))
    ]
    if len(records) != summary["completed_unit_count"]:
        raise ValueError("unit trace count differs from verified run summary")

    controls = {
        record["assignment_block_id"]: record["post_action_user_plane_burden"]
        for record in records
        if record["action_id"] == "observe_only"
    }
    for record in records:
        control = controls.get(record["assignment_block_id"])
        if control is None:
            raise ValueError(f"missing observe-only control for {record['assignment_block_id']}")
        benefit = control - record["post_action_user_plane_burden"]
        record["no_action_user_plane_burden"] = control
        record["observed_action_benefit"] = benefit
        record["violates_benefit_margin"] = bool(
            record["action_applied"] and benefit <= record["benefit_margin_points"]
        )
        record["harmful_action"] = bool(
            record["action_applied"]
            and (benefit < -record["benefit_margin_points"] or record["false_remediation"])
        )
    return sorted(records, key=lambda record: record["unit_id"])


def quality_report(
    records: list[dict[str, Any]], *, require_complete: bool = True
) -> dict[str, Any]:
    ids = [record["unit_id"] for record in records]
    split_counts = Counter(record["split"] for record in records)
    action_counts = Counter(record["action_id"] for record in records)
    blocks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        blocks[record["assignment_block_id"]].append(record)

    metric_cells = 0
    missing_metric_cells = 0
    timestamps_monotonic = True
    for record in records:
        prior: datetime | None = None
        for stage in REQUIRED_STAGES:
            for sample in record["windows"][stage]["samples"]:
                timestamp = _iso(sample["observed_at"])
                timestamps_monotonic = timestamps_monotonic and (
                    prior is None or timestamp >= prior
                )
                prior = timestamp
                metrics = sample["metrics"]
                metric_cells += len(EXPECTED_METRICS)
                missing_metric_cells += sum(
                    name not in metrics or metrics[name] is None for name in EXPECTED_METRICS
                )

    structural_checks = {
        "unit_ids_unique": len(ids) == len(set(ids)),
        "complete_five_action_blocks": bool(blocks)
        and all(
            len(block) == 5 and {row["action_id"] for row in block} == set(ACTION_IDS)
            for block in blocks.values()
        ),
        "four_three_sample_windows_per_unit": all(
            set(record["windows"]) == set(REQUIRED_STAGES)
            and all(len(record["windows"][stage]["samples"]) == 3 for stage in REQUIRED_STAGES)
            for record in records
        ),
        "timestamps_monotonic": timestamps_monotonic,
        "all_recovery_states_clean": all(
            all(
                sample["metrics"]["configured_packet_loss_pct"] == 0.0
                and sample["metrics"]["upf_process_running"] == 1.0
                and sample["metrics"]["stress_workers_count"] == 0.0
                and sample["metrics"]["packet_loss_pct"] <= 1.0
                for sample in record["windows"]["recovery"]["samples"]
            )
            for record in records
        ),
        "approvals_and_fail_closed_decisions_recorded": all(
            record["approval_id"]
            and (
                (record["action_applied"] and record["safety_decision"] == "require-human-approval")
                or (not record["action_applied"] and record["safety_decision"] == "observe-only")
            )
            for record in records
        ),
        "mutations_reversible_with_rollback": all(
            not record["action_applied"]
            or (record["reversible"] and record["rollback_plan_recorded"])
            for record in records
        ),
        "claim_labels_separated": all(
            record["evidence_label"] == "sandbox-measured"
            and record["radio_evidence_label"] == "simulated"
            and record["hardware_evidence_label"] is None
            and record["operator_validation"] is False
            for record in records
        ),
        "mttr_not_censored": all(record["mttr_status"] != "right-censored" for record in records),
        "public_records_exclude_approval_text": all(
            "authorization_basis" not in json.dumps(record, sort_keys=True)
            and "approved_by" not in json.dumps(record, sort_keys=True)
            for record in records
        ),
    }
    full_checks = {
        "record_count_675": len(records) == 675,
        "split_unit_counts_match_amendment": dict(split_counts) == EXPECTED_SPLIT_UNITS,
        "split_block_counts_match_amendment": {
            split: len({row["assignment_block_id"] for row in records if row["split"] == split})
            for split in EXPECTED_SPLIT_BLOCKS
        }
        == EXPECTED_SPLIT_BLOCKS,
        "action_portfolio_balanced": dict(action_counts) == {action: 135 for action in ACTION_IDS},
        "calibration_minimum_met": split_counts["calibration"] == 105,
        "test_minimum_met": split_counts["test"] == 350,
        "false_remediation_denominator_present": any(
            record["false_remediation"] for record in records
        ),
    }
    checks = {**structural_checks, **full_checks}
    structural_passed = all(structural_checks.values())
    release_eligible = structural_passed and all(full_checks.values())
    return {
        "schema_version": 2,
        "dataset_version": DATASET_VERSION,
        "passed": release_eligible if require_complete else structural_passed,
        "release_eligible": release_eligible,
        "checks": checks,
        "structural_checks": structural_checks,
        "full_campaign_checks": full_checks,
        "record_count": len(records),
        "split_counts": dict(sorted(split_counts.items())),
        "action_counts": dict(sorted(action_counts.items())),
        "assignment_block_count": len(blocks),
        "telemetry_sample_count": len(records) * len(REQUIRED_STAGES) * 3,
        "metric_cells": metric_cells,
        "missing_metric_cells": missing_metric_cells,
        "harmful_action_count": sum(record["harmful_action"] for record in records),
        "false_remediation_count": sum(record["false_remediation"] for record in records),
        "benefit_margin_violation_count": sum(
            record["violates_benefit_margin"] for record in records
        ),
        "mttr_status_counts": dict(
            sorted(Counter(record["mttr_status"] for record in records).items())
        ),
        "causal_identification_status": (
            "named-action contrasts identified within complete randomized-order sandbox "
            "blocks, conditional on clean-reset consistency and no interference"
        ),
        "limitations": [
            "All measurements come from one isolated software sandbox on one host and one campaign date.",
            "UERANSIM supplies simulated radio access; no hardware or operator evidence is inferred.",
            "The action order is reproducible SHA-256 ordering rather than blinded operator assignment.",
            "Linux netem packet randomness is not explicitly seedable.",
            "Three samples per stage limit temporal resolution and make MTTR interval-censored at sample times.",
            "The common service burden is max(packet loss, UPF-down percentage); CPU stress may not change it on this host.",
            "Six unrelated co-resident containers started on separate Docker networks after the campaign began; a measured idle snapshot found no network overlap, but CPU, memory, kernel, Docker-engine, and scheduler isolation were not established, so CPU-saturation and timing outcomes may contain uncontrolled shared-host contention.",
            "Benefit contrasts depend on clean reset, consistency, and absence of cross-unit interference.",
            "Primary policy inference must use independent blocks, exact denominators, and the preregistered multiplicity correction.",
        ],
        "evidence_label": "sandbox-measured",
        "radio_evidence_label": "simulated",
        "hardware_evidence_label": None,
        "operator_validation": False,
    }


def build_release(source_bundle: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite frozen release: {output}")
    source_bundle = source_bundle.resolve()
    records = build_records(source_bundle, require_complete=True)
    report = quality_report(records, require_complete=True)
    if not report["release_eligible"]:
        raise ValueError(f"v2a data-quality gate failed: {report['checks']}")
    output.mkdir(parents=True)
    (output / "records.jsonl").write_text(
        "".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    schema = {
        "schema_version": 2,
        "dataset_version": DATASET_VERSION,
        "unit_of_analysis": "one independently reset named-action sandbox assignment",
        "assignment_unit": "fault family, severity, seed, workload, split, and named action",
        "required_stages": list(REQUIRED_STAGES),
        "samples_per_stage": 3,
        "reference_action_id": "observe_only",
        "action_ids": list(ACTION_IDS),
        "contrast": "observe-only service burden minus named-action service burden within block",
        "service_burden": "max(mean packet-loss percentage, 100 * (1 - mean UPF-running indicator))",
        "certificate_margin_points": 5.0,
        "harm": "mutating action with benefit below -5 points, or any mutation in a no-fault block",
        "split_counts": {"units": EXPECTED_SPLIT_UNITS, "blocks": EXPECTED_SPLIT_BLOCKS},
        "public_safety": "approval identifier retained; authorization text and operator identity excluded",
    }
    (output / "schema.json").write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    (output / "data-quality.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    captured = {
        path.name: sha256(path)
        for path in sorted(output.iterdir())
        if path.is_file() and path.name != "manifest.json"
    }
    manifest = {
        "schema_version": 2,
        "dataset_version": DATASET_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "frozen": True,
        "passed": True,
        "evidence_label": "sandbox-measured",
        "radio_evidence_label": "simulated",
        "hardware_evidence_label": None,
        "operator_validation": False,
        "source_bundle": str(source_bundle.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "source_manifest_sha256": sha256(source_bundle / "manifest.json"),
        "record_count": len(records),
        "captured_file_sha256": captured,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest
