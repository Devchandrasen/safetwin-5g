# Phase 7 Analysis Amendment A1 — G3 no-fault denominator

**Frozen:** 2026-08-25 during train-split campaign execution, before any test
unit was executed or any test label was opened.  
**Trigger:** source-code audit, not an observed outcome.

The first sealed implementation matched BRACE and the point-estimate policy
only across the 60 faulty test blocks for G3. That contradicts the already
frozen harm endpoint in `docs/PHASE7_PROTOCOL.md`, which includes false
remediation in a no-fault block. Excluding the ten no-fault blocks could hide a
point policy's unsafe false remediation.

Amendment A1 therefore keeps G2 unchanged at 60 faulty test blocks but evaluates
G3 on all 70 paired test blocks. The point policy receives exactly the same
total number of mutations as BRACE, selected by its frozen predicted-benefit
ranking across all 70 blocks. BRACE and matched point-policy harms are then
compared on every paired test block. Thus a selected no-fault mutation enters
the frozen harm endpoint as false remediation.

No model, feature, split, action, benefit margin, calibration rule, p-value,
Holm correction, gate threshold, or claim boundary changes. Test labels remain
sealed, and the prior analysis lock is superseded only after new source hashes
and the full test suite pass.
