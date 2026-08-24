# SafeTwin-5G local dashboard

This is a localhost-only, read-only view of the current SafeTwin-5G evidence.
It does not expose an actuation endpoint, accept approvals, or raise any result
above its recorded evidence label.

From this directory:

```powershell
npm ci
npm run dev
```

The development and production scripts bind to loopback. The authoritative
decision source is
`evidence/benchmarks/20260824T054718Z-benchmark-report-v0` in the repository
root. The dashboard reports its radio evidence separately as `simulated`.

Read-only machine endpoints:

- `GET /api/status`
- `GET /api/proposals`

The evidence snapshot is generated under `app/data/status.json` by
`../tools/export_product_snapshot.py`. No mutation or actuation route exists.

Production verification:

```powershell
npm run build
npm audit
```

End-to-end production smoke testing is run from the repository root:

```powershell
.\.venv\Scripts\python.exe .\tools\run_dashboard_smoke.py
```
