import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
LOCK_PATH = ROOT / "sandbox" / "versions.lock.json"


class VersionLockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
        cls.components = cls.lock["components"]

    def test_required_components_are_locked(self):
        self.assertTrue(
            {"open5gs", "ueransim", "mongodb", "prometheus"}.issubset(
                self.components
            )
        )

    def test_source_builds_use_full_commit_ids(self):
        for name in ("open5gs", "ueransim"):
            self.assertRegex(self.components[name]["commit"], r"^[0-9a-f]{40}$")
            self.assertNotEqual(self.components[name]["tag"].lower(), "latest")

    def test_upstream_images_use_sha256_digests(self):
        for name in (
            "mongodb",
            "prometheus",
            "ubuntu_open5gs_base",
            "debian_ueransim_base",
        ):
            component = self.components[name]
            self.assertRegex(component["digest"], r"^sha256:[0-9a-f]{64}$")
            self.assertNotIn(":latest", component["image"])

    def test_lock_contains_no_mutable_latest_token(self):
        serialized = json.dumps(self.lock).lower()
        self.assertIsNone(re.search(r'[:\"]latest(?:[\"@]|$)', serialized))


if __name__ == "__main__":
    unittest.main()
