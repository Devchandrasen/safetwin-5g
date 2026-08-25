"""Run the preregistered Phase 6 statistical and safety evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.analysis_v1 import analyze, load_records  # noqa: E402
from safetwin5g.dataset_v1 import verify_manifest  # noqa: E402


DATASET = ROOT / "data" / "releases" / "safetwin5g-interventions-v1"
SOURCES = {
    "dataset_manifest": DATASET / "manifest.json",
    "dataset_quality": DATASET / "data-quality.json",
    "experiment_design": ROOT / "config" / "experiments" / "phase6-v1.json",
    "preregistered_protocol": ROOT / "docs" / "PHASE6_PROTOCOL.md",
    "analysis_module": ROOT / "src" / "safetwin5g" / "analysis_v1.py",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def value(item: Any) -> str:
    if item is None:
        return "undefined"
    if isinstance(item, float):
        return f"{item:.4f}"
    return str(item)


def render_markdown(report: dict) -> str:
    h1 = report["hypotheses"]["H1"]
    h2 = report["hypotheses"]["H2"]
    h3 = report["hypotheses"]["H3"]
    test = report["baselines"]["evaluation"]["test"]
    calibration = report["uncertainty"]["calibration"]
    selective = report["selective_safety"]["test"]
    lines = [
        "# SafeTwin-5G Phase 6 Decision",
        "",
        f"Evidence: `{report['evidence_label']}` intervention; `{report['radio_evidence_label']}` radio  ",
        "Hardware measured: `no`; operator validated: `no`",
        "",
        "## Outcome",
        "",
        f"- Model promotion: **{report['promotion']['model_promotion'].upper()}**",
        f"- Live actuation: **{report['promotion']['live_actuation'].upper()}**",
        f"- H1: `{h1['status']}`",
        f"- H2: `{h2['status']}`",
        f"- H3: `{h3['status']}`",
        "",
        "## Locked test benchmark",
        "",
        "| Predictor | MAE | Median absolute error | RMSE |",
        "|---|---:|---:|---:|",
    ]
    for name in report["baselines"]["test_ranking_by_mae"]:
        metrics = test[name]
        lines.append(
            f"| {name} | {metrics['mae']:.4f} | "
            f"{metrics['absolute_error_distribution']['median']:.4f} | {metrics['rmse']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## Preregistered gates",
            "",
            "| Gate | Estimate | 95% block-bootstrap CI | Holm p | Coverage | Result |",
            "|---|---:|---:|---:|---:|---|",
            f"| H1 model minus temporal absolute error | {h1['estimate_and_ci']['estimate']:.4f} | "
            f"[{h1['estimate_and_ci']['ci95'][0]:.4f}, {h1['estimate_and_ci']['ci95'][1]:.4f}] | "
            f"{h1['holm_adjusted_pvalue']:.4f} | n/a | {h1['status']} |",
            f"| H2 selective minus always-act harm incidence | {h2['estimate_and_ci']['estimate']:.4f} | "
            f"[{h2['estimate_and_ci']['ci95'][0]:.4f}, {h2['estimate_and_ci']['ci95'][1]:.4f}] | "
            f"{h2['holm_adjusted_pvalue']:.4f} | {h2['coverage']:.4f} | {h2['status']} |",
            "",
            "## Uncertainty and OOD",
            "",
            f"The nominal 90% split-conformal radius is `{value(calibration['radius'])}` "
            f"from `{calibration['calibration_n']}` calibration units (status: `{calibration['status']}`).",
            "",
            f"Locked test OOD: `{report['ood']['test_ood_count']}/{report['ood']['test_n']}`; "
            f"designated OOD detected: `{report['ood']['ood_split_ood_count']}/{report['ood']['ood_n']}`.",
            "",
            f"Selective test coverage is `{selective['coverage']:.4f}` with "
            f"`{selective['selective_harmful_count_all_candidates']}` harmful eligible candidates "
            f"versus `{selective['always_act_harmful_count']}` under always-act.",
            "",
            "## Promotion reasons",
            "",
            *[f"- {reason}" for reason in report["promotion"]["reasons"]],
            "",
            "## Claim boundary",
            "",
            "These are versioned single-host software-sandbox results with a simulated UERANSIM radio. "
            "They do not establish private-5G hardware performance, operator validity, publication acceptance, "
            "or permission for live actuation.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    verify_manifest(DATASET / "manifest.json")
    started = datetime.now(timezone.utc)
    records = load_records(DATASET / "records.jsonl")
    report, predictions, contrasts = analyze(records)
    run_id = started.strftime("%Y%m%dT%H%M%SZ-phase6-analysis-v1")
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
    (output / "predictions.jsonl").write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in predictions
        ),
        encoding="utf-8",
    )
    (output / "contrasts.jsonl").write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in contrasts
        ),
        encoding="utf-8",
    )
    source_evidence = {
        "schema_version": 1,
        "files": [
            {
                "role": role,
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256(path),
            }
            for role, path in sorted(SOURCES.items())
        ],
    }
    (output / "source-evidence.json").write_text(
        json.dumps(source_evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
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
                "evidence_label": "sandbox-measured",
                "radio_evidence_label": "simulated",
                "hardware_evidence_label": None,
                "operator_validation": False,
                "captured_file_sha256": captured,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(output)
    print(json.dumps(report["promotion"], indent=2, sort_keys=True))
    print(json.dumps(report["hypotheses"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
