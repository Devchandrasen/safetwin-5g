# SafeTwin-5G

SafeTwin-5G is a research and product project for **causal, uncertainty-aware
network digital twins that support safe closed-loop operations in private 5G
and future 6G networks**.

The project was locked on **2026-08-24**. Its research identity is
**Trustworthy Autonomous Networks**. The scope and claim boundaries are defined
in [PROJECT_LOCK.md](PROJECT_LOCK.md).

## Current status

**Phase 1: isolated software sandbox gate in progress**

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
The clean baseline also passed with 20/20 user-plane packets returned. This
does **not** yet satisfy the project's `sandbox-measured` claim gate: the
approved fault/action/rollback record is still pending. Fixture, simulation,
sandbox, hardware, and operator results remain strictly separated.

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

## Research question

> Can an intervention-trained network digital twin estimate the effects of
> candidate remediation actions and safely abstain or escalate under
> uncertainty, reducing SLA violations without increasing harmful actions?

## Repository map

```text
config/                 Versioned action and safety policy
docs/                   Research protocol and execution roadmap
evidence/               Append-only measured logs and hash manifests
examples/               Valid, synthetic contract examples
sandbox/                Official component locks and isolated 5G SA stack
src/safetwin5g/         Contracts, safety gate, store, and CLI
tests/                  Executable correctness checks
PROJECT_LOCK.md         Fixed scope, hypotheses, and change-control rule
```

## Immediate next gate

Run one explicitly approved, reversible sandbox fault/action/rollback
experiment. No algorithmic result will be called a live-network result.
