"""Fail-closed selective safety policy for proposed network actions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any, Mapping

from .contracts import ActionProposal, InterventionRecord


class Decision(str, Enum):
    REJECT = "reject"
    ABSTAIN = "abstain"
    REQUIRE_APPROVAL = "require-human-approval"


@dataclass(frozen=True)
class SafetyEvaluation:
    decision: Decision
    reasons: tuple[str, ...]
    policy_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.value,
            "reasons": list(self.reasons),
            "policy_version": self.policy_version,
        }


class SafetyPolicy:
    def __init__(self, config: Mapping[str, Any]):
        self.config = dict(config)
        self.policy_version = str(config.get("policy_version", "unknown"))
        self.actions = config.get("actions", {})
        if not isinstance(self.actions, Mapping) or not self.actions:
            raise ValueError("safety policy requires a non-empty actions object")
        self.min_confidence = float(config.get("min_model_confidence", 1.0))
        self.max_ood = float(config.get("max_ood_score", 0.0))
        self.max_risk = float(config.get("max_estimated_risk", 0.0))
        self.allow_live = bool(config.get("allow_live_actuation", False))

    @classmethod
    def from_path(cls, path: Path) -> "SafetyPolicy":
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def evaluate(self, record: InterventionRecord) -> SafetyEvaluation:
        return self.evaluate_action(
            record.action,
            environment=record.environment,
            decision_source=record.decision_source,
            model_confidence=record.model_confidence,
            ood_score=record.ood_score,
        )

    def evaluate_action(
        self,
        action: ActionProposal,
        *,
        environment: str,
        decision_source: str,
        model_confidence: float | None = None,
        ood_score: float | None = None,
    ) -> SafetyEvaluation:
        reasons: list[str] = []
        action_policy = self.actions.get(action.kind)

        if not isinstance(action_policy, Mapping):
            return self._result(Decision.REJECT, f"unsupported action kind: {action.kind}")

        target_types = action_policy.get("target_types", [])
        if action.target_type not in target_types:
            return self._result(
                Decision.REJECT,
                f"action {action.kind} does not support target type {action.target_type}",
            )

        if environment == "live" and not self.allow_live:
            reasons.append("live actuation is blocked by the current project phase")
        if action_policy.get("sandbox_only") and environment != "sandbox":
            reasons.append(f"action {action.kind} is restricted to the sandbox")
        if not action.reversible:
            reasons.append("irreversible actions are blocked")
        if not action.rollback_plan:
            reasons.append("a rollback plan is required")
        if action.estimated_risk > self.max_risk:
            reasons.append(
                f"estimated risk {action.estimated_risk:.3f} exceeds {self.max_risk:.3f}"
            )
        if reasons:
            return SafetyEvaluation(Decision.REJECT, tuple(reasons), self.policy_version)

        if decision_source == "model":
            if model_confidence is None or ood_score is None:
                return self._result(
                    Decision.ABSTAIN,
                    "model confidence and OOD score are required for model decisions",
                )
            uncertainty: list[str] = []
            if model_confidence < self.min_confidence:
                uncertainty.append(
                    f"model confidence {model_confidence:.3f} is below {self.min_confidence:.3f}"
                )
            if ood_score > self.max_ood:
                uncertainty.append(f"OOD score {ood_score:.3f} exceeds {self.max_ood:.3f}")
            if uncertainty:
                return SafetyEvaluation(Decision.ABSTAIN, tuple(uncertainty), self.policy_version)

        return self._result(
            Decision.REQUIRE_APPROVAL,
            "eligible non-live proposal; explicit human approval is still mandatory",
        )

    def _result(self, decision: Decision, reason: str) -> SafetyEvaluation:
        return SafetyEvaluation(decision, (reason,), self.policy_version)
