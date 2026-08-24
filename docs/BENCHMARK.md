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
