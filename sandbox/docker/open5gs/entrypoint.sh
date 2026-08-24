#!/usr/bin/env bash
set -Eeuo pipefail

mkdir -p /opt/open5gs/var/log/open5gs

if ! ip link show ogstun >/dev/null 2>&1; then
    ip tuntap add name ogstun mode tun
fi
if ! ip -4 address show dev ogstun | grep -q '10\.45\.0\.1/16'; then
    ip address add 10.45.0.1/16 dev ogstun
fi
ip link set ogstun up

declare -a names=(nrf udr udm ausf pcf nssf bsf smf upf amf)
declare -a pids=()

shutdown() {
    local pid
    for pid in "${pids[@]:-}"; do
        kill -TERM "${pid}" >/dev/null 2>&1 || true
    done
    wait || true
}
trap shutdown EXIT TERM INT

for name in "${names[@]}"; do
    binary="/opt/open5gs/bin/open5gs-${name}d"
    config="/opt/open5gs/etc/open5gs/${name}.yaml"
    "${binary}" -c "${config}" &
    pids+=("$!")
    if [[ "${name}" == "nrf" ]]; then
        sleep 1
    else
        sleep 0.5
    fi
done

echo "SafeTwin-5G Open5GS processes started: ${names[*]}"

while true; do
    for pid in "${pids[@]}"; do
        if ! kill -0 "${pid}" >/dev/null 2>&1; then
            echo "Open5GS process ${pid} exited" >&2
            exit 1
        fi
    done
    sleep 2
done
