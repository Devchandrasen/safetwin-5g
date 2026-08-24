"""Audit completeness and provenance of a measured intervention bundle."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any

from verify_evidence import file_sha256, verify_bundle


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_COMMANDS = {
    "baseline-ping",
    "inject-fault",
    "fault-ping",
    "approved-action-clear-impairment",
    "post-action-ping",
    "rollback-reapply-fault",
    "rollback-ping",
    "final-cleanup",
    "final-ping",
}
TELEMETRY_STAGES = ("baseline", "fault", "post-action", "rollback", "final")
JOBS = ("amf", "smf", "upf")
IMAGES = (
    "safetwin5g/open5gs:2.7.7-318eeb49",
    "safetwin5g/ueransim:3.3.0-6bf5a1a9",
    "mongo:8.0.29-noble",
    "prom/prometheus:v3.13.2",
)


def aware_timestamp(value: str) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return False
    return parsed.tzinfo is not None


def run_capture(argv: list[str]) -> tuple[dict[str, Any], str]:
    started = datetime.now(timezone.utc).isoformat()
    result = subprocess.run(
        argv,
        cwd=ROOT,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    command = {
        "started_at": started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "argv": argv,
        "returncode": result.returncode,
    }
    if result.returncode != 0:
        raise RuntimeError(f"audit command failed ({result.returncode}): {argv}")
    return command, result.stdout


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("bundle", type=Path)
    args = parser.parse_args()
    source = args.bundle.resolve()
    started = datetime.now(timezone.utc)
    audit_id = started.strftime("%Y%m%dT%H%M%SZ-intervention-audit")
    output = ROOT / "evidence" / "audits" / audit_id
    output.mkdir(parents=True, exist_ok=False)

    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    record = json.loads(
        (source / "intervention-record.json").read_text(encoding="utf-8")
    )
    commands = [
        json.loads(line)
        for line in (source / "commands.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    command_names = {command["name"] for command in commands}
    command_times_valid = all(
        aware_timestamp(command.get("started_at"))
        and aware_timestamp(command.get("completed_at"))
        and datetime.fromisoformat(command["started_at"])
        <= datetime.fromisoformat(command["completed_at"])
        for command in commands
    )
    execution_times_valid = all(
        aware_timestamp(record["execution"][stage]["started_at"])
        for stage in ("fault", "approved_action", "rollback", "final_cleanup")
    )
    telemetry_files = [
        source / "telemetry" / f"{stage}-{job}-metrics.txt"
        for stage in TELEMETRY_STAGES
        for job in JOBS
    ]
    target_files = [
        source / "telemetry" / f"{stage}-prometheus-targets.json"
        for stage in TELEMETRY_STAGES
    ]
    telemetry_complete = all(path.is_file() and path.stat().st_size > 0 for path in telemetry_files)
    targets_complete = all(
        path.is_file()
        and len(json.loads(path.read_text(encoding="utf-8"))["data"]["activeTargets"])
        == 3
        and all(
            target["health"] == "up"
            for target in json.loads(path.read_text(encoding="utf-8"))["data"]["activeTargets"]
        )
        for path in target_files
    )
    approval = record["approval"]
    approval_text = approval["authorization_text"].encode("utf-8")
    approval_hash_valid = (
        hashlib.sha256(approval_text).hexdigest()
        == approval["authorization_text_sha256"]
    )

    config_hashes = manifest["configuration_sha256"]
    config_hashes_valid = all(
        (ROOT / relative).is_file() and file_sha256(ROOT / relative) == expected
        for relative, expected in config_hashes.items()
    )
    version_lock = json.loads(
        (ROOT / "sandbox" / "versions.lock.json").read_text(encoding="utf-8")
    )
    required_components = {"open5gs", "ueransim", "mongodb", "prometheus"}
    version_lock_complete = required_components.issubset(version_lock["components"])

    audit_commands: list[dict[str, Any]] = []
    command, docker_version = run_capture(
        ["docker", "version", "--format", "{{json .}}"]
    )
    audit_commands.append(command)
    (output / "docker-version.json").write_text(docker_version, encoding="utf-8")
    command, image_identities = run_capture(
        ["docker", "image", "inspect", *IMAGES, "--format", "{{json .}}"]
    )
    audit_commands.append(command)
    (output / "image-identities.jsonl").write_text(
        image_identities, encoding="utf-8"
    )
    images = [json.loads(line) for line in image_identities.splitlines() if line]
    image_identity_complete = len(images) == 4 and all(image.get("Id") for image in images)
    open5gs_pin_matches = any(
        image.get("Config", {}).get("Labels", {}).get("safetwin5g.upstream.commit")
        == version_lock["components"]["open5gs"]["commit"]
        for image in images
    )
    ueransim_pin_matches = any(
        image.get("Config", {}).get("Labels", {}).get("safetwin5g.upstream.commit")
        == version_lock["components"]["ueransim"]["commit"]
        for image in images
    )
    mongo_digest = version_lock["components"]["mongodb"]["digest"]
    prometheus_digest = version_lock["components"]["prometheus"]["digest"]
    upstream_digests_match = any(
        any(mongo_digest in digest for digest in image.get("RepoDigests", []))
        for image in images
    ) and any(
        any(prometheus_digest in digest for digest in image.get("RepoDigests", []))
        for image in images
    )

    checks = {
        "source_bundle_hashes_complete": not verify_bundle(source),
        "source_manifest_passed": manifest.get("passed") is True,
        "source_label_sandbox_measured": manifest.get("evidence_label") == "sandbox-measured",
        "configuration_hashes_match": config_hashes_valid,
        "required_commands_recorded": REQUIRED_COMMANDS.issubset(command_names),
        "command_timestamps_valid": command_times_valid,
        "execution_timestamps_valid": execution_times_valid,
        "telemetry_stage_job_matrix_complete": telemetry_complete,
        "three_prometheus_targets_up_at_each_stage": targets_complete,
        "approval_hash_valid": approval_hash_valid,
        "approval_status_approved": approval.get("approval_status") == "approved",
        "version_lock_complete": version_lock_complete,
        "four_running_image_identities_captured": image_identity_complete,
        "open5gs_source_commit_matches_lock": open5gs_pin_matches,
        "ueransim_source_commit_matches_lock": ueransim_pin_matches,
        "mongodb_and_prometheus_digests_match_lock": upstream_digests_match,
        "claim_boundaries_explicit": record.get("claim_boundaries")
        == {
            "intervention": "sandbox-measured",
            "radio_access": "simulated",
            "hardware": "not measured",
            "operator_validation": "not performed",
            "model_scores": "not applicable; deterministic runbook",
        },
    }
    passed = all(checks.values())
    report = {
        "schema_version": 1,
        "audit_id": audit_id,
        "source_bundle": str(source.relative_to(ROOT)).replace("\\", "/"),
        "source_manifest_sha256": file_sha256(source / "manifest.json"),
        "started_at": started.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "evidence_label": "sandbox-measured" if passed else "simulated",
        "claim_boundary": (
            "Audit of an isolated software-sandbox intervention; radio remains simulated, "
            "with no hardware measurement or operator validation."
        ),
        "checks": checks,
        "component_versions": {
            name: version_lock["components"][name] for name in sorted(required_components)
        },
        "source_configuration_sha256": config_hashes,
    }
    (output / "audit-report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "audit-commands.jsonl").write_text(
        "".join(json.dumps(command, sort_keys=True) + "\n" for command in audit_commands),
        encoding="utf-8",
    )
    captured = {
        str(path.relative_to(output)).replace("\\", "/"): file_sha256(path)
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "manifest.json"
    }
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "audit_id": audit_id,
                "passed": passed,
                "evidence_label": report["evidence_label"],
                "captured_file_sha256": captured,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(output)
    print(json.dumps(checks, indent=2, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
