# Recovery pilot R1: rejected at the no-fault baseline

Decision date: 2026-09-05. The six-trial pilot is **not accepted**. The runtime
correctly stopped after the first trial; no UPF fault or watchdog was started.
This does not validate the interruption or watchdog paths in the real sandbox.

## Frozen protocol and measured result

Commit `272b2e3` froze the protocol, six assigned holds, runtime and independent
raw-command auditor before execution. The software verification passed 200
tests and 19 subtests; these are software checks, not pilot acceptance.

The run `evidence/engineering/20260905T051750Z-recovery-pilot-r1` contains:

| Window | Packets received / transmitted | Result |
|---|---:|---|
| Three pre-fault baseline samples | 0 / 15 | rejected before injection |
| Three primitive-cleanup samples | 0 / 15 | restoration failed |
| Three samples after approved UE-only restart | 15 / 15 | service restored |

In all nine samples, UPF was running, qdisc was neutral, no stress worker was
observed, and all three Prometheus targets were up. The UE restart step took
14.015 seconds, including health waiting and its three verification samples.
This is not an exact MTTR measurement or an average over interruption trials.
Only one of six planned trials ran, and that no-fault control failed. Its
successful final restoration does not reverse the failure. The runner retained
64 commands, all nine samples, approval, container identities, versions, source
hashes, logs, timestamps, summary and manifest.

The independent acceptance auditor rejects `incomplete pilot`. The separate
read-only diagnosis at
`evidence/engineering/20260905T052348Z-recovery-pilot-r1-diagnosis` verifies the
manifest, all command-output hashes and raw samples, confirms zero injected
faults and exactly one approved UE restart, and retains extended container
history plus pinned upstream sources and their licence. It does not run BRACE,
comparators, hypothesis tests or the positive manuscript gate.
After adding retained-failure regressions, 203 tests and 19 subtests passed at
`evidence/verification/20260905T052550Z-recovery-pilot-r1`. The frozen
statistical-source lock still passes. This verifies rejection and preservation,
not completion of the unexecuted five trials.

The sleep-inhibition wrapper reported that inhibition was enabled and cleared.
Its `CHILD_EXIT_CODE` field was blank, a retained wrapper limitation, so the
parent shell exit status is not used as the experiment's acceptance signal.
The runtime transcript is in
`evidence/engineering/20260905T051800Z-recovery-pilot-r1-runtime`; the directory
name is a label, not the start timestamp. Use the recorded command timestamps.

## Investigation, not an unverified network patch

The extended history narrows the failure sequence:

1. At 04:04:14 UTC, initial registration and PDU establishment succeeded.
2. At 04:14:49, a simulated radio-link failure occurred. gNB assigned a new UE
   context identifier; subsequent cell-selection failures are retained.
3. At 04:22:40, UE sent a Service Request. gNB logged AMF selection failure and
   missing AMF context; there was no successful replacement PDU setup.
4. During the 05:17:51 baseline, gNB rejected uplink packets for the new UE
   identifier because its PDU-session resource did not exist.
5. At 05:18:15, the approved UE restart completed fresh registration and PDU
   establishment. Its address became 10.45.0.3, and all 15 probe packets returned.

In the exact pinned UERANSIM revision, [Initial NAS processing](https://github.com/aligungr/UERANSIM/blob/6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156/src/gnb/ngap/nas.cpp)
initializes requested slice type to -1 and extracts a slice from a Registration
Request. [AMF selection](https://github.com/aligungr/UERANSIM/blob/6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156/src/gnb/ngap/nnsf.cpp)
requires exact slice-type equality. **Source-inspection inference:** a Service
Request on a new context can retain -1, so it cannot match advertised SST 1.
This is consistent with the recorded selection failure, not a packet-level
reproduction of the full mechanism. The [GTP uplink path](https://github.com/aligungr/UERANSIM/blob/6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156/src/gnb/gtp/task.cpp)
explicitly drops packets when that UE/PDU resource is absent. None of these
observations establishes why the initial simulated radio link was lost.

An optional read-only `nr-cli ... --exec status` probe did not return. The
exact experiment-owned CLI process (container PID 301) was identified and
terminated; the UE process was not terminated. Four duplicate CLI discovery
entries were observed after repeated container restarts. CLI output is not
used for the service acceptance decision.

The investigate skill kept diagnosis ahead of patching. Global skill upgrades,
new checkpoint preferences and durable memory updates were not part of this
project change. No networking source, image, protocol threshold or frozen
statistical file was changed after observing this failure.

## Next bounded gate

Keep the recovery roadmap item open. Before another interruption pilot,
preregister a small link-loss/re-establishment engineering reproduction and
its approved restoration. First reproduce the Service Request selection path
and check the source-level candidate. If a local upstream patch is necessary,
give the derived image a new source/patch hash and validate registration,
re-establishment and packet delivery in a separate engineering protocol.
Do not silently replace the official pin, retry until a run happens to pass,
pool failed and successful runs, or start another 675-unit campaign.

DEBUG REPORT

- Symptom: healthy process/target flags coexisted with 100% packet loss.
- Root cause: missing gNB PDU context observed; the reconnect selection path is
  a source-supported candidate, while initial radio-link loss is unresolved.
- Fix: no upstream fix claimed; the existing fail-closed guard prevented fault
  injection, and its approved UE restart restored service.
- Evidence: nine independently replayed samples, zero faults, one UE restart.
- Regression: `tests/test_recovery_pilot_evidence.py` locks this negative result.
- Related: historical Phase 7 recovery rejection R1, D1 shared-host limitations.
- Status: DONE_WITH_CONCERNS for bounded diagnosis; recovery acceptance pending.

All intervention evidence is sandbox-measured with simulated radio. The static
source counterexample is fixture-level reasoning, not a second network trial.
No TNSM superiority, long-campaign reliability, hardware, operator or live
actuation claim is permitted. The original 675-unit data rejection and P1
collection-gap disclosure remain unchanged.
