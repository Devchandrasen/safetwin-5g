# R4 bounded execution integration, prospective software gate

Date: 2026-09-05. Evidence at this gate is **fixture**, including controlled
Windows child-process probes. Read-only daemon checks establish prerequisites
only. No R4 image application, fault, restart, ping, measured assignment or
actual sleep-inhibition request is part of this gate. Network recovery, BRACE
confirmation and TNSM readiness remain unverified.

## Immutable dependencies and exact scope

The eight-source [R4 collection contract](RECONNECT_R4_COLLECTION.md) and its
lock remain unchanged, as do R3's 74-source execution lock, original rejected
network capture and both original/observation audit verdicts. This new
15-source execution lock binds the prior collection lock and its transitive
R3/image/source/build dependencies. Main requires exact bytes in Git HEAD for
every new source and the lock. The fixture generator may run before commit,
but independently replays the frozen bytes. Unit development explicitly uses
an unfrozen-fixture exception; the release generator and network CLI cannot.

The only prospective assignments are control-before, drop-a, drop-b and
control-after. Controls wait eight seconds; drops use the already frozen
eight-second UE-eth0 netem command with its self-removal trap. The same R3
instrumentation-only image is applied to exactly UE and gNB, without a build,
tag overwrite or configuration expansion. The exact five-container internal
network, images, devices, capabilities, mounts, command and isolation scope
are checked using the frozen minimal snapshots. No unrelated container is
modified. No endpoint, partition, statistical threshold or historical claim
changes here.

## Admission, command capture and host lifecycle

`sandbox/run_reconnect_r4.py` defaults to parser rejection, before lock checks
or subprocess work. A later explicit `--execute --approval PATH` requires
all committed locks, audited image provenance, fail-closed project policy,
no existing R4 attempt directory, no R3 runtime lock and an exclusively created
R4 runtime lock. Never remove an unexplained stale lock or prior attempt.
The approval file must identify the user, exact revision digest, four trials,
three reset targets, two immutable images, explicit rollback and sandbox-only
authority. Standing user authority is not an operator signature. This gate
does not create a measured-execution approval file.

A bounded read-only process snapshot must show no other Python campaign,
recovery-pilot or reconnect runner. This is point-in-time evidence, not mutual
exclusion against unrelated tools or an uncooperative process started later.
An owned Windows sleep-inhibition request must succeed before network commands;
its pre-command admission and final clearing outcome are durably recorded.
Failure to clear rejects protocol completion even if packets recovered.
[Microsoft documents](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate)
that this request prevents automatic system sleep, not a user/lid sleep or
shutdown. Do not promise uninterrupted execution on a closing laptop.

The adapter accepts only exact argv and a timeout of at most 35 seconds.
It starts an owned hidden Python launcher which cannot start the target until
it reads `GO`. The launcher is assigned to an unnamed Windows Job object
with kill-on-close and no breakaway flags **before** `GO` is sent. Separate
unbuffered stdout/stderr readers retain at most a combined 1 MiB; reaching
the cap is rejection, not success. Timeout, overflow, invalid UTF-8, process
failure or incomplete cleanup retains raw base64, byte hashes, replacement
text if necessary, exit code, timing and explicit flags. Closing the owned
job terminates its client process tree; joining/reaping has a two-second
cleanup grace. A denied job assignment never sends `GO`.

