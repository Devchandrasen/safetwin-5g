# SafeTwin-5G

SafeTwin-5G is a research and product project for **causal, uncertainty-aware
network digital twins that support safe closed-loop operations in private 5G
and future 6G networks**.

The project was locked on **2026-08-24**. Its research identity is
**Trustworthy Autonomous Networks**. The scope and claim boundaries are defined
in [PROJECT_LOCK.md](PROJECT_LOCK.md).

## Current status

**All locally executable Phase 1-6 roadmap work complete**

Implemented on day one:

- a strict schema for telemetry-backed intervention records;
- a selective safety gate that rejects unsupported or irreversible actions;
- mandatory abstention when confidence or distribution-shift checks fail;
- mandatory human approval for every otherwise-eligible sandbox action;
- an append-only JSONL intervention store;
- a CLI for environment checks, a safe-decision demo, and log validation;
- unit tests for contracts, safety decisions, and dataset integrity.

The official-tag Open5GS/UERANSIM source builds now run with MongoDB and
Prometheus on an internal Compose network. A simulated UE registered and
created PDU Session ID 1, and the first hash-manifested stack capture passed.
The clean baseline passed with 20/20 user-plane packets returned. A separately
approved deterministic runbook then measured 0% baseline loss, 100% controlled
loss, 0% after remediation, 100% after rollback, and 0% after final cleanup.
That intervention record passes the `sandbox-measured` gate; its radio remains
`simulated`, and it is neither hardware-measured nor operator-validated.
The expanded preregistered study froze 132 intervention units in 44 complete
three-arm blocks with 1,584 telemetry samples. The locked test set retained the
deterministic rule as the winner (MAE 3.889) over the action-conditional ridge
model (5.261) and temporal persistence (17.460). The conformal radius is finite
at calibration n=21, test coverage is 20/21, and the designated OOD split is
detected 48/48.

H1 and H2 are `not-supported` after the preregistered Holm correction
(adjusted p=0.0625 for both); H2 coverage is 3/14, below its 50% gate. H3 is
`gated-not-run` because H1 and H2 did not pass. The consolidated decision is
therefore no-go for model promotion, positive H1-H3 claims, and autonomous/live
actuation. Zero model-selected actions were executed.
The local evidence product is read-only, loopback-only, and exposes GET status
and proposal-audit APIs without an actuation route. Hardware, operator, and
publication gates remain pending external authorization.

### Phase 7 TNSM novelty falsification

Phase 6 remains a locked negative result. Phase 7 tests a narrower candidate
contribution, **BRACE** (Block-Randomized Action Certification with Evidence
tiers): complete clean-reset named-action blocks, simultaneous conformal
calibration of all action-versus-observe contrasts, and fail-closed OOD,
evidence, approval, reversibility, and rollback preconditions. The construction
uses established conformal ideas; the candidate contribution is the causal
network-remediation specialization, safety contract, and replayable benchmark,
not a claim of a new general conformal theorem.

The precision-amended campaign contains 675 isolated sandbox units in 135
complete five-action blocks. Its analysis is hash-locked before the 70 test
blocks: model selection uses train-block leave-one-block-out only, uncertainty
uses 21 calibration blocks, G2 uses 60 faulty test blocks, and G3 includes all
70 paired test blocks so no-fault false remediation cannot be hidden. Two full
campaign attempts were externally interrupted and are preserved as
inadmissible operational evidence: one by a Docker Desktop Compose stop and
one by a Windows Application-API sleep transition. A third run started on
September 1, paused at user request after 546 durable units, and continued on
September 5 with the existing resume support and verified sleep-inhibition
wrapper. All 675 traces were collected, but the frozen dataset gate rejected
them: 582 units had failed user-plane recovery and right-censored MTTR.
[Recovery rejection R1](docs/PHASE7_RECOVERY_REJECTION_1.md) records a validation
defect: the old runner and auditor checked fault configuration without checking
actual packet delivery. The defect is corrected, with 188 tests plus 15
subtests passing. The historical passing flags remain preserved but do not
establish acceptance. No dataset-v2a release or confirmatory BRACE analysis was
produced; the current TNSM disposition is **no-go-data-quality**.
[Pause/resume P1](docs/PHASE7_PAUSE_RESUME_1.md) preserves the original
environment and command prefix and discloses the collection gap. A bounded
recovery engineering pilot is required before another confirmatory campaign.
The first [recovery pilot R1](docs/RECOVERY_PILOT_R1_DECISION.md) was rejected
at its no-fault baseline: 0/15 packets despite healthy processes and targets.
No interruption was injected. An approved UE restart restored 15/15 packets;
that restoration does not make the six-trial pilot complete. A bounded
reconnect-path investigation is the current engineering gate. The separately
frozen [reconnect R1](docs/RECONNECT_R1_DECISION.md) then reproduced the failure
in both eight-second link-drop trials: post-rollback delivery was 0/15, versus
15/15 in both no-fault controls, and approved UE restarts restored 15/15.
Independent audit passed all four trials, 280 commands and 30 samples. This
validates failure reproduction, not a network fix; the recovery gate stays open.

