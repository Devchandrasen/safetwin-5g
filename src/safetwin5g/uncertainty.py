"""Finite-sample uncertainty and design-range OOD detection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import ceil
from typing import Any


@dataclass(frozen=True)
class ConformalCalibration:
    coverage: float
    calibration_n: int
    rank: int
    radius: float | None
    status: str

    @classmethod
    def fit(
        cls, predictions: list[float], targets: list[float], coverage: float
    ) -> "ConformalCalibration":
        if len(predictions) != len(targets) or not predictions:
            raise ValueError("calibration predictions and targets must have equal non-zero length")
        if not 0.0 < coverage < 1.0:
            raise ValueError("coverage must be between zero and one")
        residuals = sorted(
            abs(prediction - target)
            for prediction, target in zip(predictions, targets)
        )
        rank = ceil((len(residuals) + 1) * coverage)
        if rank > len(residuals):
            return cls(
                coverage,
                len(residuals),
                rank,
                None,
                "unbounded-insufficient-calibration",
            )
        return cls(coverage, len(residuals), rank, residuals[rank - 1], "finite")

    def interval(self, prediction: float) -> tuple[float, float] | None:
        if self.radius is None:
            return None
        return prediction - self.radius, prediction + self.radius

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RangeOODDetector:
    severity_ranges: dict[str, tuple[float, float]]
    fitted_scenario_ids: tuple[str, ...]

    @classmethod
    def fit(cls, records: list[dict[str, Any]]) -> "RangeOODDetector":
        if not records:
            raise ValueError("OOD detector requires development records")
        values: dict[str, list[float]] = {}
        for record in records:
            values.setdefault(record["fault_family"], []).append(
                float(record["severity_value"])
            )
        return cls(
            severity_ranges={
                family: (min(items), max(items)) for family, items in values.items()
            },
            fitted_scenario_ids=tuple(sorted(record["scenario_id"] for record in records)),
        )

    def evaluate(self, record: dict[str, Any]) -> dict[str, Any]:
        family = record["fault_family"]
        severity = float(record["severity_value"])
        if family not in self.severity_ranges:
            return {
                "ood_score": 1.0,
                "is_ood": True,
                "reason": "unseen fault family",
            }
        lower, upper = self.severity_ranges[family]
        outside = severity < lower or severity > upper
        return {
            "ood_score": 1.0 if outside else 0.0,
            "is_ood": outside,
            "reason": (
                f"severity {severity:g} outside development range [{lower:g}, {upper:g}]"
                if outside
                else "within observed development severity range"
            ),
        }


def selective_assessment(
    prediction: float,
    calibration: ConformalCalibration,
    ood: dict[str, Any],
) -> dict[str, Any]:
    reasons = []
    interval = calibration.interval(prediction)
    if interval is None:
        reasons.append("nominal uncertainty interval is unbounded")
    if ood["is_ood"]:
        reasons.append(ood["reason"])
    return {
        "prediction": prediction,
        "interval": list(interval) if interval is not None else None,
        "calibration_status": calibration.status,
        "ood_score": ood["ood_score"],
        "is_ood": ood["is_ood"],
        "decision": "abstain" if reasons else "eligible-for-safety-gate",
        "reasons": reasons,
    }
