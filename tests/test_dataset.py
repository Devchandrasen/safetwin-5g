import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from safetwin5g.dataset import build_records, build_release, quality_report


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "evidence" / "scenarios" / "20260824T051612Z-scenario-matrix-v0"


class DatasetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = build_records(SOURCE)

    def test_records_preserve_scenarios_and_claim_boundaries(self):
        self.assertEqual(len(self.records), 12)
        self.assertEqual(len({record["scenario_id"] for record in self.records}), 12)
        self.assertEqual({record["evidence_label"] for record in self.records}, {"sandbox-measured"})
        self.assertEqual({record["radio_evidence_label"] for record in self.records}, {"simulated"})

    def test_splits_are_disjoint_and_balanced(self):
        counts = {
            split: sum(record["split"] == split for record in self.records)
            for split in ("train", "calibration", "test", "ood")
        }
        self.assertEqual(counts, {"train": 3, "calibration": 3, "test": 3, "ood": 3})
        by_group = {}
        for record in self.records:
            by_group.setdefault(record["group_id"], set()).add(record["split"])
        self.assertTrue(all(len(splits) == 1 for splits in by_group.values()))

    def test_quality_report_exposes_causal_limitations(self):
        report = quality_report(self.records)
        self.assertTrue(report["passed"])
        self.assertEqual(
            report["causal_identification_status"],
            "not identified for alternative actions",
        )
        self.assertGreaterEqual(len(report["limitations"]), 6)
        self.assertEqual(report["metric_cells"], 720)
        self.assertEqual(report["missing_metric_cells"], 32)

    def test_release_is_hash_manifested_and_refuses_overwrite(self):
        with TemporaryDirectory() as directory:
            output = Path(directory) / "release"
            manifest = build_release(SOURCE, output)
            self.assertTrue(manifest["frozen"])
            self.assertEqual(manifest["record_count"], 12)
            self.assertEqual(
                len((output / "records.jsonl").read_text(encoding="utf-8").splitlines()),
                12,
            )
            with self.assertRaises(FileExistsError):
                build_release(SOURCE, output)


if __name__ == "__main__":
    unittest.main()
