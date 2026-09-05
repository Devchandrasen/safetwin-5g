"""Read-only diagnosis of the rejected pilot; no injections, restart or analysis."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

from audit_recovery_pilot import replay_sample

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "evidence/engineering/20260905T051750Z-recovery-pilot-r1"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    output = ROOT / "evidence/engineering" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-recovery-pilot-r1-diagnosis")
    output.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((RUN / "manifest.json").read_text())["captured_file_sha256"]
    assert all(sha(RUN / name) == value for name, value in manifest.items())
    commands = {r["sequence"]: r for r in (json.loads(line) for line in (RUN / "commands.jsonl").read_text().splitlines())}
    samples = [json.loads(line) for line in (RUN / "samples.jsonl").read_text().splitlines()]
    replayed = [{"trial_id": s["trial_id"], "window": s["window"], "index": s["index"],
                 "clean": replay_sample(s, commands), "observed_at": s["observed_at"]} for s in samples]
    trial = json.loads((RUN / "trial-01.json").read_text())
    assert trial["passed"] is False and trial["recovery_clean"] is True
    assert len(replayed) == 9 and sum(r["clean"] for r in replayed) == 3
    assert not any(r["name"] in ("suspend-upf", "resume-watchdog") for r in commands.values())
    assert [r["argv"] for r in commands.values() if r["argv"][:2] == ["docker", "restart"]] == [["docker", "restart", "safetwin5g-ue"]]
    capture = []
    def cmd(name, argv, accepted=(0,)):
        started = datetime.now(timezone.utc).isoformat()
        result = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=25)
        row = {"name": name, "argv": argv, "started_at": started,
               "completed_at": datetime.now(timezone.utc).isoformat(),
               "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr}
        capture.append(row)
        (output / (name + ".json")).write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        if result.returncode not in accepted:
            raise RuntimeError(name + " failed")
        return result.stdout
    for container in ("safetwin5g-gnb", "safetwin5g-ue", "safetwin5g-open5gs"):
        cmd(container + "-history", ["docker", "logs", "--since", "2026-09-05T04:00:00Z", "--tail", "1000", container])
    cmd("current-containers", ["docker", "ps", "--format", "{{.Names}} {{.Status}}"])
    cmd("ue-processes", ["docker", "exec", "safetwin5g-ue", "ps", "-eo", "pid,args"])
    cmd("current-ping", ["docker", "exec", "safetwin5g-ue", "ping", "-I", "uesimtun0", "-c", "5", "-W", "1", "10.45.0.1"], (0, 1))
    source_records = []
    commit = "6bf5a1a96aaef6ae8778b9d8b477ac6e2bbf8156"
    for path in ("src/gnb/ngap/nas.cpp", "src/gnb/ngap/nnsf.cpp", "src/gnb/gtp/task.cpp", "LICENSE"):
        url = f"https://raw.githubusercontent.com/aligungr/UERANSIM/{commit}/{path}"
        content = urllib.request.urlopen(url, timeout=25).read()
        local = "upstream-" + path.replace("/", "-")
        (output / local).write_bytes(content)
        source_records.append({"url": url, "file": local, "sha256": sha(output / local), "retrieved_at": datetime.now(timezone.utc).isoformat()})
    # Static counterexample, not a packet-level reproduction or an upstream fix.
    nas = (output / "upstream-src-gnb-ngap-nas.cpp").read_text()
    nnsf = (output / "upstream-src-gnb-ngap-nnsf.cpp").read_text()
    assert "int32_t requestedSliceType = -1" in nas and "dynamic_cast<nas::RegistrationRequest *>" in nas
    assert "supportedSliceType == requestedSliceType" in nnsf and "return nullptr" in nnsf
    report = {
        "diagnostic_integrity_passed": True, "pilot_accepted": False,
        "pilot_manifest_sha256": sha(RUN / "manifest.json"),
        "raw_command_hashes_verified": all(hashlib.sha256(r["stdout"].encode()).hexdigest() == r["stdout_sha256"] for r in commands.values()),
        "raw_samples_replayed": replayed, "baseline_packets_received": 0, "baseline_packets_transmitted": 15,
        "primitive_packets_received": 0, "primitive_packets_transmitted": 15,
        "ue_restart_packets_received": 15, "ue_restart_packets_transmitted": 15,
        "faults_injected": 0, "approved_ue_restarts": 1,
        "ue_restart_step_seconds": trial["recovery_attempts"][-1]["elapsed_seconds"],
        "upstream_sources": source_records,
        "source_inspection_inference": "Non-RegistrationRequest Initial NAS retains requestedSliceType=-1; exact SST matching cannot select an AMF advertising SST 1. This is consistent with the recorded post-radio-link-failure Service Request and AMF-selection errors, not a unique causal proof of the initial radio loss.",
        "initial_radio_loss_cause": "unresolved",
        "network_fix_applied": False, "retry_run": False,
        "evidence_label": "sandbox-measured", "radio_evidence_label": "simulated",
        "source_counterexample_label": "fixture", "TNSM_ready": False,
        "long_campaign_ready": False, "live_actuation": False,
    }
    assert report["raw_command_hashes_verified"]
    (output / "diagnosis.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    hashes = {p.name: sha(p) for p in output.iterdir() if p.is_file()}
    (output / "manifest.json").write_text(json.dumps({"captured_file_sha256": hashes}, indent=2) + "\n", encoding="utf-8")
    print(output)
    print(json.dumps({"diagnostic_integrity_passed": True, "pilot_accepted": False, "samples_replayed": len(replayed), "faults_injected": 0}))


if __name__ == "__main__":
    main()
