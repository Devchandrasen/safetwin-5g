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
- [x] Implement, dry-run, and audit the fail-closed v2a named-action runner and
      one complete-block sandbox pilot
      (`evidence/scenarios/20260825T044909Z-phase7-pilot-v2a`; 5/5 units,
      four approved reversible mutations, all five named actions, zero model
      actions, and clean recovery without abort; independent bundle/command/
      state audit plus 155 tests passed at
      `evidence/verification/20260825T045224Z-phase7-runner-v2a`).
- [x] Freeze and verify the public-safe dataset v2a builder before opening any
      confirmatory labels (`docs/DATASET_V2A_CONTRACT.md`; full releases reject
      pilot or incomplete input, authorization prose/identity is excluded, and
      160 tests plus 9 subtests passed at
      `evidence/verification/20260825T045956Z-dataset-v2a-builder`).
- [x] Implement and hash-lock the block-independent analysis, required
      comparators, BRACE calibration, paired inference, Holm correction,
      ablations, OOD abstention, and honest no-go path before outcome analysis
      (`config/experiments/phase7-analysis-v2a-lock.json`; Analysis Amendment A1
      corrected G3 to include no-fault false remediation across all 70 paired
      test blocks while G2 remains on 60 faulty blocks; Environment Deviation
      D1 adds only the co-resident-host limitation, with no statistical change;
      the seal is procedural rather than cryptographic and operational monitors
      read pass/cleanup metadata but no outcomes; synthetic full-design
      baseline-win/no-go check; 172 tests plus 9 subtests passed at
      `evidence/verification/20260825T081330Z-phase7-analysis-freeze`).
- [x] Measure and audit BRACE certificate-computation scalability with bounded
      fixture claims (`evidence/benchmarks/20260825T051037Z-phase7-brace-scalability`;
      21 to 5,000 blocks, empirical log-log slope 0.976, 3.024 ms median at
      5,000 blocks, and 2.662 microseconds per proposal; no network, radio,
      hardware, or operator performance claim; verified at
      `evidence/verification/20260825T051111Z-phase7-scalability`).
- [x] Implement and fixture-verify the independent cross-artifact provenance
      auditor; it rejects broken campaign-to-dataset hashes and claim-tier
      promotion, requires D1 in dataset quality, and keeps the actual-chain
      audit gated on final artifacts
      (`evidence/verification/20260825T081920Z-phase7-provenance-auditor`;
      175 tests plus 9 subtests passed).
- [x] Implement and fixture-verify the fail-closed local TNSM manuscript gate:
      all G1-G4 and actual provenance must pass, while a baseline win, missing
      D1 disclosure, claim promotion, live actuation, or submission authority
      mismatch blocks a positive draft (`evidence/verification/
      20260825T081907Z-tnsm-manuscript-gate`; 175 tests plus 9 subtests passed;
      actual gate evaluation remains pending final artifacts).
- [ ] Execute the fresh 675-unit named-action sandbox campaign; freeze and
      audit the 135 complete-block dataset before outcome analysis. **No-go
      pending recovery correction validation:** the first attempt was rejected after an external
      Docker Desktop Compose stop at 419/675; the second attempt reached a
      435/675 stdout progress line but persisted only 434 traces before a
      Windows Application-API sleep transition stopped the process. Both runs
      remain unanalysed and inadmissible
      (`docs/PHASE7_CAMPAIGN_ABORT_1.md`;
      `docs/PHASE7_CAMPAIGN_ABORT_2.md`; host-sleep diagnosis, wrapper probe,
      and 180-test regression verification passed at
      `evidence/verification/20260901T025845Z-phase7-host-resilience`). The
      third attempt started at unit 1 under the verified host sleep-inhibition
      wrapper on September 1 and was paused at user request after 546 durable
      units. Metadata and cleanup checks passed before September 5 continuation
      from unit 547 using the existing resume support
      (`docs/PHASE7_PAUSE_RESUME_1.md`; checkpoint:
      `evidence/environment/20260905T015200Z-phase7-resume-checkpoint`;
      provenance audit and 185 tests plus 9 subtests passed at
      `evidence/verification/20260905T015825Z-phase7-resume`). Collection
      finished at 675/675, but the frozen dataset gate rejected 582 unclean
      service-recovery units and 582 right-censored MTTR records. The original
      runner's passing flags omitted observed packet loss and are not
      acceptance evidence (`docs/PHASE7_RECOVERY_REJECTION_1.md`). No dataset
      release or confirmatory model analysis was produced. P1 and D1 retain
      the collection-gap and shared-host limitations.
