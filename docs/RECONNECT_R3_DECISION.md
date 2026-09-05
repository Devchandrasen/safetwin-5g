# R3 diagnostic rejected before exposure: trace capture incomplete

Date: 2026-09-05. **The first no-fault assignment stopped during its first
baseline window. Zero fault or control exposures ran. The four-trial diagnostic
is not accepted. Both official UE/gNB images and final 15/15 packet delivery
were restored. There is no network-fix or TNSM-readiness claim.**

The execution contract was committed as
`26baf9cc17bc10f56830a91b2ee0adcb04955b45` before application. The fresh read-only
preflight at `evidence/engineering/20260905T130903Z-reconnect-r3-preflight`
passed. The 74-source committed execution lock and R3 build audit passed.
No frozen runner, image, source helper, protocol, endpoint or acceptance
auditor was changed during or after the run.

## Actual observations, not the earlier fake transport

Run: `evidence/engineering/20260905T131024Z-reconnect-r3-network`.
The four assigned trials remain control-before, drop-a, drop-b, control-after.
Only control-before was attempted. The summary's `completed_trials: 1` counts
one saved attempted assignment, **not** a valid completed trial. There are zero
valid assignments. All remaining assignments were unexecuted, with no repeats.

| Observed step | ICMP ID | Source IP | Replies | Trace observations |
| --- | ---: | --- | --- | --- |
| First baseline window | 10001 | 10.45.0.2 | 5/5 | Sequence 1 absent; 2-5 have complete forwarding paths |
| UE-restart restoration, first window | 10002 | 10.45.0.3 | 5/5 | No matching trace records |
| Full-reset restoration, first window | 10003 | 10.45.0.2 | 5/5 | Sequences 1-2 absent; 3-5 have complete forwarding paths |
| Final official verification, three windows | 10004-10006 | 10.45.0.2 | 15/15 | Official binaries, no R3 trace markers expected or found |

The baseline did **not** achieve the required three-window 15/15 validation:
the first five-packet sample raised `missing packet or fingerprint mismatch`.
The other two baseline windows were never collected. The two derived-image
restoration steps also stopped at their first trace-invalid window, so their
`clean: false` flags remain false. Returned packets do not make missing trace
complete, and missing trace does not prove lost packets. All six actual ping
invocations returned their five explicitly listed replies.

For the seven observed instrumented packet paths, the NAS ingress/forward,
UE RLS and gNB ingress/resource records have matching IP IDs, sizes and full
fingerprints in valid within-component order. The runtime error is generic;
the captured evidence shows missing packet identities, not a fingerprint
disagreement among these present records. No unobserved ingress or packet fate
is invented, and there is no drop/resumption observation to localize.

## Capture assumptions exposed

Two distinct issues require a new collection contract, not retrospective
repair of this run.

1. **Host and container wall clocks are not interchangeable.** The frozen
   runner takes Windows-host timestamps immediately before ping and uses them
   as Docker-log `--since` bounds. A later read-only probe took ten paired
   UE/gNB `date -u` samples, bracketing each remote timestamp between host
   command start and completion without a symmetric-latency assumption.
   Every remote-minus-host upper bound was negative. The ten intervals span
   a conservative combined range of -0.327649 to -0.071462 seconds. This is
   a later measurement, not a fixed offset established throughout R3.
2. **UE-only reset changed the traced flow.** Raw ping command 51 explicitly
   reports source 10.45.0.3. The immutable R3 helper admits only source
   10.45.0.2 and destination 10.45.0.1. Its existing compiled parser fixture
   tests every changed source/destination octet, including `.2 XOR 1 = .3`.
   Thus that returned traffic is outside the trace filter by construction.
   The frozen ping-metric parser checks replies but does not validate the
   source IP in the header. The new observation auditor reads that header.

