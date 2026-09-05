"""Regression checks on a retained negative sandbox result, not fixture promotion."""
import hashlib
import json
from pathlib import Path
import unittest

from tools.audit_recovery_pilot import audit, replay_sample

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "evidence/engineering/20260905T051750Z-recovery-pilot-r1"


class RetainedRecoveryPilotTests(unittest.TestCase):
    def test_retained_manifest_matches_every_captured_file(self):
        manifest = json.loads((RUN / "manifest.json").read_text())["captured_file_sha256"]
        self.assertEqual(set(manifest), {p.name for p in RUN.iterdir() if p.name != "manifest.json"})
        for name, expected in manifest.items():
            self.assertEqual(hashlib.sha256((RUN / name).read_bytes()).hexdigest(), expected, name)

    def test_failed_pilot_is_not_accepted_despite_terminal_restoration(self):
        with self.assertRaisesRegex(ValueError, "incomplete pilot"):
            audit(RUN)

    def test_failed_baseline_injected_nothing_and_retained_failed_recovery(self):
        commands = {r["sequence"]: r for r in (json.loads(line) for line in (RUN / "commands.jsonl").read_text().splitlines())}
        samples = [json.loads(line) for line in (RUN / "samples.jsonl").read_text().splitlines()]
        self.assertEqual([replay_sample(s, commands) for s in samples], [False] * 6 + [True] * 3)
        self.assertFalse(any(r["name"] in ("suspend-upf", "resume-watchdog") for r in commands.values()))
        self.assertEqual([r["argv"] for r in commands.values() if r["argv"][:2] == ["docker", "restart"]], [["docker", "restart", "safetwin5g-ue"]])
        summary = json.loads((RUN / "summary.json").read_text())
        self.assertFalse(summary["passed"])
        self.assertTrue(summary["final_service_restored"])
        self.assertFalse(summary["long_campaign_ready"])


if __name__ == "__main__":
    unittest.main()
