"""Independent raw build, source-delta, isolation and unchanged-service audit."""
import argparse
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "evidence/engineering/20260905T102301Z-reconnect-r3-freeze"
PACKET = ROOT / "evidence/engineering/20260905T091635Z-reconnect-packet-diagnosis"
BASE = "sha256:2a5c01c503927c44a6b45f8b074491ac64a42fc3a444ea2af0a8cbe5df8e537e"
OFFICIAL = "sha256:13705fc29922cf019e8c7992b5b04b9c6c584d3848d29689f1d3db64334ae725"
TAG = "safetwin5g/ueransim:3.3.0-reconnect-r3-trace"
ARTIFACTS = ["upstream-commit.txt", "base.diff", "source-before.sha256", "source-after.sha256",
             "bin-before.sha256", "bin-after.sha256", "packages-before.txt", "packages-after.txt",
             "source-status.txt", "tracked-source.diff", "LICENSE", "instrumentation.diff", "compiler.txt",
             "cmake.txt", "build-start.txt", "build-end.txt", "compile.log", "compiled-binaries.sha256"]


def require(condition, message):
    if not condition: raise ValueError(message)


def sha(data): return hashlib.sha256(data).hexdigest()


def sums(data):
    result = {}
    for line in data.decode().splitlines():
        require(re.match(r"^[0-9a-f]{64}  .+$", line), "malformed checksum row")
        digest, path = line.split("  ", 1)
        require(path not in result, "duplicate checksum path")
        result[path] = digest
    return result


def source_delta(before, after, overlay):
    require(set(after) == set(before) | {"src/utils/safetwin_trace_r3.hpp"}, "source inventory delta")
    changed = {path for path in after if before.get(path) != after[path]}
    require(changed == set(overlay) and all(after[path] == value for path, value in overlay.items()), "unexpected source delta")


def preserve_services(before, after):
    left, right = [{row["Name"]: row for row in collection} for collection in (before, after)]
    require(len(left) == len(before) and set(left) == set(right), "container inventory")
    for name, first in left.items():
        last = right[name]
        for key in ("Id", "Image", "RestartCount", "Config", "HostConfig", "Mounts"):
            require(first[key] == last[key], "container changed: " + name + ":" + key)
        for key in ("StartedAt", "FinishedAt", "Running", "Paused", "Restarting"):
            require(first["State"][key] == last["State"][key], "container state changed: " + name)
    for name in ("/safetwin5g-ue", "/safetwin5g-gnb"):
        require(left[name]["Image"] == OFFICIAL and left[name]["State"]["Running"], "official service not running")


