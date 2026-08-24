# Benchmark Ledger

## Baselines v0

Evidence: `evidence/benchmarks/20260824T052852Z-baselines-v0`

The rule, ridge-tabular, and temporal-persistence baselines use the frozen
12-record dataset. Preprocessing is fit on the three training rows; ridge alpha
is selected on the three calibration rows; test and OOD rows are untouched
until evaluation.

| Baseline | Test MAE | Test RMSE | OOD MAE |
|---|---:|---:|---:|
| deterministic rule | 3.333 | 5.774 | 0.000 |
| tabular ridge | 17.876 | 30.143 | 14.546 |
| temporal persistence | 29.333 | 49.092 | 26.000 |

The deterministic rule wins this feasibility benchmark. No learned model is
promoted. Each split has only three scenarios, no harmful action was observed,
alternative-action positivity is absent, and the action-first rollback proxy
may contain order effects. These results do not establish H1, H2, or H3.

## Held-out effect proxy v0

Evidence: `evidence/benchmarks/20260824T053222Z-heldout-effects-v0`

A family-mean paired-benefit estimator was fit only on the three training
scenarios. It obtained test MAE 17.000 and OOD MAE 13.667, so it is not superior
to the deterministic rule. The alternative-action ATE is null and marked
`not-identified`; the report records exchangeability, positivity, and
no-carry-over as blockers. H1 remains `not-supported` rather than failed or
confirmed because dataset v0 cannot identify the target causal contrast.

## Diagnostics v0

Evidence: `evidence/benchmarks/20260824T053419Z-diagnostics-v0`

All six leakage checks passed: scenario groups do not cross splits,
preprocessing and hyperparameter scopes are correct, future-outcome fields are
excluded, and mutating post-action/rollback outcomes changes predictions by
exactly zero. The final-state packet-loss placebo is also exactly zero.

The scientific readiness gate nevertheless fails. Three calibration rows are
insufficient for a finite 90% split-conformal radius: the required order rank
is four, so the interval is unbounded. The exact three-row label-permutation
control did not show ridge MAE strictly better than all permutations. Promotion
remains blocked.
