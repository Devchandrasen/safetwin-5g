"""Leakage-controlled statistical evaluation for intervention dataset v1."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from itertools import product
import json
from math import sqrt
from pathlib import Path
import random
import statistics
from typing import Any, Callable

from .baselines import Standardizer, solve
from .uncertainty import ConformalCalibration


FAMILIES = (
    "cpu_saturation",
    "network_function_interruption",
    "no_fault",
    "packet_impairment",
)
ARMS = ("effective", "negative_control", "no_action")
SPLITS = ("train", "calibration", "test", "ood")
ALPHAS = (0.01, 0.1, 1.0, 10.0, 100.0, 1000.0)


def load_records(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def percentile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def describe(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {
            "n": 0,
            "mean": None,
            "median": None,
            "standard_deviation": None,
            "minimum": None,
            "p25": None,
            "p75": None,
            "iqr": None,
            "p90": None,
            "maximum": None,
        }
    p25 = percentile(values, 0.25)
    p75 = percentile(values, 0.75)
    return {
        "n": len(values),
        "mean": statistics.fmean(values),
        "median": statistics.median(values),
        "standard_deviation": statistics.stdev(values) if len(values) > 1 else 0.0,
        "minimum": min(values),
        "p25": p25,
        "p75": p75,
        "iqr": p75 - p25,
        "p90": percentile(values, 0.90),
        "maximum": max(values),
    }


def _fault_metric(record: dict[str, Any], name: str) -> float:
    summary = record["windows"]["fault"]["summary"]["metrics"][name]
    if summary["mean"] is None:
        raise ValueError(f"missing fault feature {name} in {record['unit_id']}")
    return float(summary["mean"])


def fault_user_plane_burden(record: dict[str, Any]) -> float:
    packet_loss = _fault_metric(record, "packet_loss_pct")
    upf_down = 100.0 * (1.0 - _fault_metric(record, "upf_process_running"))
    return max(packet_loss, upf_down)


def raw_features(record: dict[str, Any]) -> list[float]:
    family = record["fault_family"]
    arm = record["action_arm"]
    family_flags = [float(family == item) for item in FAMILIES]
    arm_flags = [float(arm == item) for item in ARMS]
    interactions = [
        float(family == family_name and arm == arm_name)
        for family_name in FAMILIES
        for arm_name in ARMS
    ]
    severity_by_family = [
        float(record["severity_value"]) if family == item else 0.0
        for item in FAMILIES
    ]
    fault_metrics = [
        _fault_metric(record, name)
        for name in (
            "packet_loss_pct",
            "core_container_cpu_pct",
            "stress_workers_count",
            "upf_process_running",
            "configured_packet_loss_pct",
        )
    ]
    return (
        family_flags
        + arm_flags
        + interactions
        + severity_by_family
        + fault_metrics
        + [fault_user_plane_burden(record), float(record["workload"] == "sustained")]
    )


@dataclass(frozen=True)
class OutcomeRidge:
    coefficients: tuple[float, ...]
    standardizer: Standardizer
    alpha: float
    fitted_unit_ids: tuple[str, ...]

    @classmethod
    def fit(cls, records: list[dict[str, Any]], alpha: float) -> "OutcomeRidge":
        features = [raw_features(record) for record in records]
        standardizer = Standardizer.fit(features)
        design = [[1.0] + standardizer.transform(row) for row in features]
        targets = [float(record["post_action_user_plane_burden"]) for record in records]
        width = len(design[0])
        gram = [[0.0 for _ in range(width)] for _ in range(width)]
        rhs = [0.0 for _ in range(width)]
        for row, target in zip(design, targets, strict=True):
            for i in range(width):
                rhs[i] += row[i] * target
                for j in range(width):
                    gram[i][j] += row[i] * row[j]
        for index in range(1, width):
            gram[index][index] += alpha
        return cls(
            coefficients=tuple(solve(gram, rhs)),
            standardizer=standardizer,
            alpha=alpha,
            fitted_unit_ids=tuple(sorted(record["unit_id"] for record in records)),
        )

    def predict(self, record: dict[str, Any]) -> float:
        row = [1.0] + self.standardizer.transform(raw_features(record))
        return sum(value * coefficient for value, coefficient in zip(row, self.coefficients))


def temporal_prediction(record: dict[str, Any]) -> float:
    return fault_user_plane_burden(record)


def rule_prediction(record: dict[str, Any]) -> float:
    family = record["fault_family"]
    arm = record["action_arm"]
    if arm == "no_action":
        return fault_user_plane_burden(record)
    if arm == "effective":
        if family in {"packet_impairment", "network_function_interruption"}:
            return 0.0
        return fault_user_plane_burden(record)
    if family == "packet_impairment":
        return min(95.0, float(record["severity_value"]) + 15.0)
    if family == "network_function_interruption":
        return 100.0
    return 25.0


def error_metrics(
    records: list[dict[str, Any]], predictor: Callable[[dict[str, Any]], float]
) -> dict[str, Any]:
    errors = [
        predictor(record) - float(record["post_action_user_plane_burden"])
        for record in records
    ]
    absolute = [abs(value) for value in errors]
    return {
        "n": len(records),
        "mae": statistics.fmean(absolute),
        "rmse": sqrt(statistics.fmean([value * value for value in errors])),
        "mean_bias": statistics.fmean(errors),
        "absolute_error_distribution": describe(absolute),
        "signed_error_distribution": describe(errors),
    }


def select_model(
    train: list[dict[str, Any]], calibration: list[dict[str, Any]]
) -> tuple[OutcomeRidge, list[dict[str, float]]]:
    trials: list[dict[str, float]] = []
    best: tuple[float, float, OutcomeRidge] | None = None
    for alpha in ALPHAS:
        model = OutcomeRidge.fit(train, alpha)
        score = float(error_metrics(calibration, model.predict)["mae"])
        trials.append({"alpha": alpha, "calibration_mae": score})
        candidate = (score, alpha, model)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    assert best is not None
    return best[2], trials


def _block_values(
    records: list[dict[str, Any]], value: Callable[[dict[str, Any]], float]
) -> dict[str, list[float]]:
    blocks: dict[str, list[float]] = defaultdict(list)
    for record in records:
        blocks[record["assignment_block_id"]].append(float(value(record)))
    return blocks


def block_bootstrap_mean(
    records: list[dict[str, Any]],
    value: Callable[[dict[str, Any]], float],
    *,
    seed: int,
    iterations: int = 10_000,
) -> dict[str, Any]:
    blocks = _block_values(records, value)
    block_ids = sorted(blocks)
    observed_values = [item for block in block_ids for item in blocks[block]]
    observed = statistics.fmean(observed_values)
    rng = random.Random(seed)
    estimates = []
    for _ in range(iterations):
        chosen = [rng.choice(block_ids) for _ in block_ids]
        sample = [item for block in chosen for item in blocks[block]]
        estimates.append(statistics.fmean(sample))
    block_means = [statistics.fmean(blocks[block]) for block in block_ids]
    standard_deviation = statistics.stdev(block_means) if len(block_means) > 1 else 0.0
    return {
        "estimate": observed,
        "ci95": [percentile(estimates, 0.025), percentile(estimates, 0.975)],
        "bootstrap_iterations": iterations,
        "bootstrap_seed": seed,
        "independent_block_n": len(block_ids),
        "row_n": len(records),
        "standardized_block_effect": (
            statistics.fmean(block_means) / standard_deviation
            if standard_deviation > 0.0
            else None
        ),
    }


def exact_sign_flip_pvalue(
    records: list[dict[str, Any]],
    value: Callable[[dict[str, Any]], float],
    *,
    alternative: str = "less",
) -> dict[str, Any]:
    blocks = _block_values(records, value)
    block_means = [statistics.fmean(blocks[key]) for key in sorted(blocks)]
    if len(block_means) > 20:
        raise ValueError("exact sign-flip enumeration is limited to 20 blocks")
    observed = statistics.fmean(block_means)
    null = [
        statistics.fmean([sign * item for sign, item in zip(signs, block_means)])
        for signs in product((-1.0, 1.0), repeat=len(block_means))
    ]
    if alternative == "less":
        pvalue = sum(item <= observed + 1e-12 for item in null) / len(null)
    elif alternative == "greater":
        pvalue = sum(item >= observed - 1e-12 for item in null) / len(null)
    else:
        raise ValueError("alternative must be less or greater")
    return {
        "observed_block_mean": observed,
        "exact_one_sided_pvalue": pvalue,
        "permutations": len(null),
        "independent_block_n": len(block_means),
        "alternative": alternative,
    }


def holm_adjust(pvalues: dict[str, float]) -> dict[str, float]:
    ordered = sorted(pvalues, key=lambda key: (pvalues[key], key))
    adjusted: dict[str, float] = {}
    running = 0.0
    total = len(ordered)
    for index, key in enumerate(ordered):
        candidate = min(1.0, (total - index) * pvalues[key])
        running = max(running, candidate)
        adjusted[key] = running
    return adjusted


@dataclass(frozen=True)
class DesignOODDetector:
    severity_ranges: dict[str, tuple[float, float]]
    workloads: tuple[str, ...]
    fitted_unit_ids: tuple[str, ...]

    @classmethod
    def fit(cls, records: list[dict[str, Any]]) -> "DesignOODDetector":
        values: dict[str, list[float]] = defaultdict(list)
        for record in records:
            values[record["fault_family"]].append(float(record["severity_value"]))
        return cls(
            severity_ranges={
                family: (min(items), max(items)) for family, items in values.items()
            },
            workloads=tuple(sorted({record["workload"] for record in records})),
            fitted_unit_ids=tuple(sorted(record["unit_id"] for record in records)),
        )

    def evaluate(self, record: dict[str, Any]) -> dict[str, Any]:
        reasons = []
        family = record["fault_family"]
        severity = float(record["severity_value"])
        if family not in self.severity_ranges:
            reasons.append("unseen fault family")
        else:
            lower, upper = self.severity_ranges[family]
            if severity < lower or severity > upper:
                reasons.append(
                    f"severity {severity:g} outside development range [{lower:g}, {upper:g}]"
                )
        if record["workload"] not in self.workloads:
            reasons.append(f"unseen workload {record['workload']}")
        return {
            "is_ood": bool(reasons),
            "ood_score": 1.0 if reasons else 0.0,
            "reasons": reasons or ["within development severity and workload support"],
        }


def empirical_interval_coverage(
    records: list[dict[str, Any]],
    predictor: Callable[[dict[str, Any]], float],
    calibration: ConformalCalibration,
) -> dict[str, Any]:
    if calibration.radius is None:
        return {"n": len(records), "covered": None, "coverage": None}
    covered = sum(
        abs(predictor(record) - float(record["post_action_user_plane_burden"]))
        <= calibration.radius
        for record in records
    )
    return {"n": len(records), "covered": covered, "coverage": covered / len(records)}


def selective_assessments(
    records: list[dict[str, Any]],
    model: OutcomeRidge,
    calibration: ConformalCalibration,
    detector: DesignOODDetector,
) -> list[dict[str, Any]]:
    by_block = defaultdict(dict)
    for record in records:
        by_block[record["assignment_block_id"]][record["action_arm"]] = record
    assessments = []
    for record in records:
        control = by_block[record["assignment_block_id"]]["no_action"]
        prediction = model.predict(record)
        control_prediction = model.predict(control)
        predicted_benefit = control_prediction - prediction
        radius = calibration.radius
        contrast_margin = 2.0 * radius if radius is not None else None
        ood = detector.evaluate(record)
        reasons = []
        if record["action_arm"] == "no_action" or not record["action_applied"]:
            decision = "eligible-no-mutation"
        else:
            if radius is None:
                reasons.append("unbounded nominal uncertainty interval")
            if ood["is_ood"]:
                reasons.extend(ood["reasons"])
            if contrast_margin is not None and predicted_benefit <= contrast_margin:
                reasons.append(
                    "predicted benefit does not exceed the conservative two-radius contrast margin"
                )
            decision = "abstain" if reasons else "eligible-for-human-approval"
        eligible = decision != "abstain"
        assessments.append(
            {
                "unit_id": record["unit_id"],
                "assignment_block_id": record["assignment_block_id"],
                "split": record["split"],
                "fault_family": record["fault_family"],
                "action_arm": record["action_arm"],
                "action_applied": record["action_applied"],
                "prediction": prediction,
                "no_action_prediction": control_prediction,
                "predicted_benefit": predicted_benefit,
                "contrast_margin": contrast_margin,
                "is_ood": ood["is_ood"],
                "ood_reasons": ood["reasons"],
                "decision": decision,
                "reasons": reasons,
                "observed_harmful_action": record["harmful_action"],
                "harm_if_selective": bool(
                    eligible and record["action_applied"] and record["harmful_action"]
                ),
                "false_remediation": record["false_remediation"],
                "evidence_label": record["evidence_label"],
                "radio_evidence_label": record["radio_evidence_label"],
            }
        )
    return assessments


def selective_summary(
    records: list[dict[str, Any]], assessments: list[dict[str, Any]]
) -> dict[str, Any]:
    record_by_id = {record["unit_id"]: record for record in records}
    action_candidates = [
        item for item in assessments if item["action_arm"] != "no_action"
    ]
    eligible = [item for item in action_candidates if item["decision"] != "abstain"]
    eligible_mutations = [item for item in eligible if item["action_applied"]]
    harmful_always = sum(item["observed_harmful_action"] for item in action_candidates)
    harmful_selective = sum(item["harm_if_selective"] for item in action_candidates)
    false_always = sum(item["false_remediation"] for item in action_candidates)
    false_selective = sum(
        item["false_remediation"] and item["decision"] != "abstain"
        for item in action_candidates
    )
    applied_harmful = sum(item["harm_if_selective"] for item in eligible_mutations)
    sla_values = [
        float(record_by_id[item["unit_id"]]["sla_violation_duration_seconds"])
        for item in eligible_mutations
    ]
    mttr_values = [
        float(record_by_id[item["unit_id"]]["mttr_seconds"])
        for item in eligible_mutations
        if record_by_id[item["unit_id"]]["mttr_seconds"] is not None
    ]
    return {
        "action_candidate_n": len(action_candidates),
        "eligible_candidate_n": len(eligible),
        "eligible_applied_mutation_n": len(eligible_mutations),
        "coverage": len(eligible) / len(action_candidates) if action_candidates else None,
        "abstention_rate": (
            (len(action_candidates) - len(eligible)) / len(action_candidates)
            if action_candidates
            else None
        ),
        "always_act_harmful_count": harmful_always,
        "always_act_harmful_rate": (
            harmful_always / len(action_candidates) if action_candidates else None
        ),
        "selective_harmful_count_all_candidates": harmful_selective,
        "selective_harmful_rate_all_candidates": (
            harmful_selective / len(action_candidates) if action_candidates else None
        ),
        "selective_harmful_rate_given_applied": (
            applied_harmful / len(eligible_mutations) if eligible_mutations else None
        ),
        "always_act_false_remediation_count": false_always,
        "selective_false_remediation_count": false_selective,
        "eligible_sla_duration_seconds": describe(sla_values),
        "eligible_mttr_seconds": describe(mttr_values),
    }


def risk_coverage_curve(
    records: list[dict[str, Any]], assessments: list[dict[str, Any]]
) -> dict[str, Any]:
    candidates = [item for item in assessments if item["action_arm"] != "no_action"]
    ordered = sorted(
        candidates,
        key=lambda item: (
            -item["predicted_benefit"],
            item["unit_id"],
        ),
    )
    points = []
    harmful = 0
    for index, item in enumerate(ordered, start=1):
        harmful += int(item["observed_harmful_action"])
        points.append(
            {
                "coverage": index / len(ordered),
                "harmful_rate": harmful / index,
                "included_n": index,
            }
        )
    auc = 0.0
    previous_coverage = 0.0
    previous_risk = points[0]["harmful_rate"] if points else 0.0
    for point in points:
        auc += (point["coverage"] - previous_coverage) * (
            previous_risk + point["harmful_rate"]
        ) / 2.0
        previous_coverage = point["coverage"]
        previous_risk = point["harmful_rate"]
    return {"candidate_n": len(ordered), "aurc": auc, "points": points}


def _effect_contrasts(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks = defaultdict(dict)
    for record in records:
        blocks[record["assignment_block_id"]][record["action_arm"]] = record
    rows = []
    for block_id, block in sorted(blocks.items()):
        control = block["no_action"]
        for arm in ("effective", "negative_control"):
            treatment = block[arm]
            rows.append(
                {
                    "assignment_block_id": block_id,
                    "split": treatment["split"],
                    "fault_family": treatment["fault_family"],
                    "severity_value": treatment["severity_value"],
                    "seed": treatment["seed"],
                    "workload": treatment["workload"],
                    "action_arm": arm,
                    "user_plane_burden_effect": (
                        treatment["post_action_user_plane_burden"]
                        - control["post_action_user_plane_burden"]
                    ),
                    "sla_duration_effect_seconds": (
                        treatment["sla_violation_duration_seconds"]
                        - control["sla_violation_duration_seconds"]
                    ),
                    "mttr_effect_seconds": (
                        float(treatment["mttr_seconds"])
                        - float(control["mttr_seconds"])
                    ),
                    "treatment_harmful": treatment["harmful_action"],
                    "evidence_label": treatment["evidence_label"],
                    "radio_evidence_label": treatment["radio_evidence_label"],
                }
            )
    return rows


def causal_effect_report(contrasts: list[dict[str, Any]]) -> dict[str, Any]:
    report: dict[str, Any] = {}
    for split in ("test", "ood"):
        report[split] = {}
        for arm in ("effective", "negative_control"):
            rows = [
                row
                for row in contrasts
                if row["split"] == split and row["action_arm"] == arm
            ]
            report[split][arm] = {
                "user_plane_burden_effect": describe(
                    [float(row["user_plane_burden_effect"]) for row in rows]
                ),
                "user_plane_burden_effect_ci": block_bootstrap_mean(
                    rows,
                    lambda row: float(row["user_plane_burden_effect"]),
                    seed=6100 + (0 if split == "test" else 100) + (0 if arm == "effective" else 1),
                ),
                "sla_duration_effect_seconds": describe(
                    [float(row["sla_duration_effect_seconds"]) for row in rows]
                ),
                "mttr_effect_seconds": describe(
                    [float(row["mttr_effect_seconds"]) for row in rows]
                ),
                "harmful_count": sum(row["treatment_harmful"] for row in rows),
                "n": len(rows),
            }
    return report


def _leakage_check(records: list[dict[str, Any]], model: OutcomeRidge) -> dict[str, Any]:
    changes = []
    for record in records:
        original = model.predict(record)
        mutated = deepcopy(record)
        mutated["post_action_user_plane_burden"] = 1_000_000.0
        mutated["harmful_action"] = not mutated["harmful_action"]
        for sample in mutated["windows"]["post_action"]["samples"]:
            sample["metrics"] = {name: 1_000_000.0 for name in sample["metrics"]}
        changes.append(abs(model.predict(mutated) - original))
    return {
        "passed": max(changes, default=0.0) == 0.0,
        "max_prediction_change": max(changes, default=0.0),
        "mutated_post_treatment_fields": [
            "post_action_user_plane_burden",
            "harmful_action",
            "post_action telemetry samples",
        ],
    }


def _policy_evaluation(
    test_records: list[dict[str, Any]],
    model: OutcomeRidge,
    assessment_by_id: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    blocks = defaultdict(dict)
    for record in test_records:
        blocks[record["assignment_block_id"]][record["action_arm"]] = record
    rule_selected = []
    twin_selected = []
    selections = []
    for block_id, block in sorted(blocks.items()):
        family = block["no_action"]["fault_family"]
        rule_arm = "no_action" if family == "no_fault" else "effective"
        rule_record = block[rule_arm]
        ranked = sorted(block.values(), key=lambda record: (model.predict(record), record["action_arm"]))
        candidate = ranked[0]
        candidate_assessment = assessment_by_id[candidate["unit_id"]]
        twin_record = (
            candidate
            if candidate_assessment["decision"] != "abstain"
            else block["no_action"]
        )
        rule_selected.append(rule_record)
        twin_selected.append(twin_record)
        selections.append(
            {
                "assignment_block_id": block_id,
                "fault_family": family,
                "rule_arm": rule_record["action_arm"],
                "twin_arm": twin_record["action_arm"],
                "twin_candidate_arm": candidate["action_arm"],
                "twin_candidate_decision": candidate_assessment["decision"],
            }
        )

    def endpoints(selected: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "block_n": len(selected),
            "sla_violation_duration_seconds": describe(
                [float(record["sla_violation_duration_seconds"]) for record in selected]
            ),
            "mttr_seconds": describe([float(record["mttr_seconds"]) for record in selected]),
            "false_remediation_count": sum(record["false_remediation"] for record in selected),
            "harmful_action_count": sum(record["harmful_action"] for record in selected),
            "rollback_success_count": len(selected),
        }

    sla_differences = [
        float(twin["sla_violation_duration_seconds"])
        - float(rule["sla_violation_duration_seconds"])
        for twin, rule in zip(twin_selected, rule_selected, strict=True)
    ]
    mttr_differences = [
        float(twin["mttr_seconds"]) - float(rule["mttr_seconds"])
        for twin, rule in zip(twin_selected, rule_selected, strict=True)
    ]
    supported = (
        statistics.fmean(sla_differences) < 0.0
        and statistics.fmean(mttr_differences) <= 0.0
        and sum(record["false_remediation"] for record in twin_selected)
        <= sum(record["false_remediation"] for record in rule_selected)
    )
    return {
        "design": (
            "offline policy evaluation on independently reset, human-approved, "
            "complete test action blocks; no new or live action"
        ),
        "rule_policy": endpoints(rule_selected),
        "human_governed_twin_policy": endpoints(twin_selected),
        "paired_sla_duration_difference_seconds": describe(sla_differences),
        "paired_mttr_difference_seconds": describe(mttr_differences),
        "selections": selections,
        "support_gate_passed": supported,
    }


def analyze(records: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    by_split = {
        split: [record for record in records if record["split"] == split]
        for split in SPLITS
    }
    expected = {"train": 42, "calibration": 21, "test": 21, "ood": 48}
    if {split: len(rows) for split, rows in by_split.items()} != expected:
        raise ValueError("dataset v1 split counts changed")
    model, alpha_trials = select_model(by_split["train"], by_split["calibration"])
    predictors = {
        "action_conditional_ridge": model.predict,
        "deterministic_rule": rule_prediction,
        "temporal_persistence": temporal_prediction,
    }
    evaluation = {
        split: {
            name: error_metrics(rows, predictor)
            for name, predictor in predictors.items()
        }
        for split, rows in by_split.items()
    }
    ranking = sorted(
        predictors,
        key=lambda name: (evaluation["test"][name]["mae"], name),
    )

    calibration = ConformalCalibration.fit(
        [model.predict(record) for record in by_split["calibration"]],
        [float(record["post_action_user_plane_burden"]) for record in by_split["calibration"]],
        0.90,
    )
    detector = DesignOODDetector.fit(by_split["train"] + by_split["calibration"])
    assessments = selective_assessments(records, model, calibration, detector)
    assessment_by_id = {item["unit_id"]: item for item in assessments}
    selective = {
        split: selective_summary(
            by_split[split], [item for item in assessments if item["split"] == split]
        )
        for split in ("test", "ood")
    }
    selective["test"]["risk_coverage"] = risk_coverage_curve(
        by_split["test"], [item for item in assessments if item["split"] == "test"]
    )

    h1_value = lambda record: abs(
        model.predict(record) - float(record["post_action_user_plane_burden"])
    ) - abs(temporal_prediction(record) - float(record["post_action_user_plane_burden"]))
    h1_ci = block_bootstrap_mean(by_split["test"], h1_value, seed=6101)
    h1_test = exact_sign_flip_pvalue(by_split["test"], h1_value)

    test_assessment = {
        item["unit_id"]: item for item in assessments if item["split"] == "test"
    }
    h2_candidates = [
        record for record in by_split["test"] if record["action_arm"] != "no_action"
    ]
    h2_value = lambda record: float(
        test_assessment[record["unit_id"]]["harm_if_selective"]
    ) - float(record["harmful_action"])
    h2_ci = block_bootstrap_mean(h2_candidates, h2_value, seed=6102)
    h2_test = exact_sign_flip_pvalue(h2_candidates, h2_value)
    adjusted = holm_adjust(
        {
            "H1": float(h1_test["exact_one_sided_pvalue"]),
            "H2": float(h2_test["exact_one_sided_pvalue"]),
        }
    )
    h1_supported = h1_ci["ci95"][1] < 0.0 and adjusted["H1"] < 0.05
    h2_supported = (
        h2_ci["ci95"][1] < 0.0
        and selective["test"]["coverage"] >= 0.50
        and adjusted["H2"] < 0.05
    )

    if h1_supported and h2_supported:
        h3_evaluation = _policy_evaluation(
            by_split["test"], model, assessment_by_id
        )
        h3_status = "supported" if h3_evaluation["support_gate_passed"] else "not-supported"
    else:
        h3_evaluation = None
        h3_status = "gated-not-run"

    contrasts = _effect_contrasts(records)
    causal = causal_effect_report(contrasts)
    prediction_rows = []
    for record in records:
        row = {
            "unit_id": record["unit_id"],
            "assignment_block_id": record["assignment_block_id"],
            "split": record["split"],
            "fault_family": record["fault_family"],
            "action_arm": record["action_arm"],
            "observed_post_action_user_plane_burden": record[
                "post_action_user_plane_burden"
            ],
            "predictions": {
                name: predictor(record) for name, predictor in predictors.items()
            },
            "assessment": assessment_by_id[record["unit_id"]],
            "evidence_label": record["evidence_label"],
            "radio_evidence_label": record["radio_evidence_label"],
        }
        prediction_rows.append(row)

    report = {
        "schema_version": 1,
        "dataset_version": "safetwin5g-interventions-v1",
        "split_sizes": expected,
        "model": {
            "kind": "regularized action-conditional outcome model",
            "target": "post-action user-plane burden",
            "alpha": model.alpha,
            "alpha_trials": alpha_trials,
            "fit_split": "train",
            "fitted_unit_ids": list(model.fitted_unit_ids),
            "hyperparameter_selection_split": "calibration",
            "feature_boundary": (
                "fault family, severity, assigned action, workload identity, and "
                "pre-action fault-window metrics only"
            ),
        },
        "baselines": {
            "evaluation": evaluation,
            "test_ranking_by_mae": ranking,
            "test_winner": ranking[0],
        },
        "causal_action_contrasts": {
            "identification_status": (
                "identified for the measured sandbox action-arm contrasts conditional "
                "on clean-reset consistency, no interference, and block exchangeability"
            ),
            "estimand": "mean post-action user-plane burden difference versus no action",
            "effects": causal,
            "alternative_action_positivity": True,
            "post_treatment_rollback_used_as_control": False,
        },
        "uncertainty": {
            "calibration": calibration.to_dict(),
            "test_empirical_coverage": empirical_interval_coverage(
                by_split["test"], model.predict, calibration
            ),
            "ood_empirical_coverage": empirical_interval_coverage(
                by_split["ood"], model.predict, calibration
            ),
        },
        "ood": {
            "kind": "development severity-and-workload support detector",
            "severity_ranges": detector.severity_ranges,
            "workloads": list(detector.workloads),
            "fitted_unit_ids": list(detector.fitted_unit_ids),
            "test_ood_count": sum(
                detector.evaluate(record)["is_ood"] for record in by_split["test"]
            ),
            "ood_split_ood_count": sum(
                detector.evaluate(record)["is_ood"] for record in by_split["ood"]
            ),
            "test_n": len(by_split["test"]),
            "ood_n": len(by_split["ood"]),
            "probabilistic_calibration": "not claimed",
        },
        "selective_safety": selective,
        "hypotheses": {
            "H1": {
                "status": "supported" if h1_supported else "not-supported",
                "primary_contrast": "model minus temporal absolute prediction error",
                "estimate_and_ci": h1_ci,
                "exact_test": h1_test,
                "holm_adjusted_pvalue": adjusted["H1"],
                "gate": "upper 95% CI below zero and Holm-adjusted p < 0.05",
                "gate_passed": h1_supported,
            },
            "H2": {
                "status": "supported" if h2_supported else "not-supported",
                "primary_contrast": (
                    "selective minus always-act harmful-action incidence across "
                    "locked test action candidates"
                ),
                "estimate_and_ci": h2_ci,
                "exact_test": h2_test,
                "holm_adjusted_pvalue": adjusted["H2"],
                "coverage": selective["test"]["coverage"],
                "minimum_coverage": 0.50,
                "gate": (
                    "upper 95% CI below zero, coverage >= 0.50, and "
                    "Holm-adjusted p < 0.05"
                ),
                "gate_passed": h2_supported,
            },
            "H3": {
                "status": h3_status,
                "gate": "evaluate only if H1 and H2 pass",
                "evaluation": h3_evaluation,
            },
            "multiplicity": {
                "family": ["H1", "H2"],
                "method": "Holm",
                "unadjusted_pvalues": {
                    "H1": h1_test["exact_one_sided_pvalue"],
                    "H2": h2_test["exact_one_sided_pvalue"],
                },
                "adjusted_pvalues": adjusted,
            },
        },
        "diagnostics": {
            "future_outcome_leakage": _leakage_check(records, model),
            "complete_action_blocks": 44,
            "calibration_units": len(by_split["calibration"]),
            "calibration_minimum_met": len(by_split["calibration"]) >= 19,
            "negative_control_harmful_count": sum(
                record["action_arm"] == "negative_control" and record["harmful_action"]
                for record in records
            ),
            "no_fault_false_remediation_count": sum(
                record["false_remediation"] for record in records
            ),
        },
        "promotion": {
            "model_promotion": (
                "go"
                if h1_supported
                and h2_supported
                and h3_status == "supported"
                and ranking[0] == "action_conditional_ridge"
                else "no-go"
            ),
            "live_actuation": "no-go",
            "reasons": [],
        },
        "statistical_confidence": {
            "internal_sandbox_contrasts": "moderate",
            "external_validity": "low",
            "notes": [
                "Primary test inference uses seven independent test assignment blocks.",
                "Block bootstrap confidence intervals use 10,000 frozen-seed resamples.",
                "Exact one-sided sign-flip tests enumerate all 128 block sign patterns.",
                "H1 and H2 p-values use the preregistered Holm adjustment.",
                "The single-host simulated-radio campaign does not establish hardware or operator effects.",
            ],
        },
        "evidence_label": "sandbox-measured",
        "radio_evidence_label": "simulated",
        "hardware_evidence_label": None,
        "operator_validation": False,
    }
    promotion_reasons = report["promotion"]["reasons"]
    if not h1_supported:
        promotion_reasons.append("H1 superiority gate failed.")
    if not h2_supported:
        promotion_reasons.append("H2 harm-reduction/coverage gate failed.")
    if h3_status != "supported":
        promotion_reasons.append(f"H3 status is {h3_status}.")
    if ranking[0] != "action_conditional_ridge":
        promotion_reasons.append(
            f"The locked test MAE winner is {ranking[0]}, not the learned model."
        )
    promotion_reasons.append("Live actuation remains prohibited regardless of sandbox results.")
    return report, prediction_rows, contrasts
