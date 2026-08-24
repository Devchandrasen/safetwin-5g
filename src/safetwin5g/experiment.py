"""Load and validate preregistered SafeTwin-5G experiment designs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


SPLIT_ORDER = {"train": 0, "calibration": 1, "test": 2, "ood": 3}
REQUIRED_ACTION_ARMS = {"effective", "no_action", "negative_control"}
REQUIRED_FAULTS = {
    "packet_impairment",
    "network_function_interruption",
    "cpu_saturation",
    "no_fault",
}


def load_design(path: Path) -> dict[str, Any]:
    """Load a JSON experiment design and fail if its invariants do not hold."""

    design = json.loads(path.read_text(encoding="utf-8"))
    validate_design(design)
    return design


def _unit_id(
    experiment_id: str,
    split: str,
    family: str,
    severity: float,
    action_arm: str,
    seed: int,
) -> str:
    severity_text = str(severity).replace(".", "p")
    return "-".join(
        (experiment_id, split, family, severity_text, action_arm, str(seed))
    )


def expand_design(design: dict[str, Any]) -> list[dict[str, Any]]:
    """Expand the frozen factorial definition into independently assigned units."""

    units: list[dict[str, Any]] = []
    salt = design["randomization"]["salt"]
    actions = design["action_arms"]
    for split, split_spec in design["splits"].items():
        workload = split_spec["workload"]
        for fault in design["faults"]:
            severities = (
                [fault["ood_severity"]]
                if split == "ood"
                else fault["development_severities"]
            )
            for severity in severities:
                for action_arm in actions:
                    for seed in split_spec["seeds"]:
                        unit_id = _unit_id(
                            design["experiment_id"],
                            split,
                            fault["family"],
                            severity,
                            action_arm,
                            seed,
                        )
                        randomization_key = hashlib.sha256(
                            f"{salt}|{unit_id}".encode("utf-8")
                        ).hexdigest()
                        units.append(
                            {
                                "unit_id": unit_id,
                                "split": split,
                                "fault_family": fault["family"],
                                "severity_name": fault["severity_name"],
                                "severity_value": severity,
                                "action_arm": action_arm,
                                "action_kind": design["action_semantics"][action_arm][
                                    fault["family"]
                                ],
                                "seed": seed,
                                "workload": workload,
                                "randomization_key": randomization_key,
                            }
                        )
    return sorted(
        units,
        key=lambda unit: (SPLIT_ORDER[unit["split"]], unit["randomization_key"]),
    )


def validate_design(design: dict[str, Any]) -> None:
    """Reject designs that weaken causal, statistical, or safety gates."""

    errors: list[str] = []
    if design.get("environment") != "sandbox":
        errors.append("environment must be sandbox")
    claims = design.get("claim_boundaries", {})
    if claims.get("evidence_label_after_measurement") != "sandbox-measured":
        errors.append("measured evidence must be labeled sandbox-measured")
    if claims.get("radio_evidence_label") != "simulated":
        errors.append("radio evidence must remain simulated")
    if claims.get("hardware_evidence_label") is not None:
        errors.append("hardware evidence must remain unset")
    if claims.get("operator_validation") is not False:
        errors.append("operator validation must remain false")

    unit = design.get("unit", {})
    for key in (
        "clean_reset_before_each_unit",
        "independent_action_assignment",
        "rollback_required",
    ):
        if unit.get(key) is not True:
            errors.append(f"unit.{key} must be true")
    if int(unit.get("window_samples_per_stage", 0)) < 3:
        errors.append("at least three samples per telemetry window are required")

    actions = set(design.get("action_arms", []))
    if actions != REQUIRED_ACTION_ARMS:
        errors.append("effective, no_action, and negative_control arms are required")
    faults = {fault.get("family") for fault in design.get("faults", [])}
    if faults != REQUIRED_FAULTS:
        errors.append("three fault families plus no_fault are required")
    if set(design.get("splits", {})) != set(SPLIT_ORDER):
        errors.append("train, calibration, test, and ood splits are required")
    if design.get("splits", {}).get("ood", {}).get("workload") == design.get(
        "splits", {}
    ).get("test", {}).get("workload"):
        errors.append("OOD workload must differ from the in-distribution workload")

    safety = design.get("safety", {})
    if safety.get("allow_live_actuation") is not False:
        errors.append("live actuation must be disabled")
    for key in (
        "require_explicit_sandbox_approval",
        "require_allowlisted_mutation",
        "require_pre_action_rollback_plan",
        "require_clean_final_state",
        "abort_on_failed_cleanup",
    ):
        if safety.get(key) is not True:
            errors.append(f"safety.{key} must be true")

    analysis = design.get("analysis", {})
    if analysis.get("conformal_coverage") != 0.9:
        errors.append("the preregistered conformal coverage must be 0.9")
    if int(analysis.get("minimum_calibration_units", 0)) < 19:
        errors.append("at least 19 calibration units are required")
    if not 0.0 < float(analysis.get("minimum_non_abstained_coverage", 0)) <= 1.0:
        errors.append("minimum non-abstained coverage must lie in (0, 1]")
    if analysis.get("multiplicity_adjustment") != "holm-for-H1-H2":
        errors.append("H1 and H2 require the preregistered Holm adjustment")

    if not errors:
        units = expand_design(design)
        ids = [unit["unit_id"] for unit in units]
        if len(ids) != len(set(ids)):
            errors.append("expanded unit identifiers must be unique")
        counts = {
            split: sum(unit["split"] == split for unit in units)
            for split in SPLIT_ORDER
        }
        expected = design.get("expected_counts", {})
        if counts != {split: expected.get(split) for split in SPLIT_ORDER}:
            errors.append(f"expanded split counts do not match preregistration: {counts}")
        if len(units) != expected.get("total"):
            errors.append("expanded total does not match preregistration")
        if counts["calibration"] < analysis["minimum_calibration_units"]:
            errors.append("calibration split is below its declared minimum")
        for split in SPLIT_ORDER:
            split_units = [unit for unit in units if unit["split"] == split]
            for family in REQUIRED_FAULTS:
                family_arms = {
                    unit["action_arm"]
                    for unit in split_units
                    if unit["fault_family"] == family
                }
                if family_arms != REQUIRED_ACTION_ARMS:
                    errors.append(f"{split}/{family} lacks randomized action positivity")

    if errors:
        raise ValueError("; ".join(errors))
