# R3 pre-execution contract

## Decision and boundary

The R3 instrumentation image is built and audited, but this gate does **not**
apply it or measure a network trial. It freezes the separate execution runner,
independent raw-evidence auditor, two-service override, exact minimal execution
configuration and regression fixtures before any prospective diagnostic.
The parent recovery roadmap item remains in progress, not accepted.

This is an implementation of the unchanged
[R3 trace protocol](RECONNECT_R3_TRACE_PROTOCOL.md), not a new recovery endpoint
or a repeat of the rejected [R2 comparison](RECONNECT_R2_DECISION.md).
The unchanged R3 image ID and binary hashes are in
`config/experiments/reconnect-r3-images.json`; do not rebuild or overwrite it.

## Execution and approval

`sandbox/run_reconnect_r3.py` performs no mutation by default. Its `--execute`
entrypoint requires all execution-lock sources, configuration and the lock
itself to match committed HEAD bytes. Missing, dirty or uncommitted sources
block execution. The source lock is a procedural provenance check, not a
cryptographic authorization signature or protection against a privileged user
rewriting both source and lock.

The executable first checks the original fail-closed policy and independent R3
build audit. It refuses any prior `*-reconnect-r3-network` attempt and takes an
exclusive local runtime lock. A stale lock or partial attempt requires
inspection, not automatic deletion, replacement or rerun. The recorded
standing-user authorization names the four fixed trials, two immutable image
IDs, core/gNB/UE resets, UE/gNB image replacements, two bounded faults and
rollback. It is not an independent operator signature.

The Compose override changes **only** the UE and gNB image. It never builds,
pulls, changes dependencies, removes volumes, adds ports/capabilities or touches
unrelated containers. Each relevant scope snapshot requires the five named
SafeTwin containers on their exact internal network, current attachment IDs,
healthy running state, version pins and immutable image IDs. Minimal execution
configuration is compared against the frozen official preflight reference,
not silently adopted from whatever environment happens to exist at startup.
Only unique mount destination ordering is normalized; all mount fields remain
compared. Full Env, private labels and health-log configuration are not captured.

The read-only preflight is separately callable:

```powershell
.\.venv\Scripts\python.exe tools/preflight_reconnect_r3.py
```

It does not enable mutations, perform measurement pings, restart services or
apply the image. `ping -h` checks explicit ICMP identifier support only.

## Data collection and independent replay

Every five-packet invocation uses a fresh identifier from 10001 through 10099,
including every baseline, restoration and final official verification. An
exception does not reuse the identifier. There are no unreported warm-ups or
discarded first packets. Per-window command ranges link seven raw captures to
the durable sample: ping, tunnel qdisc, UPF state, fault workers, Prometheus
targets, UE trace and gNB trace. Raw reply sequence/count agreement is required;
exit code alone never establishes packet delivery.

Docker logs retain timestamps and closed `--since`/`--until` intervals with a
2,000-line cap. A saturated interval, malformed timestamp, missing/duplicate
stage, inconsistent fingerprint or local-order contradiction is rejected.
There is no assumed global event ordering between UE and gNB. The independent
auditor implements its own ping and trace parsers and path predicates; it does
not import the runner's acceptance functions. It shares only the frozen command
spellings in `reconnect-r3-command-contract.json`.

`tools/audit_reconnect_r3_network.py` is a **complete-protocol acceptance audit**.
It accepts only all four valid trials with exact preparation, exposure,
restoration, both image switches and final official 15/15 verification. It
rejects an incomplete run even when its raw files are faithfully retained.
Therefore an audit rejection on a stopped run is not automatically a hash
integrity defect, and this tool must not be described as an independent
integrity certification of every partial bundle. Inspect and report the actual
failure and retained rollback evidence without manufacturing an audit pass.

