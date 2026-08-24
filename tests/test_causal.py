from copy import deepcopy
from pathlib import Path
import unittest

from safetwin5g.causal import identification_report, load_graph, validate_graph


ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "config" / "causal_graph_v0.json"


class CausalGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.graph = load_graph(GRAPH)

    def test_graph_is_valid_dag(self):
        validate_graph(self.graph)
        self.assertGreaterEqual(len(self.graph["nodes"]), 10)

    def test_alternative_action_effect_fails_closed(self):
        report = identification_report(self.graph)
        self.assertFalse(report["alternative_action_effect_identified"])
        self.assertEqual(
            report["blocking_assumptions"],
            ["conditional_exchangeability", "positivity", "no_carryover"],
        )

    def test_cycle_is_rejected(self):
        graph = deepcopy(self.graph)
        graph["edges"].append(["post_action_outcome", "fault_family"])
        with self.assertRaisesRegex(ValueError, "acyclic"):
            validate_graph(graph)

    def test_unknown_edge_node_is_rejected(self):
        graph = deepcopy(self.graph)
        graph["edges"].append(["missing", "fault_state"])
        with self.assertRaisesRegex(ValueError, "unknown node"):
            validate_graph(graph)


if __name__ == "__main__":
    unittest.main()
