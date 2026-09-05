# Phase 7 user-requested pause and resume P1

The user requested a laptop shutdown on 2026-09-01 and continuation of the same
campaign on 2026-09-05. The affected run is
`evidence/scenarios/20260901T030631Z-phase7-campaign-v2a`.

## Preserved checkpoint

There are 546 durable unit traces, all with verified cleanup and matching
approval. The next unit is
`safetwin5g-phase7-brace-v2a-test-network_function_interruption-400-observe_only-1309`.
Its interrupted attempt has command records but no durable unit trace. These
commands remain in the original log. The existing runner's `--resume` mode
skips the 546 saved units and executes the 129 missing units in the original
design order, including a fresh attempt of the interrupted unit.

The campaign has no terminal manifest or summary at the checkpoint and is not
accepted for a dataset or analysis. The metadata-only resume audit checked
the complete saved design against the frozen expansion, approval coverage,
trace identities, cleanup flags, contiguous progress, frozen analysis hashes,
and 44,918 command output hashes and accepted return codes. It did not
summarize telemetry, benefits, harms, model scores, or trace passed flags.

The preserved pre-resume bundle is
`evidence/environment/20260905T015200Z-phase7-resume-checkpoint`. It includes
hashes and byte sizes of all 550 source files, plus exact copies of the original
environment, approval, design, and command log. Original files must remain
byte-identical except for the append-only command log and the environment file
which the existing runner replaces. Their original versions remain in the
checkpoint bundle.

## Operational recovery

During the September 1 stop, the child and wrapper terminated and the wrapper
reported that sleep inhibition was cleared. The explicit rollback cleared
packet impairment, resumed UPF, and terminated experiment-owned stress workers.
The user plane initially failed its ping check. UE-only restart did not restore
it; restarting Open5GS, gNB, and UE restored address 10.45.0.2/24 and 5/5 pings.
This is a shutdown-recovery observation, not a successful experimental unit.

On September 5 Docker Desktop initially failed on inaccessible temporary Unix
socket endpoints. The two exact temporary directories were moved to
recoverable siblings ending `.stale-20260905T015053Z`; images, volumes, project
data and settings were retained. Docker engine 29.4.2 recovered. The existing
five-container sandbox started and passed its user-plane baseline and all
three Prometheus target checks. Unrelated containers were left untouched.

## Acceptance and disclosure

The frozen protocol gives each unit an independent reset and does not mandate
one uninterrupted host session. The pre-existing runner supports resume when
all durable cleanup flags are verified. This operational continuation changes
no assignment, threshold, comparator, endpoint, calibration rule or model.

The four-day collection gap and host/container restart can introduce time or
environment effects, including within paired blocks. Any dataset or report
from this campaign must disclose P1 as well as shared-host limitation D1.
The procedural outcome seal remains a limitation. The first incomplete
attempt of unit 547 is retained as an operational interruption, not scored as
an additional independent observation or deleted from the command history.

The existing runner restarts command sequence numbering and uses the resume
time as `summary.started_at`; timestamps and the preserved prefix identify the
two sessions. Neither field may be used to claim uninterrupted collection.
After terminal completion, independently verify all 675 units/135 blocks,
preserved prefix hashes, approvals, cleanup and recovery, then audit the dataset
and execute the frozen analysis. TNSM acceptance remains pending those gates.
