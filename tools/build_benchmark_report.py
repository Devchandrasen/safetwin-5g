"""Build a consolidated, evidence-linked H1-H3 go/no-go report."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.reporting import (  # noqa: E402
    build_decision_report,
    load_verified_sources,
    render_markdown,
    sha256,
)


def main() -> int:
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ-benchmark-report-v0")
    output = ROOT / "evidence" / "benchmarks" / run_id
    output.mkdir(parents=True, exist_ok=False)
    sources, source_evidence = load_verified_sources(ROOT)
    report = build_decision_report(sources, run_id, started.isoformat())
    (output / "source-evidence.json").write_text(
        json.dumps(source_evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    report["source_evidence_sha256"] = sha256(output / "source-evidence.json")
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "report.md").write_text(render_markdown(report), encoding="utf-8")
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
                "evidence_label": "sandbox-measured",
                "radio_evidence_label": "simulated",
                "captured_file_sha256": captured,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(output)
    print(json.dumps(report["overall_decision"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
