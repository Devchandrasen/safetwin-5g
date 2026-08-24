"""Capture a self-describing evidence bundle from the local sandbox.

This command records observations; it does not infer that the full
``sandbox-measured`` claim gate has passed. Stack and baseline captures remain
``simulated`` until a logged, approved, reversible action and rollback exist.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "sandbox" / "compose.yaml"
CONTAINERS = {
    "mongodb": "safetwin5g-mongodb",
    "open5gs": "safetwin5g-open5gs",
    "gnb": "safetwin5g-gnb",
    "ue": "safetwin5g-ue",
    "prometheus": "safetwin5g-prometheus",
}
CONFIG_PATHS = (
    "sandbox/versions.lock.json",
    "sandbox/compose.yaml",
    "sandbox/run.ps1",
    "sandbox/capture_evidence.py",
    "sandbox/docker/open5gs/Dockerfile",
    "sandbox/docker/open5gs/configure.py",
    "sandbox/docker/open5gs/entrypoint.sh",
    "sandbox/docker/ueransim/Dockerfile",
    "sandbox/config/mongodb/10-subscriber.js",
    "sandbox/config/prometheus/prometheus.yml",
    "sandbox/config/ueransim/gnb.yaml",
    "sandbox/config/ueransim/ue.yaml",
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", choices=("stack", "baseline"), required=True)
    args = parser.parse_args()

    started = utc_now()
    run_id = started.strftime("%Y%m%dT%H%M%SZ") + f"-{args.stage}"
    output_dir = ROOT / "evidence" / "sandbox" / run_id
    logs_dir = output_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=False)
    commands: list[dict[str, object]] = []

    def run(
        name: str,
        command: list[str],
        *,
        output_file: str,
        required: bool = True,
    ) -> str:
        observed = utc_now().isoformat()
        result = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        destination = output_dir / output_file
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(result.stdout, encoding="utf-8")
        commands.append(
            {
                "name": name,
                "observed_at": observed,
                "argv": command,
                "returncode": result.returncode,
                "output_file": output_file.replace("\\", "/"),
            }
        )
        if required and result.returncode != 0:
            raise RuntimeError(f"{name} failed with exit code {result.returncode}")
        return result.stdout

    try:
        run("git-head", ["git", "rev-parse", "HEAD"], output_file="git-head.txt")
        run(
            "git-status",
            ["git", "status", "--short"],
            output_file="git-status.txt",
        )
        run(
            "docker-version",
            ["docker", "version", "--format", "{{json .}}"],
            output_file="docker-version.json",
        )
        compose_ps = run(
            "compose-status",
            [
                "docker",
                "compose",
                "-f",
                str(COMPOSE),
                "ps",
                "--format",
                "json",
            ],
            output_file="compose-ps.jsonl",
        )
        states_text = run(
            "container-states",
            [
                "docker",
                "inspect",
                *CONTAINERS.values(),
                "--format",
                "{{json .State}}",
            ],
            output_file="container-states.jsonl",
        )
        image_text = run(
            "image-identities",
            [
                "docker",
                "image",
                "inspect",
                "safetwin5g/open5gs:2.7.7-318eeb49",
                "safetwin5g/ueransim:3.3.0-6bf5a1a9",
                "mongo:8.0.29-noble",
                "prom/prometheus:v3.13.2",
                "--format",
                "{{json .}}",
            ],
            output_file="image-identities.jsonl",
        )
        run(
            "open5gs-package-versions",
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "dpkg-query",
                "safetwin5g/open5gs:2.7.7-318eeb49",
                "-W",
                "-f=${binary:Package}\\t${Version}\\n",
            ],
            output_file="open5gs-packages.tsv",
        )
        run(
            "ueransim-package-versions",
            [
                "docker",
                "run",
                "--rm",
                "--entrypoint",
                "dpkg-query",
                "safetwin5g/ueransim:3.3.0-6bf5a1a9",
                "-W",
                "-f=${binary:Package}\\t${Version}\\n",
            ],
            output_file="ueransim-packages.tsv",
        )
        ue_log = ""
        core_log = ""
        for service, container in CONTAINERS.items():
            log = run(
                f"{service}-log",
                ["docker", "logs", "--timestamps", container],
                output_file=f"logs/{service}.log",
            )
            if service == "ue":
                ue_log = log
            elif service == "open5gs":
                core_log = log

        ue_interface = run(
            "ue-pdu-interface",
            [
                "docker",
                "exec",
                CONTAINERS["ue"],
                "ip",
                "-details",
                "address",
                "show",
                "uesimtun0",
            ],
            output_file="ue-interface.txt",
        )
        baseline_measurements: dict[str, object] = {}
        if args.stage == "baseline":
            ue_status = run(
                "ue-registration-status",
                [
                    "docker",
                    "exec",
                    CONTAINERS["ue"],
                    "/opt/ueransim/bin/nr-cli",
                    "imsi-999700000000001",
                    "-e",
                    "status",
                ],
                output_file="ue-registration-status.txt",
            )
            pdu_status = run(
                "ue-pdu-session-status",
                [
                    "docker",
                    "exec",
                    CONTAINERS["ue"],
                    "/opt/ueransim/bin/nr-cli",
                    "imsi-999700000000001",
                    "-e",
                    "ps-list",
                ],
                output_file="ue-pdu-session-status.txt",
            )
            ping = run(
                "pdu-user-plane-ping",
                [
                    "docker",
                    "exec",
                    CONTAINERS["ue"],
                    "ping",
                    "-I",
                    "uesimtun0",
                    "-c",
                    "20",
                    "-i",
                    "0.2",
                    "-W",
                    "2",
                    "10.45.0.1",
                ],
                output_file="pdu-user-plane-ping.txt",
            )
            packet_match = re.search(
                r"(\d+) packets transmitted, (\d+) received, "
                r"([\d.]+)% packet loss",
                ping,
            )
            rtt_match = re.search(
                r"rtt min/avg/max/mdev = "
                r"([\d.]+)/([\d.]+)/([\d.]+)/([\d.]+) ms",
                ping,
            )
            if not packet_match or not rtt_match:
                raise RuntimeError("could not parse baseline ping statistics")
            baseline_measurements = {
                "ping_destination": "10.45.0.1",
                "ping_source_interface": "uesimtun0",
                "packets_transmitted": int(packet_match.group(1)),
                "packets_received": int(packet_match.group(2)),
                "packet_loss_pct": float(packet_match.group(3)),
                "rtt_min_ms": float(rtt_match.group(1)),
                "rtt_avg_ms": float(rtt_match.group(2)),
                "rtt_max_ms": float(rtt_match.group(3)),
                "rtt_mdev_ms": float(rtt_match.group(4)),
            }
        run(
            "subscriber-public-fields",
            [
                "docker",
                "exec",
                CONTAINERS["mongodb"],
                "mongosh",
                "open5gs",
                "--quiet",
                "--eval",
                "JSON.stringify(db.subscribers.findOne({imsi:'999700000000001'},"
                "{_id:0,imsi:1,slice:1}))",
            ],
            output_file="subscriber-public.json",
        )

        targets_text = run(
            "prometheus-targets",
            [
                "docker",
                "exec",
                CONTAINERS["open5gs"],
                "curl",
                "--fail",
                "--silent",
                "http://10.53.0.6:9090/api/v1/targets",
            ],
            output_file="prometheus-targets.json",
        )
        prometheus_targets = json.loads(targets_text)

        states = [json.loads(line) for line in states_text.splitlines() if line]
        targets = prometheus_targets["data"]["activeTargets"]
        checks = {
            "all_containers_running": len(states) == len(CONTAINERS)
            and all(state["Status"] == "running" for state in states),
            "all_healthchecks_healthy": len(states) == len(CONTAINERS)
            and all(state.get("Health", {}).get("Status") == "healthy" for state in states),
            "ue_registration_success": "Initial Registration is successful" in ue_log,
            "pdu_session_success": "PDU Session establishment is successful" in ue_log,
            "ue_tun_address_present": "10.45.0.2/24" in ue_interface,
            "open5gs_no_lost_heartbeat": "No heartbeat" not in core_log,
            "open5gs_no_http2_framing_error": "HTTP2 framing" not in core_log,
            "prometheus_three_targets_up": len(targets) == 3
            and all(target["health"] == "up" for target in targets),
            "compose_lists_all_services": all(
                container in compose_ps for container in CONTAINERS.values()
            ),
            "four_image_identities_recorded": len(
                [line for line in image_text.splitlines() if line]
            )
            == 4,
        }
        if args.stage == "baseline":
            checks.update(
                {
                    "ue_cli_registered": "rm-state: RM-REGISTERED" in ue_status,
                    "ue_cli_normal_service": (
                        "mm-state: MM-REGISTERED/NORMAL-SERVICE" in ue_status
                    ),
                    "pdu_session_active": "state: PS-ACTIVE" in pdu_status,
                    "pdu_session_address_matches_tun": (
                        "address: 10.45.0.2" in pdu_status
                    ),
                    "twenty_ping_packets_received": (
                        baseline_measurements["packets_transmitted"] == 20
                        and baseline_measurements["packets_received"] == 20
                    ),
                    "zero_baseline_packet_loss": (
                        baseline_measurements["packet_loss_pct"] == 0.0
                    ),
                }
            )
        passed = all(checks.values())

        command_path = output_dir / "commands.jsonl"
        command_path.write_text(
            "".join(json.dumps(command, sort_keys=True) + "\n" for command in commands),
            encoding="utf-8",
        )
        captured_files = [
            path
            for path in output_dir.rglob("*")
            if path.is_file() and path.name != "manifest.json"
        ]
        manifest = {
            "schema_version": 1,
            "run_id": run_id,
            "stage": args.stage,
            "started_at": started.isoformat(),
            "completed_at": utc_now().isoformat(),
            "evidence_label": "simulated",
            "claim_boundary": (
                "Versioned UERANSIM radio plus measured software-sandbox runtime. "
                "Not sandbox-measured under PROJECT_LOCK.md until an approved "
                "fault/action/rollback record passes."
            ),
            "passed": passed,
            "checks": checks,
            "measurements": baseline_measurements,
            "configuration_sha256": {
                relative: sha256(ROOT / relative) for relative in CONFIG_PATHS
            },
            "captured_file_sha256": {
                str(path.relative_to(output_dir)).replace("\\", "/"): sha256(path)
                for path in sorted(captured_files)
            },
        }
        (output_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(output_dir)
        print(json.dumps(checks, indent=2, sort_keys=True))
        return 0 if passed else 2
    except Exception as exc:
        command_path = output_dir / "commands.jsonl"
        command_path.write_text(
            "".join(json.dumps(command, sort_keys=True) + "\n" for command in commands),
            encoding="utf-8",
        )
        (output_dir / "capture-error.txt").write_text(
            f"{type(exc).__name__}: {exc}\n", encoding="utf-8"
        )
        captured_files = [
            path for path in output_dir.rglob("*") if path.is_file()
        ]
        (output_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "run_id": run_id,
                    "stage": args.stage,
                    "started_at": started.isoformat(),
                    "completed_at": utc_now().isoformat(),
                    "evidence_label": "simulated",
                    "passed": False,
                    "error": f"{type(exc).__name__}: {exc}",
                    "captured_file_sha256": {
                        str(path.relative_to(output_dir)).replace("\\", "/"): sha256(path)
                        for path in sorted(captured_files)
                    },
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"evidence capture failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
