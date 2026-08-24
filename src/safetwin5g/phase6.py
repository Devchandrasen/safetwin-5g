"""Fail-closed execution and validation primitives for Phase 6 units."""

from __future__ import annotations

from datetime import datetime, timezone
import math
import statistics
from typing import Any, Protocol


REQUIRED_STAGES = ("baseline", "fault", "post_action", "recovery")
OBSERVE_ONLY_ACTIONS = {"observe_only", "benign_observe"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def negative_control_loss(unit: dict[str, Any]) -> float:
    """Return the frozen reversible impairment for a negative-control arm."""

    if unit["fault_family"] == "packet_impairment":
        return min(95.0, float(unit["severity_value"]) + 15.0)
    return 25.0


def _percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction


def summarize_window(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize each observed metric without hiding missing values."""

    metric_names = sorted(
        {name for sample in samples for name in sample.get("metrics", {})}
    )
    metrics: dict[str, Any] = {}
    for name in metric_names:
        raw = [sample.get("metrics", {}).get(name) for sample in samples]
        values = [float(value) for value in raw if value is not None]
        metrics[name] = {
            "n": len(values),
            "missing": len(raw) - len(values),
            "mean": statistics.fmean(values) if values else None,
            "median": statistics.median(values) if values else None,
            "standard_deviation": statistics.pstdev(values) if values else None,
            "minimum": min(values) if values else None,
            "p25": _percentile(values, 0.25) if values else None,
            "p75": _percentile(values, 0.75) if values else None,
            "maximum": max(values) if values else None,
        }
    return {"sample_count": len(samples), "metrics": metrics}


def _all_samples(trace: dict[str, Any], stage: str) -> list[dict[str, Any]]:
    return trace.get("windows", {}).get(stage, {}).get("samples", [])


def _is_clean(sample: dict[str, Any]) -> bool:
    metrics = sample.get("metrics", {})
    return (
        float(metrics.get("configured_packet_loss_pct", math.inf)) == 0.0
        and float(metrics.get("upf_process_running", -math.inf)) == 1.0
        and float(metrics.get("stress_workers_count", math.inf)) == 0.0
        and float(metrics.get("packet_loss_pct", math.inf)) <= 1.0
    )


def validate_unit_trace(
    unit: dict[str, Any], trace: dict[str, Any], required_samples: int
) -> dict[str, bool]:
    """Validate assignment, state transitions, windows, and clean recovery."""

    windows = trace.get("windows", {})
    checks = {
        "four_required_windows_present": set(windows) == set(REQUIRED_STAGES),
        "window_sample_counts_match": all(
            len(_all_samples(trace, stage)) == required_samples
            for stage in REQUIRED_STAGES
        ),
        "baseline_clean": all(_is_clean(sample) for sample in _all_samples(trace, "baseline")),
        "recovery_clean": all(_is_clean(sample) for sample in _all_samples(trace, "recovery")),
        "approval_recorded": bool(trace.get("approval_id")),
        "clean_reset_recorded": trace.get("clean_reset_completed") is True,
        "cleanup_completed": trace.get("cleanup_completed") is True,
    }
    if not checks["window_sample_counts_match"]:
        return checks

    fault_samples = _all_samples(trace, "fault")
    post_samples = _all_samples(trace, "post_action")
    family = unit["fault_family"]
    severity = float(unit["severity_value"])
    if family == "packet_impairment":
        checks["fault_state_observed"] = all(
            sample["metrics"]["configured_packet_loss_pct"] == severity
            for sample in fault_samples
        )
    elif family == "network_function_interruption":
        checks["fault_state_observed"] = all(
            sample["metrics"]["upf_process_running"] == 0.0
            for sample in fault_samples
        )
    elif family == "cpu_saturation":
        checks["fault_state_observed"] = all(
            sample["metrics"]["stress_workers_count"] == severity
            for sample in fault_samples
        )
    else:
        checks["fault_state_observed"] = all(_is_clean(sample) for sample in fault_samples)

    arm = unit["action_arm"]
    if arm == "effective":
        if family == "packet_impairment":
            action_ok = all(
                sample["metrics"]["configured_packet_loss_pct"] == 0.0
                for sample in post_samples
            )
        elif family == "network_function_interruption":
            action_ok = all(
                sample["metrics"]["upf_process_running"] == 1.0
                for sample in post_samples
            )
        elif family == "cpu_saturation":
            action_ok = all(
                sample["metrics"]["stress_workers_count"] == 0.0
                for sample in post_samples
            )
        else:
            action_ok = all(_is_clean(sample) for sample in post_samples)
    elif arm == "no_action":
        if family == "packet_impairment":
            action_ok = all(
                sample["metrics"]["configured_packet_loss_pct"] == severity
                for sample in post_samples
            )
        elif family == "network_function_interruption":
            action_ok = all(
                sample["metrics"]["upf_process_running"] == 0.0
                for sample in post_samples
            )
        elif family == "cpu_saturation":
            action_ok = all(
                sample["metrics"]["stress_workers_count"] == severity
                for sample in post_samples
            )
        else:
            action_ok = all(_is_clean(sample) for sample in post_samples)
    else:
        expected_loss = negative_control_loss(unit)
        action_ok = all(
            sample["metrics"]["configured_packet_loss_pct"] == expected_loss
            for sample in post_samples
        )
        if family == "network_function_interruption":
            action_ok = action_ok and all(
                sample["metrics"]["upf_process_running"] == 0.0
                for sample in post_samples
            )
        if family == "cpu_saturation":
            action_ok = action_ok and all(
                sample["metrics"]["stress_workers_count"] == severity
                for sample in post_samples
            )
    checks["assigned_action_state_observed"] = action_ok
    return checks


class Phase6Backend(Protocol):
    def reset(self, unit: dict[str, Any]) -> None: ...

    def observe_window(self, stage: str, unit: dict[str, Any]) -> list[dict[str, Any]]: ...

    def inject_fault(self, unit: dict[str, Any]) -> None: ...

    def apply_action(self, unit: dict[str, Any]) -> None: ...

    def cleanup(self, unit: dict[str, Any]) -> None: ...


class Phase6UnitRunner:
    """Execute one approved unit and always attempt clean recovery."""

    def __init__(self, backend: Phase6Backend, required_samples: int):
        self.backend = backend
        self.required_samples = required_samples

    def run(self, unit: dict[str, Any], approval: dict[str, Any]) -> dict[str, Any]:
        if (
            approval.get("approval_status") != "approved"
            or approval.get("environment") != "sandbox"
            or approval.get("experiment_id") not in unit["unit_id"]
        ):
            raise PermissionError("valid experiment-scoped sandbox approval is required")

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
        except Exception as exc:  # cleanup still must run
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

        trace["checks"] = validate_unit_trace(unit, trace, self.required_samples)
        trace["cleanup_verified"] = (
            trace["checks"].get("recovery_clean", False)
            and trace["cleanup_completed"]
        )
        trace["passed"] = not trace["errors"] and all(trace["checks"].values())
        trace["completed_at"] = utc_now()
        return trace

    def _observe(
        self, trace: dict[str, Any], stage: str, unit: dict[str, Any]
    ) -> None:
        samples = self.backend.observe_window(stage, unit)
        trace["windows"][stage] = {
            "samples": samples,
            "summary": summarize_window(samples),
        }