The separately built and pinned [R2 candidate](docs/RECONNECT_R2_BUILD_DECISION.md)
was then tested under a frozen comparison. [The R2 decision](docs/RECONNECT_R2_DECISION.md)
is **not accepted**: official drops returned 0/15, while the first derived drop
returned 14/15 with Service Accept, failing the required 15/15 endpoint. The
comparison stopped at six of eight assignments without discarding the first
lost packet. The official image and fresh 15/15 service were restored.
Independent integrity audit replayed 480 commands and 48 samples; 240 tests
plus 19 subtests pass. These do not establish a successful network fix or TNSM
readiness. The subsequent [source diagnosis](docs/RECONNECT_PACKET_DIAGNOSIS.md)
verified idle-payload non-retention in 60 exact-method fixture cases, with
251 tests plus 22 subtests passing. This is consistent with R2's first-packet
loss, not direct packet localization or a network fix. A separately frozen
instrumented diagnostic is next; no new long campaign is running.

Environment Deviation D1 records six unrelated containers that appeared on
separate Docker networks during the run. No network overlap was observed, but
the host was not CPU/memory/scheduler exclusive; CPU-saturation and timing
results therefore carry an explicit shared-host contention limitation.

The separate BRACE computation microbenchmark uses deterministic fixture
contrasts: median calibration time was 3.024 ms at 5,000 blocks and median
proposal overhead was 2.662 microseconds. These are local-host computation
measurements, not network, radio, hardware, or operator scalability evidence.
See [docs/PHASE7_NOVELTY_AUDIT.md](docs/PHASE7_NOVELTY_AUDIT.md) and
[docs/TNSM_CLAIM_MATRIX.md](docs/TNSM_CLAIM_MATRIX.md) for the allowed and
forbidden paper claims; [docs/ROADMAP.md](docs/ROADMAP.md) tracks current
evidence.

## Setup

From this directory in PowerShell:

```powershell
python -m venv .venv --system-site-packages
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Inspect the local environment:

```powershell
.\run.ps1 doctor
```

Build, start, and capture the isolated software stack:

```powershell
.\sandbox\run.ps1 build
.\sandbox\run.ps1 up
.\sandbox\run.ps1 capture-stack
.\sandbox\run.ps1 intervention
```

See [docs/SANDBOX.md](docs/SANDBOX.md) for boundaries, exact checks, evidence
verification, and the retained Debian 12 compatibility failure.

Run the day-one safety demo:

```powershell
.\run.ps1 demo
```

Validate an intervention log:

```powershell
.\run.ps1 validate-log .\examples\interventions.example.jsonl
```

Adapt a measured evidence bundle to lossless long-form telemetry:

```powershell
.\run.ps1 adapt-telemetry `
  .\evidence\sandbox\20260824T045620Z-intervention `
  .\artifacts\telemetry.jsonl
```

Run the localhost-only evidence dashboard:

```powershell
Set-Location .\dashboard
npm ci
npm run dev
```

The dashboard is read-only and contains no actuation endpoint. See
[docs/PRODUCT.md](docs/PRODUCT.md) for its evidence and safety boundaries.

## Research question

> Can an intervention-trained network digital twin estimate the effects of
> candidate remediation actions and safely abstain or escalate under
> uncertainty, reducing SLA violations without increasing harmful actions?

## Repository map

```text
config/                 Versioned action and safety policy
dashboard/              Local read-only evidence product
docs/                   Research protocol and execution roadmap
evidence/               Append-only measured logs and hash manifests
examples/               Valid, synthetic contract examples
sandbox/                Official component locks and isolated 5G SA stack
src/safetwin5g/         Contracts, safety gate, store, and CLI
tests/                  Executable correctness checks
PROJECT_LOCK.md         Fixed scope, hypotheses, and change-control rule
```

## Remaining gates

Hardware measurement, independent operator validation, and publication require
new access or authorization and remain pending. Any new local research cycle
must be separately preregistered; the completed negative Phase 6 decision will
not be tuned into a positive result. No algorithmic result will be called a
live-network result.
