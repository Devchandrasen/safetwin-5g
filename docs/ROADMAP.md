# Execution Roadmap

## Day 1 — 2026-08-24

- [x] Lock the research area, hypotheses, non-goals, and claim gates.
- [x] Create a separate versionable project.
- [x] Define intervention and action contracts.
- [x] Implement abstain/reject/human-approval safety decisions.
- [x] Add an append-only intervention log and unit tests.
- [x] Record the Docker-engine blocker without upgrading the evidence label.

## Days 2–14 — Real sandbox gate

- [x] Start and verify Docker Desktop (engine 29.4.2 on 2026-08-24).
- [x] Pin official Open5GS, UERANSIM, MongoDB, and Prometheus versions
      (`docs/COMPONENT_PINS.md`; machine-readable digests in
      `sandbox/versions.lock.json`).
- [x] Bring up an isolated 5G Standalone software sandbox
      (`evidence/sandbox/20260824T044704Z-stack`; `simulated`, pre-intervention).
- [x] Capture a clean baseline attach/session trace
      (`evidence/sandbox/20260824T045006Z-baseline`; `simulated`, 20/20 pings).
- [x] Inject one reversible fault and execute one approved rollback
      (`evidence/sandbox/20260824T045620Z-intervention`; `sandbox-measured`
      intervention, `simulated` radio).
- [x] Save and audit configuration, commands, telemetry, timestamps, versions,
      and hashes (`evidence/audits/20260824T045939Z-intervention-audit`; 17/17
      checks passed).

**Exit criterion:** one replayable `sandbox-measured` intervention record with a
verified rollback. Until then, all records remain `fixture` or `simulated`.

## Days 15–30 — Intervention dataset v0

- [x] Implement telemetry adapters and scenario runner
      (`evidence/verification/20260824T050325Z-telemetry-scenario-runner`; 43
      tests passed, 377 measured-bundle rows replayed).
- [x] Define canonical KPIs and units
      (`evidence/verification/20260824T050537Z-canonical-kpis`; 48 tests passed,
      30-cell canonical stage grid with explicit missingness).
- [x] Execute at least three fault families at multiple severities and seeds
      (`evidence/scenarios/20260824T051612Z-scenario-matrix-v0`; 12/12 passed;
      prior 10/12 threshold failure retained at `20260824T051128Z`).
- [x] Freeze dataset manifest and data-quality report
      (`data/releases/safetwin5g-interventions-v0`; 12 records, 720 expected
      metric cells, 32 explicit missing cells; alternative-action effects not
      identified).

## Days 31–60 — Baselines and causal twin v0

- [x] Run rule, tabular, and temporal baselines
      (`evidence/benchmarks/20260824T052852Z-baselines-v0`; deterministic rule
      wins test MAE 3.333 vs ridge 17.876 and persistence 29.333; no promotion).
- [x] Define the causal graph and intervention assumptions
      (`config/causal_graph_v0.json`; alternative-action effect fails closed on
      exchangeability, positivity, and carry-over; 65 tests passed).
- [x] Estimate held-out action effects under the identification gate
      (`evidence/benchmarks/20260824T053222Z-heldout-effects-v0`; descriptive
      proxy test MAE 17.000, OOD MAE 13.667; alternative-action ATE blocked).
- [x] Run leakage, calibration, and negative-control checks
      (`evidence/benchmarks/20260824T053419Z-diagnostics-v0`; leakage/placebos
      pass, but 90% conformal calibration is unbounded at n=3; promotion
      blocked).

## Days 61–90 — Selective safety evaluation

- [x] Add fail-closed calibrated uncertainty and OOD detection
      (`evidence/benchmarks/20260824T053654Z-uncertainty-ood-v0`; 90% interval
      unbounded, 6/6 abstain, test and OOD both severity-shifted).
- [x] Evaluate risk-coverage and harmful-action endpoints
      (`evidence/benchmarks/20260824T053857Z-selective-evaluation-v0`; coverage
      0, abstention 1.0; selective harm, AURC, false-remediation, SLA duration,
      and MTTR correctly undefined).
- [x] Integrate the safety gate with sandbox proposals only
      (`evidence/benchmarks/20260824T054104Z-safety-integration-v0`; 6/6
      uncertain proposals abstained, zero actions applied, and 6/6 live
      sentinels rejected; 83 tests captured at
      `evidence/verification/20260824T054303Z-safety-integration-v0`).
- [ ] Produce a reproducible benchmark report and go/no-go decision for H1–H3.
