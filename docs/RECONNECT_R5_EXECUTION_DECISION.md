# R5 full-protocol fixture integration passes; actual recovery remains open

Date: 2026-09-06 UTC. Evidence tier: **fixture**, not new network evidence.
The parent recovery-validation item remains the sole in-progress roadmap item.
TNSM disposition remains **no-go-data-quality**.

## Verified result

The full regression capture `20260906T012542Z-reconnect-r5-execution` passes
**826 tests, 200 subtests and eight additional checks**. Sixty tests belong
to the new whole-protocol suite. Checks verify the source-lock chain, default
test discovery, original R4 negative observation, redacted R3 build evidence,
statistical lock and before/after read-only metadata. All five official
container identities remain unchanged. No new network trial, packet probe,
image application, service restart, actual power request or native clock
observation was executed.

The [lossless release](../evidence/engineering/20260906T013154Z-reconnect-r5-execution-release/release.json)
contains seven verification archives, including original failed sources and
logs. Its final archive was freshly extracted and independently replayed with
candidate acceptance, process launch, sockets and native APIs disabled.
Thirty-three distinct protocol cases cover complete and stopped executions,
approval/ownership failures, clocks, packet/trace failures, independent
rollback failures and storage faults. Storage-failure cases explicitly reject
integrity rather than claiming durability.

The twelve-source execution lock is
`config/experiments/reconnect-r5-execution-lock.json`, SHA256
`c51512faa71b2c6d53271d68b79c34c60276358e9d0f3d406e4dbc46732c09e9`.
It binds the unchanged budget/collector/host/process/journal/clock and earlier
source locks. The separate whole-run adapters retain full global command and
journal numbers; they do not slice and renumber standalone component inputs.

The nominal full fixture replays **770 commands, 33 packet windows, 340
steps and 835 shared clock points**. The normal prefix uses 741 points and
final cleanup 94, inside the frozen 768 normal/1024 total limits. The
216-point worst-case cleanup count remains a prospective upper bound, not an
assertion that every possible normal trajectory can complete four trials.

| Invented fixture assignment | Post-exposure packets | 15/15 recovery |
|---|---:|---|
| control-before | 15/15 | yes |
| drop-a | 14/15 | no |
| drop-b | 14/15 | no |
| control-after | 15/15 | yes |

The drop observations are fully accounted negative diagnostic outcomes.
Approved restoration ladders and final official 15/15 restoration succeed in
that fixture only. No first packet is omitted. This is NOT a successful
network-fix result, measured recovery, or a BRACE/TNSM contribution.

## Preserved development outcomes

Each name below denotes an exact ZIP inside the linked release directory;
the original expanded local directories also remain intact. No failed report
was replaced by a later passing report.

| Verification capture | Original outcome |
|---|---|
| `20260906T005817Z-reconnect-r5-execution` | 1 passing runner smoke test; no whole-run audit claim |
| `20260906T010430Z-reconnect-r5-execution` | 1 failed test: aggregate JSON sent to the component's 1 MiB reader |
| `20260906T010546Z-reconnect-r5-execution` | 1 passing complete runner plus independent replay test |
| `20260906T010706Z-reconnect-r5-execution` | 9 failed, 41 passed: empty rejection logs, missed fixture fault injection and suppressed image cleanup |
| `20260906T011214Z-reconnect-r5-execution` | 50 passed after the scoped corrections |
| `20260906T011933Z-reconnect-r5-execution` | 58 passed, 1 deselected by the provisional native-name filter |
| `20260906T012542Z-reconnect-r5-execution` | 826 tests and 200 subtests passed, no deselection; all eight checks passed |

## Debug report and regression evidence

Status: **DONE_WITH_CONCERNS** for software integration. Actual execution and
scientific gates remain pending. The `investigate` workflow required tracing
each failure to its cause, retaining pre-correction bytes and verifying the
scoped fix against the full suite. Global skill telemetry/settings were not
changed.

- Aggregate evidence repeats raw records in component snapshots and exceeds
  1 MiB. The separately bounded aggregate reader accepts at most 128 MiB and
  rejects duplicate keys/nonfinite values. Frozen process byte limits and
  timing predicates are unchanged.
- A rejected approval can legitimately leave an empty execution-event file.
  The auditor now accepts zero events only as an empty sequence, not missing
  positive evidence; its full cursor still rejects any claimed work.
- A fixture one-shot flag was consumed before the official-service failure
  injection. The trigger is now case-specific; the original false-positive
  fixture output remains in its failed archive.
- A clock-rejected tag read previously suppressed official image replacement.
  Emergency cleanup now separates strictly bounded tag bytes from timing
  acceptance. It still rejects unknown image identity, timer/job/reader/byte
  failures and nonzero exit. Only clock-journal errors may be separated.
  Timing/durability/rollback failures remain negative. Independent tests prove
  both image branches, all reset/health targets and all final packet/telemetry
  windows are attempted despite earlier failures.
- A later default collect-only check discovered historical source snapshots
  and produced import-name conflicts. `pytest.ini` now scopes discovery to
  `tests/`; the frozen `pyproject.toml` is unchanged. One generated bytecode
  file is explicitly listed as an auxiliary post-capture artifact in the
  earliest archive. Original manifests, source bytes and captures are not
  rewritten to hide it. The final default-discovery check passes.

Rehashed packet, dispatch-time, command-scope and cleanup-label tampering is
rejected after consistently updating duplicate records and outer hashes.
Independent replay remains operational with candidate entrypoints disabled.
Clock-consistency rejection cannot be cleared by later good points.

## Next permitted stage

This release has **no network CLI** and explicitly refuses non-fixture mode.
Its approval and prerequisite providers are synthetic. Do not call this
fixture runner with a real transport and then relabel its zero-action result.
It is not an actual committed-revision/approval-file admission implementation.

Next is a separately versioned native-admission/invocation variant and matching
independent audit, tested without real actuation first. It must bind actual
committed bytes, exact prior approval, the persistent receipt and current
scope/prior-attempt checks. Keep this twelve-source freeze unchanged. Only a
later separately committed execution decision may assess one diagnostic.
No network rerun, long campaign, dataset salvage, model promotion or positive
paper claim follows from this fixture pass. Hardware/operator/publication
still require new external authorization.
