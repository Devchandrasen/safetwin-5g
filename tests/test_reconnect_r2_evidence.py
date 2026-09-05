"""Keep the measured partial correction rejected; altered copies are fixtures."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.audit_reconnect_r2 import audit

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "evidence/engineering/20260905T082014Z-reconnect-r2"
RUNTIME = ROOT / "evidence/engineering/20260905T082013Z-reconnect-r2-runtime"


class RetainedR2NetworkTests(unittest.TestCase):
    def copied(self):
        temporary = tempfile.TemporaryDirectory(prefix="safetwin-r2-network-fixture-")
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

    def test_audited_six_trial_prefix_is_not_an_accepted_fix(self):
        result = audit(RUN)
        self.assertTrue(result["audit_passed"])
        self.assertFalse(result["protocol_execution_valid"])
        self.assertFalse(result["network_fix_validated"])
        self.assertEqual(result["completed_trials"], 6)
        self.assertEqual(result["commands_replayed"], 480)
        self.assertEqual(result["samples_replayed"], 48)
        self.assertEqual([r["post_received"] for r in result["post_packet_counts"]], [15, 0, 0, 15, 15, 14])
        self.assertEqual(result["stop_reason"], "candidate_recovery_not_verified")
        self.assertTrue(result["official_image_restored"] and result["final_service_restored"])
        self.assertFalse((RUN / "trial-07.json").exists())
        self.assertFalse((RUN / "trial-08.json").exists())

    def test_hash_consistent_fix_promotion_is_rejected(self):
        target = self.copied()
        self.change(target, "summary.json", lambda row: row.update(network_fix_validated=True))
        with self.assertRaisesRegex(ValueError, "terminal execution/fix gate"):
            audit(target)

    def test_first_lost_packet_cannot_be_relabelled_clean(self):
        target = self.copied()
        self.change(target, "trial-06.json", lambda row: row["post"][0]["metrics"].update(packets_received=5, packet_loss_pct=0))
        with self.assertRaisesRegex(ValueError, "window/durable linkage"):
            audit(target)

    def test_service_accept_does_not_override_packet_loss(self):
        rows = [json.loads(line) for line in (RUN / "commands.jsonl").read_text().splitlines()]
        trial = json.loads((RUN / "trial-06.json").read_text())
        self.assertEqual([s["metrics"]["packets_received"] for s in trial["post"]], [4, 5, 5])
        ping = next(r for r in rows if r["sequence"] == 393)["stdout"]
        self.assertNotIn("icmp_seq=1 ", ping)
        self.assertIn("icmp_seq=2 ", ping)
        ue = next(r for r in rows if r["unit_id"] == "derived:drop-a" and r["name"] == "post-safetwin5g-ue")["stdout"]
        self.assertIn("Service Accept received", ue)
        self.assertFalse(trial["candidate_recovery_verified"])

    def test_wrapper_hash_and_sleep_cleanup_remain_intact(self):
        manifest = json.loads((RUNTIME / "manifest.json").read_text())["captured_file_sha256"]
        self.assertEqual(set(manifest), {"wrapper.log"})
        self.assertEqual(hashlib.sha256((RUNTIME / "wrapper.log").read_bytes()).hexdigest(), manifest["wrapper.log"])
        self.assertIn("SLEEP_INHIBITION_CLEARED=true", (RUNTIME / "wrapper.log").read_text())


if __name__ == "__main__":
    unittest.main()
