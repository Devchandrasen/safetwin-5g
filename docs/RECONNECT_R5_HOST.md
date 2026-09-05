# R5 host admission and owned lifecycle component

Contract: `safetwin5g-reconnect-r5-host-v1`. This is a **software/fixture
component**, not the full execution gate, approval, network recovery or a
TNSM result. There is no execution CLI. Import and object construction request
no native power change. All released host cases use fake transport/power APIs
and synthetic clocks; process, socket and native DLL entry are denied.

## One domain and prospective budget

The frozen R5 clock, journal and process adapter are unchanged. The host and
process adapter must share the exact journal and clock objects. The owner PID,
clock ID and a future exact execution revision digest bind the attempt receipt.
The digest is a linkage field, not signature validation or user approval.

Starting with two existing bootstrap readings, normal host admission requires
space for three more points: exclusive receipt acquisition, one idle command,
and power-enable observation. Final cleanup uses two more points for power
clear/handle-close and receipt close. The successful isolated component uses
**seven total points**, five normal plus two cleanup. This is NOT proof that
the four-trial protocol and its worst-case health/rollback paths fit the
unchanged 1,024 total / 768 normal / 256 reserved limits. That inventory and
the collector/runner's 120/50/1,500-second budgets remain pending integration.

Every host callback references its previous precise-UTC/QPC boundary, records
same-domain raw QPC before/after the callback, and attempts one terminal
journal point. Raw QPC/domain failures latch. The host admission deadline is
the initial boundary's QPC-before plus 35 seconds. The idle command's timeout
is rounded down from the remaining deadline relative to its shared anchor;
receipt/parse/idle overhead is charged, never hidden with a fresh epoch.
Each cleanup callback has a two-second observed-return bound from its own
existing anchor. No midpoint, Python wall/monotonic clock, fitted offset,
read replacement or changed tolerance is used.

The power/filesystem APIs are synchronous. The observed-return bounds reject
late returns; they do not cancel or impose hard real-time bounds on a stalled
kernel, filesystem or scheduler. A journal fsync occurs after its timestamp,
so these are API-return envelopes, not a hard bound on durable write completion.
The future runner must recheck actual same-domain admission/health/window
deadlines before every operation. Missing/failed timing stays invalid and
does not suppress either already-owned cleanup callback.

## Cooperative exclusive receipt, never path deletion

The receipt uses exclusive binary creation, then flush/fsync for its owner,
clock, revision and random token header. Closing appends a `close-intent` and
independently closes the already-owned file object even if persistence fails.
The final host record separately reports handle-close success; a close-intent
alone does not establish it. No code unlinks, truncates or replaces a receipt.

The completed receipt deliberately **remains present** and blocks a second
attempt of the same revision. A stale, partial or completed R5 receipt must
never be removed automatically to enable a retry. This differs prospectively
from R4's deleted runtime lock and avoids deleting a path that has been
substituted. Fixture directories use their own disposable receipts, not the
authoritative runtime path. A future runner must choose the exact private
runtime path, check earlier runtime guards and prior attempt directories, and
bind all of this in its full execution lock before any real action.

This is cooperative single-path exclusion, not OS attestation or exclusion of
uncooperative/privileged writers. A missing receipt directory fails closed;
the helper does not create arbitrary parents. Existing unowned contents are
neither overwritten nor exported. Partial writes and failed syncs remain
negative durability results and are not repaired by the auditor.

## Idle snapshot and separately owned power request

The fixed read-only CIM command rejects query errors, nonzero exits, incomplete
capture and any output except one exact success marker. It checks other Python
processes for phase7, recovery-pilot and reconnect runner names, including R5
and future numbered reconnect revisions. Another Python process with an
unreadable command line also rejects admission. The current PID is excluded.
This point-in-time name query does not exclude unrelated tools or future
process starts; the receipt is not a machine-wide lock.

The new power mechanism uses its **own request object**, not the old
thread-wide request state. Microsoft's [PowerCreateRequest documentation](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-powercreaterequest)
defines object creation and handle cleanup. The 64-bit
[REASON_CONTEXT layout](https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ns-minwinbase-reason_context)
is preserved with both union alternatives and a simple reason string.
The version 0, simple-string flag 1 and system-request enum value 1 follow
[Microsoft's SDK declarations](https://github.com/microsoft/win32metadata/blob/main/generation/WinSDK/RecompiledIdlHeaders/um/winnt.h).
There is one `PowerSetRequest(PowerRequestSystemRequired)` call, followed by
independently attempted `PowerClearRequest` and `CloseHandle` on that same
handle. No display, away-mode, execution-required or global power setting is
requested. A clear failure cannot suppress handle-close; a repeated close
does not retry calls or erase the original failure.

[PowerSetRequest](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-powersetrequest)
increments the owned request count, and
[PowerClearRequest](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-powerclearrequest)
decrements it. If setting throws or returns failure after object creation,
both cleanup calls are still independently attempted, with the failed result
retained. A zero result or invalid handle rejects admission. This API change
is prospective; it neither modifies nor repairs R4's captured sleep events.

Power requests do not prevent user/lid sleep or shutdown. Microsoft also
documents expiration on Modern Standby systems on DC power after the sleep
timeout plus five minutes. The software component does not establish current
AC/standby policy, actual sleep inhibition or continuous availability. A later
actual execution prerequisite must assess those limitations explicitly. No
native power smoke test runs in this fixture gate.

## Independent replay and remaining authority

The separately implemented auditor replays exact idle argv/raw streams via
the frozen independent process audit; journal brackets, chronological anchors,
shared deadlines and callback outcomes are checked without candidate imports.
It checks owned power-call ordering and numeric results, raw receipt contents,
callback exceptions, cleanup attempts and all reported verdicts. Tampering and
candidate-disabled replay are tested. Hashes/procedural records are not proof
against a privileged actor who can forge both source and evidence.

An integrity-audited host rejection remains rejected. Storage failure can also
make integrity unauditable; retain that expected negative audit error. Host
component completion never sets network authorization, service restoration,
whole-protocol completion or validated network correction.

Still required: complete collector/runner and independent whole-protocol
replay; exact standing user approval; fixed source/prefix/first-packet, fresh
PDU, raw telemetry and immutable scope checks; independently attempted both
official image replacements and all three resets; final official 15/15; and
the full worst-case point inventory. Commit that complete integration before
a later separate network gate. All old negative R2/R3/R4, Phase 6/7 results,
P1/D1 limitations and hardware/operator/publication authority gates stay intact.
