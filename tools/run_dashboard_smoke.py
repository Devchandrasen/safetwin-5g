"""Run an end-to-end smoke test against the local production dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DASHBOARD = ROOT / "dashboard"
PORT = 4173
BASE_URL = f"http://localhost:{PORT}"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def request(path: str, method: str = "GET") -> tuple[int, dict[str, str], bytes]:
    try:
        with urlopen(Request(BASE_URL + path, method=method), timeout=10) as response:
            return response.status, {key.lower(): value for key, value in response.headers.items()}, response.read()
    except HTTPError as error:
        return error.code, {key.lower(): value for key, value in error.headers.items()}, error.read()


def wait_until_ready(process: subprocess.Popen[str]) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"dashboard exited before readiness: {process.returncode}")
        try:
            if request("/")[0] == 200:
                return
        except OSError:
            pass
        time.sleep(0.25)
    raise RuntimeError("dashboard did not become ready within 30 seconds")


def listening_addresses(port: int) -> list[str]:
    result = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    addresses = []
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) < 4 or fields[0].upper() != "TCP" or fields[3].upper() != "LISTENING":
            continue
        local = fields[1]
        if not local.endswith(f":{port}"):
            continue
        host = local[1 : local.index("]")] if local.startswith("[") else local.rsplit(":", 1)[0]
        addresses.append(host)
    return sorted(set(addresses))


def all_loopback(addresses: list[str]) -> bool:
    return bool(addresses) and all(address in {"127.0.0.1", "::1"} for address in addresses)


def evaluate_payloads(status: dict[str, Any], proposals: dict[str, Any]) -> list[str]:
    errors = []
    if status["api_version"] != "v2":
        errors.append("status API is not the Phase 6 v2 contract")
    if status["overall_decision"]["model_promotion"] != "no-go":
        errors.append("status API does not preserve model-promotion no-go")
    if status["safety_lock"]["allow_live_actuation"] is not False:
        errors.append("status API does not preserve the live-actuation lock")
    if "records" in status["proposal_audit"]:
        errors.append("status summary unexpectedly includes proposal records")
    if status["dataset"]["record_count"] != 132:
        errors.append("status API does not expose the 132-unit locked dataset")
    if status["diagnostic_gate"]["finite_conformal_radius"] is not True:
        errors.append("status API does not expose the finite conformal diagnostic")
    records = proposals["records"]
    if proposals["proposal_count"] != 14 or len(records) != 14:
        errors.append("proposal API does not contain exactly 14 locked-test candidates")
    if proposals["eligible_count"] != 3:
        errors.append("proposal API does not report three offline-eligible candidates")
    if proposals["abstain_count"] != 11:
        errors.append("proposal API does not report 11 abstentions")
    if proposals["applied_action_count"] != 0:
        errors.append("proposal API reports a model-applied action")
    if sum(record["decision"] == "abstain" for record in records) != 11:
        errors.append("proposal records do not contain exactly 11 abstentions")
    if any(
        record["model_execution_status"] != "not-applied-offline-evaluation"
        for record in records
    ):
        errors.append("a proposal was represented as a model execution")
    return errors


def write_bundle(output: Path, report: dict[str, Any], server_log: str) -> None:
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (output / "server.log").write_text(server_log, encoding="utf-8")
    captured = {
        path.name: sha256(path)
        for path in sorted(output.iterdir())
        if path.is_file() and path.name != "manifest.json"
    }
    (output / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "run_id": report["run_id"],
                "passed": report["execution_passed"],
                "evidence_label": "fixture",
                "source_data_evidence_label": "sandbox-measured",
                "radio_evidence_label": "simulated",
                "captured_file_sha256": captured,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%SZ-dashboard-smoke-v1")
    output = ROOT / "evidence" / "product" / run_id
    output.mkdir(parents=True, exist_ok=False)
    process = subprocess.Popen(
        ["npm.cmd", "run", "start", "--", "--port", str(PORT)],
        cwd=DASHBOARD,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
    )
    checks: dict[str, Any] = {}
    errors: list[str] = []
    server_log = ""
    try:
        wait_until_ready(process)
        root_status, root_headers, root_body = request("/")
        status_code, status_headers, status_body = request("/api/status")
        proposals_code, proposals_headers, proposals_body = request("/api/proposals")
        status_payload = json.loads(status_body)
        proposal_payload = json.loads(proposals_body)
        addresses = listening_addresses(PORT)
        method_codes = {
            f"{method} {path}": request(path, method)[0]
            for path in ("/api/status", "/api/proposals")
            for method in ("POST", "PUT", "PATCH", "DELETE")
        }
        actuation_codes = {
            f"{method} /api/actuate": request("/api/actuate", method)[0]
            for method in ("GET", "POST", "PUT", "PATCH", "DELETE")
        }
        html = root_body.decode("utf-8", errors="replace")
        checks = {
            "root_status": root_status,
            "root_content_type": root_headers.get("content-type"),
            "root_contains_project_identity": "SafeTwin-5G" in html,
            "root_contains_live_lock": "Live actuation locked" in html,
            "root_contains_proposal_audit": "Proposal audit" in html,
            "root_contains_social_preview": "/og.png" in html,
            "status_api_status": status_code,
            "status_api_content_type": status_headers.get("content-type"),
            "status_api_nosniff": status_headers.get("x-content-type-options"),
            "proposal_api_status": proposals_code,
            "proposal_api_content_type": proposals_headers.get("content-type"),
            "proposal_api_nosniff": proposals_headers.get("x-content-type-options"),
            "proposal_count": proposal_payload["proposal_count"],
            "eligible_count": proposal_payload["eligible_count"],
            "abstain_count": proposal_payload["abstain_count"],
            "applied_action_count": proposal_payload["applied_action_count"],
            "listening_addresses": addresses,
            "all_listeners_loopback": all_loopback(addresses),
            "mutation_method_status_codes": method_codes,
            "actuation_route_status_codes": actuation_codes,
        }
        errors.extend(evaluate_payloads(status_payload, proposal_payload))
        if root_status != 200 or status_code != 200 or proposals_code != 200:
            errors.append("one or more read-only product routes did not return 200")
        for name in (
            "root_contains_project_identity",
            "root_contains_live_lock",
            "root_contains_proposal_audit",
            "root_contains_social_preview",
            "all_listeners_loopback",
        ):
            if not checks[name]:
                errors.append(f"failed check: {name}")
        if status_headers.get("x-content-type-options") != "nosniff":
            errors.append("status API lacks nosniff")
        if proposals_headers.get("x-content-type-options") != "nosniff":
            errors.append("proposal API lacks nosniff")
        if any(code != 405 for code in method_codes.values()):
            errors.append("a mutation method was not rejected with 405")
        if any(code != 404 for code in actuation_codes.values()):
            errors.append("an actuation route unexpectedly exists")
    except Exception as error:  # evidence is preserved even for a failed smoke run
        errors.append(f"{type(error).__name__}: {error}")
    finally:
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
        try:
            server_log = process.communicate(timeout=5)[0] or ""
        except subprocess.TimeoutExpired:
            process.kill()
            server_log = process.communicate()[0] or ""
    report = {
        "schema_version": 1,
        "run_id": run_id,
        "started_at": started.isoformat(),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "execution_passed": not errors,
        "checks": checks,
        "errors": errors,
        "evidence_label": "fixture",
        "source_data_evidence_label": "sandbox-measured",
        "radio_evidence_label": "simulated",
        "source_sha256": {
            "package_json": sha256(DASHBOARD / "package.json"),
            "package_lock": sha256(DASHBOARD / "package-lock.json"),
            "page": sha256(DASHBOARD / "app" / "page.tsx"),
            "status_api": sha256(DASHBOARD / "app" / "api" / "status" / "route.ts"),
            "proposals_api": sha256(DASHBOARD / "app" / "api" / "proposals" / "route.ts"),
            "status_snapshot": sha256(DASHBOARD / "app" / "data" / "status.json"),
            "smoke_harness": sha256(Path(__file__)),
        },
        "claim_boundary": (
            "Local production HTTP smoke test only. It verifies a read-only product "
            "surface over sandbox-derived data; it is not network, hardware, or operator evidence."
        ),
    }
    write_bundle(output, report, server_log)
    print(output)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["execution_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
