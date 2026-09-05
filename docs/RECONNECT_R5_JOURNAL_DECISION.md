# R5 clock-journal component passes; full execution integration still pending

Date: 2026-09-05 UTC. The separate clock-journal **component** gate passes.
The parent recovery-validation roadmap item remains the only item in progress.
This is not completion of R5 execution integration, a network diagnostic,
validated recovery, confirmatory BRACE evidence or TNSM readiness.

## Evidence and exact boundary

`evidence/verification/20260905T191336Z-reconnect-r5-journal` retains
**563 passing tests, 200 passing subtests and 21 passing verification checks**.
The new component contributes 70 tests. Its five-source lock is
`config/experiments/reconnect-r5-journal-lock.json`, SHA256
`a2c000563b7b9674369968fd861e0b02d11896e847bfbb70d25c0e7063abe67b`.
The five-source native-clock contract remains unchanged and transitively binds
the old locks and rejected observations. No existing source was monkey-patched.

Ten retained synthetic cases cover complete capture, discontinuity, ambiguous
clock interval, wide read, partial returned point, changed domain, thrown API
error, cleanup reservation, complete capacity exhaustion and callback timeout.
Their archives were freshly extracted, checked byte-for-byte and independently
replayed. All callbacks in the three-step **no-I/O fixture** were attempted,
including after earlier failures. This is not evidence of actual official-image
rollback. Every callback report leaves service/network recovery false.

The tests also cover disk/fsync failure, first-read failure, independent replay
with candidate predicates disabled, resealed tampering, exclusive file creation,
owned-handle closure after failed header persistence, and continued cleanup
dispatch after KeyboardInterrupt, SystemExit, timeout and OS errors.
The full 1,024-point fixture performs exactly 523,776 pair comparisons. All
tested incremental prefixes match the unchanged frozen primitive; the separate
rational auditor replays released journals without using candidate predicates.

The earlier development capture at
`evidence/verification/20260905T191154Z-reconnect-r5-journal` passed its initial
64 focused tests and ten cases. It remains labelled development-only and is
not substituted for the later full gate. Both directories retain exact source
archives, raw test output, command/timestamp records and recursive hash manifests.
There was no failing development test run in this component gate. Prior clock
and R4 development failures remain unchanged elsewhere.

Read-only before/after scope checks passed with the same five healthy official
services and unchanged image/container/start identities. Old committed R4
execution sources, the original negative observation replay, R3 build provenance
and frozen statistical lock passed. No image, restart, fault, packet probe,
actual sleep-inhibition request or new native clock smoke capture ran.

## Why this is not the whole integration

The historical complete R4 **fixture** has 761 commands. Two new UTC brackets
per command would exceed R5's frozen 1,024-point limit. This component reserves
256 points for cleanup and ends normal clock admission at 768. It retains every
point and latches source/storage failures without opening another clock domain.
Its `admission_open` concerns only sampled clock consistency and remaining
capacity, not approval, callback success, packet quality or protocol admission.

Sharing adjacent capture-envelope boundaries is a prospective design option,
not implemented command containment. A future adapter still must prove actual
dispatch/exit lie within those brackets, charge all intervening overhead, use
raw QPC for every elapsed budget and fit the complete worst-case inventory.
An API/deadline failure must not disable already-authorized official cleanup,
but no replacement timestamp or unbounded process wait may be invented.

The cleanup helper tests exception isolation only. It neither supplies nor
validates authorization, command allowlists, images, qdiscs, reset/health order,
fresh PDU, packet counts, telemetry or final scope. Those requirements remain
with the separately named process/collection/host/runner integration and its
independent whole-protocol replay. They are not waived by this passing component.

Next continue that software-only integration, retaining fixed first packets,
source eligibility, prefix logs, all rollback branches and old negative results.
The complete new execution lock must pass and be committed before a **later
separate** execution decision. Do not rerun R3/R4 or the clock smoke probe, start
a long campaign, promote a model or claim hardware/operator/TNSM validation.
