"""Build frozen instrumentation in a new local image; never install it."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / "evidence/engineering/20260905T102301Z-reconnect-r3-freeze"
BASE_SOURCE = ROOT / "evidence/engineering/20260905T091635Z-reconnect-packet-diagnosis"
BUILD = ROOT / "sandbox/build/reconnect-r3"
CONFIG = json.loads((ROOT / "config/experiments/reconnect-r3-trace.json").read_text())
BASE_TAG = "safetwin5g/ueransim:3.3.0-reconnect-r2"
OFFICIAL_TAG = "safetwin5g/ueransim:3.3.0-6bf5a1a9"
FILES = ("upstream-commit.txt", "base.diff", "source-before.sha256", "source-after.sha256",
         "bin-before.sha256", "bin-after.sha256", "packages-before.txt", "packages-after.txt",
         "source-status.txt", "tracked-source.diff", "LICENSE", "instrumentation.diff", "compiler.txt",
         "cmake.txt", "build-start.txt", "build-end.txt", "compile.log", "compiled-binaries.sha256")
RUN_PREFIX = ["docker", "run", "--rm", "--network=none", "--read-only", "--cap-drop=ALL",
              "--security-opt=no-new-privileges", "--cpus=1", "--memory=128m"]


def sha(data): return hashlib.sha256(data).hexdigest()


def context_files():
    expected = json.loads((FREEZE / "overlay-hashes.json").read_text())
    base = {}
    for path in expected:
        if path.endswith("safetwin_trace_r3.hpp"): continue
        base[path] = sha((BASE_SOURCE / ("upstream-" + path.replace("/", "-"))).read_bytes())
    base["src/gnb/ngap/nnsf.cpp"] = sha((ROOT / "sandbox/patches/ueransim-reconnect-r2/nnsf.cpp").read_bytes())
    base["LICENSE"] = sha((BASE_SOURCE / "upstream-LICENSE").read_bytes())
    checksum = lambda mapping: "".join(f"{value}  {path}\n" for path, value in mapping.items()).encode()
    return {"Dockerfile": (BUILD / "Dockerfile").read_bytes(), "build.sh": (BUILD / "build.sh").read_bytes(),
            "instrumentation.diff": (FREEZE / "instrumentation.diff").read_bytes(),
            "expected-source.sha256": checksum(expected), "base-source.sha256": checksum(base)}


def context_tar(files):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name); member.size = len(data); member.mode = 0o644
            archive.addfile(member, io.BytesIO(data))
    return buffer.getvalue()


def main():
    output = ROOT / "evidence/engineering" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r3-build")
    output.mkdir(parents=True, exist_ok=False)
    def save(name, value):
        (output / name).write_bytes((json.dumps(value, indent=2) + "\n").encode())
    source_paths = [Path(__file__), BUILD / "Dockerfile", BUILD / "build.sh", ROOT / "tools/audit_reconnect_r3_build.py",
                    ROOT / "tests/test_reconnect_r3_build.py", ROOT / "config/experiments/reconnect-r3-trace.json"]
    save("source-hashes.json", {p.relative_to(ROOT).as_posix(): sha(p.read_bytes()) for p in source_paths})
    commands = []
    def cmd(name, argv, data=None, timeout=40, accepted=(0,)):
        print(name, flush=True)
        row = {"name": name, "argv": argv, "timeout_seconds": timeout,
               "started_at": datetime.now(timezone.utc).isoformat(), "stdin_sha256": sha(data) if data is not None else None}
        try:
            result = subprocess.run(argv, input=data, cwd=ROOT, capture_output=True, timeout=timeout)
            stdout, stderr, code = result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired as exc:
            stdout, stderr, code = exc.stdout or b"", (exc.stderr or b"") + b"\nBOUNDED_COMMAND_TIMEOUT", -999
        (output / (name + ".stdout")).write_bytes(stdout)
        (output / (name + ".stderr")).write_bytes(stderr)
        row.update(returncode=code, stdout_sha256=sha(stdout), stderr_sha256=sha(stderr),
                   completed_at=datetime.now(timezone.utc).isoformat())
        commands.append(row); save("commands.json", commands)
        if code not in accepted: raise RuntimeError(f"{name}: exit {code}")
        return stdout
    errors, built, image_id, names = [], False, None, []
    try:
        cmd("repository-head", ["git", "rev-parse", "HEAD"])
        cmd("source-audit", [sys.executable, "tools/audit_reconnect_r3_source.py", "--run", str(FREEZE)])
        cmd("docker-version", ["docker", "version", "--format", "{{json .Server}}"])
        names = cmd("container-list", ["docker", "ps", "-a", "--format", "{{.Names}}"] ).decode().splitlines()
        if not {"safetwin5g-ue", "safetwin5g-gnb"} <= set(names): raise RuntimeError("official services missing")
        cmd("services-before", ["docker", "inspect", *names])
        for label, tag, expected in (("official", OFFICIAL_TAG, CONFIG["official_image_id"]), ("base", BASE_TAG, CONFIG["base_image_id"])):
            observed = json.loads(cmd(label + "-before", ["docker", "image", "inspect", tag]))[0]
            if observed["Id"] != expected: raise RuntimeError(label + " image drift")
        if cmd("target-absence", ["docker", "image", "ls", "--no-trunc", "--format", "{{.ID}}", CONFIG["future_image_tag"]]).strip():
            raise RuntimeError("target exists: inspect existing build, never overwrite")
        data = context_tar(context_files()); (output / "context.tar").write_bytes(data)
        cmd("docker-build", ["docker", "build", "--progress=plain", "--pull=false", "--network=none", "--tag", CONFIG["future_image_tag"], "-"], data, 720)
        candidate = json.loads(cmd("derived-image", ["docker", "image", "inspect", CONFIG["future_image_tag"]]))[0]
        image_id = candidate["Id"]
        if image_id in (CONFIG["base_image_id"], CONFIG["official_image_id"]): raise RuntimeError("derived identity missing")
        for name in FILES:
            data = cmd("capture-" + name, RUN_PREFIX + [image_id, "cat", "/opt/safetwin-r3/" + name])
            (output / name).write_bytes(data)
        cmd("derived-help-ue", RUN_PREFIX + [image_id, "/opt/ueransim/bin/nr-ue", "--help"], accepted=(0, 1))
        cmd("derived-help-gnb", RUN_PREFIX + [image_id, "/opt/ueransim/bin/nr-gnb", "--help"], accepted=(0, 1))
        built = True
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        # Read-only preservation checks also run after a failed build.
        for label, tag in (("official", OFFICIAL_TAG), ("base", BASE_TAG)):
            try: cmd(label + "-after", ["docker", "image", "inspect", tag])
            except Exception as exc: errors.append(str(exc))
        if names:
            try:
                cmd("container-list-after", ["docker", "ps", "-a", "--format", "{{.Names}}"])
                cmd("services-after", ["docker", "inspect", *names])
            except Exception as exc: errors.append(str(exc))
    save("summary.json", {"build_completed": built, "independent_build_audit_required": True, "errors": errors,
          "derived_image_id": image_id, "derived_image_tag": CONFIG["future_image_tag"], "commands": len(commands),
          "evidence_label": "fixture", "sandbox_image_applied": False, "network_trials": 0,
          "network_fix_validated": False, "TNSM_ready": False})
    save("manifest.json", {"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}})
    print(output, flush=True)
    print(json.dumps({"build_completed": built, "errors": errors}), flush=True)
    return 0 if built and not errors else 2


if __name__ == "__main__": raise SystemExit(main())
