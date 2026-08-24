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

Canonical KPI definitions, scenario families, data splits, and a frozen
dataset manifest are separate roadmap gates and are not implied by this module.
