# Phase 7 TNSM Novelty Audit

**Audit date:** 2026-08-25  
**Status:** candidate novelty locked for falsification; no novelty or acceptance claim  
**Target identity:** Trustworthy Autonomous Networks

## Verdict

The Phase 6 artifact is not TNSM-grade on algorithmic novelty. Open5GS and
UERANSIM integration, an action-conditional ridge model, scalar split conformal
intervals, design-range OOD detection, and a human approval gate are useful
engineering components, but none is a defensible new method by itself.

Phase 7 therefore does not rename the existing pipeline as novel. It tests a
new, narrower candidate contribution:

> **BRACE** (Block-Randomized Action Certification with Evidence tiers) uses
> complete clean-reset blocks of named remediation actions, block-level
> simultaneous conformal calibration of all action-versus-observe contrasts,
> and fail-closed evidence/OOD/rollback preconditions to issue a
> post-selection-valid action certificate or abstain.

The statistical construction uses established split-conformal ideas. The
candidate research contribution is their causal and operational specialization
to a non-leaking, complete-action network-remediation design, plus the
replayable private-5G benchmark and safety contract. It is not claimed to be a
new general conformal theorem.

## Closest-work collisions

| Area | Closest primary source found | Collision and consequence |
|---|---|---|
| TNSM bar | [IEEE TNSM scope](https://www.comsoc.org/publications/journals/ieee-transactions-network-and-service-management) | TNSM asks for significant network-management contributions and performance/scalability or actual-system experiments. A local demo alone is insufficient. |
| NDT architecture | [IRTF NMRG NDT architecture draft-13](https://datatracker.ietf.org/doc/draft-irtf-nmrg-network-digital-twin-arch/) and [ITU-T Y.3090](https://www.itu.int/rec/T-REC-Y.3090-202202-I) | Risk-free what-if testing, validation, and closed-loop use are already core NDT concepts. Those cannot be claimed as SafeTwin inventions. |
| Zero-touch NDT | [ETSI GR ZSM 015 V1.1.1](https://www.etsi.org/deliver/etsi_gr/ZSM/001_099/015/01.01.01_60/gr_ZSM015v010101p.pdf) | NDT-assisted analytics, decision processes, and reconfiguration are already standardized research directions. |
| Intent assurance | [IETF RFC 9315](https://datatracker.ietf.org/doc/html/rfc9315) | Intent fulfillment already includes course-of-action selection, while assurance measures action effectiveness and closes the feedback loop. Action proposal plus post-action validation is not novel. |
| Service assurance | [IETF RFC 9417](https://datatracker.ietf.org/doc/html/rfc9417) | Structured assurance cases and the risk that faulty observations trigger unsafe reconfiguration are already recognized. Evidence capture alone is not a new assurance method. |
| 5G NDT implementation | [Costa et al., 2025](https://arxiv.org/abs/2510.12458) | A real private-5G NDT and open implementation already exist. An Open5GS/UERANSIM stack is not implementation novelty. SafeTwin remains software-sandbox evidence, below their hardware fidelity evidence. |
| Network mitigation ranking | [Namyar et al., NSDI 2025 (SWARM)](https://www.usenix.org/conference/nsdi25/presentation/namyar) | SWARM already ranks network mitigations, includes no action, models traffic/routing uncertainty, evaluates customer-visible distributions, and scales to large datacenters. SafeTwin cannot claim first uncertainty-aware mitigation ranking or stronger network scalability; its candidate distinction is the simultaneous finite-sample action certificate, false-remediation endpoint, and evidence-gated 5G intervention design. |
| Causal network reasoning | [NetCause, 2026](https://arxiv.org/abs/2606.13543) | Counterfactual network reasoning is already demonstrated at production scale for root-cause analysis. SafeTwin must focus on intervention choice and safety, not claim first causal networking. |
| Conformal decisions | [Zhu et al., 2026](https://arxiv.org/abs/2606.05551) and [Ek et al., 2022](https://proceedings.mlr.press/v151/ek22a.html) | Action-conditional risk-averse decisions and confidence-aware multi-objective decisions already exist. Generic conformal action selection is rejected as the novelty claim. |
| Safe remediation | [Dai et al., 2026](https://arxiv.org/abs/2607.20005) | Risk-constrained remediation, reversibility, false-remediation control, and adaptive human escalation already exist for microservices. A generic approval/rollback gate is not novel. |
| Policy-bounded autonomous remediation | [Li and Cao, USENIX Security 2026 (PatchWeaver)](https://www.usenix.org/conference/usenixsecurity26/presentation/li-rui) | Explicit approvals/evidence, executable change predicates, predicted policy risk, and replanning under divergence already exist outside networking. SafeTwin cannot claim policy-gated autonomy as a generic systems invention. |
| Formal conformal safety | [Lindemann et al., 2025](https://ieeexplore.ieee.org/abstract/document/11274485) | Conformal safety for learning-enabled control and verification is established. SafeTwin must not claim first conformal safety control. |

This search did not find the exact combination of complete named-action
clean-reset blocks, simultaneous action-contrast calibration, evidence-tier
gating, and replayable 5G-core remediation. Non-discovery is not proof of
novelty. The claim remains provisional until a broader systematic review and
external peer review.

## Search boundary

The 2026-08-25 audit searched primary standards/RFC repositories and primary
paper records for combinations of network digital twin, intent/service
assurance, autonomous remediation, counterfactual or causal action selection,
conformal decision guarantees, rollback, and private 5G. Secondary surveys were
used only to discover candidate primary sources and do not support a novelty
claim. A source was treated as a collision whenever it already supplied a
claimed mechanism, even outside telecom; the application domain was not used to
rename a generic conformal or safety idea as novel. The literature cut-off,
queries, URLs, and collision decisions must be reported in any manuscript.

## Fatal Phase 6 limitation corrected in Phase 7

Dataset v1 uses the arm names `effective` and `negative_control`. Those labels
encode whether an action should help or hurt and make a learned selector appear
more informed than a deployable policy. Phase 7 uses the same named operational
actions in every fault context:

1. observe only;
2. clear packet impairment;
3. resume the UPF;
4. stop CPU stress; and
5. apply 25% packet impairment as a reversible distractor.

No action identifier says which fault it addresses. Every assignment block
contains every action after a clean reset. The independent analysis unit is the
complete block, never a telemetry row.

## BRACE guarantee contract

For block (b), action (a), and the observe-only reference (0), define the
measured improvement

\[
\Delta_b(a) = Y_b(0) - Y_b(a),
\]

where lower burden is better. A training-only model produces
\(\widehat{\Delta}_b(a)\). For every independent calibration block, BRACE uses

\[
S_b = \max_{a \in \mathcal{A}_{mut}}
|\Delta_b(a)-\widehat{\Delta}_b(a)|.
\]

The finite-sample split-conformal quantile of the block scores gives one radius
for a simultaneous vector interval over all candidate actions. Under
exchangeable complete blocks, fixed training, clean-reset consistency, and no
cross-unit interference, the new block's full contrast vector has marginal
simultaneous coverage of at least 90%. Therefore an action selected *after*
examining the intervals is covered by the same event. BRACE certifies a mutation
only when its lower contrast bound exceeds the frozen benefit margin.

The guarantee is marginal over exchangeable blocks, not conditional for every
fault or action. It does not apply under detected OOD, incomplete action blocks,
failed recovery, hardware, or operator networks. Those cases abstain. A
certificate remains a proposal requiring human approval; it is never an
actuation authorization.

## TNSM viability gates

The project may be described as a TNSM candidate only if all of the following
are completed without changing the frozen test rules:

- BRACE implementation and its fail-closed tests pass;
- the precision-amended fresh 675-unit named-action campaign completes with
  135 clean blocks (`docs/PHASE7_PROTOCOL_AMENDMENT_1.md`);
- all 70 test-block labels remain sealed until code and hashes freeze;
- the 90% simultaneous coverage and non-trivial selective-utility gates pass;
- comparisons include runbook, point, scalar conformal, and
  action-conditional conformal baselines plus ablations;
- action, recovery, false-remediation, runtime, and scaling distributions are
  reported with counts, denominators, uncertainty, and negative results;
- the artifact is independently replayed or audited; and
- claims remain `sandbox-measured` for interventions and `simulated` for radio.

A baseline win, insufficient coverage, unbounded quantile, or failed recovery
is a valid no-go. Hardware and operator validation remain separate external
gates, not implied paper evidence.
