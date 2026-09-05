# R5 clock software gate passed; execution integration still pending

Date: 2026-09-05 UTC. **The prospective clock-source/read-bracket gate passes.**
This is not an accepted reconnect diagnostic, validated network correction,
BRACE result or TNSM-readiness decision. No new network trial was run.

## Frozen implementation and verification

The [R5 contract](RECONNECT_R5_CLOCK.md) and five-source
`config/experiments/reconnect-r5-clock-lock.json` freeze the native clock
primitive, independent rational replay, adversarial tests and verifier.
Lock ID: `safetwin5g-reconnect-r5-clock-v1`.
Lock SHA256:
`0e2b17156f3aab4d1b9fa8bdf48727561ea1f10051291746e754ac86009c6cf4`.
The old R4/R3 and statistical locks, original failed R4 manifest, later official
service manifest and original later clock-probe manifest are bound unchanged.

Verification: `evidence/verification/20260905T181844Z-reconnect-r5-clock`.

```text
493 passed, 200 subtests passed in 38.52s
```

All **twelve checks** pass. The 68 new tests cover independent interval
arithmetic, fractional counter frequencies, forward/backward steps, ambiguous
thresholds, cumulative/nonadjacent drift, wide or reordered reads, partial API
results, wrong sources/runtime/bitness, typed JSON, changed claims, sequence
exhaustion and the absence of network/process/clock-setting interfaces.
The independent replay continues working with candidate predicates disabled.

The gate retains **37 serialized synthetic cases: seven accepted sampled-clock
traces and thirty expected rejections**. They are `fixture`, not native clock
measurements. The accepted cancelling-step case explicitly demonstrates a
limit: an unobserved step and exact cancellation between reads is not
identifiable from finite samples. It is not a guarantee of clock stability.
Every expected negative case retains its raw input, candidate report and
separate audit. Full tests, transitive committed old locks, original R4 negative
observation, R3 build and statistical lock also pass their unchanged checks.

## Separate native local-host observation

The fixed 64-read API capture is in `native-clock.json` and the fsync-backed
`native-points.jsonl` journal inside the verification directory. It used
64-bit CPython 3.12.10, Windows 10.0 build 26200, precise UTC FILETIME and a
10,000,000 Hz QPC. All 64 raw reads and **2,016 pair comparisons** pass separate
rational replay. No read was replaced, discarded, used as an unreported
warm-up, or retroactively re-timed.

- Maximum expanded QPC read bracket: **17,500 ns**, below the fixed 100,000 ns cap.
- Maximum absolute endpoint of any conservative residual interval:
  **27,600 ns**, below the unchanged 1,000,000 ns tolerance.
- The entire interval, not its midpoint or mere overlap, must satisfy the rule.

This is `sandbox-measured` with the explicit scope **local-host-clock-api-only**.
It is not a radio, packet, service-recovery, timing-accuracy or hardware
measurement. Source/manifest hashes establish byte integrity, not independent
OS attestation. The source was fixed before this capture and is now frozen;
do not repeat the native probe to select a better result.

Before/after bounded read-only snapshots independently verify the same five
healthy services on the locked internal network and the same official UE/gNB
images and container/start identities. No active experimental runner or R4
runtime lock was observed. No image, service, qdisc, clock, system timer
configuration or sleep-inhibition setting was changed by this gate. These
metadata checks are not a fresh PDU or packet-delivery measurement.

## Preserved development failure

The first unit run had 59 passing tests and two setup/teardown errors. A
1 MiB malformed-JSON parameter was automatically embedded in pytest's test
identifier. Pytest then attempted to put that identifier in its current-test
environment variable, exceeding Windows' 32,767-character limit.

`evidence/engineering/20260905T181000Z-reconnect-r5-clock-development`
preserves the exact pre-correction source ZIP and the focused reproduction's
**2,100,658 raw stdout bytes**, exit 1, and three passing cases plus two errors.
The ZIP is lossless, not a shortened replacement for the raw error. The
original uncaptured full-run console is not presented as that later command.
Short explicit parameter IDs fix the harness while retaining the entire 1 MiB
test input. No timing endpoint or acceptance threshold changed to pass it.

## Debug report and next boundary

- Symptom: R4's unbracketed wall/QPC checks rejected trial admission and final
  rollback verification; a later probe did not reproduce those flags.
- Confirmed design gap: the old wall-clock resolution prerequisite and
  uncertainty between reads were not represented in its point predicate.
- Change: a separate native precise-UTC/QPC reader and conservative all-pair
  interval predicate with independently derived rational replay. No old source
  or rejection was changed.
- Evidence: no-clock-step counterexamples, 37 retained cases, 68 new tests,
  full regression logs and one fixed native API capture.
- Status: **DONE_WITH_CONCERNS**. The software gate passes; the historical cause
  remains unresolved and full network execution integration is unverified.

The investigate skill kept the change tied to a reproduced design
counterexample and required retained failures before correction. Its global
setup/sync, freeze-state, preference and learning writes were omitted to keep
this work repository-scoped. Project learning: an interval overlapping a
tolerance is not enough for conservative acceptance; require full inclusion
and check nonadjacent drift without claiming that finite samples identify
all clock changes.

Next implement and independently fixture-test a **separate R5 execution
integration**. It must use the one native QPC domain for command, host, health,
settling and admission budgets, retain every raw clock bracket, and fail closed
without suppressing mandatory safety rollback when timing admission fails.
Preserve fixed first packets, source eligibility, prefix continuity, byte/time
bounds, exact approval/scope, raw telemetry and fresh-PDU plus official 15/15
restoration checks. Do not monkey-patch frozen R4 code or silently substitute
this clock into an old run. That integration must have its own committed lock
and separate execution gate before any new image application or diagnostic.

The parent recovery item stays open. R4's original rollback flags stay false;
its later read-only 15/15 remains a separate observation. Phase 6's baseline
win, rejected 675-unit dataset, R2/R3 failures, P1 gap and D1 contention remain
unchanged. No new campaign, model promotion, hardware/operator validation,
publication submission or TNSM-ready manuscript is enabled.
