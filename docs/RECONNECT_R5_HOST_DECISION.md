# R5 host component passes; whole-protocol integration is pending

Date: 2026-09-05 UTC. The separate host admission/owned-lifecycle component
passes its **software/fixture gate**. Recovery validation remains the sole
in-progress roadmap item. This is not measured sleep inhibition, network
recovery, official rollback, full execution admission or TNSM readiness.

## Verified checkpoint

`evidence/verification/20260905T211731Z-reconnect-r5-host` retains
**649 passing tests, 200 subtests, 36 passing checks and 27 host cases**.
The new component contributes 53 tests. The five-source lock
`config/experiments/reconnect-r5-host-lock.json` has SHA256
`9d50ac6cb85f6a13ecd373a4a6c4f3add86eb23a3b5941ea330fcf18a48671a9`.
It binds the unchanged process/journal/clock and transitive older contracts.
No frozen source or old observation was patched or monkey-patched.

Each host case uses a fake idle transport, fake power API and synthetic clock.
Process creation, sockets and native DLL entry are denied during generation.
The successful case uses seven points: two bootstrap, three normal host
operations and two cleanup observations. This only establishes the host
component inventory, not the four-trial worst-case inventory.

The 27 retained cases cover busy/empty/error queries, client timeout and
transport exception; an existing receipt; power create/set/clear/close
failures and interruption; failed QPC, thrown UTC source, changed clock domain,
wide/discontinuous brackets; expired admission and late power return; reserved
or exhausted point capacity; and journal/receipt persistence failures. Every
archive was freshly extracted, byte-checked and independently replayed.

Twenty-four cases pass their independent integrity audit, including rejected
host admissions and failed cleanup. Three deliberately reject integrity:

- Failed journal fsync: `journal storage failed; no durability claim`.
- Failed receipt header/footer: `receipt storage/ownership failed; no durability claim`.

These are expected negative audits, not converted into positive durability
claims. All host cases still attempt both cleanup callbacks. After a power
clear exception, owned handle-close is attempted; after failed timing or
power cleanup, owned receipt-close is attempted. Successful dispatch does
not establish API success, timely completion, durable output or service recovery.

The earlier development capture
`evidence/verification/20260905T211416Z-reconnect-r5-host` passed its initial
48 tests and 26 cases. Its exact sources and logs remain development-only.
The final expansion adds thrown-source, lifecycle/domain, static boundary and
receipt-return tampering checks. No unexpected development test failed in
this component gate. Earlier failed gates remain unchanged.

## Prospective changes and explicit limits

An exclusive, fsynced attempt receipt remains present after normal close,
blocking an accidental second attempt. Neither stale nor completed paths are
deleted or replaced. Tests verify that a second acquisition leaves the exact
original bytes unchanged. The existing-receipt fixture archive includes only
its deliberately invented sentinel input, not an actual private runtime lock.
The production helper does not read/export an unowned receipt.

The idle query now covers R5 and future numbered reconnect runners and rejects
unreadable Python command lines. It requires an exact success marker and a
complete zero-exit/no-stderr capture. This is still a point-in-time process-name
check, not host-wide CPU/scheduler exclusivity or exclusion of other tools.

Power handling uses a separately owned `PowerRequestSystemRequired` object
and independently clears/closes only that handle. It does not modify another
thread-wide sleep request, display/away mode or global policy. Fake ABI tests
verify the 64-bit union layout and API arguments; **no actual power request
or native power smoke test ran**. The old R4 power events are unchanged.

All elapsed checks use the same raw QPC domain, with shared UTC/QPC anchors,
charged overhead and no replacement readings. The 35-second admission and
two-second cleanup bounds concern observed callback returns. Synchronous
kernel/filesystem calls cannot be forcibly cancelled by these checks; a
stalled API, scheduler or post-capture fsync can exceed them. The future
runner must recheck its actual deadlines before admitting any next operation.

User/lid sleep and power loss remain possible. The documented Modern Standby
DC request-expiration limitation also requires an explicit later prerequisite
assessment. The host component does not measure AC/standby state or claim
continuous availability. The exact revision field is linkage, not validated
standing-user approval or an operator signature.

## Read-only checks and next gate

Before/after minimal checks pass for the same five healthy official services,
unchanged container/image/start identities, the expanded R5 idle snapshot and
absence of an R5 runtime receipt. The older bounded client is used solely for
these metadata snapshots, not as R5 elapsed-time acceptance evidence. Original
negative R4 replay, R3 build provenance and statistical locks pass unchanged.
No Docker mutation, restart, measurement ping, image rebuild, clock setting,
native clock recapture or actual sleep-inhibition request ran.

Next implement the **remaining R5 collector/runner and independent whole-
protocol replay**, using the frozen components. Complete the prospective
normal/worst-case cleanup point inventory; exact approval and prior-attempt
checks; source/prefix/first-packet/fresh-PDU/telemetry/scope checks; both official
image replacements; all three reset/health branches; and final official 15/15.
That full integration needs its own committed execution lock before a later
separate diagnostic decision. The current stage authorizes no real diagnostic.

The Phase 6 baseline win, rejected 675-unit campaign, R2/R3/R4 negative results,
P1/D1 limitations and hardware/operator/publication authority boundaries remain.
No new long campaign, positive BRACE result or TNSM-ready claim follows.
