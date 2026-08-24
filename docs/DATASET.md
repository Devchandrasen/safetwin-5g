# Intervention Dataset

## Raw telemetry adapter

`EvidenceTelemetryAdapter` converts an immutable intervention bundle into
lossless long-form JSONL. Each row records the scenario, stage, timezone-aware
observation timestamp, source, native metric name, labels, numeric value, unit,
and inherited evidence label. It does not promote or reinterpret the source
evidence.

The first replay converted `20260824T045620Z-intervention` into 377 rows across
the `baseline`, `fault`, `post-action`, `rollback`, and `final` stages. Sources
were UERANSIM user-plane ping plus Open5GS AMF, SMF, and UPF exposition. This is
one `sandbox-measured` intervention with a `simulated` radio, not a multi-scenario
dataset or model result.

## Scenario state machine

`ScenarioRunner` fixes the execution order to baseline, fault, approved action,
rollback, and final cleanup. It accepts only `environment=sandbox`, refuses a
missing or out-of-scope approval, and invokes cleanup from a `finally` block if
execution fails. Network-specific backends must implement observation, fault,
action, rollback, and cleanup operations without weakening these controls.

Scenario families, data splits, and a frozen dataset manifest are separate
roadmap gates and are not implied by this module.

## Canonical KPI contract v0

The versioned registry defines six stage-level observations:

| KPI | Unit | Direction |
|---|---|---|
| `user_plane_packet_loss_pct` | percent | lower is better |
| `user_plane_rtt_avg_ms` | milliseconds | lower is better |
| `user_plane_success_ratio` | ratio | higher is better |
| `amf_registered_ues_count` | count | higher is better |
| `smf_pfcp_sessions_count` | count | higher is better |
| `upf_sessions_count` | count | higher is better |

The same registry fixes definitions for action-effect error, harmful
remediation rate, SLA-violation duration, mean time to recovery, rollback rate,
false-remediation rate, risk-coverage AUC, abstention rate, decision latency,
and CPU overhead. Those endpoints remain unavailable until the scenario matrix
and benchmark stages produce the required observations.

Canonicalization creates a complete scenario/stage/KPI grid. Missing source
observations remain null with a reason. In the first measured intervention,
RTT is missing during the fault and rollback stages because 100% packet loss
produced no replies; it is never imputed as zero. The evidence label is copied
from the source record without promotion.
