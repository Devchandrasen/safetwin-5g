"""Estimate held-out paired effects while refusing unidentified causal ATEs."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from safetwin5g.baselines import load_records  # noqa: E402
from safetwin5g.causal import load_graph  # noqa: E402
from safetwin5g.effects import (  # noqa: E402
    FamilyMeanEffectEstimator,
    IdentificationError,
    evaluate_heldout,
    require_alternative_action_identified,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    dataset = ROOT / "data" / "releases" / "safetwin5g-interventions-v0"
    graph_path = ROOT / "config" / "causal_graph_v0.json"
    records = load_records(dataset / "records.jsonl")
    train = [record for record in records if record["split"] == "train"]
    test = [record for record in records if record["split"] == "test"]
    ood = [record for record in records if record["split"] == "ood"]
    estimator = FamilyMeanEffectEstimator.fit(train)
    test_result = evaluate_heldout(estimator, test)
    ood_result = evaluate_heldout(estimator, ood)
    graph = load_graph(graph_path)
    alternative_action_error = None
    try:
        require_alternative_action_identified(graph)
    except IdentificationError as exc:
        alternative_action_error = str(exc)
    if alternative_action_error is None:
        raise RuntimeError("identification gate unexpectedly opened")

    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ-heldout-effects-v0")
    output = ROOT / "evidence" / "benchmarks" / run_id
    output.mkdir(parents=True, exist_ok=False)
    prediction_rows = test_result.pop("rows") + ood_result.pop("rows")
    (output / "predictions.jsonl").write_text(
        "".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
            for row in prediction_rows
        ),
        encoding="utf-8",
    )
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": started.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "passed": True,
        "estimator": "train-only family mean paired benefit",
        "fitted_scenario_ids": list(estimator.fitted_scenario_ids),
        "family_means": estimator.means,
        "test": test_result,
        "ood": ood_result,
        "estimand": "action-first paired rollback benefit proxy",
        "estimand_status": "descriptive-only",
        "alternative_action_ate": None,
        "alternative_action_status": "not-identified",
        "identification_error": alternative_action_error,
        "comparison_to_rule": "not superior; deterministic rule remains the baseline winner",
        "hypothesis_status": {"H1": "not-supported", "H2": "not-tested", "H3": "not-tested"},
        "dataset_manifest_sha256": sha256(dataset / "manifest.json"),
        "causal_graph_sha256": sha256(graph_path),
        "evidence_label": "sandbox-measured",
        "radio_evidence_label": "simulated",
        "claim_boundary": (
            "Held-out prediction of a descriptive paired proxy only; no identified "
            "alternative-action causal effect, hardware result, or operator validation."
        ),
    }
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
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
                "captured_file_sha256": captured,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(output)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
