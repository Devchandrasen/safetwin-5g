# R5 prospective runner inventory and timing component

Contract `safetwin5g-reconnect-r5-budget-v1`, **fixture-only**. This executable
health/settling/admission component supports the pending full runner. It is
not four-trial orchestration, approval validation, actual rollback, measured
recovery or whole-protocol replay. No real client, socket, power or native
clock API is invoked by its cases. The previous collector and all transitive
host/process/journal/clock and historical locks remain immutable.

## Prospective inventory, not executed protocol work

The count model uses these proposed future operations without executing them:
two independently checked/applied image targets; three independent resets;
each bounded health loop; existing 15-command collections plus their terminal
and four telemetry commands; exact scope/first-packet/fresh-PDU checks; owned
qdisc handling; all final telemetry and host cleanup. Health waits share their
surrounding command/terminal envelopes, not a new UTC point per two-second
wait. A health operation needs at most 25 polls plus one terminal: 26 points.
Each packet/telemetry window needs 20 points. No tolerance or cap increases.

Proposed maximum official cleanup:

| Operation | Maximum new points |
|---|---:|
| Inspect/delete only owned qdisc/verify | 3 |
| Independently check/apply both images and health | 56 |
| Post-image scope | 2 |
| Before/after identities/logs, three resets and health | 85 |
| Three packet/telemetry windows | 60 |
| Final scope, eth0 and separate telemetry | 7 |
| Owned host close and execution terminal | 3 |
| Total | 216 |

The nominal four-trial model takes **741 normal points**, assuming first-poll
healthy, neutral qdiscs and the first derived restoration arm successful.
This is an invented operation-count path, not observed successful recovery.
Summing maximum health polls and both restoration arms for every assignment
without pruning early-stop paths yields **1895 normal points**, exceeding
768. This conservative upper envelope is not a feasible positive trace and
does not guarantee four complete trials. Its unpruned packet count is 51,
below the unchanged 99-ID bound, still not a guarantee of usable samples.

Future normal admission must end at 768 while retaining the 256-point reserve.
Then the proposed cleanup maximum gives **768 + 216 = 984**, leaving 40
points below 1024. This is a conditional resource bound: the future actual
runner must implement exactly the counted cleanup and independently replay
its actual command/point inventory. Extra uncounted checkpoints, polling,
attempts, callbacks or telemetry invalidate this proof. The count model does
not bypass a failed clock/source or establish successful/durable cleanup.

## One clock and nonrenewable budgets

The caller supplies the frozen journal/transport with identical clock objects
and a wait callback. Construction requires two accepted points. Global
admission uses the second/current starting anchor's QPC-before plus 1500
seconds. Every request supplies a bounded prospective point/time inventory;
the component checks actual raw QPC and retained clock status without a
replacement domain. Such a decision alone does not prove authority or a
completed operation; the future operation must supply its closing evidence.

Health is restricted to core, gNB and UE and the exact read-only health-inspect
argv. It reserves all 26 possible points before its first poll. A single
50-second deadline is charged from its starting shared anchor. Every client's
timeout is rounded down from the remaining same-domain deadline, capped at
35 seconds, including intervening parsing/wait/fsync overhead. Its `timeout_ms`
is relative to the previous retained anchor, not to dispatch. The frozen
process adapter subtracts elapsed time at `checked_ticks` before arming the
timer; e.g. an anchor-relative 3999 ms after a two-second wait has less than
2000 ms remaining. Independent replay rejects renewal of the full timeout
after that wait. Normal health
also requires space under the original global deadline. Neither loop nor poll
renews either deadline. Cleanup health can run after global admission ended
if its current clock and reserved capacity remain valid; it does not imply
the protocol itself finished within 25 minutes.

At most 25 polls and 24 waits are possible. Nonhealthy status waits 2000 ms
using the supplied callback; raw before/after ticks must show at least two
seconds, not a successful callback alone. No wait consumes a separate UTC
point: previous and following command/terminal endpoints enclose it. Unknown,
empty, stderr, nonzero, partial or late responses reject. Even `healthy` is
not accepted until a fresh health terminal point passes the deadline/clock.

Settling similarly requests 5000 ms exactly once and requires at least five
elapsed seconds plus a fresh valid terminal within global admission. Early
return, exception, unavailable source or late closure rejects, without retry
or a replacement observation. Raw QPC/domain failure latches across operations.
Wait/API/filesystem callbacks are synchronous and not forcibly cancellable;
these are observed-return checks, not hard real-time or power-loss guarantees.

## Independent replay and remaining work

The auditor recomputes rational process/journal bounds, exact argv and global
sequences, remaining health budgets, poll/wait inventory, raw wait enclosure,
terminal evidence and reported outcomes without candidate acceptance imports.
It reconstructs every helper counter read in call order, including admission,
poll, wait and final reads, and rejects reversal or a cleared failure latch.
Poll numbers require integers; booleans cannot impersonate sequence 1.
Independent enumeration verifies the count model. Candidate-disabled replay,
positive boundary and negative failure/tampering fixtures are required.
Standalone timing replay does not replace the full runner's global cursor or
discard host/collection commands to make their independent auditors pass.

The future outer rollback must independently attempt every mandatory action
and verification branch after previous failures. Calling this health helper
cannot authorize an image/reset, and its failed timing must not suppress other
authorized safety callbacks. Failed durability stays a failed integrity audit.
Current fixtures use only invented health client results and waits.

Still required: actual four-trial runner, exact committed approval and prior-
attempt guard binding, full independent global command/collection/host replay,
raw scope/telemetry/fresh-PDU/trace/fault checks, every official rollback branch,
comparison of actual point use with this model, complete adversarial execution
fixtures and their own execution lock. Only a later separate diagnostic gate
can consider real execution after that complete lock passes and is committed.
All negative Phase 6/7 and R2/R3/R4 results, P1/D1 and external-authority gates
stay unchanged. Recovery remains the only in-progress roadmap item.
