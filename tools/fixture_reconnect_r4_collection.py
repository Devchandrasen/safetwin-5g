"""Save network-disabled R4 fixtures, including rejected cases, without overwrite."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sandbox.reconnect_r4_collection import FixtureCollector, recovery_candidate
from tools.audit_reconnect_r4_collection import audit, audit_recovery_candidate
from tests.reconnect_r4_fixture import FakeTransport, CASES, short_recovery, change_identity, IMAGES


def save(path, data):
    path.write_bytes((json.dumps(data, indent=2) + "\n").encode())


def main():
    output = ROOT / "evidence/engineering" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r4-collection-fixtures")
    output.mkdir(exist_ok=False)
    reports = {}
    valid_cases = {"complete-skewed", "complete-idle-loss", "official-service-changed-source", "official-service-4-of-5"}
    with patch("subprocess.Popen", side_effect=AssertionError("fixture cannot execute a process")), \
         patch("socket.socket", side_effect=AssertionError("fixture cannot open network")):
        for name, arguments in CASES.items():
            fake = FakeTransport(**arguments)
            bundle = FixtureCollector(fake).collect(arguments.get("mode", "trace"))
            save(output / (name + ".json"), bundle)
            try:
                report = audit(bundle, allow_fixture=True)
            except (ValueError, KeyError, TypeError) as exc:
                report = {"collection_audit_passed": False, "reason": str(exc), "network_fix_validated": False}
            report["expected_collection_valid"] = name in valid_cases
            report["expectation_matched"] = report["collection_audit_passed"] == (name in valid_cases)
            report["synthetic_commands_retained"] = len(bundle["commands"])
            reports[name] = report
        for name in ("15-of-15", "14-of-15", "wrong-final-image"):
            fake = FakeTransport(mode="official-service", source="10.45.0.3")
            collector = FixtureCollector(fake)
            windows = [collector.collect("official-service") for _ in range(2)]
            if name == "14-of-15":
                fake.mutate = short_recovery
            elif name == "wrong-final-image":
                fake.mutate = lambda rows: change_identity(rows, 13, Image=IMAGES["derived_image_id"])
            windows.append(collector.collect("official-service"))
            runtime, independent = recovery_candidate(windows), audit_recovery_candidate(windows)
            save(output / ("recovery-" + name + ".json"), {"evidence_label": "fixture", "windows": windows, "runtime": runtime, "independent": independent})
            reports["recovery-" + name] = {"expectation_matched": runtime == independent and runtime["packet_delivery_candidate"] == (name == "15-of-15")
                                          and runtime["rollback_verified"] is False, "packet_delivery_candidate": runtime["packet_delivery_candidate"],
                                          "rollback_verified": False, "synthetic_commands_retained": sum(len(w["commands"]) for w in windows)}
    summary = {"fixture_gate_passed": all(r["expectation_matched"] for r in reports.values()), "cases": reports,
               "evidence_label": "fixture", "actual_docker_commands_executed": 0, "network_execution_authorized": False,
               "network_fix_validated": False, "rollback_verified": False,
               "created_at": datetime.now(timezone.utc).isoformat(), "synthetic_clock_not_execution_timestamp": True}
    save(output / "summary.json", summary)
    save(output / "manifest.json", {"captured_file_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir() if p.is_file()}})
    print(json.dumps({"output": str(output), "fixture_gate_passed": summary["fixture_gate_passed"], "cases": len(reports)}))
    return 0 if summary["fixture_gate_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
