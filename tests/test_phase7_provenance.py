import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from safetwin5g.dataset_v1 import sha256
from safetwin5g.phase7_provenance import audit_chain


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")


class Phase7ProvenanceTests(unittest.TestCase):
    def build_fixture(self, root: Path):
        campaign = root / "evidence" / "scenarios" / "fixture-campaign"
        dataset = root / "data" / "releases" / "fixture-dataset"
        analysis = root / "evidence" / "benchmarks" / "fixture-analysis"
        scalability = root / "evidence" / "benchmarks" / "fixture-scalability"
        write_json(
            campaign / "summary.json",
            {
                "passed": True,
                "completed_unit_count": 675,
                "completed_block_count": 135,
                "experimental_mutation_count": 540,
                "aborted_for_cleanup": False,
                "evidence_label": "sandbox-measured",
                "radio_evidence_label": "simulated",
            },
        )
        write_json(campaign / "manifest.json", {"passed": True})
        write_json(
            dataset / "manifest.json",
            {
                "passed": True,
                "record_count": 675,
                "source_bundle": "evidence/scenarios/fixture-campaign",
                "source_manifest_sha256": sha256(campaign / "manifest.json"),
                "evidence_label": "sandbox-measured",
                "radio_evidence_label": "simulated",
            },
        )
        write_json(
            dataset / "data-quality.json",
            {
                "release_eligible": True,
                "limitations": [
                    "Unrelated co-resident containers create an uncontrolled shared-host contention limitation."
                ],
            },
        )
        dataset_hash = sha256(dataset / "manifest.json")
        write_json(
            analysis / "report.json",
            {
                "execution_passed": True,
                "dataset_manifest_sha256": dataset_hash,
                "decision": {
                    "TNSM_claim_gate": "no-go",
                    "live_actuation": "no-go",
                    "submission_authorized": False,
                },
            },
        )
        write_json(
            analysis / "source-evidence.json",
            {
                "dataset_manifest_sha256": dataset_hash,
                "test_labels_opened_after_lock_verification": True,
            },
        )
        write_json(analysis / "manifest.json", {"TNSM_claim_gate": "no-go"})
        write_json(
            scalability / "report.json",
            {
                "input_evidence_label": "fixture",
                "network_performance_claim": False,
                "hardware_or_operator_claim": False,
                "decision_batch": {"apply_allowed": False},
            },
        )
        write_json(scalability / "manifest.json", {"passed": True})
        return campaign, dataset, analysis, scalability

    def test_complete_chain_passes_and_retains_no_go(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self.build_fixture(root)
            result = audit_chain(
                campaign=paths[0],
                dataset=paths[1],
                analysis=paths[2],
                scalability=paths[3],
                project_root=root,
            )
            self.assertTrue(result["passed"])
            self.assertEqual(result["TNSM_claim_gate"], "no-go")
            self.assertTrue(result["environment_deviation_D1_disclosed"])
            self.assertEqual(result["claim_tiers"]["scalability_input"], "fixture")

    def test_hash_break_and_claim_tier_promotion_fail_closed(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            paths = self.build_fixture(root)
            manifest = json.loads((paths[1] / "manifest.json").read_text(encoding="utf-8"))
            manifest["source_manifest_sha256"] = "0" * 64
            write_json(paths[1] / "manifest.json", manifest)
            with self.assertRaises(AssertionError):
                audit_chain(
                    campaign=paths[0],
                    dataset=paths[1],
                    analysis=paths[2],
                    scalability=paths[3],
                    project_root=root,
                )

            paths = self.build_fixture(root)
            summary = json.loads((paths[0] / "summary.json").read_text(encoding="utf-8"))
            summary["evidence_label"] = "operator-validated"
            write_json(paths[0] / "summary.json", summary)
            with self.assertRaises(AssertionError):
                audit_chain(
                    campaign=paths[0],
                    dataset=paths[1],
                    analysis=paths[2],
                    scalability=paths[3],
                    project_root=root,
                )


if __name__ == "__main__":
    unittest.main()
