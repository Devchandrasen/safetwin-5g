from pathlib import Path
import unittest

from safetwin5g.kpis import KPI_DEFINITIONS, STAGE_KPIS, canonicalize
from safetwin5g.telemetry import EvidenceTelemetryAdapter


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "evidence" / "sandbox" / "20260824T045620Z-intervention"


class KPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.observations = canonicalize(EvidenceTelemetryAdapter(BUNDLE).rows())

    def test_registry_defines_units_directions_and_aggregation(self):
        self.assertGreaterEqual(len(KPI_DEFINITIONS), 16)
        for name, definition in KPI_DEFINITIONS.items():
            self.assertEqual(name, definition.name)
            self.assertTrue(definition.unit)
            self.assertTrue(definition.direction)
            self.assertTrue(definition.aggregation)

    def test_complete_stage_grid_is_emitted(self):
        self.assertEqual(len(self.observations), 5 * len(STAGE_KPIS))
        for stage in EvidenceTelemetryAdapter.STAGES:
            self.assertEqual(
                {item.kpi for item in self.observations if item.stage == stage},
                set(STAGE_KPIS),
            )

    def test_total_loss_rtt_is_missing_not_zero(self):
        fault_rtt = next(
            item
            for item in self.observations
            if item.stage == "fault" and item.kpi == "user_plane_rtt_avg_ms"
        )
        self.assertIsNone(fault_rtt.value)
        self.assertEqual(fault_rtt.status, "missing")
        self.assertEqual(fault_rtt.missing_reason, "no successful ping replies")

    def test_packet_success_and_session_state_are_canonicalized(self):
        indexed = {(item.stage, item.kpi): item.value for item in self.observations}
        self.assertEqual(indexed[("baseline", "user_plane_success_ratio")], 1.0)
        self.assertEqual(indexed[("fault", "user_plane_success_ratio")], 0.0)
        for stage in EvidenceTelemetryAdapter.STAGES:
            self.assertEqual(indexed[(stage, "amf_registered_ues_count")], 1.0)
            self.assertEqual(indexed[(stage, "upf_sessions_count")], 1.0)

    def test_evidence_label_is_preserved(self):
        self.assertEqual(
            {item.evidence_label for item in self.observations}, {"sandbox-measured"}
        )


if __name__ == "__main__":
    unittest.main()
