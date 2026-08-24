from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from safetwin5g.dataset_v1 import build_records, build_release, quality_report


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evidence" / "scenarios" / "20260824T074320Z-phase6-campaign-v1"


class DatasetV1Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = build_records(SOURCE)
        cls.report = quality_report(cls.records)

    def test_records_match_preregistered_counts_and_labels(self):
        self.assertEqual(len(self.records), 132)
        self.assertEqual(len({record["unit_id"] for record in self.records}), 132)
        self.assertEqual(
            {
                split: sum(record["split"] == split for record in self.records)
                for split in ("train", "calibration", "test", "ood")
            },
            {"train": 42, "calibration": 21, "test": 21, "ood": 48},
        )
        self.assertEqual(
            {record["evidence_label"] for record in self.records},
            {"sandbox-measured"},
        )
        self.assertEqual(
            {record["radio_evidence_label"] for record in self.records}, {"simulated"}
        )
        self.assertTrue(all(record["hardware_evidence_label"] is None for record in self.records))
        self.assertTrue(all(record["operator_validation"] is False for record in self.records))

    def test_all_44_blocks_have_three_action_arms(self):
        blocks = {}
        for record in self.records:
            blocks.setdefault(record["assignment_block_id"], set()).add(
                record["action_arm"]
            )
        self.assertEqual(len(blocks), 44)
        self.assertTrue(
            all(
                arms == {"effective", "no_action", "negative_control"}
                for arms in blocks.values()
            )
        )

    def test_repeated_windows_and_endpoints_are_explicit(self):
        self.assertEqual(self.report["telemetry_sample_count"], 1584)
        self.assertGreater(self.report["metric_cells"], 0)
        self.assertGreater(self.report["missing_metric_cells"], 0)
        self.assertGreater(self.report["harmful_action_count"], 0)
        self.assertGreater(self.report["false_remediation_count"], 0)
        self.assertNotIn("right-censored", self.report["mttr_status_counts"])

    def test_quality_gate_passes_and_preserves_limitations(self):
        self.assertTrue(self.report["passed"], self.report["checks"])
        self.assertTrue(all(self.report["checks"].values()))
        self.assertGreaterEqual(len(self.report["limitations"]), 8)
        self.assertIn("conditional", self.report["causal_identification_status"])

    def test_release_is_hash_manifested_and_immutable(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "release"
            manifest = build_release(SOURCE, output)
            self.assertTrue(manifest["frozen"])
            self.assertEqual(manifest["record_count"], 132)
            self.assertEqual(
                len((output / "records.jsonl").read_text(encoding="utf-8").splitlines()),
                132,
            )
            with self.assertRaises(FileExistsError):
                build_release(SOURCE, output)


if __name__ == "__main__":
    unittest.main()
