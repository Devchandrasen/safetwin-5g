"""Fail-closed local manuscript gate for the Phase 7 TNSM candidate."""

from __future__ import annotations

from typing import Any


def assess_tnsm_manuscript_gate(
    analysis_report: dict[str, Any], end_to_end_verification: dict[str, Any]
) -> dict[str, Any]:
    gates = analysis_report.get("gates", {})
    boundaries = analysis_report.get("claim_boundaries", {})
    decision = analysis_report.get("decision", {})
    checks = {
        "analysis_execution_passed": analysis_report.get("execution_passed") is True,
        "G1_passed": gates.get("G1", {}).get("passed") is True,
        "G2_passed": gates.get("G2", {}).get("passed") is True,
        "G3_passed": gates.get("G3", {}).get("passed") is True,
        "G4_passed": gates.get("G4", {}).get("passed") is True,
        "analysis_claim_gate_go": decision.get("TNSM_claim_gate") == "go",
        "actual_end_to_end_audit_passed": end_to_end_verification.get("passed") is True,
        "end_to_end_claim_gate_agrees": end_to_end_verification.get("TNSM_claim_gate")
        == decision.get("TNSM_claim_gate"),
        "D1_environment_deviation_disclosed": end_to_end_verification.get(
            "environment_deviation_D1_disclosed"
        )
        is True,
        "procedural_seal_disclosed": end_to_end_verification.get(
            "procedural_outcome_seal"
        )
        is True,
        "no_cryptographic_blinding_claim": end_to_end_verification.get(
            "cryptographic_blinding"
        )
        is False,
        "sandbox_evidence_only": boundaries.get("evidence_label")
        == "sandbox-measured",
        "simulated_radio_only": boundaries.get("radio_evidence_label") == "simulated",
        "no_hardware_claim": boundaries.get("hardware_evidence_label") is None,
        "no_operator_claim": boundaries.get("operator_validation") is False,
        "no_conditional_coverage_claim": boundaries.get("conditional_coverage_claimed")
        is False,
        "no_live_network_claim": boundaries.get("live_network_claimed") is False,
        "live_actuation_remains_no_go": decision.get("live_actuation") == "no-go"
        and end_to_end_verification.get("live_actuation") == "no-go",
        "submission_not_authorized": decision.get("submission_authorized") is False
        and end_to_end_verification.get("submission_authorized") is False,
    }
    local_go = all(checks.values())
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": 1,
        "passed": local_go,
        "local_manuscript_draft_gate": "go" if local_go else "no-go",
        "publication_submission": "pending-external-authorization",
        "live_actuation": "no-go",
        "checks": checks,
        "failed_checks": failed,
        "allowed_if_go": (
            "Draft a claim-bounded TNSM manuscript from the frozen report and artifacts."
            if local_go
            else None
        ),
        "required_if_no_go": (
            None
            if local_go
            else "Preserve the negative decision and do not draft positive novelty or superiority claims."
        ),
    }
