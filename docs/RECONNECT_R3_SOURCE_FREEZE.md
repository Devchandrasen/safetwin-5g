# R3 source and diagnostic contract freeze

Date: 2026-09-05. **Prebuild source/fixture gate passes. No R3 image has been
built or installed, and no R3 network trial has run.** The recovery roadmap
item remains open. This is not a recovery correction or TNSM-readiness claim.

The [R3 protocol](RECONNECT_R3_TRACE_PROTOCOL.md) fixes four diagnostic trials,
exact packet identifiers, seven observation stages, trace accounting, strict
controls, the unchanged 15/15 recovery endpoint, scoped approval, time budgets
and final official-image rollback. R2 remains rejected at 14/15. A complete
loss trace is deliberately distinct from successful packet recovery.

## Verified artifacts

`evidence/engineering/20260905T102301Z-reconnect-r3-freeze` contains the exact
three-file overlay and new header, source hashes, unified patch, executed
compiler inputs, stdout/stderr, official-container snapshots and manifest.
The previously retained upstream files pass their independent provenance
audit; they were not silently replaced by new upstream versions.

The independent source auditor removes the ten instrumentation blocks using
a separate line-based implementation. The three resulting files match the
retained R2 base byte-for-byte. It also applies the actual patch with Git in an
isolated temporary tree and checks all four resulting file hashes. Added code
consists of the reviewed bounded identity reader and seven logging calls;
no buffer, timer, retry, packet write or behavioral correction is introduced.
Source-removal equality does not claim zero observer overhead.

The compiled identity-reader fixture passes 65 cases covering short/invalid
headers, fixed-flow scope, fragmentation, identifier and sequence boundaries,
metadata parsing, read-only packet handling and logger behavior. A separately
constructed Python byte sequence reproduces the logged full-packet fingerprint.

Both uninstrumented and instrumented NAS fixtures pass the same 61 behavior
cases. The extra valid-IPv4 case observes four trace events: packet 1 enters
and takes the idle branch; packet 2 enters and takes the connected forwarding
branch. Only packet 2 reaches the fixture sink in both modes. These fixtures
use explicit test doubles, not the complete NAS/RRC scheduler or upstream ABI.
Real-source compilation is still required before any image acceptance.

`tools/reconnect_r3_trace.py` rejects incomplete, duplicated, inconsistent or
misidentified paths. A lost packet after gNB resource lookup remains
unlocalized. The helper is not a complete network auditor: log provenance,
capture saturation, command/window assignment, raw ping parsing, scope,
approval, exposure and rollback must still be implemented and independently
checked in the future runner/auditor pair.

`evidence/verification/20260905T102936Z-reconnect-r3` records:

```text
272 passed, 32 subtests passed in 6.38s
```

The R3 source audit, prior packet-diagnosis audit, R2 build and negative-network
integrity audits, and statistical source lock all pass. Regressions reject
image-build claim promotion, compiler-input drift, extra privileges, an
already-existing target tag, missing fixture traces and malformed blocks.

## Negative/tooling observations retained

The first independent patch replay rejected `replayed content digest`.
Read-only configuration inspection returned
`file:C:/Program Files/Git/etc/gitconfig true` for `core.autocrlf`. Repeating
the replay with command-scoped `git -c core.autocrlf=false apply` passed exact
byte hashes. The auditor now makes that option explicit; the user's global
Git configuration was not changed. This was a prebuild audit failure, not a
network result or permission to normalize historical evidence.

Compiler stderr retains `#pragma once in main file` warnings because the test
driver pastes the header into a single translation unit. All three executable
fixtures returned zero; warnings were not suppressed or relabelled as runtime
network evidence. The first RFC 791 web lookup returned HTTP 429; the RFC 792
and pinned upstream source lookup succeeded. The packet formats are linked
to official RFC references in the protocol, not to a third-party tutorial.

## Next gate and debug report

Next implement a separate bounded source build and independent build auditor.
Use the existing immutable R2 base, the exact frozen overlay and a new tag
`safetwin5g/ueransim:3.3.0-reconnect-r3-trace`. Validate real-header compilation,
licence/source retention, only intended source and UE/gNB binary changes,
new image identity and preservation of both old image IDs and running services.
No package/network changes are needed merely to apply the retained overlay.
Do not overwrite a tag or rebuild if an earlier completed build already exists.

Then, in a separate execution gate, freeze that actual image ID, the scoped
UE/gNB Compose override, runner, independent raw-log/network auditor and
regressions before applying an image. No image ID is invented in this freeze.
Recorded scoped standing-user approval and official-image restoration remain
mandatory. There is no unrestricted actuation endpoint.

DEBUG REPORT

- Symptom: a returned simulated link produced 14/15 packets in R2.
- Hypothesis: an identified post-return payload is lost at the idle NAS branch;
  source fixtures support it, but historical packet fate is not directly traced.
- Change: instrumentation-only overlay, packet identity reader, conservative
  trace-accounting helper and fixed prospective diagnostic contract.
- Evidence: 65 parser cases, 61 NAS cases per mode, four identified fixture
  events, exact removal and Git-patch replay, 272 tests plus 32 subtests.
- Fix: none applied; image build and network verification remain pending.
- Status: DONE_WITH_CONCERNS for the prebuild source gate only.

The investigate workflow kept source behavior checks and failed audit results
ahead of any build. Edits are confined to the new overlay, diagnostic tools,
tests, evidence and status docs; historical source/analysis files stay frozen.
Global skill upgrades, checkpoint preferences and durable memory writes were
out of scope. The practical learning is recorded here: verify byte-level patch
replay with explicit Git line-ending policy, not global host defaults.

All new evidence is `fixture`. The original spontaneous link loss, repeated
interruption recovery and watchdog remain unresolved/unvalidated. No new
675-unit campaign, dataset-v2a, confirmatory BRACE or positive TNSM result is
enabled. Preserve D1, P1, the rejected data and negative Phase 6 decision.
