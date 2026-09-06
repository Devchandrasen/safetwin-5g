# R5 whole-protocol software contract

This is a prospective **fixture-only execution integration**. It implements
the four-trial protocol and independent whole-run replay. Passing fixtures
does not authorize a diagnostic, establish a network fix, validate BRACE, or
change any R1-R4 result. The execution module deliberately has no network CLI
and rejects `fixture=False`. Native admission/approval-file acquisition and a
once-only actual diagnostic require a later separately committed authority
decision. Injected fixture prerequisites are not proof of real host admission.

## Fixed scope and ordering

The existing official/derived R3 images, command contract, Compose files and
five-container isolated scope remain unchanged. No build, tag overwrite,
pull, image push, outside-network action, host clock change, unlimited output
or live actuation is added. One flat command stream and one shared QPC/precise
UTC journal cover the whole execution, including host admission and cleanup.

1. Two bootstrap points, exact prior approval, receipt path binding, exclusive
   once-only receipt, idle snapshot and owned power handle.
2. Read-only revision/configuration/image/scope/neutral-qdisc preflight.
3. Independent derived gNB and UE image application and health checks, then
   complete scope verification. An uncertain first application still triggers
   the second image branch and mandatory official cleanup.
4. `control-before`, `drop-a`, `drop-b`, `control-after`, in that order. Each
   trial needs full core/gNB/UE reset, health, fresh increasing start times,
   retained log prefix and exactly one fresh registration/PDU marker pair.
5. Three baseline windows must deliver all 15 packets in one unchanged
   context, with neutral telemetry, before an eight-second exposure. Settling
   is a same-domain, verified minimum five seconds. Three post windows retain
   every packet, including the first. A completely accounted 14/15 diagnostic
   is a valid negative observation, not successful recovery.
6. Each drop or failed prepared trial uses UE-only, then full reset if needed,
   with three fresh windows for restoration. Normal admission failures stop
   progression. Unknown qdisc handles are never deleted.
7. Once any candidate application is attempted, final cleanup independently
   attempts owned-qdisc removal, BOTH official images, all THREE reset/health
   targets, all THREE packet/telemetry windows even after reset failure, final
   scope, eth0 and four telemetry commands. Owned power and receipt closure
   are attempted independently. Their errors remain errors.

In emergency cleanup only, image tag identity can be read from complete
bounded raw client bytes despite rejected clock timing/journal durability.
Only clock-journal errors may be separated from that metadata check; unknown
tag, stdout/stderr, return code, timer/job/reader failure still block unsafe
replacement. Both image branches are independently attempted. This is not a
timing, durability, successful rollback or diagnostic acceptance claim.

## Time, capacity, storage and ownership

Frozen R5 clock/journal/process/host/collection/budget sources stay byte-exact.
No fitted clock epoch, retiming, dropped record, relaxed 1 ms consistency
bound or relaxed 100 microsecond bracket bound is allowed. Command records
keep the 35 s maximum and 1 MiB output cap, with the original owned-client
cleanup contract. Every collector reserves its unique identifier durably
before dispatch. Every attempted command has a durable intent/result or
explicit pre-dispatch rejection, linked to the shared journal and admission.

Normal admission ends at 768 points. Up to 256 points remain reserved for
cleanup; the independently enumerated full cleanup envelope is 216. Its
conditional prefix-plus-cleanup bound is 984/1024. Health waits, settling,
parser overhead and filesystem work are charged to shared capture envelopes;
the global deadline is 1500 seconds from bootstrap point 2. The unpruned
normal envelope does not fit, so four-trial completion is NOT guaranteed.
Synchronous kernel/filesystem callbacks are observed and rejected if late,
not forcibly cancellable hard-real-time operations.

The persistent attempt receipt is never deleted or overwritten. Fixture
receipts and ledgers are exclusively created under the fixture output path;
an existing unowned receipt remains untouched. A native execution path is
disabled rather than claiming injected booleans establish actual admission.

Aggregate JSON evidence has a separate 128 MiB parsing cap because it repeats
bounded command records in component snapshots. Duplicate keys and nonfinite
values are rejected. This does not change any subprocess byte or time limit.
Raw artifacts are retained losslessly with pre-test sources and hashes;
compressed release copies must be extracted and replayed independently.

## Independent whole-run replay

`tools/audit_reconnect_r5_execution.py` does not import candidate acceptance
code. It replays the entire process stream once and keeps global command and
journal numbers unchanged. Separately versioned global adapters retain the
independent frozen host, collector and budget predicates while permitting
intervening protocol operations. The root cursor accounts for EVERY step,
intent/result/rejection, admission, component terminal and final terminal.
It derives exact trial, early-stop, restoration and rollback branches from
raw process/clock/packet/scope evidence, not positive summary flags.

Observation integrity, full protocol completion, 15/15 recovery and official
restoration are separate outputs. Failed durability rejects integrity. A
negative protocol can still have an honest integrity pass. Disabling all
candidate acceptance entrypoints must not prevent independent replay.

## Verification and unresolved native gate

The whole fixture harness forbids process launch, sockets and native clock or
power APIs. It uses invented timestamps and in-memory daemon states. The
existing metadata used to seed its state remains explicitly fixture input.
Never run a native clock verifier or network diagnostic to repair a fixture.

The final decision file, not this prospective contract, identifies completed
verification, retained failures and the exact committed lock. A later native
adapter must verify committed source bytes and real prerequisites, load and
recheck an actual exact prior approval, enforce the fixed receipt path and
once-only attempt, and independently pass a separate release audit before
any actual diagnostic can be considered. Hardware/operator/publication gates
remain pending external authorization.
