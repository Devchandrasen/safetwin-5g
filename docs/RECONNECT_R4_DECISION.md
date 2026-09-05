# Reconnect R4: rejected before exposure, later official service observed

Date: 2026-09-05 UTC. Disposition: **not accepted**. Investigation status:
**DONE_WITH_CONCERNS**, not a recovery fix. The parent recovery item stays open.

## Actual attempt and authority

The once-only R4 attempt used committed source checkpoint
`0749ac1ae8cf7cfddb4dd9c0dac069996b7aa064` and the unchanged 15-source execution
lock `safetwin5g-reconnect-r4-execution-v1`, SHA256
`122b2285104c407eb68bbcb5e7183adc06c25e16c45e91e868dade95425a4da6`.
The eight-source collection and 74-source R3 locks remain unchanged.

The sealed read-only preflight at
`evidence/engineering/20260905T165847Z-reconnect-r4-preflight` passed with
mutations disabled. The exact approval at
`evidence/engineering/20260905T170101Z-reconnect-r4-approval/approval.json`
records the existing standing user authorization at
`2026-09-05T17:01:01.226404+00:00`. The assistant recorded it under that
authorization; it is not an operator signature or new external authority.
Its scope was the pinned isolated diagnostic and mandatory official rollback.

From the authoritative repository, with `PYTHONPATH` containing its `src`
and repository root, the Python 3.12.10 executable recorded in the approval ran:

```powershell
python sandbox/run_reconnect_r4.py --execute --approval evidence/engineering/20260905T170101Z-reconnect-r4-approval/approval.json
```

The immutable sealed attempt is
`evidence/engineering/20260905T170131Z-reconnect-r4-network`.
It contains **55 command records, comprising 54 Docker commands and one Git
command**, one attempted assignment, zero valid assignments, zero packet
samples, and zero control/fault exposures. The original summary field named
`actual_docker_commands_executed` counts all 55 records; that naming defect is
disclosed here, not rewritten in the original artifact. Candidate image
application occurred, but the first trial stopped before preparation or baseline.
No experimental qdisc fault was injected. Image replacements and the automatic
rollback resets did interrupt the software radio service.

## Failure chain and original rollback

Three commands returned CLI status zero but failed the frozen one-millisecond
inter-command wall/QPC consistency check:

| Record | Command role | Wall delta minus QPC delta |
| --- | --- | ---: |
| 25 | First trial container scope | -1.0968 ms |
| 36 | Official-image verification | -2.5100 ms |
| 51 | UE health during official reset | -3.5207 ms |

The first flag stopped the diagnostic. Automatic cleanup then applied both
official images and independently restarted core, gNB and UE. The third flag
interrupted the UE health wait while its raw status was `starting`. At the last
original scope capture the other four services were healthy and UE was still
`starting`. Thus the original **official-image restoration and final-service
restoration verdicts are both false**. These flags are not changed by later
observations. The owned host guard recorded successful sleep-inhibition enable
and clear; its runtime lock was released. No retry was launched.

The frozen independent whole-protocol auditor successfully replays this failed
path, including the failed rollback. Audit success means the negative record is
internally consistent, not that the protocol succeeded. Invoke that frozen
auditor as a module from the root:

```powershell
python -m tools.audit_reconnect_r4_execution --run evidence/engineering/20260905T170131Z-reconnect-r4-network
```

A direct file invocation without the root import path produced
`ModuleNotFoundError: tools` during diagnosis. The module invocation above
works without editing the frozen auditor. This invocation issue did not cause
the network attempt's failure.

## Separate read-only aftercare

`evidence/engineering/20260905T170620Z-reconnect-r4-aftercare` is a later,
one-shot **read-only service observation**, not an R4 retry or amended rollback.
Its 18 exact commands perform no image switch, reset, fault, qdisc clear,
clock change or sleep-inhibition request. Packet identifiers 10091-10093 are
separately reserved before the three five-packet commands.

Independent replay verifies both five-container internal scopes, unchanged
official UE/gNB identities, source `10.45.0.2`, **15/15 replies**, neutral
`uesimtun0`/`eth0` qdiscs, a running UPF, no stress workers and all three
Prometheus jobs up. The UE log has an unchanged prefix from the original reset
and these fresh post-reset markers:

