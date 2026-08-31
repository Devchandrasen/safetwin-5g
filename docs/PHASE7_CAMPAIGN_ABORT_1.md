# Phase 7 campaign abort 1

## Decision

The first full Phase 7 campaign run,
`20260825T045337Z-phase7-campaign-v2a`, is **inadmissible** for dataset release,
outcome analysis, or a TNSM result claim. It is preserved as negative
operational evidence and must not be resumed or repaired in place.

## What happened

- The preregistered design planned 675 units in 135 complete blocks.
- The runner completed 419 units before it aborted fail-closed.
- Unit
  `safetwin5g-phase7-brace-v2a-test-cpu_saturation-2-observe_only-1309`
  completed its cleanup commands, but recovery observation failed because the
  UE container had stopped. The trace contains
  `recovery: RuntimeError: recovery-01-ping failed with exit code 128` and has
  `cleanup_verified=false`.
- The runner wrote `passed=false`, `aborted_for_cleanup=true`, and did not
  reach the OOD split. The independent campaign auditor rejected the run.

## Root-cause evidence

Archived Docker Desktop backend logs show a GUI-originated
`POST /compose/bulk/:action` for project `safetwin5g-sandbox` at
2026-08-25 09:26:39 UTC. Docker then recorded Compose stop events for all five
SafeTwin containers. Container inspection places their exits between
09:26:39.943 UTC and 09:26:42.784 UTC; none was marked OOM-killed. This is an
external Compose-project stop during the experiment, not evidence that BRACE,
a comparator, or UERANSIM independently failed.

The exact diagnostic, source-log hashes, container states, and failed-trace
hash are stored in
`evidence/environment/20260825T092639Z-phase7-abort-diagnostic`.

## Evidence and claim boundary

- The 418 passing units before the abort remain sandbox-measured traces, but
  the campaign as a whole is incomplete and statistically inadmissible.
- No held-out outcome analysis was run on this campaign.
- No partial dataset release may be constructed.
- No test threshold, comparator, endpoint, or statistical gate changes because
  of this failure.
- The radio remains UERANSIM-simulated. Hardware and operator validation were
  not performed.

## Recovery

Preserve the failed run without editing or deleting any trace. Restore and
verify the isolated Compose stack, then execute a new full 675-unit campaign
from the unchanged preregistered design. Do not delete the failed unit and do
not use the runner's resume option because cleanup was not verified.
