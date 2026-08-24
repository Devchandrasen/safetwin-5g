# Reproducible Software Sandbox

## Evidence boundary

This is an isolated software 5G Standalone experiment. UERANSIM emulates the
radio interface; there is no RF transmission, private-5G hardware, operator
network, or unrestricted live actuation. Before the approved fault/action/
rollback gate passes, captures are labelled `simulated` even though container
and telemetry observations come from the running local sandbox.

## Locked topology

| Service | Locked implementation | Sandbox role |
|---|---|---|
| Core | Open5GS 2.7.7, commit `318eeb49a7dcdff733dec60e02d9c60aefca2fb9` | NRF, UDR, UDM, AUSF, PCF, NSSF, BSF, SMF, UPF, and AMF |
| RAN/UE | UERANSIM 3.3.0, commit `6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156` | simulated gNB and one simulated UE |
| Database | MongoDB 8.0.29 Docker Official Image digest in `versions.lock.json` | one test subscriber |
| Telemetry | Prometheus 3.13.2 LTS image digest in `versions.lock.json` | AMF, SMF, and UPF scrapes |

The Compose network is `internal: true`; no service port is published to the
host. MongoDB has no authentication and is acceptable only inside this
non-routable experiment network. The core and UE receive only the TUN device
and `NET_ADMIN`/`NET_RAW` capabilities needed for their software data paths;
no container is privileged.

## Commands

Run from the repository root in PowerShell:

```powershell
.\sandbox\run.ps1 build
.\sandbox\run.ps1 up
.\sandbox\run.ps1 status
.\sandbox\run.ps1 capture-stack
```

The clean baseline command verifies the UE interface, five user-plane pings,
and all Prometheus targets. The evidence capture adds UE registration/PDU CLI
state plus a 20-packet measurement:

```powershell
.\sandbox\run.ps1 baseline
.\sandbox\run.ps1 capture-baseline
```

Stop the containers without deleting the named MongoDB and Prometheus volumes:

```powershell
.\sandbox\run.ps1 down
```

## Verified stack result

The 2026-08-24 stack capture records:

- all five containers running with healthy Docker health checks;
- successful NG setup, UE registration, and PDU Session ID 1 establishment;
- UE TUN address `10.45.0.2/24`;
- three healthy Prometheus targets (AMF, SMF, and UPF);
- no lost NF heartbeat or HTTP/2 framing error in the passing core log;
- Docker, image, package, configuration, command, and file hashes.

The separate `20260824T045006Z-baseline` bundle passed all 16 checks. UERANSIM
reported `RM-REGISTERED`, normal service, and an active PDU Session 1 at
`10.45.0.2`. Its 20-packet UE-to-UPF test measured 0% loss and RTT
min/average/max/mdev of 1.004/6.107/10.475/2.425 ms. These values describe this
single local software run and are not hardware or operator measurements.

Run the independent captured-file check against a bundle:

```powershell
.\.venv\Scripts\python.exe .\sandbox\verify_evidence.py `
  .\evidence\sandbox\<run-id>
```

The initial Debian 12 attempt is intentionally retained as a negative
compatibility result. Its NFs registered, then lost their heartbeats with
libcurl error 16. The pinned Ubuntu 22.04 fallback resolved that measured
failure. See `docs/COMPONENT_PINS.md` for the upstream issue link.

## Known limits

- This result does not validate RF, hardware timing, operator procedures, or
  production security.
- A successful attach/PDU session is not an action-effect experiment.
- The official `sandbox-measured` project gate remains closed until a fault,
  approved reversible action, observed outcome, and verified rollback are
  captured in one intervention record.
