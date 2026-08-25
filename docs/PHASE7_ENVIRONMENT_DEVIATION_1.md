# Phase 7 Environment Deviation D1 — Co-resident containers

**Detected:** 2026-08-25 during the train split, before calibration or test
execution.  
**Evidence:**
`evidence/environment/20260825T054647Z-phase7-co-resident-containers`  
**Action on external containers:** none

Six unrelated `nvg-*` containers started at approximately 05:24:01 UTC, after
the SafeTwin containers started between 04:48:28 and 04:48:51 UTC and after the
Phase 7 campaign began. They use `emulator_*` Docker networks; SafeTwin uses
`safetwin5g-isolated`. The read-only snapshot found no Docker-network overlap
and reported zero instantaneous CPU for the co-resident containers.

This does not establish host-resource isolation. The containers share the host
CPU, memory, kernel, scheduler, and Docker engine with SafeTwin, and one idle
snapshot cannot rule out prior or future contention. CPU-saturation and timing
outcomes may therefore contain an uncontrolled shared-host effect. Randomized
unit order reduces systematic action-order bias but does not remove this
external-validity limitation.

The campaign continues because the frozen protocol requires Docker-network
isolation and clean per-unit reset, both of which remain verified; it did not
preregister exclusive host ownership. Aborting only after seeing this
train-time operational event would also discard valid data without a frozen
rule. No co-resident container was stopped or changed because it is outside the
authorized project scope.

The dataset quality report, manuscript limitations, and any CPU/timing result
must disclose D1. It is prohibited to infer exclusive-host, hardware, operator,
or network-scale performance from this campaign.

## Procedural seal note

The deviation and dataset-disclosure edit was made during the train split.
During a later automatic continuation, after test execution had begun, the
operational monitor parsed completed trace files only to count `passed`,
`cleanup_verified`, and split identifiers. It did not extract, display,
aggregate, or use telemetry, action-benefit, harm, or other outcome fields, and
no statistical model, threshold, comparator, endpoint, or analysis code was
changed. This is a procedural outcome seal, not cryptographic blinding; that
distinction must be disclosed in the artifact and manuscript.
