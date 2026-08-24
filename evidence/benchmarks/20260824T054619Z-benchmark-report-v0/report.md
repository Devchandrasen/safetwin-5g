# SafeTwin-5G Benchmark Decision v0

Run: `20260824T054619Z-benchmark-report-v0`  
Evidence: `sandbox-measured`; radio: `simulated`

## Decision

| Scope | Decision |
|---|---|
| Model promotion | **NO-GO** |
| Autonomous or live actuation | **NO-GO** |
| Positive H1-H3 claims | **NO-GO** |
| Continued local sandbox research | **GO WITH CONSTRAINTS** |

## Hypotheses

### H1: not-supported

Decision: `no-go-for-superiority-claim`.

- The deterministic rule is the held-out MAE winner.
- The held-out effect estimator is not superior to the rule.
- Exchangeability, positivity, and no-carry-over are not established, so the alternative-action effect is not identified.
- The exact small-sample permutation control does not support learned-model superiority.

### H2: not-supported

Decision: `no-go-for-harm-reduction-claim`.

- The 90% conformal interval is unbounded with three calibration scenarios.
- Coverage is zero, so selective harmful-action risk and AURC are undefined.
- No harmful action was observed, so harm reduction cannot be tested.
- Both test and designated OOD rows are severity-shifted and are not distinguishable by the current design contract.

### H3: not-tested

Decision: `no-go-for-operational-value-claim`.

- Dataset v0 has no continuous SLA or sustained-recovery windows.
- There are no no-fault scenarios for a false-remediation denominator.
- The approved sandbox intervention used a deterministic runbook, not a twin-assisted comparative policy.
- All held-out model proposals abstained and none was applied.

## Required next evidence

- At least 19 independent calibration scenarios for a finite nominal 90% split-conformal rank.
- Randomized or counterbalanced action order with alternative eligible actions and positivity.
- No-fault, harmful-action, and ineffective-action scenarios.
- Continuous SLA windows and sustained-recovery timing for SLA duration and MTTR.
- A predeclared rule-versus-twin-assisted, human-governed sandbox comparison before any hardware or operator claim.

## Claim boundary

Consolidated feasibility decision derived from versioned software-sandbox evidence. Radio remains simulated; no hardware measurement, operator validation, model promotion, or live-network conclusion is claimed.

Exact source paths and SHA-256 values are recorded in `source-evidence.json`.
