import json
from pathlib import Path
import tempfile
import unittest

from safetwin5g.contracts import InterventionRecord
from safetwin5g.store import InterventionStore
from test_contracts import valid_payload


class StoreTests(unittest.TestCase):
    def test_append_and_load_round_trip(self):
        with tempfile.TemporaryDirectory() as directory:
            store = InterventionStore(Path(directory) / "interventions.jsonl")
            store.append(InterventionRecord.from_dict(valid_payload()))
            records = store.load()
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].record_id, "test-001")

    def test_invalid_line_reports_line_number(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "interventions.jsonl"
            path.write_text(json.dumps(valid_payload()) + "\nnot-json\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 2"):
                InterventionStore(path).load()


if __name__ == "__main__":
    unittest.main()
