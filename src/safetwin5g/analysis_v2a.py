"""Sealed block-level BRACE-v1 evaluation for the Phase 7 v2a campaign."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
from math import ceil, comb, sqrt
from pathlib import Path
import random
import statistics
from typing import Any, Iterable, Mapping

from .baselines import Standardizer, solve
from .brace import (
    BlockConformalCalibration,
    BraceSafetyContext,
    assess_brace_actions,
)
from .dataset_v2a import ACTION_IDS, MUTATING_ACTION_IDS


FAMILIES = (
    "cpu_saturation",
    "network_function_interruption",
    "no_fault",
    "packet_impairment",
)
ALPHAS = (0.01, 0.1, 1.0, 10.0, 100.0, 1000.0)
RUNBOOK = {
    "packet_impairment": "clear_packet_impairment",
    "network_function_interruption": "resume_upf",
    "cpu_saturation": "stop_cpu_stress",
    "no_fault": None,
}


def load_records(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def percentile(values: list[float], probability: float) -> float:
    if not values:
        raise ValueError("percentile requires values")
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def describe(values: Iterable[float]) -> dict[str, float | int | None]:
    items = [float(value) for value in values]
    if not items:
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
    p25 = percentile(items, 0.25)
    p75 = percentile(items, 0.75)
    return {
        "n": len(items),
        "mean": statistics.fmean(items),
        "median": statistics.median(items),
        "standard_deviation": statistics.stdev(items) if len(items) > 1 else 0.0,
        "minimum": min(items),
        "p25": p25,
        "p75": p75,
        "iqr": p75 - p25,
        "p90": percentile(items, 0.90),
        "maximum": max(items),
    }


def holm_adjust(pvalues: Mapping[str, float]) -> dict[str, float]:
    ordered = sorted(pvalues, key=lambda key: (pvalues[key], key))
    adjusted: dict[str, float] = {}
    running = 0.0
    for index, key in enumerate(ordered):
        candidate = min(1.0, (len(ordered) - index) * float(pvalues[key]))
        running = max(running, candidate)
        adjusted[key] = running
    return adjusted


def binomial_cdf(successes: int, trials: int, probability: float) -> float:
    if trials < 0 or not 0 <= successes <= trials or not 0.0 <= probability <= 1.0:
        raise ValueError("invalid binomial parameters")
    return sum(
        comb(trials, index)
        * probability**index
        * (1.0 - probability) ** (trials - index)
        for index in range(successes + 1)
    )


def clopper_pearson_upper(
    successes: int, trials: int, *, confidence: float = 0.95
) -> float | None:
    """Return the exact one-sided upper bound by binomial-CDF inversion."""

    if trials == 0:
        return None
    if successes == trials:
        return 1.0
    alpha = 1.0 - confidence
    lower, upper = 0.0, 1.0
    for _ in range(100):
        midpoint = (lower + upper) / 2.0
        if binomial_cdf(successes, trials, midpoint) > alpha:
            lower = midpoint
        else:
            upper = midpoint
    return (lower + upper) / 2.0


def wilson_interval(successes: int, trials: int, z: float = 1.959963984540054) -> list[float] | None:
    if trials == 0:
        return None
    proportion = successes / trials
    denominator = 1.0 + z * z / trials
    center = (proportion + z * z / (2.0 * trials)) / denominator
    half = (
        z
        * sqrt(proportion * (1.0 - proportion) / trials + z * z / (4.0 * trials * trials))
        / denominator
    )
    return [max(0.0, center - half), min(1.0, center + half)]


def paired_bootstrap_mean(
    differences: list[float], *, seed: int, iterations: int = 10_000
) -> dict[str, Any]:
    if not differences:
        return {
            "n": 0,
            "estimate": None,
            "ci95": None,
            "standardized_effect": None,
            "bootstrap_iterations": iterations,
            "bootstrap_seed": seed,
        }
    rng = random.Random(seed)
    estimates = [
        statistics.fmean(rng.choice(differences) for _ in differences)
        for _ in range(iterations)
    ]
    standard_deviation = statistics.stdev(differences) if len(differences) > 1 else 0.0
    estimate = statistics.fmean(differences)
    return {
        "n": len(differences),
        "estimate": estimate,
        "ci95": [percentile(estimates, 0.025), percentile(estimates, 0.975)],
        "standardized_effect": estimate / standard_deviation if standard_deviation else None,
        "bootstrap_iterations": iterations,
        "bootstrap_seed": seed,
    }


def paired_harm_pvalue(brace_harm: list[int], point_harm: list[int]) -> dict[str, Any]:
    if len(brace_harm) != len(point_harm):
        raise ValueError("paired policies must have the same block denominator")
    brace_only = sum(left == 1 and right == 0 for left, right in zip(brace_harm, point_harm))
    point_only = sum(left == 0 and right == 1 for left, right in zip(brace_harm, point_harm))
    discordant = brace_only + point_only
    pvalue = binomial_cdf(brace_only, discordant, 0.5) if discordant else 1.0
    return {
        "alternative": "BRACE harmful incidence is lower",
        "brace_only_harm_blocks": brace_only,
        "point_only_harm_blocks": point_only,
        "discordant_blocks": discordant,
        "exact_one_sided_pvalue": pvalue,
    }


def _mean_fault_metric(record: dict[str, Any], metric: str) -> float:
    values = [
        sample["metrics"].get(metric)
        for sample in record["windows"]["fault"]["samples"]
    ]
    measured = [float(value) for value in values if value is not None]
    if not measured:
        raise ValueError(f"missing fault metric {metric} for {record['unit_id']}")
    return statistics.fmean(measured)


def complete_blocks(records: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    blocks: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in records:
        block = blocks[record["assignment_block_id"]]
        action_id = record["action_id"]
        if action_id in block:
            raise ValueError(f"duplicate action {action_id} in {record['assignment_block_id']}")
        block[action_id] = record
    for block_id, block in blocks.items():
        if set(block) != set(ACTION_IDS):
            raise ValueError(f"incomplete named-action block: {block_id}")
        metadata = {
            (row["split"], row["fault_family"], row["severity_value"], row["seed"], row["workload"])
            for row in block.values()
        }
        if len(metadata) != 1:
            raise ValueError(f"inconsistent metadata inside block: {block_id}")
    return dict(blocks)


def _reference(block: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return block["observe_only"]


def raw_benefit_features(
    block: dict[str, dict[str, Any]], action_id: str
) -> list[float]:
    if action_id not in MUTATING_ACTION_IDS:
        raise ValueError("benefit model only predicts frozen mutating actions")
    reference = _reference(block)
    family = reference["fault_family"]
    family_flags = [float(family == item) for item in FAMILIES]
    action_flags = [float(action_id == item) for item in MUTATING_ACTION_IDS]
    interactions = [
        float(family == family_name and action_id == candidate)
        for family_name in FAMILIES
        for candidate in MUTATING_ACTION_IDS
    ]
    severity_by_family = [
        float(reference["severity_value"]) if family == item else 0.0
        for item in FAMILIES
    ]
    fault_metrics = [
        _mean_fault_metric(reference, name)
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
        + action_flags
        + interactions
        + severity_by_family
        + fault_metrics
        + [float(reference["workload"] == "sustained")]
    )


@dataclass(frozen=True)
class ActionBenefitRidge:
    coefficients: tuple[float, ...]
    standardizer: Standardizer
    alpha: float
    fitted_block_ids: tuple[str, ...]

    @classmethod
    def fit(
        cls, blocks: Mapping[str, dict[str, dict[str, Any]]], alpha: float
    ) -> "ActionBenefitRidge":
        rows = [
            (block_id, action_id, block[action_id])
            for block_id, block in sorted(blocks.items())
            for action_id in MUTATING_ACTION_IDS
        ]
        features = [raw_benefit_features(blocks[block_id], action_id) for block_id, action_id, _ in rows]
        targets = [float(record["observed_action_benefit"]) for _, _, record in rows]
        standardizer = Standardizer.fit(features)
        design = [[1.0] + standardizer.transform(feature) for feature in features]
        width = len(design[0])
        gram = [[0.0 for _ in range(width)] for _ in range(width)]
        rhs = [0.0 for _ in range(width)]
        for row, target in zip(design, targets, strict=True):
            for i in range(width):
                rhs[i] += row[i] * target
                for j in range(width):
                    gram[i][j] += row[i] * row[j]
        for index in range(1, width):
            gram[index][index] += float(alpha)
        return cls(
            coefficients=tuple(solve(gram, rhs)),
            standardizer=standardizer,
            alpha=float(alpha),
            fitted_block_ids=tuple(sorted(blocks)),
        )

    def predict(self, block: dict[str, dict[str, Any]], action_id: str) -> float:
        feature = raw_benefit_features(block, action_id)
        row = [1.0] + self.standardizer.transform(feature)
        return sum(value * coefficient for value, coefficient in zip(row, self.coefficients))

    def predict_vector(self, block: dict[str, dict[str, Any]]) -> dict[str, float]:
        return {action: self.predict(block, action) for action in MUTATING_ACTION_IDS}


def select_alpha_lobo(
    train_blocks: Mapping[str, dict[str, dict[str, Any]]],
    *,
    alphas: tuple[float, ...] = ALPHAS,
) -> tuple[float, list[dict[str, float]]]:
    if len(train_blocks) < 3:
        raise ValueError("leave-one-block-out selection requires at least three blocks")
    trials = []
    for alpha in alphas:
        errors = []
        for holdout_id in sorted(train_blocks):
            fitting = {key: value for key, value in train_blocks.items() if key != holdout_id}
            model = ActionBenefitRidge.fit(fitting, alpha)
            holdout = train_blocks[holdout_id]
            for action_id in MUTATING_ACTION_IDS:
                errors.append(
                    abs(model.predict(holdout, action_id) - float(holdout[action_id]["observed_action_benefit"]))
                )
        trials.append({"alpha": float(alpha), "lobo_mae": statistics.fmean(errors)})
    winner = min(trials, key=lambda item: (item["lobo_mae"], item["alpha"]))
    return float(winner["alpha"]), trials


def _conformal_radius(residuals: list[float], coverage: float) -> dict[str, Any]:
    rank = ceil((len(residuals) + 1) * coverage)
    radius = sorted(residuals)[rank - 1] if rank <= len(residuals) else None
    return {
        "coverage": coverage,
        "calibration_n": len(residuals),
        "rank": rank,
        "radius": radius,
        "status": "finite" if radius is not None else "unbounded",
    }


def fit_calibrations(
    calibration_blocks: Mapping[str, dict[str, dict[str, Any]]],
    model: ActionBenefitRidge,
    *,
    coverage: float = 0.90,
) -> dict[str, Any]:
    brace_rows = {
        block_id: {
            action: (
                model.predict(block, action),
                float(block[action]["observed_action_benefit"]),
            )
            for action in MUTATING_ACTION_IDS
        }
        for block_id, block in calibration_blocks.items()
    }
    brace = BlockConformalCalibration.fit(
        brace_rows, action_ids=MUTATING_ACTION_IDS, coverage=coverage
    )
    scalar_residuals = [
        abs(predicted - observed)
        for actions in brace_rows.values()
        for predicted, observed in actions.values()
    ]
    action_conditional = {
        action: _conformal_radius(
            [abs(actions[action][0] - actions[action][1]) for actions in brace_rows.values()],
            coverage,
        )
        for action in MUTATING_ACTION_IDS
    }
    return {
        "brace": brace,
        "scalar": _conformal_radius(scalar_residuals, coverage),
        "action_conditional": action_conditional,
    }


def _selected_row(
    block_id: str,
    block: dict[str, dict[str, Any]],
    policy: str,
    action_id: str | None,
    predictions: Mapping[str, float],
    *,
    lower_bound: float | None = None,
    certified: bool = False,
    reason: str,
) -> dict[str, Any]:
    reference = _reference(block)
    selected = block[action_id] if action_id is not None else reference
    return {
        "assignment_block_id": block_id,
        "split": reference["split"],
        "fault_family": reference["fault_family"],
        "severity_value": float(reference["severity_value"]),
        "workload": reference["workload"],
        "policy": policy,
        "selected_action_id": action_id,
        "mutated": action_id is not None,
        "certified": certified,
        "predicted_benefit": predictions.get(action_id) if action_id else 0.0,
        "lower_benefit_bound": lower_bound,
        "observed_benefit": float(selected["observed_action_benefit"]) if action_id else 0.0,
        "violates_benefit_margin": bool(action_id and selected["violates_benefit_margin"]),
        "harmful_action": bool(action_id and selected["harmful_action"]),
        "false_remediation": bool(action_id and selected["false_remediation"]),
        "reason": reason,
    }


def evaluate_policies(
    blocks: Mapping[str, dict[str, dict[str, Any]]],
    model: ActionBenefitRidge,
    calibrations: dict[str, Any],
    *,
    is_ood: bool,
    minimum_margin: float = 5.0,
) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    brace: BlockConformalCalibration = calibrations["brace"]
    for block_id, block in sorted(blocks.items()):
        predictions = model.predict_vector(block)
        family = _reference(block)["fault_family"]
        rows["observe_only"].append(
            _selected_row(block_id, block, "observe_only", None, predictions, reason="frozen fallback")
        )
        runbook_action = RUNBOOK[family]
        rows["deterministic_runbook"].append(
            _selected_row(
                block_id,
                block,
                "deterministic_runbook",
                runbook_action,
                predictions,
                reason="frozen family-to-action mapping" if runbook_action else "no-fault fallback",
            )
        )
        best_action = min(MUTATING_ACTION_IDS, key=lambda action: (-predictions[action], action))
        rows["point_estimate_policy"].append(
            _selected_row(
                block_id,
                block,
                "point_estimate_policy",
                best_action,
                predictions,
                reason="largest predicted benefit without uncertainty",
            )
        )

        scalar = calibrations["scalar"]
        scalar_candidates = [] if scalar["radius"] is None or is_ood else [
            (predictions[action] - scalar["radius"], action)
            for action in MUTATING_ACTION_IDS
            if predictions[action] - scalar["radius"] > minimum_margin
        ]
        scalar_choice = min(scalar_candidates, key=lambda item: (-item[0], item[1])) if scalar_candidates else None
        rows["scalar_split_conformal"].append(
            _selected_row(
                block_id,
                block,
                "scalar_split_conformal",
                scalar_choice[1] if scalar_choice else None,
                predictions,
                lower_bound=scalar_choice[0] if scalar_choice else None,
                certified=bool(scalar_choice),
                reason="scalar lower bound exceeds margin" if scalar_choice else "abstain",
            )
        )

        conditional_candidates = []
        if not is_ood:
            for action in MUTATING_ACTION_IDS:
                radius = calibrations["action_conditional"][action]["radius"]
                if radius is not None and predictions[action] - radius > minimum_margin:
                    conditional_candidates.append((predictions[action] - radius, action))
        conditional_choice = (
            min(conditional_candidates, key=lambda item: (-item[0], item[1]))
            if conditional_candidates
            else None
        )
        rows["action_conditional_conformal"].append(
            _selected_row(
                block_id,
                block,
                "action_conditional_conformal",
                conditional_choice[1] if conditional_choice else None,
                predictions,
                lower_bound=conditional_choice[0] if conditional_choice else None,
                certified=bool(conditional_choice),
                reason="per-action lower bound exceeds margin" if conditional_choice else "abstain",
            )
        )

        context = BraceSafetyContext(
            environment="sandbox",
            evidence_label="sandbox-measured",
            radio_evidence_label="simulated",
            hardware_evidence_label=None,
            operator_validation=False,
            is_ood=is_ood,
            allowlisted_actions=MUTATING_ACTION_IDS,
            reversible_actions=tuple(
                action for action in MUTATING_ACTION_IDS if block[action]["reversible"]
            ),
            rollback_plan_actions=tuple(
                action for action in MUTATING_ACTION_IDS if block[action]["rollback_plan_recorded"]
            ),
        )
        decision = assess_brace_actions(
            predictions, brace, context, minimum_benefit_margin=minimum_margin
        )
        rows["BRACE-v1"].append(
            _selected_row(
                block_id,
                block,
                "BRACE-v1",
                decision.selected_action_id,
                predictions,
                lower_bound=decision.lower_benefit_bound,
                certified=decision.decision == "require-human-approval",
                reason="; ".join(decision.reasons),
            )
        )
    return dict(rows)


def _policy_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    mutations = [row for row in rows if row["mutated"]]
    faulty = [row for row in rows if row["fault_family"] != "no_fault"]
    faulty_mutations = [row for row in faulty if row["mutated"]]
    return {
        "block_n": len(rows),
        "faulty_block_n": len(faulty),
        "mutation_n": len(mutations),
        "faulty_mutation_n": len(faulty_mutations),
        "faulty_mutation_coverage": len(faulty_mutations) / len(faulty) if faulty else None,
        "harmful_action_n": sum(row["harmful_action"] for row in rows),
        "harmful_action_rate_all_blocks": sum(row["harmful_action"] for row in rows) / len(rows),
        "harmful_action_rate_given_mutation": (
            sum(row["harmful_action"] for row in mutations) / len(mutations) if mutations else None
        ),
        "false_remediation_n": sum(row["false_remediation"] for row in rows),
        "benefit_margin_violation_n": sum(row["violates_benefit_margin"] for row in mutations),
        "observed_benefit": describe(row["observed_benefit"] for row in mutations),
        "predicted_benefit": describe(row["predicted_benefit"] for row in mutations),
    }


def vector_coverage(
    blocks: Mapping[str, dict[str, dict[str, Any]]],
    model: ActionBenefitRidge,
    calibration: BlockConformalCalibration,
) -> dict[str, Any]:
    if calibration.radius is None:
        return {"block_n": len(blocks), "covered_block_n": 0, "coverage": 0.0, "ci95": None}
    covered = 0
    per_block = []
    for block_id, block in sorted(blocks.items()):
        predictions = model.predict_vector(block)
        residuals = {
            action: abs(predictions[action] - float(block[action]["observed_action_benefit"]))
            for action in MUTATING_ACTION_IDS
        }
        is_covered = max(residuals.values()) <= calibration.radius
        covered += int(is_covered)
        per_block.append({"assignment_block_id": block_id, "covered": is_covered, "residuals": residuals})
    return {
        "block_n": len(blocks),
        "covered_block_n": covered,
        "coverage": covered / len(blocks),
        "ci95": wilson_interval(covered, len(blocks)),
        "per_block": per_block,
    }


def matched_point_rows(
    brace_rows: list[dict[str, Any]], point_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    faulty_brace = [row for row in brace_rows if row["fault_family"] != "no_fault"]
    target_n = sum(row["mutated"] for row in faulty_brace)
    faulty_point = [row.copy() for row in point_rows if row["fault_family"] != "no_fault"]
    selected_ids = {
        row["assignment_block_id"]
        for row in sorted(
            faulty_point,
            key=lambda row: (-float(row["predicted_benefit"]), row["assignment_block_id"]),
        )[:target_n]
    }
    matched = []
    for row in point_rows:
        item = row.copy()
        if item["fault_family"] == "no_fault" or item["assignment_block_id"] not in selected_ids:
            item.update(
                selected_action_id=None,
                mutated=False,
                certified=False,
                observed_benefit=0.0,
                violates_benefit_margin=False,
                harmful_action=False,
                false_remediation=False,
                reason="not selected at BRACE-matched faulty-block coverage",
            )
        item["policy"] = "point_estimate_policy_matched_coverage"
        matched.append(item)
    return matched


def analyze(records: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    blocks = complete_blocks(records)
    split_blocks = {
        split: {block_id: block for block_id, block in blocks.items() if _reference(block)["split"] == split}
        for split in ("train", "calibration", "test", "ood")
    }
    expected = {"train": 28, "calibration": 21, "test": 70, "ood": 16}
    observed = {split: len(items) for split, items in split_blocks.items()}
    if observed != expected:
        raise ValueError(f"Phase 7 block counts differ from frozen design: {observed}")

    alpha, alpha_trials = select_alpha_lobo(split_blocks["train"])
    model = ActionBenefitRidge.fit(split_blocks["train"], alpha)
    calibrations = fit_calibrations(split_blocks["calibration"], model)
    test_policies = evaluate_policies(
        split_blocks["test"], model, calibrations, is_ood=False
    )
    ood_policies = evaluate_policies(
        split_blocks["ood"], model, calibrations, is_ood=True
    )
    matched = matched_point_rows(
        test_policies["BRACE-v1"], test_policies["point_estimate_policy"]
    )
    test_policies["point_estimate_policy_matched_coverage"] = matched

    g1 = vector_coverage(split_blocks["test"], model, calibrations["brace"])
    brace_rows = test_policies["BRACE-v1"]
    faulty_brace = [row for row in brace_rows if row["fault_family"] != "no_fault"]
    certified = [row for row in faulty_brace if row["mutated"]]
    violations = sum(row["violates_benefit_margin"] for row in certified)
    g2_pvalue = binomial_cdf(violations, len(certified), 0.10) if certified else 1.0
    g2_upper = clopper_pearson_upper(violations, len(certified))

    brace_by_id = {row["assignment_block_id"]: row for row in brace_rows}
    point_by_id = {row["assignment_block_id"]: row for row in matched}
    comparison_ids = sorted(
        block_id
        for block_id, row in brace_by_id.items()
        if row["fault_family"] != "no_fault"
    )
    brace_harm = [int(brace_by_id[key]["harmful_action"]) for key in comparison_ids]
    point_harm = [int(point_by_id[key]["harmful_action"]) for key in comparison_ids]
    g3_exact = paired_harm_pvalue(brace_harm, point_harm)
    paired_differences = [left - right for left, right in zip(brace_harm, point_harm, strict=True)]
    g3_effect = paired_bootstrap_mean(paired_differences, seed=7303)
    adjusted = holm_adjust(
        {"G2": g2_pvalue, "G3": g3_exact["exact_one_sided_pvalue"]}
    )

    g1_passed = g1["coverage"] >= 0.90
    g2_passed = (
        violations == 0
        and len(certified) >= 29
        and len(certified) / len(faulty_brace) >= 0.50
        and g2_upper is not None
        and g2_upper < 0.10
        and adjusted["G2"] < 0.05
    )
    point_harm_n = sum(point_harm)
    brace_harm_n = sum(brace_harm)
    g3_passed = (
        point_harm_n > 0
        and brace_harm_n < point_harm_n
        and g3_effect["ci95"] is not None
        and g3_effect["ci95"][1] < 0.0
        and adjusted["G3"] < 0.05
    )
    g4_checks = {
        "all_units_have_approval_id": all(record["approval_id"] for record in records),
        "all_mutations_require_human_approval": all(
            not record["action_applied"] or record["safety_decision"] == "require-human-approval"
            for record in records
        ),
        "all_mutations_reversible": all(
            not record["action_applied"] or record["reversible"] for record in records
        ),
        "all_mutations_have_rollback_plan": all(
            not record["action_applied"] or record["rollback_plan_recorded"] for record in records
        ),
        "all_units_cleanup_verified": all(record["cleanup_verified"] for record in records),
    }
    g4_passed = all(g4_checks.values())

    ood_brace = ood_policies["BRACE-v1"]
    ood_without_gate = evaluate_policies(
        split_blocks["ood"], model, calibrations, is_ood=False
    )["BRACE-v1"]
    brace_test_certified = [row for row in brace_rows if row["mutated"]]
    report = {
        "schema_version": 2,
        "dataset_version": "safetwin5g-named-actions-v2a",
        "method": "BRACE-v1",
        "split_block_counts": observed,
        "model": {
            "kind": "action-conditional ridge benefit predictor",
            "target": "observe-only burden minus named-action burden",
            "alpha": alpha,
            "selection": "train-block leave-one-block-out MAE only",
            "alpha_trials": alpha_trials,
            "fitted_block_ids": list(model.fitted_block_ids),
            "calibration_used_for_model_selection": False,
            "test_or_ood_used_for_fit_or_selection": False,
            "features": "block context plus observe-only pre-action fault telemetry and named action",
        },
        "calibration": {
            "BRACE-v1": calibrations["brace"].guarantee_contract(),
            "scalar_split_conformal": calibrations["scalar"],
            "action_conditional_conformal": calibrations["action_conditional"],
        },
        "policies": {
            "test": {name: _policy_summary(rows) for name, rows in test_policies.items()},
            "ood": {name: _policy_summary(rows) for name, rows in ood_policies.items()},
        },
        "gates": {
            "G1": {
                **g1,
                "threshold": 0.90,
                "passed": g1_passed,
            },
            "G2": {
                "faulty_test_block_n": len(faulty_brace),
                "certified_mutation_n": len(certified),
                "certified_mutation_coverage": len(certified) / len(faulty_brace),
                "margin_violation_n": violations,
                "exact_one_sided_95_upper_violation_rate": g2_upper,
                "unadjusted_pvalue_against_rate_0_10": g2_pvalue,
                "holm_adjusted_pvalue": adjusted["G2"],
                "passed": g2_passed,
            },
            "G3": {
                "matched_faulty_block_n": len(comparison_ids),
                "matched_mutation_n_each_policy": len(certified),
                "brace_harm_n": brace_harm_n,
                "point_policy_harm_n": point_harm_n,
                "paired_difference": g3_effect,
                "exact_paired_test": g3_exact,
                "holm_adjusted_pvalue": adjusted["G3"],
                "strict_improvement_requires_point_harms": True,
                "passed": g3_passed,
            },
            "G4": {"checks": g4_checks, "passed": g4_passed},
            "multiplicity": {
                "family": ["G2", "G3"],
                "method": "Holm",
                "adjusted_pvalues": adjusted,
            },
        },
        "ablations": {
            "without_joint_block_score": {
                "implemented_as": "scalar_split_conformal",
                "test": _policy_summary(test_policies["scalar_split_conformal"]),
            },
            "without_ood_gate": {
                "ood_proposal_n": sum(row["mutated"] for row in ood_without_gate),
                "full_BRACE_ood_proposal_n": sum(row["mutated"] for row in ood_brace),
            },
            "without_rollback_precondition": {
                "test_certificates_that_would_survive_if_rollback_metadata_were_removed": len(brace_test_certified),
                "full_BRACE_certificates_with_missing_rollback": 0,
                "scope": "logical guard ablation; not an applied mutation experiment",
            },
        },
        "ood": {
            "block_n": len(ood_brace),
            "BRACE_abstention_n": sum(not row["mutated"] for row in ood_brace),
            "BRACE_abstention_rate": sum(not row["mutated"] for row in ood_brace) / len(ood_brace),
            "empirical_vector_coverage_diagnostic": vector_coverage(
                split_blocks["ood"], model, calibrations["brace"]
            ),
            "primary_gate_contribution": False,
        },
        "decision": {
            "all_primary_gates_passed": g1_passed and g2_passed and g3_passed and g4_passed,
            "TNSM_claim_gate": (
                "go" if g1_passed and g2_passed and g3_passed and g4_passed else "no-go"
            ),
            "live_actuation": "no-go",
            "submission_authorized": False,
        },
        "claim_boundaries": {
            "evidence_label": "sandbox-measured",
            "radio_evidence_label": "simulated",
            "hardware_evidence_label": None,
            "operator_validation": False,
            "conditional_coverage_claimed": False,
            "live_network_claimed": False,
        },
    }
    policy_rows = [row for rows in test_policies.values() for row in rows] + [
        row for rows in ood_policies.values() for row in rows
    ]
    return report, policy_rows
