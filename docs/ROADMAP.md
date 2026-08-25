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
- [x] Produce a reproducible benchmark report and go/no-go decision for H1–H3
      (`evidence/benchmarks/20260824T054718Z-benchmark-report-v0`; H1 and H2
      `not-supported`, H3 `not-tested`; model promotion, live actuation, and
      positive H1–H3 claims are no-go; 88 tests captured at
      `evidence/verification/20260824T054807Z-benchmark-report-v0`).

## Phase 5 — Local product and dashboard

- [x] Build a localhost-only, read-only evidence dashboard
      (`evidence/verification/20260824T060413Z-local-dashboard-v0`; production
      build and lint passed, full dependency audit found zero vulnerabilities,
      and 92 repository tests passed).
- [x] Add a machine-readable status API and proposal audit view with no
      actuation endpoint
      (`evidence/verification/20260824T061147Z-product-status-api-v0`; snapshot
      drift check, build, lint, zero-vulnerability audit, and 94 tests passed).
- [x] Run end-to-end local product QA and preserve the smoke-test evidence
      (`evidence/product/20260824T061959Z-dashboard-smoke-v0`; loopback-only,
      read routes 200, mutation methods 405, actuation routes 404;
      `evidence/verification/20260824T062046Z-product-qa-v0`; 97 tests passed).

## Phase 6 — Identifiable expanded sandbox study

- [x] Preregister an independent multi-action design with no-fault controls,
      continuous telemetry windows, a true held-out workload/severity split,
      and explicit H1-H3 decision gates (`docs/PHASE6_PROTOCOL.md`;
      `config/experiments/phase6-v1.json`; 132 planned units; 21 calibration
      units; 103 tests passed at
      `evidence/verification/20260824T073147Z-phase6-preregistration-v1`; the
      corrected invocation retains the failed environment-only capture at
      `20260824T073135Z`).
- [x] Implement and verify the fail-closed Phase 6 runner and reversible action
      arms (`evidence/scenarios/20260824T073851Z-phase6-pilot-v1`; 3/3
      sandbox-measured pilot units cover effective, no-action, and negative
      control arms with clean recovery; 109 tests and the bundle audit passed at
      `evidence/verification/20260824T074234Z-phase6-runner-v1`).
- [x] Execute the preregistered campaign and freeze intervention dataset v1
      (`evidence/scenarios/20260824T074320Z-phase6-campaign-v1`; 132/132 passed,
      no cleanup abort, 1,584 telemetry samples; release
      `data/releases/safetwin5g-interventions-v1` has 44 complete three-arm
      blocks, 31 harmful-action events, 8 false-remediation events, and 764
      explicit missing metric cells; bundle/data audit and 114 tests passed at
      `evidence/verification/20260824T091705Z-dataset-v1`).
- [x] Re-run baselines, causal estimation, uncertainty/OOD/abstention, and
      H1-H3 gates on the locked v1 data
      (`evidence/benchmarks/20260825T030431Z-phase6-analysis-v1`; deterministic
      rule wins test MAE 3.889 versus learned model 5.261 and temporal 17.460;
      90% conformal radius is finite at calibration n=21; test OOD 0/21 and
      designated OOD detected 48/48; H1 and H2 are `not-supported` after Holm
      adjustment at 0.0625, H2 coverage is 3/14, and H3 is `gated-not-run`;
      independent calculation/hash audit and 124 tests passed at
      `evidence/verification/20260825T030634Z-phase6-analysis-v1`).
- [x] Publish the evidence-linked Phase 6 decision and refresh the local
      read-only dashboard (`docs/PHASE6_DECISION.md`;
      `evidence/product/20260825T032218Z-dashboard-smoke-v1`; loopback-only,
      read routes 200, mutation methods 405, actuation routes 404, 14 locked
      test candidates and zero model actions; production build, lint,
      zero-vulnerability audit, and 124 tests passed at
      `evidence/verification/20260825T032902Z-phase6-product-v1`). The initial
      heading-contract smoke failure at `20260825T032117Z` and verification
      failures caused by a running-server file lock at `20260825T032458Z` and
      transient registry DNS at `20260825T032528Z` are retained.

All locally executable Phase 1-6 roadmap items are complete. The external
gates below require new authority and are not inferred from local software or
sandbox evidence.

## Phase 7 — TNSM novelty falsification

- [x] Audit the closest primary literature, reject generic conformal action
      selection and Open5GS/UERANSIM integration as novelty, and preregister
      the BRACE candidate plus a non-leaking named-action study
      (`docs/PHASE7_NOVELTY_AUDIT.md`; `docs/PHASE7_PROTOCOL.md`;
      `config/experiments/phase7-brace-v2.json`; 100 complete blocks and 500
      sandbox units; 130 tests and design validation passed at
      `evidence/verification/20260825T043343Z-phase7-preregistration-v2`).
- [x] Implement and verify BRACE simultaneous block calibration, action
      certificates, OOD abstention, and rollback/evidence preconditions
      (`docs/BRACE_METHOD.md`; `src/safetwin5g/brace.py`; finite 90% block
      radius at 21 calibration blocks, unbounded small-sample abstention, no
      actuation authorization, and 137 tests passed at
      `evidence/verification/20260825T043650Z-brace-v1`).
- [x] Run the locked v1 exploratory feasibility and prospective precision
      checks without upgrading the negative Phase 6 decision
      (`evidence/benchmarks/20260825T044022Z-phase7-v1-feasibility`; 0/44
      strict five-action blocks, seven legacy calibration blocks give
      unbounded 90% rank 8, and BRACE certifies 0/7 ID and 0/16 OOD blocks;
      independent hash/arithmetic audit and 143 tests passed at
      `evidence/verification/20260825T044039Z-phase7-v1-feasibility`). The
      prospective check found that 15 certified mutations at the frozen 50%
      coverage floor give a one-sided 95% zero-violation upper bound of 0.181,
      so the fresh test design needs a pre-campaign precision amendment for an
      empirical 0.10 safety bound.
- [x] Amend and re-freeze the v2 test split before any pilot to provide at
      least 29 certified faulty-block decisions at the 50% coverage floor
      (`docs/PHASE7_PROTOCOL_AMENDMENT_1.md`;
      `config/experiments/phase7-brace-v2a.json`; 60 faulty and 10 no-fault
      test blocks, 135 total blocks, 675 units, and exact one-sided 95%
      zero-violation upper bound 0.095 at 30 certifications; 148 tests and the
      design check passed at
      `evidence/verification/20260825T044323Z-phase7-precision-amendment-a1`).
- [ ] Execute the fresh v2 pilot and 500-unit named-action sandbox campaign;
      freeze and audit the complete-block dataset before opening test labels.
- [ ] Run the preregistered BRACE comparisons, paired-block inference,
      ablations, OOD stress test, runtime/scalability evaluation, and
      independent artifact audit.
- [ ] Draft a TNSM manuscript only if the novelty, utility, coverage, and
      recovery gates pass; otherwise publish a no-go decision instead of a
      positive claim.

## External-authority gates

- [ ] Collect `hardware-measured` evidence on identified private-5G hardware
      (pending hardware access or purchase authorization).
- [ ] Obtain `operator-validated` evidence in an independent operator
      environment (pending operator coordination and credentials).
- [ ] Submit or publish results (pending explicit publication authorization).
