# Phase 6 Preregistered Sandbox Protocol

Status: frozen before Phase 6 execution on 2026-08-24  
Machine-readable design: `config/experiments/phase6-v1.json`

## Purpose and evidence boundary

Phase 6 addresses the limitations exposed by dataset v0: only one action per
fault, an action-first rollback proxy, three calibration rows, point telemetry,
and no no-fault condition. It does not presume a positive result. A baseline
win, an unbounded interval, excessive abstention, cleanup failure, or a failed
hypothesis gate is a valid negative outcome and will be retained.

Every measurement in this phase is `sandbox-measured` for the software
intervention and `simulated` for the radio. It is neither `hardware-measured`
nor `operator-validated`. No result may be described as evidence of unrestricted
live actuation.

## Experimental unit and assignment

The unit is one clean-reset sandbox run receiving exactly one independently
assigned action arm. Each unit proceeds through baseline, fault, post-action,
and recovery windows. Every window contains three timestamped telemetry samples.
The sandbox must be clean before the unit starts and after recovery; a failed
cleanup stops the campaign.

The frozen design expands to 132 units:

| Split | Units | Seeds | Workload | Role |
| --- | ---: | --- | --- | --- |
| train | 42 | 101, 202 | steady | model fitting only |
| calibration | 21 | 303 | steady | uncertainty/risk thresholds only |
| test | 21 | 404 | steady | locked in-distribution evaluation |
| OOD | 48 | 505, 606, 707, 808 | sustained | held-out workload and severity |

Within each split/fault/severity block, units cover effective, no-action, and
negative-control arms. SHA-256 sorting with the frozen salt determines execution
order within each split. A unit never uses a post-treatment rollback observation
as its causal control; contrasts are across independently reset units.

The fault conditions are packet impairment, UPF interruption, CPU saturation,
and no fault. Development uses two severities for each real fault and one
no-fault level. OOD uses a held-out severity and a longer sustained probe
workload. The no-fault arms expose false remediation. Negative controls are
deliberately ineffective or degrading but reversible sandbox actions. They must
be allowlisted before execution and restored to the pre-action fault state
before final cleanup.

## Safety gate

The campaign is fail-closed:

1. live actuation is disabled;
2. every sandbox mutation requires an explicit recorded approval, target, and
   rollback plan;
3. only allowlisted actions may execute;
4. final clean state is verified from telemetry; and
5. any failed cleanup aborts later units until diagnosed.

Observe-only arms do not mutate the sandbox, but their assigned decision and
timestamps are still recorded. The experiment authorization does not extend to
private-5G hardware, operator systems, credentials, outreach, purchasing, or
publication submission.

## Endpoints and estimands

The primary endpoints are target-KPI prediction error, harmful-action rate,
SLA-violation duration, and MTTR. Reports include count and denominator, mean,
median, standard deviation, interquartile range, and relevant percentiles.
Action effects compare independently assigned arms within fault/severity blocks;
95% block-bootstrap confidence intervals and effect sizes accompany point
estimates. Missing windows, cleanup failures, and abstentions remain explicit
rather than being silently dropped.

The nominal split-conformal coverage is 90%. The 21-unit calibration split is
above the mathematical minimum of 19 for a finite 90% split-conformal radius.
Thresholds are selected using train and calibration only. Test and OOD labels
remain sealed until the evaluation code and hashes are frozen.

H1 and H2 are co-primary and use Holm multiplicity adjustment:

- **H1:** the upper bound of the 95% confidence interval for model-minus-temporal
  test MAE must be below zero. The deterministic rule remains a required
  comparator and can still block product promotion even if H1 passes.
- **H2:** the upper bound for selective-minus-always-act harmful-action rate must
  be below zero at non-abstained coverage of at least 0.50. Zero-coverage safety
  does not count as support.
- **H3:** a counterbalanced human-governed policy comparison runs only if H1 and
  H2 pass. If either fails, H3 is reported as `gated-not-run`, not as support or
  as an executed test.

An overall no-go is the preregistered conclusion if the promotion gates fail.
No exploratory redefinition may upgrade a primary claim; exploratory analyses
must be labeled as such.

## Data-quality and reporting checks

Before a split is accepted, validation checks unit uniqueness, expected block
counts, action-arm positivity, stage/window completeness, monotonic timestamps,
units and denominators, split isolation, absence of target leakage, final clean
state, recorded approvals and rollback, version and command capture, and SHA-256
integrity. Results report sampling limitations, simulated-radio bias, multiple
testing, uncertainty, and all negative or blocked runs.
