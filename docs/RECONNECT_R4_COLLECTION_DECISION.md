# R4 collection software gate passed, network execution still pending

Date: 2026-09-05. The separate R4 collector, independent auditor, prospective
protocol and eight-source lock pass their **fixture-only implementation gate**.
This is not a completed recovery pilot or a measured network correction.
No new network trial, fault, restart, image application or clock change ran.

Verification: `evidence/verification/20260905T143948Z-reconnect-r4-collection`.
All eleven checks passed, including **381 tests and 171 subtests**, the R4
source lock, the unchanged committed 74-source R3 lock, original source/build
audits, negative R3 observation/clock replay, and the frozen statistical lock.
The original complete R3 protocol auditor still rejects with
`eight required scope snapshots`; that expected rejection is preserved.

## Retained fixtures, not measured packets

`evidence/engineering/20260905T144000Z-reconnect-r4-collection-fixtures`
contains fourteen cases, their raw synthetic commands, independent audit
decisions and a SHA-256 manifest. Process and socket creation were denied
during generation. There were zero actual Docker commands in these fixtures.

- Complete skewed and complete idle-loss traces pass collection accounting.
  The idle-loss fixture still fails packet-delivery completeness.
- Ineligible .3 trace source stops before ping; missing sequence-1 trace,
  source-clock step, saturated capture, partial command, changed container
  identity and an incorrect official image remain rejected.
- Official-service .3 traffic is explicitly not trace-eligible. A 4/5 service
  window is retained as a valid packet observation, not successful recovery.
- Three-window fixtures independently agree: 15/15 is a packet-only candidate;
  14/15 and an incorrect final image are not. None sets `rollback_verified`.

Tests additionally cover arbitrary positive/negative component skew, host
clock steps, nanosecond local reversal, prefix loss/rewrite, malformed or
duplicate records, fingerprint mismatch, reused/exhausted IDs, mismatched
source headers, altered commands/hashes/reports, and changed service context
between otherwise complete windows. An independent audit remains operational
with the runtime acceptance predicates disabled.

## Live environment checks, not another experiment

The separately retained read-only existing-scope preflight at
`evidence/engineering/20260905T144004Z-reconnect-r3-preflight` passed with
`mutation_enabled: false`, `candidate_image_applied: false` and zero trials.
It checks the exact isolated scope and existing pins, including CLI help,
not measurement pings or a resumption exposure. Additional minimal logging
inspection in the verification bundle confirms both official UE/gNB images,
running state, and supported default `json-file` configuration.

These metadata observations do not establish that the prospective live R4
adapter works. Only its in-memory collection algorithm is implemented here.
No old instrumented container/log was restored, reconstructed or re-timed.

## Next required gate

Implement and fixture-verify the separately versioned bounded live adapter,
runner and independent whole-protocol auditor described in
[the frozen R4 protocol](RECONNECT_R4_COLLECTION.md), then commit them before
any measured execution. Preserve the fixed first packets, explicit source
eligibility, raw telemetry, fresh registration/PDU, exact isolation, mandatory
approval and independently attempted official rollback. Actual recovery stays
pending until that full 15/15 measured chain passes. No replacement long
campaign follows automatically from collection software passing.

Phase 6 remains negative. R2 remains rejected at 14/15; R3 remains rejected
before exposure; the 675-unit study remains rejected with 582 failed
recoveries/censored MTTR. P1, D1 and instrumentation timing limits remain.
There is no new dataset-v2a, confirmatory BRACE result, TNSM-ready manuscript,
hardware/operator validation or live-actuation authorization.
