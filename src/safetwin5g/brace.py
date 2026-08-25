"""BRACE: simultaneous block calibration and fail-closed action certification."""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, isfinite
from typing import Mapping


ContrastPair = tuple[float, float]


@dataclass(frozen=True)
class BlockConformalCalibration:
    """A simultaneous split-conformal radius calibrated on complete blocks.

    Each calibration block must contain predicted and observed action-versus-
    reference benefits for the same frozen set of mutating actions. The block
    score is the maximum absolute residual across that action vector.
    """

    coverage: float
    rank: int
    radius: float | None
    status: str
    action_ids: tuple[str, ...]
    calibrated_block_ids: tuple[str, ...]
    block_scores: tuple[float, ...]

    @property
    def calibration_block_n(self) -> int:
        return len(self.calibrated_block_ids)

    @property
    def alpha(self) -> float:
        return 1.0 - self.coverage

    @classmethod
    def fit(
        cls,
        blocks: Mapping[str, Mapping[str, ContrastPair]],
        *,
        action_ids: tuple[str, ...],
        coverage: float,
    ) -> "BlockConformalCalibration":
        if not 0.0 < coverage < 1.0:
            raise ValueError("coverage must lie strictly between zero and one")
        if not blocks:
            raise ValueError("at least one independent calibration block is required")
        frozen_actions = tuple(sorted(action_ids))
        if not frozen_actions or len(frozen_actions) != len(set(frozen_actions)):
            raise ValueError("action_ids must be a non-empty unique tuple")
        expected = set(frozen_actions)
        scores: list[float] = []
        block_ids = tuple(sorted(blocks))
        for block_id in block_ids:
            action_rows = blocks[block_id]
            if set(action_rows) != expected:
                raise ValueError(
                    f"calibration block {block_id} is incomplete: "
                    f"expected {sorted(expected)}, observed {sorted(action_rows)}"
                )
            residuals = []
            for action_id in frozen_actions:
                pair = action_rows[action_id]
                if not isinstance(pair, tuple) or len(pair) != 2:
                    raise ValueError(
                        f"{block_id}/{action_id} must be a (predicted, observed) tuple"
                    )
                predicted, observed = (float(pair[0]), float(pair[1]))
                if not isfinite(predicted) or not isfinite(observed):
                    raise ValueError(
                        f"{block_id}/{action_id} contains a non-finite contrast"
                    )
                residuals.append(abs(observed - predicted))
            scores.append(max(residuals))

        rank = ceil((len(scores) + 1) * coverage)
        ordered = sorted(scores)
        radius = ordered[rank - 1] if rank <= len(ordered) else None
        return cls(
            coverage=coverage,
            rank=rank,
            radius=radius,
            status="finite" if radius is not None else "unbounded",
            action_ids=frozen_actions,
            calibrated_block_ids=block_ids,
            block_scores=tuple(scores),
        )

    def intervals(
        self, predicted_benefits: Mapping[str, float]
    ) -> dict[str, tuple[float | None, float | None]]:
        if set(predicted_benefits) != set(self.action_ids):
            raise ValueError("predictions must contain exactly the calibrated action set")
        intervals: dict[str, tuple[float | None, float | None]] = {}
        for action_id in self.action_ids:
            prediction = float(predicted_benefits[action_id])
            if not isfinite(prediction):
                raise ValueError(f"prediction for {action_id} is not finite")
            if self.radius is None:
                intervals[action_id] = (None, None)
            else:
                intervals[action_id] = (
                    prediction - self.radius,
                    prediction + self.radius,
                )
        return intervals

    def guarantee_contract(self) -> dict[str, object]:
        return {
            "method": "BRACE-v1",
            "guarantee": "marginal-simultaneous-action-contrast-coverage",
            "coverage": self.coverage,
            "alpha": self.alpha,
            "calibration_unit": "complete-assignment-block",
            "calibration_block_n": self.calibration_block_n,
            "rank": self.rank,
            "radius": self.radius,
            "status": self.status,
            "post_selection_scope": "any action selected from the jointly covered vector",
            "assumptions": (
                "exchangeable complete blocks",
                "training fixed before calibration",
                "clean-reset consistency",
                "no cross-unit interference",
                "in-distribution support",
            ),
            "exclusions": (
                "conditional per-context coverage",
                "detected OOD",
                "incomplete blocks",
                "hardware or operator guarantees",
                "actuation authorization",
            ),
        }


