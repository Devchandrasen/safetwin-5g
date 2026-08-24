"""Evidence-linked benchmark decision reporting."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any


SOURCE_REPORTS = {
    "baselines": "evidence/benchmarks/20260824T052852Z-baselines-v0/report.json",
    "effects": "evidence/benchmarks/20260824T053222Z-heldout-effects-v0/report.json",
    "diagnostics": "evidence/benchmarks/20260824T053419Z-diagnostics-v0/report.json",
    "uncertainty": "evidence/benchmarks/20260824T053654Z-uncertainty-ood-v0/report.json",
    "selective": "evidence/benchmarks/20260824T053857Z-selective-evaluation-v0/report.json",
    "safety": "evidence/benchmarks/20260824T054104Z-safety-integration-v0/report.json",
}

SOURCE_MANIFESTS = {
    "dataset": "data/releases/safetwin5g-interventions-v0/manifest.json",
    "intervention": "evidence/sandbox/20260824T045620Z-intervention/manifest.json",
    **{
        name: str(Path(relative).with_name("manifest.json")).replace("\\", "/")
        for name, relative in SOURCE_REPORTS.items()
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def verify_manifest(manifest_path: Path) -> None:
    manifest = load_json(manifest_path)
    bundle = manifest_path.parent
    expected = manifest.get("captured_file_sha256", {})
    if not expected:
        raise ValueError(f"manifest has no captured files: {manifest_path}")
    errors = []
    for relative, expected_hash in expected.items():
        path = bundle / relative
        if not path.is_file():
            errors.append(f"missing {relative}")
        elif sha256(path) != expected_hash:
            errors.append(f"hash mismatch {relative}")
    actual = {
        str(path.relative_to(bundle)).replace("\\", "/")
        for path in bundle.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    errors.extend(f"unmanifested {relative}" for relative in sorted(actual - set(expected)))
    if errors:
        raise ValueError(f"invalid evidence bundle {bundle}: {'; '.join(errors)}")


def load_verified_sources(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    for relative in SOURCE_MANIFESTS.values():
        verify_manifest(root / relative)
    reports = {name: load_json(root / relative) for name, relative in SOURCE_REPORTS.items()}
    dataset = load_json(root / SOURCE_MANIFESTS["dataset"])
    dataset_hash = sha256(root / SOURCE_MANIFESTS["dataset"])
    for name, report in reports.items():
        reported_hash = report.get("dataset_manifest_sha256")
        if reported_hash is not None and reported_hash != dataset_hash:
            raise ValueError(f"{name} references a different dataset manifest")
    source_evidence = {
        "files": [
            {
                "role": role,
                "path": relative,
                "sha256": sha256(root / relative),
            }
            for role, relative in sorted(
                {**SOURCE_MANIFESTS, **{f"{key}_report": value for key, value in SOURCE_REPORTS.items()}}.items()
            )
        ]
    }
    return {**reports, "dataset": dataset}, source_evidence


def build_decision_report(
    sources: dict[str, dict[str, Any]], run_id: str, started_at: str
) -> dict[str, Any]:
    baselines = sources["baselines"]
    effects = sources["effects"]
    diagnostics = sources["diagnostics"]
    uncertainty = sources["uncertainty"]
    selective = sources["selective"]
    safety = sources["safety"]
    test_metrics = baselines["evaluation"]["test"]
    endpoints = selective["endpoints"]
    return {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "execution_passed": True,
        "evidence_label": "sandbox-measured",
        "radio_evidence_label": "simulated",
        "dataset": {
            "version": sources["dataset"]["dataset_version"],
            "record_count": sources["dataset"]["record_count"],
            "split_sizes": baselines["split_sizes"],
        },
        "hypotheses": {
            "H1": {
                "status": "not-supported",
                "decision": "no-go-for-superiority-claim",
                "primary_endpoint": "action-effect prediction error",
                "observed": {
                    "deterministic_rule_test_mae": test_metrics["deterministic_rule"]["mae"],
                    "tabular_ridge_test_mae": test_metrics["tabular_ridge"]["mae"],
                    "temporal_persistence_test_mae": test_metrics["temporal_persistence"]["mae"],
                    "heldout_proxy_test_mae": effects["test"]["mae"],
                    "alternative_action_ate": effects["alternative_action_ate"],
                    "alternative_action_status": effects["alternative_action_status"],
                },
                "reasons": [
                    "The deterministic rule is the held-out MAE winner.",
                    "The held-out effect estimator is not superior to the rule.",
                    "Exchangeability, positivity, and no-carry-over are not established, so the alternative-action effect is not identified.",
                    "The exact small-sample permutation control does not support learned-model superiority.",
                ],
            },
            "H2": {
                "status": "not-supported",
                "decision": "no-go-for-harm-reduction-claim",
                "primary_endpoint": "harmful remediation rate at declared coverage",
                "observed": {
                    "coverage": endpoints["coverage"],
                    "abstention_rate": endpoints["abstention_rate"],
                    "selective_harmful_rate": endpoints["selective_harmful_rate"],
                    "always_act_harmful_rate": endpoints["always_act_harmful_rate"],
                    "risk_coverage_auc": endpoints["risk_coverage_auc"],
                },
                "reasons": [
                    "The 90% conformal interval is unbounded with three calibration scenarios.",
                    "Coverage is zero, so selective harmful-action risk and AURC are undefined.",
                    "No harmful action was observed, so harm reduction cannot be tested.",
                    "Both test and designated OOD rows are severity-shifted and are not distinguishable by the current design contract.",
                ],
            },
            "H3": {
                "status": "not-tested",
                "decision": "no-go-for-operational-value-claim",
                "primary_endpoint": "SLA duration, MTTR, rollback, and false-remediation rates",
                "observed": {
                    "sla_violation_duration_s": endpoints["sla_violation_duration_s"],
                    "mean_time_to_recovery_s": endpoints["mean_time_to_recovery_s"],
                    "false_remediation_rate": endpoints["false_remediation_rate"],
                    "model_proposal_actions_applied": safety["applied_action_count"],
                },
                "reasons": [
                    "Dataset v0 has no continuous SLA or sustained-recovery windows.",
                    "There are no no-fault scenarios for a false-remediation denominator.",
                    "The approved sandbox intervention used a deterministic runbook, not a twin-assisted comparative policy.",
                    "All held-out model proposals abstained and none was applied.",
                ],
            },
        },
        "overall_decision": {
            "model_promotion": "no-go",
            "autonomous_or_live_actuation": "no-go",
            "H1_H2_H3_positive_claims": "no-go",
            "local_sandbox_research": "go-with-constraints",
        },
        "safety_lock": {
            "allow_live_actuation": safety["allow_live_actuation"],
            "require_human_approval": safety["require_human_approval"],
            "heldout_proposals_abstained": safety["abstain_count"],
            "heldout_proposals_applied": safety["applied_action_count"],
        },
        "required_next_evidence": [
            "At least 19 independent calibration scenarios for a finite nominal 90% split-conformal rank.",
            "Randomized or counterbalanced action order with alternative eligible actions and positivity.",
            "No-fault, harmful-action, and ineffective-action scenarios.",
            "Continuous SLA windows and sustained-recovery timing for SLA duration and MTTR.",
            "A predeclared rule-versus-twin-assisted, human-governed sandbox comparison before any hardware or operator claim.",
        ],
        "diagnostic_gate": {
            "leakage_checks_passed": all(diagnostics["leakage_checks"].values()),
            "scientific_readiness_gate_passed": diagnostics["scientific_readiness_gate_passed"],
            "calibration_status": uncertainty["calibration"]["status"],
        },
        "claim_boundary": (
            "Consolidated feasibility decision derived from versioned software-sandbox evidence. "
            "Radio remains simulated; no hardware measurement, operator validation, model "
            "promotion, or live-network conclusion is claimed."
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    hypotheses = report["hypotheses"]
    h1 = hypotheses["H1"]["observed"]
    h2 = hypotheses["H2"]["observed"]
    h3 = hypotheses["H3"]["observed"]

    def value(item: Any) -> str:
        if item is None:
            return "undefined"
        if isinstance(item, float):
            return f"{item:.3f}"
        return str(item)

    lines = [
        "# SafeTwin-5G Benchmark Decision v0",
        "",
        f"Run: `{report['run_id']}`  ",
        f"Evidence: `{report['evidence_label']}`; radio: `{report['radio_evidence_label']}`",
        "",
        "## Decision",
        "",
        "| Scope | Decision |",
        "|---|---|",
        "| Model promotion | **NO-GO** |",
        "| Autonomous or live actuation | **NO-GO** |",
        "| Positive H1-H3 claims | **NO-GO** |",
        "| Continued local sandbox research | **GO WITH CONSTRAINTS** |",
        "",
        "## Key endpoints",
        "",
        "| Hypothesis | Endpoint | Result |",
        "|---|---|---:|",
        f"| H1 | deterministic-rule test MAE | {value(h1['deterministic_rule_test_mae'])} |",
        f"| H1 | tabular-ridge test MAE | {value(h1['tabular_ridge_test_mae'])} |",
        f"| H1 | temporal-persistence test MAE | {value(h1['temporal_persistence_test_mae'])} |",
        f"| H1 | descriptive held-out proxy test MAE | {value(h1['heldout_proxy_test_mae'])} |",
        f"| H1 | alternative-action ATE | {value(h1['alternative_action_ate'])} ({h1['alternative_action_status']}) |",
        f"| H2 | coverage | {value(h2['coverage'])} |",
        f"| H2 | abstention rate | {value(h2['abstention_rate'])} |",
        f"| H2 | selective harmful-action rate | {value(h2['selective_harmful_rate'])} |",
        f"| H2 | always-act harmful-action rate | {value(h2['always_act_harmful_rate'])} |",
        f"| H2 | risk-coverage AUC | {value(h2['risk_coverage_auc'])} |",
        f"| H3 | SLA-violation duration | {value(h3['sla_violation_duration_s'])} |",
        f"| H3 | mean time to recovery | {value(h3['mean_time_to_recovery_s'])} |",
        f"| H3 | false-remediation rate | {value(h3['false_remediation_rate'])} |",
        f"| H3 | model-proposal actions applied | {value(h3['model_proposal_actions_applied'])} |",
        "",
        "## Hypotheses",
        "",
    ]
    for key in ("H1", "H2", "H3"):
        item = hypotheses[key]
        lines.extend(
            [
                f"### {key}: {item['status']}",
                "",
                f"Decision: `{item['decision']}`.",
                "",
                *[f"- {reason}" for reason in item["reasons"]],
                "",
            ]
        )
    lines.extend(
        [
            "## Required next evidence",
            "",
            *[f"- {item}" for item in report["required_next_evidence"]],
            "",
            "## Claim boundary",
            "",
            report["claim_boundary"],
            "",
            "Exact source paths and SHA-256 values are recorded in `source-evidence.json`.",
            "",
        ]
    )
    return "\n".join(lines)
