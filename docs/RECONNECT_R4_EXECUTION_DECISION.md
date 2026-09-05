# R4 execution software gate decision

Date: 2026-09-05. Decision: **software-fixture gate passed; measured R4 not run**.
The parent recovery-validation roadmap item remains the only item in progress.
This is not a network-fix, BRACE-confirmation or TNSM-readiness decision.

## Verified checkpoint

- [Protocol and limitations](RECONNECT_R4_EXECUTION.md): separately versioned
  Windows-owned job capture, exact approval and command scope, durable IDs,
  host admission, fresh registration/PDU, telemetry, restoration ladder and
  independent official rollback.
- [Execution source lock](../config/experiments/reconnect-r4-execution-lock.json):
  15 sources and the unchanged prior eight-source collection lock, which
  transitively binds the unchanged R3 dependencies.
- Verification:
  `evidence/verification/20260905T164055Z-reconnect-r4-execution`.
  **398 tests and 200 subtests passed**, plus all **12 verification checks**.
  The suite used the existing repository Python 3.12 virtual environment and
  an explicit project `src` import path. Commands, versions, stdout/stderr,
  times and hashes are retained.
- Lossless artifact release:
  `evidence/engineering/20260905T164133Z-reconnect-r4-execution-fixtures`.
  **17 protocol cases**, freshly extracted and independently replayed, and
  **seven local subprocess cases**, including timeout, output cap, inherited
  child-pipe cleanup, invalid UTF-8 and denied Windows Job assignment.
  Three exact historical development captures are archived without deleting
  their original local directories.

Only the invented complete protocol has four valid assignments. Its fake
post-delivery counts are **15/15, 14/15, 14/15, 15/15**. The two losses remain
losses; complete diagnostic accounting is not successful recovery. Sixteen
other cases deliberately reject admission, baseline, collection, command or
final restoration. Failed cleanup, core reset, health wait and official image
replacement still attempt the remaining reset targets. Sleep-enable failure
and a busy-host snapshot produce no Docker commands; sleep-clear failure
prevents protocol success even with restored service.

The current source audit consumes raw commands, separate stream bytes/hashes,
prefixes, identities, source/clock brackets, packets, markers, telemetry,
approval and terminal verdicts. Tests reject resealed claim promotion, late or
wrong approval, altered rollback, omitted ID reservation and rounded recovery.
The old R3 complete-protocol auditor still rejects with the required-eight-scope
error. The independent R3 observation audit, published R3 build audit, original
R3 source/execution locks and Phase 7 statistical lock remain intact.

## Preserved failed software gate

The first complete gate at
`evidence/verification/20260905T163556Z-reconnect-r4-execution` is **failed**.
Its fixture release at
`evidence/engineering/20260905T163558Z-reconnect-r4-execution-fixtures` is also
**failed**, despite its 17 protocol cases passing. The separate descendant
probe failed because adding hidden-process flags removed the intended
inherited pipes. The corrected helper explicitly passes stdout/stderr to its
hidden child; both unit verification and the retained fresh process capture
then verify the intended timeout/owned cleanup path.

Full test discovery initially used system Python without the package `src`
path and stopped with 19 import errors. Two read-only checks also rejected
healthy official services because the verifier compared JSON object order as
text and used the wrong Compose project label. Corrections use parsed JSON,
the existing `safetwin5g-sandbox` project name and the repository interpreter
with explicit `src` path. They do not change a network acceptance endpoint.
The initial complete source/lock bytes are archived at
`evidence/engineering/20260905T163900Z-reconnect-r4-gate-failure`.

Read-only local timing inspection additionally found Python 3.12's default
Windows `monotonic` clock uses GetTickCount64 at 15.625 ms. R4 now explicitly
uses the same high-resolution QueryPerformanceCounter-backed performance
counter for command, host, health and admission intervals. The recorded
resolution is 100 ns; the one-millisecond audit tolerance was not widened.
No host or container clock was changed. Integer timing is not an assertion
of common clock epoch or zero clock error.

## Actual environment and next gate

At the final read-only verification, both official UE/gNB services remained
healthy on image
`sha256:13705fc29922cf019e8c7992b5b04b9c6c584d3848d29689f1d3db64334ae725`,
with unchanged container IDs
`1d460cf00e44ca49d645c911d25db31e7b753d4b1b8b048a00d38726e57220ab` and
`616bc5ff04a5fb1c937c595bbd3bf5d95c66067884db2e7dd998bd46dd5ac6ad`.
All five SafeTwin services were healthy. The bounded process snapshot found
no active campaign/recovery/reconnect runner. These are current prerequisites,
not new UE registration, PDU, recovery or rollback measurements.

Before any later measured R4 attempt, verify committed byte equality and all
image/build/scope locks, absence of active jobs or unexplained runtime locks,
and exact revision-specific standing user authorization. Record the approval
before any application. Runtime must retain its no-retry, bounded four-trial
admission and independent outer-finally rollback. A Docker client timeout
does not cancel an already accepted daemon operation, and sleep inhibition
cannot prevent user/lid sleep or power loss. Failed or incomplete operational
evidence must remain negative and may require a separate observation audit.

No measured R4 approval or attempt was created here. Do not rerun R3, rebuild
the immutable trace image, relabel a fixture, increase collection caps, widen
the trace IP filter, salvage the rejected 675-unit dataset or start a new long
campaign from this result. R2/R3 rejection, Phase 6 no-go, Phase 7 recovery/MTTR
rejection, P1 pause-gap and D1 shared-host disclosures remain unchanged.
Hardware, operator validation and publication still require external authority.
