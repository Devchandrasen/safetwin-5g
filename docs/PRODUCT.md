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
