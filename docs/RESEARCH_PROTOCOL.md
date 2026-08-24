# Research Protocol v0.1

## Objective

Evaluate whether a causal network digital twin with calibrated abstention can
select safer private-5G remediation actions than correlational and always-act
baselines.

## Experimental unit

One experimental unit is a versioned scenario containing:

1. testbed version and topology;
2. workload and random seed;
3. injected fault and injection timestamp;
4. pre-action telemetry window;
5. one candidate action and rollback plan;
6. decision source and, only for model decisions, confidence and
   distribution-shift score;
7. safety-gate decision;
8. post-action telemetry window and observed outcome, if the action is applied.

## Phase-1 fault families

- CPU or memory saturation of a core network function;
- network-function termination or delayed recovery;
- packet loss, latency, or bandwidth impairment;
- signalling overload;
- reversible QoS or routing misconfiguration.

## Phase-1 action families

- restart a sandbox network function;
- scale a sandbox network function;
- change sandbox UPF selection/routing;
- apply a reversible QoS policy change;
- apply reversible admission throttling.

Every applied action must have an executable rollback and human approval.

## Baselines

1. no-action observation;
2. deterministic runbook/rule policy;
3. correlational tabular baseline;
4. temporal prediction baseline;
5. always-act version of the proposed estimator;
6. causal estimator without uncertainty abstention.

An LLM explanation layer is not a causal or control baseline.

## Splits and leakage controls

- Split by scenario, intervention, and time; never randomly split adjacent
  telemetry rows from the same intervention across train and test.
- Keep at least one fault-severity range and one workload regime for
  distribution-shift evaluation.
- Fit normalization, feature selection, calibration, and thresholds using only
  training/calibration data.
- Report simulator and sandbox results separately.

## Primary endpoints

- action-effect prediction error;
- harmful remediation rate;
- SLA-violation duration;
- mean time to recovery;
- rollback and false-remediation rate;
- risk-coverage curve and area under the risk-coverage curve;
- abstention rate under in-distribution and shifted conditions;
- decision latency and resource overhead.

## Falsification rules

- If rules or a simple tabular model match the proposed method within the
  declared uncertainty interval, do not claim superiority.
- If abstention lowers coverage without materially lowering harm, H2 is not
  supported.
- If the twin cannot predict held-out intervention effects, do not substitute
  passive anomaly-prediction accuracy for H1.
- If the system has not applied and rolled back controlled sandbox actions, do
  not claim closed-loop validation.

## Reporting labels

Every table and figure must state one of: `fixture`, `simulated`,
`sandbox-measured`, `hardware-measured`, or `operator-validated`.
