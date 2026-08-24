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
