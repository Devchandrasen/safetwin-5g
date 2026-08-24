# Official Component Pins

**Selection date:** 2026-08-24  
**Target platform:** Linux/amd64 containers on Docker Desktop  
**Machine-readable lock:** `sandbox/versions.lock.json`

These pins identify upstream software; they do not by themselves prove that a
5G session works. Runtime compatibility becomes `sandbox-measured` only after
the isolated stack completes the registration, PDU-session, telemetry, fault,
approval, action, and rollback gates.

## Selected components

| Component | Exact pin | Upstream basis | Compatibility status |
|---|---|---|---|
| Open5GS | `v2.7.7`, commit `318eeb49a7dcdff733dec60e02d9c60aefca2fb9` | Latest official Open5GS release observed on the selection date; built from the official repository | Source and tag verified locally; runtime gate pending |
| UERANSIM | `v3.3.0`, commit `6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156` | Latest official UERANSIM release observed on the selection date; built from the official repository | Source and tag verified locally; Open5GS interoperation pending |
| MongoDB | `mongo:8.0.29-noble@sha256:021b2d5a...406e` | Docker Official Image, fixed patch tag and Linux/amd64 digest | `mongod --version` verified locally; Open5GS schema access pending |
| Prometheus | `prom/prometheus:v3.13.2@sha256:508729e0...8b69` | Official supported 3.13 LTS line, fixed patch tag and Linux/amd64 digest | Binary version verified locally; Open5GS scrape pending |
| Build base | `debian:bookworm-slim@sha256:abd67ffc...9241` | Docker Official Image, fixed Linux/amd64 digest | Image identity verified locally |

Full digests are retained in the lock file and must be used in Compose and
Dockerfiles. Mutable tags such as `latest` are prohibited.

## Compatibility rationale and boundaries

- Open5GS officially documents a 5G SA core, UERANSIM-facing NGAP setup,
  external MongoDB, and native Prometheus endpoints for AMF, SMF, and UPF.
- UERANSIM v3.3.0 identifies its radio interface as simulated while its control
  and user planes are functional. Any resulting radio claim is therefore
  `simulated`; a successful software-core experiment may be labelled
  `sandbox-measured` only for the explicitly measured sandbox behavior.
- Prometheus 3.13 is an upstream LTS series supported through 2027-07-31. The
  LTS patch was selected over the newer non-LTS 3.14 line to reduce operational
  churn during the first evidence gate.
- Open5GS does not publish a project-maintained all-in-one runtime image for
  this experiment. The sandbox builds Open5GS and UERANSIM from the exact
  upstream commits instead of accepting an unverified community image.
- MongoDB is isolated on the Compose network and is not published to the host.
  This first sandbox uses no database authentication; that is acceptable only
  inside the non-routable local experiment network and is not a deployment
  recommendation.

## Primary sources

- Open5GS releases: https://github.com/open5gs/open5gs/releases
- Open5GS source-build guide: https://open5gs.org/open5gs/docs/guide/02-building-open5gs-from-sources/
- Open5GS metrics guide: https://open5gs.org/open5gs/docs/tutorial/04-metrics-prometheus/
- UERANSIM releases: https://github.com/aligungr/UERANSIM/releases
- UERANSIM official repository and scope: https://github.com/aligungr/UERANSIM
- MongoDB Docker Official Image: https://hub.docker.com/_/mongo
- Prometheus downloads: https://prometheus.io/download/
- Prometheus LTS policy: https://prometheus.io/docs/introduction/release-cycle/

## Verification record

The following checks passed on the selection machine:

```text
Open5GS v2.7.7 tag -> 318eeb49a7dcdff733dec60e02d9c60aefca2fb9
UERANSIM v3.3.0 tag -> 6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156
MongoDB runtime -> db version v8.0.29
Prometheus runtime -> version 3.13.2, revision bb5dff00cf8fdfbf5c65e0531aa835fa238a43a2
Docker image OS/architecture -> linux/amd64
```

The current evidence ceiling remains `fixture` until the next roadmap item
passes. A successful image build alone is not a compatibility result.
