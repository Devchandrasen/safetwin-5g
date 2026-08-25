# Phase 7 Protocol Amendment A1 — Test Precision

**Frozen:** 2026-08-25 before any Phase 7 pilot or campaign unit  
**Parent:** `docs/PHASE7_PROTOCOL.md` and
`config/experiments/phase7-brace-v2.json`  
**Active design:** `config/experiments/phase7-brace-v2a.json`

## Trigger

The preregistered v1 exploratory feasibility analysis was executed at
`evidence/benchmarks/20260825T044022Z-phase7-v1-feasibility`. It correctly
found that the old seven-block calibration is unbounded. Its prospective
precision check also found a weakness in the original fresh design before any
fresh data were collected.

The original design had 30 faulty test blocks. At the 50% selective-coverage
floor, only 15 certified mutations were required. Even with zero observed
certificate violations, the exact one-sided 95% binomial upper bound would be

\[
1-0.05^{1/15}=0.1810,
\]

which cannot support an empirical violation-rate bound below 0.10.

## Amendment

The test seeds increase from five to ten. This changes the fresh design as
follows:

| Quantity | Original v2 | Amended v2a |
|---|---:|---:|
| Test blocks | 35 | 70 |
| Faulty test blocks | 30 | 60 |
| No-fault test blocks | 5 | 10 |
| Test units | 175 | 350 |
| Total blocks | 100 | 135 |
| Total units | 500 | 675 |
| Minimum certified mutations at 50% faulty-block coverage | 15 | 30 |

With 30 zero-violation certified mutations, the exact one-sided 95% upper
bound is

\[
1-0.05^{1/30}=0.0950.
\]

The amended gate therefore requires both at least 50% faulty-block mutation
coverage and at least 29 certified mutations. The design provides 30 at the
coverage floor.

## Unchanged protocol

No observed fresh outcome motivated the amendment. The following remain
unchanged: action portfolio, faults and severities, train/calibration/OOD
splits, 90% simultaneous coverage, five-point benefit margin, model-selection
rule, comparators, ablations, endpoints, Holm correction, OOD abstention,
human approval, rollback, clean-recovery requirement, evidence labels, and
test-label sealing.

The additional seeds are `1306` through `1310`. A new experiment identifier
and SHA-256 randomization salt prevent accidental mixing with the superseded
design. The original files and negative feasibility artifact remain immutable
for provenance.
