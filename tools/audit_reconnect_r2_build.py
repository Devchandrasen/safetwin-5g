"""Audit a derived build without mistaking compilation for network recovery."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE_ID = "sha256:13705fc29922cf019e8c7992b5b04b9c6c584d3848d29689f1d3db64334ae725"
UPSTREAM = "6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156"
CANDIDATE = ROOT / "sandbox/patches/ueransim-reconnect-r2/nnsf.cpp"
ORIGINAL = ROOT / "evidence/engineering/20260905T052348Z-recovery-pilot-r1-diagnosis/upstream-src-gnb-ngap-nnsf.cpp"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit(run):
    run = Path(run)
    read = lambda name: json.loads((run / name).read_text())
    manifest = read("manifest.json")["captured_file_sha256"]
    require(set(manifest) == {p.name for p in run.iterdir() if p.is_file() and p.name != "manifest.json"}, "manifest inventory")
    for name, value in manifest.items():
        require(Path(name).name == name and hashlib.sha256((run / name).read_bytes()).hexdigest() == value, "file hash: " + name)
    sources = read("source-hashes.json")
    for name, value in sources.items():
        source = (ROOT / name).resolve()
        require(source.is_relative_to(ROOT) and hashlib.sha256(source.read_bytes()).hexdigest() == value, "source hash: " + name)
    summary = read("summary.json")
    require(summary["build_verified"] and not summary["errors"], "failed build")
    for key in ("sandbox_image_applied", "network_fix_validated", "long_campaign_ready", "TNSM_ready", "source_regression_is_network_evidence"):
        require(summary[key] is False, "claim boundary: " + key)
    require(summary["evidence_label"] == "fixture", "source/build evidence tier")
    commands = [read(name) for name in manifest if name.endswith(".json") and "argv" in read(name)]
    require(len(commands) == summary["commands"] and all(c["returncode"] == 0 for c in commands), "command success/inventory")
    for row in commands:
        if row["argv"][:2] == ["docker", "run"]:
            require(all(flag in row["argv"] for flag in ("--rm", "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges")), "unisolated evidence container")
            require(not any(arg.startswith(("--volume", "--mount", "--privileged", "--publish")) for arg in row["argv"]), "evidence container attachment")
        require(row["argv"][:2] not in (["docker", "exec"], ["docker", "restart"], ["docker", "compose"]), "service mutation in build")
    before = json.loads(read("official-before.json")["stdout"])[0]
    after = json.loads(read("official-after.json")["stdout"])[0]
    derived = json.loads(read("derived-image.json")["stdout"])[0]
    require(before["Id"] == after["Id"] == summary["official_image_id"] == BASE_ID, "official image preservation")
    require(not read("derived-absence.json")["stdout"].strip(), "overwritten candidate tag")
    require(derived["Id"] == summary["derived_image_id"] != BASE_ID, "derived image identity")
    labels = derived["Config"]["Labels"]
    require(labels["safetwin5g.derived.revision"] == "reconnect-r2" and labels["safetwin5g.upstream.commit"] == UPSTREAM, "derived source labels")
    require(labels["safetwin5g.derived.source.sha256"] == hashlib.sha256(CANDIDATE.read_bytes()).hexdigest() and labels["safetwin5g.derived.base.image"] == BASE_ID, "derived source/base hash")
    require((run / "upstream-commit.txt").read_text().strip() == UPSTREAM, "upstream source commit")
    cases = (run / "selection-fixtures.log").read_text().splitlines()
    require(len(cases) == 17 and len(set(cases[:-1])) == 15 and all(line.startswith("PASS ") for line in cases[:-1])
            and cases[-1] == "FIXTURE_CASES=16 FAILURES=0", "source fixture cases")
    require("OFFICIAL_COUNTEREXAMPLE: explicit SST 1 selects; unsupported SST 2 rejects; absent SST -1 rejects despite one connected compatible AMF" in (run / "official-counterexample.log").read_text(), "official function counterexample")
    patch = (run / "patch.diff").read_text()
    require([line for line in patch.splitlines() if line.startswith("diff --git ")] ==
            ["diff --git a/src/gnb/ngap/nnsf.cpp b/src/gnb/ngap/nnsf.cpp"], "single upstream source change")
    # Replay the actual Git patch in a throwaway fixture tree, never the repo.
    with tempfile.TemporaryDirectory(prefix="safetwin-r2-patch-audit-") as temporary:
        target = Path(temporary)
        source = target / "src/gnb/ngap/nnsf.cpp"
        source.parent.mkdir(parents=True)
        source.write_bytes(ORIGINAL.read_bytes())
        patch_file = target / "candidate.patch"
        patch_file.write_text(patch, encoding="utf-8", newline="\n")
        result = subprocess.run(["git", "apply", str(patch_file)], cwd=target, capture_output=True, text=True, timeout=20)
        require(result.returncode == 0, "patch replay: " + result.stderr)
        require(source.read_text() == CANDIDATE.read_text(), "patch does not produce candidate")
    binary = {line.split()[1]: line.split()[0] for line in (run / "binary-patch-sha256.txt").read_text().splitlines()}
    original_binary = {line.split()[1]: line.split()[0] for line in read("official-binaries.json")["stdout"].splitlines()}
    require(binary["/opt/ueransim/bin/nr-ue"] == original_binary["/opt/ueransim/bin/nr-ue"] and
            binary["/opt/ueransim/bin/nr-gnb"] != original_binary["/opt/ueransim/bin/nr-gnb"], "only gNB binary replaced")
    require(binary["/opt/safetwin-r2/patch.diff"] == hashlib.sha256(patch.encode()).hexdigest(), "applied patch hash")
    return {"audit_passed": True, "build_verified": True, "official_counterexample_verified": True,
            "source_fixture_cases": 16, "changed_upstream_files": 1, "derived_image_id": derived["Id"],
            "patch_sha256": binary["/opt/safetwin-r2/patch.diff"], "evidence_label": "fixture",
            "network_fix_validated": False, "sandbox_image_applied": False, "TNSM_ready": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", type=Path, required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(audit(args.run), indent=2))
    except (ValueError, KeyError, OSError) as exc:
        print(json.dumps({"audit_passed": False, "error": str(exc)}))
        raise SystemExit(2)
