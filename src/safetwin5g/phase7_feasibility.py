"""Exploratory BRACE feasibility checks on the already-opened v1 dataset."""

from __future__ import annotations

from collections import defaultdict
from math import log
import statistics
from typing import Any

from .analysis_v1 import ALPHAS, OutcomeRidge, describe
from .brace import (
    BlockConformalCalibration,
    BraceSafetyContext,
    assess_brace_actions,
)


LEGACY_MUTATING_ARMS = ("effective", "negative_control")


def _absolute_errors(
    records: list[dict[str, Any]], model: OutcomeRidge
) -> list[float]:
    return [
        abs(model.predict(record) - float(record["post_action_user_plane_burden"]))
        for record in records
    ]


def select_model_train_block_cv(
    train: list[dict[str, Any]],
) -> tuple[OutcomeRidge, list[dict[str, Any]]]:
    """Choose ridge strength without consuming calibration or held-out blocks."""

    block_ids = sorted({record["assignment_block_id"] for record in train})
    trials = []
    best: tuple[float, float] | None = None
    for alpha in ALPHAS:
        errors = []
        for held_out in block_ids:
            fit_rows = [
                record for record in train if record["assignment_block_id"] != held_out
            ]
            held_rows = [
                record for record in train if record["assignment_block_id"] == held_out
            ]
            fold_model = OutcomeRidge.fit(fit_rows, alpha)
            errors.extend(_absolute_errors(held_rows, fold_model))
        score = statistics.fmean(errors)
        trials.append(
            {
                "alpha": alpha,
                "leave_one_block_out_mae": score,
                "independent_fold_n": len(block_ids),
                "heldout_row_n": len(errors),
            }
        )
        candidate = (score, alpha)
        if best is None or candidate < best:
            best = candidate
    assert best is not None
    return OutcomeRidge.fit(train, best[1]), trials


def legacy_contrast_blocks(
    records: list[dict[str, Any]], model: OutcomeRidge
) -> dict[str, dict[str, tuple[float, float]]]:
    by_block: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
    for record in records:
        by_block[record["assignment_block_id"]][record["action_arm"]] = record
    result = {}
    for block_id, block in sorted(by_block.items()):
        if set(block) != {"effective", "negative_control", "no_action"}:
            raise ValueError(f"legacy block is incomplete: {block_id}")
        control = block["no_action"]
        control_prediction = model.predict(control)
        control_observed = float(control["post_action_user_plane_burden"])
        result[block_id] = {}
        for action_arm in LEGACY_MUTATING_ARMS:
            action = block[action_arm]
            result[block_id][action_arm] = (
                control_prediction - model.predict(action),
                control_observed - float(action["post_action_user_plane_burden"]),
            )
    return result


def _legacy_context(*, is_ood: bool) -> BraceSafetyContext:
    return BraceSafetyContext(
        environment="sandbox",
        evidence_label="sandbox-measured",
        radio_evidence_label="simulated",
        hardware_evidence_label=None,
        operator_validation=False,
        is_ood=is_ood,
        allowlisted_actions=LEGACY_MUTATING_ARMS,
        reversible_actions=LEGACY_MUTATING_ARMS,
        rollback_plan_actions=LEGACY_MUTATING_ARMS,
    )


def _decision_summary(
    blocks: dict[str, dict[str, tuple[float, float]]],
    calibration: BlockConformalCalibration,
    *,
    is_ood: bool,
) -> dict[str, Any]:
    decisions = []
    for block_id, actions in sorted(blocks.items()):
        predicted = {action: pair[0] for action, pair in actions.items()}
        decision = assess_brace_actions(
            predicted,
            calibration,
            _legacy_context(is_ood=is_ood),
            minimum_benefit_margin=5.0,
        )
        decisions.append(
            {
                "assignment_block_id": block_id,
                "decision": decision.decision,
                "selected_action_id": decision.selected_action_id,
                "reasons": list(decision.reasons),
            }
        )
    certified = sum(item["decision"] == "require-human-approval" for item in decisions)
    return {
        "independent_block_n": len(decisions),
        "certified_block_n": certified,
        "abstained_or_rejected_block_n": len(decisions) - certified,
        "certified_coverage": certified / len(decisions) if decisions else None,
        "decisions": decisions,
    }


def _one_sided_zero_event_upper_95(sample_n: int) -> float:
    if sample_n <= 0:
        raise ValueError("sample_n must be positive")
    return 1.0 - 0.05 ** (1.0 / sample_n)


