"""Retain the source mechanism without upgrading it to measured network proof."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.audit_reconnect_packet import audit
from tools.diagnose_reconnect_packet import method

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "evidence/engineering/20260905T091635Z-reconnect-packet-diagnosis"
FAILED = ROOT / "evidence/engineering/20260905T091508Z-reconnect-packet-diagnosis"


class PacketDiagnosisTests(unittest.TestCase):
    def copied(self):
        temporary = tempfile.TemporaryDirectory(prefix="safetwin-packet-audit-fixture-")
        self.addCleanup(temporary.cleanup)
        target = Path(temporary.name) / "run"
        shutil.copytree(RUN, target)
        return target

    def update(self, target, name, change):
        path = target / name
        value = json.loads(path.read_text())
        change(value)
        path.write_text(json.dumps(value), encoding="utf-8")
        manifest = json.loads((target / "manifest.json").read_text())
        manifest["captured_file_sha256"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
        (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_source_fixture_is_not_network_proof(self):
        result = audit(RUN)
        self.assertTrue(result["audit_passed"])
        self.assertEqual(result["source_files_verified"], 12)
        self.assertEqual(result["exact_method_fixture_cases"], 60)
        self.assertTrue(result["negative_control_detected"])
        self.assertEqual(result["network_trials_added"], 0)
        self.assertFalse(result["r2_loss_location_uniquely_observed"])
        self.assertFalse(result["r2_network_fix_validated"])

    def test_claim_promotion_rejected_even_after_rehash(self):
        target = self.copied()
        self.update(target, "summary.json", lambda row: row.update(r2_loss_location_uniquely_observed=True))
        with self.assertRaisesRegex(ValueError, "claim promotion"):
            audit(target)

    def test_source_inventory_cannot_omit_caller(self):
        target = self.copied()
        self.update(target, "sources.json", lambda rows: rows.pop(0))
        with self.assertRaisesRegex(ValueError, "command inventory/order"):
            audit(target)

    def test_official_source_hash_drift_rejected(self):
        target = self.copied()
        self.update(target, "sources.json", lambda rows: rows[0].update(official_sha256="0" * 64))
        with self.assertRaisesRegex(ValueError, "upstream source hashes"):
            audit(target)

    def test_stdin_hash_must_link_to_executed_methods(self):
        target = self.copied()
        self.update(target, "commands.json", lambda rows: next(r for r in rows if r["name"] == "exact-method-fixture").update(stdin_sha256="0" * 64))
        with self.assertRaisesRegex(ValueError, "executed source linkage"):
            audit(target)

    def test_added_capability_rejected(self):
        target = self.copied()
        def mutate(rows):
            next(r for r in rows if r["name"] == "compiler")["argv"].insert(2, "--cap-add=NET_ADMIN")
        self.update(target, "commands.json", mutate)
        with self.assertRaisesRegex(ValueError, "fixture container confinement"):
            audit(target)

    def test_service_restart_not_an_allowed_diagnostic_command(self):
        target = self.copied()
        self.update(target, "commands.json", lambda rows: rows[1].update(argv=["docker", "restart", "safetwin5g-gnb"]))
        with self.assertRaisesRegex(ValueError, "no service mutation"):
            audit(target)

    def test_negative_control_must_fail(self):
        target = self.copied()
        self.update(target, "commands.json", lambda rows: next(r for r in rows if r["name"] == "negative-control-fixture").update(returncode=0))
        with self.assertRaisesRegex(ValueError, "command return code"):
            audit(target)

    def test_running_image_must_remain_official(self):
        target = self.copied()
        def mutate(rows):
            row = next(r for r in rows if r["name"] == "gnb-after")
            content = json.loads(row["stdout"])
            content[0]["Image"] = "sha256:" + "0" * 64
            row["stdout"] = json.dumps(content)
        self.update(target, "commands.json", mutate)
        with self.assertRaisesRegex(ValueError, "official running identity"):
            audit(target)

    def test_first_execution_denial_is_retained_not_a_network_failure(self):
        manifest = json.loads((FAILED / "manifest.json").read_text())["captured_file_sha256"]
        for name, value in manifest.items():
            self.assertEqual(hashlib.sha256((FAILED / name).read_bytes()).hexdigest(), value)
        summary = json.loads((FAILED / "summary.json").read_text())
        self.assertFalse(summary["capture_completed"])
        self.assertEqual(summary["new_network_trials"], 0)
        commands = json.loads((FAILED / "commands.json").read_text())
        self.assertEqual(commands[-1]["returncode"], 126)
        self.assertIn("/tmp/packet-fixture: Permission denied", commands[-1]["stderr"])
        # The single documented tmpfs option edit reconstructs the exact failed
        # collector version, whose original SHA-256 remains in its manifest.
        current = (ROOT / "tools/diagnose_reconnect_packet.py").read_bytes()
        old = current.replace(b"/tmp:rw,exec,nosuid,nodev,size=32m", b"/tmp:rw,nosuid,nodev,size=32m")
        hashes = json.loads((FAILED / "collector-sources.json").read_text())
        self.assertEqual(hashlib.sha256(old).hexdigest(), hashes["tools/diagnose_reconnect_packet.py"])

    def test_method_extraction_requires_unique_balanced_definition(self):
        self.assertEqual(method("void f() { if (true) {} }", "void f("), "void f() { if (true) {} }")
        for source in ("absent", "void f() {} void f() {}", "void f() {"):
            with self.subTest(source=source), self.assertRaises(ValueError):
                method(source, "void f(")


if __name__ == "__main__":
    unittest.main()
