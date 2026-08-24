"""Leakage-controlled rule, tabular, and temporal baselines."""

from __future__ import annotations

from dataclasses import dataclass
import json
from math import sqrt
from pathlib import Path
from typing import Any, Callable


FAMILIES = (
    "cpu_saturation",
    "network_function_interruption",
    "packet_impairment",
)
CONTINUOUS_FEATURES = (
    "severity_value",
    "fault_packet_loss_pct",
    "fault_core_cpu_pct",
    "fault_stress_workers_count",
    "fault_upf_process_running",
    "fault_configured_packet_loss_pct",
)


def load_records(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def raw_features(record: dict[str, Any]) -> list[float]:
    fault = record["stages"]["fault"]["metrics"]
    values = {
        "severity_value": float(record["severity_value"]),
        "fault_packet_loss_pct": float(fault["packet_loss_pct"]),
        "fault_core_cpu_pct": float(fault["core_container_cpu_pct"]),
        "fault_stress_workers_count": float(fault["stress_workers_count"]),
        "fault_upf_process_running": float(fault["upf_process_running"]),
        "fault_configured_packet_loss_pct": float(fault["configured_packet_loss_pct"]),
    }
    return [float(record["fault_family"] == family) for family in FAMILIES] + [
        values[name] for name in CONTINUOUS_FEATURES
    ]


@dataclass(frozen=True)
class Standardizer:
    means: tuple[float, ...]
    scales: tuple[float, ...]

    @classmethod
    def fit(cls, rows: list[list[float]]) -> "Standardizer":
        if not rows:
            raise ValueError("training features must not be empty")
        columns = list(zip(*rows))
        means = tuple(sum(column) / len(column) for column in columns)
        variances = tuple(
            sum((value - mean) ** 2 for value in column) / len(column)
            for column, mean in zip(columns, means)
        )
        scales = tuple(sqrt(value) if value > 0.0 else 1.0 for value in variances)
        return cls(means, scales)

    def transform(self, row: list[float]) -> list[float]:
        return [
            (value - mean) / scale
            for value, mean, scale in zip(row, self.means, self.scales)
        ]


def solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    augmented = [row[:] + [value] for row, value in zip(matrix, vector)]
    size = len(augmented)
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("singular linear system")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                current - factor * reference
                for current, reference in zip(augmented[row], augmented[column])
            ]
    return [augmented[row][-1] for row in range(size)]


@dataclass(frozen=True)
class RidgeModel:
    coefficients: tuple[float, ...]
    standardizer: Standardizer
    alpha: float

    @classmethod
    def fit(cls, records: list[dict[str, Any]], alpha: float) -> "RidgeModel":
        features = [raw_features(record) for record in records]
        standardizer = Standardizer.fit(features)
        design = [[1.0] + standardizer.transform(row) for row in features]
        targets = [float(record["observed_benefit"]) for record in records]
        width = len(design[0])
        gram = [[0.0 for _ in range(width)] for _ in range(width)]
        rhs = [0.0 for _ in range(width)]
        for row, target in zip(design, targets):
            for i in range(width):
                rhs[i] += row[i] * target
                for j in range(width):
                    gram[i][j] += row[i] * row[j]
        for index in range(1, width):
            gram[index][index] += alpha
        return cls(tuple(solve(gram, rhs)), standardizer, alpha)

    def predict(self, record: dict[str, Any]) -> float:
        row = [1.0] + self.standardizer.transform(raw_features(record))
        return sum(coefficient * value for coefficient, value in zip(self.coefficients, row))


def rule_prediction(record: dict[str, Any]) -> float:
    fault = record["stages"]["fault"]["metrics"]
    family = record["fault_family"]
    if family == "packet_impairment":
        return float(fault["configured_packet_loss_pct"])
    if family == "network_function_interruption":
        return 1.0 - float(fault["upf_process_running"])
    if family == "cpu_saturation":
        return float(fault["stress_workers_count"])
    raise ValueError(f"unsupported family: {family}")


def temporal_persistence_prediction(record: dict[str, Any]) -> float:
    # With only one pre-action fault point, persistence predicts no treatment
    # benefit.  It is intentionally simple and distinct from the runbook.
    return 0.0


def metrics(
    records: list[dict[str, Any]], predictor: Callable[[dict[str, Any]], float]
) -> dict[str, float | int]:
    predictions = [predictor(record) for record in records]
    targets = [float(record["observed_benefit"]) for record in records]
    errors = [prediction - target for prediction, target in zip(predictions, targets)]
    return {
        "n": len(records),
        "mae": sum(abs(error) for error in errors) / len(errors),
        "rmse": sqrt(sum(error * error for error in errors) / len(errors)),
        "mean_prediction": sum(predictions) / len(predictions),
        "mean_observed_benefit": sum(targets) / len(targets),
        "predicted_harmful_count": sum(prediction < 0.0 for prediction in predictions),
        "observed_harmful_count": sum(target < 0.0 for target in targets),
    }


def select_ridge_alpha(
    train: list[dict[str, Any]], calibration: list[dict[str, Any]]
) -> tuple[RidgeModel, list[dict[str, float]]]:
    trials = []
    best: tuple[float, float, RidgeModel] | None = None
    for alpha in (0.01, 0.1, 1.0, 10.0, 100.0):
        model = RidgeModel.fit(train, alpha)
        score = float(metrics(calibration, model.predict)["mae"])
        trials.append({"alpha": alpha, "calibration_mae": score})
        candidate = (score, alpha, model)
        if best is None or candidate[:2] < best[:2]:
            best = candidate
    assert best is not None
    return best[2], trials


def prediction_rows(
    records: list[dict[str, Any]],
    predictors: dict[str, Callable[[dict[str, Any]], float]],
) -> list[dict[str, Any]]:
    return [
        {
            "scenario_id": record["scenario_id"],
            "split": record["split"],
            "fault_family": record["fault_family"],
            "severity_value": record["severity_value"],
            "seed": record["seed"],
            "observed_benefit": record["observed_benefit"],
            "predictions": {
                name: predictor(record) for name, predictor in predictors.items()
            },
            "evidence_label": record["evidence_label"],
            "radio_evidence_label": record["radio_evidence_label"],
        }
        for record in records
    ]
