from copy import deepcopy
import unittest

from safetwin5g.contracts import InterventionRecord


def valid_payload():
    return {
        "record_id": "test-001",
        "scenario_id": "upf-cpu-001",
        "observed_at": "2026-08-24T10:00:00Z",
        "environment": "sandbox",
        "fault_type": "upf_cpu_saturation",
        "pre_metrics": {"latency_ms": 125.0, "upf_cpu_pct": 92.0},
        "action": {
            "kind": "nf_scale",
            "target": "upf-1",
            "target_type": "upf",
            "parameters": {"replicas": 2},
            "reversible": True,
            "rollback_plan": "Restore one replica.",
            "estimated_risk": 0.2,
        },
        "decision_source": "model",
        "model_confidence": 0.9,
        "ood_score": 0.1,
        "expected_effects": {"latency_ms_delta": -30.0},
        "post_metrics": None,
        "evidence_label": "sandbox-measured",
    }


class ContractTests(unittest.TestCase):
    def test_valid_record_round_trips(self):
        record = InterventionRecord.from_dict(valid_payload())
        self.assertEqual(record.action.kind, "nf_scale")
        self.assertEqual(record.to_dict()["pre_metrics"]["latency_ms"], 125.0)

    def test_timestamp_requires_timezone(self):
        payload = valid_payload()
        payload["observed_at"] = "2026-08-24T10:00:00"
        with self.assertRaisesRegex(ValueError, "timezone"):
            InterventionRecord.from_dict(payload)

    def test_boolean_is_not_a_metric(self):
        payload = valid_payload()
        payload["pre_metrics"]["upf_ready"] = True
        with self.assertRaisesRegex(ValueError, "must be numeric"):
            InterventionRecord.from_dict(payload)

    def test_risk_must_be_bounded(self):
        payload = deepcopy(valid_payload())
        payload["action"]["estimated_risk"] = 1.2
        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            InterventionRecord.from_dict(payload)

    def test_evidence_label_must_match_environment(self):
        payload = valid_payload()
        payload["environment"] = "fixture"
        with self.assertRaisesRegex(ValueError, "incompatible"):
            InterventionRecord.from_dict(payload)

    def test_deterministic_runbook_does_not_claim_model_scores(self):
        payload = valid_payload()
        payload["decision_source"] = "deterministic-runbook"
        payload["model_confidence"] = None
        payload["ood_score"] = None
        record = InterventionRecord.from_dict(payload)
        self.assertIsNone(record.model_confidence)
        self.assertIsNone(record.ood_score)

    def test_non_model_source_rejects_fabricated_confidence(self):
        payload = valid_payload()
        payload["decision_source"] = "deterministic-runbook"
        payload["ood_score"] = None
        with self.assertRaisesRegex(ValueError, "must not claim"):
            InterventionRecord.from_dict(payload)

    def test_model_record_can_represent_unavailable_uncertainty(self):
        payload = valid_payload()
        payload["model_confidence"] = None
        payload["ood_score"] = None
        record = InterventionRecord.from_dict(payload)
        self.assertIsNone(record.model_confidence)
        self.assertIsNone(record.ood_score)


if __name__ == "__main__":
    unittest.main()
