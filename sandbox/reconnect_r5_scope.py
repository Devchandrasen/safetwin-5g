"""Clock-free R5 scope parser derived from immutable R3 scope checks."""
import json
from pathlib import Path
from sandbox.reconnect_r3_measurement import CORE, GNB, UE, CONTAINERS, NETWORK, HOST_FIELDS
from sandbox.run_recovery_pilot import validate_environment
ROOT = Path(__file__).resolve().parents[1]


def validate_scope(raw_network, text, role, reference, images):
    network_rows = json.loads(raw_network)
    if len(network_rows) != 1: raise PermissionError("one isolated network required")
    network = network_rows[0]
    containers = [json.loads(line) for line in text.splitlines()]
    validate_environment(network, containers, json.loads((ROOT / "sandbox/versions.lock.json").read_bytes())["components"])
    current = {row["Name"].lstrip("/"): row for row in containers}
    if len(containers) != 5 or set(current) != set(CONTAINERS): raise PermissionError("exact container inventory required")
    if {key: value["Name"] for key, value in network["Containers"].items()} != {row["Id"]: name for name, row in current.items()}:
        raise PermissionError("network attachment identity mismatch")
    for name, row in current.items():
        hc = row["HostConfig"]
        if row["State"]["Running"] is not True or row["NetworkSettings"]["Networks"][NETWORK]["NetworkID"] != network["Id"]:
            raise PermissionError("running state/network ID mismatch")
        caps = {"CAP_NET_ADMIN", "CAP_NET_RAW"} if name in (CORE, UE) else set()
        if set(hc.get("CapAdd") or []) != caps or hc.get("CapDrop") or hc.get("PidMode") or hc.get("Privileged") or hc.get("PortBindings"):
            raise PermissionError("capability/namespace scope")
        devices = [{"PathOnHost": "/dev/net/tun", "PathInContainer": "/dev/net/tun", "CgroupPermissions": "rwm"}] if name in (CORE, UE) else []
        if (hc.get("Devices") or []) != devices: raise PermissionError("device scope")
        if name in (GNB, UE):
            if row["Image"] != images[role + "_image_id"]: raise PermissionError("both UERANSIM image IDs must match")
            if role == "derived" and row["Config"]["Labels"].get("safetwin5g.derived.revision") != "reconnect-r3-trace": raise PermissionError("R3 revision missing")
            component = "gnb" if name == GNB else "ue"
            if len(row["Mounts"]) != 1: raise PermissionError("UERANSIM mount count")
            mount = row["Mounts"][0]
            if mount["RW"] or mount["Destination"] != f"/etc/ueransim/{component}.yaml" or Path(mount["Source"]).resolve() != (ROOT / f"sandbox/config/ueransim/{component}.yaml").resolve():
                raise PermissionError("UERANSIM mount source/destination")
            if row["Config"]["Cmd"] != [f"/opt/ueransim/bin/nr-{component}", "-c", f"/etc/ueransim/{component}.yaml"]:
                raise PermissionError("UERANSIM command drift")
    for name, row in current.items():
        original = reference[name]
        if name not in (GNB, UE) and row["Image"] != original["Image"]: raise PermissionError("other component image changed")
        mounts = lambda data: sorted(data["Mounts"], key=lambda m: m["Destination"])
        if (mounts(row) != mounts(original) or any(row["HostConfig"].get(k) != original["HostConfig"].get(k) for k in HOST_FIELDS)
                or any(row["Config"].get(k) != original["Config"].get(k) for k in ("Cmd", "Entrypoint", "User", "WorkingDir"))):
            raise PermissionError("container execution scope changed")
    return containers
