"""Audit redaction structure; optionally verify it against private raw inputs."""
import argparse
import hashlib
import hmac
import json
from pathlib import Path
import re

from tools.audit_reconnect_r3_build_v2 import audit as build_audit

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "evidence/engineering/20260905T111542Z-reconnect-r3-build-release"
RAW = ROOT / "evidence/engineering/20260905T111542Z-reconnect-r3-build"


def require(value, message):
    if not value: raise ValueError(message)


def sha(data): return hashlib.sha256(data).hexdigest()


def audit(run=RELEASE, private=False):
    run = Path(run)
    build = build_audit(run)
    redaction = json.loads((run / "redaction.json").read_bytes())
    require(redaction["raw_evidence_kept_local"] is True, "private evidence disclosure")
    modified = redaction["modified_captured_files"]
    require(set(modified) == {"services-before.stdout", "services-after.stdout", "commands.json"}, "redaction file scope")
    for name, item in modified.items(): require(sha((run / name).read_bytes()) == item["release_sha256"], "redaction digest")
    def check_commitment(value):
        require(set(value) == {"redacted", "equality_hmac_sha256"} and value["redacted"] is True and
                re.fullmatch(r"[0-9a-f]{64}", value["equality_hmac_sha256"]), "invalid redaction commitment")
    for name in ("services-before.stdout", "services-after.stdout"):
        for row in json.loads((run / name).read_bytes()):
            require(set(row) == {"Name", "Id", "Image", "RestartCount", "Config", "HostConfig", "Mounts", "State"}, "unredacted inspect fields")
            require(set(row["State"]) == {"StartedAt", "FinishedAt", "Running", "Paused", "Restarting"}, "unredacted state logs")
            check_commitment(row["Config"]); check_commitment(row["HostConfig"])
            for mount in row["Mounts"]:
                require(set(mount) == {"Destination", "redacted", "equality_hmac_sha256"}, "unredacted mount fields")
                check_commitment({k: v for k, v in mount.items() if k != "Destination"})
    if private:
        build_audit(RAW)
        key = (ROOT / "evidence/private/reconnect-r3-build-redaction-key.bin").read_bytes()
        require(len(key) == 32, "private key length")
        require(sha((RAW / "manifest.json").read_bytes()) == redaction["private_manifest_sha256"], "private manifest linkage")
        # Independent transform verification. Never import the publication helper.
        digest = lambda value: hmac.new(key, json.dumps(value, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256).hexdigest()
        for name in ("services-before.stdout", "services-after.stdout"):
            original, clean = [json.loads((directory / name).read_bytes()) for directory in (RAW, run)]
            require(len(original) == len(clean), "redacted service count")
            for left, right in zip(original, clean):
                for field in ("Name", "Id", "Image", "RestartCount"): require(left[field] == right[field], "identity redacted incorrectly")
                for field in right["State"]: require(left["State"][field] == right["State"][field], "state redacted incorrectly")
                for field in ("Config", "HostConfig"): require(digest(left[field]) == right[field]["equality_hmac_sha256"], "configuration commitment")
                require(len(left["Mounts"]) == len(right["Mounts"]), "redacted mount count")
                for old, new in zip(left["Mounts"], right["Mounts"]):
                    require(old["Destination"] == new["Destination"] and digest(old) == new["equality_hmac_sha256"], "mount commitment")
        for path in RAW.iterdir():
            if path.name == "manifest.json": continue
            if path.name in modified:
                require(sha(path.read_bytes()) == modified[path.name]["original_sha256"], "original digest")
            else: require(path.read_bytes() == (run / path.name).read_bytes(), "unrelated evidence redacted")
        old_commands = json.loads((RAW / "commands.json").read_bytes())
        new_commands = json.loads((run / "commands.json").read_bytes())
        for row in old_commands:
            if row["name"] in ("services-before", "services-after"):
                row["stdout_sha256"] = modified[row["name"] + ".stdout"]["release_sha256"]
        require(old_commands == new_commands, "command data changed beyond redaction linkage")
    return {"release_audit_passed": True, "private_transform_verified": private, "raw_configurations_published": False,
            "public_configuration_claim": "equality commitments only; private raw values not independently exposed",
            "build": build}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--private", action="store_true")
    print(json.dumps(audit(private=parser.parse_args().private), indent=2))
