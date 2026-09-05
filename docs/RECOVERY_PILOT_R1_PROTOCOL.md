# Recovery engineering pilot R1

Frozen before execution on 2026-09-05. Configuration:
`config/experiments/recovery-pilot-r1.json`. This is an engineering pilot;
its records do not enter the rejected Phase 7 dataset or any confirmatory
policy comparison.

## Fixed trial sequence and acceptance

Six trials use minimum UPF suspension holds of 0, 1, 30, 30, 45 and 0 seconds.
The zero-hold trials are controls. The host-observed STOP-to-CONT command window,
all command times, and all failed probes are recorded. The command window is
an upper bound, not exact in-container suspension timing. The admission budget
is 15 minutes; bounded safety restoration remains enabled after expiry, with a
35-second command timeout and a 50-second container-health timeout. A 65-second
in-container watchdog sends CONT if the host process disappears during a fault.
It checks the original UPF PID start ticks. A unique per-trial marker disarms
it after primary CONT, and a completion barrier precedes any core restart or
next trial. A watchdog firing or failing that barrier fails the trial.
Recovery probes begin after this barrier (approximately 65 seconds after
arming). Report that deliberate delay separately; it is not measured MTTR or
evidence that a short interruption immediately recovered. Attempt latency
starts at each escalation step, not at CONT.

Each trial requires three baseline samples before injection. Every sample
must have five transmitted and received packets, at most one percent loss,
neutral qdisc, running UPF, no stress workers and all three Prometheus targets
up. Missing or invalid measurements fail. For an interruption, verify the
UPF stopped state before the fixed hold. Always attempt primitive rollback:
send CONT first and clear qdisc. This pilot creates and kills no stress workers;
any observed worker makes the service window unclean and blocks injection.

Apply the same fixed recovery escalation after each interruption:

1. Probe three service samples after primitive rollback.
2. If they fail, restart only the SafeTwin UE, wait for health, and probe again.
3. If those fail, restart SafeTwin Open5GS, gNB and UE in dependency order,
   wait for health, and probe again.

Each unsuccessful step and its latency remains in the record. A trial passes
only with a clean baseline, verified assigned fault, and three clean final
recovery samples. A no-fault control additionally must recover at the primitive
step. Any failed trial stops the pilot. A final restoration is attempted even
on exceptions, and restoration failure is reported separately. No unrelated
container, volume, network or data is modified or removed.

The user's standing authorization to continue local SafeTwin work and the
explicit continuation on September 5 cover this isolated reversible engineering
work. A pre-execution approval record binds that authorization to the fixed
six trial IDs, container names, STOP/CONT and the listed restart/rollback plan.
This is not a fresh per-trial user interaction, an operator signature, or live
network authorization.

Before any mutation, verify the five exact project containers, their sole
internal network, no published ports or privileged mode, container health,
Open5GS/UERANSIM source labels, pinned MongoDB/Prometheus image references, and
the live-blocked/mandatory-human-approval policy. Record complete container
identities and image IDs. The runtime takes no user-selected target argument.

## Why this pilot

The pinned [Open5GS SMF PFCP state machine](https://github.com/open5gs/open5gs/blob/318eeb49a7dcdff733dec60e02d9c60aefca2fb9/src/smf/pfcp-sm.c)
transitions away from association on a missing heartbeat and contains session
cleanup/reselection and restoration paths. Thus a running UPF process alone
does not prove a usable PDU session. This supports investigating the retained
PFCP timeout logs; it does not prove every historical outage's cause.
The [official UERANSIM usage documentation](https://github.com/aligungr/UERANSIM/wiki/Usage)
describes the UE TUN interface and CLI status inspection. This pilot verifies
traffic through that interface directly.

## Interpretation

The main result is the observed restoration path and time, including primitive
failures. All six trials passing allows implementation of the verified recovery
procedure and a separate campaign-readiness gate. It does not establish that a
675-unit campaign is reliable. If the gate fails, preserve the no-go and refine
only a separately versioned engineering protocol. Statistical thresholds,
BRACE code, frozen test partitions and rejected campaign artifacts remain
unchanged. D1 shared-host effects remain possible. P1's earlier collection gap
does not disappear when a new short pilot passes. Evidence is sandbox-measured
intervention with simulated radio, no hardware or operator validation.
