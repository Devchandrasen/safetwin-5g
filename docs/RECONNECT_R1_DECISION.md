# Reconnect R1: failure reproduced, fix not yet validated

Decision date: 2026-09-05. The four-trial engineering reproduction passes its
independent execution audit and reproduces the preregistered failure pattern
in both impaired trials. It does **not** pass a network-fix, interruption-pilot,
long-campaign, BRACE comparison or TNSM gate.

## Frozen design and measured evidence

Commit `a37c0df` froze [the protocol](RECONNECT_R1_PROTOCOL.md), configuration,
runner, independent raw-command auditor and software checks before execution.
The pre-execution verification passed 214 tests and 19 subtests. No thresholds,
source pins, network source code or statistical lock were changed after seeing
the experiment. Exactly four assigned trials ran, with no substitutions.

Run: `evidence/engineering/20260905T062044Z-reconnect-r1`.
The command record begins at 06:20:44 UTC and the terminal summary is at
06:24:47.843685 UTC, within the 15-minute admission budget.

| Trial | Baseline packets | Post-rollback packets | Approved restoration packets |
|---|---:|---:|---:|
| control-before | 15/15 | 15/15 | not needed |
| drop-a | 15/15 | 0/15 | 15/15 after UE restart |
| drop-b | 15/15 | 0/15 | 15/15 after UE restart |
| control-after | 15/15 | 15/15 | not needed |

Both controls had an eight-second wait and no impairment. Both drop trials
installed 100% loss on only the SafeTwin UE's eth0 egress, using owned handle
`7157:`. The in-container transcripts establish intervals of 8.040857 and
8.003412 seconds respectively. Each shell's EXIT trap removed its qdisc;
the recorded state returned to the original noqueue root before post probes.
A fixed five-second settling interval preceded all post windows. These are
whole-UE-egress interruptions, not selective radio-only or physical RF faults.

Every trial used the preregistered fresh core/gNB/UE preparation sequence.
The run therefore contains four core restarts, four gNB restarts and six UE
restarts, not just the two post-failure restoration actions. Fresh registration
and PDU establishment were verified in all baselines and both restorations.
The two UE restoration steps took 14.688 and 14.641 seconds, including health
waiting and three packet samples. These are not exact MTTR estimates. The
full-reset fallback was not needed and is not validated by this run.

The independent auditor replays all **280 commands and 30 samples**, checks
source/file hashes, exact isolated container inventory, official source labels
and image digests, approval timing/scope, restart ordering, qdisc rollback,
exposure/settling intervals, raw packet counts and log markers. It accepts both
`protocol_execution_valid` and `reconnect_failure_reproduced`.
Initial post-run verification is retained at
`evidence/verification/20260905T062456Z-reconnect-r1`.
Retained-evidence regressions, including hash-consistent packet relabelling,
claim promotion and omitted-control rejection, pass with 219 tests and 19
subtests at `evidence/verification/20260905T062820Z-reconnect-r1` (the earlier
219-test verification at `20260905T062637Z-reconnect-r1` is also retained).
Those tampered-copy tests are fixtures, not additional network trials.

The runtime transcript and its SHA-256 manifest are in
`evidence/engineering/20260905T062044Z-reconnect-r1-runtime`. Sleep inhibition
was enabled and cleared. The wrapper again printed a blank `CHILD_EXIT_CODE`;
its parent exit status is not used as experiment acceptance. The independent
terminal artifact audit supplies that decision. No experiment process remained
after completion. Final service was restored.

## What the reproduction establishes

In both impaired trials, the new signal after rollback acquired a new gNB UE
context. The UE then sent a Service Request for pending uplink data. gNB logged
AMF-selection failure, missing AMF context and missing PDU-session resources;
all 15 post-rollback probe packets were lost. The two controls returned all 15
packets and did not show those error markers. A UE restart created fresh
registration/PDU state and restored service in each impaired trial.

For example, drop-a records link loss at 06:22:07.596 UTC, new signal at
06:22:14.644, and Service Request plus AMF-selection failure at 06:22:20.022.
The raw records preserve the full chronology and both repetitions.

This reproduces the **behavioural failure path**, consistent with the pinned
[Initial NAS slice extraction](https://github.com/aligungr/UERANSIM/blob/6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156/src/gnb/ngap/nas.cpp)
and [exact AMF SST matching](https://github.com/aligungr/UERANSIM/blob/6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156/src/gnb/ngap/nnsf.cpp)
candidate. It does not experimentally isolate that source condition from all
other conditions in service resumption: no source patch or internal-variable
instrumentation was applied. The initial spontaneous radio-link loss in the
historical campaign remains unexplained. Two repetitions do not establish a
population failure rate or prove the cause of every historical failed unit.

The investigate skill kept reproduction ahead of patching. No global skill
upgrade, preference change or durable memory update was needed for this task.

## Next bounded step and unchanged gates

Keep the recovery roadmap item open. Trace absent-slice handling through AMF
selection and service resumption. If a minimal local correction is warranted,
freeze a separate protocol, exact patch/source hashes and a separately named
derived image before testing it against the unchanged official-image control.
Test initial registration, reconnect, PDU restoration and actual packet
delivery, including fail-closed incompatible/ambiguous selection cases. Do not
silently replace the official source pin or interpret an image build as a fix.
Keep failed correction attempts. Only verified correction evidence can justify
returning to the bounded interruption/rollback pilot.

The original R1 interruption pilot remains rejected, with zero injected UPF
faults; its watchdog and repeated-interruption paths remain unvalidated. The
original 675-unit campaign remains rejected, with no dataset-v2a release or
confirmatory BRACE analysis. P1 collection-gap and D1 shared-host limitations
remain in force. No additional long campaign is running.

All interventions are sandbox-measured; radio is simulated. Standing user
authorization was recorded before actions and is not a fresh operator
signature. Live actuation remains blocked, unrelated containers were outside
the action scope, and hardware/operator/publication work needs new authority.
`network_patch_applied`, `long_campaign_ready`, `confirmatory_data` and
`TNSM_ready` are all false.

DEBUG REPORT

- Symptom: packet service remains unavailable after simulated link restoration.
- Root cause status: repeated AMF-selection/missing-PDU failure path observed;
  the absent-slice source condition remains a correction candidate, not a
  uniquely isolated source cause.
- Fix: no network fix applied or claimed; approved UE restarts restored service.
- Evidence: four fixed trials, 280 replayed commands, 30 replayed samples,
  exact qdisc rollback and two successful final UE restorations.
- Regression: `tests/test_reconnect.py` and `tests/test_reconnect_evidence.py`.
- Related: recovery pilot R1, Phase 7 recovery rejection R1, D1 and P1.
- Status: DONE_WITH_CONCERNS for the bounded reproduction; fix and recovery
  acceptance remain pending.
