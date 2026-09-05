# R5 prospective clock-source and read-bracket contract

Date: 2026-09-05. Contract: `safetwin5g-reconnect-r5-clock-v1`.
Scope: **software clock primitive, fixtures and local-host API observation only**.
There is no execution runner integration, command authorization, image change,
fault, restart, packet probe, clock setting, timer-resolution change or new
network diagnostic in this gate. All R3/R4 sources, locks and failed observations
remain immutable. The sole in-progress roadmap item remains recovery validation.

## Confirmed problem, not a historical-cause claim

R4's guard compares an unbracketed Python wall reading with an elapsed counter.
Its Python 3.12 wall clock has nominal resolution 15.625 ms on this host, while
the predicate uses a 1 ms tolerance. [Exact CPython 3.12.10 source](https://raw.githubusercontent.com/python/cpython/v3.12.10/Python/pytime.c)
uses `GetSystemTimeAsFileTime`; [Python's 3.13 change notes](https://docs.python.org/3.13/whatsnew/3.13.html#time)
describe the later switch to the precise API. R5 selects that Windows API
directly, without replacing the installed Python or changing the old adapter.

The previous later clock probe did not reproduce R4's three historical flags.
Scheduling between point reads, quantization and clock changes remain possible
causes. Neither R5 fixtures nor a successful API observation identifies which
occurred during R4. Old timestamps are not repaired, fitted or reinterpreted.

## Native source and raw record

The supported v1 runtime is Windows kernel version 10.0, build at least 17763,
64-bit CPython **3.12.10**. Unsupported runtimes, unavailable APIs, failed
frequency/counter calls and invalid FILETIME values fail closed. No alternative
clock is selected silently. Record the interpreter version, executable hash,
Windows build, process ID, random process-local clock ID and actual frequency.
The executable hash can identify a virtual-environment launcher; the reported
CPython version is the running interpreter, not inferred from that filename.
These records and source locks are procedural provenance, not attestation
against privileged source, OS or evidence tampering.

`WindowsClock` uses `QueryPerformanceCounter` and `QueryPerformanceFrequency`
directly. A counter frequency below 1 MHz is unsupported. Each observation is:

1. Raw signed-64-bit, nonnegative QPC-before ticks.
2. One `GetSystemTimePreciseAsFileTime` call, retaining both raw DWORD halves.
3. Raw QPC-after ticks in the same process and counter domain.

FILETIME conversion is exact integer arithmetic:
`utc_ns = (high * 2^32 + low - 116444736000000000) * 100`.
Accept only the Unix epoch through year 9999. The void UTC API starts with an
invalid all-ones sentinel; an unwritten result cannot become accepted time.
Any failed read consumes its sequence and preserves partial fields/error.
Sequences are 1-1024, without reuse or wrapping. Different process/clock IDs,
reordered/overlapping counter brackets and malformed integer types reject.

Elapsed deadlines must use this **same raw QPC domain**. Its `monotonic_ns()`
view performs integer floor conversion, with less than 1 ns conversion loss;
it never substitutes a UTC clock or Python's different `time.monotonic` API.
The primitive does not itself authorize starting a command or implement a
deadline/rollback supervisor. That future integration needs its own frozen gate.

## Conservative interval rule

The [Microsoft API reference](https://learn.microsoft.com/en-us/windows/win32/api/sysinfoapi/nf-sysinfoapi-getsystemtimepreciseasfiletime)
describes precise UTC timestamps and distinguishes them from elapsed QPC time.
Resolution and access time are different: [Microsoft's QPC guidance](https://learn.microsoft.com/en-us/windows/win32/sysinfo/acquiring-high-resolution-time-stamps)
warns against assigning a read to the beginning, middle or end of its access
interval and against premature floating-point conversion. Precision does not
establish absolute UTC accuracy or synchronization with another clock domain.

Prospective limits, not tuned to a new measurement:

- Each QPC bracket, expanded by one counter tick at each end, must be at most
  **100 microseconds** wide. Wider acquisition is rejected, not retried.
- Keep the **1,000,000 ns** clock-consistency tolerance unchanged.
- Allocate **1,000 ns per UTC read** for local read granularity plus one QPC
  tick per endpoint. This declared diagnostic allowance is not a measured
  absolute-accuracy bound or proof of UTC synchronization. Its value is fixed
  in both implementations and cannot be supplied by an artifact.

For earlier point `i` and later point `j`, use UTC readings `u`, QPC-before `b`,
QPC-after `a`, and frequency `f`. The possible residual interval in nanoseconds is:

```text
L = (u_j - u_i) - (a_j - b_i) * 10^9 / f - 2000 - 2 * 10^9 / f
U = (u_j - u_i) - (b_j - a_i) * 10^9 / f + 2000 + 2 * 10^9 / f
```

Accept a pair only when **the entire interval** lies inside `[-1 ms, +1 ms]`.
An interval wholly outside is an observed discontinuity relative to this
counter/allowance model, not proof of a specific OS adjustment. An interval
crossing either threshold is ambiguous and also rejected. Mere overlap with
the tolerance or a passing midpoint is insufficient. Integer cross-products
avoid rounding the acceptance boundary. Independent replay uses rational
fractions and an alternative interval-subtraction derivation.

Check **every earlier point**, not just adjacent points or the initial anchor.
This catches cumulative small steps and nonadjacent drift that those shortcuts
can miss. The first rejected prefix is retained with its point/pair identity;
later samples never erase rejection. A minimum of two points is required.
The finite 1024-point cap bounds replay cost; exhausting it does not authorize
starting a fresh domain to erase drift. Future integration must plan its full
domain/bridge inventory before any operation and preserve all attempted reads.

## Explicit limits and unchanged network constraints

Finite sampling cannot detect every sub-tolerance, cancelling or entirely
unobserved step. The corresponding indistinguishable fixture remains accepted
as sampled consistency, **not** as proof of uninterrupted clock stability.
UTC and QPC can also be correlated on Windows; this is not an independent
physical timing reference. No cross-machine latency, causal event ordering,
host/container epoch equality, TNSM novelty or network-fix claim follows.

This gate does not change the R4 prefix-based log collection, fixed source
eligibility, first-packet and unique-ID rules, byte/time bounds, separate raw
streams, fresh PDU checks, scoped approval or official rollback requirements.
The frozen old collector is not patched or monkey-patched to use these clocks.
A future separately named collector/runner/auditor must carry these constraints
forward and be independently tested, committed and approved before execution.

## Gate artifacts and replay

The five-source clock lock covers this contract, the native/candidate primitive,
independent replay, fixtures/tests and verification tool. It also hashes the
old execution/collection/statistical locks and original/later R4 manifests.
The verifier rechecks their transitive committed sources and old negative audit.
An uncommitted new clock lock is allowed only for this pre-commit software gate;
the standalone audit CLI requires the new lock and sources in Git HEAD.

Synthetic case files are `fixture` and require explicit fixture permission.
Actual native API reads are separately `sandbox-measured` with scope
`local-host-clock-api-only`, zero network commands, no radio measurement and
all network/hardware/operator/TNSM claims false. The fixed native smoke capture
attempts 64 reads once, retaining every one; any failed/invalid read rejects it.
It uses no fitted offset, timer change, clock setting or adaptive replacement.
Its samples are not the synthetic cases or the previous R4 clock probe.

The verifier saves complete test logs, raw case/probe files, exact expected
negative outcomes, source/lock hashes, timestamps and a SHA-256 manifest. It
independently replays each serialized case and compares native raw results.
Read-only before/after daemon/process snapshots establish current prerequisites
only; they are not registration, packet delivery or recovery measurements.
Prior R4 failed rollback and later 15/15 service remain separate verdicts.

The oversized pytest parameter-name development failure is retained separately
with exact pre-correction sources and raw output. Short explicit IDs correct
that test harness failure without changing its 1 MiB malformed input.
The frozen R4 network attempt is never repeated to verify this software fix.

After this software gate passes and is committed, assess a separate execution
integration gate. Keep the parent recovery item open and all negative Phase 6,
Phase 7, R2, R3 and R4 results, P1 gap and D1 contention disclosures unchanged.
