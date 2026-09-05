# R3 instrumented resumption diagnostic

Freeze before any R3 image build or network trial. This follows the R2 negative
decision and source diagnosis; it does not amend or rerun R2, claim a recovery
correction, or alter statistical sources. Machine-readable fixed parameters
are in `config/experiments/reconnect-r3-trace.json`.

## Question and instrumentation-only boundary

Does a newly measured, identified post-return packet enter the idle NAS branch
without reaching RLS/gNB, or does its observed path locate another failure?
The historical R2 packet cannot be retroactively localized. Instrumentation
may change timing, so this is a prospective diagnostic, not proof that its
observations exactly reproduce the earlier scheduler interleaving.

Use the audited R2 image as the source/build base, preserving its one-file
AMF-selection correction. Add a trace header and only log calls/includes in
three files: UE NAS `sm/sap.cpp`, UE `rls/ctl_task.cpp`, and gNB `gtp/task.cpp`.
Removing the ten delimited insertion blocks must reproduce those three pinned
base files byte-for-byte. The new helper must not write packets, add timers,
buffers, retries, protocol state or change routing/selection predicates.
Inspect the header itself; removal equality alone cannot prove its safety.
Full compilation against real upstream types is a separate required build gate.

Seven stages identify ingress and branch/path observations: `nas_in`,
`nas_idle`, `nas_forward`, `ue_rls`, `gnb_in`, `gnb_missing`, `gnb_resource`.
The last stage only means a PDU resource was found, not that GTP transmission
or delivery succeeded. No global cross-process event order is inferred from
merged timestamps. Preserve within-component order and compare packet keys.

Trace only PSI 1, unfragmented IPv4 ICMP echo requests from 10.45.0.2 to
10.45.0.1, identifiers 10001 through 10099 and sequences 1 through 5. Validate
IP/header lengths before reading identity fields. The helper rejects other
flows, reply types, fragmentation and truncated identity data without changing
the original forwarding path. It is an identity reader, not a full IP/ICMP
validator or checksum validator. Header/echo layouts follow
[RFC 791](https://www.rfc-editor.org/info/rfc791/) and
[RFC 792](https://www.rfc-editor.org/info/rfc792/).

Log stage, PSI, local actor ID, state, IP ID, ICMP identifier/sequence, byte
length and full-packet FNV-1a-64 fingerprint. The fingerprint is an accidental
correlation check, not cryptographic authenticity; logs/artifacts retain
SHA-256 manifests. Do not log payload contents, subscriber keys or identities.
Any key collision, contradictory path or fingerprint mismatch makes packet
localization inconclusive. NAS ingress avoids additional session-pointer
dereferences; session state is logged only inside the original active branch.

## Fixed network design, not yet authorized by a build alone

Four instrumented trials, in order: control-before, drop-a, drop-b,
control-after. Fresh core/gNB/UE preparation precedes each assignment. Require
fresh registration/PDU state, 15/15 baseline packets, three up Prometheus
targets, UPF running, no fault workers and neutral qdisc before a fault.

Drop trials use the unchanged eight-second UE eth0 100% loss, owned handle
7157, in-container 15-second timeout and EXIT cleanup. Controls have no qdisc
mutation. Use the fixed five-second settling interval, then three five-packet
windows with 0.2-second spacing, one-second reply timeout and 56-byte payload.
All first packets remain measurements as well as traffic stimuli. No extra
warm-up ping, delayed window, replaced observation or invented reply is allowed.

Every ping invocation, including baseline, post and restoration, receives a
new monotonically assigned ICMP identifier starting at 10001 via `ping -e`.
Retain the exact invocation-to-window mapping. No ID reuse/wrap is allowed;
stop admission before 10099 is exceeded. Verify CLI support before execution.
Replies must be parsed independently from raw ping output, including the
transmitted count and sequence numbers; a zero exit code is not 5/5 delivery.

Preserve full bounded per-component log intervals covering all five input
packets of each window. Reject a saturated 2,000-line capture, malformed trace,
missing ingress, duplicate identity/stage, out-of-order local stages or an
unaccounted forwarded path. Do not use missing log lines alone as loss proof.
All five packets need one NAS ingress and one branch record. Forwarded packets
need RLS and gNB ingress plus resource-found/missing observations. An idle
packet must not also have downstream/reply evidence. A lost packet after the
resource-found stage remains unlocalized; trace completeness is not endpoint
success. Independently check these relationships from raw logs, not only the
runtime trace helper. The helper is fixture-tested, not yet a complete runner.

Both controls require 15/15 post packets and complete forwarding/reply traces.
Drop windows retain any observed packet delivery. A valid, fully accounted loss
does not stop this diagnostic merely because it is not lossless: the purpose
is localization, and both drop assignments were fixed beforehand. Stop on an
invalid baseline, uncontrolled exposure, incomplete trace, failed control or
failed restoration; add no replacement trial. This rule changes neither R2's
first-failed-recovery stop nor any later recovery-validation criterion.

Report each drop's unchanged 15/15 recovery endpoint separately, with Service
Accept/context evidence where present. Never set `network_fix_validated` from
this logging-only experiment, even if a fully returned window is observed.
The four-trial result is not a reliability, superiority or overhead estimate.

## Image, approval and rollback gates

The official image and R2 image/tag remain unchanged. The new tag is
`safetwin5g/ueransim:3.3.0-reconnect-r3-trace`; refuse to overwrite it. Build
only after the source overlay, protocol and fixture/audit contracts are
committed. Retain source, licence, actual applied diff, compiler, binary hashes,
image IDs and commands. Audit overlay removal against the retained R2 source,
real build success and the expected UE/gNB binary changes. No registry push.

Before network execution, commit the immutable R3 image ID, a separate scoped
Compose override, runner, independent network auditor and regression tests.
Record standing-user approval naming the exact four trials, image IDs, two
UERANSIM containers, fixed resets, bounded faults and rollback. It is not an
operator signature. Validate the internal-only network, source pins and exact
image IDs, unchanged mounts/devices/capabilities/commands and unrelated service
images. Replace only the scoped UE/gNB services; no ports, extra capabilities,
volume removal, dependency rebuilds or unrelated container changes.

Post-drop restoration remains the recorded UE-restart then full-reset ladder,
including any failed steps. In the outer finally path, remove only the owned
qdisc, restore official images for both UE and gNB after any attempted switch,
then reset core/gNB/UE and verify fresh registration/PDU and 15/15 packets.
Never leave the instrumented image running implicitly. Failures do not suppress
attempted safety restoration or erase previous unsuccessful observations.

Network admission budget is 25 minutes. Command timeout is 35 seconds, bounded
health wait 50 seconds, and safety rollback remains enabled after admission
ends. No long campaign begins in this diagnostic.

## Claim limits

Prebuild tests and parser/overlay checks are `fixture`. Future interventions
may be `sandbox-measured` with `simulated` radio only. Keep D1 shared-host and
instrumentation timing limitations; preserve P1's historical gap disclosure.
No hardware/operator/live-network/TNSM claim is enabled. The original
spontaneous link loss, repeated-interruption pilot and watchdog remain open.
The rejected 675-unit data and Phase 6 negative decision are not salvaged,
pooled or retuned. No dataset-v2a or confirmatory BRACE analysis follows.
