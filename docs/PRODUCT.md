# Local Product Boundary

## Evidence dashboard v0

The Phase 5 product surface is a local, read-only dashboard under `dashboard/`.
It renders the authoritative benchmark decision from
`evidence/benchmarks/20260824T054718Z-benchmark-report-v0` and keeps
`sandbox-measured` intervention evidence separate from the `simulated` radio.

Safety boundaries:

- development and production scripts bind to IPv4 loopback;
- the page contains no form, approval control, or action trigger;
- live actuation remains locked;
- hardware and operator gates remain visibly pending;
- no database, object store, authentication, or external connector is enabled;
- the dashboard does not upgrade evidence or hypothesis status.

Verification is captured at
`evidence/verification/20260824T060413Z-local-dashboard-v0`: a clean dependency
install, production build, lint, full `npm audit` with zero known
vulnerabilities, and 92 passing repository tests. The earlier
`20260824T060228Z-local-dashboard-v0` bundle is retained; its checked command
returned zero, but the wrapper then hit a Windows CP-1252 display error. The
wrapper encoding defect was fixed before the authoritative rerun.

The next product item may expose machine-readable status and proposal audit
data, but it must not add an actuation endpoint.

## Status API and proposal audit v0

The dashboard exports a deterministic snapshot from verified benchmark,
safety-integration, and dataset manifests. Regenerate or check it with
`tools/export_product_snapshot.py`; source hashes travel with the snapshot.

Read-only routes:

- `GET /api/status` returns hypothesis, safety-lock, diagnostic, and proposal
  summary state without the per-proposal records;
- `GET /api/proposals` returns all six held-out proposal audit records.

Only `GET` handlers exist. The page renders the six records with split, fault,
candidate action, gate reason, decision, and execution status. All six remain
`abstain` and `not-applied`; approval was not requested and the live sentinel
was rejected. Verification is captured at
`evidence/verification/20260824T061147Z-product-status-api-v0`.

## End-to-end product QA v0

The production smoke harness starts the built product on port 4173, verifies
the listener address, probes the page and both read APIs, rejects all mutation
methods, confirms that no actuation route exists, captures the server log, and
stops the process tree.

The first production smoke at
`evidence/product/20260824T061711Z-dashboard-smoke-v0` failed honestly: Vinext
ignored `--host`, bound to `0.0.0.0`, and the harness compared header names
case-sensitively. The production script was corrected to `--hostname
127.0.0.1`, and headers were normalized. The authoritative source-hashed run
at `evidence/product/20260824T061959Z-dashboard-smoke-v0` passes:

- the only listener is `127.0.0.1`;
- the page, status API, and proposal API return 200;
- all POST, PUT, PATCH, and DELETE requests to the read APIs return 405;
- all tested methods for `/api/actuate` return 404;
- API responses use JSON and `nosniff`;
- six proposals remain abstained and zero actions are applied.

The smoke result is `fixture` software evidence over a snapshot whose source
data is `sandbox-measured` and whose radio remains `simulated`. Final clean
install/build/lint/audit and 97-test verification is captured at
`evidence/verification/20260824T062046Z-product-qa-v0`.
