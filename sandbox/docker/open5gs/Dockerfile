# syntax=docker/dockerfile:1.7
FROM docker.io/library/ubuntu:22.04@sha256:2edbbc5dc405e9612ba3584ce95480277e3eb374407b5505fe26f17df77c7dbc

ARG OPEN5GS_TAG=v2.7.7
ARG OPEN5GS_COMMIT=318eeb49a7dcdff733dec60e02d9c60aefca2fb9

LABEL org.opencontainers.image.title="SafeTwin-5G Open5GS sandbox"
LABEL org.opencontainers.image.source="https://github.com/open5gs/open5gs"
LABEL org.opencontainers.image.version="2.7.7"
LABEL safetwin5g.upstream.commit="${OPEN5GS_COMMIT}"
LABEL safetwin5g.evidence.ceiling="sandbox-measured"

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH=/opt/open5gs/bin:${PATH}
ENV LD_LIBRARY_PATH=/opt/open5gs/lib/x86_64-linux-gnu:/opt/open5gs/lib

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bison \
        build-essential \
        ca-certificates \
        cmake \
        curl \
        flex \
        git \
        iproute2 \
        iptables \
        iputils-ping \
        libbson-dev \
        libcurl4-gnutls-dev \
        libgcrypt20-dev \
        libgnutls28-dev \
        libidn11-dev \
        libmicrohttpd-dev \
        libmongoc-dev \
        libnghttp2-dev \
        libsctp-dev \
        libssl-dev \
        libtalloc-dev \
        libtins-dev \
        libyaml-dev \
        meson \
        ninja-build \
        pkg-config \
        procps \
        python3 \
        python3-pip \
        python3-setuptools \
        python3-wheel \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src
RUN git clone --depth 1 --branch "${OPEN5GS_TAG}" https://github.com/open5gs/open5gs.git \
    && test "$(git -C open5gs rev-parse HEAD)" = "${OPEN5GS_COMMIT}" \
    && meson setup open5gs/build open5gs --prefix=/opt/open5gs --buildtype=release \
    && ninja -C open5gs/build -j2 \
    && ninja -C open5gs/build install \
    && rm -rf /usr/src/open5gs/.git /usr/src/open5gs/build

COPY configure.py /usr/local/lib/safetwin5g-configure-open5gs.py
RUN python3 /usr/local/lib/safetwin5g-configure-open5gs.py \
    && rm /usr/local/lib/safetwin5g-configure-open5gs.py

COPY entrypoint.sh /usr/local/bin/safetwin5g-open5gs-entrypoint
RUN chmod 0755 /usr/local/bin/safetwin5g-open5gs-entrypoint

ENTRYPOINT ["/usr/local/bin/safetwin5g-open5gs-entrypoint"]
