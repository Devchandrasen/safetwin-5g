from pathlib import Path
import unittest

from safetwin5g.baselines import load_records
from safetwin5g.causal import load_graph
from safetwin5g.effects import (
    FamilyMeanEffectEstimator,
    IdentificationError,
    evaluate_heldout,
    require_alternative_action_identified,
)


ROOT = Path(__file__).resolve().parents[1]
RECORDS = load_records(
    ROOT / "data" / "releases" / "safetwin5g-interventions-v0" / "records.jsonl"
)


class EffectTests(unittest.TestCase):
    def test_estimator_fits_train_only_and_evaluates_heldout(self):
        train = [record for record in RECORDS if record["split"] == "train"]
        test = [record for record in RECORDS if record["split"] == "test"]
        estimator = FamilyMeanEffectEstimator.fit(train)
        self.assertEqual(
            set(estimator.fitted_scenario_ids),
            {record["scenario_id"] for record in train},
        )
        result = evaluate_heldout(estimator, test)
        self.assertEqual(result["n"], 3)
        self.assertEqual(
            {row["estimand_status"] for row in result["rows"]},
            {"descriptive-only"},
        )

    def test_alternative_action_effect_is_refused(self):
        graph = load_graph(ROOT / "config" / "causal_graph_v0.json")
        with self.assertRaisesRegex(
            IdentificationError, "exchangeability, positivity, no_carryover"
        ):
            require_alternative_action_identified(graph)


if __name__ == "__main__":
    unittest.main()