def _minimum_zero_event_n(target_upper: float) -> int:
    if not 0.0 < target_upper < 1.0:
        raise ValueError("target_upper must lie in (0, 1)")
    return int(log(0.05) / log(1.0 - target_upper)) + 1


def analyze_v1_feasibility(
    records: list[dict[str, Any]], phase7_design: dict[str, Any]
) -> dict[str, Any]:
    by_split = {
        split: [record for record in records if record["split"] == split]
        for split in ("train", "calibration", "test", "ood")
    }
    model, trials = select_model_train_block_cv(by_split["train"])
    calibration_blocks = legacy_contrast_blocks(by_split["calibration"], model)
    calibration = BlockConformalCalibration.fit(
        calibration_blocks,
        action_ids=LEGACY_MUTATING_ARMS,
        coverage=0.90,
    )
    test_blocks = legacy_contrast_blocks(by_split["test"], model)
    ood_blocks = legacy_contrast_blocks(by_split["ood"], model)

    required_action_kinds = {
        action["action_kind"] for action in phase7_design["action_portfolio"]
    }
    observed_kinds: dict[str, set[str]] = defaultdict(set)
    for record in records:
        observed_kinds[record["assignment_block_id"]].add(record["action_kind"])
    strict_complete = sum(
        kinds == required_action_kinds for kinds in observed_kinds.values()
    )

    expected = phase7_design["expected_counts"]
    faulty_test_blocks = 6 * len(phase7_design["splits"]["test"]["seeds"])
    minimum_coverage = phase7_design["analysis"][
        "minimum_faulty_block_mutation_coverage"
    ]
    minimum_certified = int(faulty_test_blocks * minimum_coverage + 0.999999)
    minimum_for_empirical_ten_percent = _minimum_zero_event_n(0.10)

    return {
        "analysis_status": "exploratory-negative-design-result",
        "confirmatory_claim_allowed": False,
        "phase6_decision_changed": False,
        "evidence_label": "sandbox-measured",
        "radio_evidence_label": "simulated",
        "hardware_evidence_label": None,
        "operator_validation": False,
        "legacy_limitations": {
            "action_labels_encode_outcome_role": True,
            "legacy_mutating_action_ids": list(LEGACY_MUTATING_ARMS),
            "strict_phase7_named_action_complete_blocks": strict_complete,
            "observed_v1_block_n": len(observed_kinds),
            "strict_named_action_feasibility": "not-identified",
        },
        "model": {
            "selection": "leave-one-train-block-out only",
            "selected_alpha": model.alpha,
            "fitted_unit_ids": list(model.fitted_unit_ids),
            "trials": trials,
        },
        "legacy_block_calibration": {
            **calibration.guarantee_contract(),
            "score_distribution": describe(list(calibration.block_scores)),
        },
        "legacy_test": _decision_summary(
            test_blocks, calibration, is_ood=False
        ),
        "legacy_ood": _decision_summary(ood_blocks, calibration, is_ood=True),
        "prospective_v2_design_check": {
            "calibration_blocks": expected["blocks"]["calibration"],
            "calibration_rank_at_90pct": 20,
            "finite_radius_mathematically_possible": True,
            "test_blocks": expected["blocks"]["test"],
            "faulty_test_blocks": faulty_test_blocks,
            "minimum_certified_mutations_at_frozen_coverage": minimum_certified,
            "one_sided_95pct_zero_violation_upper_at_minimum_coverage": (
                _one_sided_zero_event_upper_95(minimum_certified)
            ),
            "one_sided_95pct_zero_violation_upper_if_all_faulty_blocks_certified": (
                _one_sided_zero_event_upper_95(faulty_test_blocks)
            ),
            "minimum_zero_violation_n_for_upper_below_0p10": (
                minimum_for_empirical_ten_percent
            ),
            "empirical_ten_percent_precision_at_minimum_coverage": "insufficient",
            "recommended_amendment": (
                "increase fresh test design to at least 60 faulty blocks if a "
                "one-sided 95% empirical upper bound below 0.10 at 50% coverage "
                "is required; otherwise keep the safety statement theorem-based"
            ),
        },
        "decision": {
            "legacy_v1_BRACE_promotion": "no-go",
            "fresh_v2_campaign": "required",
            "manuscript_positive_claim": "no-go-pending-fresh-evidence",
            "live_actuation": "no-go",
        },
    }
