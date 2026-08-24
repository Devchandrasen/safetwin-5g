from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from safetwin5g.telemetry import EvidenceTelemetryAdapter, parse_ping, parse_prometheus


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "evidence" / "sandbox" / "20260824T045620Z-intervention"


class TelemetryTests(unittest.TestCase):
    def test_prometheus_parser_preserves_labels_and_values(self):
        rows = parse_prometheus('metric_total{dnn="internet",slice="1"} 3\n')
        self.assertEqual(rows, [("metric_total", {"dnn": "internet", "slice": "1"}, 3.0)])

    def test_ping_parser_handles_complete_loss_without_rtt(self):
        metrics = parse_ping(
            "5 packets transmitted, 0 received, 100% packet loss, time 4094ms\n"
        )
        self.assertEqual(metrics["packet_loss_pct"], (100.0, "percent"))
        self.assertNotIn("rtt_avg_ms", metrics)

    def test_intervention_adapter_loads_all_stages_and_sources(self):
        rows = EvidenceTelemetryAdapter(BUNDLE).rows()
        self.assertTrue(rows)
        self.assertEqual({row.stage for row in rows}, set(EvidenceTelemetryAdapter.STAGES))
        self.assertEqual(
            {row.source for row in rows},
            {"ueransim-user-plane", "open5gs-amf", "open5gs-smf", "open5gs-upf"},
        )
        loss = {
            row.stage: row.value
            for row in rows
            if row.source == "ueransim-user-plane" and row.metric == "packet_loss_pct"
        }
        self.assertEqual(
            loss,
            {"baseline": 0.0, "fault": 100.0, "post-action": 0.0, "rollback": 100.0, "final": 0.0},
        )

    def test_adapter_writes_replayable_jsonl(self):
        rows = EvidenceTelemetryAdapter(BUNDLE).rows()
        with TemporaryDirectory() as directory:
            target = Path(directory) / "telemetry.jsonl"
            EvidenceTelemetryAdapter.write_jsonl(rows, target)
            self.assertEqual(len(target.read_text(encoding="utf-8").splitlines()), len(rows))


if __name__ == "__main__":
    unittest.main()
