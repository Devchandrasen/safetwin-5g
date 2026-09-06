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
instrumented diagnostic now has a [verified prebuild source freeze](docs/RECONNECT_R3_SOURCE_FREEZE.md):
65 parser cases, 61 NAS cases per mode and 272 tests plus 32 subtests pass.
The [R3 image build](docs/RECONNECT_R3_BUILD_DECISION.md) now passes real-header
compilation and a versioned independent audit (306 tests plus 32 subtests).
At that build checkpoint it had not been applied to a running service. The separate
[R3 execution contract](docs/RECONNECT_R3_EXECUTION.md) is now fixture-verified
with 339 tests and 122 subtests. An independent replay covers 354 synthetic
commands, 33 samples and eight scope snapshots; negative fixtures check failed
baseline, missing trace and partial image-switch rollback. Two earlier
read-only preflight failures and their source versions remain retained; the
corrected preflight passed with mutations disabled. Those were implementation
checks, not a measured R3 network result or recovery validation.

The subsequent [R3 diagnostic attempt](docs/RECONNECT_R3_DECISION.md) stopped
during the first no-fault baseline: 5/5 replies returned, but early required
trace records were absent. Zero exposures ran; the remaining assignments were
unexecuted. The source IP changed outside the fixed trace filter after UE-only
reset, and later read-only probes verified a host/container clock mismatch.
Clock clipping is supported, not a recovery of the missing historical entries.
Both official images and final 15/15 service were restored. A separate
observation audit replays 131 commands, six samples and five scopes while the
original complete-protocol auditor still rejects the run. There are 355 passing
tests and 132 subtests at that checkpoint. The separate
[R4 collection software gate](docs/RECONNECT_R4_COLLECTION_DECISION.md) now
passes 381 tests, 171 subtests and eleven verification checks. Its bounded
prefix-based log collector avoids host-time filtering and checks source
eligibility explicitly. Fourteen retained cases are **fixture-only**, not new
network evidence. The separate [R4 execution software gate](docs/RECONNECT_R4_EXECUTION_DECISION.md)
now passes **398 tests, 200 subtests and twelve verification checks**. Its
15-source lock covers the byte/time-bounded Windows adapter, mandatory approval,
fresh-PDU/telemetry/rollback integration and independent whole-protocol replay.
Seventeen retained protocol cases and seven local subprocess cases are still
**fixture** evidence. Failed cleanup and official restoration remain negative;
the failed initial software gate and exact source snapshot are preserved.
The subsequent once-only [R4 attempt](docs/RECONNECT_R4_DECISION.md) was rejected
before baseline or exposure by wall/QPC consistency flags. Its 55 command
records include 54 Docker commands and one Git command; zero valid assignments
or packet samples were collected. Automatic official-image/reset cleanup ran,
but its original rollback-verification flags remain false. A separate later
read-only observation verifies both official images, fresh PDU, neutral
telemetry and 15/15 packets. This does not retroactively accept R4. A later
1,000-sample clock probe did not reproduce the failure; the reported 15.625 ms
Python wall-clock resolution exposes a compatibility gap with the 1 ms guard,
not proof of a historical clock adjustment. Independent observation replay,
425 tests, 200 subtests and twelve checks pass. Next is a prospective
software-only clock-source/bracket gate. That separate
[R5 clock gate](docs/RECONNECT_R5_CLOCK_DECISION.md) now passes 493 tests,
200 subtests and twelve checks, with 37 retained synthetic cases and one
separate 64-read native local-host clock observation. It is not integrated
with a network runner and does not prove R4's historical cause or recovery.
Next is the separately frozen R5 execution-integration fixture gate. The parent
recovery gate and TNSM disposition remain open/no-go respectively.
The first [R5 clock-journal component](docs/RECONNECT_R5_JOURNAL_DECISION.md)
now passes 563 tests, 200 subtests and 21 checks, with ten retained synthetic
cases. It reserves clock capacity for cleanup and verifies exception-isolated
no-I/O callbacks; it does not implement the new bounded command runner or
prove official rollback. Full execution integration remains pending.
The [R5 owned-client capture component](docs/RECONNECT_R5_PROCESS_DECISION.md)
now passes 596 tests, 200 subtests and 30 checks. Its 21 retained local-process
cases include clock failure, bounded cleanup, byte saturation and independent
shared-envelope replay. This is fixture evidence, not a network trial; the
host/collection/runner and whole-protocol rollback gate remained pending at
that checkpoint. The separate [R5 host component](docs/RECONNECT_R5_HOST_DECISION.md)
now passes 649 tests, 200 subtests and 36 checks, with 27 retained synthetic
host/power cases. Its persistent attempt receipt, same-domain admission and
independent owned-handle cleanup remain fixture evidence, not measured sleep
inhibition or service recovery. The separate
[R5 collector component](docs/RECONNECT_R5_COLLECTION_DECISION.md) now passes
713 tests, 200 subtests and 47 checks with 38 synthetic cases. Durable unique
packet reservations, exact-prefix accounting and same-clock window closure
remain fixture evidence. Failed durability and incomplete packets are not
positive recovery. A complete window needs 16 new points; the full four-trial
inventory, runner and independent whole-protocol rollback gate remain pending.
The separate [R5 timing/inventory component](docs/RECONNECT_R5_BUDGET_DECISION.md)
now passes 766 tests, 200 subtests and 41 checks with 32 synthetic cases.
Health/settling deadlines and adversarial independent replay are fixture-only.
The prospective cleanup count is 216 points; the conditional prefix-plus-cleanup
bound is 984 of 1024. Its unpruned normal upper envelope exceeds 768, so this
does not guarantee four completed trials. Both development failures are
preserved. The actual runner, approval binding and whole-protocol official
rollback audit remain pending; the parent recovery item stays open.
No new long campaign or TNSM-readiness claim is enabled.

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