Docker documents that timestamp bounds select which stored log entries are
returned and that `--timestamps` adds RFC3339Nano values. See the
[official log command reference](https://docs.docker.com/reference/cli/docker/container/logs/).
Applying a host-clock bound to an earlier-running container clock can omit
the beginning of an otherwise successful ping's trace. A deterministic fixture
reproduces that failure with all five replies and demonstrates complete
accounting when the synthetic capture boundary uses the matching clock domain.
That fixture does not insert lines into, re-time, or salvage the actual run.

The observed leading omissions are consistent with this clipping mechanism,
but the missing original entries are not available in the retained captures.
The instrumented containers were replaced during mandatory official rollback.
The later clock probe does **not** uniquely prove where every historical missing
entry went. No claim is made that R3's first packet was dropped, buffered,
replayed or directly localized. No VM clock was adjusted.

Probe: `evidence/engineering/20260905T132047Z-reconnect-r3-clock`.
Its fifteen commands are two pairs of minimal network/container snapshots,
ten read-only `date` calls and one current tunnel-address query. No measurement
ping, reset, fault, image replacement or clock-setting command ran. Independent
before/after comparison verifies unchanged official service snapshots. The
probe is later `sandbox-measured` environment evidence, not another trial.

## Rollback, approval and provenance

The recorded standing-user approval names the four assignments, exact images,
scoped resets, faults and rollback. It precedes commands and is not an operator
signature. In this stopped run there were ten reset commands: three core,
three gNB and four UE. Two scoped Compose commands replaced both UE/gNB images
with R3 and then restored both official images. No `netem` or control-wait
exposure command ran. All retained eth0 inspections show neutral `noqueue`.

Final rollback completed at `2026-09-05T13:12:23.021565+00:00` with fresh
registration/PDU markers, three clean five-packet samples and official image
ID `sha256:13705fc29922cf019e8c7992b5b04b9c6c584d3848d29689f1d3db64334ae725`
for both services. There was no final rollback error or admission-budget
overrun. The core image and MongoDB/Prometheus identities/configurations remain
unchanged. This is a bounded endpoint observation, not continuous availability.

The wrapper transcript at
`evidence/engineering/20260905T131020Z-reconnect-r3-runtime` records sleep
inhibition, child exit 2 and subsequent clearing. Acceptance comes from raw
artifacts, not the wrapper exit field. Private build snapshots/key remain
local-only; the new probes use minimal inspection without Env or private labels.

## Separate audit, original rejection preserved

`tools/audit_reconnect_r3_network.py` is unchanged. It still rejects this run
with `eight required scope snapshots`, because only five scopes and the stopped
prefix exist. That is the expected complete-protocol rejection, not evidence
by itself of corrupted hashes. It must not be changed to pass this attempt.

The separate `tools/audit_reconnect_r3_observation.py` checks this rejected
prefix's hashes, frozen source/image/configuration linkage, approval chronology,
exact command inventory, health waits, six unique ping invocations, actual
reply sequences, trace omissions and official restoration. It independently
replays 131 commands, six samples and five scopes, plus all fifteen clock-probe
commands. Its `observation_audit_passed` certifies those retained observations
only; `protocol_execution_valid` and `network_fix_validated` remain false.

Regressions reject invented baseline completion, hidden exposure/warm-up,
changed packet counts, stopped UPF behind neutral settings, inconsistent
fingerprints, clock-adjustment commands, changed clock intervals and claims
of historical trace recovery. They preserve the original acceptance rejection.
Verification logs and exact test totals are linked from `docs/ROADMAP.md`.

## Next gate, not another automatic R3 attempt

Do not rerun R3 or overwrite its image/source/tag. Before another diagnostic,
freeze a separately versioned clock-safe, source-aware collection contract.
It must verify its capture clock domain and address eligibility, retain all
first packets, preserve bounded logs and all sample identities, and distinguish
trace eligibility from packet-delivery restoration. Require negative fixtures
for clock drift, changed UE addresses, truncated/missing records, and failed
rollback. Any future changes to sampling or restoration evidence requirements
must be disclosed prospectively, not applied to R3's failed data. Commit the
new contract and independent audit before an additional image application.

No new diagnostic is started in this decision. The parent recovery gate stays
open. R2 remains rejected at 14/15; spontaneous link loss, repeated-interruption
recovery and UPF watchdog remain unresolved. Phase 6 is still negative; the
675-unit campaign with 582 failed recoveries/censored MTTR stays rejected.
No dataset-v2a, BRACE confirmation or new long campaign is enabled. P1's gap,
D1's shared-host contention and instrumentation timing limitations remain.
Hardware/operator validation and publication require new authority.

## Debug report and project learning

- Symptom: all five baseline replies returned, but required early trace records
  were missing; both derived restoration trace gates also failed.
- Confirmed issues: changed source IP is outside the fixed filter; later
  measured clocks invalidate the collector's assumed shared time domain.
- Historical uncertainty: clock clipping is supported, not a unique recovery
  of the absent original entries.
- Change: added a separate read-only clock probe, negative-observation audit
  and regressions. No frozen collector or network behavior was patched.
- Status: **DONE_WITH_CONCERNS** for diagnosis and safe evidence preservation;
  clock-safe collection and the measured recovery gate remain pending.

The investigate skill required raw-log/source comparison before a correction.
Its global setup/sync, preference, freeze-state and learning writes were not
used because this task is project-scoped. The durable project learning is
recorded here: packet counts, trace completeness, current flow eligibility and
capture-clock validity are distinct checks; a missing filtered log is not loss.
