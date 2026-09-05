# R5 clock-journal integration component

Contract: `safetwin5g-reconnect-r5-journal-v1`. Evidence: **fixture only**.
This is one component of the pending R5 execution-integration gate, not its
completion. It has no process, network, image, restart, packet or power API.
No measured diagnostic is authorized by this contract or its source lock.

## Frozen dependency and bounded inventory

The five-source R5 precise-clock contract and all older locks are unchanged.
The journal retains one descriptor and every returned point, without resetting
the domain after drift or replacing a failed read. It incrementally checks
every earlier point with the same integer all-pair predicate. Total comparisons
at 1,024 valid points are 523,776. Independent replay uses the unchanged,
separately derived rational clock auditor, not the incremental implementation.
The 100 microsecond expanded bracket, 1 millisecond whole-interval tolerance,
two 1,000 ns read allowances and two counter ticks are unchanged.

The historical complete R4 **fixture** contains 761 command records, in addition
to host admission. Naively allocating two fresh UTC brackets per command would
need at least 1,522 points, exceeding the frozen 1,024 cap before host/settling
boundaries. This is a prospective integration constraint, not a new R5 result.

The journal reserves the final 256 points for cleanup. Normal admission ends
at 768. A caller can ask whether a complete prospective operation's point
inventory fits; it must not start work based only on space for its first point.
Cleanup may continue recording to 1,024. Exhaustion records a blocked event and
does not call the source again, wrap its sequence or open another domain.
These limits are not a proof that the future whole protocol fits: that exact
inventory, including worst-case health polls, remains a required fixture gate.

Adjacent future command capture envelopes may share an existing boundary.
Such a boundary is **not** the next command's actual dispatch timestamp. A
separate bounded adapter must retain actual dispatch/exit ticks from the same
raw QPC domain, prove that execution lies inside its referenced UTC/QPC brackets,
charge intervening overhead, and enforce the command/window/host budgets.
This journal neither implements nor verifies that containment. No midpoint,
fitted epoch offset or unbracketed wall reading is introduced. Microsoft's
[QPC guidance](https://learn.microsoft.com/en-us/windows/win32/sysinfo/acquiring-high-resolution-time-stamps)
distinguishes local elapsed measurements from external UTC synchronization.
Shared-envelope correctness is a project design obligation, not a guarantee
provided by that documentation.

## Fail-closed journal and exception-isolated cleanup dispatch

Creation is exclusive. Each header, returned point, unavailable-source error
and blocked attempt is appended, flushed and fsynced. All reports and snapshots
are copies; later accepted reads cannot erase the first rejection. One point
alone cannot admit work. A thrown source exception is latched because its
internal sequence may have been consumed without returning a record. No retry
or fabricated timestamp fills that gap. Returned partial points remain raw.

Storage errors reject admission. In-memory state is not presented as durable
when the file write, flush or fsync failed. The independent auditor rejects a
short/incomplete/different journal and any snapshot declaring storage failure.
A disk/kernel failure can still prevent complete evidence. No storage-atomicity
or power-loss guarantee is inferred from a successful fsync.

`attempt_cleanup_steps` tests a narrow dispatch property: each supplied callback
is independently attempted even when a preceding callback, before/after clock
capture or journal write raises, including timeout and source exhaustion. It
does **not** create authorization, enforce a Docker allowlist, implement rollback
or verify service restoration. Tests supply only local no-I/O callbacks; all
network/process/native power APIs are denied. Returning from a callback is not
proof that a daemon accepted, finished or cancelled an operation. Its result
always leaves `service_restored` and `network_fix_validated` false.

The future runner must supply only the already approved, exact official cleanup
plan and must independently attempt owned-qdisc handling, both image targets,
all three reset targets, health, fresh PDU, 15/15 packets, telemetry and scope.
Unknown qdiscs remain untouched. This component is not that runner or audit.

## Retained gate and remaining work

The verifier saves exact source snapshots, test stdout/stderr, commands, UTC
verification timestamps, ten synthetic journal/callback cases, fresh archive
extraction/replay and a recursive byte manifest. Failed development attempts
are retained. The gate also rechecks committed old source locks, original R4
negative observations, R3 build provenance and the statistical lock.
Read-only environment checks are separate prerequisites, not PDU/recovery
measurements. The fixed native R5 clock smoke probe is not repeated.

This subgate can pass while the parent execution gate remains incomplete.
Still required: separately named bounded process adapter, collection and host
integration, four-trial runner, exact approval/command/deadline binding,
whole-protocol point inventory, independent raw whole-protocol replay and all
negative rollback fixtures. They need their own committed execution lock and
a later separate execution decision before any network diagnostic. Do not
monkey-patch frozen R4 code, increase caps or relabel the old 675-unit rejection.
All negative R2/R3/R4, Phase 6 and Phase 7 outcomes, P1/D1 limitations and
hardware/operator/publication authority gates remain unchanged.
