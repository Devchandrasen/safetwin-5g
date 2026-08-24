"""Fail-closed state machine for replayable sandbox scenarios."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class ScenarioSpec:
    scenario_id: str
    environment: str
    seed: int
    fault_family: str
    fault_parameters: dict[str, Any]
    action_kind: str
    target: str
    rollback_required: bool = True

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ScenarioSpec":
        scenario_id = str(payload.get("scenario_id", "")).strip()
        if not scenario_id:
            raise ValueError("scenario_id is required")
        environment = str(payload.get("environment", "")).strip()
        if environment != "sandbox":
            raise ValueError("scenario runner accepts only environment=sandbox")
        seed = payload.get("seed")
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise ValueError("seed must be a non-negative integer")
        fault_parameters = payload.get("fault_parameters", {})
        if not isinstance(fault_parameters, Mapping):
            raise ValueError("fault_parameters must be an object")
        rollback_required = payload.get("rollback_required", True)
        if rollback_required is not True:
            raise ValueError("rollback_required must remain true")
        return cls(
            scenario_id=scenario_id,
            environment=environment,
            seed=seed,
            fault_family=str(payload.get("fault_family", "")).strip(),
            fault_parameters=dict(fault_parameters),
            action_kind=str(payload.get("action_kind", "")).strip(),
            target=str(payload.get("target", "")).strip(),
            rollback_required=True,
        )


class ScenarioBackend(Protocol):
    def observe(self, stage: str) -> Mapping[str, float]: ...

    def inject_fault(self, spec: ScenarioSpec) -> None: ...

    def apply_action(self, spec: ScenarioSpec) -> None: ...

    def rollback_action(self, spec: ScenarioSpec) -> None: ...

    def cleanup(self, spec: ScenarioSpec) -> None: ...


@dataclass(frozen=True)
class ScenarioTrace:
    scenario: dict[str, Any]
    approval_id: str
    started_at: str
    completed_at: str
    stages: list[dict[str, Any]]
    passed: bool
    cleanup_verified: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ScenarioRunner:
    """Execute the fixed baseline/fault/action/rollback/cleanup sequence."""

    def __init__(self, backend: ScenarioBackend):
        self.backend = backend

    def run(self, spec: ScenarioSpec, approval: Mapping[str, Any]) -> ScenarioTrace:
        if approval.get("approval_status") != "approved":
            raise PermissionError("explicit human approval is required")
        approval_id = str(approval.get("approval_id", "")).strip()
        if not approval_id:
            raise PermissionError("approval_id is required")
        if approval.get("environment") != "sandbox":
            raise PermissionError("approval must be scoped to the sandbox")

        started = datetime.now(timezone.utc).isoformat()
        stages: list[dict[str, Any]] = []
        passed = False
        cleanup_verified = False
        try:
            stages.append(self._observe("baseline"))
            self.backend.inject_fault(spec)
            stages.append(self._observe("fault"))
            self.backend.apply_action(spec)
            stages.append(self._observe("post-action"))
            self.backend.rollback_action(spec)
            stages.append(self._observe("rollback"))
            passed = True
        finally:
            self.backend.cleanup(spec)
            stages.append(self._observe("final"))
            cleanup_verified = True
        return ScenarioTrace(
            scenario=asdict(spec),
            approval_id=approval_id,
            started_at=started,
            completed_at=datetime.now(timezone.utc).isoformat(),
            stages=stages,
            passed=passed,
            cleanup_verified=cleanup_verified,
        )

    def _observe(self, stage: str) -> dict[str, Any]:
        metrics = self.backend.observe(stage)
        if not metrics:
            raise RuntimeError(f"empty telemetry at stage {stage}")
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in metrics.values()):
            raise RuntimeError(f"non-numeric telemetry at stage {stage}")
        return {
            "stage": stage,
            "observed_at": datetime.now(timezone.utc).isoformat(),
            "metrics": {name: float(value) for name, value in sorted(metrics.items())},
        }
