"""Run and preserve the exploratory Phase 7 feasibility check on locked v1."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.analysis_v1 import load_records  # noqa: E402
from safetwin5g.dataset_v1 import verify_manifest  # noqa: E402
from safetwin5g.phase7_design import load_phase7_design  # noqa: E402
from safetwin5g.phase7_feasibility import analyze_v1_feasibility  # noqa: E402


DATASET = ROOT / "data" / "releases" / "safetwin5g-interventions-v1"
DESIGN = ROOT / "config" / "experiments" / "phase7-brace-v2.json"
SOURCES = {
    "dataset_manifest": DATASET / "manifest.json",
    "phase7_design": DESIGN,
    "phase7_protocol": ROOT / "docs" / "PHASE7_PROTOCOL.md",
    "brace_method": ROOT / "src" / "safetwin5g" / "brace.py",
    "feasibility_module": ROOT / "src" / "safetwin5g" / "phase7_feasibility.py",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_markdown(report: dict) -> str:
    limits = report["legacy_limitations"]
    calibration = report["legacy_block_calibration"]
    design = report["prospective_v2_design_check"]
    return "\n".join(
        [
            "# Phase 7 BRACE v1 Exploratory Feasibility",
            "",
            "**Result:** negative design result; no confirmatory or promotion claim",
            "",
            "## Locked v1 result",
            "",
            f"- Strict five-action complete blocks: `{limits['strict_phase7_named_action_complete_blocks']}/{limits['observed_v1_block_n']}`.",
            f"- Legacy calibration blocks: `{calibration['calibration_block_n']}`; 90% rank: `{calibration['rank']}`; status: `{calibration['status']}`.",
            f"- Legacy ID test certificates: `{report['legacy_test']['certified_block_n']}/{report['legacy_test']['independent_block_n']}`.",
            f"- Legacy OOD certificates: `{report['legacy_ood']['certified_block_n']}/{report['legacy_ood']['independent_block_n']}`.",
            "",
            "The strict named-action effect vector is not identified in v1, and the",
            "legacy two-arm exploratory calibration is unbounded. BRACE therefore",
            "abstains on every v1 test and OOD block. Phase 6 remains unchanged.",
            "",
            "## Prospective v2 precision check",
            "",
            f"- Frozen calibration blocks: `{design['calibration_blocks']}` (finite rank possible).",
            f"- Frozen test blocks: `{design['test_blocks']}`, including `{design['faulty_test_blocks']}` faulty blocks.",
            f"- Minimum certified mutations at 50% faulty-block coverage: `{design['minimum_certified_mutations_at_frozen_coverage']}`.",
            f"- One-sided 95% zero-violation upper bound at that minimum: `{design['one_sided_95pct_zero_violation_upper_at_minimum_coverage']:.4f}`.",
            f"- Minimum zero-violation sample for an upper bound below 0.10: `{design['minimum_zero_violation_n_for_upper_below_0p10']}`.",
            "",
            design["recommended_amendment"],
            "",
            "## Claim boundary",
            "",
            "Interventions are `sandbox-measured`; radio is `simulated`. Hardware,",
            "operator validation, live actuation, and a positive TNSM claim remain absent.",
            "",
        ]
    )


def main() -> int:
    verify_manifest(DATASET / "manifest.json")
    started = datetime.now(timezone.utc)
    records = load_records(DATASET / "records.jsonl")
    design = load_phase7_design(DESIGN)
    report = analyze_v1_feasibility(records, design)
    run_id = started.strftime("%Y%m%dT%H%M%SZ-phase7-v1-feasibility")
    output = ROOT / "evidence" / "benchmarks" / run_id
    output.mkdir(parents=True, exist_ok=False)
    report.update(
        {
            "run_id": run_id,
            "started_at": started.isoformat(),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "execution_passed": True,
            "dataset_manifest_sha256": sha256(DATASET / "manifest.json"),
        }
    )
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "report.md").write_text(render_markdown(report), encoding="utf-8")
    (output / "source-evidence.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "files": [
                    {
                        "role": role,
                        "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                        "sha256": sha256(path),
                    }
                    for role, path in sorted(SOURCES.items())
                ],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
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
                "artifact_type": "exploratory-design-feasibility",
                "evidence_label": "sandbox-measured",
                "radio_evidence_label": "simulated",
                "confirmatory_claim_allowed": False,
                "captured_file_sha256": captured,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(output)
    print(json.dumps(report["decision"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
