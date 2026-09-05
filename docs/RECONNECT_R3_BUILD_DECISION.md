# R3 real-header build accepted, network diagnostic pending

Date: 2026-09-05. **The separately tagged instrumentation image builds and
passes the versioned independent build audit. It has not been installed in
the running sandbox. No R3 network trial or recovery fix is validated.**

## Measured build evidence

The source contract was committed as `b7f402fa6969fd88fccb230a79549ef50b1b06b1`
before the build. No frozen R3 overlay, protocol, fixture, R2 source or
statistical file was changed to compile it. The local image lock is
`config/experiments/reconnect-r3-images.json`.

- Build: `evidence/engineering/20260905T111542Z-reconnect-r3-build-release`.
- New image: `sha256:0c9773889f62ee848144b359349014ea8200c5edab995c303a3d38a75cc70c32`.
- New tag: `safetwin5g/ueransim:3.3.0-reconnect-r3-trace`.
- Compiler: g++ Debian 12.2.0-14+deb12u1; CMake 3.25.1.
- Captured compile interval: 11:15:45 to 11:15:48 UTC.
- 34 commands; 4,267 tracked source files plus the new header audited.

The Docker build resolves the existing R2 ID. Its filesystem-layer prefix is
retained in the derived image. The same official and R2 IDs were observed
before and after. A deterministic five-file tar context supplies the frozen
patch, checksums, Dockerfile and build script; no package install or source
download is in that script. Build commands use `--pull=false --network=none`.
Docker documents that the network option controls build RUN instructions;
it is not a claim of packet-captured daemon-wide air-gapping. See the
[official build reference](https://docs.docker.com/reference/cli/docker/buildx/build/).

The incremental CMake build explicitly compiles NAS `sap.cpp`, UE RLS
`ctl_task.cpp` and gNB GTP `task.cpp` against real upstream headers. Only those
three tracked source hashes and the added trace header differ. The prior R2
AMF-selection patch, all other tracked files, licence and package inventory
are preserved. Both `nr-ue` and `nr-gnb` change and match their linked build
outputs; the three other installed executables/library hashes stay unchanged.
Both new binaries start their help path in network-disabled, read-only,
capability-dropped ephemeral containers. This is not NAS/RRC runtime validation.

The compiler has a 600-second timeout, two build workers, and enclosing
660/720-second bounds. Two workers are not a hard CPU/memory isolation claim.
The observed build finishes in seconds. No independent image rebuild was
performed and bit-for-bit image reproducibility is not claimed. Reproduction
requires the retained R2 image/source toolchain or its separately pinned build.
Do not overwrite this completed tag or rebuild it merely to obtain another ID.

## Original audit rejection and narrow amendment

The first auditor rejected `container changed: /safetwin5g-mongodb:Mounts`.
The raw snapshots show the same three complete mount objects in a different
array order. No mount field differs. The check treated array order as storage
configuration identity, causing a false rejection. The original auditor and
raw bundle remain byte-identical and still reproduce that rejection.

`tools/audit_reconnect_r3_build_v2.py` loads the frozen v1 auditor into its own
module namespace and normalizes only each container's mount-array order by
unique destination. It compares every mount field and rejects duplicate
destinations. All other v1 checks run unchanged. Regressions demonstrate that
order alone fails v1 and passes v2, while source, permission, destination and
container-state changes still fail. No network endpoint was relaxed.

Before/after checks cover 17 existing containers, including stopped containers:
IDs, image IDs, start/finish state, restart counts, Config, HostConfig and mount
contents match. Both running SafeTwin UE/gNB remain on the official image.
These snapshots are not a measurement of continuous availability, packet
delivery, or every possible internal state. No restart, exec, Compose change,
fault or service replacement occurred in the 34-command build record.

## Privacy-preserving release

Full Docker inspect output included unrelated projects' environment/config
fields. That raw build directory is retained **locally and ignored by Git**;
it was not edited or uploaded. The separately named release replaces service
Config, HostConfig and non-destination mount fields with equality commitments
using HMAC-SHA256 and a random, locally retained private key. Unneeded inspect
fields and health logs are omitted. No configuration secret or key is exported.

The release records its original manifest hash, every changed captured-file
hash, original v1 rejection, and raw-v2 audit result. Only two inspect outputs
and their command-output hash links change. An independent private audit
verifies the transformation against every original file and the private key.
The public-facing audit checks the release structure and equality commitments.
It cannot reconstruct or independently inspect secret values without private
access. This disclosure is intentional, not a claim that redacted output is raw.

The first release guard refused an unreviewed image environment key before
writing a key or release. Inspection identified the existing
`LD_LIBRARY_PATH=/opt/ueransim/bin` from the official sandbox Dockerfile; that
specific key was added to the export allowlist. The raw build was not repeated.
An earlier read-only source inspection also returned exit 1 because it asked
for `Makefile`; the retained upstream file is lowercase `makefile`. Neither
tooling observation is a failed network trial or a hidden build retry.

## Verification and next gate

`evidence/verification/20260905T112828Z-reconnect-r3-build` records:

```text
306 passed, 32 subtests passed in 8.32s
```

Eight checks pass their declared expectations: the original audit rejection
is reproduced with exit 1, while raw-v2, release-v2, private redaction, full
tests, frozen R3 source audit, negative R2 network audit and statistical lock
succeed. The failed v1 audit is not relabelled as a passing v1 audit.
The earlier 305-test capture is retained; the additional regression checks the
new image lock against measured image, binary and patch hashes. A local
privacy scan found no raw secret-bearing environment entries in the release
across 13 such entries from the private service snapshots.

Next implement and independently verify the fixed R3 network runner, raw-ping
and trace auditor, scoped two-service Compose override, approval record and
rollback checks. Commit those contracts and this measured image lock before
any image application. Future snapshots should request only required fields
at collection time, avoiding full private Docker inspect output.

The fixed four-trial protocol, unique ping identifiers, first-packet retention,
15/15 recovery endpoint and mandatory official UE/gNB rollback remain intact.
Trace accounting is separate from recovery. Do not start a new long campaign.
R2 remains rejected at 14/15; the original 675-unit campaign remains rejected;
Phase 6 remains negative. D1, P1, absent hardware/operator validation and all
statistical locks remain. This build is `fixture`, not network, hardware,
operator-validated, confirmatory BRACE or TNSM-ready evidence.

DEBUG REPORT

- Symptom: original audit rejects a storage-mount difference after compilation.
- Root cause: array-order comparison despite identical complete mount objects.
- Fix: a separate v2 audit normalizes order, without changing old code/evidence.
- Evidence: original failure reproduced, v2 raw/release audit and regressions pass.
- Status: DONE for the build/audit correction; network validation remains pending.

The investigate skill prompted the raw-object comparison before a correction.
The bug fix is confined to the new v2 auditor and its tests; artifact privacy
work and status docs are separate local release steps. No global freeze state,
tool upgrade, checkpoint preference or durable memory was changed. The project
learning is retained here: compare mount identity by unique destination and
all contents, not JSON array order; collect minimal inspect fields from the start.
