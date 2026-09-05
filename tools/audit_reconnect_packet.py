"""Audit source/fixture provenance separately from the failed R2 network gate."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path

try:
    from tools.audit_reconnect_r2 import audit as audit_r2
except ModuleNotFoundError:
    from audit_reconnect_r2 import audit as audit_r2

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATHS = {"src/ue/app/task.cpp", "src/ue/nas/task.cpp", "src/ue/nas/sm/sap.cpp",
    "src/ue/nas/sm/resource.cpp", "src/ue/nas/sm/sm.hpp", "src/ue/nas/mm/proc.cpp",
    "src/ue/nas/mm/service.cpp", "src/ue/rls/task.cpp", "src/ue/rls/ctl_task.cpp",
    "src/gnb/gtp/task.cpp", "src/gnb/ngap/context.cpp", "LICENSE"}


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def audit(run):
    run = Path(run)
    read = lambda name: json.loads((run / name).read_text(encoding="utf-8"))
    manifest = read("manifest.json")["captured_file_sha256"]
    require(set(manifest) == {p.name for p in run.iterdir() if p.is_file() and p.name != "manifest.json"}, "inventory")
    for name, value in manifest.items():
        require(Path(name).name == name and sha((run / name).read_bytes()) == value, "file hash: " + name)
    expected_local = {"tools/diagnose_reconnect_packet.py", "tools/packet_diagnosis/fixture.cpp", "config/experiments/reconnect-r2-images.json"}
    source_hashes = read("collector-sources.json")
    require(set(source_hashes) == expected_local, "collector source inventory")
    for name, value in source_hashes.items():
        require(sha((ROOT / name).read_bytes()) == value, "collector source drift: " + name)
    locked = json.loads((ROOT / "config/experiments/reconnect-r2-images.json").read_text())
    prior = ROOT / "evidence/engineering/20260905T082014Z-reconnect-r2"
    require(read("r2-manifest.json") == {"path": prior.relative_to(ROOT).as_posix(), "sha256": sha((prior / "manifest.json").read_bytes())}, "R2 linkage")
    network = audit_r2(prior)
    require(network["audit_passed"] and not network["network_fix_validated"] and network["completed_trials"] == 6, "R2 negative gate")
    records = read("commands.json")
    names = [r["name"] for r in records]
    expected = (["repository-head", "gnb-before", "ue-before", "derived-image", "retained-commit", "retained-diff", "ue-binary"]
                + ["source:" + s["path"] for s in read("sources.json")]
                + ["compiler", "exact-method-fixture", "negative-control-fixture", "gnb-after", "ue-after"])
    require(names == expected and len(names) == len(set(names)) == 24, "command inventory/order")
    by_name = {r["name"]: r for r in records}
    previous = None
    for row in records:
        start, end = datetime.fromisoformat(row["started_at"]), datetime.fromisoformat(row["completed_at"])
        require(start <= end and (previous is None or previous <= start), "command chronology")
        previous = end
        require(row["returncode"] == (42 if row["name"] == "negative-control-fixture" else 0), "command return code")
        argv = row["argv"]
        if argv[:2] == ["docker", "run"]:
            prefix = ["docker", "run", "--rm", "--network=none", "--read-only", "--cap-drop=ALL",
                      "--security-opt=no-new-privileges", "--cpus=1", "--memory=256m"]
            require(argv[:len(prefix)] == prefix, "fixture container confinement")
            tail = argv[len(prefix):]
            if row["name"] in ("exact-method-fixture", "negative-control-fixture"):
                require(tail == ["--tmpfs", "/tmp:rw,exec,nosuid,nodev,size=32m", "-i", locked["derived_image_id"], "timeout", "25", "sh", "-lc",
                    "g++ -std=c++17 -Wall -Wextra -pedantic -x c++ - -o /tmp/packet-fixture && /tmp/packet-fixture"], "compile-only command")
            else:
                require(tail[:3] == [locked["derived_image_id"], "timeout", "15"], "pinned bounded source command")
                operation = tail[3:]
                allowed = [["g++", "--version"], ["git", "-C", "/usr/src/UERANSIM", "rev-parse", "HEAD"],
                           ["git", "-C", "/usr/src/UERANSIM", "diff", "--name-only"]]
                allowed += [["git", "-C", "/usr/src/UERANSIM", "show", "HEAD:" + path] for path in SOURCE_PATHS]
                require(operation in allowed and row["stdin_sha256"] is None, "read-only source operation")
        else:
            allowed = [["git", "rev-parse", "HEAD"], ["docker", "inspect", "safetwin5g-gnb"],
                       ["docker", "inspect", "safetwin5g-ue"], ["docker", "image", "inspect", locked["derived_image_id"]],
                       ["docker", "exec", "safetwin5g-ue", "timeout", "15", "sha256sum", "/opt/ueransim/bin/nr-ue"]]
            require(argv in allowed and row["stdin_sha256"] is None, "no service mutation")
    require(by_name["retained-commit"]["stdout"].strip() == locked["upstream_commit"], "upstream commit")
    require(by_name["retained-diff"]["stdout"].splitlines() == ["src/gnb/ngap/nnsf.cpp"], "only prior gNB source changed")
    require(by_name["ue-binary"]["stdout"].split() == [locked["unchanged_ue_sha256"], "/opt/ueransim/bin/nr-ue"], "UE binary unchanged")
    require(json.loads(by_name["derived-image"]["stdout"])[0]["Id"] == locked["derived_image_id"], "derived image")
    for name in ("gnb", "ue"):
        before, after = [json.loads(by_name[name + "-" + when]["stdout"])[0] for when in ("before", "after")]
        require(before["Id"] == after["Id"] and before["Image"] == after["Image"] == locked["official_image_id"], "official running identity")
        require(before["State"]["StartedAt"] == after["State"]["StartedAt"] and before["RestartCount"] == after["RestartCount"], "no service restart")
    sources = read("sources.json")
    require(len(sources) == 12 and {s["path"] for s in sources} == SOURCE_PATHS, "upstream source inventory")
    for row in sources:
        name = "upstream-" + row["path"].replace("/", "-")
        require(row["local"] == name and row["url"] == f"https://raw.githubusercontent.com/aligungr/UERANSIM/{locked['upstream_commit']}/{row['path']}", "official source URI")
        content = (run / name).read_bytes()
        require(content == (run / ("official-" + name)).read_bytes() == by_name["source:" + row["path"]]["stdout"].encode(), "official/image/raw equality")
        require(row["byte_identical"] and sha(content) == row["official_sha256"] == row["image_sha256"], "upstream source hashes")
    sap = (run / "upstream-src-ue-nas-sm-sap.cpp").read_text(encoding="utf-8")
    resource = (run / "upstream-src-ue-nas-sm-resource.cpp").read_text(encoding="utf-8")
    # Independent extraction by adjacent production function boundaries, not
    # the collector's balanced-brace implementation or diagnosis flags.
    uplink = "void NasSm::handleUplinkDataRequest(" + sap.split("void NasSm::handleUplinkDataRequest(", 1)[1].split("void NasSm::handleDownlinkDataRequest(", 1)[0].rstrip()
    status = "void NasSm::handleUplinkStatusChange(" + resource.split("void NasSm::handleUplinkStatusChange(", 1)[1].split("bool NasSm::anyUplinkDataPending(", 1)[0].rstrip()
    methods = uplink + "\n\n" + status
    require((run / "exact-methods.cpp").read_bytes() == methods.encode(), "exact production methods")
    template = (ROOT / "tools/packet_diagnosis/fixture.cpp").read_text(encoding="utf-8")
    fixture = template.replace("// UPSTREAM_METHODS", methods).encode()
    mutant = fixture.replace(b"if (m_mm->m_cmState == ECmState::CM_CONNECTED)", b"if (true)")
    for name, data, command in (("executed-fixture.cpp", fixture, "exact-method-fixture"), ("negative-control-fixture.cpp", mutant, "negative-control-fixture")):
        require((run / name).read_bytes() == data and by_name[command]["stdin_sha256"] == sha(data), "executed source linkage")
    require(by_name["exact-method-fixture"]["stdout"].splitlines() == ["FIXTURE_CASES=60 FAILURES=0", "IDLE_FIRST_PACKET_FORWARDED=0", "AFTER_CONNECT_INPUT_PACKET=2", "IDLE_BURST_REPLAYED=0", "NETWORK_PROOF=0"], "fixture results")
    require("FIXTURE_FAILURE=matrix forwarding" in by_name["negative-control-fixture"]["stderr"], "negative control detects changed behavior")
    summary = read("summary.json")
    require(summary["capture_completed"] and not summary["errors"] and summary["evidence_label"] == "fixture" and summary["new_network_trials"] == 0, "diagnostic status")
    require(all(summary[key] is False for key in ("r2_loss_location_uniquely_observed", "network_fix_applied", "network_fix_validated", "long_campaign_ready", "TNSM_ready", "live_actuation", "hardware_measured", "operator_validated")), "claim promotion")
    return {"audit_passed": True, "source_files_verified": 12, "commands_verified": 24, "exact_method_fixture_cases": 60,
            "negative_control_detected": True, "evidence_label": "fixture", "network_trials_added": 0,
            "r2_network_fix_validated": False, "r2_loss_location_uniquely_observed": False, "TNSM_ready": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", required=True)
    print(json.dumps(audit(parser.parse_args().run), indent=2))
