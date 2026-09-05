import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.audit_reconnect_r2_build import audit

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "evidence/engineering/20260905T071413Z-reconnect-r2-build"


class ReconnectR2BuildTests(unittest.TestCase):
    def copied(self):
        temporary = tempfile.TemporaryDirectory(prefix="safetwin-r2-build-fixture-")
        self.addCleanup(temporary.cleanup)
        target = Path(temporary.name) / "run"
        shutil.copytree(RUN, target)
        return target

    def change(self, target, name, mutate):
        file = target / name
        row = json.loads(file.read_text())
        mutate(row)
        file.write_text(json.dumps(row), encoding="utf-8")
        manifest = json.loads((target / "manifest.json").read_text())
        manifest["captured_file_sha256"][name] = hashlib.sha256(file.read_bytes()).hexdigest()
        (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_patch_replay_and_source_regression_never_promote_to_network_fix(self):
        result = audit(RUN)
        self.assertEqual(result["source_fixture_cases"], 16)
        self.assertEqual(result["changed_upstream_files"], 1)
        self.assertTrue(result["official_counterexample_verified"])
        self.assertFalse(result["network_fix_validated"])
        self.assertFalse(result["sandbox_image_applied"])
        lock = json.loads((ROOT / "config/experiments/reconnect-r2-images.json").read_text())
        self.assertEqual(lock["derived_image_id"], result["derived_image_id"])
        self.assertEqual(lock["patch_sha256"], result["patch_sha256"])

    def test_hash_consistent_network_claim_is_rejected(self):
        target = self.copied()
        self.change(target, "summary.json", lambda row: row.update(network_fix_validated=True))
        with self.assertRaisesRegex(ValueError, "claim boundary"):
            audit(target)

    def test_official_image_drift_is_rejected(self):
        target = self.copied()
        def mutate(row):
            image = json.loads(row["stdout"])
            image[0]["Id"] = "sha256:fixture-drift"
            row["stdout"] = json.dumps(image)
        self.change(target, "official-after.json", mutate)
        with self.assertRaisesRegex(ValueError, "official image preservation"):
            audit(target)

    def test_evidence_container_network_attachment_is_rejected(self):
        target = self.copied()
        def mutate(row):
            row["argv"][row["argv"].index("--network=none")] = "--network=safetwin5g-isolated"
        self.change(target, "capture-selection-fixtures.log.json", mutate)
        with self.assertRaisesRegex(ValueError, "unisolated evidence container"):
            audit(target)


if __name__ == "__main__":
    unittest.main()