- Initial registration successful: `2026-09-05T17:02:26.784963714Z`.
- PDU session PSI 1 successful: `2026-09-05T17:02:26.995445290Z`.
- `uesimtun0`, `10.45.0.2` up: `2026-09-05T17:02:27.001257308Z`.

Both radios use official image
`sha256:13705fc29922cf019e8c7992b5b04b9c6c584d3848d29689f1d3db64334ae725`.
UE ID is `ba6d082e924c6ea6ed50fe98909fe1bd9f8efcd880e87cd58c8e1fb663071cda`;
gNB ID is `687b3efdae32e2ce9dac190e1c692e0b01c0a74b037fa18c15c7535ead299305`.
No additional reset occurred between the failed run and this observation.
These are Docker-source log timestamps, not a cross-clock recovery-latency
estimate. This observation does **not** satisfy the frozen R4 clock audit or
retroactively change either rollback flag.

## Clock investigation: confirmed gap, unresolved historical cause

The raw-first investigation found a compatibility gap in the frozen supervisor:
the monotonic side uses high-resolution QPC, but the wall side still uses
Python 3.12 `time.time_ns()`. This host reports its implementation as
`GetSystemTimeAsFileTime()` and nominal resolution as 15.625 ms, exceeding the
one-millisecond predicate. The adapter validates QPC properties, but not this
wall-clock prerequisite. The exact [CPython 3.12.10 implementation](https://raw.githubusercontent.com/python/cpython/v3.12.10/Python/pytime.c)
confirms the Windows API. The [official Python 3.13 change notes](https://docs.python.org/3.13/whatsnew/3.13.html#time)
describe the later change to `GetSystemTimePreciseAsFileTime`. No Python upgrade
or clock-setting change was made.

The later local probe at
`evidence/engineering/20260905T170956Z-reconnect-r4-wall-clock` retains 1,000
raw samples of both APIs, each bounded by QPC reads. Its independent replay
uses interval bounds, never midpoints or an estimated epoch offset:

| Later clock | Adjacent comparisons beyond 1 ms | Maximum distance outside QPC bracket |
| --- | ---: | ---: |
| Python wall clock | 0/999 | 288,400 ns |
| Precise UTC API | 0/999 | 0 ns |

**The later probe did not reproduce the historical failure.** A deterministic
fixture demonstrates that coarse quantization alone can violate the point-read
predicate without an actual wall-clock step. It establishes a counterexample,
not the cause of any of the three historical flags. Scheduling between
unbracketed reads and real clock adjustments remain possible. The old error
text `observed host inter-command clock step` must not be read as proof that
Windows time was adjusted. No missing timestamp is inferred or repaired.

Microsoft distinguishes [precise UTC timestamps from QPC interval measurements](https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/nf-sysinfoapi-getsystemtimepreciseasfiletime).
A prospective revision should validate its exact API/runtime, record UTC reads
inside QPC brackets, reject ambiguous or over-wide brackets, and independently
test real forward/backward steps and scheduling delays. The remedy is not to
relax the one-millisecond threshold, suppress a flag, or edit/retry R4.

## Verification and next gate

`evidence/verification/20260905T172149Z-reconnect-r4-observation` records
**425 tests, 200 subtests and twelve passing verification checks**. The 27 new
tests include raw-byte and re-sealed tampering, wrong images/scope, missing or
duplicated replies, prefix loss, claim promotion, FILETIME conversion, bracket
ordering and the no-clock-step quantization counterexample. Independent replay
checks the original rejection, later service and local clock probe separately.
Committed execution/collection locks, original R3 observations/build and the
statistical lock pass. Final bounded read-only checks found all five services
healthy, both official images present, no active experimental runner and no R4
runtime lock. Tests and replay do not constitute another network experiment.

The investigate skill required raw evidence and a testable hypothesis before
any fix. Accordingly, no frozen runtime was modified. Its global setup/sync
writes were omitted to keep this work within the authoritative repository.
Project learning: high-resolution elapsed timing does not establish adequate
wall-clock resolution or identify clock steps from unbracketed point reads.

Next: a separate, versioned **software-only clock-source/bracket contract and
independent adversarial audit**, followed by a new gate decision. Do not rerun
R4, rebuild the trace tag, change old source locks, pool rejected data, or
launch another 675-unit campaign. Recovery remains unvalidated. The actual
records are `sandbox-measured` with `simulated` radio; regression fixtures stay
`fixture`. No hardware, operator, positive BRACE or TNSM-readiness claim follows.
