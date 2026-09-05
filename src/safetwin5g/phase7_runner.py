"""Fail-closed execution contract for Phase 7 named-action units."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from .phase6 import utc_now


def _samples(trace: dict[str, Any], stage: str) -> list[dict[str, Any]]:
    return trace.get("windows", {}).get(stage, {}).get("samples", [])


def _is_clean(sample: dict[str, Any]) -> bool:
    metrics = sample.get("metrics", {})
    try:
        return (
            float(metrics["configured_packet_loss_pct"]) == 0.0
            and float(metrics["upf_process_running"]) == 1.0
            and float(metrics["stress_workers_count"]) == 0.0
            and 0.0 <= float(metrics["packet_loss_pct"]) <= 1.0
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def expected_fault_state(unit: dict[str, Any]) -> dict[str, float]:
    state = {
        "configured_packet_loss_pct": 0.0,
        "upf_process_running": 1.0,
        "stress_workers_count": 0.0,
    }
    family = unit["fault_family"]
    severity = float(unit["severity_value"])
    if family == "packet_impairment":
        state["configured_packet_loss_pct"] = severity
    elif family == "network_function_interruption":
        state["upf_process_running"] = 0.0
    elif family == "cpu_saturation":
        state["stress_workers_count"] = severity
    elif family != "no_fault":
        raise ValueError(f"unsupported fault family: {family}")
    return state


def expected_post_action_state(unit: dict[str, Any]) -> dict[str, float]:
    state = expected_fault_state(unit)
    action = unit["action_id"]
    if action == "observe_only":
        pass
    elif action == "clear_packet_impairment":
        state["configured_packet_loss_pct"] = 0.0
    elif action == "resume_upf":
        state["upf_process_running"] = 1.0
    elif action == "stop_cpu_stress":
        state["stress_workers_count"] = 0.0
    elif action == "apply_packet_impairment_25":
        state["configured_packet_loss_pct"] = float(
            unit["action_parameters"]["loss_pct"]
        )
    else:
        raise ValueError(f"unsupported action id: {action}")
    return state


def _matches_state(sample: dict[str, Any], state: dict[str, float]) -> bool:
    metrics = sample["metrics"]
    return all(metrics[name] == value for name, value in state.items())


def validate_named_action_trace(
    unit: dict[str, Any], trace: dict[str, Any], required_samples: int
) -> dict[str, bool]:
    stages = ("baseline", "fault", "post_action", "recovery")
    checks: dict[str, bool] = {
        "clean_reset_completed": trace.get("clean_reset_completed") is True,
        "fault_injection_completed": trace.get("fault_injection_completed") is True,
        "action_step_completed": trace.get("action_step_completed") is True,
        "cleanup_completed": trace.get("cleanup_completed") is True,
        "all_windows_present": set(trace.get("windows", {})) == set(stages),
    }
    for stage in stages:
        checks[f"{stage}_sample_count"] = len(_samples(trace, stage)) == required_samples

    all_samples = [sample for stage in stages for sample in _samples(trace, stage)]
    try:
        timestamps = [
            datetime.fromisoformat(sample["observed_at"]) for sample in all_samples
        ]
        checks["timestamps_timezone_aware"] = all(
            item.tzinfo is not None for item in timestamps
        )
        checks["timestamps_monotonic"] = timestamps == sorted(timestamps)
    except (KeyError, TypeError, ValueError):
        checks["timestamps_timezone_aware"] = False
        checks["timestamps_monotonic"] = False

    baseline = _samples(trace, "baseline")
    fault = _samples(trace, "fault")
    post_action = _samples(trace, "post_action")
    recovery = _samples(trace, "recovery")
    checks["baseline_clean"] = bool(baseline) and all(_is_clean(row) for row in baseline)
    fault_state = expected_fault_state(unit)
    checks["assigned_fault_state_observed"] = bool(fault) and all(
        _matches_state(row, fault_state) for row in fault
    )
    post_state = expected_post_action_state(unit)
    checks["named_action_state_observed"] = bool(post_action) and all(
        _matches_state(row, post_state) for row in post_action
    )
    checks["recovery_clean"] = bool(recovery) and all(
        _is_clean(row) for row in recovery
    )
    return checks


class Phase7Backend(Protocol):
    def reset(self, unit: dict[str, Any]) -> None: ...

    def observe_window(self, stage: str, unit: dict[str, Any]) -> list[dict[str, Any]]: ...

    def inject_fault(self, unit: dict[str, Any]) -> None: ...

    def apply_action(self, unit: dict[str, Any]) -> None: ...

    def cleanup(self, unit: dict[str, Any]) -> None: ...


class Phase7UnitRunner:
    """Execute one named-action unit and always attempt recovery."""

    def __init__(self, backend: Phase7Backend, required_samples: int):
        self.backend = backend
        self.required_samples = required_samples

    def run(self, unit: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
        if (
            approval.get("approval_status") != "approved"
            or approval.get("environment") != "sandbox"
            or approval.get("experiment_id") not in unit["unit_id"]
            or unit["unit_id"] not in approval.get("unit_ids", [])
        ):
            raise PermissionError("valid unit-scoped sandbox approval is required")

        trace: dict[str, Any] = {
            "schema_version": 1,
            "unit": unit,
            "started_at": utc_now(),
            "approval_id": approval.get("approval_id"),
            "clean_reset_completed": False,
            "fault_injection_completed": False,
            "action_step_completed": False,
            "cleanup_completed": False,
            "windows": {},
            "errors": [],
        }
        try:
            self.backend.reset(unit)
            trace["clean_reset_completed"] = True
            self._observe(trace, "baseline", unit)
            self.backend.inject_fault(unit)
            trace["fault_injection_completed"] = True
            self._observe(trace, "fault", unit)
            self.backend.apply_action(unit)
            trace["action_step_completed"] = True
            self._observe(trace, "post_action", unit)
        except Exception as exc:
            trace["errors"].append(f"execution: {type(exc).__name__}: {exc}")
        finally:
            try:
                self.backend.cleanup(unit)
                trace["cleanup_completed"] = True
            except Exception as exc:
                trace["errors"].append(f"cleanup: {type(exc).__name__}: {exc}")
            try:
                self._observe(trace, "recovery", unit)
            except Exception as exc:
                trace["errors"].append(f"recovery: {type(exc).__name__}: {exc}")

        trace["checks"] = validate_named_action_trace(
            unit, trace, self.required_samples
        )
        trace["cleanup_verified"] = (
            trace["cleanup_completed"]
            and trace["checks"].get("recovery_sample_count", False)
            and trace["checks"].get("recovery_clean", False)
        )
        trace["passed"] = not trace["errors"] and all(trace["checks"].values())
        trace["completed_at"] = utc_now()
        return trace

    def _observe(
        self, trace: dict[str, Any], stage: str, unit: dict[str, Any]
    ) -> None:
        samples = self.backend.observe_window(stage, unit)
        trace["windows"][stage] = {"samples": samples}
        if stage == "baseline" and (
            len(samples) != self.required_samples
            or not all(_is_clean(sample) for sample in samples)
        ):
            raise RuntimeError("baseline user plane or configuration is not clean")
