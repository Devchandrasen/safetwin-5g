# A locally derived engineering image. The official image/tag is not replaced.
FROM safetwin5g/ueransim:3.3.0-6bf5a1a9
ARG CANDIDATE_SHA256
ARG FIXTURE_SHA256
LABEL safetwin5g.derived.revision="reconnect-r2"
LABEL safetwin5g.derived.source.sha256="${CANDIDATE_SHA256}"
LABEL safetwin5g.derived.base.image="sha256:13705fc29922cf019e8c7992b5b04b9c6c584d3848d29689f1d3db64334ae725"
LABEL safetwin5g.derived.claim="engineering-candidate-not-network-validated"
ENV CMAKE_BUILD_PARALLEL_LEVEL=2

COPY nnsf.cpp /candidate/nnsf.cpp
COPY fixture /fixture
WORKDIR /usr/src
RUN test "$(sha256sum /candidate/nnsf.cpp | cut -d ' ' -f1)" = "$CANDIDATE_SHA256" \
    && test "$(sha256sum /fixture/test.cpp | cut -d ' ' -f1)" = "$FIXTURE_SHA256" \
    && git clone --depth 1 --branch v3.3.0 https://github.com/aligungr/UERANSIM.git \
    && test "$(git -C UERANSIM rev-parse HEAD)" = "6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156"

WORKDIR /usr/src/UERANSIM
RUN mkdir -p /opt/safetwin-r2 /tmp/selection-test \
    && cp src/gnb/ngap/nnsf.cpp /tmp/selection-test/nnsf.cpp \
    && g++ -std=c++17 -I/fixture /tmp/selection-test/nnsf.cpp /fixture/test.cpp -o /tmp/selection-test/official \
    && /tmp/selection-test/official --official-counterexample > /opt/safetwin-r2/official-counterexample.log \
    && cp /candidate/nnsf.cpp src/gnb/ngap/nnsf.cpp \
    && cp src/gnb/ngap/nnsf.cpp /tmp/selection-test/nnsf.cpp \
    && g++ -std=c++17 -I/fixture /tmp/selection-test/nnsf.cpp /fixture/test.cpp -o /tmp/selection-test/candidate \
    && /tmp/selection-test/candidate > /opt/safetwin-r2/selection-fixtures.log \
    && git diff --binary > /opt/safetwin-r2/patch.diff \
    && git diff --check \
    && cp LICENSE /opt/safetwin-r2/LICENSE \
    && git rev-parse HEAD > /opt/safetwin-r2/upstream-commit.txt \
    && g++ --version > /opt/safetwin-r2/compiler.txt

# Compile against the actual upstream types, not only the fixture interfaces.
# Retain corresponding source and patch inside this local derived image.
RUN make -j2 \
    && cp build/nr-gnb /opt/ueransim/bin/nr-gnb \
    && sha256sum /opt/ueransim/bin/nr-gnb /opt/ueransim/bin/nr-ue \
        /opt/safetwin-r2/patch.diff > /opt/safetwin-r2/binary-patch-sha256.txt
WORKDIR /opt/ueransim
