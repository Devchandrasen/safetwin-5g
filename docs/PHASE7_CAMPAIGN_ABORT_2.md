# Phase 7 campaign abort 2

## Decision

The second full Phase 7 campaign run,
`20260831T052237Z-phase7-campaign-v2a`, is **inadmissible** for dataset release,
outcome analysis, or a TNSM result claim. The partial run is preserved as
negative operational evidence and must not be resumed or repaired in place.

## What happened

- The unchanged preregistered design planned 675 units in 135 complete blocks.
- The stdout progress indicator reached 435/675, but only 434 complete unit
  trace files were durably written before the process stopped. The run has no
  final manifest or summary.
- The runner stderr log is empty. This is not evidence of successful campaign
  completion because the process was absent when the host was inspected.
- The last runner write occurred at 2026-08-31 15:16:46 IST.

## Root-cause evidence

The Windows System event log records Kernel-Power Event 42 at
2026-08-31 15:16:58 IST: the system entered sleep with reason
`Application API`. Kernel-Power Event 107 records resume at 15:17:04 IST.
After the later host resume, campaign PID 38664 and the Docker engine were
absent. The temporal evidence supports a host-lifecycle interruption; it does
not show that BRACE, a comparator, Open5GS, or UERANSIM independently failed.

The exact event records, copied runner logs, source-run file hashes, and
admissibility decision are stored in
`evidence/environment/20260831T094658Z-phase7-host-sleep-abort-diagnostic`.
The independent 438-file source/hash audit, host wrapper probe, five focused
tests, and full 180-test plus 9-subtest regression suite passed at
`evidence/verification/20260901T025845Z-phase7-host-resilience`.

## Evidence and claim boundary

- The 434 durable traces remain sandbox-measured operational traces, but the campaign
  is incomplete and statistically inadmissible.
- No held-out outcome analysis was run on this campaign.
- No partial dataset release may be constructed.
- No test threshold, comparator, endpoint, denominator, or statistical gate
  changes because of this interruption.
- The radio remains UERANSIM-simulated. Hardware and operator validation were
  not performed.

## Recovery

Preserve the interrupted run without editing or deleting traces. Restore and
verify the isolated Compose stack, then execute a new full 675-unit campaign
from unit 1 under a host sleep-inhibition wrapper. The wrapper uses only the
Windows `ES_CONTINUOUS | ES_SYSTEM_REQUIRED` execution state while the child
process runs and clears it in a `finally` block. It does not keep the display
on, does not use away mode, cannot override an explicit user sleep or shutdown,
and does not modify the frozen scientific design.

Microsoft documents the execution-state API at
<https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setthreadexecutionstate>.
