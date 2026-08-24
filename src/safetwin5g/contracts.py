"""Strict data contracts for actions and controlled network interventions."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from math import isfinite
from typing import Any, Mapping


EVIDENCE_LABELS = {
    "fixture",
    "simulated",
    "sandbox-measured",
    "hardware-measured",
    "operator-validated",
}
ENVIRONMENTS = {"fixture", "simulator", "sandbox", "live"}
ENVIRONMENT_EVIDENCE = {
    "fixture": {"fixture"},
    "simulator": {"simulated"},
    "sandbox": {"sandbox-measured"},
    "live": {"hardware-measured", "operator-validated"},
}


def _required_text(value: Any, field: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"{field} is required")
    return text


def _bounded_probability(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be a number between 0 and 1")
    number = float(value)
    if not isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(f"{field} must be a finite number between 0 and 1")
    return number


def _finite_metrics(value: Any, field: str, *, allow_empty: bool = False) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field} must be an object of numeric metrics")
    if not value and not allow_empty:
        raise ValueError(f"{field} must not be empty")
    result: dict[str, float] = {}
    for key, raw in value.items():
        name = _required_text(key, f"{field} metric name")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            raise ValueError(f"{field}.{name} must be numeric")
        number = float(raw)
        if not isfinite(number):
            raise ValueError(f"{field}.{name} must be finite")
        result[name] = number
    return result


def _aware_iso_timestamp(value: Any, field: str) -> str:
    text = _required_text(value, field)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include a timezone")
    return text


@dataclass(frozen=True)
class ActionProposal:
    kind: str
    target: str
    target_type: str
    parameters: dict[str, Any]
    reversible: bool
    rollback_plan: str
    estimated_risk: float

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ActionProposal":
        if not isinstance(payload, Mapping):
            raise ValueError("action must be an object")
        parameters = payload.get("parameters", {})
        if not isinstance(parameters, Mapping):
            raise ValueError("action.parameters must be an object")
        reversible = payload.get("reversible")
        if not isinstance(reversible, bool):
            raise ValueError("action.reversible must be a boolean")
        rollback = str(payload.get("rollback_plan", "")).strip()
        return cls(
            kind=_required_text(payload.get("kind"), "action.kind"),
            target=_required_text(payload.get("target"), "action.target"),
            target_type=_required_text(payload.get("target_type"), "action.target_type"),
            parameters=dict(parameters),
            reversible=reversible,
            rollback_plan=rollback,
            estimated_risk=_bounded_probability(payload.get("estimated_risk"), "action.estimated_risk"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class InterventionRecord:
    record_id: str
    scenario_id: str
    observed_at: str
    environment: str
    fault_type: str
    pre_metrics: dict[str, float]
    action: ActionProposal
    model_confidence: float
    ood_score: float
    expected_effects: dict[str, float]
    post_metrics: dict[str, float] | None
    evidence_label: str

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "InterventionRecord":
        if not isinstance(payload, Mapping):
            raise ValueError("intervention record must be an object")
        environment = _required_text(payload.get("environment"), "environment")
        if environment not in ENVIRONMENTS:
            raise ValueError(f"environment must be one of {sorted(ENVIRONMENTS)}")
        evidence_label = _required_text(payload.get("evidence_label"), "evidence_label")
        if evidence_label not in EVIDENCE_LABELS:
            raise ValueError(f"evidence_label must be one of {sorted(EVIDENCE_LABELS)}")
        if evidence_label not in ENVIRONMENT_EVIDENCE[environment]:
            allowed = sorted(ENVIRONMENT_EVIDENCE[environment])
            raise ValueError(
                f"evidence_label {evidence_label} is incompatible with environment "
                f"{environment}; expected one of {allowed}"
            )
        post_payload = payload.get("post_metrics")
        post_metrics = None if post_payload is None else _finite_metrics(post_payload, "post_metrics")
        return cls(
            record_id=_required_text(payload.get("record_id"), "record_id"),
            scenario_id=_required_text(payload.get("scenario_id"), "scenario_id"),
            observed_at=_aware_iso_timestamp(payload.get("observed_at"), "observed_at"),
            environment=environment,
            fault_type=_required_text(payload.get("fault_type"), "fault_type"),
            pre_metrics=_finite_metrics(payload.get("pre_metrics"), "pre_metrics"),
            action=ActionProposal.from_dict(payload.get("action")),
            model_confidence=_bounded_probability(payload.get("model_confidence"), "model_confidence"),
            ood_score=_bounded_probability(payload.get("ood_score"), "ood_score"),
            expected_effects=_finite_metrics(payload.get("expected_effects"), "expected_effects"),
            post_metrics=post_metrics,
            evidence_label=evidence_label,
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["action"] = self.action.to_dict()
        return payload
