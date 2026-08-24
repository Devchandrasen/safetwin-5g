"""Build and validate the independent multi-action intervention dataset v1."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
REQUIRED_STAGES = ("baseline", "fault", "post_action", "recovery")
TARGETS = {
    "packet_impairment": ("packet_loss_pct", "lower-is-better"),
    "network_function_interruption": ("upf_process_running", "higher-is-better"),
    "cpu_saturation": ("stress_workers_count", "lower-is-better"),
    "no_fault": ("packet_loss_pct", "lower-is-better"),
}
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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_manifest(path: Path) -> None:
    manifest = _load_json(path)
    root = path.parent
    expected = manifest.get("captured_file_sha256", {})
    if not expected:
        raise ValueError("source manifest contains no captured files")
    actual = {
        str(item.relative_to(root)).replace("\\", "/")
        for item in root.rglob("*")
        if item.is_file() and item.name != "manifest.json"
    }
    if actual != set(expected):
        raise ValueError("source manifest coverage mismatch")
    for relative, digest in expected.items():
        if sha256(root / relative) != digest:
            raise ValueError(f"source hash mismatch: {relative}")


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


def _iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError(f"timestamp lacks timezone: {value}")
    return parsed


def _violates_user_plane(sample: dict[str, Any]) -> bool:
    metrics = sample["metrics"]
    return (
        float(metrics["packet_loss_pct"]) > 1.0
        or float(metrics["upf_process_running"]) < 1.0
    )


def _action_time(
    trace: dict[str, Any], commands: dict[str, list[dict[str, Any]]]
) -> datetime:
    unit_id = trace["unit"]["unit_id"]
    action_commands = [
        command
        for command in commands[unit_id]
        if command["name"].startswith("action-")
    ]
    if action_commands:
        return _iso(action_commands[0]["started_at"])
    action_events = [
        event
        for event in trace.get("control_events", [])
        if event.get("event") in {"observe_only", "benign_observe"}
    ]
    if len(action_events) != 1:
        raise ValueError(f"{unit_id} lacks exactly one assigned-action timestamp")
    return _iso(action_events[0]["at"])


def _sla_endpoints(trace: dict[str, Any], action_at: datetime) -> dict[str, Any]:
    fault_samples = trace["windows"]["fault"]["samples"]
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

    fault_active = _violates_user_plane(fault_samples[-1])
    post_active = any(states[: len(post_samples)])
    trigger_index = 0 if fault_active else next(
        (index for index, state in enumerate(states) if state), -1
    )
    if not fault_active and trigger_index < 0:
        mttr = 0.0
        status = "not-triggered"
    else:
        search_start = trigger_index if trigger_index >= 0 else 0
        clean_index = next(
            (index for index in range(search_start, len(states)) if not states[index]),
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


def _user_plane_burden(trace: dict[str, Any], stage: str) -> float:
    packet_loss = _mean_metric(trace, stage, "packet_loss_pct")
    upf_down = 100.0 * (1.0 - _mean_metric(trace, stage, "upf_process_running"))
    return max(packet_loss, upf_down)


def build_records(source_bundle: Path) -> list[dict[str, Any]]:
    """Build v1 records only from a complete verified campaign."""

    verify_manifest(source_bundle / "manifest.json")
    summary = _load_json(source_bundle / "summary.json")
    if (
        summary.get("artifact_type") != "full-preregistered-campaign"
        or summary.get("passed") is not True
        or summary.get("completed_unit_count") != 132
        or summary.get("evidence_label") != "sandbox-measured"
        or summary.get("radio_evidence_label") != "simulated"
    ):
        raise ValueError("source must be the complete passing Phase 6 campaign")

    commands: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for line in (source_bundle / "commands.jsonl").read_text(encoding="utf-8").splitlines():
        command = json.loads(line)
        commands[command["unit_id"]].append(command)
    records: list[dict[str, Any]] = []
    for path in sorted((source_bundle / "units").glob("*.json")):
        trace = _load_json(path)
        if trace.get("passed") is not True or trace.get("cleanup_verified") is not True:
            raise ValueError(f"failed or unclean unit cannot enter v1: {path.name}")
        unit = trace["unit"]
        target_metric, target_direction = TARGETS[unit["fault_family"]]
        fault_target = _mean_metric(trace, "fault", target_metric)
        post_target = _mean_metric(trace, "post_action", target_metric)
        benefit_sign = -1.0 if target_direction == "lower-is-better" else 1.0
        action_at = _action_time(trace, commands)
        sla = _sla_endpoints(trace, action_at)
        block_id = "|".join(
            str(unit[key])
            for key in (
                "split",
                "fault_family",
                "severity_value",
                "seed",
                "workload",
            )
        )
        record = {
            "schema_version": 1,
            "dataset_version": "safetwin5g-interventions-v1",
            "unit_id": unit["unit_id"],
            "assignment_block_id": block_id,
            "split": unit["split"],
            "fault_family": unit["fault_family"],
            "severity_name": unit["severity_name"],
            "severity_value": float(unit["severity_value"]),
            "seed": int(unit["seed"]),
            "workload": unit["workload"],
            "action_arm": unit["action_arm"],
            "action_kind": unit["action_kind"],
            "action_applied": trace["action_proposal"] is not None,
            "action_at": action_at.isoformat(),
            "target_kpi": target_metric,
            "target_direction": target_direction,
            "fault_target_mean": fault_target,
            "post_action_target_mean": post_target,
            "within_unit_observed_benefit": benefit_sign * (post_target - fault_target),
            "post_action_user_plane_burden": _user_plane_burden(trace, "post_action"),
            "false_remediation": (
                unit["fault_family"] == "no_fault"
                and trace["action_proposal"] is not None
            ),
            **sla,
            "harmful_action": None,
            "harm_contrast": "post-action user-plane burden versus no-action arm in the same assignment block",
            "windows": {
                stage: trace["windows"][stage] for stage in REQUIRED_STAGES
            },
            "approval_id": trace["approval_id"],
            "safety_evaluation": trace["safety_evaluation"],
            "evidence_label": "sandbox-measured",
            "radio_evidence_label": "simulated",
            "hardware_evidence_label": None,
            "operator_validation": False,
            "contrast_design": "independent clean-reset complete action-arm block",
        }
        records.append(record)

    no_action_burden = {
        record["assignment_block_id"]: record["post_action_user_plane_burden"]
        for record in records
        if record["action_arm"] == "no_action"
    }
    for record in records:
        control = no_action_burden.get(record["assignment_block_id"])
        if control is None:
            raise ValueError(f"missing no-action control for {record['assignment_block_id']}")
        record["no_action_user_plane_burden"] = control
        record["harmful_action"] = bool(
            record["action_applied"]
            and record["post_action_user_plane_burden"] > control + 1e-9
        )
    return sorted(records, key=lambda record: record["unit_id"])


def quality_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [record["unit_id"] for record in records]
    split_counts = Counter(record["split"] for record in records)
    arm_counts = Counter(record["action_arm"] for record in records)
    family_counts = Counter(record["fault_family"] for record in records)
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
                    name not in metrics or metrics[name] is None
                    for name in EXPECTED_METRICS
                )

    checks = {
        "record_count_132": len(records) == 132,
        "unit_ids_unique": len(ids) == len(set(ids)),
        "split_counts_match_preregistration": dict(split_counts)
        == {"train": 42, "calibration": 21, "test": 21, "ood": 48},
        "action_arms_balanced": dict(arm_counts)
        == {"effective": 44, "negative_control": 44, "no_action": 44},
        "four_families_present": set(family_counts)
        == {
            "packet_impairment",
            "network_function_interruption",
            "cpu_saturation",
            "no_fault",
        },
        "forty_four_complete_action_blocks": len(blocks) == 44
        and all(
            {record["action_arm"] for record in block}
            == {"effective", "negative_control", "no_action"}
            and len(block) == 3
            for block in blocks.values()
        ),
        "calibration_minimum_met": split_counts["calibration"] >= 19,
        "four_three_sample_windows_per_unit": all(
            set(record["windows"]) == set(REQUIRED_STAGES)
            and all(
                len(record["windows"][stage]["samples"]) == 3
                for stage in REQUIRED_STAGES
            )
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
        "approvals_and_action_decisions_recorded": all(
            record["approval_id"]
            and (
                (
                    record["action_applied"]
                    and record["safety_evaluation"]["decision"]
                    == "require-human-approval"
                )
                or (
                    not record["action_applied"]
                    and record["safety_evaluation"]["decision"] == "observe-only"
                )
            )
            for record in records
        ),
        "claim_labels_separated": all(
            record["evidence_label"] == "sandbox-measured"
            and record["radio_evidence_label"] == "simulated"
            and record["hardware_evidence_label"] is None
            and record["operator_validation"] is False
            for record in records
        ),
        "mttr_not_censored": all(
            record["mttr_status"] != "right-censored" for record in records
        ),
        "harm_endpoint_has_events": any(record["harmful_action"] for record in records),
        "false_remediation_denominator_present": any(
            record["fault_family"] == "no_fault" and record["action_applied"]
            for record in records
        ),
    }
    limitations = [
        "All measurements come from one isolated software sandbox on one host and one campaign date.",
        "UERANSIM supplies a simulated radio; there is no hardware-measured or operator-validated evidence.",
        "SHA-256 ordering is deterministic and unblinded; complete within-block action coverage, not random sampling from an operator population, supports the contrasts.",
        "Linux netem randomness is not explicitly seedable even though experiment timing jitter and split seeds are recorded.",
        "Telemetry windows contain three repeated samples and are not a continuous packet trace; MTTR is resolved only to the first observed clean sample.",
        "Mandatory experiment cleanup contributes to recovery time for no-action and negative-control arms.",
        "CPU saturation is an injected fault-state condition but may not create a user-plane SLA violation on this host.",
        "Multiple hypotheses and exploratory subgroup analyses require the preregistered Holm correction and cautious interpretation.",
    ]
    return {
        "schema_version": 1,
        "passed": all(checks.values()),
        "checks": checks,
        "record_count": len(records),
        "split_counts": dict(sorted(split_counts.items())),
        "action_arm_counts": dict(sorted(arm_counts.items())),
        "family_counts": dict(sorted(family_counts.items())),
        "assignment_block_count": len(blocks),
        "telemetry_sample_count": len(records) * len(REQUIRED_STAGES) * 3,
        "metric_cells": metric_cells,
        "missing_metric_cells": missing_metric_cells,
        "harmful_action_count": sum(record["harmful_action"] for record in records),
        "false_remediation_count": sum(record["false_remediation"] for record in records),
        "mttr_status_counts": dict(
            sorted(Counter(record["mttr_status"] for record in records).items())
        ),
        "causal_identification_status": (
            "identified for preregistered sandbox action-arm contrasts conditional "
            "on clean-reset consistency, no interference, and measured block exchangeability"
        ),
        "limitations": limitations,
        "evidence_label": "sandbox-measured",
        "radio_evidence_label": "simulated",
        "hardware_evidence_label": None,
        "operator_validation": False,
    }


def build_release(source_bundle: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite frozen release: {output}")
    records = build_records(source_bundle.resolve())
    report = quality_report(records)
    if not report["passed"]:
        raise ValueError(f"v1 data-quality gate failed: {report['checks']}")
    output.mkdir(parents=True)
    (output / "records.jsonl").write_text(
        "".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    schema = {
        "schema_version": 1,
        "dataset_version": "safetwin5g-interventions-v1",
        "unit_of_analysis": "one independently reset sandbox action assignment",
        "assignment_unit": "fault family, severity, seed, workload, and one action arm",
        "required_stages": list(REQUIRED_STAGES),
        "samples_per_stage": 3,
        "action_arms": ["effective", "no_action", "negative_control"],
        "target_definitions": {
            family: {"metric": target[0], "direction": target[1]}
            for family, target in TARGETS.items()
        },
        "split_rule": {
            "train": "steady workload, seeds 101 and 202",
            "calibration": "steady workload, seed 303",
            "test": "steady workload, seed 404",
            "ood": "held-out severity, sustained workload, seeds 505/606/707/808",
        },
        "harm_definition": (
            "applied action with higher post-action user-plane burden than the "
            "no-action arm in the same complete assignment block"
        ),
        "mttr_definition": (
            "seconds from assigned-action timestamp to first observed clean sample; "
            "zero when no SLA violation is triggered"
        ),
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
        "schema_version": 1,
        "dataset_version": "safetwin5g-interventions-v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "frozen": True,
        "passed": True,
        "evidence_label": "sandbox-measured",
        "radio_evidence_label": "simulated",
        "hardware_evidence_label": None,
        "operator_validation": False,
        "source_bundle": str(source_bundle.resolve().relative_to(PROJECT_ROOT)).replace(
            "\\", "/"
        ),
        "source_manifest_sha256": sha256(source_bundle / "manifest.json"),
        "record_count": len(records),
        "captured_file_sha256": captured,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest
