"""Selective-risk endpoint calculations with explicit undefined states."""

from __future__ import annotations

from typing import Any


def safe_rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def selective_endpoints(
    records: list[dict[str, Any]], assessments: list[dict[str, Any]]
) -> dict[str, Any]:
    by_id = {record["scenario_id"]: record for record in records}
    if set(by_id) != {item["scenario_id"] for item in assessments}:
        raise ValueError("record and assessment scenario sets differ")
    eligible = [item for item in assessments if item["decision"] != "abstain"]
    applied = [by_id[item["scenario_id"]] for item in eligible]
    harmful = sum(record["observed_benefit"] < 0.0 for record in applied)
    always_harmful = sum(record["observed_benefit"] < 0.0 for record in records)
    finite_rank_scores = all(
        item.get("interval") is not None and isinstance(item.get("ood_score"), (int, float))
        for item in assessments
    )
    return {
        "scenario_count": len(records),
        "eligible_count": len(eligible),
        "coverage": safe_rate(len(eligible), len(records)),
        "abstention_rate": safe_rate(len(records) - len(eligible), len(records)),
        "selective_harmful_count": harmful,
        "selective_harmful_rate": safe_rate(harmful, len(applied)),
        "always_act_harmful_count": always_harmful,
        "always_act_harmful_rate": safe_rate(always_harmful, len(records)),
        "risk_coverage_auc": None if not finite_rank_scores else 0.0,
        "risk_coverage_status": (
            "undefined-unbounded-uncertainty" if not finite_rank_scores else "computed"
        ),
        "false_remediation_rate": None,
        "false_remediation_status": "undefined-no-no-fault-scenarios",
        "sla_violation_duration_s": None,
        "sla_duration_status": "undefined-no-continuous-sla-window",
        "mean_time_to_recovery_s": None,
        "mttr_status": "undefined-no-sustained-recovery-window",
        "harm_reduction_claim_supported": False,
    }
