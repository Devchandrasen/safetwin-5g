import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"


class DashboardConfigTests(unittest.TestCase):
    def test_scripts_bind_only_to_ipv4_loopback(self):
        package = json.loads((DASHBOARD / "package.json").read_text(encoding="utf-8"))
        self.assertIn("--host 127.0.0.1", package["scripts"]["dev"])
        self.assertIn("--hostname 127.0.0.1", package["scripts"]["start"])

    def test_dependencies_are_exact_and_have_no_latest_token(self):
        package = json.loads((DASHBOARD / "package.json").read_text(encoding="utf-8"))
        for section in ("dependencies", "devDependencies"):
            for dependency, version in package[section].items():
                self.assertNotEqual(version, "latest", dependency)
                self.assertFalse(version.startswith(("^", "~", ">", "<", "*")), dependency)

    def test_dashboard_is_read_only_and_preserves_claim_boundaries(self):
        page = (DASHBOARD / "app" / "page.tsx").read_text(encoding="utf-8")
        for forbidden in ("<form", "<button", "fetch(", "axios", "actuate", "executeAction"):
            self.assertNotIn(forbidden, page)
        for required in (
            "Live actuation locked",
            "NO-GO",
            "Not supported",
            "Not tested",
            "Simulated",
            "Sandbox-measured",
            "Hardware-measured",
            "Operator-validated",
        ):
            self.assertIn(required, page)

    def test_dashboard_has_no_persistent_addons(self):
        hosting = json.loads(
            (DASHBOARD / ".openai" / "hosting.json").read_text(encoding="utf-8")
        )
        self.assertIsNone(hosting["d1"])
        self.assertIsNone(hosting["r2"])

    def test_machine_snapshot_is_fail_closed_and_hash_linked(self):
        snapshot = json.loads(
            (DASHBOARD / "app" / "data" / "status.json").read_text(encoding="utf-8")
        )
        self.assertEqual(snapshot["overall_decision"]["model_promotion"], "no-go")
        self.assertFalse(snapshot["safety_lock"]["allow_live_actuation"])
        audit = snapshot["proposal_audit"]
        self.assertEqual(audit["proposal_count"], 6)
        self.assertEqual(audit["abstain_count"], 6)
        self.assertEqual(audit["applied_action_count"], 0)
        self.assertTrue(all(record["decision"] == "abstain" for record in audit["records"]))
        self.assertTrue(all(record["execution_status"] == "not-applied" for record in audit["records"]))
        self.assertTrue(all(len(value) == 64 for value in snapshot["source_sha256"].values()))

    def test_api_routes_are_get_only(self):
        for name in ("status", "proposals"):
            route = (DASHBOARD / "app" / "api" / name / "route.ts").read_text(
                encoding="utf-8"
            )
            self.assertIn("function GET", route)
            for method in ("POST", "PUT", "PATCH", "DELETE"):
                self.assertNotIn(f"function {method}", route)


if __name__ == "__main__":
    unittest.main()
