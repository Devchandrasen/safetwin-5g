# Phase 7 BRACE v1 Exploratory Feasibility

**Result:** negative design result; no confirmatory or promotion claim

## Locked v1 result

- Strict five-action complete blocks: `0/44`.
- Legacy calibration blocks: `7`; 90% rank: `8`; status: `unbounded`.
- Legacy ID test certificates: `0/7`.
- Legacy OOD certificates: `0/16`.

The strict named-action effect vector is not identified in v1, and the
legacy two-arm exploratory calibration is unbounded. BRACE therefore
abstains on every v1 test and OOD block. Phase 6 remains unchanged.

## Prospective v2 precision check

- Frozen calibration blocks: `21` (finite rank possible).
- Frozen test blocks: `35`, including `30` faulty blocks.
- Minimum certified mutations at 50% faulty-block coverage: `15`.
- One-sided 95% zero-violation upper bound at that minimum: `0.1810`.
- Minimum zero-violation sample for an upper bound below 0.10: `29`.

increase fresh test design to at least 60 faulty blocks if a one-sided 95% empirical upper bound below 0.10 at 50% coverage is required; otherwise keep the safety statement theorem-based

## Claim boundary

Interventions are `sandbox-measured`; radio is `simulated`. Hardware,
operator validation, live actuation, and a positive TNSM claim remain absent.
