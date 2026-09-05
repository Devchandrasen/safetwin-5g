# Reconnect first-packet diagnosis: source mechanism verified, no network fix

Date: 2026-09-05. This is a read-only follow-up to the rejected
[R2 comparison](RECONNECT_R2_DECISION.md), not an amendment or retry of it.
The 14/15 observation remains a failed 15/15 recovery endpoint. No service was
restarted, no image installed or built, and no new network trial was executed.

## Confirmed source mechanism

The pinned UERANSIM `NasSm::handleUplinkDataRequest` forwards an eligible active
session's payload only in `CM_CONNECTED`. In the other branch it sets an
uplink-pending flag and calls `handleUplinkStatusChange(psi, true)`, but neither
stores nor forwards the payload. The status handler requests the service
procedure and a mobility-management cycle, not a payload replay. The caller
owns the input message locally, so that payload has no retained queue entry
when handling returns. These are properties of the pinned source, not claims
about all 5G implementations. See the official
[uplink method](https://github.com/aligungr/UERANSIM/blob/6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156/src/ue/nas/sm/sap.cpp#L50),
[status handler](https://github.com/aligungr/UERANSIM/blob/6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156/src/ue/nas/sm/resource.cpp#L62)
and [NAS caller](https://github.com/aligungr/UERANSIM/blob/6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156/src/ue/nas/task.cpp#L53).

The App task transfers TUN payload ownership to NAS; NAS calls the uplink
method; its connected branch moves the payload to RLS. Its idle branch only
initiates resumption. A later connected packet can clear the pending flag and
be delivered, but it does not replay the earlier payload. The retained R2 logs
show the same ordering: pending-data/Service Request, Service Accept, and then
replies starting at ICMP sequence 2. This is a source-supported explanation
consistent with that observation, not a retrospective per-packet trace.

The same source has an explicit TODO that CM state alone does not establish
radio-resource readiness. The downstream gNB GTP path also rejects a packet
when the PDU resource is missing. These are reasons not to propose a generic
delay, unbounded buffer, early flush on CM state alone, ping warm-up exclusion,
or retry-until-success as a validated correction. Absence of the corresponding
error log in R2 does not prove that every downstream stage was lossless.

## Executed source fixture and provenance

`evidence/engineering/20260905T091635Z-reconnect-packet-diagnosis` preserves
12 upstream files, including callers, status/procedure handling, RLS, gNB GTP,
context handling and licence. Each was read from the retained R2 build's
immutable source commit and independently fetched from its official GitHub
commit URL; all 12 byte comparisons and SHA-256 checks pass. The only retained
source-tree modification is the previous gNB `nnsf.cpp` patch. The running UE
binary still matches the unchanged official SHA-256 in the R2 image lock.

The two production method bodies, uplink handling and status change, are
extracted verbatim into a C++ fixture. An independent auditor reconstructs
them using adjacent method boundaries rather than the collector's brace scan
and checks the exact compiler input hash. There are 60 passing fixture cases:

- 56 combinations of six accepted MM substates plus one rejected stand-in,
  two CM states, two session states and two initial pending flags;
- an idle first packet followed by a connected second packet, where only
  packet 2 reaches the sink;
- three idle inputs followed by a connected input, with no idle-burst replay;
- a callback that immediately switches CM state, which still does not make
  the already-selected idle branch forward its input;
- connected forwarding without any model of downstream radio readiness.

The fixture uses explicit test doubles: a string for byte ownership, a sink
for the RLS task, counters for MM callbacks and controlled state transitions.
It does not execute the complete NAS/RRC scheduler, actual upstream ABI,
network packets, PDU resource establishment, or timer behavior. Its label is
`fixture`, not new `sandbox-measured` evidence. No UE correction is implemented.

A deliberately incorrect fixture changes the connected predicate to true.
It fails the forwarding assertion after two completed matrix cases, exit 42.
This test-of-test shows that the fixture detects the branch distinction; it
is not a proposed patch, image, network action or positive result.

Compilation and execution use an ephemeral container with no network, host
mounts, ports, devices or capabilities, a read-only root, one CPU, 256 MiB
memory, a bounded 32 MiB temporary directory and 25-second in-container
timeout. The outer command timeout is 35 seconds. Only the temporary directory
allows execution; nothing is installed in the running UE or gNB. Before/after
container IDs, image IDs, start times and restart counts match the official
running components. The independent audit passes 24 commands and the complete
source/fixture inventory, while retaining all negative network claim flags.

## Retained tooling failure and verification

The first capture at
`evidence/engineering/20260905T091508Z-reconnect-packet-diagnosis` stopped after
the fixture compiled but execution returned 126 with
`/tmp/packet-fixture: Permission denied`. Its manifest, partial command log and
`capture_completed=false` remain unchanged. The collector's only adjustment
was the explicit `exec` option on its isolated temporary directory, as supported
by [Docker's tmpfs options](https://docs.docker.com/engine/storage/tmpfs/).
The successful second capture is separate. A regression reconstructs the
first collector's exact hash by reversing that one option change. This is a
tooling correction, not another network trial or a rewritten failed result.

`evidence/verification/20260905T091926Z-reconnect-packet` records:

```text
251 passed, 22 subtests passed in 6.27s
```

The independent packet-diagnosis audit, prior R2 source/build audit, prior R2
network-integrity audit and statistical source lock all pass. R2 still reports
`protocol_execution_valid=false` and `network_fix_validated=false`. New
regressions reject claim promotion, omitted sources, altered official hashes,
wrong compiler inputs, added capabilities, service restarts and image drift.

## Next bounded gate and debug report

The investigate skill kept source tracing and hypothesis verification ahead
of a patch. There was no upstream edit scope to unlock: edits are confined to
new diagnostic tooling, tests, evidence and status documentation. Global tool
upgrades, preference changes and durable memory writes were outside this task.
The useful learning is retained here: a Service Accept log cannot imply replay
of a payload that NAS never retained.

DEBUG REPORT

- Symptom: the first derived R2 drop returned 14/15 packets, starting at ICMP 2.
- Source cause: the eligible idle NAS branch signals pending data without
  retaining/forwarding the input; two exact production methods reproduce this
  in a controlled fixture.
- Fix: none applied to UE/gNB or recovery endpoints.
- Evidence: 12 official source matches, 60 exact-method cases, a failing
  negative control, 24-command audit, and 251 tests plus 22 subtests.
- Remaining uncertainty: historical per-packet loss location, real scheduler
  and PDU-resource readiness, and the original spontaneous link-loss cause.
- Status: DONE_WITH_CONCERNS for source diagnosis only; recovery remains open.

Next freeze a separately versioned, bounded instrumented resumption experiment
before any new image build or sandbox mutation. It should identify packet
sequence and state at NAS ingress, the idle/forward branches and relevant RLS/
gNB boundaries, retain all first packets and controls, and distinguish trace
completeness from recovery success. Instrumentation overhead is a limitation,
not a reason to drop observations. Source/patch/fixture audits, exact image
pins, recorded scoped approval and verified official-image rollback are required
before execution. Do not modify or rerun frozen R2 as that experiment.

The repeated-interruption pilot and watchdog are still unvalidated. No new
675-unit campaign, dataset-v2a, BRACE superiority or TNSM-readiness claim follows.
Phase 6's negative decision, the rejected campaign, D1 shared-host limitation,
P1 collection-gap disclosure and all statistical locks remain unchanged.
Hardware/operator validation and publication authority remain pending.
