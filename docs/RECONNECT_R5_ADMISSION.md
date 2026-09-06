# R5 file-admission component v1

Scope: the remaining **file prerequisites**, not a native runner or measured
recovery. The full frozen R5 fixture runner and every historical source lock
remain unchanged. This component has only a read-only checking CLI. It cannot
dispatch Docker, packet, fault, clock, power, restart or rollback operations.

## Implemented contract

- The caller supplies an exact 40-character Git revision, the new admission
  lock SHA256, the approval's exact raw-byte SHA256 and one fixed output name.
- Actual Git HEAD, committed blobs, working files and staged files are checked.
  The new flat manifest covers every source and immutable dependency named by
  all ten R3/R4/R5 frozen locks, plus the five new component sources. Missing,
  extra, uncommitted and differently staged inputs reject. Unrelated files,
  including the protected untracked analysis-freeze directory, are untouched.
- Paths stay under the exact Git checkout root. Traversal, alternate streams,
  symlinks, Windows reparse points, hard-linked files and oversized inputs
  reject. Reads check identity/size/change metadata; JSON rejects duplicate
  keys, nonfinite values and bool/integer scope substitution.
- `config/actions.json` must still forbid live actuation and require human
  approval. An actual prior approval file must exist at
  `evidence/private/reconnect-r5-approval.json`, match the supplied raw digest,
  and bind revision, lock, images, containers, four assignments, exact rollback
  text, output and one attempt. Approval lifetime is at most one hour, with
  explicit timezone and a half-open validity interval. Whitespace edits revoke
  the byte binding too. The component never writes or generates that file.
- Any older runtime guard, R5 receipt or prior R5 network-output name blocks a
  first reservation. `reserve()` rechecks, exclusively creates the fixed R5
  receipt, flushes/fsyncs it, exclusively creates the output, then rechecks.
  Competing callers cannot both create the receipt. A partial write, crash,
  failed fsync or later failure never deletes/truncates the receipt. It blocks
  retries even after close. A substituted receipt/output rejects ownership.
- `recheck()` rereads actual files, not caller-supplied booleans. A rejection
  permanently closes that object even if old approval bytes are restored.
  Close only closes the owned file handle; it makes no recovery claim.

## Independent verification

The independent file auditor imports no candidate module. It rereads the
filesystem, checks the same external pins and fixed scope, and retrieves
committed files using Git archive rather than the candidate's batch-blob
reader. It recomputes the entire unreserved snapshot and rejects changed
positive summary flags. It is a **contemporaneous unreserved-file audit**,
not offline native execution, clock, receipt-durability or packet replay.
Archive reads locally override `core.autocrlf=false`; machine/repository
settings stay unchanged and stored evidence is never normalized afterwards.
Git environment overrides that redirect repository/index/object lookup reject.

Tests use actual ephemeral local Git repositories and files copied from the
frozen sources. Test approvals are invented and exist only inside those
temporary fixture repositories. They are not approvals for the authoritative
checkout. Tests forbid sockets and native APIs and allow only local Git reads
during component checks. Verification retains source snapshots, raw logs,
temporary fixtures and hashes, including any failed development run.

## Boundaries still pending

`file_gate_passed` does **not** establish a human's identity: unsigned local
JSON plus a digest is byte/scope verification, not authentication. The user
must separately authorize actual execution. No permission follows merely
from writing `approved_by: user` in a file. This release lock permanently says
`native_execution_enabled: false` and `network_execution_authorized: false`.

Native invocation and the independent whole-protocol audit still need their
separate versioned integration: exact authority checks in the shared timing
domain before every normal dispatch; receipt ownership integrated with the
host lifecycle; cleanup remaining independently available after revocation;
fresh daemon scope/idle/image admission; the committed execution decision;
and proportionate software verification before any bounded diagnostic. Do not
reuse this standalone reservation and then ask the frozen host to acquire the
same receipt a second time. No such integration is claimed here.

Ordinary filesystem/Git operations are cooperative checks, not a defence
against concurrent privileged edits, a distributed lock, authenticated Git
history, power-loss-proof directory persistence, or hard-real-time calls.
The observed wall timestamp is not a replacement for frozen QPC/precise-UTC
measurement evidence. No network trial or TNSM contribution is established.
