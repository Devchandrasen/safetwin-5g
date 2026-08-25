"""Cross-artifact provenance checks for the complete Phase 7 evidence chain."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .dataset_v1 import sha256


def load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def relative(path: Path, project_root: Path) -> str:
    return str(path.resolve().relative_to(project_root.resolve())).replace("\\", "/")


def audit_chain(
    *,
    campaign: Path,
    dataset: Path,
    analysis: Path,
    scalability: Path,
    project_root: Path,
) -> dict[str, Any]:
    """Verify semantic and hash links without trusting any one summary file."""

    campaign_summary = load(campaign / "summary.json")
    campaign_manifest = load(campaign / "manifest.json")
    dataset_manifest = load(dataset / "manifest.json")
    dataset_quality = load(dataset / "data-quality.json")
    analysis_report = load(analysis / "report.json")
    analysis_sources = load(analysis / "source-evidence.json")
    analysis_manifest = load(analysis / "manifest.json")
    scalability_report = load(scalability / "report.json")
    scalability_manifest = load(scalability / "manifest.json")

    assert campaign_summary["passed"] is True
    assert campaign_summary["completed_unit_count"] == 675
    assert campaign_summary["completed_block_count"] == 135
    assert campaign_summary["experimental_mutation_count"] == 540
    assert campaign_summary["aborted_for_cleanup"] is False
    assert campaign_manifest["passed"] is True

    assert dataset_manifest["passed"] is True
    assert dataset_manifest["record_count"] == 675
    assert dataset_manifest["source_bundle"] == relative(campaign, project_root)
    assert dataset_manifest["source_manifest_sha256"] == sha256(campaign / "manifest.json")
    assert dataset_quality["release_eligible"] is True
    assert any(
        "co-resident" in limitation and "shared-host" in limitation
        for limitation in dataset_quality["limitations"]
    )

    dataset_manifest_hash = sha256(dataset / "manifest.json")
    assert analysis_report["execution_passed"] is True
    assert analysis_report["dataset_manifest_sha256"] == dataset_manifest_hash
    assert analysis_sources["dataset_manifest_sha256"] == dataset_manifest_hash
    assert analysis_sources["test_labels_opened_after_lock_verification"] is True
    assert analysis_manifest["TNSM_claim_gate"] == analysis_report["decision"]["TNSM_claim_gate"]
    assert analysis_report["decision"]["live_actuation"] == "no-go"
    assert analysis_report["decision"]["submission_authorized"] is False

    assert scalability_manifest["passed"] is True
    assert scalability_report["input_evidence_label"] == "fixture"
    assert scalability_report["network_performance_claim"] is False
    assert scalability_report["hardware_or_operator_claim"] is False
    assert scalability_report["decision_batch"]["apply_allowed"] is False

    tiers = {
        "campaign_intervention": campaign_summary["evidence_label"],
        "campaign_radio": campaign_summary["radio_evidence_label"],
        "dataset_intervention": dataset_manifest["evidence_label"],
        "dataset_radio": dataset_manifest["radio_evidence_label"],
        "scalability_input": scalability_report["input_evidence_label"],
    }
    assert tiers == {
        "campaign_intervention": "sandbox-measured",
        "campaign_radio": "simulated",
        "dataset_intervention": "sandbox-measured",
        "dataset_radio": "simulated",
        "scalability_input": "fixture",
    }
    return {
        "passed": True,
        "campaign_manifest_sha256": sha256(campaign / "manifest.json"),
        "dataset_manifest_sha256": dataset_manifest_hash,
        "analysis_manifest_sha256": sha256(analysis / "manifest.json"),
        "scalability_manifest_sha256": sha256(scalability / "manifest.json"),
        "TNSM_claim_gate": analysis_report["decision"]["TNSM_claim_gate"],
        "live_actuation": "no-go",
        "submission_authorized": False,
        "environment_deviation_D1_disclosed": True,
        "claim_tiers": tiers,
    }
