"""One read-only post-stop official-service observation, not an R4 retry.

Never resets, changes images, injects faults, clears a qdisc or changes clocks.
Original execution/rollback verdicts are not edited or upgraded.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sandbox.run_reconnect_r4 import save, append, sha, COMMANDS, IMAGES, UE, GNB
from sandbox.reconnect_r3_measurement import CONTAINERS, NETWORK, INSPECT_FORMAT
from sandbox.reconnect_r4_collection import INSPECT, command_plan
from sandbox.reconnect_r4_process import BoundedProcess, complete

RUN = ROOT / "evidence/engineering/20260905T170131Z-reconnect-r4-network"


def plan():
    identities = ["docker", "inspect", "--format", INSPECT, UE, GNB]
    address = command_plan(10091)[2]
    commands = [("before-network", ["docker", "network", "inspect", NETWORK]),
                ("before-containers", ["docker", "inspect", "--format", INSPECT_FORMAT, *CONTAINERS]),
                ("before-identities", identities), ("before-address", address)]
    for identifier in (10091, 10092, 10093):
        commands.append(("service-" + str(identifier), command_plan(identifier)[7]))
    for name in ("sample-qdisc", "upf-state", "stress-workers", "targets", "rollback-inspect-eth0"):
        commands.append((name, COMMANDS[name]))
    commands += [("after-ue-log", ["docker", "logs", "--timestamps", "--tail", "2000", UE]),
                 ("after-gnb-log", ["docker", "logs", "--timestamps", "--tail", "2000", GNB]),
                 ("after-address", address), ("after-identities", identities),
                 ("after-network", ["docker", "network", "inspect", NETWORK]),
                 ("after-containers", ["docker", "inspect", "--format", INSPECT_FORMAT, *CONTAINERS])]
    return commands


def main():
    if not (RUN / "manifest.json").exists() or (ROOT / "evidence/private/reconnect-r4-runtime.lock").exists():
        raise PermissionError("original R4 run must be stopped and sealed")
    if any((ROOT / "evidence/engineering").glob("*-reconnect-r4-aftercare")):
        raise PermissionError("post-stop observation already exists; do not repeat")
    output = ROOT / "evidence/engineering" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-reconnect-r4-aftercare")
    output.mkdir(exist_ok=False)
    commands, rows, errors = plan(), [], []
    adapter = BoundedProcess([argv for _, argv in commands])
    save(output / "design.json", {"purpose": "later-read-only-official-service-observation-not-R4-retry",
                                 "original_run": RUN.relative_to(ROOT).as_posix(), "original_manifest_sha256": sha((RUN / "manifest.json").read_bytes()),
                                 "source_sha256": sha(Path(__file__).read_bytes()), "commands": commands,
                                 "evidence_label": "sandbox-measured", "radio_evidence_label": "simulated",
                                 "mutations_authorized": False, "original_R4_verdict_unchanged": True,
                                 "R4_clock_consistency_acceptance_claimed": False})
    for sequence, (name, argv) in enumerate(commands, 1):
        if name.startswith("service-"):
            append(output / "identifiers.jsonl", {"identifier": int(name.removeprefix("service-")), "sequence": sequence})
        append(output / "intents.jsonl", {"sequence": sequence, "name": name, "argv": argv})
        row = adapter.run(argv, sequence=sequence)
        row["name"] = name
        rows.append(row)
        append(output / "commands.jsonl", row)
        if not complete(row) or row["returncode"] not in ((0, 1) if name.startswith("service-") else (0,)):
            errors.append(name + ": command incomplete/failed")
            break
        if name == "before-identities":
            states = [json.loads(line) for line in row["stdout"].splitlines()]
            if len(states) != 2 or any(s["Image"] != IMAGES["official_image_id"] or s["Running"] is not True for s in states):
                errors.append("official images required before packet observation")
                break
    save(output / "capture.json", {"capture_complete": len(rows) == len(commands) and not errors, "errors": errors,
                                  "command_records": len(rows), "mutations_executed": 0, "original_R4_verdict_unchanged": True})
    save(output / "manifest.json", {"captured_file_sha256": {p.name: sha(p.read_bytes()) for p in output.iterdir() if p.is_file()}})
    print(json.dumps({"output": str(output), "commands": len(rows), "errors": errors}))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
