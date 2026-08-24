# Causal Graph and Identification Gate v0

The machine-readable DAG is `config/causal_graph_v0.json`. Its treatment is the
applied remediation, and its immediate outcome is the family-specific target
KPI. Fault family and severity cause the observed fault state; host load may
affect both the fault state and outcomes. Action kind is deterministic within
fault family.

Dataset v0 measures an action outcome first and a rollback-proxy outcome later.
Time order can therefore create carry-over, and it is not randomized. The
paired difference is descriptive; it is not treated as an unbiased
counterfactual effect.

## Identification status

| Assumption | Status | Consequence |
|---|---|---|
| consistency | provisional | exact commands help, but versions beyond this sandbox are untested |
| conditional exchangeability | not met | action order and incompletely measured host load can confound outcomes |
| positivity | not met | one action kind exists per fault family |
| no carry-over | not met | rollback follows action in the same session |
| temporal order recorded | met | UTC-offset timestamps exist for every stage and command |
| no interference | provisional | one UE is isolated, but NFs share a core container |

The alternative-action ATE is therefore **not identified**. The only permitted
current result is a descriptive action-versus-later-rollback contrast. Closing
this gate requires randomized or counterbalanced action order, multiple actions
per comparable fault state, and stronger workload/host-load measurement.
