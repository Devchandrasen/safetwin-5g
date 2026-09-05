# Phase 7 recovery rejection R1

**Decision date:** 2026-09-05. **Disposition:** no-go for dataset release,
confirmatory policy analysis, and a positive TNSM manuscript from this campaign.

## Evidence and scope

Collection completed at 2026-09-05 03:47:04 UTC with 675 files in 135 five-action
blocks and 540 approved experimental mutations. The source bundle is
`evidence/scenarios/20260901T030631Z-phase7-campaign-v2a`. Its historical
manifest and summary remain byte-for-byte intact, including their original
`passed: true` flags. Those flags certify only the old runner checks and are
superseded for acceptance by this rejection and the frozen dataset gate.

The original command/environment prefix and 546 pre-pause unit files passed
the independent P1 preservation audit. The existing campaign auditor also
passed, but the dataset builder immediately rejected the bundle because
`all_recovery_states_clean` and `mttr_not_censored` were false. No dataset
release directory was created. No BRACE model, comparator, hypothesis test,
or manuscript gate based on invented downstream artifacts was run.

The diagnostic at
`evidence/decisions/20260905T040400Z-phase7-recovery-no-go` records:

| Observation | Count |
|---|---:|
| Units with failed baseline packet delivery | 581 / 675 |
| Units with failed recovery packet delivery | 582 / 675 |
| Failed recovery samples | 1,746 / 2,025 |
| Right-censored MTTR records | 582 / 675 |
| MTTR observed | 61 / 675 |
| MTTR not triggered | 32 / 675 |

The first affected unit in collection order is unit 91, in the train split,
on September 1. All three baseline and recovery samples at that unit report
100% observed loss while the configured loss is zero, UPF is running, and no
stress worker remains. Failure therefore predates the requested laptop pause.
The rejected data must not be repaired by discarding failed units, imputing
recovery, changing the one-percent threshold, or combining surviving prefixes.

## Confirmed validation defect

`phase7_runner._is_clean` checked configured qdisc loss, UPF process state and
stress-worker count, but omitted observed packet loss. The frozen Phase 6
runner and Phase 7 dataset gate include observed packet loss. This omission
allowed a broken user plane to pass both baseline and recovery checks and
continue collecting. The campaign auditor reused that same predicate, so it
was not independent on this material condition. The original fake backend
also omitted packet-loss telemetry and could not expose the defect.

Operational monitors checked progress, errors and file growth under the
procedural outcome seal; those checks never established service recovery.
Earlier progress statements implying verified end-to-end recovery were too
strong. The dataset validation skill prompted checking actual service
measurements rather than accepting the runner flags.

## Network diagnosis and safe recovery

At terminal inspection, qdisc was neutral, UPF was running and no CPU stress
worker remained, yet a fresh five-packet ping returned zero packets. Open5GS
logs contain PFCP heartbeat timeout, de-association and re-association events
during the interruption scenarios. These observations support session-state
loss as a candidate mechanism; they do not establish the unique root cause
of every failed unit. UPF process resumption alone is insufficient evidence of
a restored PDU user plane.

Restarting only the three SafeTwin components Open5GS, gNB and UE restored
10.45.0.2/24, five of five pings and all three Prometheus targets. Logs before
and after recovery are retained in
`evidence/environment/20260905T015600Z-phase7-resume-runtime`.
No unrelated container was changed.

## Guard correction and next gate

The execution guard now requires measured packet loss in [0, 1] percent,
rejects missing/non-finite values, blocks fault injection on an invalid
baseline, and requires all recovery samples before setting cleanup verified.
The campaign stops after any failed unit. The auditor separately checks
baseline and recovery packet delivery. Regression cases cover neutral fault
settings with 100% loss, invalid baselines, missing samples and invalid metrics.

The frozen dataset, BRACE implementation, analysis code, partitions, thresholds
and statistical lock are unchanged. Historical runner source is available at
commit `8dc5b68`, and the source summary retains its hashes. Running the corrected
audit against this historical bundle must reject it.

Before another confirmatory campaign, validate actual PDU recovery under
repeated interruption scenarios in a bounded, separately labelled engineering
pilot. An explicit reset/rollback protocol, logged timing and a stable
user-plane baseline are required. The 675-unit collection is not restarted
solely because the guard tests pass.

P1 (four-day pause/restart), D1 (shared-host contention), simulated radio,
single-host sandbox, absent hardware/operator validation, and the procedural
seal remain limitations. This is an operational dataset rejection, not evidence
that BRACE wins or loses against a baseline.
