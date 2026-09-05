"""Create a local, privacy-redacted release. No network publication is done here.

Retain raw snapshots locally. Commitments use a random private HMAC key so
configuration secrets cannot be guessed from publicly exported plain hashes.
"""
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "evidence/engineering/20260905T111542Z-reconnect-r3-build"
RELEASE = ROOT / "evidence/engineering/20260905T111542Z-reconnect-r3-build-release"
KEY_PATH = ROOT / "evidence/private/reconnect-r3-build-redaction-key.bin"


def encode(value): return (json.dumps(value, indent=2) + "\n").encode()
def sha(data): return hashlib.sha256(data).hexdigest()


def commitment(value, key):
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return {"redacted": True, "equality_hmac_sha256": hmac.new(key, canonical, hashlib.sha256).hexdigest()}


def sanitize_services(rows, key):
    state_fields = ("StartedAt", "FinishedAt", "Running", "Paused", "Restarting")
    return [{**{field: row[field] for field in ("Name", "Id", "Image", "RestartCount")},
             "Config": commitment(row["Config"], key), "HostConfig": commitment(row["HostConfig"], key),
             "Mounts": [{"Destination": mount["Destination"], **commitment(mount, key)} for mount in row["Mounts"]],
             "State": {field: row["State"][field] for field in state_fields}} for row in rows]


def main():
    # Never overwrite raw evidence, an earlier release, or its private key.
    if RELEASE.exists() or KEY_PATH.exists(): raise RuntimeError("release/key already exists; verify it, do not regenerate")
    from tools.audit_reconnect_r3_build_v2 import audit
    raw_result = audit(RAW)
    manifest_before = (RAW / "manifest.json").read_bytes()
    # Fail closed if the build image includes an unexpected environment field.
    for name in ("base-before", "base-after", "official-before", "official-after", "derived-image"):
        for row in json.loads((RAW / (name + ".stdout")).read_bytes()):
            for entry in row["Config"].get("Env", []):
                if entry.split("=", 1)[0] not in {"PATH", "DEBIAN_FRONTEND", "LD_LIBRARY_PATH", "CMAKE_BUILD_PARALLEL_LEVEL"}:
                    raise RuntimeError("unreviewed image environment field; publication refused")
    rejected = subprocess.run([sys.executable, "tools/audit_reconnect_r3_build.py", "--run", str(RAW)], cwd=ROOT, capture_output=True, timeout=30)
    if rejected.returncode != 1 or b"container changed: /safetwin5g-mongodb:Mounts" not in rejected.stderr:
        raise RuntimeError("expected original audit failure not reproduced")
    key = secrets.token_bytes(32)
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with KEY_PATH.open("xb") as stream: stream.write(key)
    RELEASE.mkdir(parents=True, exist_ok=False)
    changed = {}
    for path in RAW.iterdir():
        if path.name == "manifest.json": continue
        data = path.read_bytes()
        if path.name in ("services-before.stdout", "services-after.stdout"):
            redacted = encode(sanitize_services(json.loads(data), key))
            changed[path.name] = {"original_sha256": sha(data), "release_sha256": sha(redacted)}
            data = redacted
        (RELEASE / path.name).write_bytes(data)
    commands = json.loads((RELEASE / "commands.json").read_bytes())
    for row in commands:
        if row["name"] in ("services-before", "services-after"):
            row["stdout_sha256"] = sha((RELEASE / (row["name"] + ".stdout")).read_bytes())
    modified = encode(commands)
    changed["commands.json"] = {"original_sha256": sha((RAW / "commands.json").read_bytes()), "release_sha256": sha(modified)}
    (RELEASE / "commands.json").write_bytes(modified)
    (RELEASE / "original-v1-audit-rejection.log").write_bytes(rejected.stdout + rejected.stderr)
    (RELEASE / "private-raw-v2-audit.json").write_bytes(encode(raw_result))
    (RELEASE / "redaction.json").write_bytes(encode({
        "raw_evidence_kept_local": True, "private_manifest_sha256": sha(manifest_before),
        "method": "keyed HMAC-SHA256 equality commitments; private key not exported",
        "redacted": ["all service Config and HostConfig values", "mount fields except Destination", "unneeded inspect fields and health logs"],
        "modified_captured_files": changed,
        "public_limitation": "Configuration equality commitments can be compared but secret values cannot be reconstructed or independently inspected without private raw evidence/key.",
    }))
    (RELEASE / "manifest.json").write_bytes(encode({"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in RELEASE.iterdir() if p.is_file()}}))
    result = audit(RELEASE)
    if (RAW / "manifest.json").read_bytes() != manifest_before: raise RuntimeError("private raw manifest changed")
    print(json.dumps({"release": str(RELEASE), "audit": result, "redaction": True}, indent=2))


if __name__ == "__main__": main()
