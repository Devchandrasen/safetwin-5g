import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from tools.audit_reconnect_r3_source import audit, remove_blocks

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "evidence/engineering/20260905T102301Z-reconnect-r3-freeze"


class RetainedR3SourceTests(unittest.TestCase):
    def copied(self):
        temporary = tempfile.TemporaryDirectory(prefix="safetwin-r3-audit-fixture-")
        self.addCleanup(temporary.cleanup)
        target = Path(temporary.name) / "run"; shutil.copytree(RUN, target)
        return target

    def change(self, target, name, mutate):
        path = target / name
        row = json.loads(path.read_text()); mutate(row)
        path.write_text(json.dumps(row), encoding="utf-8")
        manifest = json.loads((target / "manifest.json").read_text())
        manifest["captured_file_sha256"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
        (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    def test_actual_patch_replay_and_source_fixtures_are_not_a_build(self):
        result = audit(RUN)
        self.assertTrue(result["audit_passed"] and result["git_patch_replay_passed"])
        self.assertEqual((result["parser_cases"], result["nas_cases_per_mode"]), (65, 61))
        self.assertFalse(result["new_image_built"] or result["network_fix_validated"])
        self.assertEqual(result["network_trials"], 0)

    def test_claim_promotion_rejected(self):
        target = self.copied()
        self.change(target, "summary.json", lambda row: row.update(new_image_built=True))
        with self.assertRaisesRegex(ValueError, "claim promotion"): audit(target)

    def test_compiler_input_hash_cannot_change(self):
        target = self.copied()
        self.change(target, "commands.json", lambda rows: next(r for r in rows if r["name"] == "parser-fixture").update(stdin_sha256="0" * 64))
        with self.assertRaisesRegex(ValueError, "compiler input linkage"): audit(target)

    def test_added_compiler_capability_rejected(self):
        target = self.copied()
        self.change(target, "commands.json", lambda rows: next(r for r in rows if r["name"] == "parser-fixture")["argv"].insert(2, "--privileged"))
        with self.assertRaisesRegex(ValueError, "isolated compiler scope"): audit(target)

    def test_existing_tag_cannot_be_reported_absent(self):
        target = self.copied()
        self.change(target, "commands.json", lambda rows: next(r for r in rows if r["name"] == "new-tag-absence").update(stdout="sha256:existing\n"))
        with self.assertRaisesRegex(ValueError, "prebuild absence"): audit(target)

    def test_missing_trace_does_not_pass_fixture_audit(self):
        target = self.copied()
        def mutate(rows):
            row = next(r for r in rows if r["name"] == "instrumented-nas-fixture")
            row["stdout"] = "\n".join(row["stdout"].splitlines()[1:])
        self.change(target, "commands.json", mutate)
        with self.assertRaisesRegex(ValueError, "identified NAS events"): audit(target)

    def test_line_based_removal_rejects_nested_markers(self):
        with self.assertRaisesRegex(ValueError, "nested trace block"):
            remove_blocks("// SAFETWIN_R3_BEGIN first\n// SAFETWIN_R3_BEGIN second\n")


if __name__ == "__main__": unittest.main()
