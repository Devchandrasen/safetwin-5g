"""Release compressed, lossless protocol fixtures and local subprocess captures.

No Docker command, socket, image application or actual sleep inhibition occurs.
Every archive is extracted into a new temporary directory and independently
audited with the frozen source lock, not an unfrozen-development exception.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sandbox.run_reconnect_r4 import save, sha
from sandbox.reconnect_r4_process import complete
from tests.reconnect_r4_execution_fixture import make_bundle
from tests.test_reconnect_r4_process import ProcessTests
from tools.audit_reconnect_r4_execution import audit

CASES = ("complete", "bad-baseline", "ineligible-source", "incomplete-trace", "failed-switch", "timeout",
         "missing-fresh-pdu", "window-budget", "failed-final-switch", "failed-cleanup", "failed-reset",
         "failed-health", "failed-official-service", "stale-official-trace", "busy-host", "sleep-enable-failed", "sleep-clear-failed")
DEVELOPMENT = ("20260905T154056Z-reconnect-r4-development", "20260905T155412Z-reconnect-r4-development", "20260905T162754Z-reconnect-r4-development")


def archive(source, destination):
    files = {p.relative_to(source).as_posix(): sha(p.read_bytes()) for p in source.rglob("*") if p.is_file()}
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as handle:
        for name in sorted(files):
            entry = zipfile.ZipInfo(name, date_time=(2026, 9, 5, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            handle.writestr(entry, (source / name).read_bytes())
    return files


def extract_verified(archive_path, output, expected):
    with zipfile.ZipFile(archive_path) as handle:
        names = handle.namelist()
        if len(names) != len(set(names)) or set(names) != set(expected):
            raise ValueError("archive inventory")
        for name in names:
            if not (output / name).resolve().is_relative_to(output.resolve()) or sha(handle.read(name)) != expected[name]:
                raise ValueError("archive path or bytes")
        handle.extractall(output)


def main():
    output = ROOT / "evidence/engineering" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r4-execution-fixtures")
    output.mkdir(exist_ok=False)
    reports = {}
    with patch("subprocess.Popen", side_effect=AssertionError("protocol fixtures cannot spawn")), patch("socket.socket", side_effect=AssertionError("protocol fixtures cannot open sockets")):
        for case in CASES:
            with tempfile.TemporaryDirectory(prefix="safetwin-r4-release-") as temporary:
                root = Path(temporary)
                result = make_bundle(root / "original", case)
                inventory = archive(root / "original", output / (case + ".zip"))
                extract_verified(output / (case + ".zip"), root / "extracted", inventory)
                replay = audit(root / "extracted", allow_fixture=True)
                reports[case] = {"runtime": result, "independent": replay, "archive_member_sha256": inventory,
                                 "expectation_matched": replay["protocol_execution_valid"] == result["protocol_execution_valid"] == (case == "complete")}
                print(json.dumps({"fixture": case, "passed": reports[case]["expectation_matched"]}), flush=True)
    # Real local child processes, still fixture evidence, not network measurement.
    captured = {}
    probe = ProcessTests()
    for mode, options in (("streams", {}), ("flood", {"cap": 32768}), ("sleep", {"timeout": 0.5}),
                          ("descendant", {"timeout": 0.5}), ("invalid-utf8", {}), ("exit-failure", {})):
        row = probe.run_child(mode, **options)
        ok = (complete(row) == (mode in ("streams", "exit-failure")) and row["process_reaped"] and row["reader_threads_joined"])
        if mode in ("sleep", "descendant"):
            ok = ok and row["timed_out"]
        if mode == "flood":
            ok = ok and row["truncated"] and row["retained_output_bytes"] == 32768
        captured[mode] = {"raw_command": row, "expectation_matched": ok}
    def denied(_):
        raise OSError("fixture job assignment denied")
    row = probe.run_child("streams", job_factory=denied)
    captured["job-denied"] = {"raw_command": row, "expectation_matched": not row["launcher_go_sent"] and row["process_reaped"] and not row["stdout"]}
    save(output / "local-process-fixtures.json", {"evidence_label": "fixture", "network_execution_authorized": False,
                                                "actual_docker_commands_executed": 0, "cases": captured})
    development = {}
    for name in DEVELOPMENT:
        source = ROOT / "evidence/engineering" / name
        inventory = archive(source, output / (name + ".zip"))
        with tempfile.TemporaryDirectory(prefix="safetwin-r4-negative-") as temporary:
            extract_verified(output / (name + ".zip"), Path(temporary) / "extracted", inventory)
        development[name] = {"archive_member_sha256": inventory, "exact_historical_bytes_verified": True,
                             "reinterpreted_as_passing": False}
    passed = all(r["expectation_matched"] for r in reports.values()) and all(r["expectation_matched"] for r in captured.values())
    save(output / "summary.json", {"fixture_gate_passed": passed, "cases": reports, "development_failures": development,
                                  "evidence_label": "fixture", "network_execution_authorized": False,
                                  "actual_docker_commands_executed": 0, "network_fix_validated": False,
                                  "actual_sleep_inhibition_requested": False, "synthetic_protocol_clocks": True})
    save(output / "manifest.json", {"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}})
    print(json.dumps({"output": str(output), "fixture_gate_passed": passed, "protocol_cases": len(reports), "process_cases": len(captured)}))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
