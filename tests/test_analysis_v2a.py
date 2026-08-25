from copy import deepcopy
import unittest

from safetwin5g.analysis_v2a import (
    ActionBenefitRidge,
    analyze,
    binomial_cdf,
    clopper_pearson_upper,
    complete_blocks,
    fit_calibrations,
    holm_adjust,
    matched_point_rows,
    paired_harm_pvalue,
    raw_benefit_features,
    select_alpha_lobo,
)
from safetwin5g.dataset_v2a import ACTION_IDS


def synthetic_records(block_n: int, split: str = "train"):
    families = (
        "packet_impairment",
        "network_function_interruption",
        "cpu_saturation",
        "no_fault",
    )
    return synthetic_family_records(
        [families[index % len(families)] for index in range(block_n)], split
    )


def synthetic_family_records(families, split: str):
    records = []
    correct = {
        "packet_impairment": "clear_packet_impairment",
        "network_function_interruption": "resume_upf",
        "cpu_saturation": "stop_cpu_stress",
        "no_fault": None,
    }
    for index, family in enumerate(families):
        block_id = f"{split}|{family}|{index}"
        for action in ACTION_IDS:
            benefit = 20.0 if action == correct[family] else 0.0
            if action == "apply_packet_impairment_25":
                benefit = -25.0
            mutates = action != "observe_only"
            metrics = {
                "packet_loss_pct": 20.0 if family == "packet_impairment" else 0.0,
                "core_container_cpu_pct": 80.0 if family == "cpu_saturation" else 5.0,
                "stress_workers_count": 2.0 if family == "cpu_saturation" else 0.0,
                "upf_process_running": 0.0 if family == "network_function_interruption" else 1.0,
                "configured_packet_loss_pct": 20.0 if family == "packet_impairment" else 0.0,
            }
            record = {
                "unit_id": f"{block_id}|{action}",
                "assignment_block_id": block_id,
                "split": split,
                "fault_family": family,
                "severity_value": float(index % 3),
                "seed": index,
                "workload": "steady",
                "action_id": action,
                "action_applied": mutates,
                "observed_action_benefit": benefit,
                "violates_benefit_margin": bool(mutates and benefit <= 5.0),
                "harmful_action": bool(mutates and (benefit < -5.0 or family == "no_fault")),
                "false_remediation": bool(mutates and family == "no_fault"),
                "reversible": mutates,
                "rollback_plan_recorded": mutates,
                "approval_id": "synthetic-fixture-approval",
                "safety_decision": "require-human-approval" if mutates else "observe-only",
                "cleanup_verified": True,
                "windows": {"fault": {"samples": [{"metrics": metrics} for _ in range(3)]}},
            }
            records.append(record)
    return records


def synthetic_phase7_records():
    development = [
        "packet_impairment",
        "packet_impairment",
        "network_function_interruption",
        "network_function_interruption",
        "cpu_saturation",
        "cpu_saturation",
        "no_fault",
    ]
    return (
        synthetic_family_records(development * 4, "train")
        + synthetic_family_records(development * 3, "calibration")
        + synthetic_family_records(
            ["packet_impairment"] * 20
            + ["network_function_interruption"] * 20
            + ["cpu_saturation"] * 20
            + ["no_fault"] * 10,
            "test",
        )
        + synthetic_family_records(
            ["packet_impairment"] * 4
            + ["network_function_interruption"] * 4
            + ["cpu_saturation"] * 4
            + ["no_fault"] * 4,
            "ood",
        )
    )


class AnalysisV2aTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = synthetic_records(8)
        cls.blocks = complete_blocks(cls.records)

    def test_complete_blocks_reject_missing_action(self):
        incomplete = self.records[:-1]
        with self.assertRaisesRegex(ValueError, "incomplete"):
            complete_blocks(incomplete)

    def test_features_are_pre_action_and_invariant_to_outcome_changes(self):
        block = self.blocks[sorted(self.blocks)[0]]
        original = raw_benefit_features(block, "clear_packet_impairment")
        mutated = deepcopy(block)
        for row in mutated.values():
            row["observed_action_benefit"] = 1_000_000.0
            row["harmful_action"] = not row["harmful_action"]
        self.assertEqual(original, raw_benefit_features(mutated, "clear_packet_impairment"))

    def test_lobo_selects_using_train_blocks_and_final_fit_records_ids(self):
        alpha, trials = select_alpha_lobo(self.blocks, alphas=(0.1, 1.0))
        self.assertIn(alpha, {0.1, 1.0})
        self.assertEqual(len(trials), 2)
        model = ActionBenefitRidge.fit(self.blocks, alpha)
        self.assertEqual(set(model.fitted_block_ids), set(self.blocks))

    def test_joint_calibration_uses_one_score_per_complete_block(self):
        model = ActionBenefitRidge.fit(self.blocks, 1.0)
        calibrations = fit_calibrations(self.blocks, model)
        brace = calibrations["brace"]
        self.assertEqual(brace.calibration_block_n, 8)
        self.assertEqual(len(brace.block_scores), 8)
        self.assertEqual(brace.rank, 9)
        self.assertEqual(brace.status, "unbounded")
        self.assertEqual(calibrations["scalar"]["calibration_n"], 32)
        self.assertEqual(
            {item["calibration_n"] for item in calibrations["action_conditional"].values()},
            {8},
        )

    def test_exact_bounds_multiplicity_and_paired_test(self):
        self.assertAlmostEqual(binomial_cdf(0, 30, 0.10), 0.9**30)
        self.assertLess(clopper_pearson_upper(0, 30), 0.10)
        self.assertEqual(holm_adjust({"G2": 0.01, "G3": 0.04}), {"G2": 0.02, "G3": 0.04})
        paired = paired_harm_pvalue([0, 0, 0], [1, 1, 0])
        self.assertEqual(paired["discordant_blocks"], 2)
        self.assertEqual(paired["exact_one_sided_pvalue"], 0.25)

    def test_matched_point_policy_can_expose_no_fault_false_remediation(self):
        brace = [
            {
                "assignment_block_id": "fault",
                "fault_family": "packet_impairment",
                "mutated": True,
            },
            {
                "assignment_block_id": "clean",
                "fault_family": "no_fault",
                "mutated": False,
            },
        ]
        point = [
            {
                "assignment_block_id": "fault",
                "fault_family": "packet_impairment",
                "predicted_benefit": 10.0,
                "mutated": True,
            },
            {
                "assignment_block_id": "clean",
                "fault_family": "no_fault",
                "predicted_benefit": 20.0,
                "mutated": True,
                "false_remediation": True,
                "harmful_action": True,
            },
        ]
        matched = matched_point_rows(brace, point)
        selected = next(row for row in matched if row["mutated"])
        self.assertEqual(selected["assignment_block_id"], "clean")
        self.assertTrue(selected["false_remediation"])

    def test_full_frozen_analysis_keeps_a_baseline_win_as_no_go(self):
        report, rows = analyze(synthetic_phase7_records())
        self.assertEqual(report["split_block_counts"], {"train": 28, "calibration": 21, "test": 70, "ood": 16})
        self.assertEqual(report["gates"]["G2"]["faulty_test_block_n"], 60)
        self.assertEqual(report["gates"]["G3"]["matched_test_block_n"], 70)
        self.assertFalse(report["gates"]["G3"]["passed"])
        self.assertEqual(report["decision"]["TNSM_claim_gate"], "no-go")
        self.assertEqual(report["decision"]["live_actuation"], "no-go")
        self.assertEqual(len(rows), 586)


if __name__ == "__main__":
    unittest.main()
