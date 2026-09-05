"""Build an explicitly derived local image; never install it into the sandbox."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CONTEXT = ROOT / "sandbox/patches/ueransim-reconnect-r2"
OFFICIAL = "safetwin5g/ueransim:3.3.0-6bf5a1a9"
BASE_ID = "sha256:13705fc29922cf019e8c7992b5b04b9c6c584d3848d29689f1d3db64334ae725"
DERIVED = "safetwin5g/ueransim:3.3.0-reconnect-r2"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = ROOT / "evidence/engineering" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r2-build")
    output.mkdir(parents=True, exist_ok=False)
    def save(name, data):
        (output / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    sources = {str(p.relative_to(ROOT)).replace("\\", "/"): sha(p) for p in CONTEXT.rglob("*") if p.is_file()}
    sources["tools/build_reconnect_r2.py"] = sha(Path(__file__))
    save("source-hashes.json", sources)
    commands = []
    def cmd(name, argv, accepted=(0,), timeout=40):
        print(name, flush=True)
        row = {"name": name, "argv": argv, "started_at": datetime.now(timezone.utc).isoformat()}
        try:
            result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
            row.update(returncode=result.returncode, stdout=result.stdout, stderr=result.stderr)
        except subprocess.TimeoutExpired as exc:
            row.update(returncode=-999, stdout=(exc.stdout or b"").decode("utf-8", "replace") if isinstance(exc.stdout, bytes) else (exc.stdout or ""), stderr="bounded command timeout")
        row["completed_at"] = datetime.now(timezone.utc).isoformat()
        commands.append(row)
        save(name + ".json", row)
        if row["returncode"] not in accepted:
            raise RuntimeError(f"{name}: exit {row['returncode']}")
        return row["stdout"]
    errors, built, derived_id = [], False, None
    try:
        cmd("git-head", ["git", "rev-parse", "HEAD"])
        cmd("docker-version", ["docker", "version", "--format", "{{json .Server}}"])
        official = json.loads(cmd("official-before", ["docker", "image", "inspect", OFFICIAL]))[0]
        if official["Id"] != BASE_ID:
            raise PermissionError("official local base image drift")
        # Do not overwrite a previous derived candidate or retry over its tag.
        existing = cmd("derived-absence", ["docker", "image", "ls", "--no-trunc", "--format", "{{.ID}}", DERIVED])
        if existing.strip():
            raise PermissionError("derived tag already exists; inspect the earlier build first")
        source_hash = sha(CONTEXT / "nnsf.cpp")
        fixture_hash = sha(CONTEXT / "fixture/test.cpp")
        cmd("docker-build", ["docker", "build", "--progress=plain", "--pull=false", "--network=default",
                             "--build-arg", "CANDIDATE_SHA256=" + source_hash,
                             "--build-arg", "FIXTURE_SHA256=" + fixture_hash,
                             "--tag", DERIVED, str(CONTEXT)], timeout=1800)
        candidate = json.loads(cmd("derived-image", ["docker", "image", "inspect", DERIVED]))[0]
        derived_id = candidate["Id"]
        if (derived_id == BASE_ID or candidate["Config"]["Labels"].get("safetwin5g.derived.source.sha256") != source_hash
                or candidate["Config"]["Labels"].get("safetwin5g.derived.revision") != "reconnect-r2"):
            raise RuntimeError("derived image identity mismatch")
        # No network, capabilities, host volumes or service attachment. This
        # short-lived read-only container only prints retained build evidence.
        for name in ("official-counterexample.log", "selection-fixtures.log", "patch.diff", "LICENSE", "upstream-commit.txt", "compiler.txt", "binary-patch-sha256.txt"):
            data = cmd("capture-" + name, ["docker", "run", "--rm", "--network=none", "--read-only",
                       "--cap-drop=ALL", "--security-opt=no-new-privileges", "--cpus=1", "--memory=128m",
                       derived_id, "cat", "/opt/safetwin-r2/" + name])
            (output / name).write_text(data, encoding="utf-8")
        if "FIXTURE_CASES=16 FAILURES=0" not in (output / "selection-fixtures.log").read_text():
            raise RuntimeError("source regression cases incomplete")
        if "OFFICIAL_COUNTEREXAMPLE:" not in (output / "official-counterexample.log").read_text():
            raise RuntimeError("official counterexample missing")
        original_binaries = cmd("official-binaries", ["docker", "run", "--rm", "--network=none", "--read-only",
                  "--cap-drop=ALL", "--security-opt=no-new-privileges", "--cpus=1", "--memory=128m", BASE_ID,
                  "sha256sum", "/opt/ueransim/bin/nr-gnb", "/opt/ueransim/bin/nr-ue"])
        original = {line.split()[1]: line.split()[0] for line in original_binaries.splitlines()}
        derived = {line.split()[1]: line.split()[0] for line in (output / "binary-patch-sha256.txt").read_text().splitlines()}
        if (original["/opt/ueransim/bin/nr-ue"] != derived["/opt/ueransim/bin/nr-ue"]
                or original["/opt/ueransim/bin/nr-gnb"] == derived["/opt/ueransim/bin/nr-gnb"]):
            raise RuntimeError("only gNB binary must change")
        # The experiment has not changed any running service or Compose file.
        current = json.loads(cmd("official-after", ["docker", "image", "inspect", OFFICIAL]))[0]
        if current["Id"] != BASE_ID:
            raise RuntimeError("official image changed during build")
        built = True
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    save("summary.json", {"build_verified": built, "errors": errors, "official_image_id": BASE_ID,
          "derived_image_id": derived_id, "derived_image_tag": DERIVED, "commands": len(commands),
          "evidence_label": "fixture", "source_regression_is_network_evidence": False,
          "sandbox_image_applied": False, "network_fix_validated": False, "long_campaign_ready": False,
          "TNSM_ready": False, "completed_at": datetime.now(timezone.utc).isoformat()})
    save("manifest.json", {"captured_file_sha256": {p.name: sha(p) for p in output.iterdir() if p.is_file()}})
    print(output, flush=True)
    print(json.dumps({"build_verified": built, "errors": errors}), flush=True)
    return 0 if built else 2


if __name__ == "__main__":
    raise SystemExit(main())
