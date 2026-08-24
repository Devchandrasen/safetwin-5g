"""Held-out descriptive effect estimation guarded by causal identification."""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any

from .causal import identification_report


class IdentificationError(RuntimeError):
    """Raised when a requested causal estimand is not identified."""


@dataclass(frozen=True)
class FamilyMeanEffectEstimator:
    means: dict[str, float]
    fitted_scenario_ids: tuple[str, ...]

    @classmethod
    def fit(cls, records: list[dict[str, Any]]) -> "FamilyMeanEffectEstimator":
        if not records:
            raise ValueError("effect estimator requires training records")
        grouped: dict[str, list[float]] = {}
        for record in records:
            grouped.setdefault(record["fault_family"], []).append(
                float(record["observed_benefit"])
            )
        return cls(
            means={family: sum(values) / len(values) for family, values in grouped.items()},
            fitted_scenario_ids=tuple(sorted(record["scenario_id"] for record in records)),
        )

    def predict(self, record: dict[str, Any]) -> float:
        family = record["fault_family"]
        if family not in self.means:
            raise ValueError(f"unseen fault family: {family}")
        return self.means[family]


def evaluate_heldout(
    estimator: FamilyMeanEffectEstimator, records: list[dict[str, Any]]
) -> dict[str, Any]:
    rows = []
    errors = []
    for record in records:
        prediction = estimator.predict(record)
        observed = float(record["observed_benefit"])
        error = prediction - observed
        errors.append(error)
        rows.append(
            {
                "scenario_id": record["scenario_id"],
                "fault_family": record["fault_family"],
                "split": record["split"],
                "predicted_paired_benefit": prediction,
                "observed_paired_benefit": observed,
                "error": error,
                "estimand_status": "descriptive-only",
                "evidence_label": record["evidence_label"],
                "radio_evidence_label": record["radio_evidence_label"],
            }
        )
    return {
        "n": len(records),
        "mae": sum(abs(error) for error in errors) / len(errors),
        "rmse": sqrt(sum(error * error for error in errors) / len(errors)),
        "rows": rows,
    }


def require_alternative_action_identified(graph: dict[str, Any]) -> None:
    report = identification_report(graph)
    if not report["alternative_action_effect_identified"]:
        blockers = ", ".join(report["blocking_assumptions"])
        raise IdentificationError(
            f"alternative-action effect is not identified; blockers: {blockers}"
        )
