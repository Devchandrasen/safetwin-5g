# Reconnect R2: partial resumption, recovery gate not accepted

Date: 2026-09-05. Commit `59d57d2` froze the runner, independent auditor and
[execution contract](RECONNECT_R2_EXECUTION.md) before this comparison. The
[R2 protocol](RECONNECT_R2_PROTOCOL.md), image lock and endpoint were not changed
after observation. **Six of eight assignments executed. The first derived-image
drop returned 14/15 packets, not the required 15/15, so execution stopped.**
`protocol_execution_valid=false` and `network_fix_validated=false`.

## Measured observations

The hash-manifested run is
`evidence/engineering/20260905T082014Z-reconnect-r2`. All six preparation
baselines had fresh registration/PDU state and 15/15 packets. Post windows
were measured before any post-trial UE restart.

| Assignment | Baseline packets | Post packets | Post-observation restoration |
| --- | --- | --- | --- |
| Official control-before | 15/15 | 15/15 | No drop restoration needed |
| Official drop-a | 15/15 | 0/15 | Approved UE restart, 15/15 |
| Official drop-b | 15/15 | 0/15 | Approved UE restart, 15/15 |
| Official control-after | 15/15 | 15/15 | No drop restoration needed |
| Derived control-before | 15/15 | 15/15 | No drop restoration needed |
| Derived drop-a | 15/15 | 14/15 | Approved UE restart, 15/15 |
| Derived drop-b | Unexecuted | Unexecuted | Unexecuted |
| Derived control-after | Unexecuted | Unexecuted | Unexecuted |

The three derived-drop post windows returned 4/5, 5/5 and 5/5. Raw command
393 contains replies for ICMP sequences 2 through 5, but none for sequence 1.
Commands 398 and 403 contain the next two clean windows. The first packet is
both the traffic stimulus and an endpoint observation under the frozen
contract. It cannot now be discarded as warm-up or replaced with a retry.

The derived drop's owned qdisc interval was
08:25:44.146184254 to 08:25:52.149381156 UTC. UE logs in command 410 show radio
link failure, a returning signal, a traffic-triggered Service Request at
08:25:57.514, and Service Accept at 08:25:57.517. gNB logs in command 409 show
Initial Context Setup at 08:25:57.516 without the previous AMF-selection
failure. These logs and the returned packets support partial automatic
service resumption in this one trial. They do not override the lost packet,
prove where it was lost, establish a new PDU session, or estimate recovery
reliability or superiority. No per-packet internal trace or packet capture
localizes that loss. The cause of the original spontaneous radio-link loss
also remains unresolved.

## Independent integrity audit and rollback

The independent auditor replayed 480 commands, 48 samples and 10 scope
snapshots, including the actual packet counts, exact assignment prefix,
source/image hashes, approval timing, scoped mutations and final rollback.
Its `audit_passed=true` means the stopped comparison is faithfully preserved;
it does not mean the eight-trial protocol or network-fix endpoint passed.
The stop reason is `candidate_recovery_not_verified`. No replacement trials
were added and the final two assignments remain unexecuted.

All three eight-second UE eth0 drop intervals ended with the owned `7157:`
qdisc removed and `noqueue` observed. There were 24 recorded restart commands:
seven core, seven gNB and ten UE restarts. These comprise six fixed trial
preparations, three post-drop UE restorations and the final three-component
reset. Two additional scoped Compose replacements switched only the gNB to
the derived image and back to the official image. They were not hidden retries.

The candidate was temporarily applied, then rolled back. The final official
gNB image is
`sha256:13705fc29922cf019e8c7992b5b04b9c6c584d3848d29689f1d3db64334ae725`.
The tested derived image is
`sha256:2a5c01c503927c44a6b45f8b074491ac64a42fc3a444ea2af0a8cbe5df8e537e`.
The patch, unchanged UE binary and original source provenance are recorded in
[the separate build decision](RECONNECT_R2_BUILD_DECISION.md) and
`config/experiments/reconnect-r2-images.json`. The official lock was not replaced.

Final rollback completed at 08:26:57.882503 UTC with fresh registration/PDU
state, three clean five-packet windows, the official image and scope checks.
No rollback error or admission-budget overrun was recorded. These observations
do not measure continuous availability beyond the captured windows or an exact
MTTR. Approval was recorded before mutations under the user's standing scoped
sandbox authorization, not a new operator signature. No live action occurred.

The wrapper transcript and manifest are at
`evidence/engineering/20260905T082013Z-reconnect-r2-runtime`. Sleep inhibition
was enabled and cleared. Its child-exit-code field is blank and cannot support
experiment acceptance; the decision uses the durable raw commands and audit.

## Verification and next gate

`evidence/verification/20260905T083007Z-reconnect-r2` records 240 tests and
19 subtests passing, the unchanged statistical lock, independent source/build
audit and independent network integrity audit. Five new retained-evidence
regressions reject promoting this stopped prefix to a fix, relabelling the
lost packet as clean, or treating Service Accept alone as packet recovery.
The earlier post-run verification at `20260905T082710Z-reconnect-r2` is retained.
The final rerun at `20260905T083704Z-reconnect-r2` repeats all four verification
checks with 240 tests and 19 subtests passing.
Passing software tests do not promote the failed measured endpoint.

The current recovery roadmap item stays open. Next perform a bounded,
read-only investigation of the pinned UE/gNB traffic-resumption path and the
retained packet/log sequence. If a further correction or instrumented sandbox
experiment is justified, freeze it as a separate versioned protocol with
approval, independent audit and rollback before execution. Do not rerun R2
until lucky, weaken its 15/15 criterion or start another 675-unit campaign.
UPF watchdog and repeated-interruption recovery remain unvalidated.

This is engineering `sandbox-measured` evidence with `simulated` radio; source
fixtures remain `fixture`. It is not confirmatory BRACE data, hardware-measured,
operator-validated, a demonstrated novelty result or TNSM readiness. D1's
co-resident-host limitation and P1's historical collection-gap disclosure remain
unchanged. The rejected 675-unit campaign is not salvaged, pooled or retuned;
there is still no dataset-v2a release or confirmatory BRACE analysis. Phase 6
remains a locked negative result. External-authority gates remain pending.
