# Environment Snapshot — 2026-08-24

Status labels in this file are local measurements made on the project-creation
machine. They are not network-experiment results.

| Component | Measured status |
|---|---|
| Operating context | Windows / PowerShell |
| Python | 3.12.10 |
| Git | 2.54.0.windows.1 |
| Docker CLI | 29.4.2 |
| Docker engine | 29.4.2, started and reachable |
| Project package | `safetwin-5g 0.1.0`, editable install |
| Unit tests | 13 passed |
| Open5GS sandbox | Not deployed |
| Evidence ceiling | `fixture` |

## Verified commands

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\run.ps1 demo
.\run.ps1 validate-log .\examples\interventions.example.jsonl
.\run.ps1 doctor
```

## Next environment gate

Pin and deploy Open5GS, UERANSIM, MongoDB, and Prometheus in an isolated Docker
network. The gate passes only after a UE registration/PDU session, telemetry
capture, one reversible fault, and a verified rollback are recorded.
