"""Build and validate immutable SafeTwin-5G intervention datasets."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TARGETS = {
    "packet_impairment": ("packet_loss_pct", "lower-is-better", -1.0),
    "network_function_interruption": ("upf_process_running", "higher-is-better", 1.0),
    "cpu_saturation": ("stress_workers_count", "lower-is-better", -1.0),
}
REQUIRED_STAGES = ("baseline", "fault", "post-action", "rollback", "final")
EXPECTED_STAGE_METRICS = {
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


def split_for(severity_rank: int, seed_rank: int) -> str:
    return {
        (0, 0): "train",
        (0, 1): "calibration",
        (1, 0): "test",
        (1, 1): "ood",
    }[(severity_rank, seed_rank)]


def build_records(source_bundle: Path) -> list[dict[str, Any]]:
    summary = json.loads(
        (source_bundle / "summary.json").read_text(encoding="utf-8")
    )
    if not summary.get("passed") or summary.get("evidence_label") != "sandbox-measured":
        raise ValueError("source matrix must be a passing sandbox-measured bundle")
    traces = []
    for directory in sorted((source_bundle / "scenarios").iterdir()):
        if directory.is_dir():
            traces.append(json.loads((directory / "trace.json").read_text(encoding="utf-8")))
    severities: dict[str, list[float]] = {}
    seeds: dict[str, list[int]] = {}
    for trace in traces:
        scenario = trace["scenario"]
        family = scenario["fault_family"]
        severity = float(next(iter(scenario["fault_parameters"].values())))
        severities.setdefault(family, []).append(severity)
        seeds.setdefault(family, []).append(int(scenario["seed"]))
    severity_levels = {
        family: sorted(set(values)) for family, values in severities.items()
    }
    seed_levels = {family: sorted(set(values)) for family, values in seeds.items()}

    records: list[dict[str, Any]] = []
    for trace in traces:
        if not trace.get("passed"):
            raise ValueError(f"failed trace cannot enter release: {trace['scenario']}")
        scenario = trace["scenario"]
        family = scenario["fault_family"]
        severity_name, severity_raw = next(iter(scenario["fault_parameters"].items()))
        severity = float(severity_raw)
        seed = int(scenario["seed"])
        stages = {stage["stage"]: stage for stage in trace["stages"]}
        if set(stages) != set(REQUIRED_STAGES):
            raise ValueError(f"stage mismatch in {scenario['scenario_id']}")
        target_kpi, direction, benefit_sign = TARGETS[family]
        treatment_outcome = float(stages["post-action"]["metrics"][target_kpi])
        rollback_control = float(stages["rollback"]["metrics"][target_kpi])
        paired_difference = treatment_outcome - rollback_control
        record = {
            "schema_version": 1,
            "dataset_version": "safetwin5g-interventions-v0",
            "scenario_id": scenario["scenario_id"],
            "group_id": scenario["scenario_id"],
            "fault_family": family,
            "severity_name": severity_name,
            "severity_value": severity,
            "seed": seed,
            "split": split_for(
                severity_levels[family].index(severity),
                seed_levels[family].index(seed),
            ),
            "action_kind": scenario["action_kind"],
            "target_kpi": target_kpi,
            "target_direction": direction,
            "treatment_outcome": treatment_outcome,
            "rollback_control_outcome": rollback_control,
            "paired_outcome_difference": paired_difference,
            "observed_benefit": benefit_sign * paired_difference,
            "harmful_action": benefit_sign * paired_difference < 0.0,
            "stages": {
                stage: {
                    "observed_at": stages[stage]["observed_at"],
                    "metrics": stages[stage]["metrics"],
                }
                for stage in REQUIRED_STAGES
            },
            "evidence_label": "sandbox-measured",
            "radio_evidence_label": "simulated",
            "hardware_evidence_label": None,
            "operator_validation": False,
            "contrast_design": "action-first paired rollback proxy",
        }
        records.append(record)
    return sorted(records, key=lambda record: record["scenario_id"])


def quality_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    ids = [record["scenario_id"] for record in records]
    families = sorted({record["fault_family"] for record in records})
    splits = sorted({record["split"] for record in records})
    missing_metric_cells = 0
    metric_cells = 0
    for record in records:
        for stage in record["stages"].values():
            metrics = stage["metrics"]
            metric_cells += len(EXPECTED_STAGE_METRICS)
            missing_metric_cells += sum(
                name not in metrics or metrics[name] is None
                for name in EXPECTED_STAGE_METRICS
            )
    checks = {
        "twelve_records": len(records) == 12,
        "scenario_ids_unique": len(ids) == len(set(ids)),
        "three_fault_families": len(families) == 3,
        "four_records_per_family": all(
            sum(record["fault_family"] == family for record in records) == 4
            for family in families
        ),
        "two_severities_per_family": all(
            len(
                {
                    record["severity_value"]
                    for record in records
                    if record["fault_family"] == family
                }
            )
            == 2
            for family in families
        ),
        "two_seeds_per_family": all(
            len(
                {
                    record["seed"]
                    for record in records
                    if record["fault_family"] == family
                }
            )
            == 2
            for family in families
        ),
        "four_disjoint_splits": splits == ["calibration", "ood", "test", "train"],
        "no_group_crosses_splits": all(
            len({record["split"] for record in records if record["group_id"] == group}) == 1
            for group in set(ids)
        ),
        "all_final_cleanups_healthy": all(
            record["stages"]["final"]["metrics"]["packet_loss_pct"] == 0.0
            and record["stages"]["final"]["metrics"]["upf_process_running"] == 1.0
            and record["stages"]["final"]["metrics"]["stress_workers_count"] == 0.0
            for record in records
        ),
        "claim_labels_separated": all(
            record["evidence_label"] == "sandbox-measured"
            and record["radio_evidence_label"] == "simulated"
            and record["hardware_evidence_label"] is None
            and record["operator_validation"] is False
            for record in records
        ),
    }
    limitations = [
        "Only 12 scenarios are available; train/calibration/test/OOD each contain three rows.",
        "Each fault family has one deterministic remediation, so alternative-action positivity is absent.",
        "The rollback control is observed after the action, so order and carry-over may confound the paired contrast.",
        "Seed controls pre-fault timing jitter; Linux netem packet randomness is not explicitly seedable in the pinned image.",
        "CPU saturation was directly observed but did not cause packet loss in these runs.",
        "UERANSIM supplies a simulated radio; no hardware or operator data are present.",
    ]
    return {
        "schema_version": 1,
        "passed": all(checks.values()),
        "checks": checks,
        "record_count": len(records),
        "family_counts": {
            family: sum(record["fault_family"] == family for record in records)
            for family in families
        },
        "split_counts": {
            split: sum(record["split"] == split for record in records) for split in splits
        },
        "metric_cells": metric_cells,
        "missing_metric_cells": missing_metric_cells,
        "limitations": limitations,
        "causal_identification_status": "not identified for alternative actions",
        "evidence_label": "sandbox-measured",
        "radio_evidence_label": "simulated",
    }


def build_release(source_bundle: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        raise FileExistsError(f"refusing to overwrite frozen release: {output}")
    output.mkdir(parents=True)
    records = build_records(source_bundle.resolve())
    record_path = output / "records.jsonl"
    record_path.write_text(
        "".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    schema = {
        "schema_version": 1,
        "dataset_version": "safetwin5g-interventions-v0",
        "unit_of_analysis": "one measured scenario with action-first paired rollback proxy",
        "required_stages": list(REQUIRED_STAGES),
        "target_definitions": {
            family: {
                "metric": values[0],
                "direction": values[1],
                "benefit_sign": values[2],
            }
            for family, values in TARGETS.items()
        },
        "split_rule": {
            "train": "lower severity, seed 101",
            "calibration": "lower severity, seed 202",
            "test": "higher severity, seed 101",
            "ood": "higher severity, seed 202",
        },
    }
    (output / "schema.json").write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report = quality_report(records)
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    (output / "data-quality.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    captured = {
        path.name: sha256(path)
        for path in sorted(output.iterdir())
        if path.is_file() and path.name != "manifest.json"
    }
    source_manifest = source_bundle / "manifest.json"
    manifest = {
        "schema_version": 1,
        "dataset_version": "safetwin5g-interventions-v0",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "frozen": True,
        "passed": report["passed"],
        "evidence_label": "sandbox-measured",
        "radio_evidence_label": "simulated",
        "source_bundle": str(source_bundle.resolve().relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "source_manifest_sha256": sha256(source_manifest),
        "record_count": len(records),
        "captured_file_sha256": captured,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return manifest
