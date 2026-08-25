# SafeTwin-5G TNSM Claim Matrix

**Cut-off:** 2026-08-25  
**Status:** pre-result claim lock; no submission or acceptance claim

This matrix prevents an engineering feature, a lower evidence tier, or a
non-significant result from being promoted into novelty. It supplements the
primary-source collision audit in `docs/PHASE7_NOVELTY_AUDIT.md`.

| Candidate statement | Current status | Closest collision | Permitted wording if the frozen gates pass | Forbidden wording |
|---|---|---|---|---|
| Open5GS/UERANSIM network digital twin | established integration, not novel | IRTF NDT architecture, ETSI ZSM 015, Costa et al. | version-pinned reproducible sandbox used to evaluate BRACE | first 5G NDT; real-network twin; implementation novelty |
| Uncertainty-aware mitigation ranking | established problem, not novel | SWARM; action-conditional conformal decisions | comparator context for a post-selection certificate | first uncertainty-aware network remediation selector |
| Causal/counterfactual networking | established area, not novel | NetCause and causal decision literature | clean-reset intervention contrasts identify the measured sandbox action effects under stated assumptions | first causal network-management system; production causal validity |
| Approval, rollback, and evidence policy | established safety practice, not algorithmic novelty | RFC 9315/9417, safe remediation, PatchWeaver | fail-closed operational contract coupled to the certificate and fully audited in the sandbox | first safe remediation system; approval itself proves safety |
| BRACE simultaneous action certificate | implemented method candidate; empirical gate pending | generic split conformal, action-conditional conformal decisions, formal conformal control | block-level simultaneous finite-sample certificate for post-selection among named 5G remediation actions, under exchangeability, complete-block, consistency, and no-interference assumptions | new general conformal theorem; conditional/per-action/OOD guarantee |
| Named-action intervention benchmark | 675-unit campaign in progress | private-5G NDT POC and existing remediation testbeds | reproducible complete-action, randomized-order, clean-reset Open5GS benchmark with separated evidence tiers | hardware benchmark; operator dataset; representative population sample |
| Safer decisions than point estimates | sealed confirmatory result pending | SWARM and safe-remediation policies | report only the frozen paired G3 estimate, interval, exact test, Holm value, counts, and denominator | safer if G3 fails; redefine harm after labels; hide no-fault false remediation |
| Useful certified coverage | sealed confirmatory result pending | selective prediction and conformal decision work | report only if G2 has zero margin violations, at least 29 certifications, at least 50% faulty-block coverage, exact upper bound below 0.10, and adjusted significance | useful with zero/few certifications; use unadjusted row-level confidence |
| Scalability | certificate computation measured on fixture inputs | SWARM large-datacenter evaluation | local Python certificate overhead over 21–5,000 blocks, with host and timing distribution | network-scale, radio-scale, Docker-scale, or operator-scale performance |
| Operational safety | campaign recovery gate pending | change-management and rollback systems | all 540 planned sandbox mutations had explicit approval, commands, rollback plans, and verified cleanup, only if G4 passes | autonomous/live safety; infer recovery from a good outcome |
| External validity | not established; D1 records non-exclusive host | real private-5G and production-network studies | single-host software-sandbox evidence with simulated radio and disclosed co-resident-container limitation | exclusive-host, hardware-measured, multi-site, operator-validated, or live-network result |

## Paper contribution gate

A TNSM manuscript may claim a contribution only if the corresponding evidence
passes without changing the lock:

1. **C1 — Method:** BRACE implementation, proof contract, leakage audit, and
   simultaneous coverage gate G1 pass.
2. **C2 — Benchmark:** all 675 units, 135 complete blocks, manifests, approvals,
   and clean recovery pass; the public-safe release excludes authorization
   prose and identities.
3. **C3 — Decision evidence:** G2 utility/validity and G3 paired comparative
   safety both pass with Holm adjustment. A deterministic or point baseline win
   blocks the positive decision contribution.
4. **C4 — Systems evidence:** G4 and the end-to-end provenance audit pass;
   computation timing remains separately labelled fixture-input/local-host.

If C1–C4 do not all pass, the positive TNSM manuscript gate is `no-go`. The
project must preserve the benchmark and negative result rather than retune the
test. Hardware trials, operator validation, and submission remain separate
external-authority gates even after a local `go`.