Trace completeness and 15/15 recovery are separate fields. The fixed drop
assignments may retain fully accounted loss for diagnostic localization; that
never changes the earlier recovery endpoint. A lost packet after the gNB
resource-found stage stays unlocalized. Even a lossless R3 diagnostic cannot
set `network_fix_validated`, because this is instrumentation, not a new repair.

## Stop and rollback behavior

Invalid baseline blocks exposure. Incomplete trace, uncontrolled exposure,
failed no-fault control or failed restoration stops admission without a
replacement assignment. Each drop retains its UE-restart then full-reset
restoration ladder, including unsuccessful steps.

The outer finally path runs after any attempted candidate image switch,
including a partially failed Compose command. It separately attempts owned
qdisc cleanup, both official image replacements and core/gNB/UE reset followed
by fresh registration/PDU, three clean five-packet samples and final scope
verification. An earlier cleanup/switch error cannot suppress the reset
attempt. Unknown qdiscs are not explicitly deleted. Restoration failures remain
errors and require attention; source code alone does not prove restoration.

Admission is limited to 25 minutes, each subprocess to at most 35 seconds and
each health wait to 50 seconds. A health poll uses the smaller remaining wait
budget, not a new 35 seconds after the deadline. Bounded safety restoration can
continue after admission expires. Timeouts and OS command failures retain
their failure records rather than a fabricated stdout success.

## Retained development failures and fixtures

Two read-only preflights failed before any mutation was enabled:

- `20260905T122202Z-reconnect-r3-preflight`: Docker's Go template rejected the
  absent optional `HostConfig.Sysctls` key. The corrected minimal template uses
  map `index`, preserving absent values as null.
- `20260905T122302Z-reconnect-r3-preflight`: capability spellings were checked
  without the `CAP_` prefix returned by this engine. The corrected check
  requires exactly `CAP_NET_ADMIN` and `CAP_NET_RAW` for core/UE, not additional
  privileges.

The read-only preflights at `20260905T122339Z` and `20260905T124915Z` passed.
The latter also verifies the locked initial execution scope and bounded-wait
implementation. The first three preflight bundles retain exact recoverable
source versions in
`evidence/engineering/20260905T122339Z-reconnect-r3-preflight-source-archive`.
Their original failed commands and manifests remain unchanged.

The execution fixtures use a deterministic in-memory fake Docker transport.
During fixture generation, any actual subprocess call is an error. Their
design explicitly says `fake-docker-no-io`, summary says `fixture` and records
zero actual Docker commands. The complete example deliberately models controls
at 15/15 and drops at 14/15, with 354 synthetic command records, 33 samples and
eight scope snapshots. Those invented fixture outcomes are **not predictions
or observations of the forthcoming network trial**.

Separate negative fixtures cover an invalid first baseline with zero faults,
incomplete trace stopping at the first drop, and a partially failed image
switch. All demonstrate attempted official restoration in the fake transport,
not physical evidence that rollback will succeed. The independent auditor
rejects partial protocols and refuses even the complete fixture unless its
explicit `--allow-fixture` flag is supplied.

## Next permitted step and unresolved claims

After this implementation, evidence and lock are committed, a fresh unchanged
preflight and exact standing approval may precede the one bounded four-trial
diagnostic. Do not automatically repeat a failed attempt or begin a long
campaign. Capture the actual logs and independently audit before making a
separate decision. Keep both official images restored at the end.

Phase 6 stays negative. The rejected 675-unit campaign with 582 failed
recoveries/censored MTTR stays rejected. R2 remains 14/15, not rounded up. P1's
historical collection gap, D1's shared-host contention and instrumentation
timing limitations remain disclosed. Spontaneous link loss, repeated
interruption recovery and the UPF watchdog are unresolved. There is no
dataset-v2a, confirmatory BRACE analysis, hardware/operator validation, live
actuation or TNSM-readiness claim.

Official interface references: [Docker runtime capabilities](https://docs.docker.com/engine/containers/run/)
and [timestamped bounded Docker logs](https://docs.docker.com/reference/cli/docker/container/logs/).
