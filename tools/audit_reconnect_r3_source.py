"""Independent overlay removal, actual Git-patch replay and fixture-log audit."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "evidence/engineering/20260905T091635Z-reconnect-packet-diagnosis"
PATHS = {"src/ue/nas/sm/sap.cpp": 4, "src/ue/rls/ctl_task.cpp": 2, "src/gnb/gtp/task.cpp": 4}
HEADER_PATH = "src/utils/safetwin_trace_r3.hpp"


def require(value, message):
    if not value: raise ValueError(message)


def sha(data): return hashlib.sha256(data).hexdigest()


def remove_blocks(text):
    # Deliberately line-based; do not call the overlay generator/regex stripper.
    kept, blocks, current, content = [], {}, None, []
    for line in text.splitlines(keepends=True):
        if line.startswith("// SAFETWIN_R3_BEGIN "):
            require(current is None, "nested trace block")
            current = line.strip().split()[-1]; content = []
            require(current not in blocks, "duplicate trace block")
        elif line.startswith("// SAFETWIN_R3_END "):
            require(current is not None and line.strip().split()[-1] == current, "trace block end")
            blocks[current] = "".join(content); current = None
        elif current is not None: content.append(line)
        else: kept.append(line)
    require(current is None, "unterminated trace block")
    return "".join(kept), blocks


def audit(run):
    run = Path(run).resolve()
    read = lambda name: json.loads((run / name).read_text(encoding="utf-8"))
    manifest = read("manifest.json")["captured_file_sha256"]
    require(set(manifest) == {p.name for p in run.iterdir() if p.is_file() and p.name != "manifest.json"}, "inventory")
    for name, digest in manifest.items():
        require(Path(name).name == name and sha((run / name).read_bytes()) == digest, "artifact hash")
    for name, digest in read("source-hashes.json").items():
        path = (ROOT / name).resolve()
        require(path.is_relative_to(ROOT) and sha(path.read_bytes()) == digest, "frozen source drift: " + name)
    overlay = read("overlay-hashes.json")
    require(set(overlay) == set(PATHS) | {HEADER_PATH}, "overlay file scope")
    stages = []
    for path, count in PATHS.items():
        data = (run / ("overlay-" + path.replace("/", "-"))).read_bytes()
        require(sha(data) == overlay[path], "overlay digest")
        original, blocks = remove_blocks(data.decode())
        require(original.encode() == (BASE / ("upstream-" + path.replace("/", "-"))).read_bytes(), "instrumentation removal changes base")
        require(len(blocks) == count and blocks.pop("include") == "#include <utils/safetwin_trace_r3.hpp>\n", "include/block scope")
        for addition in blocks.values():
            require(addition.count("\n") == 1 and addition.strip().startswith("safetwin_r3::emit(m_logger.get(), ") and addition.strip().endswith(");"), "only logging statement allowed")
            require(not any(token in addition for token in ("; ", "&&", "||", "++", "--", "return", "throw")), "logging expression side effect")
            stage = re.findall(r'"([a-z_]+)"', addition)
            require(len(stage) == 1, "trace stage literal")
            stages += stage
    require(set(stages) == {"nas_in", "nas_idle", "nas_forward", "ue_rls", "gnb_in", "gnb_missing", "gnb_resource"} and len(stages) == 7, "seven trace sites")
    header = (run / "overlay-src-utils-safetwin_trace_r3.hpp").read_bytes()
    require(sha(header) == overlay[HEADER_PATH] and header == (ROOT / "sandbox/patches/ueransim-reconnect-r3-trace/safetwin_trace_r3.hpp").read_bytes(), "reviewed trace header")
    patch = (run / "instrumentation.diff").read_text(encoding="utf-8")
    require(re.findall(r"(?m)^\+\+\+ b/(.+)$", patch) == list(overlay), "patch path scope/order")
    with tempfile.TemporaryDirectory(prefix="safetwin-r3-overlay-audit-") as temporary:
        directory = Path(temporary)
        for path in PATHS:
            target = directory / path; target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((BASE / ("upstream-" + path.replace("/", "-"))).read_bytes())
        replay = subprocess.run(["git", "-c", "core.autocrlf=false", "apply", str(run / "instrumentation.diff")], cwd=directory, capture_output=True, timeout=15)
        require(replay.returncode == 0, "actual Git patch replay: " + replay.stderr.decode("utf-8", "replace"))
        require({p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()} == set(overlay), "replayed file scope")
        for path, digest in overlay.items(): require(sha((directory / path).read_bytes()) == digest, "replayed content digest")
    commands = read("commands.json")
    expected_names = ["repository-head", "source-provenance", "official-before", "base-image", "new-tag-absence", "ping-help",
                      "parser-fixture", "baseline-nas-fixture", "instrumented-nas-fixture", "full-tests", "statistical-lock", "official-after"]
    require([r["name"] for r in commands] == expected_names, "command inventory/order")
    records = {r["name"]: r for r in commands}
    previous = None
    for row in commands:
        start, end = datetime.fromisoformat(row["started_at"]), datetime.fromisoformat(row["completed_at"])
        require(start <= end and (previous is None or previous <= start), "chronology")
        previous = end
        require(row["returncode"] in ((0,2) if row["name"] == "ping-help" else (0,)), "command failure")
    config = json.loads((ROOT / "config/experiments/reconnect-r3-trace.json").read_text())
    require(not records["new-tag-absence"]["stdout"].strip() and "-e <identifier>" in records["ping-help"]["stderr"] + records["ping-help"]["stdout"], "prebuild absence/CLI capability")
    require(json.loads(records["base-image"]["stdout"])[0]["Id"] == config["base_image_id"], "R2 base identity")
    before, after = [json.loads(records["official-" + when]["stdout"]) for when in ("before", "after")]
    require(len(before) == len(after) == 2, "running component count")
    for left, right in zip(before, after):
        require(left["Id"] == right["Id"] and left["Image"] == right["Image"] == config["official_image_id"]
                and left["State"]["StartedAt"] == right["State"]["StartedAt"] and left["RestartCount"] == right["RestartCount"], "official service changed")
    for name in ("parser-fixture", "baseline-nas-fixture", "instrumented-nas-fixture"):
        row = records[name]; source = (run / (name + ".cpp")).read_bytes()
        require(sha(source) == row["stdin_sha256"], "compiler input linkage")
        expected_argv = ["docker", "run", "--rm", "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                        "--cpus=1", "--memory=256m", "--tmpfs", "/tmp:rw,exec,nosuid,nodev,size=32m", "-i", config["base_image_id"],
                        "timeout", "25", "sh", "-lc", "g++ -std=c++17 -Wall -Wextra -pedantic -x c++ - -o /tmp/r3-fixture && /tmp/r3-fixture"]
        require(row["argv"] == expected_argv, "isolated compiler scope")
        require(header in source, "executed header missing")
    require("PARSER_CASES=65 FAILURES=0" in records["parser-fixture"]["stdout"], "parser cases")
    # Check the nominal metadata/fingerprint with separately constructed bytes.
    payload = bytearray(84); payload[0] = 0x45; payload[3] = 84; payload[4:6] = bytes.fromhex("1234")
    payload[8:10] = bytes([64,1]); payload[12:20] = bytes([10,45,0,2,10,45,0,1]); payload[20] = 8
    payload[24:28] = bytes.fromhex("27110001")
    value = 0xcbf29ce484222325
    for octet in payload: value = ((value ^ octet) * 0x100000001b3) & 0xffffffffffffffff
    require(f"ipid=4660 id=10001 seq=1 bytes=84 fp={value}" in records["parser-fixture"]["stdout"], "independent packet identity")
    reference = records["baseline-nas-fixture"]["stdout"].splitlines()
    observed = records["instrumented-nas-fixture"]["stdout"].splitlines()
    require(reference == [line for line in observed if not line.startswith("ST3 ")] and "FIXTURE_CASES=61 FAILURES=0" in reference, "fixture behavior differs")
    require(len([line for line in observed if line.startswith("ST3 ")]) == 4, "identified NAS events")
    for name, source_name in (("baseline-nas-fixture", "upstream-src-ue-nas-sm-sap.cpp"), ("instrumented-nas-fixture", "overlay-src-ue-nas-sm-sap.cpp")):
        source = ((BASE if name.startswith("baseline") else run) / source_name).read_text(encoding="utf-8")
        exact = "void NasSm::handleUplinkDataRequest(" + source.split("void NasSm::handleUplinkDataRequest(",1)[1].split("void NasSm::handleDownlinkDataRequest(",1)[0].rstrip()
        require(exact in (run / (name + ".cpp")).read_text(encoding="utf-8"), "exact method not executed")
    summary = read("summary.json")
    require(summary["capture_completed"] and not summary["errors"] and summary["evidence_label"] == "fixture" and summary["network_trials"] == 0
            and all(summary[k] is False for k in ("new_image_built", "sandbox_image_applied", "network_fix_validated", "TNSM_ready")), "claim promotion")
    return {"audit_passed": True, "source_files_instrumented": 3, "new_header": 1, "insertion_blocks": 10, "git_patch_replay_passed": True,
            "parser_cases": 65, "nas_cases_per_mode": 61, "identified_fixture_events": 4, "evidence_label": "fixture",
            "new_image_built": False, "network_trials": 0, "network_fix_validated": False, "TNSM_ready": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(); parser.add_argument("--run", required=True)
    print(json.dumps(audit(parser.parse_args().run), indent=2))
