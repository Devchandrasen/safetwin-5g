import json
from pathlib import Path
import unittest
from unittest.mock import patch

from sandbox.run_reconnect_r2 import (CORE, GNB, UE, LOCK, R2Backend, candidate_recovery,
                                      stop_reason, trials, validate_switch_approval)
from tests.test_recovery_pilot import good_samples
from tools.audit_reconnect_r2 import audit_endpoints


class ReconnectR2Tests(unittest.TestCase):
    def result(self, **changes):
        row = {"protocol_execution_valid": True, "trial": {"drop_ue_egress": True},
               "automatic_service_recovered": True, "reconnect_failure_reproduced": False,
               "role": "derived", "candidate_recovery_verified": True}
        return row | changes

    def logs(self):
        return {UE: "Radio link failure detected; Sending Service Request; Service Accept received",
                GNB: "Initial Context Setup Request received"}

    def test_eight_fixed_assignments(self):
        rows = trials()
        self.assertEqual(len(rows), 8)
        self.assertEqual([r["drop_ue_egress"] for r in rows], [False, True, True, False] * 2)
        self.assertEqual(rows[0]["trial_id"], "official:control-before")
        self.assertEqual(rows[-1]["trial_id"], "derived:control-after")

    def test_packet_recovery_and_context_logs_are_both_required(self):
        self.assertTrue(candidate_recovery(self.result(), self.logs()))
        self.assertFalse(candidate_recovery(self.result(automatic_service_recovered=False), self.logs()))
        self.assertFalse(candidate_recovery(self.result(), {UE: self.logs()[UE], GNB: ""}))
        self.assertFalse(candidate_recovery(self.result(), {UE: "Service Accept received", GNB: self.logs()[GNB]}))

    def test_amf_error_cannot_be_hidden_by_later_success(self):
        logs = self.logs()
        logs[GNB] += " failed. Could not find a suitable AMF."
        self.assertFalse(candidate_recovery(self.result(), logs))

    def test_partial_candidate_or_invalid_trial_stops(self):
        self.assertEqual(stop_reason(self.result(candidate_recovery_verified=False)), "candidate_recovery_not_verified")
        self.assertEqual(stop_reason(self.result(protocol_execution_valid=False)), "invalid_trial")
        self.assertIsNone(stop_reason(self.result()))

    def test_official_control_cannot_substitute_for_failure_reproduction(self):
        self.assertEqual(stop_reason(self.result(role="official")), "official_failure_not_reproduced")
        self.assertIsNone(stop_reason(self.result(role="official", reconnect_failure_reproduced=True)))

    def test_image_switch_needs_exact_preapproved_ids(self):
        images = json.loads(LOCK.read_text())
        approval = {"status": "approved", "environment": "sandbox", "image_container": GNB,
                    "image_ids": [images["official_image_id"], images["derived_image_id"]], "rollback_plan": "fixture"}
        validate_switch_approval(approval, "derived", images)
        for invalid in ({}, approval | {"image_container": UE}, approval | {"image_ids": []}):
            with self.assertRaises(PermissionError):
                validate_switch_approval(invalid, "derived", images)

    def test_official_rollback_is_attempted_even_if_qdisc_cleanup_fails(self):
        class Backend:
            candidate_touched = True
            def __init__(self): self.events = []
            def clear_owned_fault(self): raise RuntimeError("fixture cleanup failure")
            def switch(self, role): self.events.append(role)
            def restart(self, containers): self.events.append(containers)
            def window(self, label): return good_samples()
            def logs(self, label, since): return {UE: "Initial Registration is successful; PDU Session establishment is successful"}
            def scope(self, role, label): self.events.append(label)
            def eth0(self, label): return [{"kind": "noqueue", "root": True}]
        backend = Backend()
        result = R2Backend.final_rollback(backend)
        self.assertEqual(backend.events[:2], ["official", [CORE, GNB, UE]])
        self.assertTrue(result["service_restored"])
        self.assertTrue(result["errors"])

    def test_failed_candidate_switch_is_still_marked_for_rollback(self):
        images = json.loads(LOCK.read_text())
        class Backend:
            candidate_touched = False
            approval = {"status": "approved", "environment": "sandbox", "image_container": GNB,
                        "image_ids": [images["official_image_id"], images["derived_image_id"]], "rollback_plan": "fixture"}
            def cmd(self, name, argv):
                if name.endswith("-image"): return json.dumps([{"Id": images["derived_image_id"]}])
                raise RuntimeError("fixture replacement failure")
        backend = Backend()
        backend.images = images
        with self.assertRaisesRegex(RuntimeError, "replacement failure"):
            R2Backend.switch(backend, "derived")
        self.assertTrue(backend.candidate_touched)

    def test_independent_endpoint_auditor_rejects_partial_delivery(self):
        logs = self.logs()
        self.assertEqual(audit_endpoints("derived", True, False, logs[UE], logs[GNB], False), (False, False, "candidate_recovery_not_verified"))
        self.assertEqual(audit_endpoints("derived", True, True, logs[UE], logs[GNB], False), (False, True, None))

    def test_independent_endpoint_auditor_requires_chronological_acceptance(self):
        ue = "Service Accept received; Radio link failure detected; Sending Service Request"
        self.assertFalse(audit_endpoints("derived", True, True, ue, self.logs()[GNB], False)[1])

    def test_independent_auditor_does_not_promote_official_failure(self):
        ue = "Radio link failure detected; Sending Service Request"
        gnb = "failed. Could not find a suitable AMF.; Uplink data failure, PDU session not found."
        self.assertEqual(audit_endpoints("official", True, False, ue, gnb, True), (True, False, None))
        self.assertEqual(audit_endpoints("official", True, True, ue, gnb, False)[2], "official_failure_not_reproduced")

    def test_scope_rejects_extra_gnb_capabilities_before_mutation(self):
        root = Path(__file__).resolve().parents[1]
        recorded = [json.loads(line) for line in (root / "evidence/engineering/20260905T062044Z-reconnect-r1/commands.jsonl").read_text().splitlines()]
        network = next(r["stdout"] for r in recorded if r["name"] == "isolated-network")
        containers = json.loads(next(r["stdout"] for r in recorded if r["name"] == "container-identities"))
        next(c for c in containers if c["Name"] == "/" + GNB)["HostConfig"]["CapAdd"] = ["SYS_ADMIN"]
        class Backend:
            reference = None
            images = json.loads(LOCK.read_text())
            def cmd(self, name, argv):
                if name.endswith("-network"): return network
                return json.dumps(containers)
        with self.assertRaisesRegex(PermissionError, "attachment scope"):
            R2Backend.scope(Backend(), "official", "fixture")


if __name__ == "__main__":
    unittest.main()
