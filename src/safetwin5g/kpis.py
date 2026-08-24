"""Canonical KPI registry and transformations for SafeTwin-5G datasets."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from .telemetry import TelemetryRow


@dataclass(frozen=True)
class KPIDefinition:
    name: str
    unit: str
    direction: str
    aggregation: str
    description: str
    availability: str


KPI_DEFINITIONS = {
    definition.name: definition
    for definition in (
        KPIDefinition(
            "user_plane_packet_loss_pct",
            "percent",
            "lower-is-better",
            "per-stage ping summary",
            "Share of transmitted UE-to-UPF packets not received.",
            "stage",
        ),
        KPIDefinition(
            "user_plane_rtt_avg_ms",
            "milliseconds",
            "lower-is-better",
            "arithmetic mean over successful ping replies",
            "Mean UE-to-UPF round-trip time; missing when no reply is received.",
            "stage",
        ),
        KPIDefinition(
            "user_plane_success_ratio",
            "ratio",
            "higher-is-better",
            "received packets divided by transmitted packets",
            "Fraction of UE-to-UPF probes that receive a reply.",
            "stage",
        ),
        KPIDefinition(
            "amf_registered_ues_count",
            "count",
            "higher-is-better",
            "sum across exposed PLMN and slice label sets",
            "Registered-state subscribers exposed by the AMF.",
            "stage",
        ),
        KPIDefinition(
            "smf_pfcp_sessions_count",
            "count",
            "higher-is-better",
            "single SMF gauge",
            "Active PFCP sessions exposed by the SMF.",
            "stage",
        ),
        KPIDefinition(
            "upf_sessions_count",
            "count",
            "higher-is-better",
            "single UPF gauge",
            "Active PDU sessions exposed by the UPF.",
            "stage",
        ),
        KPIDefinition(
            "action_effect_error",
            "target-native",
            "lower-is-better",
            "mean absolute error on held-out interventions",
            "Absolute error between predicted and observed action effect.",
            "benchmark",
        ),
        KPIDefinition(
            "harmful_remediation_rate",
            "ratio",
            "lower-is-better",
            "harmful applied actions divided by applied actions",
            "Rate at which an applied action worsens the declared outcome.",
            "benchmark",
        ),
        KPIDefinition(
            "sla_violation_duration_s",
            "seconds",
            "lower-is-better",
            "wall-clock duration above the versioned SLA threshold",
            "Duration of the declared SLA violation within a scenario.",
            "scenario",
        ),
        KPIDefinition(
            "mean_time_to_recovery_s",
            "seconds",
            "lower-is-better",
            "mean from fault observation to sustained recovery",
            "Elapsed time from observed fault to sustained SLA recovery.",
            "benchmark",
        ),
        KPIDefinition(
            "rollback_rate",
            "ratio",
            "lower-is-better",
            "rolled-back actions divided by applied actions",
            "Fraction of applied remediations subsequently rolled back.",
            "benchmark",
        ),
        KPIDefinition(
            "false_remediation_rate",
            "ratio",
            "lower-is-better",
            "actions applied to non-fault scenarios divided by such scenarios",
            "Rate of unnecessary action when no actionable fault is present.",
            "benchmark",
        ),
        KPIDefinition(
            "risk_coverage_auc",
            "ratio",
            "lower-is-better",
            "trapezoidal area under empirical risk versus coverage",
            "Aggregate selective-prediction risk over retained coverage.",
            "benchmark",
        ),
        KPIDefinition(
            "abstention_rate",
            "ratio",
            "context-dependent",
            "abstained proposals divided by eligible proposals",
            "Fraction of proposals withheld by uncertainty or OOD policy.",
            "benchmark",
        ),
        KPIDefinition(
            "decision_latency_ms",
            "milliseconds",
            "lower-is-better",
            "wall-clock decision latency distribution",
            "Time required to produce and gate one action proposal.",
            "benchmark",
        ),
        KPIDefinition(
            "resource_overhead_cpu_pct",
            "percentage-points",
            "lower-is-better",
            "CPU utilization delta versus no-twin observation",
            "Incremental compute overhead of telemetry and decision components.",
            "benchmark",
        ),
    )
}


@dataclass(frozen=True)
class KPIObservation:
    scenario_id: str
    stage: str
    observed_at: str
    kpi: str
    value: float | None
    unit: str
    status: str
    missing_reason: str | None
    evidence_label: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


STAGE_KPIS = tuple(
    name for name, definition in KPI_DEFINITIONS.items() if definition.availability == "stage"
)


def canonicalize(rows: Iterable[TelemetryRow]) -> list[KPIObservation]:
    materialized = list(rows)
    if not materialized:
        return []
    groups: dict[tuple[str, str], list[TelemetryRow]] = {}
    for row in materialized:
        groups.setdefault((row.scenario_id, row.stage), []).append(row)

    result: list[KPIObservation] = []
    for (scenario_id, stage), stage_rows in sorted(groups.items()):
        evidence_labels = {row.evidence_label for row in stage_rows}
        if len(evidence_labels) != 1:
            raise ValueError(f"mixed evidence labels in {scenario_id}/{stage}")
        observed_at = max(row.observed_at for row in stage_rows)
        values = {
            "user_plane_packet_loss_pct": _single(
                stage_rows, "ueransim-user-plane", "packet_loss_pct"
            ),
            "user_plane_rtt_avg_ms": _single(
                stage_rows, "ueransim-user-plane", "rtt_avg_ms"
            ),
            "user_plane_success_ratio": _success_ratio(stage_rows),
            "amf_registered_ues_count": _sum(
                stage_rows,
                "open5gs-amf",
                "fivegs_amffunction_rm_registeredsubnbr",
            ),
            "smf_pfcp_sessions_count": _single(
                stage_rows, "open5gs-smf", "pfcp_sessions_active"
            ),
            "upf_sessions_count": _single(
                stage_rows,
                "open5gs-upf",
                "fivegs_upffunction_upf_sessionnbr",
            ),
        }
        for kpi in STAGE_KPIS:
            value = values[kpi]
            missing_reason = None
            if value is None:
                missing_reason = (
                    "no successful ping replies"
                    if kpi == "user_plane_rtt_avg_ms"
                    and values["user_plane_packet_loss_pct"] == 100.0
                    else "source metric unavailable"
                )
            result.append(
                KPIObservation(
                    scenario_id=scenario_id,
                    stage=stage,
                    observed_at=observed_at,
                    kpi=kpi,
                    value=value,
                    unit=KPI_DEFINITIONS[kpi].unit,
                    status="observed" if value is not None else "missing",
                    missing_reason=missing_reason,
                    evidence_label=next(iter(evidence_labels)),
                )
            )
    return result


def _matching(rows: list[TelemetryRow], source: str, metric: str) -> list[float]:
    return [row.value for row in rows if row.source == source and row.metric == metric]


def _single(rows: list[TelemetryRow], source: str, metric: str) -> float | None:
    values = _matching(rows, source, metric)
    if not values:
        return None
    if len(values) != 1:
        raise ValueError(f"expected one {source}/{metric} sample, got {len(values)}")
    return values[0]


def _sum(rows: list[TelemetryRow], source: str, metric: str) -> float | None:
    values = _matching(rows, source, metric)
    return sum(values) if values else None


def _success_ratio(rows: list[TelemetryRow]) -> float | None:
    transmitted = _single(rows, "ueransim-user-plane", "packets_transmitted")
    received = _single(rows, "ueransim-user-plane", "packets_received")
    if transmitted is None or received is None or transmitted <= 0:
        return None
    return received / transmitted
