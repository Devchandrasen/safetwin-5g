# SafeTwin-5G Project Lock

**Lock date:** 2026-08-24
**Review horizon:** 2029-12-31
**Research identity:** Trustworthy Autonomous Networks

## Fixed research area

**Causal, uncertainty-aware network digital twins for safe autonomous
private-5G/6G operations.**

Individual papers, student projects, datasets, demos, grant proposals, and
product features must contribute to this common platform. They must not become
disconnected topic changes.

## Flagship question

Can an intervention-trained network digital twin estimate the effects of
candidate remediation actions and safely abstain or escalate under uncertainty,
reducing SLA violations without increasing harmful actions?

## Initial network boundary

- Private 5G Standalone sandbox first.
- Open5GS core, UERANSIM software RAN/UE, and Prometheus telemetry.
- Core and orchestration actions before RAN control.
- RAN, hardware, multi-site, and operator trials enter only after the software
  sandbox evidence gate passes.

## Fixed methodological spine

1. Controlled interventions, not passive correlation alone.
2. Causal/counterfactual action-effect estimation.
3. Calibrated uncertainty and distribution-shift detection.
4. Selective prediction: abstain when evidence is insufficient.
5. Explicit safety policy, rollback plan, and human approval.
6. Reproducible testbed and honest simulation/sandbox/live labels.

## Hypotheses

- **H1 — Effect estimation:** under intervention-held-out evaluation, the
  causal twin will reduce action-effect prediction error relative to
  correlational temporal baselines.
- **H2 — Selective safety:** at a declared operating coverage, uncertainty-aware
  abstention will reduce harmful remediation rate relative to always-act
  policies.
- **H3 — Operational value:** human-governed twin-assisted remediation will
  reduce SLA-violation duration and mean time to recovery relative to rules and
  propose-only diagnosis, without increasing rollback or false-remediation rate.

These are hypotheses to test, not assumed results.

## Non-goals

- A generic telecom chatbot or generic “AI for 6G” survey project.
- Unrestricted LLM or agentic control of a network.
- Another isolated metaheuristic resource-allocation paper.
- Combining blockchain, quantum, photonics, federated learning, and agents
  without a direct need from the flagship question.
- Calling fixtures, generated telemetry, or a simulator a live network.
- Manufacturing a positive result when a simple baseline wins.

## Claim gates

| Label | Minimum evidence |
|---|---|
| `fixture` | Protocol-compatible deterministic source; no network claim |
| `simulated` | Versioned simulator/configuration, seeds, and replayable run |
| `sandbox-measured` | Running Open5GS/UERANSIM/Prometheus stack with logged faults and actions |
| `hardware-measured` | Identified private-5G hardware and repeatable measurement protocol |
| `operator-validated` | Independent operator environment or operator-confirmed trial |

No higher label may be inferred from a lower one.

## Safety lock

During Phase 0 and Phase 1:

- all network actions are sandbox-only;
- all eligible actions require human approval;
- live actuation is blocked;
- irreversible actions and actions without rollback plans are rejected;
- low-confidence or shifted cases must abstain;
- the LLM, if added, may explain evidence but may not bypass the safety gate.

## Scope-change rule

The area remains locked through the review horizon. A scope amendment requires a
versioned architecture decision record containing:

1. new operational evidence;
2. impact on the flagship hypotheses;
3. what is removed, not only what is added;
4. resource and validation cost;
5. an explicit decision to accept or reject the amendment.
