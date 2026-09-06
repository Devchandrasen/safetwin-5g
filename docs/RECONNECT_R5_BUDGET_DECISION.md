# R5 timing/inventory component passes; full recovery runner remains pending

Date: 2026-09-05 UTC. This is a **software/fixture component** decision, not
four-trial execution, measured recovery, official rollback or TNSM readiness.
Recovery validation remains the sole in-progress roadmap item.

## Verified evidence

`evidence/verification/20260905T235320Z-reconnect-r5-budget` retains
**766 passing tests, 200 subtests, 41 passing checks and 32 synthetic cases**.
The new component contributes 53 tests. Thirty-one raw integrity audits pass,
including rejected health/settling outcomes. The journal-fsync case explicitly
rejects integrity with `journal storage failed; no durability claim`.

The five-source lock `config/experiments/reconnect-r5-budget-lock.json` has
SHA256 `b730c374485d3f5666e19efebb33cd2323648ed1c9f6af05d028810a5fb031f8`.
It binds the unchanged collector and transitive host/process/journal/clock
and historical locks. The exact source ZIP precedes tests; every fixture ZIP
is freshly extracted and independently replayed. Sources and all raw logs
have hash manifests. The scoped `-text` attribute preserves captured bytes.

Before/after read-only metadata checks passed with unchanged five-container
official identities, health, isolated scope, idle query and no R5 receipt.
Original R4 negative observation replay, R3 build provenance and the frozen
statistical lock pass unchanged. These checks do not recapture native clock
observations or confer network timing acceptance. There were zero new packet
trials, image mutations, restarts or actual power requests.

## Preserved development failures and root-cause fixes

All directories below are under `evidence/verification/` and retain exact
pre-test sources, stdout/stderr, case ZIPs and original result flags.

| Capture | Original verification result |
|---|---|
| `20260905T234013Z-reconnect-r5-budget` | Failed: 4 tests failed, 45 passed; four fixture assertions failed |
| `20260905T234710Z-reconnect-r5-budget` | Passed: 50 tests, 32 cases |
| `20260905T234921Z-reconnect-r5-budget` | Failed: 3 new adversarial tests failed, 50 passed; 32 ordinary cases passed |
| `20260905T235132Z-reconnect-r5-budget` | Passed: 53 tests, 32 cases |

Debug report, using the repository-scoped `investigate` workflow:

- Symptom: the last health-poll timeout assertion failed in four boundary
  fixtures. Root cause: it confused the anchor-relative `timeout_ms` with the
  time remaining at dispatch. The retained row has 3999 ms from its previous
  anchor, but its timer is 1.998995 seconds after the two-second wait is charged.
  Fix: assert exact anchor/deadline/timer arithmetic and reject a timer renewed
  after the wait. Neither runtime timing nor its 50-second limit was relaxed.
- Symptom: three adversarial replays were incorrectly accepted. Root cause:
  individual anchor checks did not enforce order between all helper counter
  reads, and boolean `True` compared equal to poll number 1. Fix: independently
  replay admission/poll/wait/final reads in call order with a persistent failed
  counter latch, and require an integer poll number. The failing tests precede
  the auditor correction; the same tests and full suite now pass.
- Regression source: `tests/test_reconnect_r5_budget.py`, `check_case` and
  `test_raw_budget_tamper`. Status: **DONE** for these reproduced software
  defects. No claim that historical R4 timing or network recovery was fixed.

Fresh release replay checks original failure preservation separately from
current raw-observation integrity. It must not change either failed development
report to passed or regenerate an old capture using corrected source code.

Release evidence `evidence/engineering/20260906T000058Z-reconnect-r5-budget-release`
passes fresh extraction and byte verification for all **160 cases across the
five captures**, with candidate construction/acceptance disabled. Both failed
development results remain false. Its first staged-byte check covers 210
files; final staging is checked again after adding this release record.

## What the count model proves, and what it does not

The prospective model enumerates 216 cleanup points. If the future actual
runner stops normal admission at 768 and implements exactly that inventory,
the bound is **768 + 216 = 984**, leaving 40 of 1024 points. This is conditional
software arithmetic, not a measured or implemented full-run cleanup proof.
The nominal normal path needs 741 points. The unpruned upper envelope needs
1895, exceeding 768; four complete trials are therefore **not guaranteed**.

Health reserves all 26 possible points before its first command, uses at most
25 polls and 24 two-second waits, and requires fresh terminal evidence inside
one nonrenewable 50-second deadline. Settling requests 5000 ms once and requires
at least five observed seconds and an accepted terminal. The original global
1500-second admission, 35-second command, 120-second collection, 1 ms clock
residual, 100 microsecond bracket and packet-ID bounds remain unchanged.
Synchronous callback/filesystem stalls are observed failures, not hard-real-time
guarantees. Cleanup after global admission closes does not prove a protocol
completed within 25 minutes.

Next is the **full four-trial software runner and independent whole-protocol
replay**: exact committed approval and one-attempt receipt/ledger binding,
actual point inventory, one global clock/command cursor, every scope/telemetry/
fresh-PDU/trace/first-packet/fault check and every independently attempted
official rollback branch. Standalone component journals must not be sliced or
renumbered into a claimed whole-run audit. A separate complete execution lock
must pass and be committed before a later diagnostic decision.

The baseline win, rejected 675-unit campaign, negative R2/R3/R4 results and
P1/D1 limitations remain unchanged. No dataset-v2a, confirmatory BRACE result,
model promotion, new long campaign, hardware/operator claim or publication
submission is enabled by this component.
