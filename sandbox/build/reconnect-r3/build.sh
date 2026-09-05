#!/bin/sh
set -eu
cd /usr/src/UERANSIM
test "$(git rev-parse HEAD)" = "6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156"
test "$(git status --porcelain)" = " M src/gnb/ngap/nnsf.cpp"
test ! -e /opt/safetwin-r3
mkdir /opt/safetwin-r3
git rev-parse HEAD > /opt/safetwin-r3/upstream-commit.txt
git diff --binary > /opt/safetwin-r3/base.diff
test "$(sha256sum /opt/safetwin-r3/base.diff | cut -d ' ' -f1)" = "4d3df81523ae2b9c6753d96e036cab5126a9b2a988e107ce05f365a92e62522c"
sha256sum -c /opt/safetwin-r3-input/base-source.sha256
git ls-files -z | xargs -0 sha256sum > /opt/safetwin-r3/source-before.sha256
sha256sum /opt/ueransim/bin/* > /opt/safetwin-r3/bin-before.sha256
dpkg-query -W > /opt/safetwin-r3/packages-before.txt
git -c core.autocrlf=false apply --check /opt/safetwin-r3-input/instrumentation.diff
git -c core.autocrlf=false apply /opt/safetwin-r3-input/instrumentation.diff
sha256sum -c /opt/safetwin-r3-input/expected-source.sha256
git diff --check
git status --porcelain > /opt/safetwin-r3/source-status.txt
git diff --binary > /opt/safetwin-r3/tracked-source.diff
cp LICENSE /opt/safetwin-r3/LICENSE
cp /opt/safetwin-r3-input/instrumentation.diff /opt/safetwin-r3/instrumentation.diff
g++ --version > /opt/safetwin-r3/compiler.txt
cmake --version > /opt/safetwin-r3/cmake.txt
date -u +%Y-%m-%dT%H:%M:%SZ > /opt/safetwin-r3/build-start.txt
# Incremental real-header build: do not run upstream's destructive clean target.
set +e
timeout -k 10 600 cmake --build cmake-build-release --parallel 2 > /opt/safetwin-r3/compile.log 2>&1
result=$?
set -e
cat /opt/safetwin-r3/compile.log
test "$result" -eq 0
cp cmake-build-release/nr-ue /opt/ueransim/bin/nr-ue
cp cmake-build-release/nr-gnb /opt/ueransim/bin/nr-gnb
git ls-files -z | xargs -0 sha256sum > /opt/safetwin-r3/source-after.sha256
sha256sum src/utils/safetwin_trace_r3.hpp >> /opt/safetwin-r3/source-after.sha256
sha256sum /opt/ueransim/bin/* > /opt/safetwin-r3/bin-after.sha256
sha256sum cmake-build-release/nr-ue cmake-build-release/nr-gnb > /opt/safetwin-r3/compiled-binaries.sha256
dpkg-query -W > /opt/safetwin-r3/packages-after.txt
cmp /opt/safetwin-r3/packages-before.txt /opt/safetwin-r3/packages-after.txt
sha256sum -c /opt/safetwin-r3-input/expected-source.sha256
date -u +%Y-%m-%dT%H:%M:%SZ > /opt/safetwin-r3/build-end.txt
printf 'REAL_HEADER_BUILD_COMPLETED\n'
