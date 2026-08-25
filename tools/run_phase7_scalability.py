"""Run and hash-manifest the BRACE computation microbenchmark."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.dataset_v1 import sha256  # noqa: E402
from safetwin5g.phase7_scalability import benchmark_brace  # noqa: E402


def main() -> int:
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ-phase7-brace-scalability")
    output = ROOT / "evidence" / "benchmarks" / run_id
    output.mkdir(parents=True, exist_ok=False)
    report = benchmark_brace()
    report.update(
        {
            "run_id": run_id,
            "started_at": started.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "concurrent_phase7_campaign": any(
                (ROOT / "evidence" / "scenarios").glob("*-phase7-campaign-v2a")
            ),
        }
    )
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    sources = {
        str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path)
        for path in (
            ROOT / "src" / "safetwin5g" / "phase7_scalability.py",
            ROOT / "src" / "safetwin5g" / "brace.py",
            ROOT / "tools" / "run_phase7_scalability.py",
        )
    }
    (output / "source-evidence.json").write_text(
        json.dumps({"files_sha256": sources}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    captured = {
        path.name: sha256(path)
        for path in sorted(output.iterdir())
        if path.is_file() and path.name != "manifest.json"
    }
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": run_id,
                "passed": True,
                "input_evidence_label": "fixture",
                "runtime_measurement": "local-host-measured",
                "network_performance_claim": False,
                "hardware_or_operator_claim": False,
                "captured_file_sha256": captured,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(output)
    print(json.dumps(report["decision_batch"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
