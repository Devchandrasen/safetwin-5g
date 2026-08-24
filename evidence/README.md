# Evidence bundles

Evidence is append-only by run directory. Each completed bundle contains a
`manifest.json`, timestamps, exact command arguments, configuration hashes,
captured-file hashes, container/image identities, and raw service logs.

The directory name is `<UTC timestamp>-<stage>`. A bundle whose manifest has
`passed: false`, or an interrupted bundle with `capture-error.txt`, is a
preserved negative result and must not be represented as passing evidence.

Verify a completed bundle with:

```powershell
.\.venv\Scripts\python.exe .\sandbox\verify_evidence.py `
  .\evidence\sandbox\<run-id>
```

Pre-intervention `stack` and `baseline` bundles are labelled `simulated` under
the project claim gates. Only the later approved fault/action/rollback bundle
can satisfy the minimum `sandbox-measured` claim.
