# Reconnect engineering reproduction R1

Frozen before execution, 2026-09-05. This is a separate, bounded engineering
reproduction following the rejected recovery pilot. No statistical source,
official image pin, prior artifact or confirmatory partition is changed.

## Hypothesis and fixed design

The current source-supported candidate is that a post-link-loss Service
Request on a new UE context cannot select an AMF: Initial NAS processing keeps
requested slice type -1 for non-RegistrationRequest messages, while AMF
selection matches advertised SST exactly. The earlier cause of spontaneous
radio-link loss is not identified by this experiment.

Run exactly four trials in order: no-fault control, drop-a, drop-b, no-fault
control. Each begins with a fixed fresh Open5GS, gNB, UE restart sequence,
healthy containers, fresh UE registration/PDU establishment logs, and three
five-packet baseline samples. These planned preparation resets are recorded
and approved, not hidden retries of failed baselines. Any invalid baseline or
unrestored final state stops further trials; no replacement trial is added.

The two drop trials install 100% egress loss on **only the SafeTwin UE eth0**
for eight seconds. This interrupts the software radio's UDP transport; it is
not physical RF fading or a selective radio-only impairment. Core, gNB and
unrelated interfaces are not impaired. Controls wait the same eight seconds
without changing qdisc. Baseline eth0 must be the exact noqueue root state.

A single in-container shell owns the temporary `7157:` root qdisc. It records
UTC times and JSON qdisc state, waits eight seconds, and removes its qdisc in
an EXIT trap. A 15-second in-container timeout bounds the shell independently
of the host Python process; INT/TERM/HUP cause exit through the same trap.
The host command timeout is 35 seconds. An idempotent emergency cleanup only
deletes the exact owned handle; unknown state fails closed. Afterward, verify
the original noqueue root state, wait five seconds, then probe three more
five-packet windows. This fixed observation delay is not exact MTTR.

For each impaired trial, record logs before restoration, then restart UE and
verify a fresh registration, PDU session and three clean five-packet samples.
If that approved restoration fails, use the fixed full Open5GS/gNB/UE reset
and verify again. Retain failed restoration probes. Controls must self-recover
without a post-window restart; a failed control is preserved and stops the run
after the same safety restoration ladder. No CPU workers or UPF faults are
created, and the unexecuted UPF watchdog from recovery pilot R1 is not validated.

## Separate decisions

`protocol_execution_valid` requires all four exact trials, clean baselines,
the assigned qdisc state and eight-second interval, verified eth0 rollback,
and final service restoration. Failed automatic reconnect is an observation,
not a reason to discard a properly executed drop trial.

`reconnect_failure_reproduced` additionally requires both drop trials to show,
in their post-exposure/pre-restoration logs, a radio-link failure, a Service
Request, gNB AMF-selection failure, and missing PDU resources, alongside zero
returned packets out of 15 after qdisc rollback. Both control post-windows
must return 15/15 without those error markers. If this pattern is absent or
only partly observed, report that precisely and do not claim reproduction.
Even two successful reproductions do not prove the unique cause of every
historical outage, population reliability, or causality of a proposed patch.

The total admission budget is 15 minutes. Safety restoration remains enabled
after that budget, with bounded commands; any overrun is reported. Approval
records must precede actions, identify these four trials, exact containers,
fixed resets, qdisc handle, timeout and rollback. The user's standing local
sandbox authorization is not an operator signature or live-network approval.
Verify internal-only topology, five project containers, no published ports or
privileged mode, source labels/image digests, and mandatory-approval/live-blocked
policy before mutation. Capture all commands, stdout/stderr, samples, UTC times,
versions, source hashes, manifests and explicit failure decisions.

## Primary sources and boundaries

The pinned [Initial NAS processing](https://github.com/aligungr/UERANSIM/blob/6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156/src/gnb/ngap/nas.cpp)
and [AMF selection](https://github.com/aligungr/UERANSIM/blob/6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156/src/gnb/ngap/nnsf.cpp)
define the candidate. The [UE radio-link transport](https://github.com/aligungr/UERANSIM/blob/6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156/src/ue/rls/udp_task.cpp)
uses a 2,000 ms heartbeat threshold, motivating an eight-second exposure.
[GTP packet handling](https://github.com/aligungr/UERANSIM/blob/6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156/src/gnb/gtp/task.cpp)
rejects a missing UE/PDU resource. Source logic is not substituted for a run.

Evidence is sandbox-measured intervention and simulated radio. D1 shared-host
limitations remain; P1 applies to the earlier rejected collection. No dataset
release, BRACE comparison, TNSM promotion, hardware/operator claim, live action,
upstream contribution or publication is authorized by this reproduction.
Any patch and follow-up validation require a separately versioned next step.
