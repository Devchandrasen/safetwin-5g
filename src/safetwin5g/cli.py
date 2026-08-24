"""Command-line entrypoint for the SafeTwin-5G foundation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

from .contracts import InterventionRecord
from .safety import SafetyPolicy
from .store import InterventionStore


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = PROJECT_ROOT / "config" / "actions.json"


def _command_status(command: list[str]) -> tuple[bool, str]:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)
    streams = [stream.strip() for stream in (completed.stdout, completed.stderr) if stream.strip()]
    output = "\n".join(streams) or f"command exited with code {completed.returncode}"
    return completed.returncode == 0, output


def doctor() -> int:
    docker_cli = shutil.which("docker")
    engine_ok = False
    engine_detail = "Docker CLI not found"
    if docker_cli:
        engine_ok, engine_detail = _command_status(
            [docker_cli, "info", "--format", "{{.ServerVersion}}"]
        )
    report = {
        "project": "SafeTwin-5G",
        "phase": 0,
        "python": sys.version.split()[0],
        "docker_cli": docker_cli,
        "docker_engine_running": engine_ok,
        "docker_engine_detail": engine_detail,
        "evidence_ceiling": "sandbox-measured" if engine_ok else "fixture",
        "next_gate": (
            "bring up pinned Open5GS/UERANSIM/Prometheus sandbox"
            if engine_ok
            else "start Docker Desktop and rerun doctor"
        ),
    }
    print(json.dumps(report, indent=2))
    return 0 if engine_ok else 2


def demo() -> int:
    example_path = PROJECT_ROOT / "examples" / "interventions.example.jsonl"
    record = InterventionStore(example_path).load()[0]
    evaluation = SafetyPolicy.from_path(DEFAULT_POLICY).evaluate(record)
    print(json.dumps({"record": record.to_dict(), "safety": evaluation.to_dict()}, indent=2))
    return 0


def validate_log(path: Path) -> int:
    records = InterventionStore(path).load()
    policy = SafetyPolicy.from_path(DEFAULT_POLICY)
    decisions: dict[str, int] = {}
    for record in records:
        decision = policy.evaluate(record).decision.value
        decisions[decision] = decisions.get(decision, 0) + 1
    print(json.dumps({"path": str(path), "records": len(records), "decisions": decisions}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="safetwin", description="SafeTwin-5G research CLI")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor", help="check local prerequisites and evidence ceiling")
    commands.add_parser("demo", help="evaluate the bundled safe-action example")
    validate = commands.add_parser("validate-log", help="validate a JSONL intervention log")
    validate.add_argument("path", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        return doctor()
    if args.command == "demo":
        return demo()
    if args.command == "validate-log":
        return validate_log(args.path)
    raise AssertionError(f"unhandled command: {args.command}")