[Windows Job objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
provide descendant grouping and kill-on-close. Assignment can fail, including
under incompatible containing jobs, so
[assignment failure](https://learn.microsoft.com/en-us/windows/win32/api/jobapi2/nf-jobapi2-assignprocesstojobobject)
is fail-closed. This is stronger than collecting unbounded output and checking
its size afterwards; Python's
[subprocess documentation](https://docs.python.org/3.12/library/subprocess.html)
warns about pipe buffering and timeout cleanup responsibilities.

The guarantee concerns owned **client** processes, not cancellation of an
operation already accepted by the Docker daemon. A client timeout is never
proof that a restart, Compose operation or daemon-side exec did not occur.
It rejects the trial and triggers independent final restoration and scope
checks. Host power loss, disk failure, kernel/API failure or a delayed daemon
operation can prevent complete evidence or cleanup; unresolved intents and
failed rollback remain explicit failures requiring inspection. There is no
automatic retry or success inference from missing output.

## Collection, fresh reset and restoration

Before any collection command, append, flush and fsync a new ID reservation.
IDs 10001 through 10099 never wrap, retry or serve as discarded warm-ups.
The fixed 15-command collection uses no `--since`/`--until`; strict unsaturated
prefixes, integer nanosecond source/host brackets, source eligibility, raw ping
header, all packet paths and fingerprints use the unchanged collection rules.
Host wall/monotonic disagreement above one millisecond is rejection, not an
offset estimate. The Windows adapter and all host/runner deadlines use the
same high-resolution monotonic `perf_counter_ns`/`perf_counter` source, requiring
an unadjustable counter with resolution at most one microsecond. Local Python
3.12 reports QueryPerformanceCounter at 100 ns; its different `monotonic`
API uses GetTickCount64 at 15.625 ms and is unsuitable for this tolerance.
Counter implementation/resolution is recorded, not inferred from the `_ns`
unit. [Python's time documentation](https://docs.python.org/3.12/library/time.html#time.perf_counter)
defines this performance counter and its integer variant. No clock is set or
threshold relaxed. Each collection admits commands only while 35 seconds remain
in its 120-second monotonic window. A deadline stop records its checked time,
reason and next command, preserving the complete attempted prefix. Four
subsequent telemetry commands are separately bounded. The overall 1,500-second
budget blocks further trial admission; required safety rollback remains enabled.

Every reset records three identities, an unsaturated old UE log prefix,
independently attempted target resets/health waits, then new identities and
logs. Each target must retain its container and image identity and have a new
start time; the new suffix must contain exactly one successful initial
registration and one PDU establishment marker. Marker presence without a
fresh prefix/start is insufficient. Health waits share a 50-second bound,
not a renewed bound per poll. A failed reset never skips the other requested
core, gNB and UE reset attempts.

A baseline requires a fresh full reset, three valid five-packet collections,
15/15 delivery in one unchanged source/container context, neutral qdiscs,
running UPF, zero stress workers and exactly three healthy Prometheus jobs.
Invalid baseline blocks exposure. The fixed trace source remains 10.45.0.2;
a UE-only reset producing 10.45.0.3 is ineligible for trace evidence even if
the ping would succeed. Official packet-only restoration can use a stable
eligible private PDU address, but must have no ST3 instrumentation.

After exposure, retain the fixed five-second settling interval using integer
monotonic values, three post windows and raw context messages. A fully
observed 14/15 drop result can be valid **diagnostic accounting**, never a
15/15 recovery or correction. Controls require 15/15 without radio-link
failure. Failed trials stop further assignments. The bounded derived
restoration ladder attempts UE reset, then full reset if needed. The outer
finally independently attempts owned qdisc cleanup, both official-image
replacements, all three resets, fresh PDU, official 15/15, scope and telemetry,
even after an earlier cleanup, switch or reset failure. Unknown qdiscs are
not deleted. Any failed cleanup/restoration remains negative.

## Independent replay and retained failures

The whole-protocol auditor follows a command cursor from prior approval and
host admission through preflight, reset, exposure, restoration and final
scope. It independently parses raw bytes, clock/source bounds, ping, trace,
telemetry and markers. It does not call the execution runner or its acceptance
predicates. The separately versioned window-audit helper copies the frozen
collection auditor's raw parsers and changes only the outer transport wrapper
to allow explicit fixture or bounded Windows captures; it does not modify
the old auditor. Observation integrity and protocol success are separate
fields, including failed official rollback. Every claimed packet endpoint,
trial count, sample, ID reservation, operation and terminal flag is linked
to the raw journal. Invalid or unhandled stopped prefixes remain rejected
observations, never presumed complete executions.

The fixture release retains 17 whole-protocol cases, seven real local
subprocess cases and three historical development captures in lossless ZIP
archives. Each archive is freshly extracted and all original bytes checked;
current protocol cases are independently audited against the frozen lock.
Protocol fixtures forbid process and socket APIs; only the separate local
process probes launch deterministic output/sleep helpers. Host power requests
are mocked. Negative development captures remain negative under their saved
source versions, not rewritten with current passing flags:

- The initial fake Compose replacement incorrectly retained the previous
  container's trace history. Runtime correctly rejected stale ST3 on official
  service. The fake now distinguishes recreate from restart.
- An early audit used floating-point epoch conversion and rejected an equal
  prior approval timestamp after rounding. Integer timedelta conversion fixes
  that arithmetic; the approval threshold is unchanged. Settling records also
  use integer nanoseconds instead of floating-point subtraction.
- After host admission was added, a timeout fake accessed a command name
  before any network command existed. The saved attempt has zero assignments
  and no switch. The fake now handles this pre-command state explicitly.

These are development defects, not network observations or evidence that R4
works in the sandbox. The measured R3 rejection, original eight-scope audit
rejection, R2 rejection, Phase 7 failed recovery/MTTR dataset, P1 gap and D1
shared-host limitations remain unchanged. A later approved measured gate must
be assessed separately before any recovery, new campaign or TNSM claim.
