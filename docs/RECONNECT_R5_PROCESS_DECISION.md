# R5 owned-client component passes; full protocol integration remains pending

Date: 2026-09-05 UTC. The separately named bounded process adapter and its
independent raw-capture auditor pass their **software/fixture component gate**.
This is not a network diagnostic, official rollback, full execution gate or
TNSM-readiness result. Recovery validation remains the sole in-progress item.

## Verified evidence

`evidence/verification/20260905T201840Z-reconnect-r5-process` records
**596 passing tests, 200 subtests, 30 passing checks and 21 retained cases**.
There are 33 new tests. The five-source lock
`config/experiments/reconnect-r5-process-lock.json` has SHA256
`97f529e39d4c40ba66a3f31c4ad6f0bfbca6348bb380f09065a7c08eda4cae0e`.
It binds the unchanged journal/native-clock contracts. Committed R4 execution
sources also bind the reused clock-free job/GO launcher and deterministic child.
No frozen runtime or acceptance predicate was changed or monkey-patched.

Twenty cases use synthetic clocks with real, owned, hidden local child helpers.
They cover separate streams, capped flood, timeout, a pipe-holding descendant,
invalid UTF-8, nonzero exit, denied job assignment, unavailable timer, timer-wait
failures before/after GO, reported job-close failure, failed journal persistence,
QPC failure before/after dispatch, clock step, exhausted/reserved point budgets,
and an expired shared capture envelope. Each archive was freshly extracted,
byte-checked and independently replayed; raw failed captures remain failed.

Notable negative results are deliberately preserved:

- With QPC unavailable, normal dispatch is blocked. An explicitly allowlisted
  cleanup helper still runs under the kernel relative timer, but its timing
  result remains false. A stuck cleanup helper with the same failed QPC source
  reaches the 500 ms fixture cutoff; the owned launcher and readers are reaped.
- A 32 KiB fixture output cap retains exactly 32,768 bytes and rejects the
  saturated capture. This smaller test cap does not enlarge the production
  1 MiB limit. Invalid UTF-8 retains original bytes and a negative decode flag.
- A captured exit 7 remains exit 7, even when byte/timing capture is complete.
  Capture completeness is not successful command execution.
- After injected fsync failure, both local helper commands still dispatch,
  but the durability auditor **rejects** the journal. The expected audit error
  is retained in the archive, not relabelled as observation integrity.
- After all 1,024 UTC readings are used, a cleanup helper can be attempted with
  bounded process handling, but no end timestamp is fabricated and its timing
  verdict remains false. An expired normal shared envelope sends no GO.

Tampering tests reject altered clock domains, GO containment, streams, point
references, integer types, deadlines/timer duration, allowlists and completion
claims. Independent replay remains functional with candidate methods disabled.

## Separate native shared-envelope observation

`native-shared-envelopes.zip` retains one fixed two-command local-helper capture,
not a repeat of the earlier 64-read clock smoke probe. Both owned commands exit
zero, with valid capture/containment accounting. They share the exact recorded
boundary between commands: two bootstrap points plus two terminal points,
**four points and six clock-pair comparisons** in total.

The maximum expanded UTC-read bracket is **10,500 ns**; the maximum absolute
residual endpoint is **11,000 ns**, within the unchanged 100,000 ns and
1,000,000 ns limits. Every point and both commands are retained; no warm-up,
replacement or favorable recapture occurred. The scope is
`native-owned-process-only`, still **fixture** evidence. These are local client
and clock observations, not network packets, PDU recovery, radio or hardware
measurements. They do not explain or repair the historical R4 clock flags.

The earlier development gate
`evidence/verification/20260905T201305Z-reconnect-r5-process` passed its initial
28 focused tests and 17 cases. Its exact sources and logs remain development-only,
not a substitute for the final gate. No unexpected development test failed in
this component gate. All older failed gates and source archives remain intact.

## Scope checks, limitations and next work

Before/after read-only snapshots verified the same five healthy official
services and unchanged image/container/start identities. The original negative
R4 observation, R3 build audit and statistical lock pass unchanged. No Docker
image application, restart, fault, measurement ping or actual sleep-inhibition
request ran. The frozen idle probe checks its existing campaign/reconnect names;
the future R5 host guard must explicitly include the new runner and cannot
claim general host exclusivity from that point-in-time query.

The kernel relative timer is a termination safeguard, not a replacement clock
for accepted data. No absolute/fitted timestamps are synthesized. Windows
relative timers exclude low-power time; user/lid sleep, scheduling starvation
and kernel/API failure can still prevent complete bounded evidence or cleanup.
Job/timer errors remain negative. Client termination cannot establish cancellation
of a Docker-daemon operation that was already accepted.

Next implement the separately named **host, collection and four-trial runner**
integration and independent whole-protocol replay, using this committed adapter
and the frozen journal. Required work still includes exact standing approval,
idle/exclusive guards, complete worst-case point inventory, fresh PDU and
source/prefix/first-packet checks, telemetry, every official-image/reset/health
rollback branch and the final 15/15 endpoint. The complete execution lock must
pass and be committed before a **later separate** diagnostic decision.

The parent recovery item stays open. No new long campaign, positive BRACE,
hardware/operator validation, publication submission or TNSM-ready claim follows.
Phase 6's baseline win, rejected 675-unit dataset and all R2/R3/R4, P1/D1 negative
results and limitations remain unchanged.
