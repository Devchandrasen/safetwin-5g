"""Validation and deterministic expansion for the Phase 7 named-action study."""

from __future__ import annotations

import hashlib
import json
from math import ceil
from pathlib import Path
from typing import Any


SPLIT_ORDER = {"train": 0, "calibration": 1, "test": 2, "ood": 3}
REQUIRED_ACTION_IDS = {
    "observe_only",
    "clear_packet_impairment",
    "resume_upf",
    "stop_cpu_stress",
    "apply_packet_impairment_25",
}
REQUIRED_FAULTS = {
    "packet_impairment",
    "network_function_interruption",
    "cpu_saturation",
    "no_fault",
}
LEAKING_ACTION_TOKENS = ("effective", "negative_control", "oracle", "correct_action")


def load_phase7_design(path: Path) -> dict[str, Any]:
    design = json.loads(path.read_text(encoding="utf-8"))
    validate_phase7_design(design)
    return design


def _severity_text(value: float | int) -> str:
    return str(value).replace(".", "p")


def expand_phase7_design(design: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand complete named-action blocks without encoding action correctness."""

    units: list[dict[str, Any]] = []
    salt = design["randomization"]["salt"]
    for split, split_spec in design["splits"].items():
        workload = split_spec["workload"]
        for fault in design["faults"]:
            severities = (
                [fault["ood_severity"]]
                if split == "ood"
                else fault["development_severities"]
            )
            for severity in severities:
                for seed in split_spec["seeds"]:
                    block_id = "|".join(
                        (
                            split,
                            fault["family"],
                            _severity_text(severity),
                            str(seed),
                            workload,
                        )
                    )
                    for action in design["action_portfolio"]:
                        unit_id = "-".join(
                            (
                                design["experiment_id"],
                                split,
                                fault["family"],
                                _severity_text(severity),
                                action["action_id"],
                                str(seed),
                            )
                        )
                        randomization_key = hashlib.sha256(
                            f"{salt}|{unit_id}".encode("utf-8")
                        ).hexdigest()
                        units.append(
                            {
                                "unit_id": unit_id,
                                "assignment_block_id": block_id,
                                "split": split,
                                "fault_family": fault["family"],
                                "severity_name": fault["severity_name"],
                                "severity_value": severity,
                                "action_id": action["action_id"],
                                "action_kind": action["action_kind"],
                                "action_parameters": action.get("parameters", {}),
                                "mutates": action["mutates"],
                                "seed": seed,
                                "workload": workload,
                                "randomization_key": randomization_key,
                            }
                        )
    return sorted(
        units,
        key=lambda unit: (SPLIT_ORDER[unit["split"]], unit["randomization_key"]),
    )


def validate_phase7_design(design: dict[str, Any]) -> None:
    """Reject leakage, underpowered blocks, or weakened safety boundaries."""

    errors: list[str] = []
    if design.get("environment") != "sandbox":
        errors.append("environment must be sandbox")

    claims = design.get("claim_boundaries", {})
    if claims.get("evidence_label_after_measurement") != "sandbox-measured":
        errors.append("measured interventions must remain sandbox-measured")
    if claims.get("radio_evidence_label") != "simulated":
        errors.append("radio evidence must remain simulated")
    if claims.get("hardware_evidence_label") is not None:
        errors.append("hardware evidence must remain unset")
    if claims.get("operator_validation") is not False:
        errors.append("operator validation must remain false")

    actions = design.get("action_portfolio", [])
    action_ids = [action.get("action_id") for action in actions]
    if set(action_ids) != REQUIRED_ACTION_IDS or len(action_ids) != len(REQUIRED_ACTION_IDS):
        errors.append("the five frozen named actions are required exactly once")
    for action in actions:
        searchable = "|".join(
            str(action.get(key, "")).lower()
            for key in ("action_id", "action_kind", "description")
        )
        if any(token in searchable for token in LEAKING_ACTION_TOKENS):
            errors.append(f"action label leaks correctness: {action.get('action_id')}")
        if action.get("action_id") == "observe_only":
            if action.get("mutates") is not False:
                errors.append("observe_only must not mutate")
        elif action.get("mutates") is not True:
            errors.append(f"named action must declare mutation: {action.get('action_id')}")
    if design.get("reference_action_id") != "observe_only":
        errors.append("observe_only must be the causal reference action")

    faults = {fault.get("family") for fault in design.get("faults", [])}
    if faults != REQUIRED_FAULTS:
        errors.append("three fault families plus no_fault are required")
    if set(design.get("splits", {})) != set(SPLIT_ORDER):
        errors.append("train, calibration, test, and ood splits are required")
    if design.get("splits", {}).get("ood", {}).get("workload") == design.get(
        "splits", {}
    ).get("test", {}).get("workload"):
        errors.append("OOD workload must differ from the test workload")

    unit = design.get("unit", {})
    for key in ("clean_reset_before_each_unit", "rollback_required"):
        if unit.get(key) is not True:
            errors.append(f"unit.{key} must be true")
    if int(unit.get("window_samples_per_stage", 0)) < 3:
        errors.append("at least three samples per telemetry window are required")

    safety = design.get("safety", {})
    if safety.get("allow_live_actuation") is not False:
        errors.append("live actuation must be disabled")
    for key in (
        "require_explicit_sandbox_approval",
        "require_allowlisted_mutation",
        "require_pre_action_rollback_plan",
        "require_clean_final_state",
        "abort_on_failed_cleanup",
        "model_actions_are_proposals_only",
    ):
        if safety.get(key) is not True:
            errors.append(f"safety.{key} must be true")

    analysis = design.get("analysis", {})
    if analysis.get("method") != "BRACE-v1":
        errors.append("analysis method must be BRACE-v1")
    if analysis.get("simultaneous_conformal_coverage") != 0.9:
        errors.append("simultaneous conformal coverage must be 0.9")
    if analysis.get("calibration_unit") != "complete_assignment_block":
        errors.append("calibration unit must be the complete assignment block")
    if analysis.get("ood_policy") != "always_abstain":
        errors.append("OOD policy must always abstain")

    if not errors:
        units = expand_phase7_design(design)
        ids = [unit["unit_id"] for unit in units]
        if len(ids) != len(set(ids)):
            errors.append("expanded unit identifiers must be unique")
        blocks: dict[str, set[str]] = {}
        split_blocks: dict[str, set[str]] = {split: set() for split in SPLIT_ORDER}
        for unit_row in units:
            blocks.setdefault(unit_row["assignment_block_id"], set()).add(
                unit_row["action_id"]
            )
            split_blocks[unit_row["split"]].add(unit_row["assignment_block_id"])
        incomplete = [
            block_id
            for block_id, block_actions in blocks.items()
            if block_actions != REQUIRED_ACTION_IDS
        ]
        if incomplete:
            errors.append(f"incomplete action blocks: {len(incomplete)}")
        observed_blocks = {split: len(value) for split, value in split_blocks.items()}
        observed_units = {
            split: sum(unit_row["split"] == split for unit_row in units)
            for split in SPLIT_ORDER
        }
        expected = design.get("expected_counts", {})
        if observed_blocks != expected.get("blocks"):
            errors.append(f"block counts differ from preregistration: {observed_blocks}")
        if observed_units != expected.get("units"):
            errors.append(f"unit counts differ from preregistration: {observed_units}")
        if len(blocks) != expected.get("total_blocks"):
            errors.append("total block count differs from preregistration")
        if len(units) != expected.get("total_units"):
            errors.append("total unit count differs from preregistration")
        if observed_blocks["calibration"] < 19:
            errors.append("at least 19 independent calibration blocks are required")
        if observed_blocks["test"] < 35:
            errors.append("at least 35 independent test blocks are required")
        amendment = design.get("amendment")
        if amendment is not None:
            if amendment.get("amendment_id") != "phase7-precision-a1":
                errors.append("unknown Phase 7 amendment identifier")
            faulty_test_blocks = len(
                {
                    unit_row["assignment_block_id"]
                    for unit_row in units
                    if unit_row["split"] == "test"
                    and unit_row["fault_family"] != "no_fault"
                }
            )
            minimum_coverage = float(
                analysis.get("minimum_faulty_block_mutation_coverage", 0.0)
            )
            minimum_certified = ceil(faulty_test_blocks * minimum_coverage)
            declared_minimum = int(
                analysis.get("minimum_certified_mutation_count", 0)
            )
            if declared_minimum < 29:
                errors.append("amended design requires at least 29 certified mutations")
            if minimum_certified < declared_minimum:
                errors.append(
                    "test blocks and coverage floor cannot reach the certified-mutation minimum"
                )

    if errors:
        raise ValueError("; ".join(errors))
