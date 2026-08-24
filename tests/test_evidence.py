import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from sandbox.verify_evidence import verify_bundle


class EvidenceTests(unittest.TestCase):
    def test_verified_bundle_hashes_pass(self):
        with TemporaryDirectory() as directory:
            bundle = Path(directory)
            payload = b"measured output\n"
            (bundle / "output.txt").write_bytes(payload)
            (bundle / "manifest.json").write_text(
                json.dumps(
                    {
                        "captured_file_sha256": {
                            "output.txt": hashlib.sha256(payload).hexdigest()
                        }
                    }
                ),
                encoding="utf-8",
            )
            self.assertEqual(verify_bundle(bundle), [])

    def test_tampered_bundle_fails(self):
        with TemporaryDirectory() as directory:
            bundle = Path(directory)
            (bundle / "output.txt").write_text("changed", encoding="utf-8")
            (bundle / "manifest.json").write_text(
                json.dumps({"captured_file_sha256": {"output.txt": "0" * 64}}),
                encoding="utf-8",
            )
            self.assertEqual(verify_bundle(bundle), ["hash mismatch: output.txt"])


if __name__ == "__main__":
    unittest.main()
