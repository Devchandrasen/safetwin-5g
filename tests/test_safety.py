from copy import deepcopy
from pathlib import Path
import unittest

from safetwin5g.contracts import InterventionRecord
from safetwin5g.safety import Decision, SafetyPolicy
from test_contracts import valid_payload


ROOT = Path(__file__).resolve().parents[1]


class SafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = SafetyPolicy.from_path(ROOT / "config" / "actions.json")

    def evaluate(self, payload=None):
        return self.policy.evaluate(InterventionRecord.from_dict(payload or valid_payload()))

    def test_eligible_action_still_requires_human_approval(self):
        self.assertEqual(self.evaluate().decision, Decision.REQUIRE_APPROVAL)

    def test_low_confidence_abstains(self):
        payload = valid_payload()
        payload["model_confidence"] = 0.6
        self.assertEqual(self.evaluate(payload).decision, Decision.ABSTAIN)

    def test_distribution_shift_abstains(self):
        payload = valid_payload()
        payload["ood_score"] = 0.7
        self.assertEqual(self.evaluate(payload).decision, Decision.ABSTAIN)

    def test_live_action_is_rejected(self):
        payload = valid_payload()
        payload["environment"] = "live"
        payload["evidence_label"] = "operator-validated"
        self.assertEqual(self.evaluate(payload).decision, Decision.REJECT)

    def test_irreversible_action_is_rejected(self):
        payload = valid_payload()
        payload["action"]["reversible"] = False
        self.assertEqual(self.evaluate(payload).decision, Decision.REJECT)

    def test_unknown_action_is_rejected(self):
        payload = deepcopy(valid_payload())
        payload["action"]["kind"] = "delete_network"
        self.assertEqual(self.evaluate(payload).decision, Decision.REJECT)

    def test_deterministic_runbook_still_requires_approval(self):
        payload = valid_payload()
        payload["decision_source"] = "deterministic-runbook"
        payload["model_confidence"] = None
        payload["ood_score"] = None
        self.assertEqual(self.evaluate(payload).decision, Decision.REQUIRE_APPROVAL)

    def test_sandbox_only_action_is_rejected_in_simulator(self):
        payload = valid_payload()
        payload["environment"] = "simulator"
        payload["evidence_label"] = "simulated"
        self.assertEqual(self.evaluate(payload).decision, Decision.REJECT)

    def test_action_only_evaluation_avoids_fabricated_model_fields(self):
        record = InterventionRecord.from_dict(valid_payload())
        result = self.policy.evaluate_action(
            record.action,
            environment="sandbox",
            decision_source="deterministic-runbook",
        )
        self.assertEqual(result.decision, Decision.REQUIRE_APPROVAL)

    def test_unavailable_confidence_and_high_ood_both_cause_abstention(self):
        payload = valid_payload()
        payload["model_confidence"] = None
        payload["ood_score"] = 1.0
        result = self.evaluate(payload)
        self.assertEqual(result.decision, Decision.ABSTAIN)
        self.assertIn("confidence is unavailable", result.reasons[0])
        self.assertIn("OOD score 1.000", result.reasons[1])


if __name__ == "__main__":
    unittest.main()
