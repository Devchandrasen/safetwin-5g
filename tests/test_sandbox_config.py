import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class SandboxConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.compose = (ROOT / "sandbox" / "compose.yaml").read_text(encoding="utf-8")
        cls.lock = json.loads(
            (ROOT / "sandbox" / "versions.lock.json").read_text(encoding="utf-8")
        )

    def test_compose_uses_locked_image_digests(self):
        for name in ("mongodb", "prometheus"):
            component = self.lock["components"][name]
            self.assertIn(component["image"], self.compose)
            self.assertIn(component["digest"], self.compose)

    def test_compose_network_is_internal_and_has_no_core_ports(self):
        self.assertIn("internal: true", self.compose)
        self.assertNotIn("27017:27017", self.compose)
        self.assertNotIn("38412:38412", self.compose)
        self.assertNotIn("ports:", self.compose)

    def test_radio_simulation_is_explicit_in_image_metadata(self):
        dockerfile = (
            ROOT / "sandbox" / "docker" / "ueransim" / "Dockerfile"
        ).read_text(encoding="utf-8")
        self.assertIn('safetwin5g.radio.evidence="simulated"', dockerfile)

    def test_core_and_ue_receive_only_required_tun_device(self):
        self.assertEqual(self.compose.count("/dev/net/tun:/dev/net/tun"), 2)
        self.assertNotIn("privileged: true", self.compose)

    def test_open5gs_uses_minimal_direct_nrf_topology(self):
        configure = (
            ROOT / "sandbox" / "docker" / "open5gs" / "configure.py"
        ).read_text(encoding="utf-8")
        entrypoint = (
            ROOT / "sandbox" / "docker" / "open5gs" / "entrypoint.sh"
        ).read_text(encoding="utf-8")
        self.assertIn('"amf.yaml",', configure)
        self.assertIn("      nrf:\\n", configure)
        self.assertNotIn("declare -a names=(nrf scp", entrypoint)

    def test_open5gs_avoids_known_debian_12_libcurl_failure(self):
        dockerfile = (
            ROOT / "sandbox" / "docker" / "open5gs" / "Dockerfile"
        ).read_text(encoding="utf-8")
        base = self.lock["components"]["ubuntu_open5gs_base"]
        self.assertIn(f'{base["image"]}@{base["digest"]}', dockerfile)

    def test_live_actuation_remains_disabled(self):
        policy = json.loads((ROOT / "config" / "actions.json").read_text(encoding="utf-8"))
        self.assertFalse(policy["allow_live_actuation"])
        self.assertTrue(policy["require_human_approval"])

    def test_pre_intervention_capture_cannot_claim_sandbox_measured(self):
        capture = (ROOT / "sandbox" / "capture_evidence.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"evidence_label": "simulated"', capture)
        self.assertIn("Not sandbox-measured under PROJECT_LOCK.md", capture)

    def test_intervention_runner_is_sandbox_only_and_restores_clean_state(self):
        runner = (ROOT / "sandbox" / "run_intervention.py").read_text(encoding="utf-8")
        self.assertIn('UE = "safetwin5g-ue"', runner)
        self.assertIn('"live_actuation_blocked": not policy.allow_live', runner)
        self.assertIn('"rollback-reapply-fault"', runner)
        self.assertIn('"final-cleanup"', runner)
        self.assertIn('"evidence_label": "sandbox-measured"', runner)

    def test_network_impairment_action_is_sandbox_only(self):
        policy = json.loads((ROOT / "config" / "actions.json").read_text(encoding="utf-8"))
        action = policy["actions"]["network_impairment_clear"]
        self.assertTrue(action["sandbox_only"])
        self.assertEqual(action["target_types"], ["ue_tunnel"])

    def test_baseline_capture_requires_registration_session_and_ping(self):
        capture = (ROOT / "sandbox" / "capture_evidence.py").read_text(
            encoding="utf-8"
        )
        for required_check in (
            '"ue_cli_registered"',
            '"pdu_session_active"',
            '"twenty_ping_packets_received"',
            '"zero_baseline_packet_loss"',
        ):
            self.assertIn(required_check, capture)


if __name__ == "__main__":
    unittest.main()
