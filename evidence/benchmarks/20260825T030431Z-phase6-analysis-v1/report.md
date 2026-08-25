# SafeTwin-5G Phase 6 Decision

Evidence: `sandbox-measured` intervention; `simulated` radio  
Hardware measured: `no`; operator validated: `no`

## Outcome

- Model promotion: **NO-GO**
- Live actuation: **NO-GO**
- H1: `not-supported`
- H2: `not-supported`
- H3: `gated-not-run`

## Locked test benchmark

| Predictor | MAE | Median absolute error | RMSE |
|---|---:|---:|---:|
| deterministic_rule | 3.8889 | 0.0000 | 8.2696 |
| action_conditional_ridge | 5.2612 | 2.4174 | 8.9429 |
| temporal_persistence | 17.4603 | 0.0000 | 35.3666 |

## Preregistered gates

| Gate | Estimate | 95% block-bootstrap CI | Holm p | Coverage | Result |
|---|---:|---:|---:|---:|---|
| H1 model minus temporal absolute error | -12.1992 | [-22.7396, -2.5349] | 0.0625 | n/a | not-supported |
| H2 selective minus always-act harm incidence | -0.3571 | [-0.5000, -0.2143] | 0.0625 | 0.2143 | not-supported |

## Uncertainty and OOD

The nominal 90% split-conformal radius is `19.4591` from `21` calibration units (status: `finite`).

Locked test OOD: `0/21`; designated OOD detected: `48/48`.

Selective test coverage is `0.2143` with `0` harmful eligible candidates versus `5` under always-act.

## Promotion reasons

- H1 superiority gate failed.
- H2 harm-reduction/coverage gate failed.
- H3 status is gated-not-run.
- The locked test MAE winner is deterministic_rule, not the learned model.
- Live actuation remains prohibited regardless of sandbox results.

## Claim boundary

These are versioned single-host software-sandbox results with a simulated UERANSIM radio. They do not establish private-5G hardware performance, operator validity, publication acceptance, or permission for live actuation.
