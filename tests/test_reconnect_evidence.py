"""Retain a measured failure reproduction; tampered copies remain fixtures."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.audit_reconnect import audit

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "evidence/engineering/20260905T062044Z-reconnect-r1"
RUNTIME = ROOT / "evidence/engineering/20260905T062044Z-reconnect-r1-runtime"


class RetainedReconnectTests(unittest.TestCase):
    def copied_run(self):
        temporary = tempfile.TemporaryDirectory(prefix="safetwin-reconnect-fixture-")
        self.addCleanup(temporary.cleanup)
        target = Path(temporary.name) / "run"
        shutil.copytree(RUN, target)
        return target

    def change_json(self, target, name, mutate):
        path = target / name
        value = json.loads(path.read_text())
        mutate(value)
        path.write_text(json.dumps(value), encoding="utf-8")
        manifest = json.loads((target / "manifest.json").read_text())
        manifest["captured_file_sha256"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
        (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_all_raw_samples_reproduce_failure_but_never_validate_fix(self):
        result = audit(RUN)
        self.assertTrue(result["protocol_execution_valid"])
        self.assertTrue(result["reconnect_failure_reproduced"])
        self.assertEqual(result["commands_replayed"], 280)
        self.assertEqual(result["samples_replayed"], 30)
        self.assertEqual([r["post_received"] for r in result["post_packet_counts"]], [15, 0, 0, 15])
        for key in ("network_fix_validated", "long_campaign_ready", "TNSM_ready"):
            self.assertFalse(result[key])

    def test_hash_consistent_claim_promotion_is_rejected(self):
        target = self.copied_run()
        self.change_json(target, "summary.json", lambda row: row.update(TNSM_ready=True))
        with self.assertRaisesRegex(ValueError, "claim/budget gate: TNSM_ready"):
            audit(target)

    def test_hash_consistent_packet_relabelling_is_rejected(self):
        target = self.copied_run()
        self.change_json(target, "trial-02.json", lambda row: row["post"][0]["metrics"].update(packets_received=5))
        with self.assertRaisesRegex(ValueError, "durable sample mismatch"):
            audit(target)

    def test_omitted_control_is_rejected_even_with_matching_manifest(self):
        target = self.copied_run()
        (target / "trial-04.json").unlink()
        # Keep this fixture's inventory valid
        # so the independent four-trial requirement, not just hashing, is tested.
        manifest = json.loads((target / "manifest.json").read_text())
        manifest["captured_file_sha256"].pop("trial-04.json")
        (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "incomplete reproduction protocol"):
            audit(target)

    def test_wrapper_transcript_hash_and_sleep_cleanup_are_retained(self):
        manifest = json.loads((RUNTIME / "manifest.json").read_text())["captured_file_sha256"]
        for name, value in manifest.items():
            self.assertEqual(hashlib.sha256((RUNTIME / name).read_bytes()).hexdigest(), value)
        text = (RUNTIME / "wrapper.log").read_text()
        self.assertIn("SLEEP_INHIBITION_CLEARED=true", text)
        self.assertIn("CHILD_EXIT_CODE=\n", text)


if __name__ == "__main__":
    unittest.main()
