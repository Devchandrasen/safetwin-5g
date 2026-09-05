# Reconnect R2 build: source correction verified, network gate pending

Date: 2026-09-05. Commit `363f602` froze the candidate and comparison protocol
before the derived build. The independent build audit passes; no running
sandbox service has been changed by this build task.

`evidence/engineering/20260905T071413Z-reconnect-r2-build` retains the official
function counterexample, 16 passing selection fixtures, real-header/full-source
compilation, compiler version, licence, actual Git patch, binary hashes,
official/derived image identities, source hashes, commands and manifest.
The original function, executed against a one-connected-compatible-AMF fixture,
selects explicit SST 1, rejects unsupported SST 2, and also rejects absent SST
-1. The candidate accepts the last case while rejecting incompatible,
disconnected, unready, invalid and ambiguous inputs. These are source fixtures,
not extra sandbox measurements or proof of end-to-end recovery.

Only upstream `src/gnb/ngap/nnsf.cpp` changes. The independent auditor applies
the recorded patch to the retained original source in a temporary fixture tree
and verifies exact candidate content. The real upstream source also compiles
against its actual types. Both original and modified source, the patch and
licence remain available inside the local derived image.

- Official image: `sha256:13705fc29922cf019e8c7992b5b04b9c6c584d3848d29689f1d3db64334ae725`.
- Derived image: `sha256:2a5c01c503927c44a6b45f8b074491ac64a42fc3a444ea2af0a8cbe5df8e537e`.
- Applied patch SHA-256: `4d3df81523ae2b9c6753d96e036cab5126a9b2a988e107ce05f365a92e62522c`.
- Derived gNB binary SHA-256: `67abe4370326e7ec935d86065f9564fd8c526cf128c4fb398ef428383aff6dbf`.
- Unchanged UE binary SHA-256: `022cf739e77ba005a07bd1f61f4ed0cb8a6cf20722767fdb52d4321f31b4abac`.

The official image ID was identical before and after the build. The separate
derived tag was absent before construction and was not overwritten. Temporary
evidence containers were read-only with no network, ports, host mounts or
capabilities; they only printed build artifacts. Running containers still used
the official images after the build. No upstream publication or registry push
was performed.

`config/experiments/reconnect-r2-images.json` pins the audited identities.
`evidence/verification/20260905T071849Z-reconnect-r2` records 223 tests and
19 subtests passing, an unchanged statistical source lock, and the independent
build audit. Hash-consistent network-claim promotion, official-image drift and
an evidence container's network attachment are rejected by fixture regressions.

The sleep-inhibition wrapper transcript and manifest are in
`evidence/engineering/20260905T071413Z-reconnect-r2-build-runtime`. Inhibition
was enabled and cleared; the wrapper's blank child-exit field remains disclosed.
Acceptance uses the retained build commands and independent audit, not that
blank field or the wrapper's shell exit code.

The investigate workflow isolated the absent-SST predicate and constrained the
correction before building. Global skill upgrades, new preferences and durable
memory writes were outside this project task. Source browsing initially tried
two nonexistent paths, `src/gnb/ngap/types.hpp` and `Makefile`; the actual pinned
files are `src/gnb/types.hpp` and lowercase `makefile`. These lookup failures
were not build or network trial results.

DEBUG REPORT

- Symptom: R1 measured missing AMF/PDU selection after a simulated link return.
- Source cause: exact SST-only selection rejects the absent-SST sentinel in
  an executed original-function fixture; wider network recovery is not proven.
- Candidate: unique connected compatible AMF selection, with explicit mismatch
  and ambiguity rejection; one upstream file changed.
- Verification: 16 source fixtures, real-source compilation, patch replay,
  binary/image preservation and 223 tests plus 19 subtests.
- Status: DONE_WITH_CONCERNS for source/build validation. No network fix claim.

Next execute [the frozen R2 comparison](RECONNECT_R2_PROTOCOL.md) only after its
runner, auditor and approval/rollback contracts are committed. Until then,
`sandbox_image_applied`, `network_fix_validated`, `long_campaign_ready` and
`TNSM_ready` remain false. The recovery roadmap item stays open; R1's UPF pilot
and watchdog remain unvalidated. No rejected campaign data is reused.