def audit(run):
    run = Path(run).resolve()
    read = lambda name: json.loads((run / name).read_bytes())
    blob = lambda name: (run / name).read_bytes()
    manifest = read("manifest.json")["captured_file_sha256"]
    require(set(manifest) == {p.name for p in run.iterdir() if p.is_file() and p.name != "manifest.json"}, "artifact inventory")
    for name, value in manifest.items():
        require(Path(name).name == name and sha(blob(name)) == value, "artifact digest: " + name)
    source_hashes = read("source-hashes.json")
    require(set(source_hashes) == {"tools/build_reconnect_r3.py", "tools/audit_reconnect_r3_build.py", "tests/test_reconnect_r3_build.py",
                                  "sandbox/build/reconnect-r3/Dockerfile", "sandbox/build/reconnect-r3/build.sh", "config/experiments/reconnect-r3-trace.json"}, "build source inventory")
    for name, digest in source_hashes.items(): require(sha((ROOT / name).read_bytes()) == digest, "build source drift: " + name)
    summary = read("summary.json")
    require(summary["build_completed"] is True and not summary["errors"] and summary["independent_build_audit_required"] is True, "incomplete build")
    require(summary["evidence_label"] == "fixture" and summary["network_trials"] == 0, "evidence tier")
    for key in ("sandbox_image_applied", "network_fix_validated", "TNSM_ready"): require(summary[key] is False, "claim promotion: " + key)
    rows = read("commands.json")
    order = ["repository-head", "source-audit", "docker-version", "container-list", "services-before", "official-before", "base-before",
             "target-absence", "docker-build", "derived-image"] + ["capture-" + name for name in ARTIFACTS] + [
             "derived-help-ue", "derived-help-gnb", "official-after", "base-after", "container-list-after", "services-after"]
    require([r["name"] for r in rows] == order and len(rows) == summary["commands"], "command inventory/order")
    records = {r["name"]: r for r in rows}
    stdout = lambda name: blob(name + ".stdout")
    names = stdout("container-list").decode().splitlines()
    require(set(names) == set(stdout("container-list-after").decode().splitlines()) and len(names) == len(set(names)), "service list drift")
    derived = json.loads(stdout("derived-image"))[0]
    image = derived["Id"]
    require(re.fullmatch(r"sha256:[0-9a-f]{64}", image) and image == summary["derived_image_id"] and image not in (BASE, OFFICIAL), "image identity")
    require(summary["derived_image_tag"] == TAG and TAG in derived["RepoTags"], "image tag")
    expected = {
        "repository-head": ["git", "rev-parse", "HEAD"],
        "source-audit": [records["source-audit"]["argv"][0], "tools/audit_reconnect_r3_source.py", "--run", str(FREEZE)],
        "docker-version": ["docker", "version", "--format", "{{json .Server}}"],
        "container-list": ["docker", "ps", "-a", "--format", "{{.Names}}"],
        "container-list-after": ["docker", "ps", "-a", "--format", "{{.Names}}"],
        "services-before": ["docker", "inspect", *names], "services-after": ["docker", "inspect", *names],
        "target-absence": ["docker", "image", "ls", "--no-trunc", "--format", "{{.ID}}", TAG],
        "docker-build": ["docker", "build", "--progress=plain", "--pull=false", "--network=none", "--tag", TAG, "-"],
        "derived-image": ["docker", "image", "inspect", TAG],
    }
    for label, tag in (("official", "safetwin5g/ueransim:3.3.0-6bf5a1a9"), ("base", "safetwin5g/ueransim:3.3.0-reconnect-r2")):
        for when in ("before", "after"): expected[label + "-" + when] = ["docker", "image", "inspect", tag]
    isolated = ["docker", "run", "--rm", "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--cpus=1", "--memory=128m", image]
    for name in ARTIFACTS:
        expected["capture-" + name] = isolated + ["cat", "/opt/safetwin-r3/" + name]
        require(stdout("capture-" + name) == blob(name), "image artifact linkage: " + name)
    for component in ("ue", "gnb"):
        name = "derived-help-" + component
        expected[name] = isolated + ["/opt/ueransim/bin/nr-" + component, "--help"]
        require(b"UERANSIM v3.3.0" in stdout(name) + blob(name + ".stderr") and b"Usage:" in stdout(name) + blob(name + ".stderr"), "binary startup help")
    previous = None
    for row in rows:
        name = row["name"]
        require(row["argv"] == expected[name], "command scope: " + name)
        require(row["returncode"] in ((0, 1) if name.startswith("derived-help-") else (0,)), "command failed")
        require(row["timeout_seconds"] == (720 if name == "docker-build" else 40), "command timeout")
        require(row["stdin_sha256"] == (sha(blob("context.tar")) if name == "docker-build" else None), "build input linkage")
        require(row["stdout_sha256"] == sha(stdout(name)) and row["stderr_sha256"] == sha(blob(name + ".stderr")), "command output linkage")
        start, end = [datetime.fromisoformat(row[key]) for key in ("started_at", "completed_at")]
        require(start <= end and (previous is None or previous <= start), "command chronology"); previous = end
    require(not stdout("target-absence").strip() and json.loads(stdout("source-audit"))["audit_passed"] is True, "source gate or target overwrite")
    images = {}
    for label, identity in (("official", OFFICIAL), ("base", BASE)):
        images[label] = json.loads(stdout(label + "-before"))[0]
        require(images[label]["Id"] == json.loads(stdout(label + "-after"))[0]["Id"] == identity, "base image drift")
    layers = images["base"]["RootFS"]["Layers"]
    require(len(derived["RootFS"]["Layers"]) > len(layers) and derived["RootFS"]["Layers"][:len(layers)] == layers, "immutable R2 layer ancestry")
    for key in ("Cmd", "Entrypoint", "Env", "ExposedPorts", "Volumes", "User", "WorkingDir", "Healthcheck"):
        require(derived["Config"].get(key) == images["base"]["Config"].get(key), "runtime config changed: " + key)
    labels = derived["Config"]["Labels"]
    require(labels["safetwin5g.derived.revision"] == "reconnect-r3-trace" and labels["safetwin5g.derived.base.image"] == BASE
            and labels["safetwin5g.derived.source.sha256"] == sha((FREEZE / "instrumentation.diff").read_bytes())
            and labels["safetwin5g.derived.claim"] == "instrumentation-only-not-network-validated", "derived labels")
    preserve_services(json.loads(stdout("services-before")), json.loads(stdout("services-after")))
    with tarfile.open(fileobj=io.BytesIO(blob("context.tar"))) as archive:
        members = archive.getmembers()
        require(len(members) == 5 and all(m.isfile() for m in members), "context type/count")
        context = {m.name: archive.extractfile(m).read() for m in members}
    require(set(context) == {"Dockerfile", "build.sh", "instrumentation.diff", "expected-source.sha256", "base-source.sha256"}, "context scope")
    for name in ("Dockerfile", "build.sh"): require(context[name] == (ROOT / "sandbox/build/reconnect-r3" / name).read_bytes(), "build contract linkage")
    require(context["instrumentation.diff"] == blob("instrumentation.diff") == (FREEZE / "instrumentation.diff").read_bytes(), "frozen overlay changed")
    overlay = json.loads((FREEZE / "overlay-hashes.json").read_bytes())
    require(sums(context["expected-source.sha256"]) == overlay, "overlay checksum contract")
    before, after = sums(blob("source-before.sha256")), sums(blob("source-after.sha256"))
    require(len(before) == 4267, "upstream tracked source inventory")
    source_delta(before, after, overlay)
    for path in overlay:
        if path.endswith("safetwin_trace_r3.hpp"): continue
        require(before[path] == sha((PACKET / ("upstream-" + path.replace("/", "-"))).read_bytes()), "retained base source mismatch")
    expected_base = {p: before[p] for p in overlay if p in before}
    expected_base.update({p: before[p] for p in ("LICENSE", "src/gnb/ngap/nnsf.cpp")})
    require(sums(context["base-source.sha256"]) == expected_base, "base checksum contract")
    require(blob("LICENSE") == (PACKET / "upstream-LICENSE").read_bytes() and before["LICENSE"] == sha(blob("LICENSE")), "licence retention")
    require(sha(blob("base.diff")) == "4d3df81523ae2b9c6753d96e036cab5126a9b2a988e107ce05f365a92e62522c", "R2 patch preservation")
    require(before["src/gnb/ngap/nnsf.cpp"] == sha((ROOT / "sandbox/patches/ueransim-reconnect-r2/nnsf.cpp").read_bytes()), "R2 selection source preservation")
    require(blob("upstream-commit.txt").strip() == b"6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156", "upstream commit")
    require(set(blob("source-status.txt").decode().splitlines()) == {" M " + p for p in overlay if p in before} |
            {" M src/gnb/ngap/nnsf.cpp", "?? src/utils/safetwin_trace_r3.hpp"}, "source status")
    bins_before, bins_after = sums(blob("bin-before.sha256")), sums(blob("bin-after.sha256"))
    changed_bins = {p for p in bins_after if bins_before.get(p) != bins_after[p]}
    require(set(bins_before) == set(bins_after) and changed_bins == {"/opt/ueransim/bin/nr-ue", "/opt/ueransim/bin/nr-gnb"}, "binary delta")
    lock = json.loads((ROOT / "config/experiments/reconnect-r2-images.json").read_bytes())
    require(bins_before["/opt/ueransim/bin/nr-ue"] == lock["unchanged_ue_sha256"] and bins_before["/opt/ueransim/bin/nr-gnb"] == lock["derived_gnb_sha256"], "R2 binary linkage")
    compiled = sums(blob("compiled-binaries.sha256"))
    require(compiled == {"cmake-build-release/nr-" + name: bins_after["/opt/ueransim/bin/nr-" + name] for name in ("ue", "gnb")}, "compiled/runtime binary linkage")
    require(blob("packages-before.txt") == blob("packages-after.txt"), "dependency changes")
    log = blob("compile.log")
    for name in (b"nas/sm/sap.cpp.o", b"rls/ctl_task.cpp.o", b"gtp/task.cpp.o", b"Built target nr-ue", b"Built target nr-gnb"):
        require(name in log, "missing real-source build: " + name.decode())
    require(b"REAL_HEADER_BUILD_COMPLETED" in stdout("docker-build") + blob("docker-build.stderr"), "build terminal marker")
    require(datetime.fromisoformat(blob("build-start.txt").decode().strip()) <= datetime.fromisoformat(blob("build-end.txt").decode().strip()), "compiler chronology")
    return {"audit_passed": True, "build_verified": True, "derived_image_id": image, "upstream_tracked_files": len(before),
            "modified_source_files": 3, "new_source_headers": 1, "changed_binaries": sorted(changed_bins),
            "commands": len(rows), "preserved_containers": len(names), "evidence_label": "fixture", "sandbox_image_applied": False,
            "network_trials": 0, "network_fix_validated": False, "TNSM_ready": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--run", required=True)
    print(json.dumps(audit(parser.parse_args().run), indent=2))
