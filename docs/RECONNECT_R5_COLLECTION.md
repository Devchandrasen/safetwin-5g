# R5 collection software component

Contract `safetwin5g-reconnect-r5-collection-v1`. **Fixture-only software gate**,
not a network execution lock or measured recovery. The parent recovery item
remains open. No execution CLI, child creation, packet dispatch, socket, native
clock observation or power request is performed by the component fixtures.

## Fixed collection and durable identifiers

One window uses the unchanged fifteen exact R4 command spellings: initial UE
and gNB minimal identities, PDU address, two raw source dates, two complete log
prefixes, five-packet ping, two complete suffix captures, two source dates,
PDU address and final identities. Initial seven-command precheck must pass
before the packet command. Trace eligibility stays exactly `10.45.0.2`;
official-service mode permits the fixed sandbox subnet but never ST3 traces.
Both images and context identities must remain unchanged within a window.

An exclusively created identifier ledger appends, flushes and fsyncs a
reservation **before any collection command**. IDs are 10001 through 10099,
consumed on failure, never wrapped or reused. Exhaustion refuses allocation.
An existing ledger is never overwritten or removed. Failed storage blocks
dispatch and cannot receive a positive durability audit. Successful fsync is
procedural evidence, not power-loss or privileged-tampering attestation.
The future outer runner must supply a unique attempt path guarded by the
already frozen persistent host receipt; a new ledger alone is not attempt
authorization. This component does not delete or inspect unowned receipts.

The immutable clock-free R4 runtime and independent parsers keep exact raw
packet sequence, first-packet, fingerprint, historical trace, no-foreign-ID,
UTF-8, nonempty newline and unsaturated prefix requirements. Retained first-
packet loss may be a valid observation, never a successful recovery. Raw
streams remain separate and hash checked. No `--since`, `--until`, hidden
warm-up, first-packet discard or epoch-based log cutoff is introduced.

Docker's [logs reference](https://docs.docker.com/reference/cli/docker/container/logs/)
documents batch capture and nine-digit RFC3339Nano timestamps. Its
[json-file documentation](https://docs.docker.com/engine/logging/drivers/json-file/)
describes stream timestamps and rotation. Neither guarantees clock equality,
prefix persistence or physical event order. The component fails closed on
observed rotation, rewriting, saturation, malformed or missing trace paths;
it does not inspect daemon-owned log files.

## Shared clock, elapsed brackets and closure

The collector, transport and journal must share the same clock object and
descriptor. There is no wall/monotonic substitution, UTC offset fitting or
fresh domain after rejection. Every command retains the frozen owned-process
envelope, 35-second maximum, 1 MiB combined cap, actual parent GO-before and
GO-after readings, completion-observed tick, cleanup and terminal point.
Completion-observed is a parent poll observation, not exact child exit time.
Client containment does not imply daemon-side command cancellation.

For each source date pair, its elapsed value must lie between the later
GO-before minus earlier completion-observed and later completion-observed
minus earlier GO-before, expanded only by the unchanged 1 ms tolerance.
Runtime uses integer cross-products; independent replay uses rational
fractions. Absolute source epoch skew is irrelevant; source elapsed jumps
reject. This is sampled elapsed consistency, not source synchronization.

One nonrenewable 120-second window starts at the preceding journal anchor's
QPC-before, charging intervening overhead. Admission reserves all remaining
points and requires room for the **full** next 35-second command budget.
One fresh terminal point after parsing brackets the final deadline check.
A complete window uses 15 process endpoints plus one terminal point: **16
new points**, or 18 including two standalone bootstrap points. This is not
the still-pending four-trial worst-case inventory.

Clock-source/counter/storage errors latch rejection. Cleanup-mode collection
can access the frozen 256-point reserve (normal cap 768, total cap 1024), but
does not bypass failed timing to claim verified packets. The future outer
rollback must independently attempt all mandatory cleanup branches even
when this verification component cannot admit work. A failed collection
must not be used to suppress official image/reset/telemetry cleanup.
Synchronous fsync and OS calls are not hard real-time cancellable: a stall
after the last point can exceed the observed bound. The future runner must
recheck its actual global deadline before the next operation.

## Independent replay and remaining authority gates

Standalone replay checks the entire serialized journal and all globally
sequenced process rows, ledger reservations before dispatch, exact command
prefix, precheck-stop behavior, raw streams, source intervals, result parsing,
failure phase, closure and point inventory. It never calls the candidate's
acceptance functions. Negative observations can have passing integrity while
their collection outcome remains false. Failed durability rejects integrity.
Snapshots are not cryptographic hardware attestation.

Three valid official-service windows can establish a **packet-delivery
candidate** only if all 15 packets return, IDs are consecutive and the source
and both minimal identities agree across windows. Even then `rollback_verified`
and `network_fix_validated` remain false. Fresh registration/PDU provenance,
official health/telemetry/qdisc/worker state, scope, approvals and reset order
are not established by this helper.

The verifier retains exact pre-test sources, complete command/test output,
UTC verification timestamps, synthetic journal/ledger/window bytes, fresh
extraction/replay and hashes. Those timestamps describe verification, not
invented packet measurement time. Old negative observations, committed locks
and minimal read-only environment snapshots are checked separately. No native
clock or process smoke observation is repeated.

Required next: separately named four-trial runner; full normal/worst-case
point inventory; health/global/settling deadlines; exact committed approval
binding; independent **whole-protocol** replay including noncollection rows;
all mandatory official rollback branches and adversarial fixtures. Do not
slice or renumber a whole-run journal to feed this standalone auditor. These
need their own committed execution lock and later diagnostic decision.

No R2/R3/R4 rerun, new campaign, model promotion, network-fix claim or TNSM-ready
claim follows. The Phase 6 baseline win, rejected 675-unit campaign and P1/D1
limitations remain unchanged. Hardware, operator and publication authority
gates remain pending. No frozen source or historical observation is modified.
