"""Deterministic microbenchmark for BRACE calibration and proposal overhead."""

from __future__ import annotations

from math import log
import platform
import statistics
from time import perf_counter_ns
from typing import Any, Callable

from .brace import (
    BlockConformalCalibration,
    BraceSafetyContext,
    assess_brace_actions,
)
from .dataset_v2a import MUTATING_ACTION_IDS


def synthetic_contrast_blocks(block_n: int) -> dict[str, dict[str, tuple[float, float]]]:
    if block_n <= 0:
        raise ValueError("block_n must be positive")
    return {
        f"fixture-block-{index:06d}": {
            action: (
                10.0 + action_index + (index % 7) * 0.01,
                10.0 + action_index + (index % 7) * 0.01 + ((index + action_index) % 5 - 2) * 0.1,
            )
            for action_index, action in enumerate(MUTATING_ACTION_IDS)
        }
        for index in range(block_n)
    }


def _measure(callable_: Callable[[], Any], repeats: int) -> dict[str, Any]:
    if repeats < 3:
        raise ValueError("at least three repeats are required")
    callable_()
    elapsed_ms = []
    for _ in range(repeats):
        started = perf_counter_ns()
        callable_()
        elapsed_ms.append((perf_counter_ns() - started) / 1_000_000.0)
    return {
        "repeats": repeats,
        "median_ms": statistics.median(elapsed_ms),
        "mean_ms": statistics.fmean(elapsed_ms),
        "standard_deviation_ms": statistics.stdev(elapsed_ms),
        "minimum_ms": min(elapsed_ms),
        "maximum_ms": max(elapsed_ms),
        "all_elapsed_ms": elapsed_ms,
    }


def _log_slope(points: list[tuple[int, float]]) -> float:
    x = [log(float(size)) for size, _ in points]
    y = [log(max(elapsed, 1e-9)) for _, elapsed in points]
    x_mean = statistics.fmean(x)
    y_mean = statistics.fmean(y)
    denominator = sum((value - x_mean) ** 2 for value in x)
    return sum((left - x_mean) * (right - y_mean) for left, right in zip(x, y)) / denominator


def benchmark_brace(
    *,
    block_sizes: tuple[int, ...] = (21, 100, 500, 1000, 5000),
    repeats: int = 7,
    decision_batch_n: int = 10_000,
) -> dict[str, Any]:
    if len(block_sizes) < 3 or tuple(sorted(set(block_sizes))) != block_sizes:
        raise ValueError("block_sizes must contain at least three increasing unique values")
    calibration_rows = []
    fitted: BlockConformalCalibration | None = None
    for block_n in block_sizes:
        blocks = synthetic_contrast_blocks(block_n)

        def fit() -> BlockConformalCalibration:
            return BlockConformalCalibration.fit(
                blocks, action_ids=MUTATING_ACTION_IDS, coverage=0.90
            )

        timing = _measure(fit, repeats)
        fitted = fit()
        calibration_rows.append(
            {
                "block_n": block_n,
                "action_n": len(MUTATING_ACTION_IDS),
                "contrast_cell_n": block_n * len(MUTATING_ACTION_IDS),
                "rank": fitted.rank,
                "radius": fitted.radius,
                "status": fitted.status,
                "timing": timing,
            }
        )
    assert fitted is not None
    context = BraceSafetyContext(
        environment="sandbox",
        evidence_label="sandbox-measured",
        radio_evidence_label="simulated",
        hardware_evidence_label=None,
        operator_validation=False,
        is_ood=False,
        allowlisted_actions=MUTATING_ACTION_IDS,
        reversible_actions=MUTATING_ACTION_IDS,
        rollback_plan_actions=MUTATING_ACTION_IDS,
    )
    predictions = {action: 10.0 + index for index, action in enumerate(MUTATING_ACTION_IDS)}

    def decision_batch() -> None:
        for _ in range(decision_batch_n):
            decision = assess_brace_actions(
                predictions, fitted, context, minimum_benefit_margin=5.0
            )
            if decision.apply_allowed or decision.decision != "require-human-approval":
                raise AssertionError("fixture certificate violated the fail-closed contract")

    decision_timing = _measure(decision_batch, repeats)
    per_decision_us = 1000.0 * decision_timing["median_ms"] / decision_batch_n
    slope = _log_slope(
        [(row["block_n"], row["timing"]["median_ms"]) for row in calibration_rows]
    )
    return {
        "schema_version": 1,
        "benchmark": "BRACE-v1 calibration-and-proposal-microbenchmark",
        "input_evidence_label": "fixture",
        "runtime_measurement": "local-host-measured",
        "network_performance_claim": False,
        "radio_performance_claim": False,
        "hardware_or_operator_claim": False,
        "environment": {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "processor": platform.processor() or "not-reported",
        },
        "calibration": calibration_rows,
        "empirical_log_log_slope": slope,
        "expected_complexity": "O(B*A) residual scan plus O(B log B) score ordering",
        "decision_batch": {
            "decision_n_per_repeat": decision_batch_n,
            "timing": decision_timing,
            "median_microseconds_per_proposal": per_decision_us,
            "decision": "require-human-approval",
            "apply_allowed": False,
        },
        "limitations": [
            "Contrasts are deterministic fixtures, not network measurements.",
            "Wall-clock timing is host- and load-dependent and includes Python interpreter overhead.",
            "The fixed four-action portfolio does not establish scaling in the number of actions.",
            "This benchmark measures certificate computation only, not telemetry, model inference, Docker, or network recovery latency.",
        ],
    }
