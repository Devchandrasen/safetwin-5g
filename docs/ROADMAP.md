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
- [ ] Pin Open5GS, UERANSIM, Prometheus, and dashboard versions.
- [ ] Bring up an isolated 5G Standalone software sandbox.
- [ ] Capture a clean baseline attach/session trace.
- [ ] Inject one reversible fault and execute one approved rollback.
- [ ] Save configuration, commands, telemetry, timestamps, and hashes.

**Exit criterion:** one replayable `sandbox-measured` intervention record with a
verified rollback. Until then, all records remain `fixture` or `simulated`.

## Days 15–30 — Intervention dataset v0

- [ ] Implement telemetry adapters and scenario runner.
- [ ] Define canonical KPIs and units.
- [ ] Execute at least three fault families at multiple severities and seeds.
- [ ] Freeze dataset manifest and data-quality report.

## Days 31–60 — Baselines and causal twin v0

- [ ] Run rule, tabular, and temporal baselines.
- [ ] Define the causal graph and intervention assumptions.
- [ ] Estimate held-out action effects.
- [ ] Run leakage, calibration, and negative-control checks.

## Days 61–90 — Selective safety evaluation

- [ ] Add calibrated uncertainty and out-of-distribution detection.
- [ ] Evaluate risk-coverage and harmful-action endpoints.
- [ ] Integrate the safety gate with sandbox proposals only.
- [ ] Produce a reproducible benchmark report and go/no-go decision for H1–H3.
