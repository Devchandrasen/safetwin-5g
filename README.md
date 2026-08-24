# SafeTwin-5G

SafeTwin-5G is a research and product project for **causal, uncertainty-aware
network digital twins that support safe closed-loop operations in private 5G
and future 6G networks**.

The project was locked on **2026-08-24**. Its research identity is
**Trustworthy Autonomous Networks**. The scope and claim boundaries are defined
in [PROJECT_LOCK.md](PROJECT_LOCK.md).

## Current status

**All locally executable Phase 1-5 roadmap work complete**

Implemented on day one:

- a strict schema for telemetry-backed intervention records;
- a selective safety gate that rejects unsupported or irreversible actions;
- mandatory abstention when confidence or distribution-shift checks fail;
- mandatory human approval for every otherwise-eligible sandbox action;
- an append-only JSONL intervention store;
- a CLI for environment checks, a safe-decision demo, and log validation;
- unit tests for contracts, safety decisions, and dataset integrity.

The official-tag Open5GS/UERANSIM source builds now run with MongoDB and
Prometheus on an internal Compose network. A simulated UE registered and
created PDU Session ID 1, and the first hash-manifested stack capture passed.
The clean baseline passed with 20/20 user-plane packets returned. A separately
approved deterministic runbook then measured 0% baseline loss, 100% controlled
loss, 0% after remediation, 100% after rollback, and 0% after final cleanup.
That intervention record passes the `sandbox-measured` gate; its radio remains
`simulated`, and it is neither hardware-measured nor operator-validated.
The frozen 12-intervention dataset now supports reproducible baseline,
diagnostic, uncertainty, and selective-safety runs. The deterministic rule
still beats the learned baselines, alternative-action effects are not
identified, and all six held-out model proposals abstain. No model has been
promoted and no model-proposed action has been applied.
The consolidated H1-H3 benchmark decision is therefore no-go for model
promotion, positive hypothesis claims, and autonomous/live actuation. It is
go-with-constraints only for continued local sandbox research.
The local evidence product is read-only, loopback-only, and exposes GET status
and proposal-audit APIs without an actuation route. Hardware, operator, and
publication gates remain pending external authorization.

## Setup

From this directory in PowerShell:

```powershell
python -m venv .venv --system-site-packages
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Inspect the local environment:

```powershell
.\run.ps1 doctor
```

Build, start, and capture the isolated software stack:

```powershell
.\sandbox\run.ps1 build
.\sandbox\run.ps1 up
.\sandbox\run.ps1 capture-stack
.\sandbox\run.ps1 intervention
```

See [docs/SANDBOX.md](docs/SANDBOX.md) for boundaries, exact checks, evidence
verification, and the retained Debian 12 compatibility failure.

Run the day-one safety demo:

```powershell
.\run.ps1 demo
```

Validate an intervention log:

```powershell
.\run.ps1 validate-log .\examples\interventions.example.jsonl
```

Adapt a measured evidence bundle to lossless long-form telemetry:

```powershell
.\run.ps1 adapt-telemetry `
  .\evidence\sandbox\20260824T045620Z-intervention `
  .\artifacts\telemetry.jsonl
```

Run the localhost-only evidence dashboard:

```powershell
Set-Location .\dashboard
npm ci
npm run dev
```

The dashboard is read-only and contains no actuation endpoint. See
[docs/PRODUCT.md](docs/PRODUCT.md) for its evidence and safety boundaries.

## Research question

> Can an intervention-trained network digital twin estimate the effects of
> candidate remediation actions and safely abstain or escalate under
> uncertainty, reducing SLA violations without increasing harmful actions?

## Repository map

```text
config/                 Versioned action and safety policy
dashboard/              Local read-only evidence product
docs/                   Research protocol and execution roadmap
evidence/               Append-only measured logs and hash manifests
examples/               Valid, synthetic contract examples
sandbox/                Official component locks and isolated 5G SA stack
src/safetwin5g/         Contracts, safety gate, store, and CLI
tests/                  Executable correctness checks
PROJECT_LOCK.md         Fixed scope, hypotheses, and change-control rule
```

## Remaining gates

Hardware measurement, independent operator validation, and publication require
new access or authorization and remain pending. The next local research cycle
must expand calibration, action positivity, no-fault/harm scenarios, and
continuous SLA/MTTR windows before revisiting H1-H3. No algorithmic result will
be called a live-network result.
