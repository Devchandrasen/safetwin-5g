# Local R2 tag is checked by ID before/after, and its layer prefix is audited.
FROM safetwin5g/ueransim:3.3.0-reconnect-r2
LABEL safetwin5g.derived.revision="reconnect-r3-trace"
LABEL safetwin5g.derived.base.image="sha256:2a5c01c503927c44a6b45f8b074491ac64a42fc3a444ea2af0a8cbe5df8e537e"
LABEL safetwin5g.derived.claim="instrumentation-only-not-network-validated"
LABEL safetwin5g.derived.source.sha256="e50a96ad8dfa409cf9344faf0f0cfb4dbea9783caa87185d49f5f435a8ca9f0e"
LABEL safetwin5g.derived.source.kind="frozen-instrumentation-patch"
LABEL safetwin5g.derived.source.contract="b7f402fa6969fd88fccb230a79549ef50b1b06b1"
COPY build.sh instrumentation.diff expected-source.sha256 base-source.sha256 /opt/safetwin-r3-input/
WORKDIR /usr/src/UERANSIM
RUN timeout -k 10 660 sh /opt/safetwin-r3-input/build.sh
WORKDIR /opt/ueransim