@dataclass(frozen=True)
class BraceSafetyContext:
    environment: str
    evidence_label: str
    radio_evidence_label: str
    hardware_evidence_label: str | None
    operator_validation: bool
    is_ood: bool
    allowlisted_actions: tuple[str, ...]
    reversible_actions: tuple[str, ...]
    rollback_plan_actions: tuple[str, ...]


@dataclass(frozen=True)
class BraceDecision:
    decision: str
    selected_action_id: str | None
    predicted_benefit: float | None
    lower_benefit_bound: float | None
    upper_benefit_bound: float | None
    minimum_benefit_margin: float
    intervals: dict[str, tuple[float | None, float | None]]
    reasons: tuple[str, ...]
    human_approval_required: bool
    apply_allowed: bool
    evidence_label: str
    radio_evidence_label: str


def assess_brace_actions(
    predicted_benefits: Mapping[str, float],
    calibration: BlockConformalCalibration,
    context: BraceSafetyContext,
    *,
    minimum_benefit_margin: float,
) -> BraceDecision:
    """Return a proposal decision; BRACE never authorizes applying an action."""

    intervals = calibration.intervals(predicted_benefits)
    common = {
        "minimum_benefit_margin": float(minimum_benefit_margin),
        "intervals": intervals,
        "human_approval_required": True,
        "apply_allowed": False,
        "evidence_label": context.evidence_label,
        "radio_evidence_label": context.radio_evidence_label,
    }

    if context.environment != "sandbox":
        return BraceDecision(
            decision="reject",
            selected_action_id=None,
            predicted_benefit=None,
            lower_benefit_bound=None,
            upper_benefit_bound=None,
            reasons=("BRACE-v1 certification is restricted to the isolated sandbox",),
            **common,
        )

    boundary_reasons = []
    if context.evidence_label != "sandbox-measured":
        boundary_reasons.append("intervention evidence is not sandbox-measured")
    if context.radio_evidence_label != "simulated":
        boundary_reasons.append("Phase 7 radio evidence must remain simulated")
    if context.hardware_evidence_label is not None:
        boundary_reasons.append("hardware evidence cannot be inferred in Phase 7")
    if context.operator_validation:
        boundary_reasons.append("operator validation cannot be inferred in Phase 7")
    if boundary_reasons:
        return BraceDecision(
            decision="abstain",
            selected_action_id=None,
            predicted_benefit=None,
            lower_benefit_bound=None,
            upper_benefit_bound=None,
            reasons=tuple(boundary_reasons),
            **common,
        )

    if context.is_ood:
        return BraceDecision(
            decision="abstain",
            selected_action_id=None,
            predicted_benefit=None,
            lower_benefit_bound=None,
            upper_benefit_bound=None,
            reasons=("detected OOD always abstains",),
            **common,
        )
    if calibration.radius is None:
        return BraceDecision(
            decision="abstain",
            selected_action_id=None,
            predicted_benefit=None,
            lower_benefit_bound=None,
            upper_benefit_bound=None,
            reasons=("simultaneous conformal radius is unbounded",),
            **common,
        )

    allowlisted = set(context.allowlisted_actions)
    reversible = set(context.reversible_actions)
    rollback = set(context.rollback_plan_actions)
    candidates: list[tuple[float, str, float, float]] = []
    excluded: list[str] = []
    for action_id in calibration.action_ids:
        lower, upper = intervals[action_id]
        assert lower is not None and upper is not None
        missing = []
        if action_id not in allowlisted:
            missing.append("not allowlisted")
        if action_id not in reversible:
            missing.append("not reversible")
        if action_id not in rollback:
            missing.append("rollback plan missing")
        if lower <= minimum_benefit_margin:
            missing.append("lower benefit bound does not exceed margin")
        if missing:
            excluded.append(f"{action_id}: {', '.join(missing)}")
            continue
        candidates.append((lower, action_id, float(predicted_benefits[action_id]), upper))

    if not candidates:
        return BraceDecision(
            decision="abstain",
            selected_action_id=None,
            predicted_benefit=None,
            lower_benefit_bound=None,
            upper_benefit_bound=None,
            reasons=tuple(excluded) or ("no certifiable mutation",),
            **common,
        )

    lower, action_id, prediction, upper = sorted(
        candidates, key=lambda item: (-item[0], item[1])
    )[0]
    return BraceDecision(
        decision="require-human-approval",
        selected_action_id=action_id,
        predicted_benefit=prediction,
        lower_benefit_bound=lower,
        upper_benefit_bound=upper,
        reasons=(
            "simultaneous lower benefit bound exceeds the frozen margin",
            "certificate is proposal-only and cannot bypass human approval",
        ),
        **common,
    )
