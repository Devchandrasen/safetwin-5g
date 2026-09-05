# R5 collector component passes; recovery remains unverified

Date: 2026-09-05 UTC. The separate collector passes its **software/fixture
component gate**. Recovery validation remains the sole in-progress roadmap
item. No new network diagnostic, measured packet result, power request or
native clock observation ran. This is not the full runner or a TNSM result.

## Verified checkpoint

`evidence/verification/20260905T224927Z-reconnect-r5-collection` retains
**713 passing tests, 200 subtests, 47 passing checks and 38 synthetic cases**.
The new component contributes 64 tests. The five-source lock
`config/experiments/reconnect-r5-collection-lock.json` has SHA256
`3f10ad67b9b2af7b643f8c3fe4bf33084a99f71827b9dbabb6e81d02de0cf352`.
It binds the unchanged host/process/journal/clock and transitive older locks.
No frozen source or old measured observation was patched or monkey-patched.

The earlier development capture
`evidence/verification/20260905T224659Z-reconnect-r5-collection` retains
55 passing tests and 35 cases, with exact earlier sources. Final expansion
adds normal/cleanup capacity boundaries, rejected terminal-bracket coverage,
inclusive source-interval edges and one-nanosecond-outside rejection, durable
reservation-before-dispatch and failed-header preservation. No unexpected
development or final regression test failed in this component gate.

The first subsequent release-byte audit did fail. Its exact pre-correction
sources, full reproduced traceback and eleven differing working/index byte
pairs are retained at
`evidence/engineering/20260905T225717Z-reconnect-r5-release-bytes`.
Every difference was solely Git CRLF-to-LF normalization: the new collection
folder lacked the `-text` rule already used for other self-hashed evidence.
One scoped `.gitattributes` rule preserves its original bytes. No captured log,
manifest, result, source lock or old observation was rewritten. Re-staging
and release-byte replay are required before commit. The preservation verifier
also reruns the complete test suite after this configuration correction.

Debug report: symptom, staged bytes differed; cause, missing collection-folder
byte-preservation rule; fix, one `.gitattributes` line; regression procedure,
`tools/verify_reconnect_r5_release_bytes.py` compares every staged file to disk
and reruns the same rejecting release audit. The `--expect-mismatch` capture
retains the negative pre-correction result, not a successful release claim.

A further release attempt at
`evidence/engineering/20260905T225811Z-reconnect-r5-release-bytes` still
rejected those eleven files: ordinary `git add` retained the cached index
content despite the corrected attributes. Its full failure and differing
byte pairs are also retained. `git add --renormalize --` restricted to the
two new collection verification folders reapplies the new `-text` rule and
copies the original CRLF bytes into the index without modifying disk files.
Both raw and staged sample files then report CRLF with `text` unset. This
follows the [Git add re-clean option](https://git-scm.com/docs/git-add) and
[text attribute rules](https://git-scm.com/docs/gitattributes), not a change
to evidence serialization. A fresh all-file release audit remains required.

All collector case generation uses invented packet/log/clock records with
child, socket and native DLL entry denied. ZIPs are freshly extracted, their
member bytes verified and raw journal, ledger, process and collection records
independently replayed. Thirty-seven final cases pass integrity, including
rejected collection outcomes. The deliberately failed ledger-fsync case
rejects integrity with `identifier ledger storage failed; no durability claim`.
Its reserved ID is consumed and zero collection commands dispatch. Failed
storage is not converted into a successful durability result.

Adverse cases preserve missing first-packet traces, idle first-packet loss,
ineligible source, reused/foreign IDs, saturated/empty/lost prefixes, changed
images or restart context, forbidden official traces, elapsed clock jumps,
malformed source dates, stderr/status/UTF-8/timeout failures, host clock/source
failure, rejected admission/deadline/terminal timing and transport exceptions.
Three official windows with invented 15/15 yield only a packet-delivery
candidate. Invented 14/15 and changed context do not. Both rollback and
network-fix flags remain false in every case.

## Prospective contract and limits

Every attempt reserves one unique ID durably before its first command; failed
attempts do not reuse an ID. Exclusive files are retained, not overwritten or
deleted. Ninety-nine reservations exhaust the range without wrapping. A
seven-command precheck rejects invalid source/image/prefix before packet
dispatch. First packets and all five sequences remain in the accounting.

A complete window requires **16 new journal points**: fifteen process
endpoints and one post-parser terminal. With two standalone bootstrap points
the complete fixture uses 18. Exact boundary fixtures end at 768 normal and
1024 cleanup points; the final 256 remain reserved for cleanup. This does not
prove the four-trial worst-case inventory fits. A nonrenewable 120-second
window charges shared-anchor overhead and requires the full next 35-second
budget before dispatch. Closure failures cannot retain a positive collection
flag, even if the raw packet parser had already returned a result.

Source elapsed checks use raw parent GO/completion observations, an unchanged
1 ms tolerance, integer runtime and independently derived rational replay.
Arbitrary epoch skews are not estimated away; no host/source epoch equality
is claimed. The completion tick is observed, not exact child exit time.
Synchronous OS/fsync stalls, power loss and user/lid sleep remain possible.
Future operation admission must recheck real same-domain elapsed deadlines.

The collector cannot authorize or suppress outer official rollback. Cleanup
mode permits reserved capacity, not successful verification after rejected
timing. The future runner must independently attempt all mandatory image,
reset, health, fresh PDU, packet, telemetry and scope branches despite earlier
failure. Whole-run replay must retain all noncollection process records and
the complete global journal; slicing/renumbering to use this standalone audit
is not valid full-protocol evidence.

## Read-only prerequisites and next gate

Before/after minimal metadata checks pass for the same five healthy official
containers, unchanged image/ID/start identities, expanded idle query and no
R5 runtime receipt. These use the old bounded client only for metadata, not
new R5 timing acceptance. Original R4 negative replay, R3 build provenance
and statistical locks pass unchanged. No Docker mutation, measurement ping,
restart, image rebuild, actual power request or native clock recapture ran.

Next is the remaining **software-only four-trial runner and independent
whole-protocol replay**, including normal/worst-case capacity, global/health/
settling deadlines, exact committed approval and persistent prior-attempt
guards, plus all independently attempted official rollback branches. That
full integration needs a committed execution lock before a later separate
diagnostic decision. This component authorizes no actual diagnostic.

The Phase 6 baseline win, rejected 675-unit campaign, negative R2/R3/R4
outcomes and P1/D1 limitations remain unchanged. No model promotion, new
long campaign, positive BRACE or TNSM-ready claim follows. Hardware, operator
and publication authority gates remain pending.
