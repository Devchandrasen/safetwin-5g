"""Retain one development failure with exact sources; never call Docker."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tests.reconnect_r4_execution_fixture import make_bundle
from sandbox.run_reconnect_r4 import save, sha


def main():
    case = sys.argv[1] if len(sys.argv) > 1 else "complete"
    output = ROOT / "evidence/engineering" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r4-development")
    output.mkdir(exist_ok=False)
    with patch("subprocess.Popen", side_effect=AssertionError("no subprocess in protocol fixture")), patch("socket.socket", side_effect=AssertionError("no socket")):
        result = make_bundle(output / "fixture", case)
    sources = ["sandbox/run_reconnect_r4.py", "sandbox/reconnect_r4_process.py", "sandbox/reconnect_r4_launcher.py",
               "sandbox/reconnect_r4_host_guard.py", "tools/reconnect_r4_window_audit.py", "tools/audit_reconnect_r4_execution.py", "tests/reconnect_r4_execution_fixture.py", "tests/test_reconnect_r4_execution.py"]
    inventory = {}
    for name in sources:
        raw = (ROOT / name).read_bytes()
        filename = name.replace("/", "--")
        (output / filename).write_bytes(raw)
        inventory[name] = sha(raw)
    from tools.audit_reconnect_r4_execution import audit
    try:
        audited = audit(output / "fixture", allow_fixture=True, allow_unfrozen_fixture=True)
    except (ValueError, KeyError, TypeError) as exc:
        audited = {"observation_audit_passed": False, "error": str(exc)}
    save(output / "development.json", {"case": "development fixture and current independent audit checkpoint", "independent_audit": audited,
                                       "result": result, "source_sha256": inventory, "evidence_label": "fixture",
                                       "actual_docker_commands_executed": 0, "network_fix_validated": False})
    save(output / "manifest.json", {"captured_file_sha256": {p.relative_to(output).as_posix(): sha(p.read_bytes()) for p in output.rglob("*") if p.is_file()}})
    rollback = json.loads((output / "fixture/final-rollback.json").read_bytes())
    print(output)
    print(json.dumps({"case": case, "summary": result, "rollback": None if rollback is None else rollback["errors"]}))


if __name__ == "__main__":
    main()
