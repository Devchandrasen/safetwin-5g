# syntax=docker/dockerfile:1.7
FROM docker.io/library/debian:bookworm-slim@sha256:abd67ffcfa541b485a3dff59865ab629aa048a6c613e639d36e7456b0b229241

ARG UERANSIM_TAG=v3.3.0
ARG UERANSIM_COMMIT=6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156

LABEL org.opencontainers.image.title="SafeTwin-5G UERANSIM sandbox"
LABEL org.opencontainers.image.source="https://github.com/aligungr/UERANSIM"
LABEL org.opencontainers.image.version="3.3.0"
LABEL safetwin5g.upstream.commit="${UERANSIM_COMMIT}"
LABEL safetwin5g.radio.evidence="simulated"

ENV DEBIAN_FRONTEND=noninteractive
ENV LD_LIBRARY_PATH=/opt/ueransim/bin

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        cmake \
        git \
        iproute2 \
        iputils-ping \
        libsctp-dev \
        lksctp-tools \
        make \
        procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src
RUN git clone --depth 1 --branch "${UERANSIM_TAG}" https://github.com/aligungr/UERANSIM.git \
    && test "$(git -C UERANSIM rev-parse HEAD)" = "${UERANSIM_COMMIT}" \
    && make -C UERANSIM -j2 \
    && mkdir -p /opt/ueransim/bin \
    && cp UERANSIM/build/nr-gnb UERANSIM/build/nr-ue UERANSIM/build/nr-cli \
        UERANSIM/build/nr-binder UERANSIM/build/libdevbnd.so /opt/ueransim/bin/ \
    && rm -rf /usr/src/UERANSIM

WORKDIR /opt/ueransim