- [x] Diagnose the Phase 7 service-recovery validation gap and correct the
      runtime guard and independent auditor. Invalid/missing service metrics
      or baseline block mutations, recovery requires all clean samples, and
      any failed unit stops collection. The corrected auditor rejects the
      historical bundle; 188 tests plus 15 subtests pass at
      `evidence/verification/20260905T040812Z-phase7-recovery-guard`.
- [ ] Validate a bounded repeated-interruption engineering pilot and an
      explicit PDU reset/rollback protocol before another confirmatory run.
      **In progress, not accepted:** R1 stopped at its first no-fault baseline
      (0/15 packets), injected no fault, and restored 15/15 packets only after
      an approved UE restart. Independent raw-sample/hash diagnosis preserves
      the failure and a source-supported Service Request/AMF-selection
      candidate (`docs/RECOVERY_PILOT_R1_DECISION.md`). The separately frozen
      reconnect R1 completed all four trials and independently replayed 280
      commands and 30 samples: both controls returned 15/15, both eight-second
      link drops returned 0/15 after qdisc rollback, and approved UE restarts
      restored 15/15 (`docs/RECONNECT_R1_DECISION.md`; 219 tests and 19 subtests
      passed at `evidence/verification/20260905T062820Z-reconnect-r1`). Failure
      reproduction is verified, not a network fix. R2 then verified the
      original-function absent-SST counterexample, 16 source fixtures, the
      full derived build and one-file patch replay; the official image and
      UE binary remain unchanged (`docs/RECONNECT_R2_BUILD_DECISION.md`;
      223 tests plus 19 subtests at
      `evidence/verification/20260905T071849Z-reconnect-r2`). The separately
      frozen R2 network comparison then stopped at six of eight assignments:
      official drops reproduced 0/15, but the first derived drop returned only
      14/15 despite Service Accept. The required 15/15 endpoint failed; the
      final two assignments were not run. The official image and fresh 15/15
      service were restored. Independent integrity audit replayed 480 commands,
      48 samples and 10 scope snapshots, with 240 tests and 19 subtests passing
      (`docs/RECONNECT_R2_DECISION.md`;
      `evidence/verification/20260905T083007Z-reconnect-r2`). Integrity is
      verified, not a network fix. The read-only first-packet investigation
      then verified that the pinned idle NAS branch signals pending data but
      does not retain/forward its payload: 60 exact-method fixture cases,
      a failing negative control, 12 official source matches and a 24-command
      audit (`docs/RECONNECT_PACKET_DIAGNOSIS.md`; 251 tests and 22 subtests at
      `evidence/verification/20260905T091926Z-reconnect-packet`). This is source
      fixture evidence consistent with R2, not direct packet localization or
      a correction. The R3 instrumentation-only source and four-trial diagnostic
      contract are now frozen: 65 parser cases, 61 NAS cases in each of two
      modes, exact three-file removal and actual Git-patch replay pass
      (`docs/RECONNECT_R3_SOURCE_FREEZE.md`; 272 tests and 32 subtests at
      `evidence/verification/20260905T102936Z-reconnect-r3`). The separate R3
      image build and real-header compile now pass a versioned independent
      audit: 4,267 tracked files, only the three intended edits plus one header,
      both linked binaries, immutable R2 ancestry and preserved container
      identity/configuration checks (`docs/RECONNECT_R3_BUILD_DECISION.md`;
      306 tests and 32 subtests at
      `evidence/verification/20260905T112828Z-reconnect-r3-build`). The original
      mount-order audit rejection and local private raw evidence are retained;
      the Git release uses explicitly audited redaction. No image is applied.
      The separate execution runner, independent raw-ping/trace auditor,
      two-service override and 74-source execution lock now pass the fixture
      gate (`docs/RECONNECT_R3_EXECUTION.md`; 339 tests plus 122 subtests and
      nine verification checks at
      `evidence/verification/20260905T125506Z-reconnect-r3-execution`). Four
      fake-transport variants preserve complete and stopped protocol cases;
      the complete fixture replays 354 synthetic commands, 33 samples and
      eight scope snapshots, explicitly not network evidence. Two failed
      read-only preflights are retained with their exact source versions; the
      corrected scope preflight passed with mutations disabled. The subsequent
      R3 attempt was rejected during its first baseline window despite 5/5
      returned packets, because required early traces were missing. Zero
      exposures ran. Both official images and final 15/15 service were restored
      (`docs/RECONNECT_R3_DECISION.md`; run
      `evidence/engineering/20260905T131024Z-reconnect-r3-network`). A separate
      observation audit verifies the rejected prefix: 131 commands, six samples
      and five scopes, with the original complete-protocol rejection preserved.
      UE-only reset changed the source address outside the trace filter; later
      read-only clock probes independently verify host/container skew, supporting
      but not uniquely proving historical log-prefix clipping. Seven verification
      checks, 355 tests and 132 subtests pass at
      `evidence/verification/20260905T133535Z-reconnect-r3-observation`.
      A separate R4 collection contract now passes the fixture-only software
      gate (`docs/RECONNECT_R4_COLLECTION_DECISION.md`; eight-source lock,
      independent prefix/clock/source/path replay, fourteen retained fixture
      cases, 381 tests and 171 subtests, eleven checks at
      `evidence/verification/20260905T143948Z-reconnect-r4-collection`). No
      network trial or image application ran; read-only scope and official
      logging metadata checks passed. The separate bounded Windows adapter and
      full approval/telemetry/fresh-PDU/rollback execution integration now pass
      their software gate (`docs/RECONNECT_R4_EXECUTION_DECISION.md`; 15-source
      lock, 398 tests, 200 subtests and twelve checks at
      `evidence/verification/20260905T164055Z-reconnect-r4-execution`). Seventeen
      whole-protocol and seven local subprocess cases are retained and the
      protocol archives are freshly extracted and independently replayed.
      Failed cleanup, reset, health wait and official restoration are covered;
      the failed initial gate and its exact sources remain preserved. These
      are fixture results, not measured recovery. No R4 image application,
      fault, restart, ping or sleep-inhibition request ran in this gate.
      The subsequent once-only approved R4 diagnostic was rejected before
      baseline or exposure: 55 command records (54 Docker, one Git), no samples
      and zero valid assignments. Three wall/QPC flags interrupted trial
      admission and official rollback verification; both original restoration
      flags remain false. A separate read-only observation verifies official
      images, fresh PDU, neutral telemetry and 15/15 packets. Its independent
      audit does not accept or repair R4. The later 1,000-sample clock probe
      did not reproduce the failure, although nominal wall resolution 15.625 ms
      exceeds the frozen 1 ms predicate. Historical cause remains unresolved
      (`docs/RECONNECT_R4_DECISION.md`; 425 tests, 200 subtests and twelve checks
      at `evidence/verification/20260905T172149Z-reconnect-r4-observation`).
      The separate five-source R5 clock contract now passes its software gate:
      37 retained cases (seven sampled-consistency passes, thirty expected
      rejections), 493 tests, 200 subtests and twelve checks. A separate fixed
      64-read local-host API observation passes 2,016 independent interval
      comparisons, with maximum expanded bracket 17.5 microseconds and worst
      residual endpoint 27.6 microseconds. This is not network recovery or a
      historical-cause proof (`docs/RECONNECT_R5_CLOCK_DECISION.md`;
      `evidence/verification/20260905T181844Z-reconnect-r5-clock`). The oversized
      pytest-name failure and exact pre-correction sources are preserved.
      Next is a separate R5 execution-integration fixture gate, preserving all
      approval, capture, source, telemetry and official rollback requirements.
      Its first clock-journal component now passes, but the full integration
      remains pending (`docs/RECONNECT_R5_JOURNAL_DECISION.md`; 563 tests,
      200 subtests, 21 checks and ten independently replayed synthetic cases at
      `evidence/verification/20260905T191336Z-reconnect-r5-journal`). This adds
      a nonrenewable 256-point cleanup reserve, incremental all-pair checks
      and exception-isolated no-I/O cleanup callbacks. It does not implement
      command containment, actual official rollback or whole-protocol replay.
      No network trial, packet probe or sleep-inhibition request ran.
      The separately named R5 owned-client adapter now also passes its component
      gate (`docs/RECONNECT_R5_PROCESS_DECISION.md`; 596 tests, 200 subtests,
      30 checks and 21 retained local-process cases at
      `evidence/verification/20260905T201840Z-reconnect-r5-process`). Same-domain
      shared-envelope accounting, byte/time caps and a negative-evidence kernel
      cutoff after QPC failure are verified. A fixed two-command native helper
      observation uses four points; this remains fixture evidence, not PDU or
      recovery measurement. Host/collection/runner integration, full point
      inventory and independent whole-protocol/official rollback replay remain
      pending. No new network diagnostic was executed.
      This parent recovery item remains open.
      No R3/R4 rerun, endpoint relaxation, model promotion or new 675-unit
      campaign follows from observation integrity or later service recovery.
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
