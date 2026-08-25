# BRACE-v1 Method Contract

## Purpose

BRACE (Block-Randomized Action Certification with Evidence tiers) wraps a
training-only action-effect predictor. It returns either a simultaneous
benefit certificate for one named remediation proposal or a fail-closed
abstention/rejection. It never authorizes application.

## Data object

A complete assignment block contains one clean-reset measurement for the
observe-only reference and one for every frozen mutating action. For burden
outcome (Y), where lower is better, action benefit is

\[
\Delta_b(a)=Y_b(0)-Y_b(a).
\]

Training data fit any frozen predictor
\(\widehat{\Delta}(X_b,a)\). The conformal calibration unit is an entire block,
not an action row or telemetry sample.

## Simultaneous block calibration

For each of (n) independent calibration blocks, compute

\[
S_b=\max_{a\in\mathcal A_{mut}}
\left|\Delta_b(a)-\widehat{\Delta}(X_b,a)\right|.
\]

With target coverage (1-\alpha), set

\[
k=\left\lceil(n+1)(1-\alpha)\right\rceil
\]

and let (q) be the (k)-th smallest calibration score. If (k>n), BRACE
sets (q=\infty) and every mutation abstains. Otherwise the interval for each
action is

\[
C_a(X)=[\widehat{\Delta}(X,a)-q,
        \widehat{\Delta}(X,a)+q].
\]

## Finite-sample proposition

Assume the fitted predictor is fixed before calibration and the (n)
calibration blocks plus a new block are exchangeable, complete, clean-reset
consistent, and free of cross-unit interference. Then, with randomized tie
breaking or the usual conservative order statistic,

\[
P\{\forall a\in\mathcal A_{mut}:\Delta_{n+1}(a)\in C_a(X_{n+1})\}
\ge 1-\alpha.
\]

**Proof sketch.** The new block score and the (n) calibration block scores
are exchangeable. The new score therefore has rank at most
\(\lceil(n+1)(1-\alpha)\rceil\) with probability at least (1-\alpha).
Whenever that event holds, the new maximum residual is at most (q), which is
equivalent to simultaneous inclusion of every action contrast in its interval.
The score is one scalar per block, so dependence between action outcomes inside
a block does not require an independence assumption. QED.

If a policy selects any action after seeing the full interval vector and only
certifies when the selected lower bound exceeds margin (m), the same joint
event implies the selected action's true benefit exceeds (m). This is the
post-selection property used by BRACE. It is inherited from simultaneous vector
coverage, not claimed as a new general conformal theorem.

## Safety decision contract

An action enters the candidate set only if:

- its lower benefit bound is greater than the frozen margin;
- the context is in frozen design support;
- the evidence is `sandbox-measured` and radio is `simulated`;
- no hardware or operator validation is inferred;
- the action is allowlisted and reversible; and
- a pre-action rollback plan exists.

The candidate with the largest lower bound is proposed; identifier order breaks
ties. The output is `require-human-approval`. Missing candidates, unbounded
calibration, OOD, or claim-boundary mismatch returns `abstain`; a non-sandbox
environment returns `reject`. `apply_allowed` is always false.

## Non-guarantees

The guarantee is marginal across exchangeable blocks. It is not per-fault,
per-action, conditional, OOD, hardware, operator, or live-network coverage. It
does not guarantee that recovery succeeds; recovery is separately measured and
must pass. It does not convert approval into actuation authority.
