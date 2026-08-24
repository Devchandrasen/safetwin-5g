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

Production verification:

```powershell
npm run build
npm audit
```
