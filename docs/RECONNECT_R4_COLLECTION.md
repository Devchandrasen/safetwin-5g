# R4 prospective collection contract, fixture gate only

Date: 2026-09-05. This separately versioned collection revision changes no
network behavior, image, historical artifact, R3 acceptance predicate or
statistical endpoint. The rejected R3 attempt and its 74-source lock remain
immutable. The parent recovery-validation roadmap item stays open.

## What changes, and why

The later clock brackets and the changed UE source in
[R3's negative decision](RECONNECT_R3_DECISION.md) exposed two capture assumptions.
They do not recover historical missing entries or establish a constant offset.
R4 removes wall-clock filtering completely; it does not tune padding from the
rejected run, set any clock or widen the immutable trace header's IP filter.

[Docker's CLI documentation](https://docs.docker.com/reference/cli/docker/container/logs/)
describes timestamp-based selection, batch retrieval of available logs,
RFC3339Nano framing and a tail limit. It does not establish clock equality
between a Windows client, the Docker daemon and a container application.
The [JSON-file driver documentation](https://docs.docker.com/engine/logging/drivers/json-file/)
describes per-container timestamps and configurable rotation, and warns against
external access to daemon-owned log files. R4 uses only the supported CLI, with
no direct log-file access or logging reconfiguration.

The prospective selection rule is an **unsaturated complete-prefix difference**:

1. Capture a nonempty, newline-terminated `docker logs --timestamps --tail 2000`
   snapshot for each of UE and gNB before the identified ping. Never supply
   `--since`, `--until`, relative durations, `--follow` or `--details`.
2. Each snapshot must contain fewer than 2,000 lines and fewer than 1 MiB of
   UTF-8 output. Exactly at either cap is rejection, not presumed completeness.
   Require unchanged running container ID, image, start time and restart count,
   with `json-file` logging and no configured options. Other configurations
   remain incompatible; do not silently change them or enlarge the limits.
3. Capture the same bounded snapshots once after the ping. Every old line must
   remain the exact prefix of the new snapshot. Only its appended suffix is
   the current collection. A missing/rewritten prefix, rotation, empty anchor,
   truncated line, timeout, error or stderr stream rejects the window.
4. Reject a current ICMP identifier already present in either old prefix. Every
   invocation consumes a new ID from 10001 through 10099, including unsuccessful
   admission. Do not wrap/reuse IDs, add warm-ups, retry a partial command or
   discard first packets. Capture once; delayed logging that leaves a required
   event absent is an honest collection rejection, not grounds for recapture.
5. Require all five packet paths, exact identity/stage cardinality, matching
   fingerprints and within-component order. Distinguish a fully observed idle
   loss from an unobserved event. Never sort UE and gNB into a global timeline.

This algorithm needs short, unsaturated container histories. It intentionally
rejects a busy/long-lived container rather than deleting logs or quietly
restarting it. The future runner must prove its scope and freshness before
admission. A prefix and five complete paths do not prove that a daemon never
dropped some unrelated log record, nor that logging has no timing overhead.
Late duplicates after the last snapshot and unobserved intervening clock steps
cannot be ruled out by a finite capture. These are limits, not positive claims.

## Clock checks without assuming a shared epoch

All command records preserve integer host wall and monotonic start/end values,
raw stdout/stderr hashes, exit code, timeout and truncation flags. The fixed
per-command bound is 35 seconds; the collection window bound is 120 seconds.
Observed host wall/monotonic disagreements within or between commands above
the prospectively declared 1 ms resolution tolerance reject the window.
This tolerance is not a log-selection offset or a packet-delivery threshold.

Each component supplies `date -u +%s.%N` before and after collection. Its elapsed
source time must lie in the conservative host-monotonic command brackets:

`after.start - before.end <= source.after - source.before <= after.end - before.start`

The same 1 ms resolution tolerance applies. No midpoint, symmetric latency or
constant host/source offset is assumed. Absolute skew of either sign is allowed.
Each component's Docker log timestamps are also checked for reversal at full
nanosecond precision. Source probes do not establish the daemon's clock domain;
forward/cancelling steps within latency uncertainty may escape detection. This
does not clip entries because **no timestamp selects the captured prefix**.

## Source eligibility and service restoration are separate

Before sending a trace-mode ping, require one UP `uesimtun0` global IPv4 source
equal to **10.45.0.2**. Check it again afterwards and require the exact raw
`PING ... from ... uesimtun0` header to agree. A change to .3 blocks trace
admission or invalidates a collected window; its missing filtered trace is not
packet-loss evidence. The image/header remains R3 with its original fixed flow.

The separate `official-service` mode permits a single stable UE address in the
fixed private PDU subnet and requires both immutable official images and no
ST3 instrumentation. Raw return sequences, duplicate detection and exact
five-packet counts remain mandatory. Three consecutive unique invocation IDs
with 5/5 each in one unchanged source/container context are only a **15/15
packet-delivery candidate**, not verified rollback.
14/15, two windows, duplicate windows or a remaining derived image cannot pass.

Prospective amendment: collection validity, trace eligibility and packet-only
service restoration are separate fields. A future derived-image restoration
may retain its returned packets even when the fixed trace source is ineligible,
but that observation cannot reopen trace admission or pass the diagnostic.
This module does not implement or authorize that restoration ladder. The old
R3 failed derived-restoration flags stay false, and the 15/15 endpoint is not
weakened. Fresh registration/PDU, neutral qdisc, UPF running, no stress workers,
three healthy Prometheus jobs and exact five-container isolation still need
their own raw-evidence audit in the future execution integration.

## Implementation and independent verification

`sandbox/reconnect_r4_collection.py` implements the fixed 15-command window
against an explicitly in-memory fixture transport. There is no live adapter,
subprocess execution, image switch, fault/restart API or `--execute` endpoint.
The transport type label is not a security barrier against arbitrary Python;
tests also deny subprocess and socket creation.

`tools/audit_reconnect_r4_collection.py` independently implements command,
clock, prefix, source, ping and path checks. It never imports runtime acceptance
predicates. Even complete fixture data requires explicit `--allow-fixture`.
Fixture captures preserve rejected prefixes as well as complete windows.
Generated command dates are synthetic and labelled separately from the real
artifact-generation timestamp. SHA-256 manifests establish byte integrity,
not authenticity, independent operator approval or network validity.

Run the separate fixture gate and the proportionate regression verifier:

```powershell
.\.venv\Scripts\python.exe tools/fixture_reconnect_r4_collection.py
.\.venv\Scripts\python.exe tools/verify_reconnect_r4_collection.py
```

The latter also performs bounded, read-only existing-scope and logging metadata
checks, not a ping or network diagnostic. These checks do not turn fixture
outcomes into sandbox measurements. The source lock covers this protocol,
configuration, collector, independent audit, fixtures, tests and verification
tools; it binds the unchanged R3 lock. Commit the lock before any live adapter.

## Next gate, still required before another measured attempt

Integrate a separately versioned bounded runner and independent whole-protocol
audit, including fresh registration/PDU, raw telemetry, exact internal-only
five-container scope, immutable image/configuration checks and failed-baseline
admission. A future live capture adapter must enforce byte/time caps while
reading, preserve partial outputs, prove supported stream behavior and durably
reserve IDs. Fixture flags alone are not a live adapter implementation.

Keep mandatory recorded standing-user approval for the exact new contract and
both images; it is not an operator signature. After any attempted image switch,
attempt owned-qdisc cleanup, both official UE/gNB replacements, and independent
core/gNB/UE resets even after an earlier failure. Verify fresh registration/PDU,
the full 15/15 recovery endpoint, telemetry and final scope. Safety rollback
remains enabled after admission ends. Failed official restoration needs attention,
not an acceptance flag. Commit and fixture-audit that complete integration before
any image application; this gate does not authorize an immediate measured run.

No R3 rerun, VM clock change, behavioral buffer/timer/retry, rebuilt image or
new 675-unit campaign follows from a collector pass. Phase 6 stays negative,
R2 stays rejected at 14/15, and Phase 7's 582 failed recoveries/censored MTTR stay
rejected. Preserve P1's pause gap, D1's shared-host limit and instrumentation
timing limits. No dataset-v2a, confirmatory BRACE, hardware/operator, live-network
or TNSM-readiness claim is enabled.
