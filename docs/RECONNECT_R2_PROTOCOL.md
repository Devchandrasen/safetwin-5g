# Reconnect R2: bounded source-correction engineering comparison

Frozen before any candidate is applied to a running sandbox. This protocol
follows the accepted R1 **failure reproduction**, not a successful recovery
pilot. It changes no statistical source, partition, threshold or prior artifact.

## Source hypothesis and bounded correction

The pinned UERANSIM Initial NAS path extracts an SST only from an initial
Registration Request and uses -1 otherwise. Its selectAmf implementation only
matches explicit SST values, so a Service Request's absent SST has no match.
R1 twice measured the corresponding AMF-selection/missing-PDU failure path.
The source-level counterexample must execute the exact official function with
one connected, compatible AMF: SST 1 selects, SST 2 rejects, and SST -1 rejects.
This fixture isolates the selection predicate, not the whole network path.

Candidate R2 changes only upstream `src/gnb/ngap/nnsf.cpp`. For an absent SST,
it considers connected AMFs advertising the configured PLMN and an exact
configured slice (SST and optional SD). It requires one eligible AMF. Explicit
unsupported SSTs never fall back; invalid SSTs, disconnected/unready contexts,
wrong PLMN/MNC length, absent/default slice mismatch and ambiguity reject.
Duplicate slice advertisements from the same AMF are not multiple AMFs.
Explicit SST selection retains the original SST-only granularity but now also
requires connected, same-PLMN, unambiguous candidates. This conservative policy
is for this local sandbox, not a general multi-AMF routing implementation.
NAS parsing/rewriting, authentication, ciphering, AMF reallocation and PDU
resource handling are not changed. Their broader correctness is not claimed.

The production source function is compiled against fixture interfaces for
sixteen specified selection cases, then the complete source is built against
the real upstream headers. Fixture success and a build are not network evidence.

## Separately identified image, not a replaced official pin

The official UERANSIM image stays
`safetwin5g/ueransim:3.3.0-6bf5a1a9`, image ID
`sha256:13705fc29922cf019e8c7992b5b04b9c6c584d3848d29689f1d3db64334ae725`.
The local derived tag is `safetwin5g/ueransim:3.3.0-reconnect-r2`. Build tooling
refuses pre-existing derived tags rather than overwriting a prior attempt.
It checks the official base before/after, exact upstream commit, candidate
and fixture hashes, retains the applied Git diff, licence, compiler, binary
hashes, complete source and derived image identity. Only nr-gnb is replaced;
nr-ue remains the original binary. Image/source provenance must be audited
and immutable IDs frozen in an execution lock before service replacement.

The build performs no service mutation. Its read-only evidence containers have
no network, published ports, capabilities, host mounts or sandbox attachment.
No external registry push or upstream contribution is authorized. Build and
source evidence are labelled fixture, with network-validation flags false.

## Fixed future network comparison

Before running this section, commit its execution runner, independent auditor,
approval contract, image IDs and regression tests. Do not execute from prose.

Use eight trials in two fixed legs: official, then derived. Each leg has
control-before, drop-a, drop-b, control-after with the same eight-second UE
eth0 loss, owned handle 7157, in-container 15-second timeout, EXIT rollback,
five-second settling delay and three five-packet baseline/post windows as R1.
The deterministic leg order is disclosed; this is engineering verification,
not a randomized performance comparison or population reliability estimate.

Before each trial, use the fixed fresh core/gNB/UE preparation and verify fresh
registration/PDU establishment, 15/15 baseline packets, neutral qdisc, UPF
running, no fault workers and three up Prometheus targets. Stop on invalid
baseline, uncontrolled impairment, missing data or failed final restoration.
Retain every failure and add no replacement trials.

Official drop trials must reproduce the R1 failure; official controls must be
clean. Derived drop trials must show link loss, subsequent Service Request,
successful service acceptance and PDU-resource re-establishment in gNB/core
logs, without AMF-selection errors. Their post window must deliver 15/15 with
no intervening UE restart. Derived controls must remain clean. Post-failure
restoration does not count as automatic recovery. A partial pattern is not a
verified fix, and unsuccessful derived observations do not justify retries.

All legs retain the approved UE restart then full reset safety-restoration
ladder, including failed steps. Use only the SafeTwin gNB container/image
replacement plus its core/UE resets; retain MongoDB/Prometheus data and leave
unrelated containers untouched. Image switching requires explicit experiment
approval and an override separate from the official Compose file. Pin/check
the exact selected image ID, isolated network, mounts, devices and capabilities
before each leg. Record commands, versions, UTC times, source/patch/binary/image
hashes, approvals, samples and log evidence for independent replay.

The network admission budget is 25 minutes. Safety rollback remains enabled
after admission expires, with bounded commands. After either success or failure,
restore the official gNB image, then reset core/gNB/UE and verify fresh
registration/PDU state and 15/15 packet delivery. A new derived baseline must
not remain installed implicitly. No long campaign or interruption pilot starts
inside this comparison.

The execution auditor must distinguish protocol validity, official failure
reproduction, candidate automatic recovery and final official-image rollback.
An image build, fixture test, or successful restoration cannot set the candidate
network-fix flag. Hardware/operator evidence and TNSM readiness remain false.
D1 shared-host limitations apply; simulated radio is never physical RF. P1 and
the rejected 675-unit campaign stay untouched.

## Primary source anchors

- [Initial NAS handling](https://github.com/aligungr/UERANSIM/blob/6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156/src/gnb/ngap/nas.cpp)
- [AMF selection](https://github.com/aligungr/UERANSIM/blob/6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156/src/gnb/ngap/nnsf.cpp)
- [NGAP context and PDU-resource setup](https://github.com/aligungr/UERANSIM/blob/6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156/src/gnb/ngap/context.cpp)
- [AMF/gNB types](https://github.com/aligungr/UERANSIM/blob/6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156/src/gnb/types.hpp)
- [PLMN and slice types](https://github.com/aligungr/UERANSIM/blob/6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156/src/utils/common_types.hpp)
