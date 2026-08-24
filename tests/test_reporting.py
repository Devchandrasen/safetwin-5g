import json
from pathlib import Path
import tempfile
import unittest

from safetwin5g.reporting import (
    SOURCE_MANIFESTS,
    build_decision_report,
    load_verified_sources,
    render_markdown,
    verify_manifest,
)


ROOT = Path(__file__).resolve().parents[1]


class ReportingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources, cls.source_evidence = load_verified_sources(ROOT)
        cls.report = build_decision_report(
            cls.sources, "test-benchmark-report-v0", "2026-08-24T00:00:00+00:00"
        )

    def test_all_source_manifests_are_verified_and_hashed(self):
        roles = {item["role"] for item in self.source_evidence["files"]}
        self.assertTrue(set(SOURCE_MANIFESTS).issubset(roles))
        for item in self.source_evidence["files"]:
            self.assertEqual(len(item["sha256"]), 64)

    def test_report_refuses_positive_hypothesis_claims(self):
        self.assertEqual(self.report["hypotheses"]["H1"]["status"], "not-supported")
        self.assertEqual(self.report["hypotheses"]["H2"]["status"], "not-supported")
        self.assertEqual(self.report["hypotheses"]["H3"]["status"], "not-tested")
        self.assertEqual(self.report["overall_decision"]["model_promotion"], "no-go")
        self.assertEqual(self.report["overall_decision"]["local_sandbox_research"], "go-with-constraints")

    def test_report_preserves_undefined_endpoints(self):
        h2 = self.report["hypotheses"]["H2"]["observed"]
        h3 = self.report["hypotheses"]["H3"]["observed"]
        self.assertIsNone(h2["selective_harmful_rate"])
        self.assertIsNone(h2["risk_coverage_auc"])
        self.assertIsNone(h3["sla_violation_duration_s"])
        self.assertIsNone(h3["mean_time_to_recovery_s"])

    def test_markdown_states_labels_and_no_go(self):
        markdown = render_markdown(self.report)
        self.assertIn("Evidence: `sandbox-measured`; radio: `simulated`", markdown)
        self.assertIn("Positive H1-H3 claims | **NO-GO**", markdown)
        self.assertIn("deterministic-rule test MAE | 3.333", markdown)
        self.assertIn("alternative-action ATE | undefined (not-identified)", markdown)
        self.assertIn("selective harmful-action rate | undefined", markdown)
        self.assertIn("### H3: not-tested", markdown)

    def test_tampered_source_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            bundle = Path(temp)
            (bundle / "captured.txt").write_text("actual", encoding="utf-8")
            (bundle / "manifest.json").write_text(
                json.dumps({"captured_file_sha256": {"captured.txt": "0" * 64}}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "hash mismatch"):
                verify_manifest(bundle / "manifest.json")


if __name__ == "__main__":
    unittest.main()
