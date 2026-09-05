# R5 bounded owned-client capture component

Contract: `safetwin5g-reconnect-r5-process-v1`. Scope: **software/fixture only**.
This is not the full R5 process/collection/host/runner gate. No Docker mutation,
packet probe, image application or actual sleep-inhibition request is authorized.
The component has no standalone execution endpoint; its allowlists default empty.

## Dependencies, authority and captured boundaries

The frozen R5 native-clock and journal contracts remain byte-identical. The
new adapter uses the journal's one clock object and raw QPC domain. It does not
call Python wall/performance/monotonic clock APIs or fit an epoch offset. It
latches thrown, malformed, reversing or changed-descriptor counter reads;
later commands cannot clear that counter error. The journal separately preserves
all UTC/QPC brackets, every earlier-pair check and source/storage failures.

Only the clock-free `OwnedJob` implementation and GO launcher are reused from
R4. Their exact sources, and the unchanged deterministic local child helper,
are bound through the committed R4 execution lock. The old `BoundedProcess`,
old wall/elapsed predicates and old runner are not reused or monkey-patched.

Every invocation must match an exact argv allowlist, strict consecutive sequence
and integer bounds: 1-35,000 ms, at most 1 MiB combined stdout/stderr, and a
2,000 ms cleanup grace. Cleanup has a distinct allowlist, a subset of the first;
setting a cleanup boolean cannot expand it. These allowlists do **not** constitute
human approval or validate image/network scope. A future committed runner must
establish that authority before providing any mutable command to this library.

The start envelope references the existing last journal point. The adapter
records QPC ticks for admission check, immediately before/after sending GO,
observation of client completion/stop, and completion of owned cleanup. One
new precise UTC/QPC point terminates the envelope and may be the next command's
start anchor. The two bootstrap points therefore need only one further point
per command. Intervening logging, parsing and idle overhead is charged to the
next envelope, not silently excluded. The deadline is the anchor's raw
QPC-before tick plus the integer tick budget, rounded down by less than one
tick. Expired normal envelopes stop before GO; no fresh anchor hides the delay.

An accepted timing record requires ordered same-domain observations wholly
inside its start/end brackets, pre-cleanup completion before the command
deadline, and cleanup shorter than two seconds. Raw UTC appears only in the
journal, never as an inferred GO or exact process-exit timestamp. GO observations
bound parent dispatch; completion is observed after polling, not an exact
child scheduling instant. They concern the owned client, not the duration of
a Docker-daemon operation. Both the full 1,024-point cap and the nonrenewable
256-point cleanup reserve remain unchanged. The complete four-trial protocol's
worst-case point inventory still needs a separate prospective integration audit.

## Owned process and independent fail-safe timeout

An unnamed Windows Job with kill-on-close and no breakaway contains an owned
hidden launcher before GO. The launcher cannot start its target before GO.
Two unbuffered pipe readers retain only the bounded combined prefix, continue
draining while termination is initiated, and record separate raw base64/hashes
plus strict UTF-8 status. Saturation, invalid UTF-8, timeout and failed cleanup
remain rejected. No unrelated process is selected or killed by name.
See [Microsoft's Job object documentation](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).

Normal elapsed admission and completion use raw QPC. An independent kernel
relative timer is also armed before even creating the idle launcher, so a
failed QPC API cannot turn a client wait into an unbounded Python loop.
It is unnamed, non-inheritable, manual-reset and one-shot, with negative
100-ns due time, zero period, no callback and `fResume=false`. The remaining
normal QPC budget is rounded down to 100-ns units for this fail-safe. No system
clock, global timer-resolution or power setting is changed. These API semantics
are described by [CreateWaitableTimerW](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-createwaitabletimerw)
and [SetWaitableTimer](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-setwaitabletimer).

Only an already-allowlisted cleanup invocation may proceed after clock rejection,
unavailable/exhausted brackets or an expired old envelope. If no QPC deadline
can be used, its configured relative timer still bounds the wait and the record
sets `emergency_timer_only`; it never fabricates timestamps or passes timing
acceptance. This is an out-of-band termination safeguard, not an alternative
measurement epoch or a relaxed scientific deadline. A timer creation/arming
failure dispatches no target. The future rollback supervisor must still try
each remaining independently authorized target; this component cannot implement
that complete official restoration plan by itself.

Finally, owned job close and owned-launcher termination are independently
attempted, followed by bounded reaping/pipe-thread joining. A separate two-second
relative timer and, when available, the same QPC cleanup deadline limit waiting.
Zero-time thread joins add no alternate elapsed-clock budget. All failures are
retained; no missing reap, thread or timestamp is inferred successful.

The kernel timer is not a hard real-time/power-loss guarantee. On Windows 8+
relative timers and [bounded waits](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-waitforsingleobject)
exclude low-power time. User/lid sleep, scheduler starvation, disk failure or
a blocked/failed kernel API can prevent timely completion and evidence. Timer
or cleanup API failures remain negative, even when subsequent OS termination
occurs. Killing the client tree does not cancel a daemon operation already
accepted. No claim of continuous network service or daemon cancellation follows.

## Independent replay and evidence labels

The separate auditor imports no candidate process or clock code. It replays
the frozen rational clock/journal audit, exact allowlists/sequences, boundary
references, raw streams, byte caps, counter-domain/order, charged deadline and
reported flags. `client_capture_complete` is raw capture completeness, not a
successful command exit. A complete captured exit 7 remains exit 7; the future
caller must enforce its exact per-command return codes. `complete` additionally
requires valid timing, never approval or actual service restoration.

Fixture generation launches only the pinned hidden deterministic local helper.
Most process cases use explicitly synthetic clocks; their timestamps are not
measured process latencies. A separate once-only two-command native shared-
envelope observation captures actual local QPC/UTC, retaining any rejection
without replacement. Its narrow accounting result is still **fixture** evidence,
not network/hardware measurement or a repeat of the previous native clock smoke
capture. Every source version, test log and raw case is retained in lossless
archives and freshly extracted for independent replay. Storage-failure fixtures
expect a durability-audit rejection, not an invented successful journal.

Still pending: the separately named host/collection/runner integration, fresh
PDU and trace/source checks, full scope/approval/telemetry/official rollback
plan, whole-protocol inventory and independent adverse-path replay. Only their
complete committed execution gate may precede a later separate diagnostic
decision. Old R2/R3/R4, rejected Phase 7 data, Phase 6 baseline wins and P1/D1
limitations are unchanged. No new campaign, TNSM, hardware or operator claim.
