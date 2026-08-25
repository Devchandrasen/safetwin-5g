# Phase 7 BRACE Preregistered Protocol

**Frozen:** 2026-08-25 before implementation, pilot, or v2 campaign  
**Machine-readable design:** `config/experiments/phase7-brace-v2.json`  
**Evidence boundary:** `sandbox-measured` intervention; `simulated` radio

## Research question

Can a block-calibrated counterfactual certificate select a beneficial named
private-5G remediation action after inspecting all candidate intervals while
retaining simultaneous 90% marginal coverage, useful action coverage, verified
rollback, and mandatory human approval?

This is a new Phase 7 question informed by the locked Phase 6 negative result.
Phase 6 is not re-analysed into a positive claim. Dataset v1 may be used only for
implementation feasibility and explicitly labelled exploratory diagnostics.
All confirmatory results must come from the fresh frozen v2 splits.

## Experimental design

The assignment block is a fault family, severity, seed, workload, and split.
Every block executes the same five named actions in SHA-256 order. Each action
receives a separate clean-reset sandbox run with baseline, fault, post-action,
and recovery windows. Each window has three timestamped samples. Any incomplete
block, failed cleanup, missing approval, or dirty recovery stops acceptance of
the campaign.

| Split | Independent blocks | Units | Use |
|---|---:|---:|---|
| Train | 28 | 140 | model fit and block-level cross-validation only |
| Calibration | 21 | 105 | BRACE and comparator calibration only |
| Test | 35 | 175 | sealed confirmatory evaluation |
| OOD | 16 | 80 | held-out severity and sustained-workload stress test |
| **Total** | **100** | **500** | five complete named-action units per block |

The intervention portfolio is observe only, clear packet impairment, resume
UPF, stop CPU stress, and apply 25% packet impairment. The last action is an
approved reversible distractor, not an assumed harmful label. Outcome status is
computed only after measurement.

## Models and comparators

Hyperparameters are chosen by leave-one-block-out validation within train only.
Calibration labels never tune the outcome model. Required policies are:

- observe-only fallback;
- deterministic runbook;
- best point-estimate action without uncertainty;
- row-wise scalar split conformal;
- per-action action-conditional conformal; and
- BRACE-v1 simultaneous block conformal.

Required ablations remove, one at a time, the joint block score, OOD gate, and
rollback precondition. An ablation is evaluated offline and cannot bypass the
sandbox mutation policy.

## BRACE decision

For every ID block, the fitted model predicts each named action's improvement
against observe-only. The calibration score is the largest absolute contrast
residual across mutating actions in that complete block. Rank
`ceil((n_cal + 1) * 0.90)` defines the simultaneous radius; if the rank exceeds
the number of calibration blocks, the interval is unbounded and every mutation
abstains.

A mutation is certifiable only when all conditions hold:

1. the block is within frozen workload and severity support;
2. all required action predictions are present;
3. the simultaneous lower benefit bound exceeds 5 burden points;
4. the action is allowlisted and reversible;
5. a pre-action rollback plan is present; and
6. the proposal has explicit human approval before sandbox execution.

The offline policy chooses the certifiable action with the largest lower bound;
ties resolve by frozen action identifier. No certifiable mutation means
observe-only plus abstention/escalation. Test evaluation never applies a model
action; it scores the already-randomized experimental arms. Future sandbox
application would still require a new explicit approval record.

## Endpoints and gates

All reports use blocks as independent units and include counts, denominators,
mean, median, standard deviation, IQR, relevant percentiles, effect sizes, and
95% confidence intervals. Paired block inference is used where policies are
evaluated on the same blocks. G2 and G3 use Holm adjustment.

- **G1 — simultaneous coverage:** at least 90% of the 35 test blocks have every
  named-action contrast inside the BRACE vector interval.
- **G2 — certificate validity and utility:** zero certified mutation violates
  the frozen 5-point benefit margin and certified mutation coverage is at least
  50% among faulty ID test blocks. Zero selected actions cannot pass.
- **G3 — comparative safety:** BRACE harmful-action incidence is below the
  point-estimate policy at matched mutation coverage under paired block
  inference. If the point policy has no harms, the strict improvement claim
  fails rather than changing comparator or endpoint.
- **G4 — operational recovery:** every experimental mutation has recorded
  approval, command trace, timestamps, versions, hashes, and verified clean
  recovery. One unresolved dirty recovery blocks dataset acceptance.

Harm means a mutating selected action either worsens burden beyond the frozen
margin or constitutes false remediation in a no-fault block. Recovery success
is reported separately and is not inferred from a beneficial post-action
outcome.

## OOD and claim policy

Designated OOD blocks never contribute to ID calibration or the primary gates.
BRACE must abstain on all of them; their empirical interval coverage is reported
only as a stress-test diagnostic. No conditional, hardware, operator, or live
network guarantee is claimed.

The manuscript gate remains closed until implementation, fresh campaign,
analysis, audit, scalability measurements, and reproducible artifact review all
pass. Submission itself requires separate user authorization.
