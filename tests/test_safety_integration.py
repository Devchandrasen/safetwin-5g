import json
from pathlib import Path
import unittest

from safetwin5g.baselines import load_records
from safetwin5g.contracts import InterventionRecord
from safetwin5g.safety import Decision, SafetyPolicy
from tools.run_safety_integration import action_payload


ROOT = Path(__file__).resolve().parents[1]


class SafetyIntegrationTests(unittest.TestCase):
    def test_all_heldout_uncertain_proposals_abstain(self):
        records = {
            record["scenario_id"]: record
            for record in load_records(
                ROOT
                / "data"
                / "releases"
                / "safetwin5g-interventions-v0"
                / "records.jsonl"
            )
            if record["split"] in {"test", "ood"}
        }
        assessment_path = (
            ROOT
            / "evidence"
            / "benchmarks"
            / "20260824T053654Z-uncertainty-ood-v0"
            / "assessments.jsonl"
        )
        assessments = [
            json.loads(line)
            for line in assessment_path.read_text(encoding="utf-8").splitlines()
        ]
        policy = SafetyPolicy.from_path(ROOT / "config" / "actions.json")
        decisions = []
        for assessment in assessments:
            source = records[assessment["scenario_id"]]
            proposal = InterventionRecord.from_dict(
                {
                    "record_id": f"test-{source['scenario_id']}",
                    "scenario_id": source["scenario_id"],
                    "observed_at": source["stages"]["fault"]["observed_at"],
                    "environment": "sandbox",
                    "fault_type": source["fault_family"],
                    "pre_metrics": source["stages"]["fault"]["metrics"],
                    "action": action_payload(source),
                    "decision_source": "model",
                    "model_confidence": None,
                    "ood_score": assessment["ood_score"],
                    "expected_effects": {"benefit": assessment["prediction"]},
                    "post_metrics": None,
                    "evidence_label": "sandbox-measured",
                }
            )
            decisions.append(policy.evaluate(proposal).decision)
        self.assertEqual(decisions, [Decision.ABSTAIN] * 6)


if __name__ == "__main__":
    unittest.main()
