"""Leakage, calibration, and negative-control diagnostics."""

from __future__ import annotations

from copy import deepcopy
from itertools import permutations
from math import ceil
from typing import Any, Callable


def split_group_overlaps(records: list[dict[str, Any]]) -> dict[str, list[str]]:
    groups: dict[str, set[str]] = {}
    for record in records:
        groups.setdefault(record["group_id"], set()).add(record["split"])
    return {
        group: sorted(splits) for group, splits in groups.items() if len(splits) > 1
    }


def future_outcome_leakage_check(
    records: list[dict[str, Any]], predictor: Callable[[dict[str, Any]], float]
) -> dict[str, Any]:
    differences = []
    for record in records:
        original = predictor(record)
        mutated = deepcopy(record)
        mutated["observed_benefit"] = 1_000_000.0
        mutated["treatment_outcome"] = -1_000_000.0
        mutated["rollback_control_outcome"] = 1_000_000.0
        mutated["stages"]["post-action"]["metrics"] = {
            key: 1_000_000.0
            for key in mutated["stages"]["post-action"]["metrics"]
        }
        mutated["stages"]["rollback"]["metrics"] = {
            key: -1_000_000.0
            for key in mutated["stages"]["rollback"]["metrics"]
        }
        differences.append(abs(original - predictor(mutated)))
    return {
        "passed": max(differences, default=0.0) == 0.0,
        "max_prediction_change": max(differences, default=0.0),
        "mutated_fields": [
            "observed_benefit",
            "treatment_outcome",
            "rollback_control_outcome",
            "post-action metrics",
            "rollback metrics",
        ],
    }


def split_conformal_radius(
    residuals: list[float], coverage: float
) -> dict[str, Any]:
    if not 0.0 < coverage < 1.0:
        raise ValueError("coverage must be between zero and one")
    absolute = sorted(abs(value) for value in residuals)
    rank = ceil((len(absolute) + 1) * coverage)
    if rank > len(absolute):
        return {
            "coverage": coverage,
            "calibration_n": len(absolute),
            "rank": rank,
            "radius": None,
            "status": "unbounded-insufficient-calibration",
        }
    return {
        "coverage": coverage,
        "calibration_n": len(absolute),
        "rank": rank,
        "radius": absolute[rank - 1],
        "status": "finite",
    }


def final_state_placebo(records: list[dict[str, Any]]) -> dict[str, Any]:
    differences = [
        float(record["stages"]["final"]["metrics"]["packet_loss_pct"])
        - float(record["stages"]["baseline"]["metrics"]["packet_loss_pct"])
        for record in records
    ]
    return {
        "mean_difference_pct": sum(differences) / len(differences),
        "max_absolute_difference_pct": max(abs(value) for value in differences),
        "passed": max(abs(value) for value in differences) == 0.0,
    }


def permutation_control(
    records: list[dict[str, Any]], predictor: Callable[[dict[str, Any]], float]
) -> dict[str, Any]:
    predictions = [predictor(record) for record in records]
    observed = [float(record["observed_benefit"]) for record in records]

    def mae(targets: tuple[float, ...] | list[float]) -> float:
        return sum(
            abs(prediction - target) for prediction, target in zip(predictions, targets)
        ) / len(predictions)

    observed_mae = mae(observed)
    null_maes = [mae(values) for values in permutations(observed)]
    return {
        "n_permutations": len(null_maes),
        "observed_mae": observed_mae,
        "null_mae_min": min(null_maes),
        "null_mae_median": sorted(null_maes)[len(null_maes) // 2],
        "observed_is_strictly_better_than_all_permutations": observed_mae
        < min(value for value in null_maes if value != observed_mae)
        if len(set(null_maes)) > 1
        else False,
        "interpretation": "descriptive exact three-row permutation control; not a significance test",
    }
