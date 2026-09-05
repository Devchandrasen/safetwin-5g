"""Read-only live preflight capture. Does not enable or call image switching."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sandbox.run_reconnect_r3 import R3Backend, CONFIG_PATH, IMAGE_PATH, approval_record, now, sha, save


def main():
    output = ROOT / "evidence/engineering" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r3-preflight")
    output.mkdir(parents=True, exist_ok=False)
    config, images = json.loads(CONFIG_PATH.read_bytes()), json.loads(IMAGE_PATH.read_bytes())
    backend = R3Backend(output, config, images, approval_record(config, images, now()))
    errors = []
    try: backend.preflight()
    except Exception as exc: errors.append(f"{type(exc).__name__}: {exc}")
    save(output / "summary.json", {"preflight_passed": not errors, "errors": errors, "mutation_enabled": backend.authorized,
                                  "candidate_image_applied": backend.candidate_touched, "network_trials": 0,
                                  "evidence_label": "fixture", "network_fix_validated": False})
    save(output / "source-hashes.json", {p: sha((ROOT / p).read_bytes()) for p in
        ("sandbox/run_reconnect_r3.py", "sandbox/reconnect_r3_measurement.py", "sandbox/compose.reconnect-r3.yaml", "tools/preflight_reconnect_r3.py")})
    save(output / "manifest.json", {"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}})
    print(output); print(json.dumps({"preflight_passed": not errors, "errors": errors, "mutation_enabled": backend.authorized}))
    return 0 if not errors else 2


if __name__ == "__main__": raise SystemExit(main())
