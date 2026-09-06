"""Fresh raw-byte replay; keep failed development outcomes explicitly failed."""
from contextlib import ExitStack
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.verify_reconnect_r5_budget import replay_fresh, verify_lock, SOURCES, LOCK
from tools.verify_reconnect_r5_journal import save, sha


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--failed-development", action="append", default=[])
    parser.add_argument("--development", action="append", required=True)
    parser.add_argument("--final", required=True)
    args = parser.parse_args()
    verify_lock()
    results = []
    runs = [("failed-development", n, False) for n in args.failed_development]
    runs.extend(("development", n, True) for n in args.development)
    runs.append(("final", args.final, True))
    for label, directory, expected_pass in runs:
        root = (ROOT/directory).resolve()
        assert root.is_relative_to((ROOT/"evidence/verification").resolve())
        manifest = json.loads((root/"manifest.json").read_bytes())["captured_file_sha256"]
        assert set(manifest) == {p.name for p in root.iterdir() if p.is_file() and p.name != "manifest.json"}
        assert all(Path(n).name == n and sha((root/n).read_bytes()) == h for n, h in manifest.items())
        report = json.loads((root/"verification.json").read_bytes())
        assert report["verification_passed"] is expected_pass and report["development_only"] is (label != "final")
        assert report["checks"]["source-bytes-unchanged"]["passed"] is True
        assert report["checks"]["tests"]["passed"] is expected_pass
        assert report["evidence_label"] == "fixture" and report["measurement_scope"] == "synthetic-runner-budget-only"
        assert report["network_trials_executed"] == 0
        assert all(report[k] is False for k in ("network_execution_authorized", "whole_protocol_verified", "official_rollback_verified",
                   "network_fix_validated", "TNSM_ready", "actual_sleep_inhibition_requested", "new_native_clock_observation"))
        with zipfile.ZipFile(root/"sources.zip") as archive:
            assert len(archive.namelist()) == len(report["source_sha256"]) and set(archive.namelist()) == set(report["source_sha256"])
            assert all(sha(archive.read(n)) == h for n, h in report["source_sha256"].items())
            if label == "final":
                assert set(archive.namelist()) == set((*SOURCES, LOCK))
                assert all(archive.read(n) == (ROOT/n).read_bytes() for n in archive.namelist())
        cases = {}
        for name, entry in report["cases"].items():
            assert Path(name).name == name
            with tempfile.TemporaryDirectory(prefix="safetwin-r5-budget-release-") as temporary:
                target = Path(temporary)/"fresh"
                with zipfile.ZipFile(root/(name+".zip")) as archive:
                    assert len(archive.namelist()) == 2 and set(archive.namelist()) == {"clock.jsonl", "capture.json"}
                    members = {n: sha(archive.read(n)) for n in archive.namelist()}
                    if entry["passed"]:
                        assert members == entry["member_sha256"]
                    else:
                        assert label == "failed-development"
                    archive.extractall(target)
                assert all(sha((target/n).read_bytes()) == h for n, h in members.items())
                bundle = json.loads((target/"capture.json").read_bytes())
                assert bundle["case"] == name
                with ExitStack() as stack:
                    for predicate in ("RunnerBudget", "inventory"):
                        stack.enter_context(patch("sandbox.reconnect_r5_budget."+predicate,
                                                  side_effect=AssertionError("candidate forbidden during independent replay")))
                    replay_fresh(bundle, target)
                cases[name] = dict(raw_replay_passed=True, original_case_verification_passed=entry["passed"],
                                   expected_audit_error=bundle["audit_error"], member_sha256=members)
        results.append(dict(directory=directory, label=label, original_verification_passed=expected_pass,
                            original_failed_checks=[k for k, v in report["checks"].items() if not v["passed"]],
                            preservation_audit_passed=True, manifest_members=len(manifest), cases=cases))
    staged = [n for n in subprocess.check_output(["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"], cwd=ROOT).decode().split("\0") if n]
    assert staged
    for name in staged:
        assert not name.startswith(("evidence/private/", "evidence/engineering/20260905T111542Z-reconnect-r3-build/",
                                    "evidence/verification/20260825T081310Z-phase7-analysis-freeze/"))
        assert subprocess.check_output(["git", "show", ":"+name], cwd=ROOT) == (ROOT/name).read_bytes(), name
    output = ROOT/"evidence/engineering"/(datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")+"-reconnect-r5-budget-release")
    output.mkdir(exist_ok=False)
    save(output/"release.json", dict(release_audit_passed=True, results=results, runtime_predicates_disabled=True,
         staged_file_sha256={n: sha((ROOT/n).read_bytes()) for n in staged}, auditor_sha256=sha(Path(__file__).read_bytes()),
         evidence_label="fixture", network_trials_executed=0, network_fix_validated=False, whole_protocol_verified=False))
    save(output/"manifest.json", dict(captured_file_sha256={"release.json": sha((output/"release.json").read_bytes())}))
    print(json.dumps(dict(output=str(output), release_audit_passed=True, staged_files=len(staged),
                         cases_replayed=sum(len(r["cases"]) for r in results), failed_development_runs_preserved=len(args.failed_development))))


if __name__ == "__main__":
    main()
