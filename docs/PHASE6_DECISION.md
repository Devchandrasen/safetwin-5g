# Phase 6 Locked Decision

**Decision date:** 2026-08-25  
**Identity:** Trustworthy Autonomous Networks  
**Analysis:** `evidence/benchmarks/20260825T030431Z-phase6-analysis-v1`  
**Locked dataset:** `data/releases/safetwin5g-interventions-v1`

## Decision

Phase 6 is a scientifically complete negative result. Model promotion, live
actuation, and positive H1–H3 claims are **NO-GO**. The learned
action-conditional model did not beat the deterministic rule on the locked
test set, H1 and H2 did not pass their preregistered Holm-adjusted gates, and H3
was consequently not run.

This outcome does not make the study incomplete. The preregistered campaign,
dataset freeze, diagnostics, confirmatory tests, negative controls, uncertainty
evaluation, OOD evaluation, and safety decision all completed. The correct
research conclusion is to retain the deterministic baseline and abstaining
safety policy.

## Preregistered hypotheses

| Gate | Locked result | Decision |
|---|---|---|
| H1: learned model improves absolute error over temporal persistence | Model-minus-temporal estimate −12.199; 95% block-bootstrap CI [−22.740, −2.535]; exact one-sided p=0.03125; Holm-adjusted p=0.0625 | **Not supported** |
| H2: selective policy lowers harmful-action incidence with coverage ≥0.50 | Selective-minus-always-act incidence −0.357; 95% block-bootstrap CI [−0.500, −0.214]; exact one-sided p=0.03125; Holm-adjusted p=0.0625; coverage 3/14=0.214 | **Not supported** |
| H3: twin-assisted policy improves operational value | Protocol permits evaluation only if H1 and H2 pass | **Gated—not run** |

The H1 contrast is negative because the learned model beat temporal
persistence. That is insufficient for promotion: the adjusted significance
gate failed, and the deterministic rule remained the actual held-out winner.
The H2 selective policy avoided the five harmful actions that the always-act
policy would have selected, but only covered 3 of 14 action candidates, below
the preregistered 50% minimum, and its adjusted significance gate also failed.

## Locked benchmark and uncertainty

| Method | Test MAE (n=21) |
|---|---:|
| Deterministic rule | **3.889** |
| Action-conditional ridge | 5.261 |
| Temporal persistence | 17.460 |

The 90% conformal calibration became finite with calibration n=21: rank 20,
radius 19.459. Empirical coverage was 20/21=0.952 on the locked test split and
41/48=0.854 on the designated OOD split. The support detector classified 0/21
test units and 48/48 designated OOD units as OOD. It is a deterministic support
detector, not a claimed probabilistically calibrated OOD score.

## Identified sandbox contrasts

The complete three-arm blocks identify the preregistered sandbox action
contrasts only under clean-reset consistency, no interference, and measured
block exchangeability.

- Effective versus no-action test burden: mean −39.048, 95% block-bootstrap CI
  [−72.381, −8.571], 0/7 harmful actions.
- Negative-control versus no-action test burden: mean +13.333, 95%
  block-bootstrap CI [4.762, 22.857], 5/7 harmful actions.
- The frozen dataset contains 132 units in 44 complete blocks, 1,584 telemetry
  samples, 31 harmful-action events, eight false-remediation events, and 764
  explicit missing metric cells.

These contrasts validate the action-arm design and harm endpoint. They do not
overrule the failed H1/H2 promotion gates.

## Safety and claim boundary

- The dashboard performs locked offline evaluation only; it has no mutation or
  actuation endpoint.
- Zero model-selected actions were applied.
- Eighty campaign actions were experimental interventions, each explicitly
  approved under the sandbox policy and followed by verified clean recovery.
- Intervention outcomes are labelled `sandbox-measured`; the radio path is
  `simulated` through UERANSIM.
- `hardware-measured` remains absent and `operator-validated` remains false.

The evidence supports a local sandbox research result only. It does not support
private-5G hardware performance, operator deployment, unrestricted autonomy,
or live actuation.

## Remaining external-authority gates

These are intentionally pending and cannot be completed from the local repo:

1. collect measurements on identified private-5G hardware after access or
   purchase authorization;
2. conduct an independent operator trial after credentials and coordination;
3. submit or publish only after explicit publication authorization.
