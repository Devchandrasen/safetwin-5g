"""Route held-out model proposals through the sandbox-only safety policy."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.baselines import load_records  # noqa: E402
from safetwin5g.contracts import InterventionRecord  # noqa: E402
from safetwin5g.safety import Decision, SafetyPolicy  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def action_payload(record: dict) -> dict:
    family = record["fault_family"]
    if family == "packet_impairment":
        return {
            "kind": "network_impairment_clear",
            "target": "safetwin5g-ue/uesimtun0",
            "target_type": "ue_tunnel",
            "parameters": {"qdisc": "fq_codel"},
            "reversible": True,
            "rollback_plan": "Reapply the exact measured netem loss setting.",
            "estimated_risk": 0.05,
        }
    if family == "network_function_interruption":
        return {
            "kind": "nf_process_resume",
            "target": "safetwin5g-open5gs/open5gs-upfd",
            "target_type": "upf",
            "parameters": {"signal": "CONT"},
            "reversible": True,
            "rollback_plan": "Send STOP to the same recorded UPF PID.",
            "estimated_risk": 0.15,
        }
    if family == "cpu_saturation":
        return {
            "kind": "cpu_stress_stop",
            "target": "safetwin5g-open5gs",
            "target_type": "core_container",
            "parameters": {"signal": "TERM", "process": "yes"},
            "reversible": True,
            "rollback_plan": "Restart the same number of pinned CPU workers.",
            "estimated_risk": 0.10,
        }
    raise ValueError(f"unsupported fault family: {family}")


def main() -> int:
    dataset = ROOT / "data" / "releases" / "safetwin5g-interventions-v0"
    uncertainty = (
        ROOT
        / "evidence"
        / "benchmarks"
        / "20260824T053654Z-uncertainty-ood-v0"
    )
    records = {
        record["scenario_id"]: record
        for record in load_records(dataset / "records.jsonl")
        if record["split"] in {"test", "ood"}
    }
    assessments = load_jsonl(uncertainty / "assessments.jsonl")
    policy = SafetyPolicy.from_path(ROOT / "config" / "actions.json")
    outputs = []
    for assessment in assessments:
        source = records[assessment["scenario_id"]]
        fault_metrics = {
            key: float(value)
            for key, value in source["stages"]["fault"]["metrics"].items()
        }
        payload = {
            "record_id": f"proposal-{source['scenario_id']}",
            "scenario_id": source["scenario_id"],
            "observed_at": source["stages"]["fault"]["observed_at"],
            "environment": "sandbox",
            "fault_type": source["fault_family"],
            "pre_metrics": fault_metrics,
            "action": action_payload(source),
            "decision_source": "model",
            "model_confidence": None,
            "ood_score": assessment["ood_score"],
            "expected_effects": {
                "paired_benefit_prediction": float(assessment["prediction"])
            },
            "post_metrics": None,
            "evidence_label": "sandbox-measured",
        }
        proposal = InterventionRecord.from_dict(payload)
        evaluation = policy.evaluate(proposal)
        if evaluation.decision is not Decision.ABSTAIN:
            raise RuntimeError(
                f"proposal did not abstain: {source['scenario_id']} {evaluation.decision}"
            )
        live_payload = dict(payload)
        live_payload["record_id"] = f"live-sentinel-{source['scenario_id']}"
        live_payload["environment"] = "live"
        live_payload["evidence_label"] = "operator-validated"
        live_evaluation = policy.evaluate(InterventionRecord.from_dict(live_payload))
        if live_evaluation.decision is not Decision.REJECT:
            raise RuntimeError("live sentinel was not rejected")
        outputs.append(
            {
                "proposal": proposal.to_dict(),
                "safety_evaluation": evaluation.to_dict(),
                "live_sentinel_evaluation": live_evaluation.to_dict(),
                "execution_status": "not-applied",
                "human_approval_requested": False,
                "reason": "proposal abstained before approval eligibility",
            }
        )
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ-safety-integration-v0")
    output = ROOT / "evidence" / "benchmarks" / run_id
    output.mkdir(parents=True, exist_ok=False)
    (output / "proposals.jsonl").write_text(
        "".join(
            json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n"
            for item in outputs
        ),
        encoding="utf-8",
    )
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": started.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "execution_passed": True,
        "proposal_count": len(outputs),
        "abstain_count": sum(
            item["safety_evaluation"]["decision"] == "abstain" for item in outputs
        ),
        "approval_required_count": sum(
            item["safety_evaluation"]["decision"] == "require-human-approval"
            for item in outputs
        ),
        "applied_action_count": sum(
            item["execution_status"] == "applied" for item in outputs
        ),
        "live_sentinel_reject_count": sum(
            item["live_sentinel_evaluation"]["decision"] == "reject"
            for item in outputs
        ),
        "policy_version": policy.policy_version,
        "allow_live_actuation": policy.allow_live,
        "require_human_approval": bool(policy.config["require_human_approval"]),
        "evidence_label": "sandbox-measured",
        "radio_evidence_label": "simulated",
        "policy_sha256": sha256(ROOT / "config" / "actions.json"),
        "uncertainty_manifest_sha256": sha256(uncertainty / "manifest.json"),
        "claim_boundary": (
            "Proposal-only integration test. All held-out model proposals abstained; "
            "no action was applied and every live sentinel was rejected."
        ),
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    captured = {
        path.name: sha256(path)
        for path in sorted(output.iterdir())
        if path.is_file() and path.name != "manifest.json"
    }
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_id,
                "passed": True,
                "evidence_label": "sandbox-measured",
                "captured_file_sha256": captured,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(output)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
