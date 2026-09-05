# R2 execution contract

This implements the previously frozen R2 protocol, not an endpoint amendment.
The eight exact assignments, their order, 8-second impairment, 15-second
in-container timeout, 5-second settling interval, 15-packet windows and
25-minute admission budget are unchanged. No candidate network result existed
when this contract was written.

`sandbox/run_reconnect_r2.py` reuses the unchanged R1 fault, sampling and
per-trial restoration helpers. Its additional scope checks require the exact
official/derived image IDs, unchanged other component images, internal-only
network and matching mounts/devices/capabilities and command configuration.
The gNB has no added capabilities or devices and only its expected read-only
configuration mount. The separate Compose override must differ from the base
configuration only in the gNB image. Image replacement uses only the gNB
service, with no dependency recreation, builds, pulls or volume removal.

Approval is recorded before commands under the user's standing local sandbox
authorization. It names all eight assignments, both immutable image IDs, exact
containers, fixed resets, owned fault handle and mandatory rollback. It is not
a fresh operator signature. Source hashes and image locks are recorded before
mutations; tests or a build do not authorize a live action.

The first failed trial, missing official failure reproduction or unverified
candidate recovery stops further assignments without adding replacements.
Every failed observation and performed action remains in its original record.
All drop trials still receive the approved post-observation restoration. An
outer finally path clears the owned qdisc, restores the official gNB image
after any attempted candidate replacement, then resets core/gNB/UE and checks
fresh registration/PDU and 15/15 final packets. Cleanup errors do not suppress
the attempt to restore the official image and are never erased by later success.

The candidate endpoint requires R1's three clean post windows, link-failure and
Service Request logs, UE `Service Accept received`, and gNB
`Initial Context Setup Request received`, with no AMF-selection failure. The
context log plus restored user-plane delivery is the operational PDU-resource
check; an Initial Context Setup header alone does not prove resource success
and no new PDU Session ID or new session-creation claim is inferred.
The upstream [Service Accept handler](https://github.com/aligungr/UERANSIM/blob/6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156/src/ue/nas/mm/service.cpp)
and [context handler](https://github.com/aligungr/UERANSIM/blob/6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156/src/gnb/ngap/context.cpp)
define those log markers. The first post packet is both a traffic stimulus and
part of the measurement; it is not discarded as warm-up. Partial delivery,
including just one lost packet, cannot pass the frozen 15/15 endpoint.

`tools/audit_reconnect_r2.py` independently replays raw ping/telemetry commands,
assignments, scope snapshots, source/image hashes, log markers, timing, reset
order, exact fault/rollback states, first-stop semantics and terminal rollback.
It does not trust runtime success flags or call the runtime classification.
It may accept the integrity of a faithfully stopped comparison while reporting
`protocol_execution_valid=false` and `network_fix_validated=false`. That is
not eight-trial completion or a successful correction. Invalid trial artifacts
or failed rollback are rejected. Software and build verification remain
separate from network endpoint acceptance.

The official Compose file, source/version lock, prior artifacts and frozen
statistical sources stay unchanged. D1 and simulated-radio limitations remain;
the historical P1 disclosure and rejected campaign are not revisited. Even a
positive eight-trial correction gate does not validate the UPF watchdog,
repeated-interruption pilot, long campaign, BRACE superiority or TNSM readiness.
